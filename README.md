# 🏦 Top Management Decision Support Platform

An AI-powered banking intelligence platform. A landing page hub owns the
sign-in and opens three services inside it: the news dashboard, which
collects news from Indian business publications and summarises it with a
local language model, and Peer Benchmarking, which compares PNB with its
peers quarter by quarter from the banks' own published figures.

One sign-in opens all of them, with the same role.

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
      News Dashboard        Peer Benchmarking       SQL Genie
      (frontend/)           (benchmarking/)        (planned)
             │                      │
             ▼                      ▼
        FastAPI               its own FastAPI,
      (backend/)              its own database
             │                      ▲
             │  one users table,    │ a single-use sign-in
             │  one role per        │ ticket, server to server
             └──────────────────────┘
```

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

The setup script installs everything, writes `backend/.env` and
`benchmarking/.env` with the secret the two servers share, and creates
the demo accounts. Then open <http://localhost:5174> and sign in with
`Admin` / `Admin@news26`.

**[docs/SETUP.md](docs/SETUP.md) has the full instructions for both
operating systems**, including what to do when a package will not
download and how to fix a port that is already in use.

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

This writes `backend/.env` and `benchmarking/.env`, including the
secret the two servers share, so that one sign-in opens both.

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

NEWS_CUTOFF_DATE=2026-06-20

JWT_SECRET_KEY=<generated>

KPI_APP_URL=http://127.0.0.1:8077

KPI_HANDOFF_SECRET=<the same value as HANDOFF_SECRET in benchmarking/.env>
```

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
example `Admin` / `Admin@news26`. The news dashboard and Peer
Benchmarking both open inside the workspace, already signed in, with the
same role.

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

See [docs/integration.md](docs/integration.md) for the full description
of how the applications share a session.

---

# Run in Visual Studio Code

The repository ships with a VS Code configuration for all three
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
- JWT authentication with admin and user roles
- Landing page hub with single sign-on into the embedded dashboard
- Peer benchmarking of PNB against SBI, BoB, Canara Bank and Union Bank
- One sign-in across the hub, the news dashboard and Peer Benchmarking
- Four roles across the platform: administrator, analyst, approver and general manager
- One rail that drives every service, including the screens of Peer Benchmarking

In Progress

- Ollama integration
- Executive summaries

Planned

- SQL Genie and Data Summarizer services
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