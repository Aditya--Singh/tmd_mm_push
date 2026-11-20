"""FastAPI entry point for the PNB Employee Productivity Tool.

This is the Data Analyzer of the Executive Intelligence Hub. The hub frames this app and
owns the sign-in, so the app serves its own built interface from its own origin: there is
one address to allow in the frame headers, and one address to put in the hub's settings.
"""

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
    # A Content-Security-Policy source list is separated by spaces. A comma here
    # makes the browser drop the list, and the hub's frame stays empty.
    ancestors = " ".join(settings.frame_ancestor_list) or "'none'"
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

# The built interface, served from this app's own origin.
if FRONTEND_DIST.is_dir():
    assets = FRONTEND_DIST / "assets"

    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def the_interface(full_path: str):
        index = FRONTEND_DIST / "index.html"
        candidate = FRONTEND_DIST / full_path

        if full_path and candidate.is_file():
            return FileResponse(candidate)

        return FileResponse(index)
