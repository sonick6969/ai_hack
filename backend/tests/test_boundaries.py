from .conftest import confirm_diagnostic, create, update


def test_new_problem_cannot_be_appended_or_merged(loaded):
    ticket = create(loaded)
    body = {'sender': 'Кафе «Кедр»', 'text': 'На 205 теперь слабый пар, молоко не греется.'}
    result = loaded.post(f'/api/tickets/{ticket["id"]}/messages?revision={ticket["revision"]}', json=body)
    assert result.status_code == 409 and result.json()['error']['code'] == 'different_problem'
    other = create(loaded, **body)
    result = loaded.post(f'/api/tickets/{other["id"]}/merge', json={'revision': other['revision'], 'target_id': ticket['id'],
                           'target_revision': ticket['revision'], 'reason': 'Проверка новой проблемы на той же машине.'})
    assert result.status_code == 409 and result.json()['error']['code'] == 'different_problem'


def test_different_machine_cannot_be_appended(loaded):
    ticket = create(loaded)
    result = loaded.post(f'/api/tickets/{ticket["id"]}/messages?revision={ticket["revision"]}', json={
        'sender': 'Кафе «Кедр»', 'text': 'На машине 101 тоже течь снизу.'})
    assert result.status_code == 409 and result.json()['error']['code'] == 'different_equipment'


def test_manual_replacement_of_exact_match_requires_reason(loaded):
    ticket = confirm_diagnostic(loaded, create(loaded))
    ticket = update(loaded, ticket, equipment_id='EQ01', equipment_confirmed=True, address_confirmed=True)
    assert 'identity_conflict' in [b['key'] for b in ticket['readiness']['blockers']]


def test_null_fields_do_not_crash_readiness(loaded):
    ticket = create(loaded)
    ticket = update(loaded, ticket, symptom=None, purpose_note=None, visit_date=None, identity_resolution=None)
    assert not ticket['readiness']['can_prepare']


def test_validation_unknown_field_and_negative_quantity(loaded):
    assert loaded.post('/api/messages', json={'sender': 'A', 'text': 'OK'}).status_code == 422
    ticket = create(loaded)
    result = loaded.patch(f'/api/tickets/{ticket["id"]}', json={'revision': ticket['revision'], 'ready': True})
    assert result.status_code == 422
    result = loaded.post(f'/api/tickets/{ticket["id"]}/parts', json={'revision': ticket['revision'], 'sku': 'F010', 'warehouse': 'Москва', 'quantity': -1})
    assert result.status_code == 422
    assert 'error' in result.json()
