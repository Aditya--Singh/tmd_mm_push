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
ROOT="$(pwd)"
cd "$(dirname "$0")"

# How long the backend is given to answer before it is called a failure. A first
# start on a new machine is slow: every file of the environment is read for the
# first time, and the antivirus reads them as well.
BACKEND_WAIT_SECONDS=90

BACKEND_PID=""
BENCH_PID=""
SENTINEL_PID=""
NEWS_PID=""
LANDING_PID=""

# The port the backend of the hub listens on. It is read from backend/.env, so
# that a machine where the port is already taken can use another one.
BACKEND_PORT="$(grep -E '^PORT=' backend/.env 2>/dev/null | head -1 | cut -d= -f2 | tr -d '[:space:]')"
BACKEND_PORT="${BACKEND_PORT:-8000}"

cleanup() {
  echo ""
  echo "Stopping the platform."
  for pid in "$LANDING_PID" "$NEWS_PID" "$SENTINEL_PID" "$BENCH_PID" "$BACKEND_PID"; do
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
  case "$name" in
    backend)   BACKEND_PID="$pid" ;;
    benchmarking) BENCH_PID="$pid" ;;
    sentinel)  SENTINEL_PID="$pid" ;;
    news)      NEWS_PID="$pid" ;;
    landing)   LANDING_PID="$pid" ;;
  esac
}

if [ ! -d backend/.venv ] || [ ! -d benchmarking/.venv ] || [ ! -d sentinel/.venv ]; then
  echo "Run ./setup.sh first."
  exit 1
fi

# Whether something is listening on a port.
port_is_open() {  # port_is_open <port>
  (echo > "/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1
}

# Everything the backend says is kept, and shown here if it does not come up.
LOG_DIR="$ROOT/backend/logs"
mkdir -p "$LOG_DIR"
BACKEND_LOG="$LOG_DIR/backend.log"
rm -f "$BACKEND_LOG"

# Wait for the backend to answer, so that a sign-in that cannot go through is
# never a mystery.
wait_for_the_backend() {
  local attempt
  for attempt in $(seq 1 "$BACKEND_WAIT_SECONDS"); do
    if curl -fsS --max-time 2 "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
      echo "The backend is up."
      return 0
    fi
    # Stop waiting as soon as the backend is gone: it will not come back.
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      return 1
    fi
    sleep 1
  done
  return 1
}

start backend bash -c "cd '$ROOT/backend' && exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $BACKEND_PORT > '$BACKEND_LOG' 2>&1"
sleep 2

# The landing page cannot sign anybody in without the backend, so wait for it and
# say plainly when it does not come up.
if ! wait_for_the_backend; then
  echo ""
  echo "The backend of the hub did not start, so signing in will not work."
  echo ""

  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "It stopped with an error. This is what it said:"
  elif port_is_open "$BACKEND_PORT"; then
    echo "Something else is on port $BACKEND_PORT, so the backend cannot start."
    echo "To see what it is:"
    echo "    sudo ss -tlnp | grep :$BACKEND_PORT"
    echo "Stop it, or give the backend another port in backend/.env (PORT=...)"
    echo "and run 'python scripts/make_env.py' again."
  else
    echo "It is still starting after ${BACKEND_WAIT_SECONDS} seconds, so it is slow on this machine."
    echo "Start it by hand to watch it go:"
    echo "    cd backend"
    echo "    .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $BACKEND_PORT"
  fi

  echo ""

  if [ -f "$BACKEND_LOG" ]; then
    tail -n 25 "$BACKEND_LOG" | sed 's/^/    /'
  fi

  echo ""
  echo "The whole record is in backend/logs/backend.log"
  echo "To have the whole platform checked: python scripts/doctor.py"
  exit 1
fi

start benchmarking bash -c "cd benchmarking && .venv/bin/python -m kpibench.main"
sleep 2

# The Data Summarizer serves its own interface from the same address as its API.
start sentinel bash -c "cd '$ROOT/sentinel/backend' && exec ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090"
sleep 2

start news bash -c "cd frontend && npm run dev -- --host 127.0.0.1 --port 5173"
start landing bash -c "cd landing && npm run dev -- --host 127.0.0.1 --port 5174"

cat <<'DONE'

The platform is starting.

    Landing page hub    http://localhost:5174
    News dashboard      http://localhost:5173
    Peer Benchmarking   http://localhost:8077
    Data Summarizer     http://localhost:8090
    Backend and its API http://127.0.0.1:$BACKEND_PORT/docs

Sign in at http://localhost:5174 with admin / admin@tmd26

DONE

wait
