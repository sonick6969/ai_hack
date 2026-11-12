import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def connect(path=None):
    path = Path(path or config.DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    # One connection per request. FastAPI may move dependency/endpoint work between worker threads.
    conn = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=10000')
    return conn


def migrate(path=None):
    with connect(path) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        for file in sorted((config.ROOT / 'backend' / 'migrations').glob('*.sql')):
            if not conn.execute('SELECT 1 FROM schema_migrations WHERE version=?', (file.name,)).fetchone():
                # executescript manages its own transaction; DDL and migration marker commit together.
                safe_name = file.name.replace("'", "''")
                conn.executescript('BEGIN IMMEDIATE;\n' + file.read_text() +
                                   f"\nINSERT INTO schema_migrations VALUES ('{safe_name}', '{now()}');\nCOMMIT;")


@contextmanager
def transaction(conn):
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def audit(conn, action, details, ticket_id=None, actor='Диспетчер'):
    conn.execute('INSERT INTO audit(ticket_id,action,actor,details,created_at) VALUES(?,?,?,?,?)',
                 (ticket_id, action, actor, encode(details), now()))


class DomainError(Exception):
    def __init__(self, code, message, status=409, details=None):
        self.code, self.message, self.status, self.details = code, message, status, details


def require_ticket(conn, ticket_id, revision=None):
    row = conn.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
    if not row:
        raise DomainError('not_found', 'Заявка не найдена.', 404)
    if row['state'] == 'merged':
        raise DomainError('merged', 'Заявка объединена. Откройте основную заявку.', details={'ticket_id': row['merged_into']})
    if revision is not None and revision != row['revision']:
        raise DomainError('stale_revision', 'Заявка изменена в другом окне. Обновите карточку и повторите действие.')
    return dict(row)


def touch(conn, ticket_id, data=None):
    row = require_ticket(conn, ticket_id)
    data = data if data is not None else json.loads(row['data'])
    data.pop('approval', None)
    conn.execute('UPDATE tickets SET data=?, revision=revision+1, prepared_revision=NULL, prepared_at=NULL, updated_at=? WHERE id=?',
                 (encode(data), now(), ticket_id))
