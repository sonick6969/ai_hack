from .conftest import create, update


def test_manual_symptom_classification_updates_required_questions(loaded):
    ticket = create(loaded, 'Кафе «Лист»', 'Машина 310 булькает на нагреве.')
    assert ticket['analysis']['symptoms'] == ['unknown']
    ticket = update(loaded, ticket, issue_types=['noise'])
    assert ticket['analysis']['symptoms'] == ['noise']
    assert [q['key'] for q in ticket['readiness']['questions']] == ['noise_context']
    assert not ticket['readiness']['can_prepare']


def test_manual_category_does_not_change_original_analysis_or_text(loaded):
    text = 'Машина 310 булькает на нагреве.'
    ticket = create(loaded, 'Кафе «Лист»', text)
    ticket = update(loaded, ticket, issue_types=['noise'])
    assert ticket['messages'][0]['text'] == text
    assert ticket['messages'][0]['analysis']['symptoms'] == ['unknown']
