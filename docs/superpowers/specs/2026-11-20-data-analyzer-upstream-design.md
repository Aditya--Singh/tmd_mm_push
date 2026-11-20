# The Data Analyzer: the Employee Productivity Tool in the workspace

**Date:** 2026-11-20
**Status:** agreed
**Service:** `dataanalyzer/` — the fifth service of the Executive Intelligence Hub

## 1. The goal

The hub has a **Data Analyzer** card. It must open the application published at
`https://github.com/Aditya--Singh/employee-productivity` — the "PNB Employee Productivity
Tool" — inside the hub's frame, with the hub's sign-in, and with nothing else about the
platform's shape changed.

The tool itself is kept as it is: **Document Assistant** (extract, summarise, rewrite,
proofread, export, and a chat over a spreadsheet), **Circular Analyzer** (a placeholder in
the upstream, kept as a placeholder), and **Coming Soon**.

Two things are decided and are not open again:

- **The app is the upstream app.** The half-finished "data models" application that
  currently sits in `dataanalyzer/` is discarded, along with its uncommitted refactor. The
  upstream's data chat (`data_ops`, `data_stats`, `data_cells`) covers the same ground.
- **LanguageTool is optional.** The upstream's proofread feature needs a separate local
  LanguageTool server (Java, normally Docker, port 8120). The feature stays; the
  dependency does not. Everything else in the app works without it, and the app says so
  in words when it is not there.

## 2. What replaces what

| Path | Now | After |
| --- | --- | --- |
| `dataanalyzer/backend/app/core/` | `db.py`, `handoff.py`, `models.py`, `security.py` | the upstream's `config.py`, `ollama.py`, `languagetool.py`, `uploads.py`, **plus** `handoff.py` and `security.py` from the platform |
| `dataanalyzer/backend/app/tabs/` | `document_assistant/` (the platform's own) | the upstream's `document_assistant/` and `circular_analyzer/` |
| `dataanalyzer/backend/app/analysis/` | `figures.py`, `plots.py`, `query.py`, `tables.py`, `understanding.py` | gone — the upstream's data chat replaces it |
| `dataanalyzer/backend/app/llm/` | `client.py`, `models.py` | gone — the upstream's `core/ollama.py` talks to the model, and the model is chosen by `scripts/make_env.py` |
| `dataanalyzer/backend/app/api/` | `auth.py`, `documents.py` | `handoff.py` (the hub's bridge) |
| `dataanalyzer/backend/app/main.py` | the platform's | the upstream's, plus the session guard, the frame headers and the static mount |
| `dataanalyzer/frontend/src/` | the platform's own | the upstream's React application, plus a bridge client |
| `dataanalyzer/backend/data/` | `analyzer.db`, `plots/`, `uploads/` | `uploads/` only — the upstream's file store; there is no database |

The upstream's own `app/tabs/document_assistant/CLAUDE.md` is kept as it is.

## 3. The layout

```
dataanalyzer/
  .env                      written by scripts/make_env.py
  .env.example              the same keys, with the defaults
  README.md                 rewritten for the upstream's application
  backend/
    pyproject.toml          the upstream's dependencies; requires-python relaxed to >=3.11
    app/
      core/
        config.py            the upstream's dataclass, extended with the hub's settings
        ollama.py            the upstream's client (local hosts only)
        languagetool.py      the upstream's client (optional)
        uploads.py           the upstream's
        security.py          NEW — the token this app issues and checks
        handoff.py           NEW — single-use tickets, signed with the shared secret
      tabs/
        document_assistant/  the upstream's, unchanged
        circular_analyzer/   the upstream's stub, unchanged
      api/
        handoff.py           NEW — /api/auth/handoff, /api/auth/exchange, /api/ui/manifest
      main.py                the upstream's, extended
    tests/                   the upstream's tests, plus tests for the handoff
  frontend/
    src/                     the upstream's application, plus src/lib/hub.ts
    package.json             the upstream's, with the toolchain downgraded (see §5)
```

The backend keeps the upstream's own package name `app`. It lives in its own directory with
its own virtual environment, so there is no clash with the hub's `backend/app/`.

## 4. The sign-in

The upstream has **no authentication at all**: any browser that can reach the port can read
and delete documents. The hub's sign-in is therefore not an addition to the upstream, it is
the only thing standing between the app and an open port.

The shape is the one the sentinel already uses, so there is one pattern in the platform:

1. The browser asks the hub for a **ticket** for the analyzer. The hub's server asks the
   analyzer's server for it, server to server, with the shared secret in
   `X-Handoff-Secret`. A browser can never ask for a ticket.
2. The hub hands the ticket to the frame over the message bridge. The ticket is never in a
   URL.
3. The frame swaps the ticket for the analyzer's **own token** (`POST /api/auth/exchange`).
   The ticket is single use and short lived; a spent ticket is refused.
4. The frame sends that token as `Authorization: Bearer …` on every call.

### The role

The role a person holds in the **News Feed** (`role_news`) is the role in the Data Analyzer.
The hub decides who may open the app; the app enforces what that role may do.

- `admin` — everything a `user` may do, **and** may delete a document and its files.
- `user` — may extract, summarise, rewrite, proofread, export, chat over a spreadsheet and
  download the results.

The hub states the role; the app does not invent one. A request that arrives without a
role, or with a role outside `admin`/`user`, is refused. Unlike the Data Summarizer, the
Data Analyzer keeps **no accounts of its own**: there is no local users table, no
password, and no second sign-in. The identity and the role travel in the token.

### The endpoints

| Method | Path | Who | What |
| --- | --- | --- | --- |
| `POST` | `/api/auth/handoff` | the hub's server, with `X-Handoff-Secret` | issues a single-use ticket for a person the hub has already signed in |
| `POST` | `/api/auth/exchange` | the browser, with a ticket | swaps the ticket for a token |
| `GET` | `/api/auth/me` | the browser, with a token | who am I and what may I do |
| `GET` | `/api/ui/manifest` | anybody | the names of the screens, so the hub can draw its rail |
| `GET` | `/api/health`, `/health` | anybody | is the app up, is Ollama reachable, is LanguageTool reachable |
| `POST` | `/api/document-assistant/extract`, `/summarize`, `/rewrite`, `/proofread`, `/proofread/apply`, `/export`, `/data/ask` | the browser, with a token | the upstream's work |
| `GET` | `/api/document-assistant/download/{file_id}` | the browser, with a token | the upstream's download |
| `DELETE` | `/api/document-assistant/files/{file_id}` | the browser, with a token, **`admin` only** | the upstream's delete |

`/api/health` stays open: the doctor and the app's own header read it. It reveals the
model name and whether the two local services are reachable — the same facts the app
already shows on its own screen.

### The manifest

The upstream's three tabs become the hub's rail entries:

```json
{
  "service": "data-analyzer",
  "title": "Data Analyzer",
  "defaultSection": "document-assistant",
  "sections": [
    {"id": "document-assistant", "title": "Document Assistant", "icon": "📄", "path": "/#/document-assistant"},
    {"id": "circular-analyzer", "title": "Circular Analyzer", "icon": "🔔", "path": "/#/circular-analyzer"},
    {"id": "coming-soon", "title": "Coming Soon", "icon": "✨", "path": "/#/coming-soon"}
  ]
}
```

The paths carry the hash because the upstream keeps its tab in the hash.

## 5. The frontend

The upstream's React application is kept as it is: its three tabs, its PNB header, its
panels, its Tailwind theme (maroon `#A6192E`, gold `#F2A900`). Three changes:

**The toolchain is downgraded** so the app builds on the same Node as the rest of the
platform (Node 18.19.1 is the floor the platform supports):

| Package | Upstream | Platform |
| --- | --- | --- |
| `vite` | `^8.3.4` | `^6.4.6` |
| `@vitejs/plugin-react` | `^6.1.2` | `^4.7.0` |
| `tailwindcss`, `@tailwindcss/vite` | `^4.3.3` | `~4.1.11` |
| `typescript` | `^7.0.2` | `^5.9.3` |
| `react`, `react-dom` | `^19.3.0` | unchanged |

The application's own code is plain React and TypeScript and needs no change for this.

**A bridge client** is added at `src/lib/hub.ts`, a port of the sentinel's: it asks the hub
for a ticket, swaps it for a token, keeps the token, and reports the current route so the
hub's rail stays in step. The app has no sign-in page of its own; without a ticket from the
hub it shows "open this from the dashboard" and nothing else.

**The API calls carry the token.** The upstream's `src/tabs/document_assistant/api.ts` sends
no headers today; every call gains the `Authorization` header, and a `401` is turned into
the message "your session has expired, open the service again from the dashboard".

**The built interface is served from the app's own origin** (port 8095), exactly as the
sentinel does it: the backend mounts `frontend/dist`, so there is one address to allow in
the frame headers and one address to put in the hub's settings. In development the Vite
proxy points at the app's own port.

## 6. The settings

`dataanalyzer/.env` is written by `scripts/make_env.py`, from `dataanalyzer/.env.example`:

| Key | Meaning | Default |
| --- | --- | --- |
| `PORT` | the app's port | `8095` |
| `JWT_SECRET` | the app's own signing key for its tokens | generated |
| `HANDOFF_SECRET` | the secret the hub and this app share | generated, mirrored to the hub's `ANALYZER_HANDOFF_SECRET` |
| `HANDOFF_TICKET_SECONDS` | how long a ticket lives | `120` |
| `FRAME_ANCESTORS` | who may frame the app | the hub's origin |
| `EMBED_PARENT_ORIGINS` | who may drive it over the message bridge | the hub's origin |
| `CORS_ORIGINS` | who may call it from a browser | the hub's origin |
| `OLLAMA_URL` | the local model server | `http://localhost:11434` |
| `OLLAMA_MODEL` | the model to use | **the best model that is actually installed** |
| `OLLAMA_NUM_CTX` | the context window | `32768` |
| `LANGUAGETOOL_URL` | the optional LanguageTool server | `http://localhost:8120` |
| `LANGUAGETOOL_LANGUAGE` | the language it checks | `en-GB` |
| `MAX_UPLOAD_MB` | the largest upload | `20` |
| `DATA_DIR` | where uploads are kept | `backend/data` |

The upstream's default model is `gpt-oss:20b`. That default is replaced: the setup writes
the best model the machine has, chosen the same way as everywhere else in the platform
(newest family first, larger model within the family, never an embedding model). The
upstream's `OLLAMA_URL` is honoured, so the app talks to the same model server as the rest
of the platform.

The upstream's `config.py` reads the environment directly and has no `.env` file of its
own; `python-dotenv` is added and `dataanalyzer/.env` is read at start-up. The **first**
occurrence wins, matching the rest of the platform.

## 7. The platform wiring

The hub, the landing page and the tooling already know about the analyzer. What changes:

- **`backend/app/api/integrations.py`** — the analyzer router keeps `POST
  /api/services/analyzer/ticket` and `GET /api/services/analyzer/manifest`. The manifest
  proxy returns the app's own manifest, so the hub's rail is drawn by the app.
- **`backend/app/config/settings.py`** — `analyzer_app_url` and `analyzer_handoff_secret`,
  as they are.
- **`landing/src/services.js`** — the card stays: **Data Analyzer**, live, a ticket
  session, and the News Feed's roles.
- **`landing/src/api/dataanalyzer.js`** — stays as it is.
- **`scripts/make_env.py`** — writes the settings above, including the port (moved if the
  machine has taken 8095) and the model that is really installed.
- **`setup.sh` / `setup.ps1`** — a step for the analyzer: its virtual environment, its
  dependencies and its frontend build. A failure there is reported and the rest of the
  setup continues.
- **`run.sh` / `run.ps1`** — start the analyzer on its port, and wait for `/api/health`.
- **`scripts/doctor.py`** — check the analyzer's settings, its virtual environment, its
  port and its health.
- **`.vscode/tasks.json` and `.vscode/launch.json`** — entries for the analyzer.

## 8. When something is not there

The app must be useful on a machine that has no model server, no LanguageTool and no
Docker, and it must say what is wrong in words rather than failing silently.

| Missing | What happens |
| --- | --- |
| **Ollama** | the app starts and `/api/health` reports `ollama.reachable: false`; the calls that need the model answer with "the local model is not running" |
| **LanguageTool** | the app starts; the proofread stream says "the grammar check needs LanguageTool, which is not running" and the rest of the app is unaffected; `/api/health` reports `languagetool.reachable: false` |
| **A model that is not installed** | the app starts; the call answers with the model that is missing and what is installed instead |
| **The hub** | the frame shows "open this from the dashboard" |

The upstream's own error handling is kept where it already exists (the proofread stream
already catches `LanguageToolError`); the platform adds the wording above where the
upstream has nothing to say.

## 9. Testing

- **The upstream's tests are kept** — `tests/test_health.py`, `test_languagetool.py`,
  `test_ollama.py`, `test_uploads.py` and the twenty-odd tests under
  `tests/document_assistant/`. They must pass unchanged, apart from the fixtures that
  now need a session.
- **New: the handoff.** A ticket is single use; a ticket signed with the wrong secret is
  refused; the exchange refuses a spent ticket; the role is the one the hub stated; a
  request with no role is refused; `DELETE /api/files/{file_id}` is refused for a `user`
  and allowed for an `admin`; every document route is refused without a token.
- **New: the landing E2E** — `landing/e2e/analyzer.mjs`. Sign in as an analyst, open the
  Data Analyzer, check the rail shows the three screens, check the role reaches the app,
  check a `user` cannot delete and an `admin` can, sign out and check the app is closed.
- **Everything else stays green** — the hub's backend, the benchmarking app, the sentinel,
  the landing page, the news app, and the E2E scripts that already exist.

## 10. The documentation

- `dataanalyzer/README.md` — rewritten: what the tool does, the three tabs, the settings,
  how to run it on its own, how it is signed in from the hub, and what LanguageTool is
  for.
- `docs/SETUP.md` — the five services, the Data Analyzer's row, its settings and its
  troubleshooting.
- `docs/integration.md` § 3.8 — the Data Analyzer in the workspace, with the diagram.
- `README.md` — the platform's overview, now including the Data Analyzer.

## 11. Not in scope

- **A Circular Analyzer that works.** The upstream's tab is a placeholder and stays one.
- **A LanguageTool that the platform installs.** The setup points at it and explains how
  to start it; it does not run Docker.
- **The Data Summarizer's own accounts.** The Data Analyzer has no accounts either: the
  hub's role is the app's role.
- **Changing the hub's other four services.**
- **Pushing to GitHub.** The work is committed locally and delivered as an archive, as
  with everything else in this platform.
