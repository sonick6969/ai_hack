#!/usr/bin/env bash
# Isolated database; never resets the user's pilot database.
set -euo pipefail
pilot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$pilot_root"
mkdir -p artifacts
npm --prefix frontend run build
qa_directory="$(mktemp -d "$pilot_root/artifacts/browser-XXXXXX")"
DATABASE_PATH="$qa_directory/pilot.sqlite3" LLM_ENABLED=false .venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8011 >"$qa_directory/backend.log" 2>&1 &
qa_backend_pid=$!
trap 'kill "$qa_backend_pid" 2>/dev/null || true' EXIT INT TERM
for attempt in {1..50}; do
  if ! kill -0 "$qa_backend_pid" 2>/dev/null; then
    cat "$qa_directory/backend.log" >&2
    exit 1
  fi
  if curl --noproxy '*' -fsS http://127.0.0.1:8011/api/health >/dev/null 2>&1; then break; fi
  sleep 0.2
done
echo "Изолированная база и лог: $qa_directory"
E2E_BASE_URL=http://127.0.0.1:8011 npm --prefix frontend run test:e2e
