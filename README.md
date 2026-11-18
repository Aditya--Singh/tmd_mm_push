# 🏦 Top Management Decision Support Platform

An AI-powered banking intelligence platform. A landing page hub owns the
sign-in and opens four services inside it: the news dashboard, which
collects news from Indian business publications and summarises it with a
local language model; Peer Benchmarking, which compares PNB with its
peers quarter by quarter from the banks' own published figures; and the
Data Summarizer, which reads the circulars and the notifications of the
Reserve Bank of India and writes their summaries.

One sign-in opens all of them, with the role the person holds in each.

---

# Features

- Landing page hub with single sign-on into every service it hosts
- Multi-source news scraping
- Incremental article ingestion
- SQLite database
- AI-powered executive summaries
- Local LLM support (Ollama)
- Provider abstraction (OpenAI/Azure OpenAI ready)
- REST APIs with FastAPI
- React dashboard
- Peer benchmarking of PNB against SBI, BoB, Canara Bank and Union Bank
- JWT authentication with role based access
- Four roles across the platform: administrator, analyst, approver and general manager
- Semantic search (planned)
- Executive insights & analytics (planned)

---

# News Sources

Current

- ✅ PSU Connect

Planned

- Business Standard
- Economic Times
- ET BFSI
- BusinessLine
- ANI
- Zee Business
- News18 Business

---

# Technology Stack

## Backend

- Python 3.11+
- FastAPI
- SQLAlchemy
- Pydantic
- BeautifulSoup
- Loguru
- APScheduler

## AI

- Ollama
- Qwen 3
- LangChain

## Frontend

- React
- Vite
- Material UI

The web applications are built with Node.js 18 or newer. The versions
that are used are written down in the lock files, so every machine ends
up with the same ones.

## Database

- SQLite

---

# Project Structure

backend/
```
app/
├── api/
├── config/
├── database/
├── llm/
│ ├── providers/
│ └── prompts/
├── models/
├── repositories/
├── schemas/
├── scrapers/
├── services/
└── utils/

run_scraper.py
seed_users.py
seed/
└── users.csv            the account sheet: names, passwords, the two roles
pyproject.toml
uv.lock

```

frontend/
```
src/
├── api/
├── components/
├── config/
├── pages/
├── session/        # frame session bridge
public/

```

landing/
```
src/
├── api/
├── components/
├── config/
├── pages/
├── session/        # hub frame bridge
├── styles/
public/

```

benchmarking/
```
kpibench/           # FastAPI, its own database and audit trail
├── agents/
├── api/
├── extraction/
├── scraper/
├── services/
static/             # the screens, served without a build step
docs/               # its own installation and integration guides
```

---

# Architecture

```

                       ┌──────────────────────────┐
                       │   Landing Page Hub       │
                       │   owns the sign-in       │
                       └────────────┬─────────────┘
                                    │ one session
             ┌──────────────────────┼──────────────────────┐
             ▼                      ▼                      ▼
      News Dashboard        Peer Benchmarking       Data Summarizer
      (frontend/)           (benchmarking/)        (sentinel/)
             │                      │                      │
             ▼                      ▼                      ▼
        FastAPI               its own FastAPI,      its own FastAPI,
      (backend/)              its own database       its own database
             │                      ▲                      ▲
             │  one users table,    │ a single-use sign-in │
             │  one role per        │ ticket, server to    │
             │  application         │ server               │
             └──────────────────────┴──────────────────────┘
```

The Data Summarizer is the Regulatory Sentinel application, brought in from
<https://github.com/Aditya--Singh/regulatory-sentinel>. It keeps its own accounts, so
the hub states who the person is and the application decides what they may do there.

## The roles

A person holds one role in each application, and the two are kept apart because the
applications do different work. Both are held once, in the `users` table of the backend:

| Column | The role in | May be |
|---|---|---|
| `role_news` | the News Feed | `admin`, `user` |
| `role_bench` | Peer Benchmarking | `admin`, `maker`, `checker`, `viewer`, `user` |

Each application is given the role that belongs to it, server side, so a browser can never
choose its own role. The News Feed shows its summary, its insights and its pipeline control
to an `admin` only; Peer Benchmarking decides for itself what a `maker`, a `checker`, a
`viewer` or a `user` may do there.

The accounts, their passwords and their two roles are held in `backend/seed/users.csv`,
which is the account sheet of the platform. The password in the sheet is the password of the
account; it is hashed before it is stored, so the database only ever holds the hash.

| Account | Password | News Feed | Peer Benchmarking |
|---|---|---|---|
| `admin` | `admin@tmd26` | Administrator | Administrator |
| `analyst` | `Pnb@12345` | Reader | Analyst (Maker) |
| `approver` | `Pnb@12345` | Reader | Approver (Checker) |
| `gm` | `Pnb@12345` | Reader | Top Management (Viewer) |
| `aditya`, `hemant`, `nikhil`, `deepak`, `vijay`, `vikas`, `pankaj` | `<name>@news26` | Reader | Reader |

---

# Setup

## Clone

```bash
git clone https://github.com/Aditya--Singh/top-management-dashboard.git
cd top-management-dashboard
```

## The quick way

On Linux or macOS:

```bash
./setup.sh
./run.sh
```

On Windows:

```powershell
.\setup.ps1
.\run.ps1
```

The setup script installs everything, writes `backend/.env`,
`benchmarking/.env` and `sentinel/.env` with the secrets the servers
share, points the applications at the language model on the machine, and
creates the demo accounts. Then open <http://localhost:5174> and sign in
with `admin` / `admin@tmd26`.

It also works out the machine as it is: a port that is already taken —
by a model server, for instance — is moved and every file that names it
is written again, and the model that is really installed on the machine
is written into the settings. Nothing is downloaded behind your back.

**[docs/SETUP.md](docs/SETUP.md) has the full instructions for both
operating systems**, including what to do when a package will not
download and how to fix a port that is already in use.

To check that everything is in place, at any time:

```bash
python scripts/doctor.py
```

It looks at the settings, the accounts and the five services, and says
what is missing and the command that fixes it. What the backend said the
last time it ran is kept in `backend/logs/backend.log`.

A machine with an application control policy (AppLocker, WDAC, Smart App
Control) can refuse the compiled parts of a library. The platform uses
the plain Python parts of those libraries instead, and says so in the
record.

## The step by step way

### Install uv

Windows

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify

```bash
uv --version
```

### Install the backend

```bash
cd backend
uv sync
```

Activate

Windows

```powershell
.venv\Scripts\activate
```

Linux / macOS

```bash
source .venv/bin/activate
```

### Install Peer Benchmarking

```bash
cd benchmarking
python -m venv .venv
source .venv/bin/activate       # .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Install the Data Summarizer

```bash
cd sentinel
python -m venv .venv
source .venv/bin/activate       # .venv\Scripts\activate on Windows
pip install -r backend/requirements-dev.txt
cd frontend && npm install && npm run build && cd ..
```

### Install the two web applications

```bash
cd frontend && npm install
cd ../landing && npm install
```

### Write the settings files

```bash
cd ..
python scripts/make_env.py
```

This writes `backend/.env`, `benchmarking/.env` and `sentinel/.env`,
including the secrets the servers share, so that one sign-in opens all
of them.

---

# Environment Variables

The setup script writes both settings files for you:

```bash
python scripts/make_env.py
```

It gives the backend a signing key, gives Peer Benchmarking one of its
own, and writes **one secret into both files**, which is what lets a
single sign-in open both applications. It is safe to run again: existing
values are kept.

To do it by hand, copy the examples and fill in the blanks.

```bash
cp backend/.env.example backend/.env
cp benchmarking/.env.example benchmarking/.env
```

`JWT_SECRET_KEY` is required and has no default. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The backend stops with a readable message instead of a traceback when
the key is missing. A `.env` in the repository root is read as a
fallback, so either location works.

```text
DATABASE_URL=sqlite:///news.db

OLLAMA_BASE_URL=http://localhost:11434

OLLAMA_MODEL=qwen3:8b

TIMEZONE=Asia/Kolkata

# The oldest day the news may reach, whatever window is asked for
NEWS_CUTOFF_DATE=2026-06-20

JWT_SECRET_KEY=<generated>

PORT=8000

KPI_APP_URL=http://127.0.0.1:8077

KPI_HANDOFF_SECRET=<the same value as HANDOFF_SECRET in benchmarking/.env>

SENTINEL_APP_URL=http://127.0.0.1:8090

SENTINEL_HANDOFF_SECRET=<the same value as HANDOFF_SECRET in sentinel/.env>
```

The backend of the hub listens on the port in `backend/.env` (`PORT`).
When that port is taken on the machine — by a model server, for
instance — give it another one and run `python scripts/make_env.py`
again: the setup script tells the two web applications about the new
port, so the sign-in keeps working.

The news pipeline is told how far back the news may reach when it is
started, from the dropdown beside the button in the News Feed. The
window may be as long as 90 days, and the date it starts at is shown
under the button.

Peer Benchmarking chooses its model by itself: `OLLAMA_MODEL=auto`, the
default, means the best model that is installed on the machine is used.
`python -m kpibench.cli models` from the `benchmarking` folder says what
is installed and what will be used.

The Data Summarizer chooses its model the same way: `LLM_MODEL=auto`, the
default, means the best model that is installed on the machine is used.
`python -c "from app.llm.models import resolve; print(resolve())"` from
the `sentinel/backend` folder says what will be used.

The frontend applications read their own `.env` files, which are optional
in development because sensible defaults are built in. See
[docs/integration.md](docs/integration.md) for the full list.

---

# Run Backend

```bash
uvicorn app.main:app --reload
```

---

# Run Scraper

```bash
python run_scraper.py
```

---

# Run News Frontend

```bash
cd ../frontend

npm install

npm run dev
```

---

# Run Landing Page

The landing page is a separate application that hosts the intelligence
services and owns authentication.

```bash
cd ../landing

npm install

npm run dev
```

Open <http://localhost:5174> and sign in with a seeded account, for
example `admin` / `admin@tmd26`. The news dashboard and Peer
Benchmarking both open inside the workspace, already signed in, each with
the role the person holds in it.

Seed the users once with:

```bash
cd ../backend
python seed_users.py
```

---

# Run Peer Benchmarking

```bash
cd benchmarking

.venv/bin/python -m kpibench.main      # .venv\\Scripts\\python.exe on Windows
```

It listens on <http://localhost:8077>. Opened on its own it signs in with
its own accounts (`admin`, `analyst`, `approver`, `gm`); opened from the
hub it is signed in with the account of the person who signed in there.

# Run the Data Summarizer

```bash
cd sentinel/backend

../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

It listens on <http://localhost:8090> and serves its own interface from
that address. Opened on its own it signs in with its own administrator;
opened from the hub it is signed in as the person who signed in there.

See [docs/integration.md](docs/integration.md) for the full description
of how the applications share a session.

---

# Run in Visual Studio Code

The repository ships with a VS Code configuration for all four
services.

```text
Ctrl+Shift+P  ->  Tasks: Run Task  ->  Setup: everything
Ctrl+Shift+P  ->  Tasks: Run Task  ->  Dev: all services
```

The second command starts the backend, the news dashboard and the
landing page in separate terminals. `F5` offers a configuration that
starts everything and opens the landing page in Chrome with the Python
debugger attached to the backend.

See [docs/vscode.md](docs/vscode.md) for the details.

---

# Development Workflow

Create a feature branch

```bash
git checkout -b feature/feature-name
```

Commit

```bash
git add .

git commit -m "feat: description"
```

Push

```bash
git push origin feature/feature-name
```

---

# Git Branches

```
main

feature/*
bugfix/*
release/*
```

---

# Current Status

Completed

- FastAPI project
- SQLite database
- SQLAlchemy models
- Repository layer
- Service layer
- Pydantic schemas
- PSU Connect scraper
- Pagination
- Duplicate detection
- IST timezone support
- JWT authentication with a role per application: `role_news` and `role_bench`
- Landing page hub with single sign-on into the embedded dashboard
- Peer benchmarking of PNB against SBI, BoB, Canara Bank and Union Bank
- One sign-in across the hub, the news dashboard, Peer Benchmarking, the Data Summarizer and the Data Analyzer
- One role per application, held in the users table: `role_news` for the News Feed and
  `role_bench` for Peer Benchmarking
- One rail that drives every service, including the screens of Peer Benchmarking
- The SQL Genie opened in the workspace, with its address set in `landing/.env`
- The Data Analyzer: the documents a person shares are read, summarised, drawn and asked about

In Progress

- Ollama integration
- Executive summaries

Planned

- Semantic search
- Multi-source scraping
- Scheduler
- Analytics

---

# Roadmap

## Phase 1

- PSU Connect scraper
- Database
- AI summaries

## Phase 2

- React dashboard
- Remaining news sources

## Phase 3

- Embeddings
- RAG
- Executive analytics

---

# License

MIT License

---

# Author

Aditya Singh