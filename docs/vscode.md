# Running the Platform in Visual Studio Code

The repository ships with a VS Code configuration for all three
services, so the whole platform can be started from the editor.

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Runs the backend. `uv --version` must work in a terminal. |
| Node.js 20 or newer | Runs both frontend applications. `node --version` must work. |
| Python extension | Recommended by `.vscode/extensions.json`. |
| ESLint extension | Recommended by `.vscode/extensions.json`. |

Open the repository folder in VS Code and accept the recommended
extensions when prompted.

## 2. One-time setup

Open the Command Palette with <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd>
(<kbd>Cmd</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> on macOS) and run
**Tasks: Run Task**.

Choose **Setup: everything**. It installs the backend, the news
dashboard and the landing page, and creates the demo accounts.

The individual steps are available separately if you prefer to run them
one at a time:

| Task | What it does |
|---|---|
| `Setup: backend dependencies` | Creates `backend/.venv` and installs the packages. |
| `Setup: news frontend dependencies` | Installs the packages in `frontend/`. |
| `Setup: landing page dependencies` | Installs the packages in `landing/`. |
| `Setup: seed demo users` | Creates the demo accounts, for example `Admin` / `Admin@news26`. |

## 3. Running the platform

**Tasks: Run Task** → **Dev: all services**.

Three terminals open side by side:

| Service | URL | Terminal |
|---|---|---|
| Landing page hub | <http://localhost:5174> | `Run: landing page` |
| News dashboard | <http://localhost:5173> | `Run: news frontend` |
| FastAPI backend | <http://127.0.0.1:8000> | `Run: backend` |
| API documentation | <http://127.0.0.1:8000/docs> | |

Open <http://localhost:5174> and sign in with a seeded account, for
example `Admin` / `Admin@news26`. Select **News Feed** in the sidebar
and the dashboard opens inside the workspace, already signed in.

Each service can also be started on its own with `Run: backend`,
`Run: news frontend` or `Run: landing page`.

## 4. Debugging

Open the **Run and Debug** panel (<kbd>F5</kbd>).

| Configuration | What it does |
|---|---|
| `Backend: FastAPI` | Runs the backend under the debugger, with breakpoints in the Python code. |
| `Landing page (Chrome)` | Opens the landing page in Chrome with the frontend source maps. |
| `News dashboard (Chrome)` | Opens the news dashboard in Chrome. |
| `Debug: landing page with all services` | Starts all three services, attaches the Python debugger to the backend and opens the landing page in Chrome. |

The last one is the useful one for working on the integration: it starts
everything, and you can set a breakpoint in `backend/app/api/auth.py` or
in the session bridge.

## 5. Tests

**Tasks: Run Test Task** (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> →
**Tasks: Run Test Task**) lists the three suites, and the Python
extension offers **Debug Test** on the backend suite.

| Task | Suite |
|---|---|
| `Test: backend` | Authentication endpoints (`pytest`). |
| `Test: news frontend` | Frame session bridge (`node --test`). |
| `Test: landing page` | Hub frame bridge (`node --test`). |
| `Test: all` | All three, in parallel. |

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

### The three other services show "Planned"

That is expected. SQL Genie, Data Summarizer and Peer Benchmarking are
part of the platform scope but are not implemented yet. They are
registered in `landing/src/services.js`.
