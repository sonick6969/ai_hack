import json

from .db import DomainError, audit, encode, now, require_ticket, touch
from .extraction import LABELS, combine, extract
from .inventory import plans_for
from .matching import client_name, match_equipment
from .readiness import assess
from .rules import error_explanations


def all_equipment(conn):
    return [dict(e) for e in conn.execute('SELECT * FROM equipment ORDER BY client,id')]


def effective_analysis(messages, data):
    result = combine(messages)
    if data.get('issue_types'):
        result['symptoms'] = list(dict.fromkeys(data['issue_types']))
    return result


def create_message(conn, sender, text, channel, received_at, source, source_ref,
                   external_id=None, external_key=None, import_id=None, analysis=None, actor='Диспетчер'):
    if external_key:
        row = conn.execute('SELECT ticket_id FROM messages WHERE external_key=?', (external_key,)).fetchone()
        if row:
            return row['ticket_id'], False
    analysis = analysis or extract(text, sender)
    match = match_equipment(analysis, sender, text, all_equipment(conn))
    candidate = match['candidates'][0]['id'] if len(match['candidates']) == 1 and match['status'] in ('exact', 'unique') else None
    stamp = now()
    cur = conn.execute('INSERT INTO tickets(equipment_id,source,created_at,updated_at) VALUES(?,?,?,?)',
                       (candidate, source, stamp, stamp))
    ticket_id = cur.lastrowid
    conn.execute('''INSERT INTO messages(external_key,external_id,ticket_id,import_id,sender,channel,text,received_at,analysis,source_ref,source,created_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                 (external_key, external_id, ticket_id, import_id, sender, channel, text, received_at, encode(analysis), source_ref, source, stamp))
    audit(conn, 'message_created', {'external_id': external_id, 'source_ref': source_ref, 'engine': analysis['engine'], 'llm_status': analysis['llm_status']}, ticket_id, actor)
    return ticket_id, True


def possible_duplicates(conn, ticket, messages, analysis, equipment):
    if not messages or ticket['state'] != 'open':
        return []
    sender = client_name(messages[0]['sender'])
    result = []
    for row in conn.execute('SELECT * FROM tickets WHERE state=? AND id<>? ORDER BY id', ('open', ticket['id'])):
        row = dict(row)
        others = [dict(m) for m in conn.execute('SELECT * FROM messages WHERE ticket_id=? ORDER BY id', (row['id'],))]
        if not others or client_name(others[0]['sender']) != sender:
            continue
        other = effective_analysis(others, json.loads(row['data']))
        # A new explicit unknown number must never inherit a known machine from the client.
        if analysis['serials'] and other['serials'] and set(analysis['serials']) != set(other['serials']):
            continue
        if ticket['equipment_id'] and row['equipment_id'] and ticket['equipment_id'] != row['equipment_id']:
            continue
        common = set(analysis['symptoms']) & set(other['symptoms']) - {'unknown', 'request'}
        if not common:
            continue
        # Distinct problems on one machine remain separate; overlap alone is only a suggestion.
        result.append({'id': row['id'], 'label': f'КСР-{row["id"]:03d}', 'sender': others[0]['sender'],
                       'text': others[0]['text'], 'external_id': others[0]['external_id'],
                       'reason': 'Совпадают клиент, возможная машина и тема: ' + ', '.join(LABELS[s] for s in sorted(common)),
                       'revision': row['revision']})
    return result


def detail(conn, ticket_id, with_duplicates=True):
    ticket = require_ticket(conn, ticket_id)
    data = json.loads(ticket['data'])
    messages = [dict(m) for m in conn.execute('SELECT * FROM messages WHERE ticket_id=? ORDER BY id', (ticket_id,))]
    analysis = effective_analysis(messages, data)
    sender = messages[0]['sender'] if messages else ''
    text = '\n'.join(m['text'] for m in messages)
    matching = match_equipment(analysis, sender, text, all_equipment(conn))
    eq = conn.execute('SELECT * FROM equipment WHERE id=?', (ticket['equipment_id'],)).fetchone()
    eq = dict(eq) if eq else None
    plans = plans_for(conn, ticket_id, eq)
    duplicates = possible_duplicates(conn, ticket, messages, analysis, eq) if with_duplicates else []
    readiness = assess(ticket, data, messages, analysis, matching, eq, plans, duplicates)
    for m in messages:
        m['analysis'] = json.loads(m['analysis'])
    return {**ticket, 'label': f'КСР-{ticket_id:03d}', 'data': data, 'messages': messages,
            'analysis': analysis, 'matching': matching, 'equipment': eq, 'plans': plans,
            'duplicates': duplicates, 'readiness': readiness,
            'error_codes': error_explanations(eq, analysis, data),
            'symptom_labels': [LABELS[s] for s in analysis['symptoms']]}


def list_tickets(conn, query='', status='', source='', city=''):
    results = []
    for row in conn.execute("SELECT id FROM tickets WHERE state NOT IN ('merged','closed') ORDER BY id DESC"):
        ticket = detail(conn, row['id'])
        eq = ticket['equipment']
        if status and ticket['readiness']['status'] != status:
            continue
        if source and not any(m['source'] == source for m in ticket['messages']):
            continue
        if city and (not eq or not eq['address'].startswith(city)):
            continue
        searchable = ' '.join([ticket['label']] + [m['sender'] + ' ' + m['text'] + ' ' + (m['external_id'] or '') for m in ticket['messages']] + [eq['serial'] + ' ' + eq['address'] + ' ' + eq['model'] if eq else ''])
        if query and query.lower().replace('ё', 'е') not in searchable.lower().replace('ё', 'е'):
            continue
        results.append({'id': ticket['id'], 'label': ticket['label'], 'revision': ticket['revision'],
                        'sender': ticket['messages'][0]['sender'], 'text': ticket['messages'][0]['text'],
                        'received_at': ticket['messages'][0]['received_at'], 'source': ticket['source'],
                        'sources': sorted(set(m['source'] for m in ticket['messages'])),
                        'channel': ticket['messages'][0]['channel'], 'message_count': len(ticket['messages']),
                        'external_ids': [m['external_id'] for m in ticket['messages'] if m['external_id']],
                        'equipment': eq, 'status': ticket['readiness']['status'], 'can_prepare': ticket['readiness']['can_prepare'],
                        'blockers': ticket['readiness']['blockers'], 'symptom_labels': ticket['symptom_labels'],
                        'warranty': ticket['readiness']['warranty']['required'],
                        'duplicate_count': len(ticket['duplicates'])})
    return results


def patch_ticket(conn, ticket_id, body, actor):
    ticket = require_ticket(conn, ticket_id, body.revision)
    data = json.loads(ticket['data'])
    changes = body.model_dump(exclude_unset=True, mode='json')
    changes.pop('revision')
    for key in list(changes):
        if changes[key] is None and key not in ('equipment_id', 'visit_date', 'answers'):
            changes[key] = False if key.endswith('_confirmed') else ''
    if 'equipment_id' in changes:
        eqid = changes.pop('equipment_id')
        if eqid and not conn.execute('SELECT 1 FROM equipment WHERE id=?', (eqid,)).fetchone():
            raise DomainError('equipment_not_found', 'Машина отсутствует в реестре.', 404)
        if eqid != ticket['equipment_id']:
            conn.execute('DELETE FROM part_plans WHERE ticket_id=?', (ticket_id,))
            data.update(equipment_confirmed=False, address_confirmed=False, plan_confirmed=False)
            conn.execute('UPDATE tickets SET equipment_id=? WHERE id=?', (eqid, ticket_id))
    if 'answers' in changes:
        data['answers'] = {**data.get('answers', {}), **(changes.pop('answers') or {})}
    data.update(changes)
    touch(conn, ticket_id, data)
    audit(conn, 'ticket_updated', {'changes': body.model_dump(exclude_unset=True, mode='json')}, ticket_id, actor)


def merge_ticket(conn, source_id, body, actor):
    if source_id == body.target_id:
        raise DomainError('same_ticket', 'Нельзя объединить заявку с самой собой.')
    source = require_ticket(conn, source_id, body.revision)
    target = require_ticket(conn, body.target_id, body.target_revision)
    if source['state'] != 'open' or target['state'] != 'open':
        raise DomainError('not_open', 'Объединять можно только открытые заявки.')
    if source['equipment_id'] and target['equipment_id'] and source['equipment_id'] != target['equipment_id']:
        raise DomainError('different_equipment', 'Заявки на разные машины нельзя объединять.')
    sm = conn.execute('SELECT sender FROM messages WHERE ticket_id=? ORDER BY id LIMIT 1', (source_id,)).fetchone()
    tm = conn.execute('SELECT sender FROM messages WHERE ticket_id=? ORDER BY id LIMIT 1', (body.target_id,)).fetchone()
    if client_name(sm['sender']) != client_name(tm['sender']):
        raise DomainError('different_clients', 'Нельзя объединять обращения разных клиентов.')
    source_analysis = effective_analysis([dict(m) for m in conn.execute('SELECT * FROM messages WHERE ticket_id=? ORDER BY id', (source_id,))], json.loads(source['data']))
    target_analysis = effective_analysis([dict(m) for m in conn.execute('SELECT * FROM messages WHERE ticket_id=? ORDER BY id', (body.target_id,))], json.loads(target['data']))
    source_issues = set(source_analysis['symptoms']) - {'unknown', 'request'}
    target_issues = set(target_analysis['symptoms']) - {'unknown', 'request'}
    if source_issues and target_issues and not source_issues & target_issues:
        raise DomainError('different_problem', 'Это разные проблемы. Оставьте отдельные заявки на выезд.')
    if source_analysis['serials'] and target_analysis['serials'] and set(source_analysis['serials']) != set(target_analysis['serials']):
        raise DomainError('different_equipment', 'В сообщениях разные номера машин. Объединение запрещено.')
    if conn.execute('SELECT 1 FROM part_plans WHERE ticket_id=?', (source_id,)).fetchone():
        raise DomainError('source_has_parts', 'Сначала удалите план деталей объединяемой заявки. Резервы не переносятся автоматически.')
    conn.execute('UPDATE messages SET ticket_id=? WHERE ticket_id=?', (body.target_id, source_id))
    if not target['equipment_id'] and source['equipment_id']:
        conn.execute('UPDATE tickets SET equipment_id=? WHERE id=?', (source['equipment_id'], body.target_id))
    data = json.loads(target['data'])
    data.update(symptom_confirmed=False, equipment_confirmed=False, address_confirmed=False, plan_confirmed=False)
    data['answers'] = {}  # New evidence requires confirmation; old answers remain in audit.
    data.pop('duplicate_resolution', None)
    touch(conn, body.target_id, data)
    conn.execute("UPDATE tickets SET state='merged',merged_into=?,prepared_revision=NULL,revision=revision+1,updated_at=? WHERE id=?",
                 (body.target_id, now(), source_id))
    audit(conn, 'tickets_merged', {'source_id': source_id, 'target_id': body.target_id, 'reason': body.reason}, body.target_id, actor)
    audit(conn, 'merged_into', {'target_id': body.target_id}, source_id, actor)
