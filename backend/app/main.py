import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, File, Header, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, inventory, repository
from .card import card_html, engineer_card
from .db import DomainError, audit, connect, encode, migrate, now, require_ticket, touch, transaction
from .extraction import combine, extract
from .matching import client_name
from .importer import HEADERS, import_excel
from .schemas import Approval, Manager, Merge, NewMessage, PlanCreate, Revision, TicketPatch, Transfer


@asynccontextmanager
async def lifespan(app):
    migrate()
    yield


app = FastAPI(title='КофеСервис · подготовка выезда', version='1.0.0', lifespan=lifespan)


def db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def actor(x_actor: str = Header(default='Диспетчер', max_length=150)):
    return x_actor.strip() or 'Диспетчер'


@app.exception_handler(DomainError)
async def domain_error(request, exc):
    return JSONResponse(status_code=exc.status, content={'error': {'code': exc.code, 'message': exc.message, 'details': exc.details}})


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(status_code=422, content={'error': {'code': 'validation', 'message': 'Проверьте обязательные поля и формат значений.',
        'details': [{'field': '.'.join(map(str, err['loc'])), 'message': err['msg']} for err in exc.errors()]}})


@app.exception_handler(sqlite3.OperationalError)
async def storage_error(request, exc):
    logging.exception('SQLite operation failed')
    return JSONResponse(status_code=503, content={'error': {'code': 'storage_busy', 'message': 'Хранилище временно недоступно. Повторите действие; изменения не подтверждены.'}})


@app.exception_handler(Exception)
async def server_error(request, exc):
    logging.exception('Unhandled application error')
    return JSONResponse(status_code=500, content={'error': {'code': 'internal', 'message': 'Не удалось выполнить действие. Обновите данные и повторите. Подробности записаны в журнал сервера.'}})


@app.get('/api/health')
def health(conn=Depends(db)):
    conn.execute('SELECT 1')
    return {'status': 'ok', 'llm_enabled': os.getenv('LLM_ENABLED', 'false').lower() == 'true',
            'llm_configured': bool(os.getenv('OPENAI_API_KEY') and os.getenv('LLM_MODEL')), 'version': app.version}


@app.get('/api/summary')
def summary(conn=Depends(db)):
    tickets = repository.list_tickets(conn)
    return {'messages': conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],
            'tickets': len(tickets), 'equipment': conn.execute('SELECT COUNT(*) FROM equipment').fetchone()[0],
            'parts': conn.execute('SELECT COUNT(*) FROM parts').fetchone()[0],
            'ready': sum(t['status'] == 'ready' for t in tickets),
            'blocked': sum(t['status'] == 'blocked' for t in tickets),
            'manager': sum(t['status'] == 'manager' for t in tickets),
            'warranty': sum(any(b['key'] == 'approval' for b in t['blockers']) for t in tickets),
            'case_available': config.CASE_FILE.exists()}


@app.get('/api/tickets')
def tickets(q: str = Query(default='', max_length=200), status: str = '', source: str = '', city: str = '', conn=Depends(db)):
    return repository.list_tickets(conn, q, status, source, city)


@app.get('/api/tickets/{ticket_id}')
def get_ticket(ticket_id: int, conn=Depends(db)):
    return repository.detail(conn, ticket_id)


@app.post('/api/messages', status_code=201)
def new_message(body: NewMessage, conn=Depends(db), who=Depends(actor)):
    analysis = extract(body.text, body.sender)  # Network is outside the write transaction.
    stamp = body.received_at.isoformat() if body.received_at else datetime.now().astimezone().isoformat()
    with transaction(conn):
        key = 'manual:' + body.request_id if body.request_id else None
        if key:
            previous = conn.execute('SELECT sender,text FROM messages WHERE external_key=?', (key,)).fetchone()
            if previous and (previous['sender'] != body.sender or previous['text'] != body.text):
                raise DomainError('idempotency_conflict', 'Этот ключ запроса уже использован для другого текста.')
        ticket_id, created = repository.create_message(conn, body.sender, body.text, body.channel, stamp, 'manual', 'Ручной ввод', external_key=key, analysis=analysis, actor=who)
    return {'ticket': repository.detail(conn, ticket_id), 'created': created}


@app.post('/api/tickets/{ticket_id}/messages', status_code=201)
def append_message(ticket_id: int, body: NewMessage, revision: int = Query(ge=1), conn=Depends(db), who=Depends(actor)):
    analysis = extract(body.text, body.sender)
    stamp = body.received_at.isoformat() if body.received_at else datetime.now().astimezone().isoformat()
    with transaction(conn):
        old_ticket = require_ticket(conn, ticket_id, revision)
        old_messages = [dict(m) for m in conn.execute('SELECT * FROM messages WHERE ticket_id=? ORDER BY id', (ticket_id,))]
        if old_messages and client_name(old_messages[0]['sender']) != client_name(body.sender):
            raise DomainError('different_client', 'Обращение другого клиента нужно сохранить отдельной заявкой.')
        old_analysis = repository.effective_analysis(old_messages, json.loads(old_ticket['data']))
        existing_issues = set(old_analysis['symptoms']) - {'unknown', 'request'}
        new_issues = set(analysis['symptoms']) - {'unknown', 'request'}
        if existing_issues and new_issues and not existing_issues & new_issues:
            raise DomainError('different_problem', 'Новая проблема требует отдельной заявки. Создайте новое обращение из очереди.')
        if old_ticket['equipment_id'] and analysis['serials']:
            selected_eq = conn.execute('SELECT serial FROM equipment WHERE id=?', (old_ticket['equipment_id'],)).fetchone()
            if selected_eq and analysis['serials'] != [selected_eq['serial']]:
                raise DomainError('different_equipment', 'Сообщение о другой машине нужно сохранить отдельной заявкой.')
        key = 'manual:' + body.request_id if body.request_id else None
        prior = conn.execute('SELECT * FROM messages WHERE external_key=?', (key,)).fetchone() if key else None
        if prior:
            if prior['ticket_id'] != ticket_id or prior['text'] != body.text or prior['sender'] != body.sender:
                raise DomainError('idempotency_conflict', 'Ключ запроса уже использован для другого сообщения.')
        else:
            conn.execute('''INSERT INTO messages(external_key,ticket_id,sender,channel,text,received_at,analysis,source_ref,source,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)''', (key, ticket_id, body.sender, body.channel, body.text, stamp, encode(analysis), 'Уточнение диспетчера', 'manual', now()))
            old = require_ticket(conn, ticket_id)
            data = json.loads(old['data'])
            data.update(symptom_confirmed=False, plan_confirmed=False, equipment_confirmed=False, address_confirmed=False)
            data['answers'] = {}
            data.pop('issue_types', None)
            data.pop('identity_resolution', None)
            data.pop('duplicate_resolution', None)
            touch(conn, ticket_id, data)
            audit(conn, 'message_appended', {'engine': analysis['engine'], 'llm_status': analysis['llm_status']}, ticket_id, who)
    return repository.detail(conn, ticket_id)


@app.patch('/api/tickets/{ticket_id}')
def update_ticket(ticket_id: int, body: TicketPatch, conn=Depends(db), who=Depends(actor)):
    with transaction(conn):
        repository.patch_ticket(conn, ticket_id, body, who)
    return repository.detail(conn, ticket_id)


@app.post('/api/tickets/{ticket_id}/merge')
def merge(ticket_id: int, body: Merge, conn=Depends(db), who=Depends(actor)):
    with transaction(conn):
        repository.merge_ticket(conn, ticket_id, body, who)
    return repository.detail(conn, body.target_id)


@app.post('/api/tickets/{ticket_id}/manager')
def manager(ticket_id: int, body: Manager, conn=Depends(db), who=Depends(actor)):
    with transaction(conn):
        row = require_ticket(conn, ticket_id, body.revision)
        if conn.execute('SELECT 1 FROM part_plans WHERE ticket_id=?', (ticket_id,)).fetchone():
            raise DomainError('has_parts', 'Сначала удалите план деталей и освободите резервы.')
        data = json.loads(row['data'])
        data['manager_note'] = body.note
        touch(conn, ticket_id, data)
        conn.execute("UPDATE tickets SET state='manager' WHERE id=?", (ticket_id,))
        audit(conn, 'manager_route_recorded', {'note': body.note}, ticket_id, who)
    return repository.detail(conn, ticket_id)


@app.post('/api/tickets/{ticket_id}/reopen')
def reopen(ticket_id: int, body: Revision, conn=Depends(db), who=Depends(actor)):
    with transaction(conn):
        require_ticket(conn, ticket_id, body.revision)
        conn.execute("UPDATE tickets SET state='open' WHERE id=?", (ticket_id,))
        touch(conn, ticket_id)
        audit(conn, 'reopened', {}, ticket_id, who)
    return repository.detail(conn, ticket_id)


@app.post('/api/tickets/{ticket_id}/parts', status_code=201)
def add_part(ticket_id: int, body: PlanCreate, conn=Depends(db), who=Depends(actor)):
    with transaction(conn):
        inventory.add_plan(conn, ticket_id, body, who)
    return repository.detail(conn, ticket_id)


@app.delete('/api/tickets/{ticket_id}/parts/{plan_id}')
def remove_part(ticket_id: int, plan_id: int, revision: int = Query(ge=1), conn=Depends(db), who=Depends(actor)):
    with transaction(conn):
        require_ticket(conn, ticket_id, revision)
        row = conn.execute('SELECT 1 FROM part_plans WHERE id=? AND ticket_id=?', (plan_id, ticket_id)).fetchone()
        if not row:
            raise DomainError('plan_not_found', 'Деталь не найдена в плане.', 404)
        conn.execute('DELETE FROM part_plans WHERE id=?', (plan_id,))
        touch(conn, ticket_id)
        audit(conn, 'part_removed_and_released', {'plan_id': plan_id}, ticket_id, who)
    return repository.detail(conn, ticket_id)


@app.post('/api/tickets/{ticket_id}/reserve')
def reserve_parts(ticket_id: int, body: Revision, conn=Depends(db), who=Depends(actor)):
    with transaction(conn):
        inventory.reserve(conn, ticket_id, body.revision, who)
    return repository.detail(conn, ticket_id)


@app.post('/api/tickets/{ticket_id}/release')
def release_parts(ticket_id: int, body: Revision, conn=Depends(db), who=Depends(actor)):
    with transaction(conn):
        inventory.release(conn, ticket_id, body.revision, who)
    return repository.detail(conn, ticket_id)


@app.post('/api/tickets/{ticket_id}/parts/{plan_id}/transfer')
def transfer(ticket_id: int, plan_id: int, body: Transfer, conn=Depends(db), who=Depends(actor)):
    with transaction(conn):
        inventory.confirm_transfer(conn, ticket_id, plan_id, body, who)
    return repository.detail(conn, ticket_id)


@app.post('/api/tickets/{ticket_id}/approval')
def approve(ticket_id: int, body: Approval, conn=Depends(db), who=Depends(actor)):
    with transaction(conn):
        row = require_ticket(conn, ticket_id, body.revision)
        data = json.loads(row['data'])
        data['approval'] = {'name': body.name, 'note': body.note, 'at': now(), 'revision': row['revision']}
        conn.execute('UPDATE tickets SET data=?,updated_at=? WHERE id=?', (encode(data), now(), ticket_id))
        audit(conn, 'senior_approval_recorded', data['approval'], ticket_id, who)
    return repository.detail(conn, ticket_id)


@app.post('/api/tickets/{ticket_id}/prepare')
def prepare(ticket_id: int, body: Revision, conn=Depends(db), who=Depends(actor)):
    with transaction(conn):
        require_ticket(conn, ticket_id, body.revision)
        ticket = repository.detail(conn, ticket_id)
        if not ticket['readiness']['can_prepare']:
            raise DomainError('not_ready', 'Выезд ещё не подготовлен. Устраните перечисленные препятствия.', details=ticket['readiness']['blockers'])
        if not ticket['readiness']['ready']:
            conn.execute('UPDATE tickets SET prepared_revision=revision,prepared_at=?,updated_at=? WHERE id=?', (now(), now(), ticket_id))
            audit(conn, 'prepared', {'revision': body.revision}, ticket_id, who)
    return repository.detail(conn, ticket_id)


@app.get('/api/tickets/{ticket_id}/card')
def card(ticket_id: int, conn=Depends(db)):
    return engineer_card(conn, ticket_id)


@app.get('/api/tickets/{ticket_id}/print', response_class=HTMLResponse)
def print_card(ticket_id: int, conn=Depends(db)):
    return HTMLResponse(card_html(engineer_card(conn, ticket_id)), headers={'Cache-Control': 'no-store'})


@app.get('/api/equipment')
def equipment(conn=Depends(db)):
    return repository.all_equipment(conn)


@app.get('/api/inventory')
def stock(model: str | None = None, conn=Depends(db)):
    return inventory.inventory(conn, model)


@app.get('/api/rules')
def rules(conn=Depends(db)):
    return [dict(r) for r in conn.execute('SELECT * FROM rules ORDER BY rowid')]


@app.get('/api/audit')
def journal(ticket_id: int | None = None, conn=Depends(db)):
    query = 'SELECT * FROM audit' + (' WHERE ticket_id=?' if ticket_id is not None else '') + ' ORDER BY id DESC LIMIT 200'
    return [{**dict(r), 'details': json.loads(r['details'])} for r in conn.execute(query, (ticket_id,) if ticket_id is not None else ())]


@app.get('/api/imports')
def imports(conn=Depends(db)):
    return [{**json.loads(r['report']), 'id': r['id']} for r in conn.execute('SELECT * FROM imports ORDER BY id DESC')]


@app.post('/api/imports/case')
def import_case(conn=Depends(db), who=Depends(actor)):
    if not config.CASE_FILE.exists():
        raise DomainError('case_missing', 'Исходный Excel не найден. Загрузите файл вручную.', 404)
    return import_excel(conn, config.CASE_FILE.read_bytes(), config.CASE_FILE.name, 'case', who)


@app.post('/api/imports/excel')
def upload(file: UploadFile = File(...), conn=Depends(db), who=Depends(actor)):
    content = file.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise DomainError('file_too_large', 'Максимальный размер файла — 10 МБ.', 413)
    return import_excel(conn, content, (file.filename or 'upload.xlsx').split('/')[-1].split('\\')[-1], 'upload', who)


@app.post('/api/imports/demo')
def demo(conn=Depends(db), who=Depends(actor)):
    if not conn.execute('SELECT 1 FROM equipment').fetchone():
        raise DomainError('import_required', 'Сначала импортируйте Excel кейса: демо использует его справочники.')
    messages = json.loads((config.ROOT / 'evaluation' / 'demo_messages.json').read_text())
    created = 0
    with transaction(conn):
        for i, message in enumerate(messages):
            _, added = repository.create_message(conn, **message, source='demo', source_ref=f'demo_messages.json:{i + 1}',
                         external_id=f'ДЕМО-{i+1:02d}', external_key=f'demo:{i+1}', analysis=extract(message['text'], message['sender'], use_llm=False), actor=who)
            created += int(added)
    return {'created': created, 'skipped': len(messages) - created, 'source': 'demo'}


if config.FRONTEND_DIST.exists():
    app.mount('/', StaticFiles(directory=config.FRONTEND_DIST, html=True), name='frontend')
