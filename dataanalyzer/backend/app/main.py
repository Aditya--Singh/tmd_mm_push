"""The Data Analyzer.

    uvicorn app.main:app --host 0.0.0.0 --port 8095

The application serves its own interface from its own address, so that there is one
address to allow in the browser and one to frame.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import auth, documents
from app.config import get_settings
from app.core.db import init_db

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

log = logging.getLogger("analyzer.app")

#: The built interface, when it has been built.
FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db()

    log.info("%s ready on %s", settings.app_name, settings.public_url)

    yield


app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """The headers that keep the frame and the pages safe."""
    ancestors = settings.frame_ancestors.strip() or "*"

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN" if ancestors == "*" else "ALLOWALL"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    if ancestors != "*":
        response.headers.setdefault("Content-Security-Policy", f"frame-ancestors {ancestors}")

    return response


app.include_router(auth.router)
app.include_router(documents.router)


@app.get("/api/health")
def health():
    """Whether this server is up."""
    return {"status": "ok", "service": "data-analyzer", "version": __version__}


@app.get("/api/meta")
def meta():
    """
    What this service is, for the setup script and for the doctor.

    It says which model this machine will write with, and why, so that a person may see
    that the best installed model was picked.
    """
    from app.llm.client import get_llm

    return {
        "service": "data-analyzer",
        "title": settings.app_name,
        "version": __version__,
        "public_url": settings.public_url,
        "model": get_llm().describe(),
        # The origins that may drive this application: the hub's own address.
        "embed_parent_origins": [
            origin.strip()
            for origin in settings.embed_parent_origins.split(",")
            if origin.strip()
        ],
    }


@app.get("/api/plots/{document_id}/{name}")
def a_plot(document_id: int, name: str):
    """One picture of a document."""
    if ".." in name:
        return JSONResponse({"detail": "No such picture."}, status_code=404)

    path = documents.PLOTS / str(document_id) / name

    if not path.is_file():
        return JSONResponse({"detail": "No such picture."}, status_code=404)

    return FileResponse(path, media_type="image/png")


# ---------------------------------------------------------------------------
# The built interface
# ---------------------------------------------------------------------------

if FRONTEND.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def the_interface(full_path: str):
        """The interface of the application."""
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "No such address."}, status_code=404)

        candidate = FRONTEND / full_path

        if full_path and candidate.is_file():
            return FileResponse(candidate)

        return FileResponse(FRONTEND / "index.html")

else:

    @app.get("/")
    def not_built():
        """A note for the person who opened the address of the API."""
        return {
            "service": "data-analyzer",
            "message": (
                "The interface has not been built yet. Run `npm install && npm run build` "
                "in dataanalyzer/frontend."
            ),
        }
