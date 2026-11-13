import io

from openpyxl import load_workbook

from backend.app import config
from backend.app.config import CASE_FILE
from backend.app.db import connect, migrate


def changed_file(cell, value, sheet='Запчасти'):
    wb = load_workbook(CASE_FILE)
    wb[sheet][cell] = value
    buf = io.BytesIO(); wb.save(buf); wb.close()
    return buf.getvalue()


def test_official_excel_counts_sources_and_idempotence(client):
    report = client.post('/api/imports/case').json()
    assert report['counts'] == {'Заявки': 23, 'Оборудование': 12, 'Запчасти': 10, 'Правила': 10}
    assert report['created'] == {'equipment': 12, 'parts': 10, 'rules': 10, 'messages': 23}
    assert not report['errors']
    assert report['warnings'][0]['cell'] == 'Оборудование!A15:H15'
    assert client.get('/api/tickets/1').json()['messages'][0]['source_ref'] == 'Заявки!A4:E4'
    again = client.post('/api/imports/case').json()
    assert again['duplicate_file']
    assert again['created']['messages'] == 0 and again['skipped'] == 55
    assert client.get('/api/summary').json()['messages'] == 23
    assert len(client.get('/api/imports').json()) == 1


def test_invalid_row_rolls_back_whole_import(client):
    result = client.post('/api/imports/excel', files={'file': ('invalid.xlsx', changed_file('E4', 100))}).json()
    assert result['status'] == 'error'
    assert any('резерв' in e['message'].lower() for e in result['errors'])
    assert client.get('/api/summary').json()['equipment'] == 0
    assert client.get('/api/summary').json()['messages'] == 0
    assert len(client.get('/api/imports').json()) == 1


def test_formula_rejected(client):
    result = client.post('/api/imports/excel', files={'file': ('formula.xlsx', changed_file('D4', '=1+2'))}).json()
    assert result['status'] == 'error'
    assert any('Формулы' in e['message'] for e in result['errors'])
    assert client.get('/api/equipment').json() == []


def test_reference_changes_do_not_overwrite_stock_or_registry(loaded):
    result = loaded.post('/api/imports/excel', files={'file': ('changed.xlsx', changed_file('D4', 100))}).json()
    assert result['status'] == 'error'
    stock = loaded.get('/api/inventory').json()
    assert next(r['on_hand'] for r in stock if r['sku'] == 'G100' and r['warehouse'] == 'Москва') == 3
    assert loaded.get('/api/summary').json()['messages'] == 23


def test_corrupt_file_and_missing_sheets(client):
    result = client.post('/api/imports/excel', files={'file': ('broken.xlsx', b'not an excel')}).json()
    assert result['status'] == 'error'
    assert client.post('/api/imports/excel', files={'file': ('data.csv', b'a,b')}).json()['status'] == 'error'
    wb = load_workbook(CASE_FILE); del wb['Правила']
    buf = io.BytesIO(); wb.save(buf); wb.close()
    result = client.post('/api/imports/excel', files={'file': ('missing.xlsx', buf.getvalue())}).json()
    assert any(e['cell'] == 'Правила' for e in result['errors'])


def test_demo_is_separate_and_idempotent(loaded):
    assert loaded.post('/api/imports/demo').json()['created'] == 3
    assert loaded.post('/api/imports/demo').json()['created'] == 0
    rows = loaded.get('/api/tickets?source=demo').json()
    assert len(rows) == 3 and all(r['source'] == 'demo' for r in rows)
    assert loaded.get('/api/summary').json()['messages'] == 26


def test_migrations_are_repeatable_and_transactional(tmp_path):
    path = tmp_path / 'migration.sqlite3'
    migrate(path); migrate(path)
    with connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0] == len(list(config.ROOT.joinpath('backend/migrations').glob('*.sql')))
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
