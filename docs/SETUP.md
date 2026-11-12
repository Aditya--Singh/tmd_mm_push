# Setting up the platform

The platform is one repository with four parts. One sign-in opens all of
them.

| Part | Folder | Runs on | What it is |
|---|---|---|---|
| Landing page hub | `landing/` | <http://localhost:5174> | The sign-in and the frame around every service |
| Backend | `backend/` | <http://127.0.0.1:8000> | The API: sign-in, the news, the feedback, the bridge to Peer Benchmarking |
| News dashboard | `frontend/` | <http://localhost:5173> | The news intelligence application |
| Peer Benchmarking | `benchmarking/` | <http://localhost:8077> | The benchmarking application |

Peer Benchmarking keeps its own database, its own sessions and its own
audit trail. The hub does not take that over: it signs the person in and
hands the benchmarking app a single-use ticket, so the same person is
signed in on both sides with the role they hold in each of them.

---

## 1. What you need

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10 or newer | `python --version` must work. |
| Node.js | 20 or newer | `node --version` must work. |
| A C compiler and the headers of Python | — | Needed by a few packages of Peer Benchmarking (`pdfplumber`, `python-pptx`). On Debian and Ubuntu: `sudo apt install -y build-essential python3-dev`. |

Nothing else. No database server, no message broker and no container
runtime: both servers use a SQLite file next to the code.

---

## 2. Linux and macOS

Open a terminal in the repository folder.

```bash
git clone https://github.com/Aditya--Singh/top-management-dashboard.git
cd top-management-dashboard
./setup.sh
```

The script does five things. It can be run again at any time.

1. Checks that Python and Node.js are installed.
2. Creates `backend/.venv` and installs the backend.
3. Creates `benchmarking/.venv` and installs Peer Benchmarking.
4. Installs the packages of the two web applications.
5. Writes `backend/.env` and `benchmarking/.env`, **including the secret
   the two servers share**, and creates the demo accounts.

Then start everything:

```bash
./run.sh
```

Four services come up:

```
Landing page hub    http://localhost:5174
News dashboard      http://localhost:5173
Peer Benchmarking   http://localhost:8077
Backend and its API http://127.0.0.1:8000/docs
```

Open <http://localhost:5174> and sign in.

Stop everything with <kbd>Ctrl</kbd>+<kbd>C</kbd> in the terminal that
started `run.sh`; the other services are stopped with it.

### Doing it by hand

If you would rather run each part in its own terminal, that is what the
VS Code tasks do too.

```bash
# Terminal 1 - the backend of the hub
cd backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 - Peer Benchmarking
cd benchmarking
.venv/bin/python -m kpibench.main

# Terminal 3 - the news dashboard
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173

# Terminal 4 - the landing page hub
cd landing
npm run dev -- --host 127.0.0.1 --port 5174
```

---

## 3. Windows

Open PowerShell in the repository folder. If your machine blocks the
script, run it once with:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

```powershell
git clone https://github.com/Aditya--Singh/top-management-dashboard.git
cd top-management-dashboard
.\setup.ps1
```

Then start everything:

```powershell
.\run.ps1
```

Four windows open, one for each service. Close them to stop the
platform.

### Doing it by hand

```powershell
# Window 1 - the backend of the hub
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Window 2 - Peer Benchmarking
cd benchmarking
.\.venv\Scripts\python.exe -m kpibench.main

# Window 3 - the news dashboard
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173

# Window 4 - the landing page hub
cd landing
npm run dev -- --host 127.0.0.1 --port 5174
```

---

## 4. Signing in

The demo accounts are created by the setup, from the account sheet in
`backend/seed/users.csv`. That file holds the same content as the
`users` and `refer` worksheets of the account sheet: the name of the
account, the password in plain text, the role in the News Feed and the
role in Peer Benchmarking.

The password in the sheet is the password of the account. It is hashed
before it is stored, so the database only ever holds the hash.

| Account | Password | News Feed | Peer Benchmarking | What it can do |
|---|---|---|---|---|
| `admin` | `admin@tmd26` | Administrator | Administrator | Everything, including the summary, the pipeline control and the user list in Peer Benchmarking |
| `analyst` | `Pnb@12345` | Reader | Analyst (Maker) | Collects the figures, runs the pipeline, drafts the reports |
| `approver` | `Pnb@12345` | Reader | Approver (Checker) | Checks and approves the figures and the reports |
| `gm` | `Pnb@12345` | Reader | Top Management (Viewer) | Reads the approved figures, asks Myra |
| `aditya`, `hemant`, `nikhil`, `deepak`, `vijay`, `vikas`, `pankaj` | `<name>@news26` | Reader | Reader | Reads the news, and the same read-only view of the figures |

A person holds **one role in each application**, and the two are kept
apart: `role_news` for the News Feed and `role_bench` for Peer
Benchmarking. Both are held once, in the `users` table of the backend,
and each application is given the one that belongs to it.

The name of an account is matched without regard to case, so `Admin`
and `admin` open the same account.

To change a password or a role, change the sheet and run the seed
again:

```bash
cd backend
uv run python seed_users.py
```

---

## 5. Using the platform

Open <http://localhost:5174> and sign in. The hub is the frame around
everything: the header holds the date, the feedback control and the
sign-out, and the rail on the left holds the services.

| Service | What happens |
|---|---|
| **Peer Benchmarking** | Opens in the workspace, already signed in. The rail grows a list of screens underneath it, and choosing one moves the application to it. |
| **News Feed** | Opens in the workspace, already signed in, with its own header hidden. |
| **SQL Genie**, **Data Summarizer** | Marked **Planned**. They are part of the platform scope and are not built yet. |

Signing out of the hub ends the session in every open service as well.

### The news pipeline

The **News Data Pipeline** panel, in the summary of the News Feed, fetches
the news and runs the AI analysis over it. Before the button there is a
dropdown that says how far back the news may reach:

| Window | What is fetched |
|---|---|
| Today only | The news published today |
| Last 3, 7, 15, 30, 45, 60 or 90 days | The news published in that many days |
| Anything longer | Refused: 90 days is the longest window |

The window sets the cut-off date, and the date is written under the
button so that it is clear what is being fetched. News published before
the cut-off is neither fetched nor stored.

`NEWS_CUTOFF_DATE` in `backend/.env` is the floor: the oldest day the
news may ever reach, whatever window is asked for.

---

## 6. The settings

Two files hold the settings. Both are written by the setup script and
neither is ever sent to a browser.

### `backend/.env`

| Setting | Meaning |
|---|---|
| `JWT_SECRET_KEY` | Signs the access tokens of the hub. Generated for you. |
| `DATABASE_URL` | The news database. A SQLite file by default. |
| `OLLAMA_MODEL` | The model the AI analysis of the news uses. `qwen3:8b` by default. |
| `NEWS_CUTOFF_DATE` | The oldest day the news may reach, whatever window is asked for. |
| `CORS_ORIGINS` | The browser origins allowed to call the API. |
| `KPI_APP_URL` | Where Peer Benchmarking is listening. `http://127.0.0.1:8077`. |
| `KPI_HANDOFF_SECRET` | The secret the two servers share. **The same value as `HANDOFF_SECRET` in `benchmarking/.env`.** |

### `benchmarking/.env`

| Setting | Meaning |
|---|---|
| `SECRET_KEY` | Signs the sessions of the benchmarking app. Generated for you. |
| `PORT` | The port the benchmarking app listens on. `8077`. |
| `HANDOFF_SECRET` | The secret the two servers share. **The same value as `KPI_HANDOFF_SECRET` in `backend/.env`.** |
| `HANDOFF_ALLOW_STAFF` | `true` lets the hub sign in analysts, approvers and administrators. |
| `HANDOFF_SYNC_ROLE` | `true` makes the hub's role the role held here. |
| `FRAME_ANCESTORS` | The sites allowed to show this app in a frame. |
| `EMBED_PARENT_ORIGINS` | The sites allowed to drive this app. |
| `DEFAULT_PASSWORD` | The password of the four starter accounts of the benchmarking app. |
| `LLM_PROVIDER` | `ollama` uses the local language model; `none` writes the reports from the fixed template. The setup script chooses this: `ollama` when a model server is running. |
| `OLLAMA_MODEL` | The model the reports are written with. `auto` means the best model that is installed on this machine. Name a model, such as `qwen3:8b`, to pin it. |
| `OLLAMA_STRICT_MODEL` | `true` refuses to use any model but the one that is named. |

If the two secrets ever fall out of step, run the setup again:

```bash
python scripts/make_env.py
```

It writes one secret into both files and leaves everything else alone.

---

## 7. Running it on a server

The two web applications are static builds and the backend serves the
API, so a deployment is a reverse proxy in front of three things.

```bash
cd frontend && npm run build
cd ../landing && npm run build
```

| Path | Goes to |
|---|---|
| `/` | `landing/dist` |
| `/news/` | `frontend/dist` (built with `VITE_BASE_PATH=/news/`) |
| `/benchmarking/` | `benchmarking/` served by its own server on port 8077 |
| `/api/` | the backend on port 8000 |

In that shape the applications share one origin, the browser stops
treating them as separate sites, and the frames need no special
permission.

Set these in the environment of the machine:

```text
backend/.env
CORS_ORIGINS=https://<your-host>
KPI_APP_URL=http://127.0.0.1:8077

benchmarking/.env
FRAME_ANCESTORS='self' https://<your-host>
EMBED_PARENT_ORIGINS=https://<your-host>
```

Serve Peer Benchmarking over HTTPS when the hub is served over HTTPS: a
browser will not show an `http://` frame inside an `https://` page.

`docs/deployment.md` has the full nginx example.

---

## 8. Tests

```bash
# The backend
cd backend && .venv/bin/python -m pytest -q

# Peer Benchmarking
cd benchmarking && .venv/bin/python -m pytest tests -q

# The two web applications
cd frontend && node --test
cd landing && node --test

# The browser tests, with the platform running
cd landing/e2e && node hub-embedding.mjs
cd landing/e2e && node benchmarking.mjs
cd landing/e2e && node news-roles.mjs
```

---

## 9. When something does not work

Before anything else, let the platform check itself:

```bash
python scripts/doctor.py
```

It says what is missing and the command that fixes it.

### "Peer Benchmarking is not connected yet"

The two servers do not share a secret. Run `python scripts/make_env.py`
and restart the backend.

### "Peer Benchmarking could not be reached"

The benchmarking app is not running, or `KPI_APP_URL` points somewhere
else. Check <http://localhost:8077/healthz>.

### "Unable to connect to the authentication service"

The sign-in never reached the backend. The page says which of the two it is:

| What the page says | What to do |
|---|---|
| **The backend is not answering** | The backend is not running, or it is not on port 8000. Start it: `cd backend && uv run python -m uvicorn app.main:app --port 8000` |
| **The browser could not reach the authentication service** | The request was blocked or the address is wrong. Check `VITE_API_BASE_URL` in `landing/.env`, and that this address is listed in `CORS_ORIGINS` in `backend/.env` |

To have the whole platform checked at once:

```bash
python scripts/doctor.py
```

It looks at the settings files, the shared secret, the accounts, the
environments and the four running services, and says what is missing
and the command that fixes it.

### The workspace shows "Your session has ended"

The hub could not sign the app in. The usual cause is a mismatch
between `HANDOFF_SECRET` and `KPI_HANDOFF_SECRET`, or
`EMBED_PARENT_ORIGINS` that does not list the address the hub is served
from. The hub must be listed exactly as the browser sees it:
`http://localhost:5174` and `http://127.0.0.1:5174` are different
origins.

### The app is refused in the frame

`FRAME_ANCESTORS` in `benchmarking/.env` must list the hub's origin.

### "No module named kpibench"

Peer Benchmarking was started from the wrong folder. Run it from
`benchmarking/`, where its own package lives.

### Port 8077 or 8000 is already in use

Another copy is still running. Stop it, or change `PORT` in
`benchmarking/.env` and `KPI_APP_URL` in `backend/.env` together.

### The packages will not download

Behind a proxy, set it first:

```bash
export HTTPS_PROXY=http://<proxy-host>:<port>
export HTTP_PROXY=$HTTPS_PROXY
./setup.sh
```

Behind a mirror that does not carry every package, use the public index
once:

```bash
PIP_INDEX_URL=https://pypi.org/simple ./setup.sh
```
