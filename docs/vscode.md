# Running the Platform in Visual Studio Code

The repository ships with a VS Code configuration for all four
services, so the whole platform can be started from the editor.

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Runs the backend. `uv --version` must work in a terminal. |
| Node.js 20 or newer | Runs both frontend applications. `node --version` must work. |
| Python 3.10 or newer | Runs Peer Benchmarking. `python --version` must work. |
| Python extension | Recommended by `.vscode/extensions.json`. |
| ESLint extension | Recommended by `.vscode/extensions.json`. |

Open the repository folder in VS Code and accept the recommended
extensions when prompted.

## 2. One-time setup

Open the Command Palette with <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd>
(<kbd>Cmd</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> on macOS) and run
**Tasks: Run Task**.

Choose **Setup: everything**. It installs the backend, Peer
Benchmarking, the news dashboard and the landing page, writes the
settings files, and creates the demo accounts.

The individual steps are available separately if you prefer to run them
one at a time:

| Task | What it does |
|---|---|
| `Setup: backend dependencies` | Creates `backend/.venv` and installs the packages. |
| `Setup: benchmarking dependencies` | Creates `benchmarking/.venv` and installs the packages. |
| `Setup: news frontend dependencies` | Installs the packages in `frontend/`. |
| `Setup: landing page dependencies` | Installs the packages in `landing/`. |
| `Setup: settings files` | Writes `backend/.env` and `benchmarking/.env`, including the secret the two servers share. |
| `Setup: seed demo users` | Creates the demo accounts, for example `admin` / `admin@tmd26`. |

## 3. Running the platform

**Tasks: Run Task** → **Dev: all services**.

Six terminals open side by side:

| Service | URL | Terminal |
|---|---|---|
| Landing page hub | <http://localhost:5174> | `Run: landing page` |
| News dashboard | <http://localhost:5173> | `Run: news frontend` |
| Peer Benchmarking | <http://localhost:8077> | `Run: benchmarking` |
| Data Summarizer | <http://localhost:8090> | `Run: the Data Summarizer` |
| Data Analyzer | <http://localhost:8095> | `Run: the Data Analyzer` |
| FastAPI backend | <http://127.0.0.1:8000> | `Run: backend` |
| API documentation | <http://127.0.0.1:8000/docs> | |

Open <http://localhost:5174> and sign in with a seeded account, for
example `admin` / `admin@tmd26`. Select **News Feed** in the sidebar
and the dashboard opens inside the workspace, already signed in. Select
**Peer Benchmarking** and the benchmarking app opens there, already
signed in, with its own screens listed underneath it in the rail. Select
**Data Analyzer** and the analyzer opens there too: share an Excel file
or a CSV file, and it is described, summarised, drawn and asked about.

Each service can also be started on its own with `Run: backend`,
`Run: benchmarking`, `Run: the Data Summarizer`, `Run: the Data
Analyzer`, `Run: news frontend` or `Run: landing page`.

## 4. Debugging

Open the **Run and Debug** panel (<kbd>F5</kbd>).

| Configuration | What it does |
|---|---|
| `Backend: FastAPI` | Runs the backend under the debugger, with breakpoints in the Python code. |
| `Benchmarking: FastAPI` | Runs Peer Benchmarking under the debugger. |
| `Data Summarizer: FastAPI` | Runs the Data Summarizer under the debugger. |
| `Data Analyzer: FastAPI` | Runs the Data Analyzer under the debugger. |
| `Landing page (Chrome)` | Opens the landing page in Chrome with the frontend source maps. |
| `News dashboard (Chrome)` | Opens the news dashboard in Chrome. |
| `Peer Benchmarking (Chrome)` | Opens the benchmarking app on its own. |
| `Debug: landing page with all services` | Starts all six services, attaches the Python debugger to the backend and opens the landing page in Chrome. |
| `Debug: hub and Peer Benchmarking` | The same, with both Python servers under the debugger. |

The last one is the useful one for working on the integration: it starts
everything, and you can set a breakpoint in `backend/app/api/auth.py`, in
`backend/app/api/integrations.py` or in the session bridge.

The tasks work on Linux, on macOS and on Windows. A task that needs the
python of a virtual environment uses the place it is in on the system it
runs on: `.venv/bin/python` on Linux and macOS, `.venv\Scripts\python.exe`
on Windows.

## 5. Tests

**Tasks: Run Test Task** (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> →
**Tasks: Run Test Task**) lists the three suites, and the Python
extension offers **Debug Test** on the backend suite.

| Task | Suite |
|---|---|
| `Test: backend` | Authentication, roles and the bridge (`pytest`). |
| `Test: news frontend` | Frame session bridge (`node --test`). |
| `Test: landing page` | Hub frame bridge (`node --test`). |
| `Test: benchmarking` | The hand-off and navigation tests of Peer Benchmarking (`pytest`). |
| `Test: hub with Peer Benchmarking` | The browser test of the benchmarking service. It needs the platform running. |
| `Test: the Data Analyzer` | The tests of the Data Analyzer (`pytest`). |
| `Test: hub with the Data Analyzer` | The browser test of the analyzer: it shares a document and asks a question. It needs the platform running. |
| `Test: news feed for every role` | The browser test that every role can read the news. It needs the platform running. |
| `Test: all` | All of them, in parallel. |

`Check: lint and build` lints and builds the news frontend. The same
commands work in `landing/`.

## 6. Configuration files

| File | Purpose |
|---|---|
| `.vscode/tasks.json` | Setup, run, test and lint tasks. |
| `.vscode/launch.json` | Debug configurations. |
| `.vscode/settings.json` | Interpreter, ESLint working directories, excluded folders. |
| `.vscode/extensions.json` | Recommended extensions. |

## 7. Troubleshooting

### "The backend is not configured yet"

The backend needs a signing key for its access tokens and refuses to
start without one. Create the environment file and give it a random
value:

```bash
cd backend
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value into `JWT_SECRET_KEY` in `backend/.env`, then
start the backend again. A `.env` in the repository root is read as a
fallback, so either location works.

### "No module named uvicorn" or "No module named fastapi"

The backend is being started with a Python that does not have the
packages installed, usually because the virtual environment is not
active in that terminal.

Use the `Run: backend` task. It starts the server through `uv run`, so
it does not need the virtual environment to be activated. If you start
the backend by hand, either activate the environment:

```bash
source backend/.venv/bin/activate
```

or prefix the command:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

If the task list still shows only the old "Run Backend" entry, the
workspace is on a version of the branch from before the VS Code
configuration was updated. Pull the branch and reload the window.

### "No module named app"

The backend was started from the wrong directory. Run it from
`backend/`, or pass the application directory:

```bash
uv run uvicorn app.main:app --app-dir backend
```

### "'Settings' object has no attribute ..." in a traceback

The backend is running a cached copy of an older module. Clear the byte
code cache and restart:

```bash
cd backend
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```

This shows up on network drives and shared folders, where the file
timestamps are too coarse for Python to notice a change.

### The Python extension does not pick up the virtual environment

Run **Python: Select Interpreter** from the Command Palette and choose
`backend/.venv`. The setting `python.defaultInterpreterPath` points at
the folder, which lets the extension resolve the interpreter on Windows,
Linux and macOS, but a manual selection always overrides it.

### The tasks cannot find the backend packages

The backend tasks use `uv run`, which creates and syncs
`backend/.venv` automatically. If `uv` is not on the path, install it or
run the setup task from a terminal where `uv --version` works.

### Port 5173 or 5174 is already in use

Something else is using the port. Stop it, or start the task with a
different port and update the matching value:

```bash
cd landing
npm run dev -- --port 5180
```

Also update `VITE_NEWS_APP_URL` in `landing/.env` and the allowed
origins, so that the two applications can still find each other.

### "[Errno 98] Address already in use" on port 8000

Another backend is already running, most likely one you started earlier.
Stop it, or start the backend on a different port and point the
frontend at it with `VITE_API_BASE_URL`.

### The embedded dashboard asks for a sign-in

The landing page and the news application have to be able to find each
other. The defaults cover the standard local setup. If you moved either
one, set the matching variables:

```text
landing/.env
VITE_ALLOWED_CHILD_ORIGINS=http://localhost:5173

frontend/.env
VITE_ALLOWED_PARENT_ORIGINS=http://localhost:5174
```

### The dashboard inside the workspace is empty

The dashboard reads from the SQLite database. Run the scraper to fill
it:

```bash
cd backend
uv run python run_scraper.py
```

### The SQL Genie opens nothing

The SQL Genie is an application of its own. Point the hub at it with
`VITE_SQL_GENIE_APP_URL` in `landing/.env`, and add its origin to
`VITE_ALLOWED_CHILD_ORIGINS` in the same file. Without the second one,
the application is shown but the session is never handed over.

### The Data Analyzer shows no documents

The Data Analyzer keeps the documents it has read in its own database, in
`dataanalyzer/backend/data/`. A new installation is empty: share an
Excel workbook or a CSV file from the hub, and it appears there.

### Peer Benchmarking shows "not connected yet"

The backend and the benchmarking app have to share a secret. Run
**Setup: settings files**, which writes one secret into both
`backend/.env` and `benchmarking/.env`, and restart both services.

### Peer Benchmarking shows "Your session has ended"

The hub could not sign the app in. The two usual causes are a secret
that does not match, and `EMBED_PARENT_ORIGINS` that does not list the
address the hub is served from. `http://localhost:5174` and
`http://127.0.0.1:5174` are different origins, and the browser uses the
one it actually typed.
