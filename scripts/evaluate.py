"""Reproducible paired comparison. No LLM calls and no self-grading by a model."""
import csv
import hashlib
import json
import platform
import re
import statistics
import sys
from pathlib import Path
from time import perf_counter

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.extraction import local_extract
from backend.app.matching import match_equipment


def canonical(value):
    return re.sub(r'\s+', '', value.upper().replace('С', 'C').replace('Е', 'E').replace('Ё', 'Е'))


def verify_source(reference, workbook, path):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == reference['source_sha256'], 'The source changed; re-review labels.'
    rows = list(workbook['Оборудование'].iter_rows(min_row=4, values_only=True))
    registry = {r[0]: r for r in rows if r[0]}
    source_messages = {r[0]: r for r in workbook['Заявки'].iter_rows(min_row=4, values_only=True) if r[0]}
    checked_fields = 0
    for item in reference['records']:
        if item['split'] == 'case':
            assert source_messages[item['id']][3:5] == (item['sender'], item['text'])
        compact = canonical(item['text'])
        for key, values in item['fields'].items():
            for value in values:
                assert canonical(value) in compact, (item['id'], key, value, 'unsupported literal label')
                checked_fields += 1
        for evidence in item['registry_evidence']:
            source = registry[evidence['id']]
            assert evidence['client'] == source[1] and evidence['model'] == source[3] and evidence['serial'] == str(source[4])
        # Independent exact serial join proves machine/absence without calling the matcher.
        serials = item['fields']['serials']
        if len(serials) == 1:
            joined = sorted(k for k, row in registry.items() if str(row[4]) == serials[0])
            assert sorted(item['expected_ids']) == joined, (item['id'], 'registry serial join differs')
    return checked_fields


def measure(records, equipment, baseline):
    result = {'examples': len(records), 'equipment_set_correct': 0, 'decision_correct': 0,
              'field_values_correct': 0, 'field_values_expected': 0, 'field_values_predicted': 0,
              'all_fields_correct': 0, 'unique_suggestions': 0, 'wrong_unique_suggestions': 0,
              'provisional_symptoms_correct': 0, 'latency_samples_ms': [], 'errors': [], 'rows': []}
    for item in records:
        samples = []
        for _ in range(10):
            start = perf_counter()
            parsed = local_extract(item['text'], item['sender'], baseline=baseline)
            matched = match_equipment(parsed, item['sender'], item['text'], equipment, baseline=baseline)
            samples.append((perf_counter() - start) * 1000)
        result['latency_samples_ms'].extend(samples)
        predicted_ids = sorted(c['id'] for c in matched['candidates'])
        entity_ok = predicted_ids == sorted(item['expected_ids'])
        decision_ok = entity_ok and matched['status'] == item['expected_status']
        result['equipment_set_correct'] += int(entity_ok)
        result['decision_correct'] += int(decision_ok)
        proposed = matched['status'] in ('exact', 'unique') and len(predicted_ids) == 1
        result['unique_suggestions'] += int(proposed)
        result['wrong_unique_suggestions'] += int(proposed and (not entity_ok or item['expected_status'] not in ('exact', 'unique')))
        field_errors, all_fields = {}, True
        for key in ('models', 'serials', 'codes'):
            expected, predicted = set(item['fields'][key]), set(parsed[key])
            result['field_values_expected'] += len(expected)
            result['field_values_predicted'] += len(predicted)
            result['field_values_correct'] += len(expected & predicted)
            if expected != predicted:
                all_fields = False
                field_errors[key] = {'expected': sorted(expected), 'predicted': sorted(predicted)}
        result['all_fields_correct'] += int(all_fields)
        symptoms_ok = set(parsed['symptoms']) == set(item['symptoms_provisional'])
        result['provisional_symptoms_correct'] += int(symptoms_ok)
        row = {'id': item['id'], 'split': item['split'], 'expected_ids': item['expected_ids'], 'predicted_ids': predicted_ids,
               'expected_status': item['expected_status'], 'predicted_status': matched['status'], 'equipment_correct': entity_ok,
               'decision_correct': decision_ok, 'field_errors': field_errors, 'symptoms_provisional_correct': symptoms_ok,
               'expected_symptoms_provisional': item['symptoms_provisional'], 'predicted_symptoms': parsed['symptoms'],
               'median_latency_ms': round(statistics.median(samples), 4), 'source_ref': item['source_ref']}
        result['rows'].append(row)
        if not decision_ok or field_errors or not symptoms_ok:
            result['errors'].append(row)
    samples = sorted(result.pop('latency_samples_ms'))
    result['latency'] = {'runs': len(samples), 'median_ms': round(statistics.median(samples), 4),
                         'p95_ms': round(samples[int(.95 * (len(samples) - 1))], 4), 'max_ms': round(max(samples), 4)}
    return result


def main():
    reference_path = ROOT / 'evaluation' / 'reference.json'
    reference = json.loads(reference_path.read_text())
    source_path = ROOT / 'Данные_к_кейсу_06 (1).xlsx'
    wb = load_workbook(source_path, data_only=True)
    verified = verify_source(reference, wb, source_path)
    equipment = [dict(zip(['id','client','address','model','serial','installed_at','last_visit','history'],
                         [str(v) if v is not None else '' for v in r]))
                 for r in wb['Оборудование'].iter_rows(min_row=4, values_only=True) if r[0]]
    wb.close()
    runs = {name: measure(reference['records'], equipment, baseline) for name, baseline in [('baseline', True), ('selected_local', False)]}
    output = {'source_sha256': reference['source_sha256'], 'reference_sha256': hashlib.sha256(reference_path.read_bytes()).hexdigest(),
              'python': platform.python_version(), 'platform': platform.platform(), 'examples': len(reference['records']),
              'case_examples': 23, 'challenge_examples': 15, 'verified_literal_values': verified,
              'expert_reviewed_examples': sum(bool(r['reviewer']) for r in reference['records']),
              'llm': {'executed': False, 'reason': 'No live LLM experiment: optional adapter tested with mocks only.'}, 'results': runs}
    (ROOT / 'evaluation' / 'results.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    with (ROOT / 'evaluation' / 'review.csv').open('w', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['id','split','sender','text','source_ref','expected_equipment','model','serial','error_code','expert_name','expert_date','expert_correction'])
        for r in reference['records']:
            writer.writerow([r['id'],r['split'],r['sender'],r['text'],r['source_ref'],','.join(r['expected_ids']),','.join(r['fields']['models']),','.join(r['fields']['serials']),','.join(r['fields']['codes']),'','',''])
    lines = ['# Фактическое сравнение разбора', '',
             f'Набор: **{len(reference["records"])} примеров** — все 23 сообщения кейса и 15 дополнительных. Ни один пример не исключён из отчёта.', '',
             'Эталон идентификаторов проверен по буквальному тексту и независимым соединением с исходным реестром по серийному номеру. '
             'Ожидаемые кандидаты содержат ссылки на ячейки. Разметка симптомов и интерпретация адресов/опечаток подготовлены ассистентом и **не проверены независимым экспертом**; их цифры ниже только предварительные. '
             'Ответ LLM не используется как эталон. Проверка источника воспроизводится до запуска оценки.', '',
             f'Автоматически проверено положительных буквальных значений: {verified}. Независимо рецензировано экспертами: **0/{len(reference["records"])}**. Для рецензирования — `review.csv`.', '',
             '| Проверка | Простой baseline | Выбранный локальный разбор |', '|---|---:|---:|']
    b, s = runs['baseline'], runs['selected_local']
    metrics = [('Точный набор кандидатов', 'equipment_set_correct', 'examples'), ('Кандидаты и решение exact/unique/ambiguous/conflict/unknown', 'decision_correct', 'examples'),
               ('Полнота буквальных полей (модель, номер, код)', 'field_values_correct', 'field_values_expected'),
               ('Точность извлечённых буквальных значений', 'field_values_correct', 'field_values_predicted'),
               ('Все три поля без пропусков и лишних значений', 'all_fields_correct', 'examples'),
               ('Ошибочные однозначные предложения машины', 'wrong_unique_suggestions', 'unique_suggestions'),
               ('Предварительные классы симптомов, НЕ экспертная оценка', 'provisional_symptoms_correct', 'examples')]
    for label, numerator, denominator in metrics:
        lines.append(f'| {label} | {b[numerator]}/{b[denominator]} | {s[numerator]}/{s[denominator]} |')
    lines += ['', 'Ошибочное однозначное предложение — это предложение алгоритма; готовность к выезду дополнительно требует ручного подтверждения и бизнес-проверок. Процент готовых заявок по этой оценке не измеряется.', '',
              '| Задержка разбора + сопоставления | Baseline | Выбранный локальный |', '|---|---:|---:|',
              f'| Медиана, мс | {b["latency"]["median_ms"]} | {s["latency"]["median_ms"]} |',
              f'| p95, мс | {b["latency"]["p95_ms"]} | {s["latency"]["p95_ms"]} |',
              f'| Максимум, мс | {b["latency"]["max_ms"]} | {s["latency"]["max_ms"]} |',
              f'| Измерений | {b["latency"]["runs"]} | {s["latency"]["runs"]} |', '',
              'По 10 последовательных повторов на пример, один процесс, прогретая машина, без HTTP/БД/сети и без ожидания человека. Эти задержки не равны времени подготовки диспетчером. Среда и все результаты — в `results.json`.', '',
              '**Живая LLM не запускалась и не сравнивалась.** Ключ и модель не предоставлены. Ошибки, тайм-аут, отказ, неверный JSON и неподтверждённые цитаты проверяются отдельными тестами с HTTP-заглушками. Нельзя переносить качество локального режима на LLM.', '',
              '## Все расхождения', '']
    for name, run in runs.items():
        lines += [f'### {name}', '', '| Пример | Кандидаты: эталон → факт | Решение: эталон → факт | Ошибки полей | Предварительные симптомы: эталон → факт |', '|---|---|---|---|---|']
        for r in run['errors']:
            symptoms = 'совпали' if r['symptoms_provisional_correct'] else ', '.join(r['expected_symptoms_provisional']) + ' → ' + ', '.join(r['predicted_symptoms'])
            lines.append(f'| {r["id"]} | {", ".join(r["expected_ids"]) or "∅"} → {", ".join(r["predicted_ids"]) or "∅"} | {r["expected_status"]} → {r["predicted_status"]} | {json.dumps(r["field_errors"], ensure_ascii=False) if r["field_errors"] else "—"} | {symptoms} |')
        lines.append('')
    lines += ['## Ограничения оценки', '',
              '- Кейс вымышленный; 38 примеров — малая выборка, статистической уверенности для производственных заявлений нет.',
              '- 15 дополнительных случаев составлены после знакомства с кейсом, это challenge-набор, а не слепой внешний holdout. Незнакомое сообщение дополнительно вводится в браузерном тесте.',
              '- Поля симптомов и неявный контекст требуют независимой разметки: файл `review.csv` намеренно оставляет имя эксперта и дату пустыми.',
              '- Baseline использует явный номер/модель и название клиента; расширенный режим добавляет контекстные формы номера, опечатки и адресные ограничения. Оба используют один реестр и одни 38 текстов.',
              '- Полный список предсказаний, включая успешные, находится в `results.json`. Контрольные суммы фиксируют источник и разметку.',
              '- Снижение повторных выездов, экономия рабочего времени людей и финансовый эффект экспериментально не измерены.']
    (ROOT / 'evaluation' / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({name: {k:v for k,v in r.items() if k not in ('rows','errors')} for name,r in runs.items()}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
