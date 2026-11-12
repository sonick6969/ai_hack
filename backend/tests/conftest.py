import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATABASE_PATH', tmp_path / 'test.sqlite3')
    monkeypatch.setenv('LLM_ENABLED', 'false')
    with TestClient(app) as client:
        yield client


@pytest.fixture
def loaded(client):
    result = client.post('/api/imports/case')
    assert result.status_code == 200
    assert result.json()['status'] == 'success'
    return client


def create(client, sender='Кафе «Кедр», администратор', text='На машине 205 вода появляется справа после приготовления.', at='2026-11-16T12:00:00+03:00'):
    response = client.post('/api/messages', json={'sender': sender, 'text': text, 'received_at': at})
    assert response.status_code == 201, response.text
    return response.json()['ticket']


def update(client, ticket, **data):
    response = client.patch(f'/api/tickets/{ticket["id"]}', json={'revision': ticket['revision'], **data})
    assert response.status_code == 200, response.text
    return response.json()


def confirm_diagnostic(client, ticket):
    answers = {'leak_location': 'справа', 'leak_timing': 'после приготовления', 'onset': 'с утра',
               'after_work': 'работ не было', 'error_code': 'E07', 'noise_context': 'при приготовлении, повторяется',
               'steam_context': 'слабый пар из крана', 'general_context': 'Наблюдается слабая подача воды при приготовлении'}
    return update(client, ticket, equipment_confirmed=True, address_confirmed=True,
                  symptom=ticket['messages'][0]['text'], symptom_confirmed=True, answers=answers,
                  purpose='diagnostic', purpose_note='Провести осмотр и диагностику; без деталей, ремонт не обещан.',
                  plan_confirmed=True, duplicate_resolution='Новая независимая проблема, диспетчер проверил сообщения.')
