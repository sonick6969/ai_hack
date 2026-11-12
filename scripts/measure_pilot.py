"""Policy checks on deliberately unsafe requests, not real service outcomes."""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.app import config
from backend.app.main import app


def main():
    results = []
    with tempfile.TemporaryDirectory() as tmp, patch.object(config, 'DATABASE_PATH', Path(tmp) / 'metrics.sqlite3'), patch.dict(os.environ, {'LLM_ENABLED': 'false'}), TestClient(app) as client:
        assert client.post('/api/imports/case').json()['status'] == 'success'

        def create(text='На машине 205 течь справа после приготовления.', sender='Кафе «Кедр»'):
            r = client.post('/api/messages', json={'sender': sender, 'text': text, 'received_at': '2026-11-16T12:00:00+03:00'})
            assert r.status_code == 201, r.text
            return r.json()['ticket']

        def update(t, **data):
            r = client.patch(f'/api/tickets/{t["id"]}', json={'revision': t['revision'], **data})
            assert r.status_code == 200, r.text
            return r.json()

        def confirmed(t):
            return update(t, equipment_confirmed=True, address_confirmed=True,
                          symptom=t['messages'][0]['text'], symptom_confirmed=True,
                          answers={'leak_location': 'справа', 'leak_timing': 'после приготовления', 'onset': 'с утра',
                                   'after_work': 'работ не было', 'error_code': 'E11', 'general_context': 'Наблюдаемый симптом записан',
                                   'noise_context': 'при приготовлении', 'steam_context': 'слабый пар из крана'},
                          purpose='diagnostic', purpose_note='Проверить симптом осмотром. Ремонт без диагностики не обещан.',
                          plan_confirmed=True, duplicate_resolution='Проверено: независимый тестовый случай, отдельная проблема.')

        def reject(label, t):
            r = client.post(f'/api/tickets/{t["id"]}/prepare', json={'revision': t['revision']})
            failed = r.status_code == 200 or t['readiness']['ready']
            results.append({'case': label, 'false_ready': failed, 'http_status': r.status_code,
                            'blockers': [b['key'] for b in t['readiness']['blockers']]})

        reject('Две машины клиента, номер неизвестен', confirmed(create('Одна из двух машин течёт снизу.')))
        reject('Машина вне реестра', confirmed(create('Машина 270 течёт постоянно.', 'Гостиница «Север»')))
        t = confirmed(create('Номер 205, C300, течь справа.'))
        t = update(t, equipment_id='EQ02', equipment_confirmed=True, address_confirmed=True)
        reject('Противоречие модели и номера не разрешено', t)
        reject('Симптом не подтверждён', update(confirmed(create()), symptom_confirmed=False))
        reject('Нет времени появления течи', update(confirmed(create()), answers={'leak_timing': ''}))
        reject('Вместо кода ошибки записано «не знаю»', update(confirmed(create('На машине 108 ошибка.', 'Гостиница «Берег»')), answers={'error_code': 'не знаю'}))
        reject('Цель выезда не согласована', update(confirmed(create()), plan_confirmed=False))
        reject('Нет согласования гарантийного случая', confirmed(create('Машина 305 капает из-под группы после приготовления.', 'Кафе «Маяк»')))
        t = confirmed(create())
        r = client.post(f'/api/tickets/{t["id"]}/parts', json={'revision': t['revision'], 'sku': 'G200', 'warehouse': 'Москва'})
        assert r.status_code == 201
        t = r.json()
        reserve = client.post(f'/api/tickets/{t["id"]}/reserve', json={'revision': t['revision']})
        assert reserve.status_code == 409
        reject('Свободный остаток равен нулю', t)
        t = confirmed(create('На машине 211 код E11.', 'Кафе «Парк»'))
        t = client.post(f'/api/tickets/{t["id"]}/parts', json={'revision': t['revision'], 'sku': 'L200', 'warehouse': 'Тула'}).json()
        t = client.post(f'/api/tickets/{t["id"]}/reserve', json={'revision': t['revision']}).json()
        reject('Перевоз из другого города не согласован', t)
        t = confirmed(create())
        r = client.post(f'/api/tickets/{t["id"]}/parts', json={'revision': t['revision'], 'sku': 'G100', 'warehouse': 'Москва'})
        assert r.status_code == 409
        reject('Несовместимая деталь отклонена, план ремонта пуст', update(t, purpose='repair'))

        positive = confirmed(create())
        before = client.post(f'/api/tickets/{positive["id"]}/prepare', json={'revision': positive['revision']})
        assert before.status_code == 200
        positive = before.json()
        card = client.get(f'/api/tickets/{positive["id"]}/card').json()
        completeness = {
            'machine': bool(card['equipment'] and positive['data']['equipment_confirmed']),
            'address': bool(card['equipment']['address'] and positive['data']['address_confirmed']),
            'symptom': bool(card['symptom'] and card['symptom_confirmed']),
            'confirmed_facts': len(card['confirmed']) >= 3,
            'available_history_or_explicit_absence': bool(card['history']['text']),
            'parts_and_warehouse_or_explicit_diagnostic_without_parts': bool(card['parts']) or bool(positive['data']['purpose'] == 'diagnostic' and positive['data']['plan_confirmed']),
            'purpose': bool(card['purpose_note']), 'uncertainties': bool(card['uncertainties']),
        }
        reject('Содержательное изменение после подготовки', update(positive, symptom_confirmed=False))
        t = confirmed(create())
        t = client.post(f'/api/tickets/{t["id"]}/prepare', json={'revision': t['revision']}).json()
        r = client.post(f'/api/tickets/{t["id"]}/messages?revision={t["revision"]}', json={'sender': 'Кафе «Кедр»', 'text': 'Уточнение по течи: теперь постоянно снизу.'})
        assert r.status_code == 201
        reject('Новое сообщение после подготовки', r.json())
    output = {'measured_at': datetime.now(timezone.utc).isoformat(), 'type': 'engineered_policy_scenarios_not_field_business_experiment',
              'negative_cases': len(results), 'false_ready': sum(r['false_ready'] for r in results), 'cases': results,
              'positive_card_sections': completeness, 'complete_sections': sum(completeness.values()), 'section_denominator': len(completeness),
              'human_preparation_time': None, 'real_repeat_visits_observed': None}
    (ROOT / 'evaluation' / 'pilot_metrics.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(output, ensure_ascii=False, indent=2))
    assert output['false_ready'] == 0 and output['complete_sections'] == 8


if __name__ == '__main__':
    main()
