from .conftest import confirm_diagnostic, create


def test_same_problem_suggested_but_never_auto_merged(loaded):
    ticket = loaded.get('/api/tickets/6').json()  # З-06, 205, leak clarification
    assert 1 in [d['id'] for d in ticket['duplicates']]
    assert loaded.get('/api/summary').json()['tickets'] == 23
    original = loaded.get('/api/tickets/1').json()
    result = loaded.post('/api/tickets/6/merge', json={'revision': ticket['revision'], 'target_id': 1,
                          'target_revision': original['revision'], 'reason': 'Уточнение той же течи на машине 205.'})
    assert result.status_code == 200
    target = result.json()
    assert len(target['messages']) == 2 and target['equipment']['id'] == 'EQ02'
    assert not target['data']['equipment_confirmed']
    assert loaded.get('/api/tickets/6').status_code == 409
    assert loaded.get('/api/summary').json()['messages'] == 23
    assert loaded.get('/api/summary').json()['tickets'] == 22


def test_new_problem_same_machine_is_separate(loaded):
    steam = loaded.get('/api/tickets/23').json()
    assert steam['analysis']['symptoms'] == ['steam']
    assert 6 not in [d['id'] for d in steam['duplicates']]
    assert 12 not in [d['id'] for d in steam['duplicates']]
    assert steam['equipment']['serial'] == '205'


def test_new_machine_same_client_not_duplicate(loaded):
    assert loaded.get('/api/tickets/18').json()['duplicates'] == []
    park = loaded.get('/api/tickets/17').json()
    assert park['equipment']['id'] == 'EQ08'
    assert 22 not in [d['id'] for d in park['duplicates']]


def test_merge_different_machines_rejected(loaded):
    first = loaded.get('/api/tickets/17').json()
    second = loaded.get('/api/tickets/22').json()
    result = loaded.post('/api/tickets/17/merge', json={'revision': first['revision'], 'target_id': 22,
                             'target_revision': second['revision'], 'reason': 'Проверка защиты от объединения разных машин.'})
    assert result.status_code == 409 and result.json()['error']['code'] == 'different_equipment'


def test_repeat_manual_request_with_same_key(loaded):
    body = {'sender': 'Кафе «Угол»', 'text': 'На машине 119 медленно идёт кофе с утра.', 'request_id': 'repeat-request-123'}
    first, second = loaded.post('/api/messages', json=body), loaded.post('/api/messages', json=body)
    assert first.json()['ticket']['id'] == second.json()['ticket']['id']
    assert second.json()['created'] is False
    body['text'] = 'Совершенно другой симптом'
    assert loaded.post('/api/messages', json=body).status_code == 409
