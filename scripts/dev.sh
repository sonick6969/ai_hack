#!/usr/bin/env bash
set -euo pipefail
pilot_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$pilot_root"
if [[ ! -x .venv/bin/python || ! -f frontend/node_modules/vite/bin/vite.js ]]; then
  echo 'Сначала установите зависимости по README.md.' >&2
  exit 1
fi
backend_pid=''
frontend_pid=''
cleanup() {
  [[ -z "$backend_pid" ]] || kill "$backend_pid" 2>/dev/null || true
  [[ -z "$frontend_pid" ]] || kill "$frontend_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend/app &
backend_pid=$!
(cd frontend && exec node node_modules/vite/bin/vite.js --host 127.0.0.1) &
frontend_pid=$!
wait -n "$backend_pid" "$frontend_pid"
