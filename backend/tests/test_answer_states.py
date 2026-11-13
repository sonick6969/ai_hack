import pytest

from backend.app.rules import questions_for
from .conftest import confirm_diagnostic, create, update


@pytest.mark.parametrize('answer', [
    'пока не знаю', 'не могу сказать', '  ПОКА   НЕ ЗНАЮ!!! ', 'Не могу сказать…',
    'пока неизвестно', 'Не знаю.', 'Не помню', 'неизвестен', 'нет данных', 'неизвестна',
    '  ', '???', '—', 'Не могу ответить', 'затрудняюсь ответить', 'уточню', 'ещё не выяснили',
    'Пока не знаю, не могу сказать.', 'не в курсе', 'нет информации', 'не известно',
    'не знаю где', 'Уточню у смены', 'хорошо', 'спасибо',
    'Мне неизвестно', 'Пока неясно', 'Нужно уточнить', 'точно не скажу', 'узнаю позже',
    'пока не знаю, спасибо', 'не знаю — не могу сказать', 'Не знаю :(', 'не знаю/не могу сказать', 'Клиент не смог сказать',
])
def test_unknown_answer_does_not_resolve_question(answer):
    question = questions_for({'symptoms': ['leak'], 'facts': {}}, {'answers': {'leak_location': answer}})[0]
    assert not question['resolved']


def test_useful_information_with_unknown_reason_is_not_rejected():
    question = questions_for({'symptoms': ['leak'], 'facts': {}}, {'answers': {
        'leak_location': 'Причину не знаю, вода появляется справа после приготовления'}})[0]
    assert question['resolved']


def test_explicit_unknown_is_persisted_with_text_origin_and_history(loaded):
    ticket = create(loaded)
    ticket = update(loaded, ticket, answers={'leak_location': {
        'status': 'unknown', 'text': 'Клиент пока не может проверить', 'source': 'client'}})
    q = ticket['readiness']['questions'][0]
    assert q['status'] == 'unknown' and not q['resolved']
    assert q['answer'] == 'Клиент пока не может проверить'
    assert q['provenance']['source'] == 'client'
    ticket = update(loaded, ticket, answers={'leak_location': 'Справа под корпусом'})
    assert ticket['readiness']['questions'][0]['status'] == 'answered'
    history = loaded.get(f'/api/tickets/{ticket["id"]}/answers').json()
    assert [a['status'] for a in history if a['question_key'] == 'leak_location'] == ['unknown', 'answered']


def test_backend_cannot_be_bypassed_with_answered_unknown(loaded):
    ticket = confirm_diagnostic(loaded, create(loaded))
    ticket = update(loaded, ticket, answers={'leak_location': {
        'status': 'answered', 'text': 'ПОКА НЕ ЗНАЮ!', 'source': 'dispatcher'}})
    assert not ticket['readiness']['can_prepare']
    assert ticket['readiness']['questions'][0]['status'] == 'unknown'
    result = loaded.post(f'/api/tickets/{ticket["id"]}/prepare', json={'revision': ticket['revision']})
    assert result.status_code == 409


def test_message_provenance_cannot_reference_another_ticket(loaded):
    ticket, other = create(loaded), create(loaded)
    result = loaded.patch(f'/api/tickets/{ticket["id"]}', json={'revision': ticket['revision'], 'answers': {
        'leak_location': {'status': 'answered', 'text': 'справа', 'source': 'message', 'message_id': other['messages'][0]['id']}}})
    assert result.status_code == 409


def test_unknown_general_answer_does_not_satisfy_safe_actions(loaded):
    ticket = create(loaded, 'Кафе «Лист»', 'Пришлите инструкцию по разборке машины 310.')
    ticket = update(loaded, ticket, answers={'general_context': 'пока не знаю'})
    assert 'safe_actions' in [c['key'] for c in ticket['readiness']['blockers']]


def test_changing_machine_requires_fresh_answers_and_symptom_confirmation(loaded):
    ticket = confirm_diagnostic(loaded, create(loaded))
    ticket = update(loaded,ticket,equipment_id='EQ01')
    assert ticket['data']['answers'] == {}
    assert not ticket['data']['symptom_confirmed']
    assert not ticket['readiness']['can_prepare']
    assert loaded.get(f'/api/tickets/{ticket["id"]}/answers').json()


def test_merging_preserves_answer_history(loaded):
    first,second = create(loaded),create(loaded)
    first = update(loaded,first,answers={'leak_location':{'status':'unknown','text':'Уточню у смены','source':'client'}})
    result = loaded.post(f'/api/tickets/{first["id"]}/merge',json={'revision':first['revision'],'target_id':second['id'],
                       'target_revision':second['revision'],'reason':'Клиент подтвердил ту же течь на 205.'})
    assert result.status_code == 200
    history = loaded.get(f'/api/tickets/{second["id"]}/answers').json()
    assert history[0]['text'] == 'Уточню у смены' and history[0]['status'] == 'unknown'
