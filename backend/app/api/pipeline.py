from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import require_admin
from app.models.user import User
from app.services.news_pipeline import NewsPipelineService


router = APIRouter(
    prefix="/api/admin",
    tags=["Administration"],
)


class IngestRequest(BaseModel):
    """How far back the news may reach."""

    days: int = Field(
        default=30,
        ge=1,
        le=90,
        description=(
            "The number of days back the news may reach. News published before "
            "that day is not stored."
        ),
    )


@router.post("/news/ingest")
def ingest_news(
    body: IngestRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
):
    """
    Fetch the news and run the AI analysis over it.

    The window is counted back from today, and only the news published inside it is
    stored. The date it starts at is returned, so that the person who started it can
    see what was asked for.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=body.days)

    background_tasks.add_task(NewsPipelineService().run, body.days)

    return {
        "status": "started",
        "message": (
            f"News ingestion started. News published in the last {body.days} "
            f"days will be stored."
        ),
        "days": body.days,
        "cutoff": cutoff.isoformat(),
    }
