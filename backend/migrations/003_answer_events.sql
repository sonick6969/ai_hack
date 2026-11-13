-- Additive migration. Original JSON answers, messages, inventory and reserves stay intact.
CREATE TABLE answer_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 ticket_id INTEGER NOT NULL REFERENCES tickets(id),
 question_key TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('unanswered','unknown','answered')),
 text TEXT NOT NULL,
 source TEXT NOT NULL,
 message_id INTEGER REFERENCES messages(id),
 actor TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX answer_events_ticket ON answer_events(ticket_id, id);
