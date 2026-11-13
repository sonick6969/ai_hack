"""Answer state is decided on the server; legacy strings remain readable."""
import re


def answer_status(text):
    words = re.findall(r'[а-яa-z0-9]+', text.lower().replace('ё', 'е'))
    if not words:
        return 'unanswered'
    value = ' '.join(words)
    # Match complete clauses, never a substring of a substantive observation.
    unknown_clause = re.compile(
        r'(?:(?:я|мы|мне|нам|клиент|клиенту|сотрудник|сотруднику|пока|еще|сейчас|точно|к сожалению|вообще)\s+)*'
        r'(?:не\s+(?:знаю|знаем|знает|помню|помним|помнит|известно|выяснили|уточнили|в курсе|скажу|скажем|уверен|уверена|уверены)'
        r'|не\s+(?:могу|можем|может|мог|могла|могли|смог|смогла|смогли)\s+(?:сказать|ответить|уточнить|проверить)'
        r'|неизвест(?:но|ен|на|ны)|неясно|непонятно|без понятия|трудно сказать|нет\s+(?:данных|информации|ответа)'
        r'|затрудня(?:юсь|емся|ется)\s+ответить|(?:надо\s+|нужно\s+)?уточн(?:ить|ю|им)(?:\s+у\s+\w+)?|выясн(?:ю|им)|узна(?:ю|ем))'
        r'(?:\s+(?:пока|еще|точно|сейчас|где|когда|как|это|позже))*'
    )
    # Punctuation and conjunctions may join several expressions of uncertainty.
    clauses = [' '.join(re.findall(r'[а-яa-z0-9]+', c)) for c in re.split(r'[,;.!?…:—–/]+|\b(?:и|или)\b', text.lower().replace('ё', 'е'))]
    clauses = [c for c in clauses if c]
    acknowledgements = {'спасибо', 'извините', 'хорошо', 'понятно', 'ок', 'ага'}
    if clauses and all(unknown_clause.fullmatch(c) or c in acknowledgements for c in clauses):
        return 'unknown'
    if len(value) < 3 or value in {'уточнить', 'н д', 'хз', 'да', 'нет', 'ага', 'ок', 'понятно', 'спасибо', 'хорошо'}:
        return 'unknown'
    return 'answered'


def answer_record(data, key):
    text = data.get('answers', {}).get(key, '')
    stored = data.get('answer_records', {}).get(key, {})
    inferred = answer_status(text)
    status = stored.get('status', inferred)
    if status == 'answered' and inferred != 'answered':
        status = inferred
    return {'text': text, 'status': status, 'source': 'legacy' if not stored else stored.get('source', 'dispatcher'),
            **{k: v for k, v in stored.items() if k not in ('text', 'status')}}


def substantive(text, min_length=3):
    text = text or ''
    return len(text.strip()) >= min_length and answer_status(text) == 'answered'
