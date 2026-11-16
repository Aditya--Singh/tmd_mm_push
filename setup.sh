#!/usr/bin/env bash
# One-time setup for the whole platform: the backend of the hub, Peer
# Benchmarking, the Data Summarizer, the news dashboard and the landing page.
#
# Safe to run again. Open a terminal in the repository folder and run:
#
#     ./setup.sh
#
# On Windows use setup.ps1 in PowerShell instead.
#
# A step that fails does not stop the ones after it: the settings files and
# the accounts are written whatever else went wrong, and the problems are
# listed at the end.
set -uo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1;31m== %s\033[0m\n' "$1"; }
note() { printf '   %s\n' "$1"; }

PROBLEMS=()

problem() {
  PROBLEMS+=("$1")
  printf '   \033[1;33m!! %s\033[0m\n' "$1"
}

PY="${PYTHON:-python3}"

say "1/7  Checking what is installed"
"$PY" --version
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "   Python 3.11 or newer is needed. On Ubuntu: sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi
if ! command -v node >/dev/null; then
  echo "   Node.js 20 or newer is needed. See https://nodejs.org/"
  exit 1
fi
node --version
npm --version

say "2/7  The backend of the hub"
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

say "3/7  Peer Benchmarking"
cd benchmarking
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel >/dev/null 2>&1 || true
if ! python -m pip install -r requirements.txt; then
  problem "Peer Benchmarking could not be installed. The hub still works without it."
fi
deactivate
cd ..

say "4/7  The Data Summarizer (Regulatory Sentinel)"
cd sentinel
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel >/dev/null 2>&1 || true
if ! python -m pip install -r backend/requirements-dev.txt; then
  problem "The Data Summarizer could not be installed. The hub still works without it."
fi
deactivate
cd ..

say "5/7  The three web applications"
if ! (cd frontend && npm install); then
  problem "The libraries of the news application could not be downloaded."
fi
if ! (cd landing && npm install); then
  problem "The libraries of the landing page could not be downloaded."
fi
# The Data Summarizer serves its own interface from the same address as its API,
# so it is built once here rather than at every start.
if ! (cd sentinel/frontend && { [ -d node_modules ] || npm install; } && npm run build); then
  problem "The interface of the Data Summarizer could not be built. It will show nothing until it is."
fi

say "6/7  The settings files"
"$PY" scripts/make_env.py || problem "The settings files could not be written."

say "7/7  The demo accounts"
if ! (cd backend && .venv/bin/python seed_users.py); then
  problem "The accounts could not be written. Nobody can sign in until they are."
fi

if [ ${#PROBLEMS[@]} -eq 0 ]; then
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
else
  cat <<'DONE'

The setup finished with problems. The rest of the platform is ready.

Start the platform with:

    ./run.sh

Check what is still missing at any time:

    python scripts/doctor.py

The problems were:

DONE

  for item in "${PROBLEMS[@]}"; do
    echo "  - $item"
  done

  echo ""
  echo "Run this setup again once the cause is sorted out."
fi
