# 🏦 Bank News AI

An AI-powered banking news aggregation platform that collects news from multiple Indian business publications, stores it locally, generates executive summaries using local LLMs (Ollama), and serves the results through a FastAPI backend and React dashboard.

---

# Features

- Multi-source news scraping
- Incremental article ingestion
- SQLite database
- AI-powered executive summaries
- Local LLM support (Ollama)
- Provider abstraction (OpenAI/Azure OpenAI ready)
- REST APIs with FastAPI
- React dashboard
- JWT authentication with role based access
- Landing page hub with single sign-on into embedded services
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

---

# Architecture

```

News Sources
│
▼
Scrapers
│
▼
SQLite Database
│
├─────────────┐
▼             ▼
AI            Search
Processing    Embeddings
│
▼
FastAPI
│
▼
React Dashboard
│
│  session handed over
▼
Landing Page Hub

```

---

# Setup

## Clone

```bash
git clone https://github.com/Aditya--Singh/bank-news-ai.git

cd bank-news-ai/backend
```

---

## Install uv

Windows

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify

```bash
uv --version
```

---

## Install Dependencies

```bash
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

---

# Environment Variables

Create a `.env` file inside the backend directory.

```bash
cd backend
cp .env.example .env
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
example `Admin` / `Admin@news26`. The news dashboard opens inside the
workspace and is already signed in.

Seed the users once with:

```bash
cd ../backend
python seed_users.py
```

See [docs/integration.md](docs/integration.md) for the full description
of how the two applications share a session.

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

In Progress

- Ollama integration
- Executive summaries

Planned

- SQL Genie, Data Summarizer and Peer Benchmarking services
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