import json
from datetime import date

from .db import DomainError, audit, now, require_ticket, touch
from .rules import next_business_day


def inventory(conn, model=None):
    rows = conn.execute('''SELECT s.*,p.name,p.models,p.source_ref,
        COALESCE((SELECT SUM(r.quantity) FROM reservations r JOIN part_plans pp ON pp.id=r.plan_id
          WHERE pp.sku=s.sku AND pp.warehouse=s.warehouse),0) AS pilot_reserved
        FROM stock s JOIN parts p ON p.sku=s.sku ORDER BY p.sku,s.warehouse''').fetchall()
    return [{**dict(r), 'models': json.loads(r['models']),
             'free': r['on_hand'] - r['external_reserved'] - r['pilot_reserved'],
             'compatible': model in json.loads(r['models']) if model else None} for r in rows]


def plans_for(conn, ticket_id, equipment=None):
    rows = conn.execute('''SELECT pp.*,p.name,p.models,r.quantity AS reserved_quantity,r.created_at AS reserved_at
          FROM part_plans pp JOIN parts p ON pp.sku=p.sku LEFT JOIN reservations r ON r.plan_id=pp.id
          WHERE pp.ticket_id=? ORDER BY pp.id''', (ticket_id,)).fetchall()
    stocks = {(r['sku'], r['warehouse']): r for r in inventory(conn)}
    result = []
    for row in rows:
        item = dict(row)
        item['models'] = json.loads(item['models'])
        item['compatible'] = bool(equipment and equipment['model'] in item['models'])
        item['transfer_required'] = bool(equipment and not equipment['address'].startswith(item['warehouse']))
        item['reserved_quantity'] = item['reserved_quantity'] or 0
        item['free'] = stocks[(item['sku'], item['warehouse'])]['free']
        result.append(item)
    return result


def validate_compatibility(conn, ticket, sku):
    part = conn.execute('SELECT * FROM parts WHERE sku=?', (sku,)).fetchone()
    eq = conn.execute('SELECT * FROM equipment WHERE id=?', (ticket['equipment_id'],)).fetchone()
    if not part:
        raise DomainError('part_not_found', 'Деталь отсутствует в справочнике.', 404)
    if not eq:
        raise DomainError('equipment_required', 'Сначала выберите машину из реестра.')
    if eq['model'] not in json.loads(part['models']):
        raise DomainError('incompatible_part', f'Деталь {sku} несовместима с {eq["model"]}. Прокладки разных серий не взаимозаменяемы.')
    return dict(eq)


def add_plan(conn, ticket_id, body, actor):
    ticket = require_ticket(conn, ticket_id, body.revision)
    validate_compatibility(conn, ticket, body.sku)
    existing = conn.execute('SELECT * FROM part_plans WHERE ticket_id=? AND sku=? AND warehouse=?',
                            (ticket_id, body.sku, body.warehouse)).fetchone()
    if existing:
        raise DomainError('plan_exists', 'Деталь с этого склада уже добавлена. Удалите строку перед изменением количества.')
    if not conn.execute('SELECT 1 FROM stock WHERE sku=? AND warehouse=?', (body.sku, body.warehouse)).fetchone():
        raise DomainError('warehouse_not_found', 'Остаток для этого склада не задан.', 404)
    conn.execute('INSERT INTO part_plans(ticket_id,sku,warehouse,quantity) VALUES(?,?,?,?)',
                 (ticket_id, body.sku, body.warehouse, body.quantity))
    touch(conn, ticket_id)
    audit(conn, 'part_added', body.model_dump(), ticket_id, actor)


def reserve(conn, ticket_id, revision, actor):
    ticket = require_ticket(conn, ticket_id, revision)
    plans = plans_for(conn, ticket_id)
    if not plans:
        raise DomainError('empty_plan', 'Сначала добавьте детали в план.')
    changes = []
    for plan in plans:
        validate_compatibility(conn, ticket, plan['sku'])
        needed = plan['quantity'] - plan['reserved_quantity']
        if needed > plan['free']:
            raise DomainError('insufficient_stock', f'{plan["sku"]}, {plan["warehouse"]}: свободно {plan["free"]}, требуется ещё {needed}. Исходные резервы заняты другими выездами.')
        if needed:
            changes.append(plan)
    for plan in changes:
        conn.execute('INSERT INTO reservations(plan_id,quantity,created_at) VALUES(?,?,?) ON CONFLICT(plan_id) DO UPDATE SET quantity=excluded.quantity',
                     (plan['id'], plan['quantity'], now()))
    if changes:
        audit(conn, 'reserved', {'plans': [p['id'] for p in changes]}, ticket_id, actor)
    return not changes


def release(conn, ticket_id, revision, actor):
    require_ticket(conn, ticket_id, revision)
    cur = conn.execute('DELETE FROM reservations WHERE plan_id IN (SELECT id FROM part_plans WHERE ticket_id=?)', (ticket_id,))
    if cur.rowcount:
        conn.execute('UPDATE tickets SET prepared_revision=NULL,prepared_at=NULL,updated_at=? WHERE id=?', (now(), ticket_id))
        audit(conn, 'reservations_cancelled', {'count': cur.rowcount}, ticket_id, actor)
    return cur.rowcount


def confirm_transfer(conn, ticket_id, plan_id, body, actor):
    ticket = require_ticket(conn, ticket_id, body.revision)
    plan = conn.execute('SELECT * FROM part_plans WHERE id=? AND ticket_id=?', (plan_id, ticket_id)).fetchone()
    if not plan:
        raise DomainError('plan_not_found', 'Позиция плана не найдена.', 404)
    # Case dates can be in the future; planning anchor is the request date, not an invented same-day transfer.
    message = conn.execute('SELECT received_at FROM messages WHERE ticket_id=? ORDER BY received_at DESC LIMIT 1', (ticket_id,)).fetchone()
    earliest = next_business_day(date.fromisoformat(max(message['received_at'][:10], now()[:10])))
    if body.available_on < earliest:
        raise DomainError('transfer_too_early', f'Перевоз занимает 1 рабочий день. Получение возможно не раньше {earliest}.')
    conn.execute('UPDATE part_plans SET transfer_confirmed=1,available_on=?,transfer_note=? WHERE id=?',
                 (body.available_on.isoformat(), body.note, plan_id))
    touch(conn, ticket_id)
    audit(conn, 'transfer_agreed', body.model_dump(mode='json'), ticket_id, actor)
