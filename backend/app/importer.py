import hashlib
import io
import json
import re
import zipfile
from datetime import datetime

from openpyxl import load_workbook

from .db import DomainError, audit, encode, now, transaction
from .extraction import local_extract
from .repository import create_message

HEADERS = {
    'Заявки': ['№', 'Время', 'Канал', 'Кто обращается', 'Текст обращения'],
    'Оборудование': ['Код', 'Клиент', 'Адрес', 'Модель', 'Серийный номер', 'Дата установки', 'Последний визит', 'Результат последнего визита'],
    'Запчасти': ['Код', 'Деталь', 'Подходит для моделей', 'Москва: на складе, шт', 'Москва: резерв, шт', 'Тула: на складе, шт', 'Тула: резерв, шт'],
    'Правила': ['№', 'Тема', 'Правило'],
}


def text(value):
    return str(value).strip() if value is not None else ''


def parse_date(value, optional=False):
    if not value and optional:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return datetime.strptime(text(value), '%d.%m.%Y').date().isoformat()


def parse_workbook(content):
    errors, warnings, parsed = [], [], {}
    if len(content) > 10 * 1024 * 1024:
        raise ValueError('Файл больше 10 МБ.')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 40 * 1024 * 1024 or len(archive.infolist()) > 500:
            raise ValueError('Превышен допустимый размер распакованного Excel.')
        if any('vbaProject' in i.filename for i in archive.infolist()):
            raise ValueError('Макросы не поддерживаются. Сохраните файл как .xlsx без макросов.')
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
    try:
        for name, headers in HEADERS.items():
            if name not in workbook.sheetnames:
                errors.append({'cell': name, 'message': 'Обязательный лист отсутствует.'})
                continue
            sheet = workbook[name]
            if sheet.max_row > 10003 or sheet.max_column > 30:
                errors.append({'cell': name, 'message': 'Лимит пилота: 10 000 строк и 30 столбцов на лист.'})
                continue
            rows = list(sheet.iter_rows())
            header_index = next((i for i, row in enumerate(rows[:10]) if [text(c.value) for c in row[:len(headers)]] == headers), None)
            if header_index is None:
                errors.append({'cell': name, 'message': 'Заголовки не совпадают с шаблоном: ' + ', '.join(headers)})
                continue
            parsed[name] = []
            seen = set()
            for row in rows[header_index + 1:]:
                values = [c.value for c in row[:len(headers)]]
                if not any(v is not None for v in values):
                    continue
                ref = f'{name}!A{row[0].row}:{row[len(headers)-1].column_letter}{row[0].row}'
                try:
                    if any(c.data_type == 'f' for c in row):
                        raise ValueError('Формулы не импортируются; замените их проверенными значениями.')
                    key = text(values[0])
                    if not key or key in seen:
                        raise ValueError('Пустой или повторяющийся код строки.')
                    seen.add(key)
                    if name == 'Оборудование':
                        if not all(text(v) for v in values[:6]):
                            raise ValueError('Нужны код, клиент, адрес, модель, номер и дата установки.')
                        if not re.fullmatch(r'[CС]\d{3,4}', text(values[3])):
                            raise ValueError('Модель должна иметь вид C100.')
                        record = dict(zip(['id', 'client', 'address', 'model', 'serial'], map(text, values[:5])))
                        record['model'] = record['model'].replace('С', 'C')
                        record.update(installed_at=parse_date(values[5]), last_visit=parse_date(values[6], True), history=text(values[7]))
                        if record['last_visit'] and record['last_visit'] < record['installed_at']:
                            raise ValueError('Визит раньше установки. Проверьте даты.')
                        if not record['history']:
                            warnings.append({'cell': ref, 'message': 'История визитов не предоставлена; не будет восстановлена догадкой.'})
                    elif name == 'Запчасти':
                        if not all(text(v) for v in values[:3]):
                            raise ValueError('Нужны код, название и совместимые модели.')
                        counts = []
                        for v in values[3:7]:
                            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or int(v) != v:
                                raise ValueError('Остаток и резерв должны быть целыми неотрицательными числами.')
                            counts.append(int(v))
                        if counts[1] > counts[0] or counts[3] > counts[2]:
                            raise ValueError('Исходный резерв больше физического остатка.')
                        models = [m.strip().replace('С', 'C') for m in text(values[2]).split(',')]
                        if any(not re.fullmatch(r'C\d{3,4}', m) for m in models):
                            raise ValueError('Некорректная совместимая модель.')
                        record = {'sku': key, 'name': text(values[1]), 'models': models, 'counts': counts}
                    elif name == 'Правила':
                        if not all(text(v) for v in values):
                            raise ValueError('Правило должно содержать номер, тему и текст.')
                        record = dict(zip(['code', 'topic', 'text'], map(text, values)))
                    else:
                        if not all(text(v) for v in values):
                            raise ValueError('Все поля обращения обязательны.')
                        year_match = re.search(r'20\d{2}', text(rows[0][0].value))
                        if not year_match:
                            raise ValueError('Год обращений должен быть указан в заголовке A1.')
                        received = datetime.strptime(f'{text(values[1])} {year_match.group()}', '%d.%m %H:%M %Y').isoformat() + '+03:00'
                        record = {'external_id': key, 'received_at': received, 'channel': text(values[2]), 'sender': text(values[3]), 'text': text(values[4])}
                    record['source_ref'] = ref
                    parsed[name].append(record)
                except (ValueError, TypeError, IndexError) as exc:
                    errors.append({'cell': ref, 'message': str(exc)})
        equipment = parsed.get('Оборудование', [])
        serials = [e['serial'] for e in equipment]
        if len(serials) != len(set(serials)):
            errors.append({'cell': 'Оборудование!E', 'message': 'Повторяющийся серийный номер.'})
        if any(not parsed.get(name) for name in HEADERS):
            errors.append({'cell': 'Книга', 'message': 'Каждый обязательный лист должен содержать хотя бы одну строку данных.'})
    finally:
        workbook.close()
    return parsed, errors, warnings


def import_excel(conn, content, filename, source='upload', actor='Диспетчер'):
    digest = hashlib.sha256(content).hexdigest()
    prior = conn.execute('SELECT * FROM imports WHERE sha256=?', (digest,)).fetchone()
    if prior:
        previous_report = json.loads(prior['report'])
        return {**previous_report, 'id': prior['id'], 'duplicate_file': True,
                'created': {key: 0 for key in previous_report.get('created', {})},
                'skipped': sum(previous_report.get('counts', {}).values()) if previous_report['status'] == 'success' else 0}
    report = {'filename': filename, 'sha256': digest, 'source': source, 'created_at': now(), 'duplicate_file': False,
              'counts': {}, 'created': {'equipment': 0, 'parts': 0, 'rules': 0, 'messages': 0}, 'skipped': 0, 'errors': [], 'warnings': [], 'status': 'success'}
    try:
        if not filename.lower().endswith('.xlsx'):
            raise ValueError('Нужен Excel .xlsx. Другие форматы не поддерживаются.')
        parsed, report['errors'], report['warnings'] = parse_workbook(content)
        report['counts'] = {name: len(rows) for name, rows in parsed.items()}
    except Exception as exc:
        parsed = {}
        report['errors'] = [{'cell': 'Файл', 'message': str(exc) if isinstance(exc, ValueError) else 'Не удалось прочитать Excel. Проверьте, что файл не повреждён.'}]
    if not report['errors']:
        try:
            with transaction(conn):
                cur = conn.execute('INSERT INTO imports(filename,sha256,source,created_at,report) VALUES(?,?,?,?,?)',
                                   (filename, digest, source, report['created_at'], '{}'))
                report['id'] = cur.lastrowid
                for eq in parsed['Оборудование']:
                    old = conn.execute('SELECT * FROM equipment WHERE id=? OR serial=?', (eq['id'], eq['serial'])).fetchone()
                    if old:
                        if any(old[k] != eq[k] for k in ('id', 'client', 'address', 'model', 'serial', 'installed_at', 'last_visit', 'history')):
                            raise DomainError('import_conflict', 'Данные машины изменились. Пилот не перезаписывает справочники при повторном импорте.', details={'cell': eq['source_ref']})
                        report['skipped'] += 1
                        continue
                    conn.execute('INSERT INTO equipment VALUES(?,?,?,?,?,?,?,?,?,?)',
                                 tuple(eq[k] for k in ('id', 'client', 'address', 'model', 'serial', 'installed_at', 'last_visit', 'history', 'source_ref')) + (source,))
                    report['created']['equipment'] += 1
                for part in parsed['Запчасти']:
                    old = conn.execute('SELECT * FROM parts WHERE sku=?', (part['sku'],)).fetchone()
                    stocks = [part['sku'], 'Москва', *part['counts'][:2]], [part['sku'], 'Тула', *part['counts'][2:]]
                    if old:
                        same = old['name'] == part['name'] and json.loads(old['models']) == part['models']
                        for sku, warehouse, on_hand, external in stocks:
                            s = conn.execute('SELECT * FROM stock WHERE sku=? AND warehouse=?', (sku, warehouse)).fetchone()
                            same = same and s is not None and s['on_hand'] == on_hand and s['external_reserved'] == external
                        if not same:
                            raise DomainError('import_conflict', 'Деталь или складской снимок изменились. Автоматическая перезапись остатков запрещена.', details={'cell': part['source_ref']})
                        report['skipped'] += 1
                        continue
                    conn.execute('INSERT INTO parts VALUES(?,?,?,?)', (part['sku'], part['name'], encode(part['models']), part['source_ref']))
                    conn.executemany('INSERT INTO stock VALUES(?,?,?,?)', stocks)
                    report['created']['parts'] += 1
                for rule in parsed['Правила']:
                    old = conn.execute('SELECT * FROM rules WHERE code=?', (rule['code'],)).fetchone()
                    if old:
                        if old['text'] != rule['text'] or old['topic'] != rule['topic']:
                            raise DomainError('import_conflict', 'Правило изменилось. Требуется обновление и проверка бизнес-логики.', details={'cell': rule['source_ref']})
                        report['skipped'] += 1
                        continue
                    conn.execute('INSERT INTO rules VALUES(?,?,?,?)', tuple(rule[k] for k in ('code', 'topic', 'text', 'source_ref')))
                    report['created']['rules'] += 1
                for message in parsed['Заявки']:
                    key = 'excel:' + message['external_id']
                    old = conn.execute('SELECT * FROM messages WHERE external_key=?', (key,)).fetchone()
                    if old and any(old[k] != message[k] for k in ('sender', 'channel', 'text', 'received_at')):
                        raise DomainError('import_conflict', 'Обращение с этим номером уже существует с другим содержимым. Исходный текст не перезаписывается.', details={'cell': message['source_ref']})
                    _, created = create_message(conn, **message, source=source, external_key=key, import_id=report['id'],
                                                analysis=local_extract(message['text'], message['sender']), actor=actor)
                    report['created']['messages'] += int(created)
                    report['skipped'] += int(not created)
                conn.execute('UPDATE imports SET report=? WHERE id=?', (encode(report), report['id']))
                audit(conn, 'excel_imported', {'id': report['id'], 'filename': filename, 'created': report['created']}, actor=actor)
            return report
        except DomainError as exc:
            report['errors'] = [{'cell': (exc.details or {}).get('cell', 'Книга'), 'message': exc.message}]
            report['created'] = {key: 0 for key in report['created']}
            report['skipped'] = 0
    report['status'] = 'error'
    with transaction(conn):
        cur = conn.execute('INSERT INTO imports(filename,sha256,source,created_at,report) VALUES(?,?,?,?,?)',
                           (filename, digest, source, report['created_at'], encode(report)))
        report['id'] = cur.lastrowid
        conn.execute('UPDATE imports SET report=? WHERE id=?', (encode(report), report['id']))
        audit(conn, 'excel_import_failed', {'id': report['id'], 'errors': report['errors']}, actor=actor)
    return report
