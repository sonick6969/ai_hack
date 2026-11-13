import pytest

from .conftest import confirm_diagnostic, create, update


@pytest.mark.parametrize('field', ['symptom','purpose_note'])
def test_unknown_text_cannot_confirm_symptom_or_plan(loaded, field):
    ticket = confirm_diagnostic(loaded,create(loaded))
    confirmation = 'symptom_confirmed' if field == 'symptom' else 'plan_confirmed'
    ticket = update(loaded,ticket,**{field:'пока не знаю',confirmation:True})
    assert not ticket['readiness']['can_prepare']


def test_unknown_identity_explanation_does_not_resolve_registry_conflict(loaded):
    ticket = create(loaded,text='Машина 205, модель C300, течёт справа после приготовления.')
    ticket = update(loaded,ticket,equipment_id='EQ02',identity_resolution='пока не знаю')
    ticket = confirm_diagnostic(loaded,ticket)
    assert 'identity_conflict' in [c['key'] for c in ticket['readiness']['blockers']]


@pytest.mark.parametrize('endpoint,extra', [
    ('approval',{'name':'Старший инженер Иванов','note':'не могу сказать'}),
    ('manager',{'note':'пока не знаю'}),
])
def test_unknown_note_does_not_record_approval_or_manager_route(loaded,endpoint,extra):
    ticket = create(loaded)
    response = loaded.post(f'/api/tickets/{ticket["id"]}/{endpoint}',json={'revision':ticket['revision'],**extra})
    assert response.status_code == 422


def test_legacy_unknown_approval_does_not_satisfy_warranty(loaded):
    from backend.app.db import connect, encode
    ticket = confirm_diagnostic(loaded,create(loaded,'Кафе «Маяк»','Машина 305 капает из-под группы после приготовления.'))
    data = {**ticket['data'],'approval':{'name':'Старший инженер Иванов','note':'пока неизвестно','revision':ticket['revision']}}
    with connect() as conn:
        conn.execute('UPDATE tickets SET data=? WHERE id=?',(encode(data),ticket['id']))
    current = loaded.get(f'/api/tickets/{ticket["id"]}').json()
    assert 'approval' in [c['key'] for c in current['readiness']['blockers']]
    assert not current['readiness']['can_prepare']
