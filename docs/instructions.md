# Bank News AI — Local Setup & Porting Instructions

## 1. Purpose

This document explains how to move the project to another development machine and initialize it locally.

These instructions describe the current development setup. Production deployment is not yet a completed process.

## 2. Prerequisites

Install:

- Git
- Python
- Node.js
- npm

Verify:

```powershell
git --version
python --version
node --version
npm --version
```

Exact versions should eventually be pinned as part of production hardening.

## 3. Clone the Repository

```powershell
cd C:\Users\<username>\Downloads
git clone https://github.com/Aditya--Singh/bank-news-ai.git
cd bank-news-ai
```

Verify:

```powershell
git branch --show-current
git remote -v
```

The main development branch is:

```text
main
```

## 4. Backend Environment

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Verify:

```powershell
python --version
pip --version
```

## 5. Install Backend Dependencies

If `requirements.txt` exists:

```powershell
pip install -r requirements.txt
```

Do not install dependencies manually without updating the project's dependency file.

## 6. Environment Variables

If `.env.example` exists:

```powershell
copy .env.example .env
```

Populate local values as required.

`JWT_SECRET_KEY` is required and has no default, so the backend will not
start without it. It stops with a readable message instead of a
traceback. Generate one:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

A `.env` in the repository root is read as a fallback, so either
location works. The one in `backend/` takes precedence.

Never commit `.env` or secrets to Git.

## 7. Database

The current development setup uses SQLite.

The logical tables are:

```text
news
news_ai_analysis
```

If the development database is intentionally excluded from Git, initialize/populate it using the project's database setup process.

Do not assume SQLite is the final production database.

## 8. Start FastAPI

From `backend` with the virtual environment activated:

```powershell
uvicorn app.main:app --reload
```

Expected local API:

```text
http://127.0.0.1:8000
```

FastAPI documentation:

```text
http://127.0.0.1:8000/docs
```

If the repository uses a different application entry point, use the actual module path present in the codebase.

## 9. Verify Backend

```powershell
curl http://127.0.0.1:8000/api/dashboard/summary
```

Then:

```powershell
curl "http://127.0.0.1:8000/api/news?page=1&page_size=10"
```

The endpoints should return data when the local database has been initialized/populated.

## 10. Frontend Setup

Open a second PowerShell window:

```powershell
cd C:\Users\<username>\Downloads\bank-news-ai\frontend
npm install
```

Do not commit `node_modules`.

## 11. Start React/Vite

```powershell
npm run dev
```

Open the URL shown by Vite, normally similar to:

```text
http://localhost:5173/
```

## 12. The Ports

Six services:

```text
Terminal 1
FastAPI (the backend of the hub)
http://127.0.0.1:8000

Terminal 2
FastAPI (Peer Benchmarking)
http://localhost:8077

Terminal 3
FastAPI (the Data Summarizer)
http://localhost:8090

Terminal 4
FastAPI (the Data Analyzer)
http://localhost:8095

Terminal 5
React/Vite (news dashboard)
http://localhost:5173

Terminal 6
React/Vite (landing page hub)
http://localhost:5174
```

`setup.sh` and `setup.ps1` install all of them, and `run.sh` and
`run.ps1` start them. See [SETUP.md](SETUP.md).

The current Axios client is:

```text
frontend/src/api/client.js
```

Its base URL comes from `VITE_API_BASE_URL` and defaults to the current
origin. During development, Vite proxies `/api` to the backend.

The landing page reads its configuration from `landing/.env`. Both
frontend applications work without a `.env` file in development, because
the defaults cover the standard local setup.

## 13. Verify the Dashboard

Check:

- Total News
- High Importance
- High Risk
- Negative Sentiment
- Sentiment chart
- Importance chart
- Risk chart
- Top Banks
- Top Topics
- News Cards
- Filters
- Pagination

## 14. Test News Filters

```powershell
curl "http://127.0.0.1:8000/api/news?source=PSU%20Connect"
```

```powershell
curl "http://127.0.0.1:8000/api/news?importance=High"
```

```powershell
curl "http://127.0.0.1:8000/api/news?risk_level=High"
```

Combined:

```powershell
curl "http://127.0.0.1:8000/api/news?importance=High&risk_level=High"
```

## 15. Test Pagination

```powershell
curl "http://127.0.0.1:8000/api/news?page=1&page_size=10"
```

Then:

```powershell
curl "http://127.0.0.1:8000/api/news?page=2&page_size=10"
```

In React, page navigation should load the selected page and scroll to the beginning of the News section.

## 16. Git Workflow

Before changes:

```powershell
git status
git pull origin main
```

Review changes:

```powershell
git status
git diff
```

Stage:

```powershell
git add .
```

Review staged changes:

```powershell
git diff --cached --stat
git diff --cached
```

Commit:

```powershell
git commit -m "feat: describe the change"
```

Push:

```powershell
git push
```

## 17. Files That Must Not Be Committed

Ensure these are ignored:

```text
.venv/
venv/
__pycache__/
*.pyc
node_modules/
dist/
.env
*.db
*.sqlite
*.sqlite3
```

Check:

```powershell
git status --short
```

## 18. Windows Line Endings

A warning such as:

```text
LF will be replaced by CRLF
```

is normally a Git line-ending warning, not an application failure.

A `.gitattributes` file can standardize repository files:

```gitattributes
* text=auto
*.py text eol=lf
*.js text eol=lf
*.jsx text eol=lf
*.css text eol=lf
*.json text eol=lf
*.md text eol=lf
```

## 19. Troubleshooting

### React says "Unable to load dashboard data"

First test:

```powershell
curl http://127.0.0.1:8000/api/dashboard/summary
```

Then:

```powershell
curl "http://127.0.0.1:8000/api/news?page=1&page_size=10"
```

If the API returns HTTP 500, investigate the FastAPI terminal first.

### Combined news filters return HTTP 500

Test:

```text
importance
risk_level
importance + risk_level
```

The current implementation uses a single `NewsAIAnalysis` join when AI filters are supplied.

### Dashboard has no data

Check:

1. FastAPI is running.
2. The database is accessible.
3. `/api/dashboard/summary` returns data.
4. `/api/news` returns articles.
5. React uses the correct backend URL.

### CORS error

Check FastAPI CORS configuration and confirm the frontend origin is allowed.

Do not allow every origin in production merely to hide a configuration problem.

## 19a. Run the Landing Page

```powershell
cd bank-news-ai\landing
npm install
npm run dev
```

Then open <http://topmgmtdash.pnbbank.in:5174> and sign in with a seeded account, for
example `admin` / `admin@tmd26`.

Select **News Feed** in the sidebar to open the dashboard inside the
workspace. It is already signed in: the landing page passes the session
to the embedded application.

See `docs/integration.md` for the full description.

## 20. Quick Startup

### Terminal 1

```powershell
cd bank-news-ai\backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

### Terminal 2

```powershell
cd bank-news-ai\frontend
npm install
npm run dev
```

Then open the Vite URL.

### Terminal 3

```powershell
cd bank-news-ai\landing
npm install
npm run dev
```

Then open <http://topmgmtdash.pnbbank.in:5174>.

## 21. First-Time Machine Checklist

```text
[ ] Install Git
[ ] Install Python
[ ] Install Node.js/npm
[ ] Clone repository
[ ] Create Python virtual environment
[ ] Install backend dependencies
[ ] Configure .env if required
[ ] Initialize/restore development database
[ ] Start FastAPI
[ ] Verify /docs
[ ] Verify /api/news
[ ] Verify /api/dashboard/summary
[ ] Run npm install
[ ] Start Vite
[ ] Open React dashboard
[ ] Verify KPIs
[ ] Verify charts
[ ] Verify News Cards
[ ] Verify filters
[ ] Verify pagination
```

## 22. Porting Principle

Do not copy machine-specific environments.

Recreate:

```powershell
python -m venv .venv
pip install -r requirements.txt
```

and:

```powershell
npm install
```

This keeps the new machine reproducible from the Git repository.
