# Bank News AI — Landing Page Integration

## 1. Purpose

This document describes how the landing page (the hub) and the services
it hosts fit together, and how a single sign-on is carried from one to
the other.

The hub is a separate application in `landing/`. It owns authentication
and hosts the intelligence services. Two services live behind it today:

- the news application in `frontend/`, which shares the hub's token,
- Peer Benchmarking in `benchmarking/`, which keeps its own sessions and
  is given a single-use sign-in ticket instead.

Both keep working on their own: opened directly, the news application
still shows its own sign-in screen, and Peer Benchmarking still signs in
with its own accounts.

## 2. Components

```text
                +---------------------------------------------+
                |  Landing page (landing/)                     |
                |  port 5174 in development                    |
                |                                               |
                |  owns authentication                          |
                |  hosts the service list                       |
                +---+----------------------+------------------+
                    |                      |                      |
   session handed   | over postMessage      | a sign-in ticket,   | a sign-in ticket,
   over a frame     v                      v over a frame       v over a frame
                +--------------------+  +--------------------+ +--------------------+
                |  News app          |  |  Peer Benchmarking  | |  Data Summarizer   |
                |  (frontend/)       |  |  (benchmarking/)    | |  (sentinel/)       |
                |  port 5173         |  |  port 8077          | |  port 8090         |
                |                    |  |                      | |                    |
                |  takes the token   |  |  keeps its own      | |  keeps its own     |
                |                    |  |  database and       | |  database and      |
                |                    |  |  sessions            | |  sessions           |
                +---------+----------+  +----------+-----------+ +---------+----------+
                          |                        |                       |
                          v                        |                       |
                +---------------------------------+-----------------------+
                |  FastAPI (backend/)                                   |
                |  port 8000                                            |
                |                                                       |
                |  one users table                                      |
                |  one token issuer                                     |
                |  one role per person                                  |
                +---------------------------------+-----------------------+
                          |                       |                       |
                          | asks for a sign-in ticket,                      |
                          | server to server                               |
                          v                       v                       v
                +--------------------------------+  +---------------------------------------+
                |  Peer Benchmarking (backend)   |  |  Regulatory Sentinel (backend)        |
                |  its own users, sessions, audit |  |  its own users, sessions and audit    |
                +--------------------------------+  +---------------------------------------+
```

There is a single identity system. The hub calls the same
`POST /api/auth/login` endpoint against the same `users` table as the
news application, and receives the same access token. No second user
store and no second sign-in exists.

Peer Benchmarking keeps its own database and its own sessions, because
it has to keep its own audit trail of who approved which figure. It does
not keep its own sign-in: the hub vouches for the person, and the
benchmarking app swaps a single-use ticket for a session of its own.

The Data Summarizer is the Regulatory Sentinel application. It reads the
circulars and the notifications of the Reserve Bank of India and writes
their summaries. It keeps its own accounts, its own sessions and its own
audit trail as well, and the hub vouches for the person in the same way.
Each of the two has a secret of its own with the hub, so that one of
them being leaked does not open the other.

## 3. How the session reaches the frame

The hub and the news application are normally served from different
origins, and `localStorage` is partitioned by origin. A session
established in the hub is therefore not visible to the frame, which would
force the user to sign in twice.

The session is handed over explicitly instead:

```text
child -> parent : { type: "hubint:ready" }
parent -> child : { type: "hubint:auth", payload: { username, roleNews, accessToken } }
parent -> child : { type: "hubint:auth", payload: { username, roleBench, ticket } }
parent -> child : { type: "hubint:navigate", payload: { path } }
parent -> child : { type: "hubint:logout" }
child -> parent : { type: "hubint:logout-ack" }
child -> parent : { type: "hubint:logout" }
child -> parent : { type: "hubint:route", payload: { path } }
```

The names are shared by every service, so a service that is added later
implements one contract rather than one of its own.

1. The frame boots and posts `hubint:ready` to its parent.
2. The hub replies with `hubint:auth`, carrying what that service
   needs: the access token for the news application, a single-use
   sign-in ticket for Peer Benchmarking.
3. The frame validates the message, stores or exchanges what it was
   given, and renders. No sign-in screen is shown.

The hub also pushes the session when the frame finishes loading, so the
handover succeeds regardless of which message arrives first. The reply
to `hubint:ready` is addressed to the origin the frame really has, which
is known for certain at that moment.

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

## 3.3 Who owns which part of the screen

The landing page is the shell, so it owns everything around the
services:

| Element | Owner |
|---|---|
| Platform title and subtitle | Landing page |
| Signed-in user, avatar and greeting | Landing page |
| Give Feedback | Landing page |
| Current date | Landing page |
| Logout | Landing page |
| The service itself | The embedded application |

The embedded application therefore renders no header of its own and
starts straight at its content. Opened directly, without the landing
page, it keeps its own full header, because that is then the only
chrome around it.

Feedback is collected by the landing page and posted to
`POST /api/feedback` with the landing page's own access token. The
signed-in user is taken from the token, so the request body only
carries the ratings.

## 3.4 Theme

Both applications use one palette, so the embedded service and the hub
read as a single product:

| Token | Value | Use |
|---|---|---|
| `--primary` | `#A6192E` | Primary actions, selected states |
| `--primary-deep` | `#4E0C18` | The header band |
| `--primary-50` | `#FBF0F2` | Selected service background |
| `--accent` | `#F2B600` | The rule under the header, the marker on the selected service |
| `--text` | `#1B2130` | Body text |
| `--muted` | `#6E788A` | Secondary text |
| `--border` | `#E2E5EB` | Panel and rail borders |
| `--background` | `#F3F4F7` | The page behind the panels |

Typography is Segoe UI Variable, falling back to Segoe UI and the system
stack. Panels are flat, with a one pixel border and a soft shadow, and
corners are 10px, or 14px for the larger surfaces.

## 3.5 Collapsible service rail

The service rail can be collapsed to an icon column so that the
workspace gets the room. The control sits at the top of the rail, and
the choice is remembered in `localStorage` under
`bankHubSidebarCollapsed`.

When collapsed, the rail is 112px wide, the descriptions are hidden and
each service shows its icon above its name. The selected service keeps
its gold marker. The width is chosen so that every service name and
every screen name still fits on two lines, whatever font the machine
has.

On narrow screens the rail becomes a horizontal strip instead, with the
same items.

## 3.6 Peer Benchmarking in the workspace

Peer Benchmarking cannot take the hub's token: it signs its own
sessions with its own key, keeps its own audit trail, and its access
rules are written against its own role names. The hub therefore vouches
for the person instead of lending it a token.

```text
browser          hub backend      benchmarking backend
   |                 |                    |
   | open the        |                    |
   | service         |                    |
   |---------------->|                    |
   |                 | POST /api/auth/handoff
   |                 |  X-Handoff-Secret  |
   |                 | {username, role_bench} |
   |                 |------------------->|
   |                 |     one-use       |
   |                 |     ticket        |
   |                 |<-------------------|
   | <-- the ticket -|                    |
   |                                     |
   |  hubint:auth { ticket }  over the frame bridge
   |-------------------------------------------->|
   |                                     |
   |                    POST /api/auth/exchange
   |                                     |---------->|
   |                                     |  session  |
   |<------------ the application is signed in -----|
```

The ticket is single use and lives for 120 seconds. It never appears in
a URL, and the shared secret never reaches a browser: it is only ever
used between the two servers.

## 3.7 The Data Summarizer in the workspace

The Data Summarizer is the Regulatory Sentinel application. It works
the same way as Peer Benchmarking, with two differences.

**It keeps its own accounts.** The hub states who the person is; the
summarizer decides what they may do there, from the list of accounts
that are administrators in it (`HANDOFF_ADMIN_USERS` in
`sentinel/.env`). A request that tries to state a role is not given
one, so a browser cannot make itself an administrator.

**It serves its own interface from the same address as its API.** The
built interface is served by the summarizer itself on port 8090, so
there is one address to allow in the browser and one to frame.

Its secret with the hub is a secret of its own, so that the two
applications never share one:

```text
backend/.env      SENTINEL_HANDOFF_SECRET  the same value as
sentinel/.env     HANDOFF_SECRET           the one below
```

## 3.8 The Data Analyzer in the workspace

The Data Analyzer is the **PNB Employee Productivity Tool**: a document assistant that
extracts a document, summarises it, rewrites it, proofreads it, exports it, and answers
questions about a spreadsheet in words. It is an application of its own, in
`dataanalyzer/`, with its own API and its own sessions. It keeps no accounts of its own,
and it has no database: the hub states who the person is, and the application decides
what that role may do.

It works the same way as Peer Benchmarking: the hub vouches for the person and the
application decides for itself what they may do.

```text
browser          hub backend      data analyzer backend
   |                 |                    |
   | open the        |                    |
   | service         |                    |
   |---------------->|                    |
   |                 | POST /api/auth/handoff
   |                 |  X-Handoff-Secret  |
   |                 | {username, role}   |
   |                 |------------------->|
   |                 |     one-use       |
   |                 |     ticket        |
   | |<-------------------|
   |                                     |
   |  hubint:auth { ticket }  over the frame bridge
   |-------------------------------------------->|
   |                                     |
   |                    POST /api/auth/exchange
   |                                     |---------->|
   |                                     |  session  |
   |<------------ the application is signed in -----|
```

**The role is the role of the News Feed.** The `role_news` column of the `users` table
holds `admin` or `user`, and the analyzer uses the same names, so a person holds one role
in each of the applications they may open. The role is taken from the signed-in person and
never from the request, so a browser cannot make itself an administrator.

The secret is a secret of its own, so that the two applications never share one:

```text
backend/.env        ANALYZER_HANDOFF_SECRET  the same value as
dataanalyzer/.env   HANDOFF_SECRET           the one below
```

**It serves its own interface from the same address as its API.** The built interface is
served by the analyzer itself on port 8095, so there is one address to allow in the
browser and one to frame.

**It has one screen with four tools, and the hub's rail names them.** The rail of the hub
draws the tools of the application under its card, and each tool is a route of the app
(`/#/proofread`, `/#/rewrite`, `/#/summarize`, `/#/data`):

```text
hub rail                  analyzer
Proofread     --------->  #/proofread     the spelling and grammar check
Rewrite      --------->  #/rewrite       the passage, written another way
Summarize    --------->  #/summarize     the summary of the document
Ask about data -------->  #/data         the question about a spreadsheet
```

The list is one list: the analyzer's manifest (`GET /api/ui/manifest`) names the four
tools, and the application draws the same four as its own buttons. The two cannot
disagree.

## 3.9 The SQL Genie in the workspace

The SQL Genie is **not offered at the moment**. Its card is hidden in the hub, and the
code of the card is kept in `landing/src/services.js` with the marks that hide it, so
that it may be brought back by removing them.

It is an application of its own that the hub opens in its
workspace, like the other four. It is not part of this repository and
is not started by the setup script: it is pointed at by name.

```bash
# landing/.env
VITE_SQL_GENIE_APP_URL=http://localhost:8080/
```

Two things have to agree with that address:

- **The origin has to be allowed.** The hub only accepts session
  messages from the origins in `VITE_ALLOWED_CHILD_ORIGINS`. Add the
  origin of the SQL Genie there, next to the ones that are already
  there:

  ```bash
  VITE_ALLOWED_CHILD_ORIGINS=http://localhost:5173,...,http://localhost:8080,http://127.0.0.1:8080
  ```

  Without it, the application is shown, but the session is never handed
  over and the person is asked to sign in again.

- **The application has to accept the frame.** It has to allow the hub
  to frame it, and it has to answer the messages of the bridge.

### What the application is handed

The SQL Genie shares this platform's token, the same way the news
application does:

```text
child -> parent : { type: "hubint:ready" }
parent -> child : { type: "hubint:auth", payload: { username, accessToken } }
```

It is **not** told a role. The hub says who the person is; the SQL
Genie asks the backend who that is, and decides for itself what they
may do:

```bash
curl -H "Authorization: Bearer <accessToken>" http://127.0.0.1:8000/api/auth/me
```

The answer carries both roles the person holds, so the application can
write its own rules without a third column in the user table.

The bridge is the same contract every service uses, and the client that
implements it is small. The one in `frontend/src/session/index.js` is
the shortest example: it listens for `hubint:auth`, keeps the token and
hands it to the application.

### One role per application

A person holds one role in each application, and the two are kept
apart, because the applications do different work. Both are held once,
in the `users` table of the backend:

| Column | The role in | May be |
|---|---|---|
| `role_news` | the News Feed | `admin`, `user` |
| `role_bench` | Peer Benchmarking | `admin`, `maker`, `checker`, `viewer`, `user` |

Each application is given the one that belongs to it, server side, so a
browser can never choose its own role.

**The News Feed** reads `role_news`. An `admin` may open the summary,
the application insights and the pipeline control; a `user` reads the
news feed and nothing else.

**Peer Benchmarking** reads `role_bench`, in its own words, with no
translation: `admin` for everything, including the list of users;
`maker` to collect the figures, run the pipeline and draft the reports;
`checker` to check and approve the figures and the reports; `viewer` to
read the approved figures and ask Myra; and `user`, which reads the
approved figures and nothing else.

The `user` role in Peer Benchmarking is for the people who are in the
platform for the news only. It carries no work, so it is handed over
without the application needing to be configured for staff sign-ins.

A role that is not known is treated as the read-only view, so an
unexpected value in the user table can never grant more than reading.

With `HANDOFF_SYNC_ROLE=true` the benchmarking app adopts the role the
hub states, and writes an `auth.handoff.role_changed` entry to its audit
trail. That is what keeps the two applications from disagreeing about
what somebody may do.

The accounts, their passwords and their two roles are held in
`backend/seed/users.csv`, which is the account sheet of the platform.
The password in the sheet is the password of the account; it is hashed
before it is stored, and the database only ever holds the hash.

### The language model

Peer Benchmarking writes its reports with a language model on the machine, and the model it
uses is the one that is actually installed there. `OLLAMA_MODEL` may be `auto`, which is the
default: the best model that is installed is chosen, the newest family first, the larger model
within it, and never a model for embeddings. A model that is named but not pulled is replaced
by the best one that is there, and the reason is shown in the header of the application and
beside the switch that writes the narrative.

The setup script asks the machine whether a model server is running, and points the app at it
when there is one. To see what is installed and what will be used:

```bash
cd benchmarking && .venv/bin/python -m kpibench.cli models
```

The Data Summarizer works the same way. `LLM_MODEL` may be `auto`, which is the default: the
best model that is installed on the machine is chosen, by the same rules. A model that is
named but not installed is replaced by the best one that is there, and the reason is shown
with the health of the model. `LLM_STRICT_MODEL=true` refuses to use anything else.

The embeddings come from the same server when there is one, so that nothing has to be
downloaded. A machine without a model server still works: the retrieval falls back to a
plain method of its own, and the interface says so.

To see which model the summarizer would use:

```bash
cd sentinel && .venv/bin/python -c "from app.llm.models import resolve; print(resolve())"
```

### One rail, not two

Peer Benchmarking has seven screens. In the hub they are drawn in the
hub's own rail, underneath the service, so that the workspace is not a
second application inside the first one.

The benchmarking app publishes its navigation at `GET /api/ui/manifest`,
and the hub reads it through its own backend. Choosing a screen in the
rail sends `hubint:navigate` to the frame; the app moves to it and
answers with `hubint:route`, so the rail follows a journey made inside
the application.

### The news window

The **News Data Pipeline** panel of the News Feed fetches the news and runs the AI analysis
over it. The window is chosen before the run: the dropdown beside the button says how many
days back the news may reach, up to 90 days, and the cut-off date it works out is written
under the button.

The window is carried in the request, so the server decides what is stored and the browser
cannot ask for more than the limit. The scraper walks the pages of the source until it
reaches the cut-off, and only the news published inside the window is stored.

`NEWS_CUTOFF_DATE` is the floor: the oldest day the news may ever reach, whatever window is
asked for. A run may ask for less news, never for more.

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

1. The hub sends `hubint:logout` and repeats it until the frame
   answers, because a frame that is still starting up has not attached
   its message listener yet and would not receive the first request.
2. The frame clears its session and answers with `hubint:logout-ack`.
3. Only then does the hub clear its own session and remove the frame.

If the frame never answers, the hub clears the session anyway after a
short delay, so signing out can never get stuck.

### 4.2 Why a sign-out cannot be undone by a late handshake

The frame answers every `hubint:ready` with the session. A handshake
that was already in flight could therefore arrive after a sign-out and
revive the session.

Two rules prevent this:

- The hub stops handing over the session as soon as it asks the frame
  to sign out. It only resumes when a new session is set.
- The frame records the token it just revoked and ignores an
  authentication message that carries the same token. A genuinely new
  sign-in has a different token and is accepted.

## 5. Running it locally

`docs/SETUP.md` has the full instructions for Linux and for Windows.
The short version:

```bash
./setup.sh      # or .\setup.ps1 on Windows
./run.sh        # or .\run.ps1 on Windows
```

That is six services:

```text
cd backend      && .venv/bin/python -m uvicorn app.main:app --reload
cd benchmarking && .venv/bin/python -m kpibench.main
cd sentinel/backend && ../.venv/bin/python -m uvicorn app.main:app --port 8090
cd dataanalyzer/backend && ../.venv/bin/python -m uvicorn app.main:app --port 8095
cd frontend     && npm run dev                # http://localhost:5173
cd landing      && npm run dev                # http://localhost:5174
```

Open <http://localhost:5174> and sign in with a seeded account, for
example `admin` / `admin@tmd26`.

The news application is still reachable on its own at
<http://localhost:5173>, where it signs in separately. Peer Benchmarking
is still reachable on its own at <http://localhost:8077>, where it signs
in with its own accounts. This is intentional: each service stays
independently usable.

## 6. Configuration

### Backend

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///news.db` | Database connection. |
| `JWT_SECRET_KEY` | none, required | Signing key for access tokens. |
| `JWT_ALGORITHM` | `HS256` | Token algorithm. |
| `JWT_EXPIRATION_MINUTES` | `480` | Token lifetime. |
| `CORS_ORIGINS` | the development origins | Comma-separated list of browser origins allowed to call the API. |
| `KPI_APP_URL` | `http://127.0.0.1:8077` | Where Peer Benchmarking is listening. |
| `KPI_HANDOFF_SECRET` | none | The secret the two servers share. The same value as `HANDOFF_SECRET` in the benchmarking app's `.env`. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Where the language model is. |
| `OLLAMA_MODEL` | `qwen3:8b` | The model the analysis of the news uses. |
| `NEWS_CUTOFF_DATE` | `2026-06-20` | The oldest day the news may reach, whatever window is asked for. |

### Landing page (`landing/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Base URL of the API. Empty keeps the browser on the current origin, which is what the development proxy and a reverse proxy expect. |
| `VITE_NEWS_APP_URL` | `http://localhost:5173/` | URL of the news application opened in the workspace. |
| `VITE_BENCHMARKING_APP_URL` | `http://localhost:8077/` | URL of Peer Benchmarking opened in the workspace. |
| `VITE_SUMMARIZER_APP_URL` | `http://localhost:8090/` | URL of the Data Summarizer opened in the workspace. |
| `VITE_SQL_GENIE_APP_URL` | `http://localhost:8080/` | URL of the SQL Genie, whose card is hidden at the moment. |
| `VITE_ANALYZER_APP_URL` | `http://localhost:8095/` | URL of the Data Analyzer opened in the workspace. |
| `VITE_ALLOWED_CHILD_ORIGINS` | the development origins | Origins the hub accepts session messages from. The origin of the SQL Genie has to be in this list. |

### News application (`frontend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Base URL of the API, same rule as above. |
| `VITE_ALLOWED_PARENT_ORIGINS` | the development origins | Origins the application accepts session messages from. |

Both defaults cover the development setup, so the integration works
without any configuration file. A configuration file is needed only when
the origins differ from the defaults.

### Peer Benchmarking (`benchmarking/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | none, required | Signing key for its own sessions. |
| `PORT` | `8077` | The port it listens on. |
| `HANDOFF_SECRET` | none | The secret it shares with the backend. The same value as `KPI_HANDOFF_SECRET`. |
| `HANDOFF_ALLOW_STAFF` | `false` | Must be `true` for the hub to sign in analysts, approvers and administrators. |
| `HANDOFF_SYNC_ROLE` | `false` | When `true`, the role the hub states replaces the role held here. |
| `FRAME_ANCESTORS` | `'self'` | The sites allowed to show this app in a frame. |
| `EMBED_PARENT_ORIGINS` | empty | The sites allowed to drive this app. |
| `LLM_PROVIDER` | `ollama` | `ollama` writes the reports with the local model; `none` writes them from the fixed template. The setup script sets this: `ollama` when a model server is running. |
| `OLLAMA_MODEL` | `auto` | The model the reports are written with. `auto` means the best model that is installed on this machine. |
| `OLLAMA_STRICT_MODEL` | `false` | When `true`, no model but the one that is named is used. |

`scripts/make_env.py` writes both files and keeps the two secrets in
step, so they never have to be copied by hand.

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

The landing page is built with the address the news application is
served from, so that the frame points inside the one address:

```bash
cd landing
VITE_NEWS_APP_URL=https://newsintel.pnbbank.in/news/ npm run build
```

The address has to be the one the browser uses, and nothing else may be
loaded from a second address.

Because both are then served from one origin, the frame adopts the
session from shared storage and the `postMessage` handover is not
needed, although it remains available as a fallback.

## 8. Tests

```bash
cd backend  && .venv/bin/python -m pytest      # authentication, roles, the bridge
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

A second script covers Peer Benchmarking in the workspace:

```bash
node landing/e2e/benchmarking.mjs
```

It checks that the benchmarking app opens already signed in, that it
shows no sign-in form of its own, that it holds the role the hub holds,
that the hub's rail offers its screens and that choosing one moves the
application to it, and that signing out of the hub ends the session
inside the app.

To exercise the same-origin deployment, build both applications for that
arrangement and run the check. It starts a small proxy in place of the web
server, proves that the whole platform works from one address, and stops
the proxy again:

```bash
cd frontend && VITE_BASE_PATH=/news/ npm run build
cd landing  && VITE_NEWS_APP_URL=http://127.0.0.1:5175/news/ npm run build

cd landing/e2e && node same-origin.mjs
```

The backend, Peer Benchmarking, the Data Summarizer and the Data Analyzer
have to be running, as they do for the other browser tests.

The proxy on its own can also be started by hand, which is useful when the
browser is the thing being looked at:

```bash
HUB_DIST=landing/dist NEWS_DIST=frontend/dist PORT=5175 \
    node landing/e2e/same-origin-proxy.mjs
```

## 9. Adding another service

1. Build the service as its own application with its own sign-in-free
   entry point.
2. Add it to `SERVICES` in `landing/src/services.js` with its URL and
   the roles that may use it.
3. If it runs on a different origin, add that origin to
   `VITE_ALLOWED_CHILD_ORIGINS` on the hub and to
   `VITE_ALLOWED_PARENT_ORIGINS` on the service.
4. Implement the same messages in the service so that the hub can hand
   over the session. The implementation in
   `frontend/src/session/parentSession.js` can be copied as a starting
   point, and `benchmarking/static/js/bridge.js` shows the same contract
   written for a service that takes a sign-in ticket instead of a token.
5. If the service has screens of its own, publish them at
   `GET /api/ui/manifest` and the hub will draw them in its rail.
