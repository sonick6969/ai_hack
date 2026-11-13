from backend.app import config
from backend.app.db import connect, encode, migrate, now
from backend.app.repository import detail


def test_additive_migration_preserves_legacy_messages_answers_stock_and_reserves(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    with connect(path) as conn:
        conn.executescript((config.ROOT / 'backend/migrations/001_initial.sql').read_text())
        conn.execute('CREATE TABLE schema_migrations(version TEXT PRIMARY KEY,applied_at TEXT NOT NULL)')
        conn.execute('INSERT INTO schema_migrations VALUES(?,?)',('001_initial.sql',now()))
        text = 'На машине 205 вода появляется справа после приготовления.'
        old_analysis = {'models':[],'serials':['205'],'codes':[],'symptoms':['leak'],'facts':{},'unsafe_request':False,'evidence':[],
                        'engine':'local+llm','llm_status':'ok'}
        data = {'answers':{'leak_location':' ПОКА НЕ ЗНАЮ!!! ','leak_timing':'после приготовления'},'symptom':text,
                'symptom_confirmed':True,'equipment_confirmed':True,'address_confirmed':True,
                'purpose':'diagnostic','purpose_note':'Проверка и диагностика на месте.','plan_confirmed':True}
        conn.execute('INSERT INTO equipment VALUES(?,?,?,?,?,?,?,?,?,?)',('EQ02','Кафе «Кедр»','Москва, ул. Лесная, 12','C200','205','2025-06-02',None,'','Оборудование!A5:H5','case'))
        conn.execute('INSERT INTO tickets(id,equipment_id,data,prepared_revision,source,created_at,updated_at) VALUES(1,?,?,1,?,?,?)',('EQ02',encode(data),'case',now(),now()))
        conn.execute('INSERT INTO messages(ticket_id,sender,channel,text,received_at,analysis,source_ref,source,created_at) VALUES(1,?,?,?,?,?,?,?,?)',
                     ('Кафе «Кедр»','Звонок',text,'2026-11-16T12:00:00+03:00',encode(old_analysis),'Заявки!A9:E9','case',now()))
        conn.execute('INSERT INTO parts VALUES(?,?,?,?)',('F010','Фильтр-картридж',encode(['C200']),'Запчасти!A12:G12'))
        conn.execute('INSERT INTO stock VALUES(?,?,?,?)',('F010','Москва',14,6))
        conn.execute('INSERT INTO part_plans(id,ticket_id,sku,warehouse,quantity) VALUES(1,1,?,?,1)',('F010','Москва'))
        conn.execute('INSERT INTO reservations VALUES(1,1,?)',(now(),))
    migrate(path); migrate(path)
    with connect(path) as conn:
        ticket = detail(conn,1)
        assert ticket['messages'][0]['text'] == text
        assert conn.execute('SELECT analysis FROM messages').fetchone()[0] == encode(old_analysis)
        assert ticket['data']['answers']['leak_location'] == ' ПОКА НЕ ЗНАЮ!!! '
        assert ticket['readiness']['questions'][0]['status'] == 'unknown'
        assert not ticket['readiness']['ready']
        assert ticket['plans'][0]['reserved_quantity'] == 1
        assert conn.execute('SELECT on_hand,external_reserved FROM stock').fetchone()[:] == (14,6)
        assert ticket['messages'][0]['analysis']['llm_status'] == 'legacy_reparsed'
