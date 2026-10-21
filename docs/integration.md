# Bank News AI — Landing Page Integration

## 1. Purpose

This document describes how the landing page (the hub) and the news
application fit together, and how a single sign-on is carried from one to
the other.

The hub is a separate application in `landing/`. It owns authentication
and hosts the intelligence services. The news application in `frontend/`
keeps working on its own: opened directly, it still shows its own sign-in
screen and still talks to the same backend.

## 2. Components

```text
                +-----------------------------+
                |  Landing page (landing/)    |
                |  port 5174 in development   |
                |                             |
                |  owns authentication        |
                |  hosts the service list     |
                +--------------+--------------+
                               |
              session handed  |  over postMessage
              over a frame    |
                               v
                +-----------------------------+
                |  News app (frontend/)       |
                |  port 5173 in development   |
                |                             |
                |  renders inside the frame  |
                +--------------+--------------+
                               |
                               v
                +-----------------------------+
                |  FastAPI (backend/)         |
                |  port 8000                  |
                |                             |
                |  one users table            |
                |  one token issuer           |
                +-----------------------------+
```

There is a single identity system. The hub calls the same
`POST /api/auth/login` endpoint against the same `users` table as the
news application, and receives the same access token. No second user
store and no second sign-in exists.

## 3. How the session reaches the frame

The hub and the news application are normally served from different
origins, and `localStorage` is partitioned by origin. A session
established in the hub is therefore not visible to the frame, which would
force the user to sign in twice.

The session is handed over explicitly instead:

```text
child -> parent : { type: "newsint:ready" }
parent -> child : { type: "newsint:auth", payload: { username, role, accessToken } }
parent -> child : { type: "newsint:logout" }
child -> parent : { type: "newsint:logout-ack" }
child -> parent : { type: "newsint:logout" }
```

1. The frame boots and posts `newsint:ready` to its parent.
2. The hub replies with `newsint:auth` carrying the access token.
3. The frame validates the message, stores the session under
   `bankNewsUser` and renders the dashboard. No sign-in screen is shown.

The hub also pushes the session when the frame finishes loading, so the
handover succeeds regardless of which message arrives first.

### 3.1 The same-origin shortcut

When both applications are served from one origin, the frame can see the
hub's session in the shared `localStorage` and adopts it directly, with
no message exchange at all. The frame prefers, in order:

1. a session in its own storage,
2. the hub's session in shared storage (same-origin deployments),
3. a session obtained from the parent over `postMessage`.

The bridge therefore behaves correctly in both deployment shapes without
any special configuration.

### 3.2 Security rules

- Every inbound message is checked against an explicit origin allowlist.
- Every inbound message is checked against the expected source window.
- Outbound messages are always addressed to a specific origin. The
  wildcard `"*"` is never used.
- A frame served from the same origin is trusted without an entry in the
  allowlist, because it already shares the storage and script context.
- The access token is never placed in a URL. URLs leak into browser
  history, server logs and `Referer` headers.
- The frame is not sandboxed, because it is a first-party application
  that needs its own storage and script context. If third-party services
  are embedded later, give them their own origin and their own
  allowlist entry.

## 4. Signing out

Signing out is propagated in both directions, so the two shells never
disagree:

| Action | Effect |
|---|---|
| Logout in the hub | The hub asks the frame to sign out, waits for the confirmation, then clears its own session and removes the frame. |
| Logout in the frame | The frame clears its session, tells the hub, and the hub returns to the sign-in screen. |
| Token rejected with 401 | The API client clears the session and fires `auth-expired`. The frame relays that to the hub and both return to the sign-in screen. |

### 4.1 Why the sign-out is confirmed

The frame usually runs on a different origin, so it keeps its own copy of
the session. That copy has to be cleared too, otherwise the dashboard
stays signed in when it is opened directly.

The hub cannot simply remove the frame: a message that is still in
flight is discarded together with the frame, and the frame would keep
its session. The sign-out is therefore confirmed:

1. The hub sends `newsint:logout` and repeats it until the frame
   answers, because a frame that is still starting up has not attached
   its message listener yet and would not receive the first request.
2. The frame clears its session and answers with `newsint:logout-ack`.
3. Only then does the hub clear its own session and remove the frame.

If the frame never answers, the hub clears the session anyway after a
short delay, so signing out can never get stuck.

### 4.2 Why a sign-out cannot be undone by a late handshake

The frame answers every `newsint:ready` with the session. A handshake
that was already in flight could therefore arrive after a sign-out and
revive the session.

Two rules prevent this:

- The hub stops handing over the session as soon as it asks the frame
  to sign out. It only resumes when a new session is set.
- The frame records the token it just revoked and ignores an
  authentication message that carries the same token. A genuinely new
  sign-in has a different token and is accepted.

## 5. Running it locally

Four terminals, or three if the seeded database already exists.

### Terminal 1 — backend

```bash
cd backend
uv sync --all-groups
cp .env.example .env       # then set JWT_SECRET_KEY
.venv/bin/python seed_users.py
.venv/bin/python -m uvicorn app.main:app --reload
```

### Terminal 2 — news application

```bash
cd frontend
npm install
npm run dev                # http://localhost:5173
```

### Terminal 3 — landing page

```bash
cd landing
npm install
npm run dev                # http://localhost:5174
```

Open <http://localhost:5174> and sign in with a seeded account, for
example `Admin` / `Admin@news26`.

The news application is still reachable on its own at
<http://localhost:5173>, where it signs in separately. This is
intentional: it keeps the news application independently usable.

## 6. Configuration

### Backend

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///news.db` | Database connection. |
| `JWT_SECRET_KEY` | none, required | Signing key for access tokens. |
| `JWT_ALGORITHM` | `HS256` | Token algorithm. |
| `JWT_EXPIRATION_MINUTES` | `480` | Token lifetime. |
| `CORS_ORIGINS` | the development origins | Comma-separated list of browser origins allowed to call the API. |

### Landing page (`landing/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Base URL of the API. Empty keeps the browser on the current origin, which is what the development proxy and a reverse proxy expect. |
| `VITE_NEWS_APP_URL` | `http://localhost:5173/` | URL of the news application opened in the workspace. |
| `VITE_ALLOWED_CHILD_ORIGINS` | the development origins | Origins the hub accepts session messages from. |

### News application (`frontend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Base URL of the API, same rule as above. |
| `VITE_ALLOWED_PARENT_ORIGINS` | the development origins | Origins the application accepts session messages from. |

Both defaults cover the development setup, so the integration works
without any configuration file. A configuration file is needed only when
the origins differ from the defaults.

## 7. Deployment layout

The expected production arrangement serves everything from one origin:

```text
https://newsintel.pnbbank.in/          landing page
https://newsintel.pnbbank.in/news/     news application
https://newsintel.pnbbank.in/api/      FastAPI
```

The news application must be built with a base path so that its assets
resolve under `/news/`:

```bash
cd frontend
VITE_BASE_PATH=/news/ npm run build
```

The landing page is built normally:

```bash
cd landing
npm run build
```

Because both are then served from one origin, the frame adopts the
session from shared storage and the `postMessage` handover is not
needed, although it remains available as a fallback.

## 8. Tests

```bash
cd backend  && .venv/bin/python -m pytest      # authentication endpoints
cd frontend && npm test                        # frame session bridge
cd landing  && npm test                        # hub frame bridge
```

### End to end

An end-to-end check drives a real browser through the whole flow. It
needs Playwright and a running backend:

```bash
npm install --no-save playwright
npx playwright install chromium
node landing/e2e/hub-embedding.mjs
```

The script covers the sign-in, the handover into the frame, the
authorised API call from the frame, the expiry of a session and the
sign-out in both directions.

To exercise the same-origin deployment, build both applications, start
the bundled proxy and point the script at it:

```bash
cd frontend && VITE_BASE_PATH=/news/ npm run build
cd landing  && VITE_NEWS_APP_URL=http://127.0.0.1:5175/news/ npm run build

HUB_DIST=landing/dist NEWS_DIST=frontend/dist PORT=5175 \
    node landing/e2e/same-origin-proxy.mjs

HUB_URL=http://127.0.0.1:5175/ E2E_FRAME_MATCH=/news/ \
    node landing/e2e/hub-embedding.mjs
```

## 9. Adding another service

1. Build the service as its own application with its own sign-in-free
   entry point.
2. Add it to `SERVICES` in `landing/src/services.js` with its URL and
   the roles that may use it.
3. If it runs on a different origin, add that origin to
   `VITE_ALLOWED_CHILD_ORIGINS` on the hub and to
   `VITE_ALLOWED_PARENT_ORIGINS` on the service.
4. Implement the same five messages in the service so that the hub can
   hand over the session. The implementation in
   `frontend/src/session/parentSession.js` can be copied as a starting
   point.
