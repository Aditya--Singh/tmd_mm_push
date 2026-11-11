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

start backend bash -c "cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
sleep 2

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
