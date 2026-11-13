import json

import pytest

from backend.app import config
from backend.app.extraction import combine, local_extract
from .conftest import create, update


CASES = json.loads((config.ROOT / 'evaluation/language_cases.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_language_corpus(case):
    result = local_extract(case['text'])
    assert set(result['symptoms']) - {'unknown'} == set(case['current'])
    for expected, actual in [('negated', 'negated_symptoms'), ('past', 'past_symptoms'), ('suspected', 'suspected_symptoms')]:
        assert set(case.get(expected, [])) <= set(result.get(actual, []))
    if case.get('uncertain'):
        assert result.get('uncertainties'), 'Ambiguity must request clarification'
    for serial, expected in case.get('machines', {}).items():
        assertions = [a for a in result.get('assertions', []) if a['machine'] == serial and a['status'] == 'current']
        assert {a['symptom'] for a in assertions} == set(expected)
    for a in result.get('assertions', []):
        assert a['quote'] in case['text']


def test_correction_replaces_old_symptom_and_keeps_evidence():
    texts = ['Машина 205 течёт справа.', 'Машина 205 больше не течёт. Теперь только гудит при приготовлении.']
    messages = [{'id': i, 'text': text, 'source_ref': 'test', 'received_at': f'2026-11-16T1{i}:00:00+03:00',
                 'analysis': local_extract(text)} for i, text in enumerate(texts)]
    result = combine(messages)
    assert result['symptoms'] == ['noise']
    assert 'leak' in result['negated_symptoms']
    assert len(result['assertions']) >= 3
    assert 'leak_location' not in result['facts']


def test_correction_can_be_appended_to_existing_problem(loaded):
    ticket = create(loaded)
    result = loaded.post(f'/api/tickets/{ticket["id"]}/messages?revision={ticket["revision"]}', json={
        'sender': 'Кафе «Кедр»', 'text': 'Машина 205 больше не течёт. Теперь только гудит при приготовлении.',
        'received_at': '2026-11-16T13:00:00+03:00'})
    assert result.status_code == 201
    ticket = result.json()
    assert ticket['analysis']['symptoms'] == ['noise']
    assert len(ticket['messages']) == 2
    assert {q['key'] for q in ticket['readiness']['questions']} == {'noise_context'}


def test_later_denial_applies_only_to_its_machine():
    texts = ['Машина 205 течёт. Машина 119 гудит.', 'Машина 119 не течёт и не гудит.']
    messages = [{'id': i, 'text': text, 'source_ref': 'test', 'analysis': local_extract(text)} for i, text in enumerate(texts)]
    result = combine(messages)
    assert result['symptoms'] == ['leak']


@pytest.mark.parametrize('text,current,negated', [
    ('Не понимаю, почему машина 205 гудит.', ['noise'], []),
    ('Не знаю почему машина 205 гудит.', ['noise'], []),
    ('Не уверен, что машина 205 гудит.', [], []),
    ('Машина 205 не перестала течь.', ['leak'], []),
    ('Течи на машине 205 нет, гул остался.', ['noise'], ['leak']),
    ('Машина 205 не течёт. Гудит машина 119.', ['noise'], ['leak']),
])
def test_additional_scope_variants(text,current,negated):
    result = local_extract(text)
    assert set(result['symptoms']) - {'unknown'} == set(current)
    assert set(negated) <= set(result['negated_symptoms'])


def test_following_subject_does_not_inherit_previous_machine():
    result = local_extract('Машина 205 не течёт. Гудит машина 119.')
    assert next(a for a in result['assertions'] if a['symptom'] == 'noise')['machine'] == '119'


def test_years_and_measurements_are_not_machine_identifiers():
    result = local_extract('Машина 205 течёт. В 2026 году уже чинили; нагрев до 100 градусов, стоимость 1200 рублей.')
    assert result['serials'] == ['205']
    assert result['symptoms'] == ['leak']


def test_selected_machine_does_not_get_another_machines_symptom(loaded):
    ticket = create(loaded, text='Машина 205 течёт справа. Машина 101 гудит.')
    ticket = update(loaded,ticket,equipment_id='EQ02',identity_resolution='Клиент подтвердил: эта карточка для машины 205, 101 оформляется отдельно.')
    assert ticket['analysis']['symptoms'] == ['leak']
    assert len(ticket['messages'][0]['analysis']['assertions']) == 2


def test_explicit_denial_with_new_symptom_needs_no_magic_correction_word(loaded):
    ticket = create(loaded)
    result = loaded.post(f'/api/tickets/{ticket["id"]}/messages?revision={ticket["revision"]}',json={
        'sender':'Кафе «Кедр»','text':'Машина 205 не течёт, а гудит.'})
    assert result.status_code == 201
    corrected = result.json()
    assert corrected['analysis']['symptoms'] == ['noise']
    assert corrected['messages'][0]['text'] == ticket['messages'][0]['text']
    assert corrected['messages'][1]['analysis']['supersedes_message_ids'] == [ticket['messages'][0]['id']]


def test_explicit_correction_can_be_merged_without_resurrecting_cancelled_symptom(loaded):
    original = create(loaded)
    correction = create(loaded,text='Машина 205 не течёт, а гудит.',at='2026-11-16T13:00:00+03:00')
    assert original['id'] in [d['id'] for d in correction['duplicates']]
    result = loaded.post(f'/api/tickets/{correction["id"]}/merge',json={'revision':correction['revision'],'target_id':original['id'],
                        'target_revision':original['revision'],'reason':'Клиент исправил прежнюю жалобу: вместо течи слышен гул.'})
    assert result.status_code == 200
    assert result.json()['analysis']['symptoms'] == ['noise']
