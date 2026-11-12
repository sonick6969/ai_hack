from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from .conftest import confirm_diagnostic, create


def plan(client, ticket, sku, warehouse='Москва', qty=1):
    return client.post(f'/api/tickets/{ticket["id"]}/parts', json={'revision': ticket['revision'], 'sku': sku, 'warehouse': warehouse, 'quantity': qty})


def action(client, ticket, verb):
    return client.post(f'/api/tickets/{ticket["id"]}/{verb}', json={'revision': ticket['revision']})


def test_incompatible_part_is_rejected(loaded):
    ticket = create(loaded)
    result = plan(loaded, ticket, 'G100')
    assert result.status_code == 409 and result.json()['error']['code'] == 'incompatible_part'
    assert loaded.get(f'/api/tickets/{ticket["id"]}').json()['plans'] == []


def test_external_reserve_never_reassigned(loaded):
    ticket = create(loaded)
    ticket = plan(loaded, ticket, 'G200').json()
    result = action(loaded, ticket, 'reserve')
    assert result.status_code == 409 and result.json()['error']['code'] == 'insufficient_stock'
    stock = next(s for s in loaded.get('/api/inventory').json() if s['sku'] == 'G200' and s['warehouse'] == 'Москва')
    assert stock['free'] == 0 and stock['external_reserved'] == 2 and stock['pilot_reserved'] == 0


def test_competing_requests_for_last_part_are_atomic(loaded):
    tickets = [create(loaded, 'Кафе «Маяк»', 'На машине 305 капает из-под группы после приготовления.') for _ in range(2)]
    tickets = [plan(loaded, ticket, 'G300').json() for ticket in tickets]
    barrier = Barrier(2)
    def compete(ticket):
        barrier.wait()
        return action(loaded, ticket, 'reserve')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compete, tickets))
    assert sorted(r.status_code for r in results) == [200, 409]
    stock = next(s for s in loaded.get('/api/inventory').json() if s['sku'] == 'G300' and s['warehouse'] == 'Москва')
    assert stock['pilot_reserved'] == 1 and stock['free'] == 0


def test_repeated_reserve_and_cancel_are_idempotent(loaded):
    ticket = plan(loaded, create(loaded), 'F010').json()
    assert action(loaded, ticket, 'reserve').status_code == 200
    assert action(loaded, ticket, 'reserve').status_code == 200
    stock = next(s for s in loaded.get('/api/inventory').json() if s['sku'] == 'F010' and s['warehouse'] == 'Москва')
    assert stock['pilot_reserved'] == 1
    assert action(loaded, ticket, 'release').status_code == 200
    assert action(loaded, ticket, 'release').status_code == 200
    stock = next(s for s in loaded.get('/api/inventory').json() if s['sku'] == 'F010' and s['warehouse'] == 'Москва')
    assert stock['pilot_reserved'] == 0 and stock['external_reserved'] == 6


def test_multi_part_reservation_rolls_back_on_shortage(loaded):
    ticket = plan(loaded, create(loaded), 'F010').json()
    ticket = plan(loaded, ticket, 'G200').json()
    assert action(loaded, ticket, 'reserve').status_code == 409
    assert all(p['reserved_quantity'] == 0 for p in loaded.get(f'/api/tickets/{ticket["id"]}').json()['plans'])


def test_equipment_change_releases_old_reservations(loaded):
    from .conftest import update
    ticket = plan(loaded, create(loaded), 'F010').json()
    ticket = action(loaded, ticket, 'reserve').json()
    ticket = update(loaded, ticket, equipment_id='EQ01')
    assert ticket['plans'] == []
    assert not ticket['data']['equipment_confirmed']
    stock = next(s for s in loaded.get('/api/inventory').json() if s['sku'] == 'F010' and s['warehouse'] == 'Москва')
    assert stock['pilot_reserved'] == 0


def test_cross_city_transfer_and_working_day(loaded):
    from .conftest import update
    ticket = create(loaded, 'Кафе «Парк»', 'На машине 211 код E11, вода в баке есть.')
    ticket = plan(loaded, ticket, 'L200', 'Тула').json()
    ticket = confirm_diagnostic(loaded, ticket)
    ticket = action(loaded, ticket, 'reserve').json()
    assert 'transfer' in [b['key'] for b in ticket['readiness']['blockers']]
    pid = ticket['plans'][0]['id']
    payload = {'revision': ticket['revision'], 'available_on': '2026-11-16', 'note': 'Согласовано ответственными складов'}
    assert loaded.post(f'/api/tickets/{ticket["id"]}/parts/{pid}/transfer', json=payload).status_code == 409
    payload['available_on'] = '2026-11-17'
    ticket = loaded.post(f'/api/tickets/{ticket["id"]}/parts/{pid}/transfer', json=payload).json()
    assert 'transfer' in [b['key'] for b in ticket['readiness']['blockers']]
    ticket = update(loaded, ticket, visit_date='2026-11-17')
    assert 'transfer' not in [b['key'] for b in ticket['readiness']['blockers']]
