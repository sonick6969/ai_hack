import pytest

from .conftest import confirm_diagnostic, create, update


@pytest.mark.parametrize('purpose', ['repair', 'maintenance'])
def test_official_rules_allow_work_without_replacement_parts(loaded, purpose):
    ticket = confirm_diagnostic(loaded, create(loaded))
    ticket = update(loaded, ticket, purpose=purpose,
                    purpose_note='Проверить и исправить подключение подачи воды без замены деталей.', plan_confirmed=True)
    assert ticket['readiness']['can_prepare']
    for key in ['compatibility', 'reservation', 'transfer', 'approval']:
        check = next(c for c in ticket['readiness']['checks'] if c['key'] == key)
        assert check['state'] == 'not_required'
        assert not check['passed']
    assert ticket['readiness']['not_required'] >= 4
    assert ticket['readiness']['total'] == len([c for c in ticket['readiness']['checks'] if c['state'] != 'not_required'])


def test_failed_checks_have_reason_and_action_separate_from_label(loaded):
    ticket = create(loaded)
    identity = next(c for c in ticket['readiness']['checks'] if c['key'] == 'identity')
    assert identity['state'] == 'action_required'
    assert identity['next_action'] == 'Подтвердите машину и адрес'
    assert identity['reason'] and identity['label'] != identity['next_action']
    questions = next(c for c in ticket['readiness']['checks'] if c['key'] == 'questions')
    assert questions['basis'] == 'case'
    noise = create(loaded, 'Кафе «Лист»', 'Машина 310 гудит.')
    question_check = next(c for c in noise['readiness']['checks'] if c['key'] == 'questions')
    assert question_check['basis'] == 'product'


def test_ambiguous_symptom_requires_substantive_clarification(loaded):
    ticket = create(loaded, text='Машина 205 то ли течёт, то ли шумит.')
    assert ticket['analysis'].get('uncertainties')
    assert any(q['key'] == 'general_context' for q in ticket['readiness']['questions'])
