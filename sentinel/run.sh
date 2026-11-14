#!/usr/bin/env bash
# Local run without Docker.
#   ./run.sh          build the UI once and serve everything on http://localhost:8090 (PORT in .env)
#   ./run.sh dev      hot-reload: API on PORT, UI on http://localhost:5173
#   ./run.sh test     run the backend test-suite
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { cp .env.example .env; echo "Created .env from .env.example - edit it, then re-run."; exit 1; }

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r backend/requirements-dev.txt
  .venv/bin/python -m playwright install chromium   # headless browser that reads every Master Circular year
fi
PY="$PWD/.venv/bin/python"
PORT="$(grep -E '^PORT=' .env | cut -d= -f2 || true)"; PORT="${PORT:-8090}"

case "${1:-serve}" in
  test)
    cd backend && "$PY" -m pytest -q ;;
  dev)
    (cd frontend && [ -d node_modules ] || npm ci) >/dev/null
    (cd backend && "$PY" -m uvicorn app.main:app --reload --port "$PORT") &
    API=$!
    trap 'kill $API' EXIT
    cd frontend && npm run dev ;;
  *)
    (cd frontend && { [ -d node_modules ] || npm ci; } && npm run build)
    echo "Open http://localhost:$PORT"
    cd backend && exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1 ;;
esac
