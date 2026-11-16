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
| Python | 3.11 or newer | `python --version` must work. |
| Node.js | 18 or newer | `node --version` must work. The versions that are installed are written down in the lock files, so every machine ends up with the same ones. |
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

The script does seven things. It can be run again at any time.

1. Checks that Python and Node.js are installed.
2. Creates `backend/.venv` and installs the backend.
3. Creates `benchmarking/.venv` and installs Peer Benchmarking.
4. Creates `sentinel/.venv` and installs the Data Summarizer.
5. Installs the packages of the web applications, and builds the
   interface of the Data Summarizer.
6. Writes `backend/.env`, `benchmarking/.env` and `sentinel/.env`,
   **including the secrets the servers share**. It also writes the
   ports each service uses and the model that is really installed on
   the machine. A port that is already taken — by a model server, for
   instance — is moved, and every file that names it is written again
   with the new port.
7. Creates the demo accounts.

Then start everything:

```bash
./run.sh
```

Five services come up:

```
Landing page hub    http://localhost:5174
News dashboard      http://localhost:5173
Peer Benchmarking   http://localhost:8077
Data Summarizer     http://localhost:8090
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

Five windows open, one for each service. Close them to stop the
platform.

### Doing it by hand

```powershell
# Window 1 - the backend of the hub
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Window 2 - Peer Benchmarking
cd benchmarking
.\.venv\Scripts\python.exe -m kpibench.main

# Window 3 - the Data Summarizer
cd sentinel\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8090

# Window 4 - the news dashboard
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173

# Window 5 - the landing page hub
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
| **Data Summarizer** | The Regulatory Sentinel application: the circulars and the notifications of the Reserve Bank of India, and their summaries. Opens in the workspace, already signed in, with its own sidebar replaced by a slim tab bar. |
| **News Feed** | Opens in the workspace, already signed in, with its own header hidden. |
| **SQL Genie** | Opens in the workspace, already signed in. It is an application of its own: point the hub at it with `VITE_SQL_GENIE_APP_URL` in `landing/.env`, and add its origin to `VITE_ALLOWED_CHILD_ORIGINS` there as well. |

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

### The ports and the model are worked out for you

`scripts/make_env.py` looks at the machine and writes down what it finds,
so that the settings match the machine they are on:

- **The ports.** Each service has a port it prefers. When that port is
  already taken — by a model server, for instance — another port nearby
  is chosen instead, and every file that names the port is written again
  with the new one. A port that one of our own services is already using
  is left alone, so running the setup again while the platform is up does
  not move anything.

  The ports that were chosen are named at the end of the setup, and
  `python scripts/doctor.py` checks the running services against them.

- **The model.** The model server on the machine is asked which models it
  has, and the best one of them is written into the settings, so that the
  settings say plainly what will be used. A model for embeddings is
  written as well; when the machine has none, the Data Summarizer falls
  back to a plain method of its own and downloads nothing.

  Nothing is downloaded by the setup. Pull a model first and run the
  setup again to have it named:

  ```bash
  ollama pull qwen3:32b
  python scripts/make_env.py
  ```

### `backend/.env`

| Setting | Meaning |
|---|---|
| `PORT` | The port the backend of the hub listens on. `8000`. Change it when the port is taken on this machine; the setup script tells the two web applications about it. |
| `JWT_SECRET_KEY` | Signs the access tokens of the hub. Generated for you. |
| `DATABASE_URL` | The news database. A SQLite file by default. |
| `OLLAMA_MODEL` | The model the AI analysis of the news uses. The best model that is installed on the machine, written by the setup script. |
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

### `sentinel/.env`

The Data Summarizer, which is the Regulatory Sentinel application.

| Setting | Meaning |
|---|---|
| `JWT_SECRET` | Signs the sessions of the summarizer. Generated for you. |
| `PORT` | The port the summarizer listens on. `8090`. |
| `AUTH_ENABLED` | `true` keeps the summarizer's own sign-in switched on, so that the person who signs in at the hub is signed in here as well. |
| `HANDOFF_SECRET` | The secret the hub and the summarizer share. **The same value as `SENTINEL_HANDOFF_SECRET` in `backend/.env`.** |
| `HANDOFF_ADMIN_USERS` | The hub accounts that are administrators in the summarizer as well. `admin` by default. |
| `FRAME_ANCESTORS` | The sites allowed to show this app in a frame. |
| `EMBED_PARENT_ORIGINS` | The sites allowed to drive this app. |
| `LLM_PROVIDER` | `openai_compat` writes with the language model on the machine; `none` writes the summaries without a model. |
| `LLM_MODEL` | The model the summaries are written with. `auto` means the best model that is installed on this machine. Name a model, such as `qwen3:8b`, to pin it. |
| `LLM_STRICT_MODEL` | `true` refuses to use any model but the one that is named. |
| `EMBEDDING_PROVIDER` | `openai_compat` takes the embeddings from the same model server; `hash` needs nothing at all. |

If the secrets ever fall out of step, run the setup again:

```bash
python scripts/make_env.py
```

It writes one secret into each pair of files and leaves everything else alone.

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

### "The backend of the hub did not start"

`run.sh` and `run.ps1` wait for the backend before they say the platform
is starting. When it does not come up, they show what the backend said,
so the reason is never left in a window that is out of the way:

```
It stopped with an error. This is what it said:

    Value error, JWT_SECRET_KEY is not set.
    ...
```

The whole record is kept in `backend/logs/backend.log`.

The two usual causes are:

| What the backend said | What to do |
|---|---|
| `JWT_SECRET_KEY is not set` | The settings file is missing. Run `./setup.sh` (Windows: `.\setup.ps1`) |
| `address already in use` | Another copy of the backend is running. Stop it, or change `PORT` and `KPI_APP_URL` together |
| `No module named uvicorn` | The setup did not finish. Run `./setup.sh` again |
| It is still starting, with nothing said | The first start on a new machine is slow. Wait, or start the backend by hand to watch it: `cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` |

### "An Application Control policy has blocked this file"

The machine has a rule — AppLocker, WDAC, Smart App Control, or an
antivirus that works the same way — that refuses to load some compiled
files. SQLAlchemy is written partly in C, and from version 2.1 it
imports that part directly, so a refused file stops the whole library
from being imported, and the backend with it.

The platform arranges for itself. Every library of that kind also
ships a version written in plain Python, which does the same work a
little more slowly. When the backend starts, the compiled files that
the machine refuses are set aside, and the plain Python parts are used
instead. It says so in the record:

```
The machine would not load sqlalchemy.sql._cache_key_cy, so the plain
Python version of it is used instead.
```

To do it by hand, or to see what was set aside:

```bash
cd backend
.venv/bin/python -c "from app.blocked_extensions import make_work; print(make_work())"
```

And to check whether it is needed at all:

```bash
python scripts/doctor.py
```

The setup keeps SQLAlchemy inside the 2.0 series, where the compiled
part is optional, so a new installation does not need this at all.

### The workspace shows "Your session has ended"

The hub could not sign the app in. The usual cause is a mismatch
between `HANDOFF_SECRET` and `KPI_HANDOFF_SECRET`, or
`EMBED_PARENT_ORIGINS` that does not list the address the hub is served
from. The hub must be listed exactly as the browser sees it:
`http://localhost:5174` and `http://127.0.0.1:5174` are different
origins.

### "The Data Summarizer is not connected yet"

The hub and the summarizer do not share a secret. Run the setup again:

```bash
python scripts/make_env.py
```

It writes the same secret into `backend/.env`
(`SENTINEL_HANDOFF_SECRET`) and `sentinel/.env` (`HANDOFF_SECRET`).

### "The Data Summarizer could not be reached"

The summarizer is not running, or `SENTINEL_APP_URL` in `backend/.env`
does not point at it. It listens on port 8090:

```bash
cd sentinel/backend && ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

### The app is refused in the frame

`FRAME_ANCESTORS` in `benchmarking/.env` must list the hub's origin.
For the Data Summarizer it is `FRAME_ANCESTORS` in `sentinel/.env`.

### "No module named kpibench"

Peer Benchmarking was started from the wrong folder. Run it from
`benchmarking/`, where its own package lives.

### Port 8077 or 8000 is already in use

The setup script moves a port that is taken on this machine by something
else — a model server, for instance — and writes the new port everywhere
it is named. So the usual answer is to run the setup again:

```bash
python scripts/make_env.py
```

To see what is on the port:

```bash
sudo ss -tlnp | grep :8000
sudo lsof -i :8000
```

To choose the port by hand, set it and run the same script, which writes
it into every file that names it:

```bash
# backend/.env
PORT=8010

python scripts/make_env.py
```

A port that one of our own services is already using is left alone, so
running the setup while the platform is up does not move anything.

### "Multiple top-level packages discovered in a flat-layout"

The backend could not be built. This happens with an old copy of the
code, where the backend folder held more than one folder that could be a
package. Take the newest copy of the project and run the setup again:

```bash
git pull
./setup.sh
```

### "Cannot find native binding"

The interface of the Data Summarizer could not be built: the compiled
part of Tailwind was left out. Some versions of npm leave it out when it
is named for a newer version of Node. The setup script installs it by
hand when that happens. To do it yourself:

```bash
cd sentinel/frontend
npm install --no-save "@tailwindcss/oxide-linux-x64-gnu@$(node -p "require('./node_modules/@tailwindcss/oxide/package.json').version")"
npm run build
```

On a machine with a newer Node this does not happen at all.

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
