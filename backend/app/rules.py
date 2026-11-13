import re
from datetime import date, timedelta

from .extraction import local_extract, norm
from .answers import answer_record

ERROR_CODES = {'E03': 'Нет подачи воды в машину', 'E07': 'Заварочный блок не обнаружен', 'E11': 'Датчик показывает низкий уровень воды'}
QUESTIONS = {
    'leak_location': ('Где появляется вода?', 'Снизу, справа, слева, из-под группы или поддона'),
    'leak_timing': ('Когда появляется вода?', 'Во время приготовления, после него или постоянно'),
    'onset': ('С какого момента поток стал слабым?', 'Время или событие начала симптома'),
    'after_work': ('Какие работы были перед этим?', 'Если работ не было, так и укажите'),
    'error_code': ('Какой точный код на экране?', 'Перепишите код; фотография необязательна'),
    'noise_context': ('Когда и при каких условиях слышен шум?', 'При приготовлении, на нагреве, постоянно; повторяется ли сейчас'),
    'steam_context': ('Что происходит с паром и когда?', 'Как работает паровой кран, греется ли молоко'),
    'general_context': ('Что происходит с машиной?', 'Наблюдаемый симптом, место и условия проявления'),
}


def next_business_day(value):
    value += timedelta(days=1)
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


def questions_for(analysis, data):
    keys = []
    for symptom in analysis['symptoms']:
        keys += {'leak': ['leak_location', 'leak_timing'], 'flow': ['onset', 'after_work'],
                 'error': ['error_code'], 'noise': ['noise_context'], 'steam': ['steam_context'],
                 'unknown': ['general_context'], 'request': ['general_context']}.get(symptom, [])
    if analysis.get('uncertainties'):
        keys.append('general_context')

    def resolved(key):
        record = answer_record(data, key)
        answer = record['text'].strip()
        if record['status'] != 'answered':
            return False
        if key == 'error_code':
            return bool(re.fullmatch(r'[EЕeе]\s*\d{2}', answer))
        return True

    return [{'key': key, 'question': QUESTIONS[key][0], 'hint': QUESTIONS[key][1],
             'suggested': analysis['facts'].get(key, ''), 'answer': answer_record(data, key)['text'],
             'status': answer_record(data, key)['status'], 'provenance': answer_record(data, key),
             'basis': 'case' if key in {'leak_location','leak_timing','onset','after_work','error_code'} else 'product',
             'resolved': resolved(key)}
            for key in dict.fromkeys(keys)]


def warranty_for(equipment, analysis, at):
    if not equipment:
        return {'required': False, 'reason': 'Сначала определите машину', 'uncertainties': []}
    at = date.fromisoformat(at[:10])
    installed = date.fromisoformat(equipment['installed_at'])
    reasons, unknown = [], []
    age = (at - installed).days
    if 0 <= age < 30:
        reasons.append(f'Установка {equipment["installed_at"]}: прошло {age} дн., меньше 30')
    history = equipment['history']
    if equipment['last_visit'] and history:
        gap = (at - date.fromisoformat(equipment['last_visit'])).days
        previous = local_extract(history)['symptoms']
        overlap = set(previous) & set(analysis['symptoms']) - {'unknown', 'maintenance'}
        repair = bool(re.search(r'замен[её]н|после осмотра замен|исправлен|ремонт', norm(history)))
        if 0 <= gap <= 30 and overlap and repair:
            reasons.append(f'Повтор той же жалобы через {gap} дн. после ремонта {equipment["last_visit"]}')
        if re.search(r'узел', norm(history)) and not re.search(r'\b[GPLVFS]\d{3}\b', history):
            unknown.append('В истории не указан код заменённого узла; уточнить по акту, не подбирать деталь по догадке.')
        if re.search(r'не повторился|ничего не наш', norm(history)):
            unknown.append('На прошлом визите симптом не подтвердился; причина и необходимая деталь неизвестны.')
    else:
        unknown.append('Истории визитов в предоставленном реестре нет.')
    return {'required': bool(reasons), 'reason': '; '.join(reasons) or 'Оснований по правилу П-9 в доступных данных не обнаружено',
            'uncertainties': unknown}


def error_explanations(equipment, analysis, data):
    codes = list(analysis['codes'])
    codes += re.findall(r'\bE\d{2}\b', data.get('answers', {}).get('error_code', '').upper().replace('Е', 'E'))
    codes = list(dict.fromkeys(codes))
    if not codes:
        return []
    if not equipment or equipment['model'] not in ('C100', 'C200'):
        return [{'code': code, 'meaning': 'Расшифровки для этой модели в данных нет', 'known': False} for code in codes]
    return [{'code': code, 'meaning': ERROR_CODES.get(code, 'Код отсутствует в предоставленной таблице'), 'known': code in ERROR_CODES} for code in codes]
