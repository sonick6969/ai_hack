"""Clause-level observations. Vocabulary and polarity/time/subject scopes are separate."""
import json
import re
from datetime import datetime

PARSER_VERSION = 2
ORDER = ['leak', 'flow', 'error', 'noise', 'steam', 'maintenance', 'request']
LEXICON = {
    'leak': r'\b(?:теч[еёиь]\w*|текл\w*|подтека\w*|протека\w*|капает|капало|луж\w*)|вод[аы]\s+появля\w*',
    'flow': r'\b(?:напор\w*|тонк\w*\s+стру\w*|медленн\w*|слаб\w*\s+поток\w*|по\s+капле|еле\s+(?:ид[её]т|ль[её]тся))',
    'error': r'\b(?:ошиб\w*|код\w*|низкий\s+уровень|датчик\s+уровня|[eе]\s*\d{2}\b)|не\s+(?:выда[её]т|готовит)\s+кофе',
    'noise': r'\b(?:гул\w*|гуд\w*|шум\w*|дребез\w*|свист\w*|тарахт\w*|скреж\w*)',
    'steam': r'\bпар\w*[^,.;!?]{0,35}\bслаб\w*|\bслаб\w*\s+пар\w*|молоко\s+не\s+гре\w*',
    'maintenance': r'заменить\s+фильтр|планов\w*\s+обслужив\w*|профилактик\w*',
    'request': r'разборк\w*|сами\s+почин\w*|разобрат\w*',
}
PATTERNS = {key: re.compile(value, re.I) for key, value in LEXICON.items()}
SERIAL = re.compile(
    r'(?:(?:серийн\w*(?:\s+номер)?|номер|№|шильдик[еа]?|машин\w*|на|s/?n)\s*[:№]?\s*'
    r'|(?:^|(?<=[,;.!?:]))\s*|\b(?:а|и|но|зато|теперь|сейчас)\s+)'
    r'(\d{3,8})\b(?!\s*(?:год\w*|руб\w*|минут\w*|градус\w*|мл\b|мг\b|бар\b))', re.I)
CLAUSE_BREAK = re.compile(r'[.!?;\n]+|,\s*|\b(?:но|а|зато|однако|и)\b', re.I)
PAST = re.compile(r'\b(?:раньше|вчера|прежде|летом|тогда|прошл\w*)\b', re.I)
PRESENT = re.compile(r'\b(?:сейчас|теперь|сегодня|снова)\b', re.I)
DOUBT = re.compile(r'\b(?:кажется|возможно|наверное|похоже|предполож\w*|то\s+ли|может\s+быть|не\s+уверен\w*|вроде(?:\s+бы)?)\b', re.I)
CORRECTION = re.compile(r'больше\s+не|перестал\w*|прекратил\w*|уточн\w*|исправл\w*|теперь\s+только', re.I)
FACT_PATTERNS = {
    'leak_location': r'из[ -]под\s+(?:заварочной\s+)?группы|из[ -]под\s+поддона|снизу|слева|справа',
    'leak_timing': r'после\s+(?:приготовления|него)|во время\s+приготовления|при приготовлении|постоянно',
    'onset': r'с\s+утра|сегодня|вчера|после\s+(?:мойки|чистки|декальцинации|обслуживания)|\d+\s+дн[яей]+',
    'after_work': r'после\s+(?:мойки|чистки|декальцинации|обслуживания)|работ\s+не\s+было|ничего\s+не\s+делали|до этого\s+не\s+обслуживали',
    'error_code': r'\b[eе]\s*\d{2}\b',
    'noise_context': r'при приготовлении|во время приготовления|после приготовления|постоянно|на нагреве',
    'steam_context': r'пар\s+из\s+крана[^,.;!?]{0,35}|молоко не греется',
}
FACT_SYMPTOMS = {'leak_location': 'leak', 'leak_timing': 'leak', 'onset': 'flow', 'after_work': 'flow',
                 'error_code': 'error', 'noise_context': 'noise', 'steam_context': 'steam'}


def norm(text):
    return re.sub(r'\s+', ' ', text.lower().replace('ё', 'е')).strip()


def clauses(text):
    start = 0
    for boundary in CLAUSE_BREAK.finditer(text):
        if text[start:boundary.start()].strip():
            yield start, boundary.start(), text[start:boundary.start()], boundary.group()
        start = boundary.end()
    if text[start:].strip():
        yield start, len(text), text[start:], ''


def machine_at(text, start, end, inherited=None):
    mentions = list(SERIAL.finditer(text))
    following = [m for m in mentions if start <= m.start() < end]
    if len({m.group(1) for m in following}) == 1:
        return following[0].group(1)
    before = [m for m in mentions if m.start() <= start]
    if before:
        return before[-1].group(1)
    inside = [m for m in mentions if m.start() < end]
    return inside[-1].group(1) if inside else inherited


def scope_status(clause, match, punctuation):
    prefix, suffix = norm(clause[:match.start()]), norm(clause[match.end():])
    scope_prefix = re.sub(r'\bне\s+только\b', '', prefix)
    # A negation binds to an observation or its auxiliary, not to "не знаю почему".
    negative = bool(re.search(r'\b(?:не|ни|нет)(?:\s+(?:совсем|вообще|больше|уже|может|могу|показыва\w*|слышно|видно|наблюда\w*|сильн\w*|перестал\w*|прекратил\w*)){0,3}\s*$', scope_prefix))
    negative ^= bool(re.search(r'\b(?:перестал\w*|прекратил\w*)\s*(?:не\s*)?$', scope_prefix))
    negative |= bool(re.match(r'^(?:(?:на|у|машин\w*|\d{3,8})\s+){0,3}нет\b|^не\s+(?:наблюда\w*|повтор\w*|обнаруж\w*)', suffix))
    temporal = [(m.start(), 'past') for m in PAST.finditer(prefix)] + [(m.start(), 'current') for m in PRESENT.finditer(prefix)]
    # "со вчера"/"с прошлого вечера" is an onset continuing into the present.
    ongoing = bool(re.search(r'\b(?:с|со)\s+(?:вчера|прошл\w*)', prefix))
    if max(temporal, default=(-1, 'current'))[1] == 'past' and not ongoing:
        return 'past'
    if negative:
        return 'negated'
    if DOUBT.search(prefix) or '?' in punctuation:
        return 'suspected'
    if re.fullmatch(r'(?:текл[аио]?|гудел[аио]?|шумел[аио]?|капало)', norm(match.group())) and not PRESENT.search(prefix):
        return 'past'
    return 'current'


def uncertainty(quote, question, kind='ambiguous', machine=None):
    return {'kind': kind, 'quote': quote, 'question': question, 'machine': machine}


def summarise(assertions, uncertainties):
    states = {(a.get('machine'), a['symptom']): a for a in assertions}
    contradicted = {(u.get('machine'), u.get('symptom')) for u in uncertainties if u.get('kind') == 'contradiction'}
    categories = {status: [] for status in ('current', 'negated', 'past', 'suspected')}
    for key, assertion in states.items():
        categories['suspected' if key in contradicted else assertion['status']].append(assertion['symptom'])
    ordered = lambda values: [s for s in ORDER if s in values]
    return {'symptoms': ordered(categories['current']) or ['unknown'],
            'current_symptoms': ordered(categories['current']), 'negated_symptoms': ordered(categories['negated']),
            'past_symptoms': ordered(categories['past']), 'suspected_symptoms': ordered(categories['suspected'])}


def parse_observations(text):
    serials = list(dict.fromkeys(m.group(1) for m in SERIAL.finditer(text)))
    assertions, evidence, uncertainties = [], [], []
    inherited = serials[0] if len(serials) == 1 else None
    modifier_start = None
    for start, end, clause, punctuation in clauses(text):
        if modifier_start is not None:
            start, modifier_start = modifier_start, None
            clause = text[start:end]
        machine = machine_at(text, start, end, inherited)
        inherited = machine
        matches = sorted([(m.start(), key, m) for key, pattern in PATTERNS.items() for m in pattern.finditer(clause)])
        if not matches and DOUBT.fullmatch(norm(clause)) and ',' in punctuation:
            modifier_start = start
        flow_context = bool(PATTERNS['flow'].search(clause) and re.search(r'кофе|напиток|носик|стру', clause, re.I))
        for _, symptom, match in matches:
            if symptom == 'leak' and flow_context and not re.search(r'вод[аы]|снизу|из[ -]под|слева|справа', clause, re.I):
                continue
            assertions.append({'symptom': symptom, 'status': scope_status(clause, match, punctuation),
                               'quote': clause.strip(), 'machine': machine_at(text, start + match.start(), end, machine),
                               'provider': 'local', 'start': start + match.start(), 'end': start + match.end()})
    for machine, symptom in {(a['machine'], a['symptom']) for a in assertions}:
        group = [a for a in assertions if (a['machine'], a['symptom']) == (machine, symptom)]
        if {'current', 'negated'} <= {a['status'] for a in group} and not CORRECTION.search(text) and not PAST.search(text):
            uncertainties.append({**uncertainty(text, 'Противоречивое описание: подтвердите, что происходит сейчас.', 'contradiction', machine), 'symptom': symptom})
    for a in assertions:
        if a['status'] == 'suspected':
            uncertainties.append(uncertainty(a['quote'], 'Подтвердите, наблюдается ли предполагаемый симптом сейчас.', 'hypothesis', a['machine']))
    if len(serials) > 1:
        uncertainties.append(uncertainty(text, 'Разделите обращение по машинам или уточните номер для этой карточки.', 'multiple_machines'))
    summary = summarise(assertions, uncertainties)
    if not assertions:
        uncertainties.append(uncertainty(text, 'Что именно происходит с машиной сейчас? Уточните место и условия.', 'incomplete', inherited))
    active = {(a['machine'], a['symptom']) for a in assertions if a['status'] == 'current'}
    for field, pattern in FACT_PATTERNS.items():
        for match in re.finditer(pattern, text, re.I):
            machine = machine_at(text, match.start(), match.end(), inherited)
            if (machine, FACT_SYMPTOMS[field]) not in active or re.search(r'\bне\s*$', norm(text[max(0, match.start()-12):match.start()])):
                continue
            covering = [a for a in assertions if a['machine'] == machine and a['symptom'] == FACT_SYMPTOMS[field] and a['start'] <= match.start() <= a['end']]
            if covering and any(a['status'] != 'current' for a in covering):
                continue
            value = match.group()
            evidence.append({'field': field, 'value': value, 'quote': value, 'machine': machine, 'provider': 'local'})
    facts = {e['field']: e['value'] for e in evidence if FACT_SYMPTOMS[e['field']] in summary['current_symptoms']}
    codes = list(dict.fromkeys('E' + m for e in evidence if e['field'] == 'error_code' for m in re.findall(r'\d{2}', e['value'])))
    return {'serials': serials, 'codes': codes, **summary, 'facts': facts, 'assertions': assertions,
            'uncertainties': uncertainties, 'evidence': evidence, 'correction': bool(CORRECTION.search(text)),
            'parser_version': PARSER_VERSION}


def message_analysis(message):
    item = json.loads(message['analysis']) if isinstance(message['analysis'], str) else message['analysis']
    if item.get('parser_version') == PARSER_VERSION:
        return item
    from .extraction import local_extract
    return {**local_extract(message.get('text', '')), 'llm_status': 'legacy_reparsed', 'stored_engine': item.get('engine', 'local')}


def combine(messages, machine=None):
    """New explicit assertions replace only the same symptom on the same machine.

    Preserve the full timeline. Received time, not a merge's insertion order, wins.
    Legacy cached results are reinterpreted locally without rewriting messages.
    """
    result = {'models': [], 'serials': [], 'codes': [], 'facts': {}, 'unsafe_request': False,
              'evidence': [], 'assertions': [], 'uncertainties': [], 'processing': []}
    def order(message):
        try:
            return datetime.fromisoformat(message.get('received_at', '')).timestamp(), message['id']
        except ValueError:
            return 0, message['id']
    pending = [(m, message_analysis(m)) for m in sorted(messages, key=order)]
    items, emitted = [], set()
    available = {m['id'] for m in messages}
    while pending:
        index = next((i for i, (_, a) in enumerate(pending)
                      if not (set(a.get('supersedes_message_ids', [])) & available) - emitted), 0)
        item = pending.pop(index)
        items.append(item)
        emitted.add(item[0]['id'])
    for _, item in items:
        for key in ('models', 'serials'):
            result[key] = list(dict.fromkeys(result[key] + item[key]))
    fallback_machine = machine or (result['serials'][0] if len(result['serials']) == 1 else None)
    states, uncertain_by_machine = {}, {}
    for message, item in items:
        source = {'message_id': message['id'], 'source_ref': message['source_ref']}
        result['unsafe_request'] |= item['unsafe_request']
        result['processing'].append({**source, 'engine': item['engine'], 'llm_status': item['llm_status']})
        for a in item.get('assertions', []):
            a = {**a, 'machine': a.get('machine') or fallback_machine, **source}
            result['assertions'].append(a)
            if not machine or not a['machine'] or a['machine'] == machine:
                states[(a['machine'], a['symptom'])] = a
        item_machines = {a.get('machine') or fallback_machine for a in item.get('assertions', [])} or {fallback_machine}
        for serial in item_machines:
            uncertain_by_machine[serial] = [{**u, **source} for u in item.get('uncertainties', []) if u.get('machine') in (None, serial)]
        result['evidence'].extend([{**e, 'machine': e.get('machine') or fallback_machine, **source} for e in item['evidence']])
    latest = list(states.values())
    result['uncertainties'] = [u for serial, values in uncertain_by_machine.items() for u in values if not machine or serial in (None, machine)]
    result.update(summarise(latest, result['uncertainties']))
    active = {(a['machine'], a['symptom']) for a in latest if a['status'] == 'current'}
    for e in result['evidence']:
        if machine and e.get('machine') and e['machine'] != machine:
            continue
        if e['field'] in FACT_SYMPTOMS and (e.get('machine'), FACT_SYMPTOMS[e['field']]) not in active:
            continue
        result['facts'][e['field']] = e.get('value', e['quote'])
    if 'error' in result['current_symptoms']:
        result['codes'] = list(dict.fromkeys('E' + m for m in re.findall(r'[EЕeе]\s*(\d{2})', result['facts'].get('error_code', ''))))
    return result
