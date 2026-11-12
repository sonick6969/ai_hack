import re
from difflib import SequenceMatcher

from .extraction import norm


def client_name(text):
    quoted = re.search(r'[«\"]([^»\"]+)[»\"]', text)
    if quoted:
        return norm(quoted.group(1))
    text = re.sub(r'^(?:кафе|кофейня|гостиница|пекарня|ресторан|ооо)\s+', '', norm(text))
    return re.split(r'[,;]', text)[0].strip()


def match_equipment(analysis, sender, text, equipment, baseline=False):
    equipment = [dict(e) for e in equipment]
    name = client_name(sender)
    clients = sorted(set(e['client'] for e in equipment))
    exact_clients = [c for c in clients if client_name(c) == name or (client_name(c) in norm(text) and len(client_name(c)) > 3)]
    fuzzy = False
    if not exact_clients and not baseline and name:
        scores = sorted([(SequenceMatcher(None, name, client_name(c)).ratio(), c) for c in clients], reverse=True)
        if scores and scores[0][0] >= .8 and (len(scores) == 1 or scores[0][0] - scores[1][0] > .1):
            exact_clients = [scores[0][1]]
            fuzzy = True
    serials, models = analysis['serials'], analysis['models']
    candidates, reasons, status = equipment, [], 'ambiguous'

    def response(state, rows, reason):
        return {'status': state, 'reason': reason, 'client_typo': fuzzy,
                'candidates': [{**e, 'reasons': reasons.copy()} for e in rows]}

    if len(serials) > 1:
        return response('conflict', [e for e in equipment if e['serial'] in serials], 'Указано несколько серийных номеров. Разделите обращение по машинам или уточните номер.')
    if serials:
        candidates = [e for e in candidates if e['serial'] == serials[0]]
        reasons.append('Серийный номер ' + serials[0])
        if not candidates:
            return response('unknown', [], 'Серийного номера нет в реестре. Уточните шильдик; при подтверждении передайте менеджеру.')
        status = 'exact'
    if models:
        filtered = [e for e in candidates if e['model'] in models]
        if not filtered:
            return response('conflict' if serials else 'unknown', candidates if serials else [], 'Модель не согласуется с реестром. Требуется ручная проверка шильдика.')
        if len(models) > 1:
            return response('conflict', filtered, 'Указано несколько моделей. Уточните модель конкретной машины.')
        candidates = filtered
        reasons.append('Модель ' + models[0])
    if exact_clients:
        filtered = [e for e in candidates if e['client'] in exact_clients]
        if not filtered and (serials or models):
            return response('conflict', candidates, 'Клиент и идентификаторы машины противоречат друг другу.')
        candidates = filtered
        reasons.append('Клиент' + (' (возможная опечатка)' if fuzzy else ''))
    elif name:
        return response('conflict' if serials else 'unknown', candidates if serials else [], 'Клиент не найден в реестре. Нельзя подтвердить договор на основании номера другой компании.')
    elif not serials and not models:
        return response('unknown', [], 'Недостаточно данных для поиска машины.')
    if not baseline:
        # Address mentions declaring that a different machine is working are negative evidence.
        active_segments = [s for s in re.split(r'[.!?;\n]', norm(text)) if not re.search(r'все в порядке|исправн|работает нормально', s)]
        active_text = ' '.join(active_segments)
        hits = []
        for eq in candidates:
            tokens = re.findall(r'[а-яa-z]{4,}', norm(eq['address']))
            tokens = [t for t in tokens if t not in {'москва', 'тула', 'ленинградский', 'набережная'}]
            if any((t[:-2] if len(t) >= 7 else t[:5]) in active_text for t in tokens):
                hits.append(eq)
        if hits:
            candidates = hits
            reasons.append('Адрес в сообщении')
    if len(candidates) == 1:
        status = status if status == 'exact' else 'unique'
        return response(status, candidates, 'Кандидат найден. Диспетчер должен подтвердить машину и адрес.')
    return response('ambiguous' if candidates else 'unknown', candidates, 'У клиента несколько машин. Нужен номер или точный адрес.' if candidates else 'Совпадений нет.')
