from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# The repair has to happen before SQLAlchemy is imported anywhere else, so it is
# imported first. It does nothing on a machine that loads compiled parts as usual.
from app import blocked_extensions  # noqa: F401

import app.models
from app.config.settings import get_settings
from app.database.database import Base, engine
from app.database.migrate import migrate


settings = get_settings()

from app.api.news import router as news_router
from app.api.dashboard import router as dashboard_router
from app.api.feedback import router as feedback_router
from app.api.auth import router as auth_router
from app.api.pipeline import router as pipeline_router
from app.api.integrations import router as integrations_router

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(news_router)
app.include_router(dashboard_router)
app.include_router(feedback_router)
app.include_router(auth_router)
app.include_router(pipeline_router)
app.include_router(integrations_router)

# A database that was made before the roles were split is brought up to the
# current shape first, and only then are the missing tables created.
migrate(engine)

Base.metadata.create_all(bind=engine)


@app.get("/")
def home():
    """
    A quick way to confirm that the API is running.

    The interactive documentation is at /docs.
    """

    return {
        "application": settings.app_name,
        "environment": settings.env,
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }
