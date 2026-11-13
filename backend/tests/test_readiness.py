import pytest

from backend.app.rules import next_business_day
from datetime import date
from .conftest import confirm_diagnostic, create, update
from .test_inventory import action, plan


def test_unprepared_cannot_be_marked_ready(loaded):
    ticket = create(loaded)
    result = action(loaded, ticket, 'prepare')
    assert result.status_code == 409
    assert result.json()['error']['code'] == 'not_ready'
    assert not loaded.get(f'/api/tickets/{ticket["id"]}/card').json()['ready']


def test_confirmed_diagnostic_and_print_card(loaded):
    ticket = confirm_diagnostic(loaded, create(loaded))
    assert ticket['readiness']['can_prepare']
    ticket = action(loaded, ticket, 'prepare').json()
    assert ticket['readiness']['ready']
    again = action(loaded, ticket, 'prepare').json()
    assert again['prepared_at'] == ticket['prepared_at']
    card = loaded.get(f'/api/tickets/{ticket["id"]}/card').json()
    assert card['ready'] and card['equipment']['serial'] == '205'
    assert card['history']['source_ref'] == 'Оборудование!A5:H5'
    assert any('не гарантирует' in x for x in card['uncertainties'])
    printed = loaded.get(f'/api/tickets/{ticket["id"]}/print')
    assert printed.status_code == 200 and 'КАРТОЧКА ГОТОВА К ПЕРЕДАЧЕ' in printed.text
    for label in ('Подтверждённые сведения', 'Доступная история', 'Детали и склад получения', 'Цель визита', 'Оставшиеся неопределённости'):
        assert label in printed.text


def test_change_after_preparation_invalidates_card(loaded):
    ticket = action(loaded, confirm_diagnostic(loaded, create(loaded)), 'prepare').json()
    revision = ticket['revision']
    ticket = update(loaded, ticket, symptom='После приготовления вода справа; место уточнено диспетчером.')
    assert ticket['revision'] == revision + 1
    assert ticket['prepared_revision'] is None and not ticket['readiness']['ready']
    assert 'ЧЕРНОВИК' in loaded.get(f'/api/tickets/{ticket["id"]}/print').text


def test_new_evidence_invalidates_answers_and_preparation(loaded):
    ticket = action(loaded, confirm_diagnostic(loaded, create(loaded)), 'prepare').json()
    result = loaded.post(f'/api/tickets/{ticket["id"]}/messages?revision={ticket["revision"]}', json={
        'sender': 'Кафе «Кедр», администратор', 'text': 'Уточнение: вода на 205 появляется снизу постоянно.', 'received_at': '2026-11-16T13:00:00+03:00'})
    assert result.status_code == 201
    ticket = result.json()
    assert not ticket['readiness']['ready'] and not ticket['data']['symptom_confirmed']
    assert ticket['data']['answers'] == {}
    assert len(ticket['messages']) == 2


@pytest.mark.parametrize('answer', ['не знаю', 'неизвестно', 'не помню', '?', 'E7', 'насос'])
def test_unknown_or_invalid_error_code_never_satisfies_readiness(loaded, answer):
    ticket = create(loaded, 'Гостиница «Берег»', 'На машине 108 код на экране, кофе не выдаёт.')
    ticket = confirm_diagnostic(loaded, ticket)
    ticket = update(loaded, ticket, answers={'error_code': answer})
    assert 'questions' in [b['key'] for b in ticket['readiness']['blockers']]
    assert not ticket['readiness']['ready']


def test_unknown_equipment_cannot_be_ready(loaded):
    ticket = create(loaded, 'Гостиница «Север»', 'Вторая машина 270, течёт из-под поддона постоянно.')
    assert ticket['matching']['status'] == 'unknown' and ticket['equipment'] is None
    ticket = confirm_diagnostic(loaded, ticket)
    assert not ticket['readiness']['can_prepare']
    result = action(loaded, ticket, 'prepare')
    assert result.status_code == 409


def test_manual_identity_conflict_requires_explanation(loaded):
    ticket = create(loaded, 'Кафе «Кедр»', 'Номер 205, C300, течёт справа после приготовления.')
    ticket = update(loaded, ticket, equipment_id='EQ02')
    ticket = confirm_diagnostic(loaded, ticket)
    assert 'identity_conflict' in [b['key'] for b in ticket['readiness']['blockers']]
    ticket = update(loaded, ticket, identity_resolution='Клиент сверил шильдик: C200. C300 — ошибочная запись.')
    assert 'identity_conflict' not in [b['key'] for b in ticket['readiness']['blockers']]


def test_warranty_recurrence_new_install_and_history_boundaries(loaded):
    ticket = create(loaded, 'Кафе «Маяк»', 'Машина 305 капает из-под группы после приготовления.')
    assert ticket['readiness']['warranty']['required']
    ticket = confirm_diagnostic(loaded, ticket)
    assert 'approval' in [b['key'] for b in ticket['readiness']['blockers']]
    ticket = loaded.post(f'/api/tickets/{ticket["id"]}/approval', json={'revision': ticket['revision'], 'name': 'Старший инженер Иванов', 'note': 'Согласована диагностика гарантийного случая.'}).json()
    assert ticket['readiness']['can_prepare']
    ticket = update(loaded, ticket, uncertainties='Уточнить акт прошлого ремонта.')
    assert ticket['data'].get('approval') is None
    assert 'approval' in [b['key'] for b in ticket['readiness']['blockers']]
    new = create(loaded, 'Ресторан «Пирс»', 'На машине 133 пар из крана идёт слабо, кофе нормальный.')
    assert new['readiness']['warranty']['required']
    assert new['readiness']['warranty']['uncertainties']
    noise = create(loaded, 'Кафе «Лист»', 'C300 снова гудит при приготовлении.')
    assert not noise['readiness']['warranty']['required']
    assert noise['readiness']['warranty']['uncertainties']
    vague = create(loaded, 'Кофейня «Сквер»', 'Машина 214 гудит при приготовлении как в августе.')
    assert not vague['readiness']['warranty']['required']
    assert any('код' in x for x in vague['readiness']['warranty']['uncertainties'])


def test_c300_error_has_no_invented_decoding_or_part(loaded):
    ticket = create(loaded, 'Кафе «Маяк»', 'На экране C300, номер 305, код E11.')
    assert ticket['error_codes'] == [{'code': 'E11', 'meaning': 'Расшифровки для этой модели в данных нет', 'known': False}]
    assert ticket['plans'] == []
    card = loaded.get(f'/api/tickets/{ticket["id"]}/card').json()
    assert any('Расшифровки' in u for u in card['uncertainties'])


def test_optimistic_concurrency_rejects_stale_update(loaded):
    ticket = create(loaded)
    update(loaded, ticket, uncertainties='Уточнить текущее состояние.')
    result = loaded.patch(f'/api/tickets/{ticket["id"]}', json={'revision': ticket['revision'], 'symptom': 'Из другого окна: течь снизу.'})
    assert result.status_code == 409 and result.json()['error']['code'] == 'stale_revision'


def test_manager_route_is_internal_and_reversible(loaded):
    ticket = create(loaded, 'Кафе «Ромашка»', 'C200, номер 230, договора пока нет.')
    ticket = loaded.post(f'/api/tickets/{ticket["id"]}/manager', json={'revision': ticket['revision'], 'note': 'Для менеджера: C200, №230. Договор отсутствует.'}).json()
    assert ticket['state'] == 'manager' and not ticket['readiness']['ready']
    ticket = action(loaded, ticket, 'reopen').json()
    assert ticket['state'] == 'open'


def test_print_escapes_untrusted_message(loaded):
    ticket = create(loaded, 'Кафе «Кедр»', 'На машине 205 течь. <script>alert(1)</script>')
    html = loaded.get(f'/api/tickets/{ticket["id"]}/print').text
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html


def test_cancellation_clears_preparation_and_own_reserve_only(loaded):
    ticket = plan(loaded, create(loaded), 'F010').json()
    ticket = confirm_diagnostic(loaded, ticket)
    ticket = action(loaded, ticket, 'reserve').json()
    ticket = action(loaded, ticket, 'prepare').json()
    assert ticket['readiness']['ready']
    ticket = action(loaded, ticket, 'release').json()
    assert not ticket['readiness']['ready'] and ticket['prepared_revision'] is None


def test_weekend_transfer_date():
    assert next_business_day(date(2026, 11, 13)) == date(2026, 11, 16)
