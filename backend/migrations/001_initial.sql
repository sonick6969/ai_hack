CREATE TABLE imports (
 id INTEGER PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
 source TEXT NOT NULL, created_at TEXT NOT NULL, report TEXT NOT NULL
);
CREATE TABLE equipment (
 id TEXT PRIMARY KEY, client TEXT NOT NULL, address TEXT NOT NULL,
 model TEXT NOT NULL, serial TEXT NOT NULL UNIQUE, installed_at TEXT NOT NULL,
 last_visit TEXT, history TEXT NOT NULL DEFAULT '', source_ref TEXT NOT NULL,
 source TEXT NOT NULL
);
CREATE TABLE parts (
 sku TEXT PRIMARY KEY, name TEXT NOT NULL, models TEXT NOT NULL, source_ref TEXT NOT NULL
);
CREATE TABLE stock (
 sku TEXT NOT NULL REFERENCES parts(sku), warehouse TEXT NOT NULL,
 on_hand INTEGER NOT NULL CHECK(on_hand >= 0),
 external_reserved INTEGER NOT NULL CHECK(external_reserved >= 0 AND external_reserved <= on_hand),
 PRIMARY KEY(sku, warehouse)
);
CREATE TABLE rules (
 code TEXT PRIMARY KEY, topic TEXT NOT NULL, text TEXT NOT NULL, source_ref TEXT NOT NULL
);
CREATE TABLE tickets (
 id INTEGER PRIMARY KEY AUTOINCREMENT, equipment_id TEXT REFERENCES equipment(id),
 state TEXT NOT NULL DEFAULT 'open' CHECK(state IN ('open','manager','merged','closed')),
 data TEXT NOT NULL DEFAULT '{}', revision INTEGER NOT NULL DEFAULT 1,
 prepared_revision INTEGER, prepared_at TEXT, merged_into INTEGER REFERENCES tickets(id),
 source TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT, external_key TEXT UNIQUE, external_id TEXT,
 ticket_id INTEGER NOT NULL REFERENCES tickets(id), import_id INTEGER REFERENCES imports(id),
 sender TEXT NOT NULL, channel TEXT NOT NULL, text TEXT NOT NULL,
 received_at TEXT NOT NULL, analysis TEXT NOT NULL, source_ref TEXT NOT NULL,
 source TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE part_plans (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
 sku TEXT NOT NULL REFERENCES parts(sku), warehouse TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity > 0), transfer_confirmed INTEGER NOT NULL DEFAULT 0,
 available_on TEXT, transfer_note TEXT NOT NULL DEFAULT '',
 UNIQUE(ticket_id, sku, warehouse),
 FOREIGN KEY(sku, warehouse) REFERENCES stock(sku, warehouse)
);
CREATE TABLE reservations (
 plan_id INTEGER PRIMARY KEY REFERENCES part_plans(id) ON DELETE CASCADE,
 quantity INTEGER NOT NULL CHECK(quantity > 0), created_at TEXT NOT NULL
);
CREATE TABLE audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER REFERENCES tickets(id),
 action TEXT NOT NULL, actor TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX messages_ticket ON messages(ticket_id);
CREATE INDEX plans_ticket ON part_plans(ticket_id);
CREATE INDEX audit_ticket ON audit(ticket_id, id);
