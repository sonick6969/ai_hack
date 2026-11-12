import pytest

from backend.app.extraction import local_extract
from backend.app.matching import match_equipment


@pytest.mark.parametrize('sender,text,status,ids', [
    ('Кафе «Кедр»', 'На шильдике 205 течь справа', 'exact', ['EQ02']),
    ('Кафе «Кедр»', 'Течёт одна из двух машин', 'ambiguous', ['EQ01', 'EQ02']),
    ('Кафе «Кедрр»', 'C200, номер 205, вода справа', 'exact', ['EQ02']),
    ('Кафе «Кедр»', 'Номер 205, модель C300', 'conflict', ['EQ02']),
    ('Кафе «Кедр»', 'Модель C999, течь', 'unknown', []),
    ('Кафе «Кедр»', 'Номер 108, не выдаёт кофе', 'conflict', ['EQ03']),
    ('Гостиница «Север»', 'Вторая машина, номер 270, течёт', 'unknown', []),
    ('Пекарня «Зерно»', 'Напор слабый на Садовой. На Ленина всё в порядке.', 'unique', ['EQ08']),
    ('Пекарня «Зерно»', 'Теперь на Ленина E03', 'unique', ['EQ09']),
    ('Кафе «Лист»', 'На С300 снова гул', 'unique', ['EQ04']),
    ('Кафе «Ромашка»', 'C200, номер 230, нет договора', 'unknown', []),
    ('Кафе «Кедр»', 'Машины 101 и номер 205', 'conflict', ['EQ01', 'EQ02']),
])
def test_exact_ambiguous_typos_unknown_conflict_and_multiple(loaded, sender, text, status, ids):
    equipment = loaded.get('/api/equipment').json()
    result = match_equipment(local_extract(text, sender), sender, text, equipment)
    assert result['status'] == status
    assert [e['id'] for e in result['candidates']] == ids


def test_evidence_and_symptom_are_not_diagnoses():
    text = 'На машине 211 надпись «Низкий уровень», хотя вода в баке есть. Можно сразу привезти новый насос?'
    parsed = local_extract(text)
    assert parsed['serials'] == ['211']
    assert parsed['codes'] == []
    assert parsed['symptoms'] == ['error']
    assert 'diagnosis' not in parsed and 'part' not in parsed


def test_new_message_not_in_demo(loaded):
    from .conftest import create
    ticket = create(loaded, 'Кафе «Угол», новая смена', 'У нас С100, серийный номер 119. Со вчера кофе готовится медленно. Работ не было.')
    assert ticket['equipment']['id'] == 'EQ06'
    assert ticket['analysis']['symptoms'] == ['flow']
    assert ticket['readiness']['status'] == 'blocked'
    assert not ticket['readiness']['ready']
