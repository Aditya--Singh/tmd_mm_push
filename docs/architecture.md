# Bank News AI — Architecture

## 1. Project Status

**Documentation baseline:** Current Git checkpoint.

### Implemented
- FastAPI backend
- SQLAlchemy data layer
- SQLite development database
- News API with filtering and pagination
- AI analysis integration and persisted AI analysis records
- AI-based sentiment, importance, risk, bank, organization, keyword and topic extraction
- Priority-based news ordering
- React/Vite frontend
- Executive dashboard KPIs and charts
- JWT authentication with admin and user roles
- Landing page hub that hosts the intelligence services
- Single sign-on from the landing page into the embedded dashboard
- News cards with AI analysis
- Pagination with automatic navigation to the first card of the selected page

### In progress / planned
- Responsive UI
- News detail view
- Production deployment
- Scheduled scraper orchestration
- Production database
- Automated testing and production hardening

## 2. High-Level Architecture

```text
                 +----------------------+
                 |   News Sources       |
                 |  Business/Banking    |
                 |      Publications    |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 |   Scraper Layer      |
                 |   (planned/ongoing)  |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 |     News Database    |
                 |       SQLite         |
                 |                      |
                 |       News           |
                 |       AI Analysis    |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 |   AI Analysis Layer  |
                 |  Summary / Risk /    |
                 |  Importance / Topics |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 |     FastAPI API      |
                 | /api/news            |
                 | /api/dashboard/*     |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | React / Vite Frontend|
                 | Executive Dashboard  |
                 +----------------------+
```

## 3. Backend

The backend is implemented using Python and FastAPI.

Primary responsibilities:
- Expose dashboard APIs.
- Expose paginated news APIs.
- Apply news filters.
- Select the latest available AI analysis for an article.
- Prioritize important/risky news.
- Return data in a frontend-friendly JSON structure.

## 4. Frontend

The frontend is implemented using React with Vite.

Current structure:

```text
frontend/src/
├── api/
│   ├── client.js
│   ├── dashboard.js
│   └── news.js
├── components/
│   ├── DashboardStats.jsx
│   ├── DistributionChart.jsx
│   ├── KpiCard.jsx
│   └── NewsCard.jsx
├── pages/
│   └── Dashboard.jsx
├── App.jsx
├── App.css
├── index.css
└── main.jsx
```

The current dashboard consumes the FastAPI backend directly through Axios.

## 5. Landing Page Hub

The landing page in `landing/` is a separate React/Vite application. It
owns authentication and hosts the intelligence services.

```text
                 +----------------------+
                 |   Landing Page Hub   |
                 |  owns authentication |
                 +----------+-----------+
                            |
             session handed | over to the frame
                            v
                 +----------------------+
                 | React / Vite Frontend|
                 | Executive Dashboard  |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 |     FastAPI API      |
                 | /api/news            |
                 | /api/dashboard/*     |
                 | /api/auth/*          |
                 +----------------------+
```

The hub and the dashboard share one identity system: the same users
table, the same `POST /api/auth/login` endpoint and the same access
token. The session is carried into the frame over `postMessage` with an
origin allowlist, or read directly from shared storage when both are
served from one origin.

`docs/integration.md` describes the message contract, the configuration
and the deployment layout in full.

## 6. Current News Prioritization

News is ordered primarily by publication date and then by an AI-derived priority score.

Current priority concept:

| Condition | Score |
|---|---:|
| High Risk + High Importance | 5 |
| High Risk | 4 |
| High Importance | 3 |
| Medium Risk + High Importance | 2 |
| Other | 1 |

Publication date remains the primary ordering dimension.

## 7. Design Principles

- Separate scraping, persistence, AI processing and presentation concerns.
- Keep the React frontend independent from backend implementation details.
- Use API contracts between frontend and backend.
- Keep AI-generated attributes structured rather than embedding them only in free text.
- Make prioritization deterministic and explainable.
- Keep one identity system for the platform rather than one per application.
- Keep the landing page and the services it hosts independently deployable.
