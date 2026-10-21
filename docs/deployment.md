# Bank News AI — Deployment

## 1. Current Status

The application is currently running in a local development environment.

Current components:

```text
Landing Page (React / Vite)
        |
        v
React / Vite  ->  FastAPI  ->  SQLAlchemy  ->  SQLite
```

The landing page hosts the news dashboard in a frame and hands the
session over to it, so a user signs in once.

## 2. Local Backend

The backend is currently served at:

```text
http://127.0.0.1:8000
```

FastAPI provides the API endpoints used by the React frontend.

## 3. Local Frontend

The frontend is implemented with React and Vite.

The development frontend is served by Vite, currently using the standard development setup.

The frontend communicates with the FastAPI backend using Axios.

The landing page is a second React/Vite application in `landing/`, served
on port 5174 during development.

## 4. Current Configuration

The API base URL is read from the environment and defaults to the current
origin, so the browser stays on a single origin:

```javascript
const apiClient = axios.create({
    baseURL: env.VITE_API_BASE_URL || "",
});
```

During development, Vite proxies `/api` to the backend, so no CORS
configuration is needed. Set `VITE_API_BASE_URL` to a full origin to
call the backend directly.

The origins allowed to exchange session messages are configured with
`VITE_ALLOWED_PARENT_ORIGINS` and `VITE_ALLOWED_CHILD_ORIGINS`. Both
default to the development origins.

The allowed CORS origins on the backend are configured with the
`CORS_ORIGINS` environment variable.

## 5. Source Control

The project is maintained in Git.

Current branch:

```text
main
```

The project has a GitHub remote configured.

The current development checkpoint is intended to serve as a baseline before the next feature phase.

## 6. Production Deployment — Planned

Production deployment has not yet been implemented.

The eventual deployment should address:

- Production database
- Backend hosting
- Frontend hosting
- Environment configuration
- Secrets management
- CORS
- HTTPS
- Logging
- Monitoring
- Scheduled scraper jobs
- AI processing jobs
- Database backups

## 7. Reverse Proxy Layout — Planned

The intended production arrangement serves everything from one origin:

```text
https://newsintel.pnbbank.in/          landing page
https://newsintel.pnbbank.in/news/     news dashboard
https://newsintel.pnbbank.in/api/      FastAPI
```

The news dashboard must be built with a base path so that its assets
resolve under `/news/`:

```bash
cd frontend
VITE_BASE_PATH=/news/ npm run build
```

Serving both applications from one origin lets the dashboard adopt the
session from shared storage directly.

## 8. Containerization — Planned

Dockerization has not yet been completed.

A potential production structure is:

```text
+----------------------+
| React frontend       |
+----------+-----------+
           |
           v
+----------------------+
| FastAPI backend      |
+----------+-----------+
           |
     +-----+------+
     |            |
     v            v
 Database     AI pipeline
     ^
     |
 Scraper jobs
```

The final infrastructure and hosting platform have not yet been selected.

## 9. Security

Production security requirements are still pending, including:

- Restricted CORS origins
- Restricted session message origins
- A generated `JWT_SECRET_KEY` per environment
- Secret/API-key management
- Authentication/authorization where required
- HTTPS
- Database access controls
- Logging and audit controls
