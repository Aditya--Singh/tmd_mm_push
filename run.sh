#!/usr/bin/env bash
# Starts the whole platform in four terminals: the backend of the hub, Peer
# Benchmarking, the news dashboard and the landing page.
#
#     ./run.sh
#
# Stop everything with Ctrl+C in each terminal.
#
# On Windows use run.ps1 in PowerShell instead.
set -euo pipefail
cd "$(dirname "$0")"

BACKEND_PID=""
BENCH_PID=""
NEWS_PID=""
LANDING_PID=""

cleanup() {
  echo ""
  echo "Stopping the platform."
  for pid in "$LANDING_PID" "$NEWS_PID" "$BENCH_PID" "$BACKEND_PID"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

start() {  # start <name> <command...>
  local name="$1"; shift
  echo "Starting $name"
  "$@" &
  local pid=$!
  echo "$pid" > "/tmp/platform-$name.pid"
  case "$name" in
    backend)   BACKEND_PID="$pid" ;;
    benchmarking) BENCH_PID="$pid" ;;
    news)      NEWS_PID="$pid" ;;
    landing)   LANDING_PID="$pid" ;;
  esac
}

if [ ! -d backend/.venv ] || [ ! -d benchmarking/.venv ]; then
  echo "Run ./setup.sh first."
  exit 1
fi

# Wait for the backend to answer, so that a sign-in that cannot go through is
# never a mystery.
wait_for_the_backend() {
  local attempt
  for attempt in $(seq 1 30); do
    if curl -fsS --max-time 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
      echo "The backend is up."
      return 0
    fi
    sleep 1
  done
  return 1
}

start backend bash -c "cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
sleep 2

# The landing page cannot sign anybody in without the backend, so wait for it and
# say plainly when it does not come up.
if ! wait_for_the_backend; then
  echo ""
  echo "The backend of the hub did not start, so signing in will not work."
  echo "It is started by the line above; the reason is in that window."
  echo "The usual causes are a missing settings file (run ./setup.sh) or the"
  echo "port 8000 already being taken."
  exit 1
fi

start benchmarking bash -c "cd benchmarking && .venv/bin/python -m kpibench.main"
sleep 2

start news bash -c "cd frontend && npm run dev -- --host 127.0.0.1 --port 5173"
start landing bash -c "cd landing && npm run dev -- --host 127.0.0.1 --port 5174"

cat <<'DONE'

The platform is starting.

    Landing page hub    http://localhost:5174
    News dashboard      http://localhost:5173
    Peer Benchmarking   http://localhost:8077
    Backend and its API http://127.0.0.1:8000/docs

Sign in at http://localhost:5174 with admin / admin@tmd26

DONE

wait
