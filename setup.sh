#!/usr/bin/env bash
# One-time setup for the whole platform: the backend of the hub, Peer
# Benchmarking, the news dashboard and the landing page.
#
# Safe to run again. Open a terminal in the repository folder and run:
#
#     ./setup.sh
#
# On Windows use setup.ps1 in PowerShell instead.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1;31m==\033[1m %s\n' "$1"; }
note() { printf '   %s\n' "$1"; }

PY="${PYTHON:-python3}"

say "1/6  Checking what is installed"
"$PY" --version
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "   Python 3.10 or newer is needed. On Ubuntu: sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi
if ! command -v node >/dev/null; then
  echo "   Node.js 20 or newer is needed. See https://nodejs.org/"
  exit 1
fi
node --version
npm --version

say "2/6  The backend of the hub"
cd backend
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel >/dev/null 2>&1 || true
if ! python -m pip install -e .; then
  echo "   The packages could not be downloaded. Behind a proxy, set HTTPS_PROXY first."
  echo "   Behind a private mirror: PIP_INDEX_URL=https://pypi.org/simple ./setup.sh"
  exit 1
fi
deactivate
cd ..

say "3/6  Peer Benchmarking"
cd benchmarking
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel >/dev/null 2>&1 || true
if ! python -m pip install -r requirements.txt; then
  echo "   The packages could not be downloaded. Behind a proxy, set HTTPS_PROXY first."
  echo "   Behind a private mirror: PIP_INDEX_URL=https://pypi.org/simple ./setup.sh"
  exit 1
fi
deactivate
cd ..

say "4/6  The two web applications"
(cd frontend && npm install)
(cd landing && npm install)

say "5/6  The settings files"
"$PY" scripts/make_env.py

say "6/6  The demo accounts"
(cd backend && .venv/bin/python seed_users.py)

cat <<'DONE'

Everything is ready.

Start the platform with:

    ./run.sh

Check that everything is in place at any time:

    python scripts/doctor.py

Then open http://localhost:5174 and sign in with, for example:

    admin     / admin@tmd26        administrator in both applications
    analyst   / Pnb@12345          analyst, collects the figures
    approver  / Pnb@12345          approver, checks the figures
    gm        / Pnb@12345          general manager, reads them

DONE
