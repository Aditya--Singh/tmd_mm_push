"""FastAPI application entry point.

    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__, scheduler
from app.api import auth, chat, circulars, handoff, observability
from app.config import get_settings
from app.core import runtime_settings as rs
from app.core.db import init_db, session_scope
from app.core.models import User
from app.core.security import hash_password
from app.observability import audit
from app.observability.events import bus
from app.observability.logging import setup_logging
from app.rag.index import index

settings = get_settings()
setup_logging(settings.data_dir / "logs", settings.log_level)
log = logging.getLogger("sentinel.app")


def _seed_admin() -> None:
    created = False
    with session_scope() as db:
        if not db.query(User).filter(User.email == settings.admin_email.lower()).first():
            db.add(User(email=settings.admin_email.lower(), name=settings.admin_name, role="admin",
                        password_hash=hash_password(settings.admin_password), must_change_password=True))
            created = True
    if created:
        audit.record("system", "user.seed_admin", resource=settings.admin_email.lower())
        log.warning("seeded administrator account - change the password after first login", extra={"email": settings.admin_email})


@asynccontextmanager
async def lifespan(app: FastAPI):
    bus.bind_loop(asyncio.get_running_loop())
    init_db()
    _seed_admin()
    from app.agents.ingestion import reembed_stale
    from app.llm.embeddings import get_embedder

    get_embedder()  # load model once at startup (may download on first run)
    info = await index.rebuild()
    if info["stale"]:
        await reembed_stale(info["stale"])
        await index.rebuild()
    with session_scope() as db:
        interval = int(rs.get(db, "sync_interval_minutes") or settings.sync_interval_minutes)
    scheduler.start(interval, run_soon=settings.sync_on_startup)
    audit.record("system", "app.start", details={"version": __version__, "index_chunks": index.size})
    log.info("RBI Regulatory Sentinel ready", extra={"version": __version__, "chunks": index.size})
    yield
    scheduler.shutdown()
    audit.record("system", "app.stop")


app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials="*" not in settings.cors_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    # allow the Top Management Dashboard to show this app in an iframe (FRAME_ANCESTORS in .env)
    response.headers.setdefault("Content-Security-Policy", f"frame-ancestors {settings.frame_ancestors}")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error", extra={"path": request.url.path})
    return JSONResponse(status_code=500, content={"detail": "Internal error. The details are in the server logs."})


for r in (auth.router, circulars.router, chat.router, observability.router, handoff.router):
    app.include_router(r)


@app.get("/api/schedule")
def schedule_info():
    return {"next_run": scheduler.next_run()}


# ---- serve the built React app (frontend/dist) when present -----------------
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if not _dist.exists():
    _dist = Path(__file__).resolve().parents[1] / "static"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        candidate = _dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
