"""Server-clock measurement; no synthetic dispatcher observations or self-grading."""
import csv
import hashlib
import io
import json
import sqlite3
import statistics
from datetime import datetime

from .card import engineer_card
from .db import DomainError, audit, encode, now, require_ticket

LEASE_MS = 120000
OPEN_STATES = {'working', 'waiting', 'paused'}


def elapsed_ms(start, end):
    return max(0, round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() * 1000))


def event(conn, run_id, kind, details):
    conn.execute('INSERT INTO measurement_events(run_id,type,details,created_at) VALUES(?,?,?,?)',
                 (run_id, kind, encode(details), now()))


def require_run(conn, run_id, client_id=None, revision=None):
    row = conn.execute('SELECT * FROM measurement_runs WHERE id=?', (run_id,)).fetchone()
    if not row:
        raise DomainError('measurement_missing', 'Замер не найден.', 404)
    run = dict(row)
    if client_id is not None and client_id != run['client_id']:
        raise DomainError('measurement_other_tab', 'Таймер открыт в другом окне. Продолжите в том окне, чтобы не считать время дважды.')
    if revision is not None and revision != run['revision']:
        raise DomainError('measurement_stale', 'Замер изменился. Обновите его перед действием.')
    return run


def accrue(conn, run):
    stamp = now()
    if run['state'] not in OPEN_STATES:
        return run
    total = elapsed_ms(run['accounted_at'], stamp)
    # Never silently count a disconnected browser as hours of human work.
    accounted = min(total, max(0, LEASE_MS - elapsed_ms(run['last_seen_at'], run['accounted_at'])))
    unknown = total - accounted
    field = {'working': 'active_ms', 'waiting': 'waiting_ms', 'paused': 'paused_ms'}[run['state']]
    conn.execute(f'UPDATE measurement_runs SET {field}={field}+?,unknown_ms=unknown_ms+?,accounted_at=? WHERE id=?',
                 (accounted, unknown, stamp, run['id']))
    if unknown:
        event(conn, run['id'], 'unobserved_interval', {'ms': unknown, 'previous_state': run['state']})
    return require_run(conn, run['id'])


def start(conn, body, actor):
    previous = conn.execute('SELECT * FROM measurement_runs WHERE id=?', (body.request_id,)).fetchone()
    if previous:
        keys = ('participant', 'participant_kind', 'method', 'context', 'comparison_key', 'process_description', 'ticket_id', 'client_id')
        if any(previous[k] != getattr(body, k) for k in keys):
            raise DomainError('measurement_request_reused', 'Ключ начала замера уже использован с другими данными.')
        return view(conn, body.request_id)
    if body.ticket_id:
        require_ticket(conn, body.ticket_id)
    active = conn.execute("SELECT id FROM measurement_runs WHERE participant=? AND state IN ('working','waiting','paused')", (body.participant,)).fetchone()
    if active:
        raise DomainError('measurement_already_running', 'У этого участника уже есть открытый замер. Завершите или продолжите его.', details={'run_id': active['id']})
    stamp = now()
    conn.execute('''INSERT INTO measurement_runs(id,participant,participant_kind,method,context,comparison_key,
        process_description,ticket_id,client_id,state,started_at,accounted_at,last_seen_at)
        VALUES(?,?,?,?,?,?,?,?,?,'working',?,?,?)''',
        (body.request_id, body.participant, body.participant_kind, body.method, body.context, body.comparison_key,
         body.process_description, body.ticket_id, body.client_id, stamp, stamp, stamp))
    event(conn, body.request_id, 'started', {'method': body.method, 'participant_kind': body.participant_kind})
    audit(conn, 'measurement_started', {'run_id': body.request_id, 'participant_kind': body.participant_kind, 'method': body.method}, body.ticket_id, actor)
    return view(conn, body.request_id)


def pulse(conn, run_id, body):
    run = require_run(conn, run_id, body.client_id)
    if run['state'] not in OPEN_STATES or body.sequence <= run['heartbeat_sequence']:
        return view(conn, run_id)
    run = accrue(conn, run)
    if body.activations < run['activations']:
        raise DomainError('measurement_counter_regressed', 'Счётчик действий устарел. Обновите таймер.')
    conn.execute('UPDATE measurement_runs SET last_seen_at=?,heartbeat_sequence=?,activations=? WHERE id=?',
                 (now(), body.sequence, body.activations, run_id))
    return view(conn, run_id)


def set_artifact(conn, run_id, artifact, ticket_revision=None):
    raw = encode(artifact)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    conn.execute('UPDATE measurement_runs SET artifact=?,artifact_hash=?,submitted_ticket_revision=? WHERE id=?',
                 (raw, digest, ticket_revision, run_id))


def transition(conn, run_id, body, actor):
    run = require_run(conn, run_id, body.client_id, body.revision)
    if body.state == run['state']:
        return view(conn, run_id)
    if run['state'] == 'abandoned':
        raise DomainError('measurement_closed', 'Прерванный замер не возобновляется. Он сохранён в отчёте.')
    if body.state == 'waiting' and not body.reason:
        raise DomainError('measurement_wait_reason', 'Укажите причину ожидания.', 422)
    reopening = run['state'] == 'finished'
    if reopening and body.state != 'working':
        raise DomainError('measurement_rework_state', 'Для доработки сначала возобновите работу.')
    if reopening and len(body.note) < 5:
        raise DomainError('measurement_rework_note', 'Запишите причину доработки.', 422)
    if body.state in {'finished', 'abandoned'}:
        if body.state == 'finished' and body.outcome not in {'ready', 'blocked', 'manager'}:
            raise DomainError('measurement_outcome_required', 'Укажите результат работы.', 422)
        if (body.state == 'abandoned' or body.outcome in {'blocked', 'manager'}) and len(body.note) < 5:
            raise DomainError('measurement_outcome_note', 'Запишите, почему задача не завершилась готовой заявкой.', 422)
        if run['method'] == 'pilot' and body.state == 'finished':
            card = engineer_card(conn, run['ticket_id'])
            ticket = require_ticket(conn, run['ticket_id'])
            actual = 'ready' if card['ready'] else 'manager' if ticket['state'] == 'manager' else 'blocked'
            if body.outcome != actual:
                raise DomainError('measurement_wrong_outcome', 'Результат не соответствует текущей заявке. Нельзя записать готовность в обход проверок.')
            set_artifact(conn, run_id, card, card['revision'])
    if reopening:
        conn.execute('''UPDATE measurement_runs SET review_wait_ms=review_wait_ms+?,rework_count=rework_count+1,
             artifact=NULL,artifact_hash=NULL,submitted_ticket_revision=NULL WHERE id=?''',
             (elapsed_ms(run['finished_at'], now()), run_id))
    else:
        accrue(conn, run)
    stamp = now()
    finished = stamp if body.state in {'finished', 'abandoned'} else None
    outcome = 'abandoned' if body.state == 'abandoned' else body.outcome if body.state == 'finished' else None
    try:
        conn.execute('''UPDATE measurement_runs SET state=?,wait_reason=?,finished_at=?,outcome=?,note=?,
            last_seen_at=?,accounted_at=?,revision=revision+1 WHERE id=?''',
            (body.state, body.reason if body.state == 'waiting' else '', finished, outcome, body.note,
             stamp, stamp, run_id))
    except sqlite3.IntegrityError as exc:
        raise DomainError('measurement_already_running', 'У участника уже есть другой открытый замер.') from exc
    event(conn, run_id, 'rework_started' if reopening else body.state, {'reason': body.reason, 'outcome': outcome, 'note': body.note})
    if finished:
        audit(conn, 'measurement_finished', {'run_id': run_id, 'outcome': outcome}, run['ticket_id'], actor)
    return view(conn, run_id)


def attach_artifact(conn, run_id, body, actor):
    run = require_run(conn, run_id, body.client_id, body.revision)
    if run['method'] != 'manual' or run['state'] != 'finished':
        raise DomainError('measurement_artifact_state', 'Текст ручной карточки прикладывается после завершения ручного замера.')
    set_artifact(conn, run_id, {'manual_card': body.text, 'outcome': run['outcome']})
    conn.execute('UPDATE measurement_runs SET revision=revision+1 WHERE id=?', (run_id,))
    event(conn, run_id, 'manual_artifact_attached', {})
    audit(conn, 'measurement_artifact_attached', {'run_id': run_id}, actor=actor)
    return view(conn, run_id)


def review(conn, run_id, body, actor):
    run = require_run(conn, run_id)
    if run['state'] != 'finished' or not run['artifact_hash']:
        raise DomainError('measurement_no_result', 'Сначала завершите замер и приложите результат.')
    if body.reviewer.casefold() == run['participant'].casefold():
        raise DomainError('measurement_self_review', 'Карточку должен проверить другой участник.')
    if body.artifact_hash != run['artifact_hash']:
        raise DomainError('measurement_stale_artifact', 'Снимок карточки изменился. Проверьте актуальный результат.')
    accepted = all(body.checks.values()) and not body.critical_errors
    conn.execute('''INSERT INTO measurement_reviews(run_id,reviewer,reviewer_kind,artifact_hash,checks,critical_errors,accepted,note,created_at)
        VALUES(?,?,?,?,?,?,?,?,?)''', (run_id, body.reviewer, body.reviewer_kind, body.artifact_hash,
        encode(body.checks), encode(body.critical_errors), int(accepted), body.note, now()))
    event(conn, run_id, 'review_recorded', {'accepted': accepted, 'reviewer_kind': body.reviewer_kind})
    audit(conn, 'measurement_reviewed', {'run_id': run_id, 'accepted': accepted}, run['ticket_id'], actor)
    return view(conn, run_id)


def view(conn, run_id):
    run = require_run(conn, run_id)
    # Projection only; GET requests never mutate the timer.
    if run['state'] in OPEN_STATES:
        delta = elapsed_ms(run['accounted_at'], now())
        available = max(0, LEASE_MS - elapsed_ms(run['last_seen_at'], run['accounted_at']))
        field = {'working': 'active_ms', 'waiting': 'waiting_ms', 'paused': 'paused_ms'}[run['state']]
        run[field] += min(delta, available)
        run['unknown_ms'] += max(0, delta - available)
    run['elapsed_ms'] = elapsed_ms(run['started_at'], run['finished_at'] or now())
    run['artifact'] = json.loads(run['artifact']) if run['artifact'] else None
    row = conn.execute('SELECT * FROM measurement_reviews WHERE run_id=? AND artifact_hash=? ORDER BY id DESC LIMIT 1', (run_id, run['artifact_hash'])).fetchone()
    run['review'] = {**dict(row), 'checks': json.loads(row['checks']), 'critical_errors': json.loads(row['critical_errors'])} if row else None
    # Test reviewers must never create a field-study quality acceptance.
    run['eligible_time'] = run['participant_kind'] == 'dispatcher' and run['context'] != 'practice' and run['state'] == 'finished' and run['outcome'] == 'ready' and run['unknown_ms'] == 0 and bool(run['review'] and run['review']['accepted'] and run['review']['reviewer_kind'] == 'engineer')
    return run


def list_runs(conn):
    return [view(conn, row['id']) for row in conn.execute('SELECT id FROM measurement_runs ORDER BY started_at,id')]


def distribution(values):
    if not values:
        return {'n': 0, 'median_ms': None, 'q1_ms': None, 'q3_ms': None, 'min_ms': None, 'max_ms': None}
    q = statistics.quantiles(values, n=4, method='inclusive') if len(values) > 1 else [values[0]] * 3
    return {'n': len(values), 'median_ms': statistics.median(values), 'q1_ms': q[0], 'q3_ms': q[2], 'min_ms': min(values), 'max_ms': max(values)}


def report(conn):
    runs = list_runs(conn)
    human = [r for r in runs if r['participant_kind'] == 'dispatcher' and r['context'] != 'practice']
    # First attempt is selected before filtering for speed or success. Rework stays in that run.
    first = {}
    for run in human:
        if run['context'] == 'controlled' and run['comparison_key']:
            first.setdefault((run['participant'], run['comparison_key'], run['method']), run)
    pairs = []
    for participant, key in sorted(set((p, k) for p, k, _ in first)):
        manual, pilot = first.get((participant, key, 'manual')), first.get((participant, key, 'pilot'))
        valid = bool(manual and pilot and manual['eligible_time'] and pilot['eligible_time'])
        pairs.append({'participant': participant, 'comparison_key': key,
                      'manual_id': manual['id'] if manual else None, 'pilot_id': pilot['id'] if pilot else None,
                      'eligible': valid, 'manual_ms': manual['active_ms'] if valid else None,
                      'pilot_ms': pilot['active_ms'] if valid else None,
                      'saved_ms': manual['active_ms'] - pilot['active_ms'] if valid else None})
    accepted = [r for r in human if r['eligible_time']]
    reviewed = [r for r in human if r['review'] and r['review']['reviewer_kind'] == 'engineer']
    ready_reviewed = [r for r in reviewed if r['outcome'] == 'ready']
    participants = sorted(set(r['participant'] for r in human))
    pair_subjects = sorted(set(p['participant'] for p in pairs if p['eligible']))
    paired_manual = [p['manual_ms'] for p in pairs if p['eligible']]
    paired_pilot = [p['pilot_ms'] for p in pairs if p['eligible']]
    comparison = None
    if paired_manual and statistics.median(paired_manual) > 0:
        # Pair-first summaries; also publish participant medians, avoiding pseudo-replication.
        subjects = [{'participant': person, 'median_saved_ms': statistics.median(p['saved_ms'] for p in pairs if p['eligible'] and p['participant'] == person)} for person in pair_subjects]
        comparison = {'manual': distribution(paired_manual), 'pilot': distribution(paired_pilot),
                      'median_paired_saved_ms': statistics.median(p['saved_ms'] for p in pairs if p['eligible']),
                      'difference_of_medians_percent': 100 * (statistics.median(paired_manual) - statistics.median(paired_pilot)) / statistics.median(paired_manual),
                      'participant_summaries': subjects, 'confidence_interval': None,
                      'inference': 'Описательная пилотная оценка; интервальная и причинная оценка не заявляется.'}
    return {'generated_at': now(), 'human_identity_verification': 'Должность и идентичность подтверждает организатор, не приложение.',
            'all_attempts': len(runs), 'dispatcher_attempts': len(human), 'dispatcher_participants': len(participants),
            'automated_attempts': sum(r['participant_kind'] == 'automated' for r in runs),
            'tester_or_practice_attempts': sum(r['participant_kind'] != 'automated' and (r['participant_kind'] == 'tester' or r['context'] == 'practice') for r in runs),
            'eligible_correct_attempts': len(accepted), 'unfinished_attempts': sum(r['state'] in OPEN_STATES for r in human),
            'unknown_time_attempts': sum(r['unknown_ms'] > 0 for r in human),
            'quality': {'accepted': sum(bool(r['review']['accepted']) for r in reviewed), 'reviewed': len(reviewed),
                        'false_ready': sum(bool(r['review']['critical_errors']) for r in ready_reviewed), 'ready_reviewed': len(ready_reviewed)},
            'by_method': {method: {'time': distribution([r['active_ms'] for r in accepted if r['method'] == method]),
                                    'waiting': distribution([r['waiting_ms'] for r in human if r['method'] == method and r['state'] == 'finished']),
                                    'attempts': sum(r['method'] == method for r in human)} for method in ('manual', 'pilot')},
            'pairs': pairs, 'complete_pairs': sum(p['eligible'] for p in pairs), 'paired_participants': len(pair_subjects),
            'comparison': comparison,
            'status': 'observations_available' if comparison else 'no_verified_comparison',
            'message': 'Подтверждённого сравнения времени реальных диспетчеров пока нет.' if not comparison else 'Есть описательные парные наблюдения; проверьте объём выборки и качество.',
            'runs': runs}


def export_csv(conn):
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    columns = ['id', 'participant', 'participant_kind', 'method', 'context', 'comparison_key', 'process_description', 'ticket_id', 'state', 'outcome', 'started_at', 'finished_at', 'active_ms', 'waiting_ms', 'paused_ms', 'unknown_ms', 'review_wait_ms', 'elapsed_ms', 'rework_count', 'activations', 'eligible_time', 'artifact_hash', 'note']
    writer.writerow(columns + ['reviewer', 'reviewer_kind', 'accepted', 'critical_errors'])
    def safe(value):
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
            return "'" + value
        return value
    for run in list_runs(conn):
        review = run['review'] or {}
        writer.writerow([safe(run.get(k)) for k in columns] + [safe(review.get('reviewer', '')), review.get('reviewer_kind', ''), review.get('accepted', ''), ','.join(review.get('critical_errors', []))])
    return '\ufeff' + out.getvalue()
