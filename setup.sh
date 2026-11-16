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
  echo "   Node.js is needed. On Ubuntu: sudo apt install -y nodejs npm"
  echo "   or, for a newer version: https://github.com/nodesource/distributions#installation-instructions"
  exit 1
fi
node --version
npm --version

# The web applications are built with Vite, which needs Node 18 or newer. An
# older Node is reported plainly, because the failure otherwise shows up much
# later as a strange error from the build.
if ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 18 ? 0 : 1)'; then
  echo "   Node.js 18 or newer is needed to build the web applications."
  echo "   On Ubuntu: sudo apt install -y nodejs npm"
  echo "   or, for a newer version: https://github.com/nodesource/distributions#installation-instructions"
  exit 1
fi

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

# The packages are installed from the lock files, so that every machine ends up
# with the same versions. When the installation fails halfway, it leaves a
# broken folder behind, and a second attempt over it fails in the same way, so
# the folder is removed before the second attempt.
install_packages() {  # install_packages <folder>
  local folder="$1"
  (cd "$folder" && npm install --no-audit --no-fund) && return 0

  note "The installation of $folder was interrupted. Trying once more."
  rm -rf "$folder/node_modules"

  (cd "$folder" && npm install --no-audit --no-fund)
}

if ! install_packages frontend; then
  problem "The libraries of the news application could not be downloaded."
fi
if ! install_packages landing; then
  problem "The libraries of the landing page could not be downloaded."
fi
# The Data Summarizer serves its own interface from the same address as its API,
# so it is built once here rather than at every start.
if ! (cd sentinel/frontend && { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build); then
  problem "The interface of the Data Summarizer could not be built. It will show nothing until it is."
fi

# Some versions of npm leave out a library that is meant for this machine when
# it is named for a newer version of Node. The Data Summarizer needs its
# compiled part, and the build fails with a strange message when it is missing.
if [ -d sentinel/frontend/node_modules/@tailwindcss/oxide ] && \
   ! ls sentinel/frontend/node_modules/@tailwindcss/ | grep -q "linux-x64-gnu"; then
  note "The compiled part of the Data Summarizer is missing. Installing it by hand."
  (cd sentinel/frontend && npm install --no-save --no-audit --no-fund \
    "@tailwindcss/oxide-linux-x64-gnu@$(node -p "require('./node_modules/@tailwindcss/oxide/package.json').version")") \
    >/dev/null 2>&1 || true
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
