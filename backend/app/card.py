import html

from .db import DomainError
from .repository import detail

PURPOSES = {'diagnostic': 'Диагностика', 'repair': 'Ремонт по согласованному плану', 'maintenance': 'Обслуживание по согласованному плану'}


def engineer_card(conn, ticket_id):
    ticket = detail(conn, ticket_id)
    eq, data = ticket['equipment'], ticket['data']
    ready = ticket['readiness']['ready']
    confirmed = []
    if eq and data.get('equipment_confirmed'):
        confirmed.append('Машина: ' + eq['model'] + ', серийный № ' + eq['serial'])
    if eq and data.get('address_confirmed'):
        confirmed.append('Адрес подтверждён: ' + eq['address'])
    for q in ticket['readiness']['questions']:
        if q['resolved']:
            confirmed.append(q['question'] + ' — ' + q['answer'])
    uncertainties = ['Причина неисправности определяется инженером на осмотре.']
    uncertainties.append('Назначение инженера, время выезда и физическое получение деталей в приложении не проверяются.')
    uncertainties += [u['question'] for u in ticket['analysis'].get('uncertainties', [])]
    uncertainties += [q['question'] + ' — ответ пока неизвестен' for q in ticket['readiness']['questions'] if q['status'] == 'unknown']
    uncertainties += ticket['readiness']['warranty']['uncertainties']
    uncertainties += [c['code'] + ': ' + c['meaning'] for c in ticket['error_codes'] if not c.get('known')]
    if data.get('uncertainties'):
        uncertainties.append(data['uncertainties'])
    if not ticket['plans']:
        uncertainties.append('Детали не запланированы. Диагностика не гарантирует устранение неисправности за один визит.')
    return {'label': ticket['label'], 'revision': ticket['revision'], 'ready': ready,
            'prepared_at': ticket['prepared_at'], 'equipment': eq,
            'symptom': data.get('symptom', ''), 'symptom_confirmed': bool(data.get('symptom_confirmed')),
            'confirmed': confirmed,
            'history': {'date': eq['last_visit'] if eq else None, 'text': eq['history'] if eq and eq['history'] else 'История визитов не предоставлена.',
                        'source_ref': eq['source_ref'] if eq else None},
            'parts': ticket['plans'], 'purpose': PURPOSES.get(data.get('purpose'), 'Цель не согласована'),
            'purpose_note': data.get('purpose_note', ''), 'visit_date': data.get('visit_date'),
            'uncertainties': uncertainties, 'blockers': ticket['readiness']['blockers'],
            'warranty': ticket['readiness']['warranty'], 'approval': data.get('approval'),
            'messages': ticket['messages'], 'error_codes': ticket['error_codes']}


def card_html(card):
    e = lambda value: html.escape(str(value or '—'))
    eq = card['equipment'] or {}
    facts = ''.join(f'<li>{e(f)}</li>' for f in card['confirmed']) or '<li>Подтверждений пока нет</li>'
    parts = ''.join(f'<tr><td>{e(p["sku"])} · {e(p["name"])}</td><td>{p["quantity"]}</td><td>{e(p["warehouse"])}</td><td>{"Подтверждён" if p["reserved_quantity"] == p["quantity"] else "Не подтверждён"}{"; перевоз: " + e(p["available_on"]) if p["transfer_required"] else ""}</td></tr>' for p in card['parts'])
    unknown = ''.join(f'<li>{e(u)}</li>' for u in card['uncertainties'])
    blockers = ''.join(f'<li>{e(b["next_action"])}: {e(b["reason"])}</li>' for b in card['blockers'])
    source = ''.join(f'<p><strong>{e(m["external_id"] or m["sender"])}</strong> · {e(m["received_at"])} · {e(m["source_ref"])}<br>{e(m["text"])}</p>' for m in card['messages'])
    return f'''<!doctype html><html lang="ru"><meta charset="utf-8"><title>{e(card['label'])} — карточка инженера</title>
<style>@page{{size:A4;margin:14mm}}body{{font:14px/1.55 system-ui,sans-serif;color:#171717;background:white;max-width:840px;margin:32px auto;padding:0 24px}}h1{{font-size:26px;margin:0}}h2{{font-size:17px;margin:22px 0 8px;border-bottom:1px solid #777;padding-bottom:5px}}.stamp{{padding:10px 14px;background:#e3eddb;border:1px solid #5d7356;margin:16px 0;font-weight:700}}.draft{{background:#fbf0da;border-color:#9b7a40}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:8px;border:1px solid #aaa}}.meta{{color:#555}}p{{white-space:pre-wrap;overflow-wrap:anywhere}}.toolbar{{display:flex;gap:10px;margin:0 0 28px}}button,a{{font:inherit;padding:9px 16px;border:1px solid #777;border-radius:2px;background:white;cursor:pointer;color:inherit;text-decoration:none}}button:focus-visible,a:focus-visible{{outline:3px solid #194f9b;outline-offset:3px}}@media print{{body{{margin:0;padding:0;max-width:none;font-size:10.5px;color:black}}.toolbar{{display:none}}.stamp,.draft{{background:white;color:black;border-color:black}}.meta{{color:#333}}h1{{font-size:22px}}h2{{font-size:14px;break-after:avoid}}tr,p,li{{break-inside:avoid}}}}</style>
<div class="toolbar"><button onclick="window.print()">Печать / сохранить PDF</button><a href="/">Вернуться в очередь</a></div>
<div class="meta">КОФЕСЕРВИС РЕГИОН · ПОДГОТОВКА ВЫЕЗДА</div><h1>Карточка инженера · {e(card['label'])}</h1>
<div class="stamp {'draft' if not card['ready'] else ''}">{'КАРТОЧКА ГОТОВА К ПЕРЕДАЧЕ' if card['ready'] else 'ЧЕРНОВИК — КАРТОЧКА НЕ ПОДГОТОВЛЕНА'} · версия {card['revision']}</div>
<p><strong>{e(eq.get('client'))}</strong><br>{e(eq.get('address'))}<br>Модель {e(eq.get('model'))} · серийный № {e(eq.get('serial'))} · код {e(eq.get('id'))}</p>
<p>Дата визита: {e(card['visit_date'])} · Подготовлено: {e(card['prepared_at'])}</p>
<h2>Симптом со слов клиента{' · подтверждён диспетчером' if card['symptom_confirmed'] else ' · требует подтверждения'}</h2><p>{e(card['symptom'])}</p>
<h2>Подтверждённые сведения</h2><ul>{facts}</ul>
<h2>Доступная история</h2><p>{e(card['history']['date'])} · {e(card['history']['source_ref'])}<br>{e(card['history']['text'])}</p>
<h2>Детали и склад получения</h2>{'<table><tr><th>Деталь</th><th>Кол-во</th><th>Склад</th><th>Резерв / перевоз</th></tr>' + parts + '</table>' if parts else '<p>Детали не запланированы.</p>'}
<h2>Цель визита</h2><p><strong>{e(card['purpose'])}</strong><br>{e(card['purpose_note'])}</p>
<h2>Согласование</h2><p>{e(card['warranty']['reason'])}<br>{e(card['approval']['name'] + ': ' + card['approval']['note']) if card['approval'] else 'Отдельное согласование не записано'}</p>
<h2>Оставшиеся неопределённости</h2><ul>{unknown}</ul>
{'<h2>Препятствия к выезду</h2><ul>' + blockers + '</ul>' if blockers else ''}
<h2>Исходные сообщения и происхождение</h2>{source}
<p class="meta">Сведения из реестра и слова клиента не являются диагнозом. Карточка отражает состояние заявки на момент открытия; перед выездом проверьте актуальную версию.</p></html>'''
