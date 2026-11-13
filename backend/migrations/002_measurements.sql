CREATE TABLE measurement_runs (
 id TEXT PRIMARY KEY,
 participant TEXT NOT NULL,
 participant_kind TEXT NOT NULL CHECK(participant_kind IN ('dispatcher','tester','automated')),
 method TEXT NOT NULL CHECK(method IN ('manual','pilot')),
 context TEXT NOT NULL CHECK(context IN ('controlled','field','practice')),
 comparison_key TEXT NOT NULL DEFAULT '',
 process_description TEXT NOT NULL,
 ticket_id INTEGER REFERENCES tickets(id),
 client_id TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('working','waiting','paused','finished','abandoned')),
 wait_reason TEXT NOT NULL DEFAULT '',
 started_at TEXT NOT NULL,
 accounted_at TEXT NOT NULL,
 last_seen_at TEXT NOT NULL,
 finished_at TEXT,
 active_ms INTEGER NOT NULL DEFAULT 0 CHECK(active_ms >= 0),
 waiting_ms INTEGER NOT NULL DEFAULT 0 CHECK(waiting_ms >= 0),
 paused_ms INTEGER NOT NULL DEFAULT 0 CHECK(paused_ms >= 0),
 unknown_ms INTEGER NOT NULL DEFAULT 0 CHECK(unknown_ms >= 0),
 review_wait_ms INTEGER NOT NULL DEFAULT 0 CHECK(review_wait_ms >= 0),
 heartbeat_sequence INTEGER NOT NULL DEFAULT 0,
 activations INTEGER NOT NULL DEFAULT 0 CHECK(activations >= 0),
 revision INTEGER NOT NULL DEFAULT 1,
 rework_count INTEGER NOT NULL DEFAULT 0,
 outcome TEXT,
 note TEXT NOT NULL DEFAULT '',
 artifact TEXT,
 artifact_hash TEXT,
 submitted_ticket_revision INTEGER
);
CREATE UNIQUE INDEX measurement_one_open_per_person
 ON measurement_runs(participant) WHERE state IN ('working','waiting','paused');
CREATE INDEX measurement_ticket ON measurement_runs(ticket_id);
CREATE TABLE measurement_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 run_id TEXT NOT NULL REFERENCES measurement_runs(id),
 type TEXT NOT NULL,
 details TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE measurement_reviews (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 run_id TEXT NOT NULL REFERENCES measurement_runs(id),
 reviewer TEXT NOT NULL,
 reviewer_kind TEXT NOT NULL CHECK(reviewer_kind IN ('engineer','test_reviewer')),
 artifact_hash TEXT NOT NULL,
 checks TEXT NOT NULL,
 critical_errors TEXT NOT NULL,
 accepted INTEGER NOT NULL CHECK(accepted IN (0,1)),
 note TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE action_requests (
 request_id TEXT PRIMARY KEY,
 ticket_id INTEGER NOT NULL REFERENCES tickets(id),
 operation TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 created_at TEXT NOT NULL
);
