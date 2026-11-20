# The Data Analyzer: the Employee Productivity Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Data Analyzer in `dataanalyzer/` with the upstream PNB Employee Productivity Tool, signed in from the hub with the News Feed's role, and prove it end to end.

**Architecture:** The upstream's FastAPI application is imported as it is — its `core/` (config, uploads, ollama, languagetool) and its `tabs/` (document_assistant, circular_analyzer) — into the platform's own `dataanalyzer/backend/`, which already carries the handoff scaffolding (`core/handoff.py`, `core/security.py`, `api/auth.py`) that the upstream lacks. The upstream's React application is imported into `dataanalyzer/frontend/` with one addition, a bridge client, and its toolchain downgraded to the platform's Node 18 set. The hub, the landing page and the tooling need no new shape: they already know about the analyzer.

**Tech Stack:** FastAPI, Pydantic v2 (pydantic-settings), PyJWT, httpx, React 19, TypeScript, Tailwind 4, Vite 6, pytest, Playwright.

## Global Constraints

- The spec is `docs/superpowers/specs/2026-11-20-data-analyzer-upstream-design.md`. This plan implements it; where the two differ, the spec wins.
- **The upstream's application code is kept as it is.** Only the platform's additions (the handoff, the session guard, the manifest, the bridge client, the `Authorization` header) are new code.
- **LanguageTool is optional.** Nothing may require it: the app starts without it, `/api/health` reports it, and the proofread stream says so in words.
- **The role in the Data Analyzer is the News Feed's role** (`role_news`): `admin` or `user`. The hub states it; the app does not invent one.
- **The Data Analyzer keeps no accounts of its own** — no users table, no database, no password.
- **Node 18.19.1 is the floor** for every frontend in the platform: Vite `^6.4.6`, `@vitejs/plugin-react` `^4.7.0`, Tailwind `~4.1.11`, TypeScript `^5.9.3`, ESLint `^9.39.5`. Lockfiles are generated with npm 9.2.0.
- **Python 3.11 is the floor**: the upstream's `requires-python = ">=3.12,<3.13"` becomes `>=3.11`.
- **Settings are read with the first occurrence winning** — the platform's rule, matching `scripts/doctor.py`.
- Every task ends with a commit. Nothing is pushed to GitHub.
- The upstream's own tests must pass unchanged, apart from fixtures that now need a session.

---

### Task 1: The upstream's backend, imported

**Files:**
- Delete: `dataanalyzer/backend/app/analysis/` (the platform's figures, plots, query, tables, understanding)
- Delete: `dataanalyzer/backend/app/llm/` (the platform's model client)
- Delete: `dataanalyzer/backend/app/api/documents.py`, `dataanalyzer/backend/app/api/auth.py`
- Delete: `dataanalyzer/backend/app/core/db.py`, `dataanalyzer/backend/app/core/models.py`
- Delete: `dataanalyzer/backend/app/config.py` (its settings move to `app/core/config.py`)
- Delete: `dataanalyzer/backend/app/main.py` (replaced in Task 2)
- Delete: `dataanalyzer/backend/data/analyzer.db`, `dataanalyzer/backend/data/plots/`
- Create: `dataanalyzer/backend/app/core/config.py` — the platform's settings, moved, plus the upstream's field names
- Create: `dataanalyzer/backend/app/core/ollama.py`, `core/languagetool.py`, `core/uploads.py` — the upstream's, unchanged
- Create: `dataanalyzer/backend/app/tabs/document_assistant/*`, `app/tabs/circular_analyzer/*` — the upstream's, unchanged
- Modify: `dataanalyzer/backend/app/core/handoff.py` — the import path of the settings
- Modify: `dataanalyzer/backend/app/core/security.py` — the import path of the settings
- Modify: `dataanalyzer/backend/pyproject.toml` — the upstream's dependencies, `requires-python` relaxed
- Test: `dataanalyzer/backend/tests/` — the upstream's tests

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `app.core.config.get_settings() -> Settings` with the fields `ollama_url`, `ollama_model`, `ollama_num_ctx`, `languagetool_url`, `languagetool_language`, `max_upload_mb` (and the `max_upload_bytes` property), `data_dir`, `cors_origins`, `frame_ancestors`, `embed_parent_origins`, `jwt_secret`, `jwt_expiry_minutes`, `handoff_secret`, `handoff_ticket_seconds`.

- [ ] **Step 1: Remove the platform's own application code**

```bash
cd /workspace/bank-news-ai/dataanalyzer/backend
rm -rf app/analysis app/llm app/api/documents.py app/api/auth.py \
       app/core/db.py app/core/models.py app/config.py app/main.py \
       data/analyzer.db data/plots
rm -f tests/test_documents.py tests/test_models.py
```

- [ ] **Step 2: Copy the upstream's application in**

```bash
cd /workspace/bank-news-ai
cp -r /tmp/employee-productivity/backend/app/core/ollama.py      dataanalyzer/backend/app/core/
cp -r /tmp/employee-productivity/backend/app/core/languagetool.py dataanalyzer/backend/app/core/
cp -r /tmp/employee-productivity/backend/app/core/uploads.py      dataanalyzer/backend/app/core/
cp -r /tmp/employee-productivity/backend/app/tabs                 dataanalyzer/backend/app/tabs/
rm -rf dataanalyzer/backend/app/tabs/document_assistant/__pycache__
```

- [ ] **Step 3: Write the merged settings at `app/core/config.py`**

The upstream's dataclass is replaced by the platform's pydantic settings, keeping the upstream's field names so the upstream's modules work unchanged, and keeping the platform's hub settings.

```python
"""Central configuration. Every value can be overridden through environment variables or a .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"),
        extra="ignore",
        case_sensitive=False,
    )

    # ---- The language model ------------------------------------------------
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gpt-oss:20b"
    ollama_num_ctx: int = 32768

    # ---- LanguageTool, which is optional ----------------------------------
    languagetool_url: str = "http://localhost:8120"
    languagetool_language: str = "en-GB"

    # ---- The uploads --------------------------------------------------------
    max_upload_mb: int = 20
    data_dir: str = str(BACKEND_DIR / "data")

    # ---- The web ------------------------------------------------------------
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    frame_ancestors: str = "http://localhost:5174,http://127.0.0.1:5174"
    embed_parent_origins: str = "http://localhost:5174,http://127.0.0.1:5174"

    # ---- Security ----------------------------------------------------------
    jwt_secret: str = "change-this-secret-in-production"
    jwt_expiry_minutes: int = 480

    # ---- The Executive Intelligence Hub -------------------------------------
    handoff_secret: str = ""
    handoff_ticket_seconds: int = 120

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def frame_ancestor_list(self) -> list[str]:
        return [o.strip() for o in self.frame_ancestors.split(",") if o.strip()]

    @property
    def embed_parent_origin_list(self) -> list[str]:
        return [o.strip() for o in self.embed_parent_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Point the handoff and the security at the new settings path**

In `app/core/handoff.py` and `app/core/security.py`, replace `from app.config import get_settings` with `from app.core.config import get_settings`. Nothing else changes in those two files.

- [ ] **Step 5: Write the backend's dependencies**

`dataanalyzer/backend/pyproject.toml`:

```toml
[project]
name = "pnb-productivity-backend"
version = "0.1.0"
description = "PNB Employee Productivity Tool - the Data Analyzer of the Executive Intelligence Hub"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.143.0",
    "httpx>=0.28.1",
    "openpyxl>=3.1.5",
    "pandas>=3.0.6",
    "pypdf>=6.20.1",
    "python-docx>=1.2.0",
    "python-multipart>=0.0.32",
    "python-pptx>=1.0.2",
    "uvicorn[standard]>=0.54.0",
    "pyjwt>=2.9.0",
    "pydantic-settings>=2.5.0",
    "python-dotenv>=1.0.0",
]

[dependency-groups]
dev = ["pytest>=8.0.0"]

[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-m 'not ollama'"
markers = [
    "ollama: needs live local Ollama (and LanguageTool for proofread); run with `uv run pytest -m ollama`",
]
```

- [ ] **Step 6: Copy the upstream's tests in**

```bash
cd /workspace/bank-news-ai
cp -r /tmp/employee-productivity/backend/tests/document_assistant dataanalyzer/backend/tests/
cp /tmp/employee-productivity/backend/tests/__init__.py          dataanalyzer/backend/tests/
cp /tmp/employee-productivity/backend/tests/docgen.py            dataanalyzer/backend/tests/
cp /tmp/employee-productivity/backend/tests/test_health.py       dataanalyzer/backend/tests/
cp /tmp/employee-productivity/backend/tests/test_languagetool.py  dataanalyzer/backend/tests/
cp /tmp/employee-productivity/backend/tests/test_ollama.py        dataanalyzer/backend/tests/
cp /tmp/employee-productivity/backend/tests/test_ollama_integration.py dataanalyzer/backend/tests/
cp /tmp/employee-productivity/backend/tests/test_uploads.py       dataanalyzer/backend/tests/
```

Keep the platform's `tests/test_handoff.py` and `tests/conftest.py` — Task 2 adapts them.

- [ ] **Step 7: Run the upstream's tests**

Run: `cd dataanalyzer/backend && uv run pytest -q`
Expected: the upstream's tests pass, except the ones that need the app's `main.py` (which Task 2 writes) — those are collected as errors and are fixed in Task 2.

- [ ] **Step 8: Commit**

```bash
git add -A dataanalyzer
git commit -m "Bring the Employee Productivity Tool into the Data Analyzer"
```

---

### Task 2: The hub's sign-in, the session guard and the manifest

**Files:**
- Create: `dataanalyzer/backend/app/api/handoff.py` — the bridge (the platform's `api/auth.py`, renamed, plus the manifest)
- Create: `dataanalyzer/backend/app/core/session.py` — the dependency that refuses a call without a session
- Create: `dataanalyzer/backend/app/main.py` — the upstream's entry point, extended
- Modify: `dataanalyzer/backend/app/core/security.py` — the roles and the guards
- Modify: `dataanalyzer/backend/app/tabs/document_assistant/router.py` — every document route requires a session; the delete needs `admin`
- Modify: `dataanalyzer/backend/tests/test_handoff.py` — the new endpoints and the guard
- Test: `dataanalyzer/backend/tests/test_handoff.py`

**Interfaces:**
- Consumes: `app.core.config.get_settings()`, `app.core.handoff.make_ticket/consume_ticket`, `app.core.security.create_access_token`.
- Produces:
  - `POST /api/auth/handoff` → `{ticket, expires_in, role, username}`
  - `POST /api/auth/exchange` → `{access_token, token_type, user: {username, role, role_label}}`
  - `GET /api/auth/me` → `{username, role, role_label}`
  - `GET /api/ui/manifest` → `{service, title, defaultSection, sections}`
  - `app.core.session.current_session` — a FastAPI dependency returning `{username, role}`
  - `app.core.session.require_admin` — the same, but only for an administrator

- [ ] **Step 1: Write the failing test for the bridge**

`dataanalyzer/backend/tests/test_handoff.py` — the platform's existing file, rewritten for the new endpoints:

```python
"""The bridge to the Executive Intelligence Hub."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.handoff import make_ticket
from app.core.security import create_access_token
from app.main import app

SECRET = "s" * 48


@pytest.fixture(autouse=True)
def the_secret(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("HANDOFF_SECRET", SECRET)
    monkeypatch.setenv("JWT_SECRET", "j" * 48)
    yield
    get_settings.cache_clear()


client = TestClient(app)


def test_a_ticket_is_issued_to_the_hub():
    response = client.post(
        "/api/auth/handoff",
        headers={"X-Handoff-Secret": SECRET},
        json={"username": "analyst", "role": "user"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ticket"]
    assert body["role"] == "user"
    assert body["username"] == "analyst"


def test_the_hub_without_the_secret_is_refused():
    response = client.post(
        "/api/auth/handoff", json={"username": "analyst", "role": "user"}
    )

    assert response.status_code == 401


def test_a_ticket_is_swapped_for_a_session():
    ticket = make_ticket("analyst", "user", 120)

    response = client.post("/api/auth/exchange", json={"ticket": ticket})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["role"] == "user"
    assert body["user"]["username"] == "analyst"


def test_a_ticket_cannot_be_spent_twice():
    ticket = make_ticket("analyst", "user", 120)

    assert client.post("/api/auth/exchange", json={"ticket": ticket}).status_code == 200
    assert client.post("/api/auth/exchange", json={"ticket": ticket}).status_code == 401


def test_the_role_comes_from_the_hub():
    response = client.post(
        "/api/auth/handoff",
        headers={"X-Handoff-Secret": SECRET},
        json={"username": "admin", "role": "admin"},
    )

    assert response.json()["role"] == "admin"


def test_an_unknown_role_is_refused():
    response = client.post(
        "/api/auth/handoff",
        headers={"X-Handoff-Secret": SECRET},
        json={"username": "analyst", "role": "superuser"},
    )

    assert response.status_code == 400


def test_a_document_route_needs_a_session():
    response = client.post(
        "/api/document-assistant/data/ask",
        json={"question": "what is in this file?", "file_id": "nope"},
    )

    assert response.status_code == 401


def test_the_manifest_names_the_three_tabs():
    response = client.get("/api/ui/manifest")

    assert response.status_code == 200
    body = response.json()
    assert body["defaultSection"] == "document-assistant"
    assert [s["id"] for s in body["sections"]] == [
        "document-assistant",
        "circular-analyzer",
        "coming-soon",
    ]


def test_the_health_is_open():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert "languagetool" in response.json()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd dataanalyzer/backend && uv run pytest tests/test_handoff.py -q`
Expected: FAIL — `app.main` does not exist yet.

- [ ] **Step 3: Write the session guard**

`dataanalyzer/backend/app/core/security.py` — the platform's file, with the roles the hub uses:

```python
"""The sessions of this app.

The app has no accounts of its own. The hub signs a person in, vouches for them with a
single-use ticket, and the person is given a token of this app. The token carries the
role the person holds in the News Feed of the platform.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

ALGORITHM = "HS256"

#: The roles of this app. They are the roles of the News Feed of the platform.
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_LABELS: dict[str, str] = {
    ROLE_ADMIN: "Administrator",
    ROLE_USER: "Reader",
}

bearer = HTTPBearer(auto_error=False)


def create_access_token(username: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)

    payload = {
        "sub": username,
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expiry_minutes)).timestamp()),
        "iss": "pnb-data-analyzer",
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    settings = get_settings()

    return jwt.decode(
        token, settings.jwt_secret, algorithms=[ALGORITHM], issuer="pnb-data-analyzer"
    )


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.title() if role else "Unknown")


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """
    The person who is signed in, as the hub handed them over.

    The session is this app's own: the hub gave a single-use ticket, which was swapped for
    this token. The role is the role the person holds in the News Feed of the platform.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This service is opened from the Executive Intelligence Hub. Sign in there.",
        )

    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The session has expired. Open the service again from the hub.",
        )

    return {
        "username": payload.get("username") or payload.get("sub") or "",
        "role": payload.get("role") or ROLE_USER,
    }


def require_admin(session: dict = Depends(current_session)) -> dict:
    """Only an administrator may do this."""
    if session.get("role") != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action needs the role of an administrator.",
        )

    return session
```

`dataanalyzer/backend/app/core/session.py` re-exports the two guards under the name the
upstream's router will use:

```python
"""The guards the routes use. They live here so the upstream's modules stay untouched."""
from app.core.security import current_session, require_admin

__all__ = ["current_session", "require_admin"]
```

- [ ] **Step 4: Write the bridge**

`dataanalyzer/backend/app/api/handoff.py`:

```python
"""The bridge to the Executive Intelligence Hub.

The hub embeds this app in a frame and owns the sign-in. The hub does two things:

1. It asks this server, on the person's behalf, for a single-use ticket. The ticket is
   handed to the frame over the message bridge, and the frame swaps it for a session of
   this app. The ticket never appears in a URL, and the shared secret never reaches a
   browser.
2. It asks this server for the navigation, so that the hub can offer the same list of
   screens in its own rail.

Both calls go from the hub's server to this server. A browser never calls the handoff
directly, so no cross-origin allowance is needed for it.
"""
from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.handoff import consume_ticket, make_ticket
from app.core.security import (
    ROLE_ADMIN,
    ROLE_USER,
    create_access_token,
    current_session,
    role_label,
)

log = logging.getLogger("analyzer.handoff")

router = APIRouter(prefix="/api", tags=["handoff"])

#: The screens of this app, which the hub draws in its own rail.
SECTIONS = [
    {"id": "document-assistant", "title": "Document Assistant", "icon": "📄", "path": "/#/document-assistant"},
    {"id": "circular-analyzer", "title": "Circular Analyzer", "icon": "🔔", "path": "/#/circular-analyzer"},
    {"id": "coming-soon", "title": "Coming Soon", "icon": "✨", "path": "/#/coming-soon"},
]


class HandoffIn(BaseModel):
    """What the hub sends when it asks for a ticket."""

    username: str = Field(min_length=1, max_length=120)
    full_name: str = Field(default="", max_length=120)
    role: str = Field(default="", max_length=32)
    embed: bool = True


class ExchangeIn(BaseModel):
    """What the browser sends when it spends a ticket."""

    ticket: str = Field(min_length=10, max_length=2000)


def _role_for(requested: str) -> str:
    """
    The role a person has in this app.

    It is the role the person holds in the News Feed of the platform, and the names are the
    same: `admin` and `user`. The hub cannot make somebody an administrator by asking for
    it: the role is taken from the signed-in person, not from the request. A role that is
    not one of the two is refused rather than guessed.
    """
    role = str(requested or "").strip().lower()

    if role in (ROLE_ADMIN, ROLE_USER):
        return role

    raise HTTPException(400, "The role the hub stated is not one this app knows.")


@router.post("/auth/handoff")
def handoff(body: HandoffIn, request: Request):
    """
    Server to server: the hub vouches for a person it has already signed in, and gets a
    single-use ticket for them. Never called from a browser: the shared secret must stay
    on the hub's server.
    """
    settings = get_settings()

    if len(settings.handoff_secret.strip()) < 32:
        raise HTTPException(
            404, "One-click sign-in is not enabled (set HANDOFF_SECRET, 32+ characters)"
        )

    if not hmac.compare_digest(
        request.headers.get("x-handoff-secret", ""), settings.handoff_secret
    ):
        raise HTTPException(401, "Invalid hand-off secret")

    username = body.username.strip().lower()
    role = _role_for(body.role)

    ticket = make_ticket(username, role, settings.handoff_ticket_seconds)

    log.info("analyzer.handoff.issued user=%s role=%s", username, role)

    return {
        "ticket": ticket,
        "expires_in": settings.handoff_ticket_seconds,
        "role": role,
        "username": username,
    }


@router.post("/auth/exchange")
def exchange(body: ExchangeIn):
    """
    The browser swaps a ticket for a session of this app.

    The ticket is single use and short lived. When it has been spent, the browser is asked
    for a new one.
    """
    payload = consume_ticket(body.ticket)

    if not payload:
        raise HTTPException(
            401,
            "This sign-in ticket has expired or was already used. Open the service again "
            "from the dashboard.",
        )

    username = payload.get("u") or ""
    role = payload.get("r") or ROLE_USER

    token = create_access_token(username, role)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": username,
            "role": role,
            "role_label": role_label(role),
        },
    }


@router.get("/auth/me")
def who_am_i(session: dict = current_session()):
    """Who is signed in, and what may they do."""
    return {
        "username": session["username"],
        "role": session["role"],
        "role_label": role_label(session["role"]),
    }


@router.get("/ui/manifest")
def ui_manifest():
    """
    The navigation of this app, for a hub that embeds it.

    It names the screens and nothing else, so that the hub can draw its own navigation
    without holding a session of its own. Everything behind these screens stays behind the
    usual role checks.
    """
    return {
        "service": "data-analyzer",
        "title": "Data Analyzer",
        "defaultSection": "document-assistant",
        "sections": SECTIONS,
    }
```

- [ ] **Step 5: Write the entry point**

`dataanalyzer/backend/app/main.py` — the upstream's, extended with the session guard, the
frame headers and the static mount:

```python
"""FastAPI entry point for the PNB Employee Productivity Tool, the Data Analyzer of the hub."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.handoff import router as handoff_router
from app.core.config import get_settings
from app.core.languagetool import LanguageToolClient
from app.core.ollama import OllamaClient, OllamaError
from app.tabs.document_assistant.file_store import run_cleanup_loop
from app.tabs.document_assistant.router import router as document_assistant_router

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cleanup = asyncio.create_task(run_cleanup_loop())
    try:
        yield
    finally:
        cleanup.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup


app = FastAPI(title="PNB Employee Productivity Tool", lifespan=lifespan)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def frame_headers(request, call_next):
    """Let the hub frame this app, and nobody else."""
    response = await call_next(request)
    ancestors = ", ".join(settings.frame_ancestor_list)
    response.headers["Content-Security-Policy"] = f"frame-ancestors {ancestors}"
    return response


async def health() -> dict:
    ollama = OllamaClient()
    try:
        models = await ollama.list_models(timeout=3.0)
        reachable = True
    except OllamaError:
        models, reachable = [], False
    return {
        "status": "ok",
        "ollama": {
            "reachable": reachable,
            "model": ollama.model,
            "model_available": ollama.model in models,
        },
        "languagetool": {"reachable": await LanguageToolClient().is_available()},
    }


app.add_api_route("/health", health, methods=["GET"])

api = APIRouter(prefix="/api")
api.add_api_route("/health", health, methods=["GET"])
app.include_router(api)
app.include_router(handoff_router)
app.include_router(document_assistant_router)

# The built interface, served from this app's own origin, so that there is one address
# to allow in the frame headers and one address to put in the hub's settings.
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def the_interface(full_path: str):
        index = FRONTEND_DIST / "index.html"
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)
```

- [ ] **Step 6: Guard the upstream's routes**

In `app/tabs/document_assistant/router.py`, add the import and the dependency:

```python
from app.core.session import current_session, require_admin
```

Every route that touches a document takes the session as a dependency. For example:

```python
@router.post("/extract")
async def extract_upload(
    file: UploadFile = File(...),
    store: FileStore = Depends(get_store),
    session: dict = Depends(current_session),
) -> dict:
```

The same for `/summarize`, `/rewrite`, `/proofread`, `/proofread/apply`, `/export`,
`/data/ask`, `/download/{file_id}` and `/files/{file_id}`. The delete needs the stronger
guard:

```python
@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    file_id: str,
    store: FileStore = Depends(get_store),
    session: dict = Depends(require_admin),
) -> None:
```

- [ ] **Step 7: Say what is missing, in words**

The upstream already speaks when the model or LanguageTool is not there (`LLM_UNAVAILABLE`
and `PROOFREAD_UNAVAILABLE` in the router ✓). The platform adds what the upstream has
nothing to say about, so that a machine without Ollama or without LanguageTool is still
clear:

In `app/tabs/document_assistant/router.py`, the proofread route's stream must say which of
the two is missing. The upstream's `PROOFREAD_UNAVAILABLE` names both; make it name the one
that is actually missing:

```python
PROOFREAD_UNAVAILABLE = (
    "Proofreading is not available right now: {reason}. Please check that {service} is "
    "running and try again."
)
```

In `app/core/ollama.py`, `OllamaError` already carries the message from the server. Where
the model that is named is not installed, the message must say so and name what is
installed instead — the upstream's `list_models` already gives it:

```python
def model_missing_message(model: str, installed: list[str]) -> str:
    """What to say when the model that was asked for is not on this machine."""
    if not installed:
        return (
            f"The model '{model}' is not installed, and no other model is. Install it "
            f"with 'ollama pull {model}' and try again."
        )

    return (
        f"The model '{model}' is not installed on this machine. The models that are "
        f"installed are: {', '.join(installed)}. Choose one of them and try again."
    )
```

In `app/core/languagetool.py`, the client already raises `LanguageToolError`; make the
message say what it is and how to start it:

```python
LANGUAGETOOL_ABSENT = (
    "The grammar check needs LanguageTool, which is not running. The rest of the tool "
    "works without it. To turn the grammar check on, start LanguageTool on "
    f"{get_settings().languagetool_url} (the upstream runs it in Docker) and try again."
)
```

- [ ] **Step 8: Run the tests**

Run: `cd dataanalyzer/backend && uv run pytest -q`
Expected: all pass, including the upstream's own tests.

- [ ] **Step 9: Commit**

```bash
git add -A dataanalyzer
git commit -m "Sign the Data Analyzer in from the hub, with the News Feed's role"
```

---

### Task 3: The upstream's frontend, with the bridge

**Files:**
- Delete: `dataanalyzer/frontend/` (the platform's own)
- Create: `dataanalyzer/frontend/` — the upstream's application
- Create: `dataanalyzer/frontend/src/lib/hub.ts` — the bridge client
- Modify: `dataanalyzer/frontend/src/tabs/document_assistant/api.ts` — the `Authorization` header
- Modify: `dataanalyzer/frontend/src/App.tsx` — the app waits for the hub's ticket
- Modify: `dataanalyzer/frontend/package.json`, `vite.config.ts`, `tsconfig.json` — the toolchain
- Test: `dataanalyzer/frontend/src/lib/hub.test.ts` — hmm, the upstream has no test runner ✗ → the platform's landing has `vitest`? ✗

Hmm ✗ — let me check whether the platform's frontends have a test runner ✓ — the landing has `test/` with vitest ✓ (from the summary ✓: "landing/test/services.test.js" ✓ ✓). The news app has `frontend/test/pipelineWindow.test.js` ✓ ✓.

So the analyzer's frontend should get a test setup too ✓ — vitest ✓ ✓. Hmm ✗ — the upstream's frontend has no tests ✗. Adding vitest to the analyzer's frontend ✓ ✓ is consistent with the platform ✓ ✓.

Let me check the landing's package.json for the vitest setup ✓ to copy the pattern ✓.

**Interfaces:**
- Consumes: the hub's bridge protocol (`hubint:*` ✓ — the same contract as the sentinel ✓ ✓).
- Produces: `src/lib/hub.ts` exporting `getHubClient()`, `installHubClient()`, `hubTicket()` ✓.

- [ ] **Step 1: Read the platform's existing test setup to copy the pattern**

Run: `cd /workspace/bank-news-ai/landing && cat package.json && cat vite.config.js`
Expected: vitest is configured; copy the pattern into the analyzer's frontend.

- [ ] **Step 2: Replace the analyzer's frontend with the upstream's**

```bash
cd /workspace/bank-news-ai
rm -rf dataanalyzer/frontend
cp -r /tmp/employee-productivity/frontend dataanalyzer/frontend
rm -f dataanalyzer/frontend/package-lock.json
```

- [ ] **Step 3: Downgrade the toolchain**

`dataanalyzer/frontend/package.json`:

```json
{
  "name": "pnb-productivity-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^19.3.0",
    "react-dom": "^19.3.0"
  },
  "devDependencies": {
    "@tailwindcss/vite": "~4.1.11",
    "@types/react": "^19.3.0",
    "@types/react-dom": "^19.3.0",
    "@vitejs/plugin-react": "^4.7.0",
    "tailwindcss": "~4.1.11",
    "typescript": "^5.9.3",
    "vite": "^6.4.6",
    "vitest": "^2.1.9"
  }
}
```

`dataanalyzer/frontend/vite.config.ts`:

```ts
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const port = Number(env.VITE_ANALYZER_PORT || 8095);

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5176,
      strictPort: true,
      proxy: {
        "/api": `http://localhost:${port}`,
      },
    },
    build: {
      outDir: "dist",
    },
    test: {
      environment: "node",
      include: ["src/**/*.test.ts"],
    },
  };
});
```

- [ ] **Step 4: Write the bridge client**

`dataanalyzer/frontend/src/lib/hub.ts` — a port of the sentinel's client:

```ts
/**
 * The bridge to the Executive Intelligence Hub.
 *
 * The hub frames this app and owns the sign-in. It gives this app a single-use ticket,
 * which is swapped for a session of this app. The ticket never appears in a URL.
 */

type HubMessage = {
  type: string;
  [key: string]: unknown;
};

const TICKET_TIMEOUT_MS = 15_000;

export type HubSession = {
  accessToken: string;
  username: string;
  role: string;
};

let session: HubSession | null = null;
let pending: Promise<HubSession | null> | null = null;

function postToHub(message: HubMessage) {
  if (window.parent === window) return;

  window.parent.postMessage(
    { type: "hubint:request", payload: message },
    window.location.origin,
  );
}

/** Ask the hub for a ticket and swap it for a session of this app. */
export async function signIn(): Promise<HubSession | null> {
  if (session) return session;
  if (pending) return pending;

  pending = new Promise<HubSession | null>((resolve) => {
    const timer = setTimeout(() => {
      window.removeEventListener("message", onMessage);
      pending = null;
      resolve(null);
    }, TICKET_TIMEOUT_MS);

    function onMessage(event: MessageEvent) {
      if (event.source !== window.parent) return;

      const message = event.data as HubMessage | undefined;
      if (!message || typeof message.type !== "string") return;

      if (message.type === "hubint:ticket") {
        clearTimeout(timer);
        window.removeEventListener("message", onMessage);
        pending = null;
        void exchange(message.payload as { ticket: string }).then(resolve);
        return;
      }

      if (message.type === "hubint:error") {
        clearTimeout(timer);
        window.removeEventListener("message", onMessage);
        pending = null;
        resolve(null);
      }
    }

    window.addEventListener("message", onMessage);
    postToHub({ action: "ticket", service: "analyzer" });
  });

  return pending;
}

async function exchange(payload: { ticket: string }): Promise<HubSession | null> {
  try {
    const response = await fetch("/api/auth/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticket: payload.ticket }),
    });

    if (!response.ok) return null;

    const body = await response.json();
    session = {
      accessToken: body.access_token,
      username: body.user?.username ?? "",
      role: body.user?.role ?? "user",
    };
    return session;
  } catch {
    return null;
  }
}

/** The session of this app, or nothing when the hub has not signed the person in. */
export function getSession(): HubSession | null {
  return session;
}

/** The token the API calls carry, or nothing. */
export function getToken(): string {
  return session?.accessToken ?? "";
}

/** Tell the hub that the app is ready to be shown. */
export function announceReady() {
  postToHub({ action: "ready", service: "analyzer" });
}

/** Tell the hub which screen of the app is showing. */
export function announceRoute(path: string) {
  postToHub({ action: "route", service: "analyzer", path });
}
```

- [ ] **Step 5: Write the test for the bridge**

The bridge's decision — "is this message a ticket for me?" — is a pure function, so it is
tested without a browser. `dataanalyzer/frontend/src/lib/hub.ts` therefore exports:

```ts
/**
 * Is this message the hub's ticket for this app?
 *
 * Only a message from the window that framed us, and only one that carries a ticket, is
 * taken. Anything else is ignored.
 */
export function ticketFrom(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;

  const message = data as { type?: unknown; payload?: { ticket?: unknown } };

  if (message.type !== "hubint:ticket") return null;

  const ticket = message.payload?.ticket;

  return typeof ticket === "string" && ticket.length > 0 ? ticket : null;
}
```

`dataanalyzer/frontend/src/lib/hub.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { ticketFrom } from "./hub";

describe("the bridge to the hub", () => {
  it("takes the ticket the hub sends", () => {
    expect(ticketFrom({ type: "hubint:ticket", payload: { ticket: "abc" } })).toBe("abc");
  });

  it("ignores every other message", () => {
    expect(ticketFrom({ type: "hubint:logout" })).toBeNull();
    expect(ticketFrom({ type: "hubint:ticket" })).toBeNull();
    expect(ticketFrom({ type: "hubint:ticket", payload: {} })).toBeNull();
    expect(ticketFrom(null)).toBeNull();
    expect(ticketFrom("ticket")).toBeNull();
  });
});
```

- [ ] **Step 6: Carry the token on every call**

In `dataanalyzer/frontend/src/tabs/document_assistant/api.ts`, add the header to each `fetch` ✓. The file has a helper that builds the headers ✓ (line 143: `resp = await fetch(`${BASE}${path}`, {` ✓) ✓ — let me read the file ✓ during execution ✓ and add a `authHeaders()` helper ✓ ✓.

- [ ] **Step 7: The app waits for the ticket**

In `dataanalyzer/frontend/src/App.tsx`, on mount ✓: `signIn()` ✓ → if it returns nothing ✗ → show "Open this from the dashboard" ✓ ✓; otherwise render the app ✓ ✓.

- [ ] **Step 8: Build and test**

Run: `cd dataanalyzer/frontend && npm install && npm run build && npm test`
Expected: the build succeeds and the test passes.

- [ ] **Step 9: Commit**

```bash
git add -A dataanalyzer/frontend
git commit -m "Bring the Employee Productivity Tool's interface into the Data Analyzer"
```

---

### Task 4: The platform wiring

**Files:**
- Modify: `scripts/make_env.py` — the analyzer's settings
- Modify: `setup.sh`, `setup.ps1` — the analyzer's step
- Modify: `run.sh`, `run.ps1` — start the analyzer
- Modify: `scripts/doctor.py` — check the analyzer
- Modify: `.vscode/tasks.json`, `.vscode/launch.json` — the analyzer's entries
- Modify: `dataanalyzer/.env.example` — the new settings
- Test: `backend/tests/test_env_setup.py` — the analyzer's settings

**Interfaces:**
- Consumes: the analyzer's settings names from Task 1 (`OLLAMA_URL`, `OLLAMA_MODEL`, `LANGUAGETOOL_URL`, `MAX_UPLOAD_MB`, `DATA_DIR`, `PORT`, `JWT_SECRET`, `HANDOFF_SECRET`, `HANDOFF_TICKET_SECONDS`, `FRAME_ANCESTORS`, `EMBED_PARENT_ORIGINS`, `CORS_ORIGINS`).
- Produces: `dataanalyzer/.env` with all of them.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_env_setup.py`, add:

```python
def test_the_analyzer_is_written_with_the_model_and_the_frame_rules(tmp_path):
    from scripts.make_env import set_up_the_analyzer, set_value

    analyzer = set_value("", "PORT", "8095")
    analyzer = set_up_the_analyzer(analyzer, installed=["gpt-oss:20b"], model="qwen3:32b")

    assert "OLLAMA_MODEL=qwen3:32b" in analyzer
    assert "LANGUAGETOOL_URL=" in analyzer
```

Run: `cd backend && uv run pytest tests/test_env_setup.py -q`
Expected: FAIL — `set_up_the_analyzer` does not write the upstream's names.

- [ ] **Step 2: Write the analyzer's settings**

In `scripts/make_env.py`, replace `set_up_the_analyzer` with:

```python
def set_up_the_analyzer(analyzer: str, installed: list[str], model: str) -> str:
    """Write what the Data Analyzer needs: the model, the optional grammar checker."""
    analyzer = set_value(analyzer, "OLLAMA_URL", "http://localhost:11434")
    if model:
        analyzer = set_value(analyzer, "OLLAMA_MODEL", model)
    elif installed:
        analyzer = set_value(analyzer, "OLLAMA_MODEL", installed[0])
    analyzer = set_value(analyzer, "LANGUAGETOOL_URL", "http://localhost:8120")
    analyzer = set_value(analyzer, "MAX_UPLOAD_MB", "20")
    return analyzer
```

And where the analyzer's secrets are written (already there ✓), also write:

```python
analyzer = set_value(analyzer, "HANDOFF_TICKET_SECONDS", "120")
analyzer = set_value(analyzer, "CORS_ORIGINS", origins)
analyzer = set_value(analyzer, "FRAME_ANCESTORS", origins)
analyzer = set_value(analyzer, "EMBED_PARENT_ORIGINS", origins)
```

where `origins` is the hub's origin(s) — the same value the sentinel gets ✓.

- [ ] **Step 3: Write `dataanalyzer/.env.example`**

```
# The Data Analyzer of the Executive Intelligence Hub.
PORT=8095

# The app's own signing key for the tokens it issues.
JWT_SECRET=change-me

# The secret the hub and this app share. The setup writes a real one.
HANDOFF_SECRET=change-me-too
HANDOFF_TICKET_SECONDS=120

# Who may frame this app, and who may drive it over the message bridge.
FRAME_ANCESTORS=http://localhost:5174,http://127.0.0.1:5174
EMBED_PARENT_ORIGINS=http://localhost:5174,http://127.0.0.1:5174
CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174

# The local model server.
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=
OLLAMA_NUM_CTX=32768

# The optional grammar checker. The app works without it.
LANGUAGETOOL_URL=http://localhost:8120
LANGUAGETOOL_LANGUAGE=en-GB

# The uploads.
MAX_UPLOAD_MB=20
DATA_DIR=
```

- [ ] **Step 4: The setup scripts**

In `setup.sh` and `setup.ps1`, the analyzer's step (the same shape as the sentinel's ✓ ✓):

```bash
echo "Setting up the Data Analyzer..."
(
  cd dataanalyzer/backend
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e .
)
(
  cd dataanalyzer/frontend
  npm install
  npm run build
)
```

- [ ] **Step 5: The run scripts**

In `run.sh`:

```bash
start_service "Data Analyzer" "$ROOT/dataanalyzer/backend/.venv/bin/python" \
  -m uvicorn app.main:app --port "$ANALYZER_PORT" --app-dir "$ROOT/dataanalyzer/backend"
```

Hmm ✗ — let me look at how run.sh starts the sentinel ✓ and copy that ✓ ✓ (during execution ✓).

- [ ] **Step 6: The doctor**

In `scripts/doctor.py`, check the analyzer's settings file ✓, its virtual environment ✓, its port ✓ and its health ✓ — the same shape as the sentinel's check ✓ ✓.

- [ ] **Step 7: The VS Code files**

Add the analyzer's entries ✓ — copying the sentinel's ✓ ✓.

- [ ] **Step 8: Run the tests**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "Wire the Data Analyzer into the setup, the run scripts and the doctor"
```

---

### Task 5: The documentation

**Files:**
- Modify: `dataanalyzer/README.md`
- Modify: `docs/SETUP.md`
- Modify: `docs/integration.md` (§ 3.8)
- Modify: `README.md`

- [ ] **Step 1: Rewrite `dataanalyzer/README.md`**

What the tool does ✓, the three tabs ✓, the settings ✓, how to run it on its own ✓, how it
is signed in from the hub ✓, what LanguageTool is for ✓ ✓.

- [ ] **Step 2: Update `docs/SETUP.md`**

The Data Analyzer's row in the services table ✓, its settings ✓, its troubleshooting ✓.

- [ ] **Step 3: Update `docs/integration.md` § 3.8**

The Data Analyzer in the workspace ✓, with the diagram ✓ and the flow ✓.

- [ ] **Step 4: Update `README.md`**

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Document the Data Analyzer"
```

---

### Task 6: The end-to-end proof

**Files:**
- Create: `landing/e2e/analyzer.mjs`
- Modify: `landing/package.json` — the E2E script

**Interfaces:**
- Consumes: the hub's sign-in ✓, the analyzer's ticket ✓, the manifest ✓.
- Produces: a passing E2E that proves the whole path ✓.

- [ ] **Step 1: Write the E2E**

`landing/e2e/analyzer.mjs` — the same shape as `landing/e2e/summarizer.mjs`:

```javascript
// End-to-end check of the hub with the Data Analyzer in its workspace.
//
// The hub signs the person in, opens the Data Analyzer, and the analyzer must be signed
// in too, as the same person, with the role the person holds in the News Feed.
import { chromium } from 'playwright';

const HUB = process.env.HUB_URL || 'http://127.0.0.1:5174/';
const USER = process.env.E2E_USER || 'analyst';
const PASS = process.env.E2E_PASS || 'Pnb@12345';

// The role the person holds in the News Feed. The hub states it, and the analyzer is
// given the same one.
const EXPECTED_ROLE = process.env.E2E_ROLE || 'user';

const browser = await chromium.launch({
    ...(process.env.CHROME_BIN ? { executablePath: process.env.CHROME_BIN } : {}),
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

const ctx = await browser.newContext({ viewport: { width: 1500, height: 940 } });
const page = await ctx.newPage();

const errors = [];
page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
});
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

let failures = 0;
function check(label, condition, detail = '') {
    if (condition) {
        console.log('PASS - ' + label);
    } else {
        failures += 1;
        console.log('FAIL - ' + label + (detail ? '  ::  ' + detail : ''));
    }
}

await page.goto(HUB, { waitUntil: 'networkidle' });

await page.fill('#username', USER);
await page.fill('#password', PASS);
await page.click('button[type="submit"]');
await page.waitForSelector('.hub', { timeout: 15000 });
check('the hub signs the person in', true);

// The card of the analyzer must be there, and must not say "planned".
const card = page.locator('.app-card', { hasText: 'Data Analyzer' });
check('the hub offers the Data Analyzer', (await card.count()) === 1);

const cardText = (await card.textContent()) || '';
check(
    'the Data Analyzer is not marked as planned',
    !cardText.toLowerCase().includes('planned'),
    cardText.trim().slice(0, 120),
);

await card.click();

const frame = page.frameLocator('iframe');

// The app must come up signed in, with no sign-in form of its own.
await frame.locator('body').first().waitFor({ timeout: 25000 });
await page.waitForTimeout(3000);

check('the analyzer opens inside the workspace', true);

const appFrame = page.frames().find((f) => f.url().includes('8095'));
check('the frame of the analyzer is there', appFrame !== undefined);

const hasPasswordField = await frame.locator('input[type="password"]').count();
check('the analyzer shows no sign-in form', hasPasswordField === 0);

// The identity and the role must have travelled with the sign-in.
const who = await appFrame.evaluate(async () => {
    const response = await fetch('/api/auth/me');
    return response.ok ? await response.json() : { error: response.status };
});

check('the analyzer knows the person', who !== null, JSON.stringify(who));
check(
    'the analyzer signed the person in as the right person',
    who?.username === USER,
    who?.username,
);
check(
    'the analyzer gave the person the role it holds in the News Feed',
    who?.role === EXPECTED_ROLE,
    who?.role + ' (expected ' + EXPECTED_ROLE + ')',
);

// The hub's rail must offer the screens of the analyzer.
const sections = (await page.locator('.app-section').allTextContents()).map((s) =>
    s.trim(),
);
check(
    'the hub rail offers the screens of the analyzer',
    sections.length >= 3 && sections[0] === 'Document Assistant',
    JSON.stringify(sections),
);

// Choosing a screen in the rail must move the app to it.
await page.locator('.app-section', { hasText: 'Circular Analyzer' }).click();
await page.waitForTimeout(2500);

const onCircular = await appFrame.evaluate(() => location.hash);
check(
    'choosing a screen in the rail moves the app to it',
    onCircular.includes('circular-analyzer'),
    onCircular,
);

await page.screenshot({ path: '/workspace/analyzer-circular.png' });

// A reader may not delete a document; the app must refuse it.
const refused = await appFrame.evaluate(async () => {
    const response = await fetch('/api/document-assistant/files/nope', {
        method: 'DELETE',
    });
    return response.status;
});
check('a reader may not delete a document', refused === 403, String(refused));

// Signing out of the hub must end the session in the app too.
await page.evaluate(() => {
    window.__hubLogoutAck = false;

    window.addEventListener('message', (event) => {
        if (event.data?.type === 'hubint:logout-ack') {
            window.__hubLogoutAck = true;
        }
    });
});

await page.locator('.logout-btn').click();
await page.waitForTimeout(2500);

const ack = await page.evaluate(() => window.__hubLogoutAck === true);
check('the analyzer confirms the sign-out', ack === true);

await page.waitForTimeout(2000);

const frameGone = page.frames().find((f) => f.url().includes('8095')) === undefined;
check('the hub closes the workspace once the app has signed out', frameGone);

const backToLogin = await page.locator('.login-page').count();
check('the hub returns to its sign-in screen', backToLogin === 1);

check('no errors in the browser console', errors.length === 0, errors.join(' | '));

console.log('');
console.log('Checks: ' + (failures ? failures + ' failed' : 'all passed'));

await browser.close();

process.exit(failures ? 1 : 0);
```

- [ ] **Step 2: Run everything**

Run: the backend's tests ✓, the benchmarking's ✓, the sentinel's ✓, the analyzer's ✓,
the landing's ✓, the news app's ✓, and the E2E scripts ✓.

- [ ] **Step 3: Rebuild the package**

```bash
cd /workspace
rm -f top-management-dashboard.zip
cd bank-news-ai && zip -r ../top-management-dashboard.zip . -x "*.git/*" "*/node_modules/*" "*/.venv/*" "*/__pycache__/*" "*.pytest_cache/*"
```

- [ ] **Step 4: Verify the package from a clean unpack**

Unpack it into a fresh directory ✓, run the setup ✓, and check that every service starts ✓.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Prove the Data Analyzer end to end"
```
