"""The bridge to the applications the landing page embeds.

Peer Benchmarking and the Data Summarizer are separate applications, each with its own
database, its own sessions and its own audit trail. The landing page does not replace any
of that. For each of them it does two things:

1. It asks the application, on the person's behalf, for a single-use sign-in ticket. The
   ticket is handed to the frame over the message bridge, and the application swaps it for
   a session of its own. The ticket never appears in a URL, and the shared secret never
   reaches a browser.
2. It asks the application for its navigation, so that the landing page can offer the same
   list of screens in its own rail.

Both calls go from this server to the application server. A browser never calls them
directly, so no cross-origin allowance is needed there.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.roles import bench_role_label
from app.config.settings import get_settings
from app.models.user import User


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/services/benchmarking",
    tags=["Peer Benchmarking"],
)

settings = get_settings()


class TicketResponse(BaseModel):
    """A single-use sign-in ticket for the embedded application."""

    ticket: str
    role: str = Field(description="The role the person holds in Peer Benchmarking")
    roleLabel: str = Field(description="The same role, named for the interface")
    expiresIn: int = Field(description="How long the ticket stays valid, in seconds")
    tab: str = Field(default="overview", description="The screen to open")


class Section(BaseModel):
    id: str
    title: str
    icon: str
    path: str


class ManifestResponse(BaseModel):
    """The navigation of the embedded application."""

    service: str
    title: str
    defaultSection: str
    sections: list[Section]


def _handoff_url() -> str:
    return f"{settings.kpi_app_url.rstrip('/')}/api/auth/handoff"


def _manifest_url() -> str:
    return f"{settings.kpi_app_url.rstrip('/')}/api/ui/manifest"


def _require_secret() -> str:
    secret = settings.kpi_handoff_secret.strip()

    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Peer Benchmarking is not connected yet. Set KPI_HANDOFF_SECRET in the "
                "backend .env to the same value as HANDOFF_SECRET in the benchmarking "
                "app's .env, then restart the backend."
            ),
        )

    return secret


@router.post(
    "/ticket",
    response_model=TicketResponse,
)
def create_ticket(
    current_user: User = Depends(get_current_user),
):
    """
    Ask Peer Benchmarking for a sign-in ticket for the person who signed in here.

    The role is the `role_bench` column of this platform's own user table, and it is handed
    over unchanged: Peer Benchmarking uses the same names. A browser can never choose the
    role: it is taken from the signed-in person, not from the request.
    """
    secret = _require_secret()

    role = current_user.role_bench

    payload = {
        "username": current_user.username,
        "full_name": current_user.username,
        "tab": "overview",
        "embed": True,
        "role": role,
    }

    try:
        response = httpx.post(
            _handoff_url(),
            json=payload,
            headers={"X-Handoff-Secret": secret},
            timeout=settings.kpi_request_timeout,
        )
    except httpx.HTTPError as exc:
        logger.warning("Peer Benchmarking could not be reached: %s", exc)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Peer Benchmarking could not be reached. Check that it is running and "
                f"that KPI_APP_URL points at it (currently {settings.kpi_app_url})."
            ),
        )

    if response.status_code != 200:
        detail = "Peer Benchmarking refused the sign-in."

        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass

        logger.warning(
            "Peer Benchmarking refused the sign-in for %s: %s",
            current_user.username,
            response.status_code,
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )

    data = response.json()

    return TicketResponse(
        ticket=data["ticket"],
        role=data.get("role", role),
        roleLabel=bench_role_label(current_user.role_bench),
        expiresIn=int(data.get("expires_in", 120)),
        tab=data.get("path", "").rsplit("#/", 1)[-1] or "overview",
    )


@router.get(
    "/manifest",
    response_model=ManifestResponse,
)
def manifest():
    """
    The navigation of Peer Benchmarking, for the landing page's own rail.

    It names the screens and nothing else. Every figure behind them stays behind the role
    checks of the benchmarking app.
    """
    try:
        response = httpx.get(
            _manifest_url(),
            timeout=settings.kpi_request_timeout,
        )
    except httpx.HTTPError as exc:
        logger.warning("The Peer Benchmarking manifest could not be read: %s", exc)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Peer Benchmarking could not be reached.",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Peer Benchmarking did not return its navigation.",
        )

    data = response.json()

    return ManifestResponse(
        service=data.get("service", "peer-benchmarking"),
        title=data.get("title", "Peer Benchmarking"),
        defaultSection=data.get("defaultSection", "overview"),
        sections=[Section(**section) for section in data.get("sections", [])],
    )


# ---------------------------------------------------------------------------
# The Data Summarizer, which is the Regulatory Sentinel application.
# ---------------------------------------------------------------------------

summarizer_router = APIRouter(
    prefix="/api/services/summarizer",
    tags=["Data Summarizer"],
)


def _sentinel_handoff_url() -> str:
    return f"{settings.sentinel_app_url.rstrip('/')}/api/auth/handoff"


def _sentinel_manifest_url() -> str:
    return f"{settings.sentinel_app_url.rstrip('/')}/api/ui/manifest"


def _require_sentinel_secret() -> str:
    secret = settings.sentinel_handoff_secret.strip()

    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The Data Summarizer is not connected yet. Set SENTINEL_HANDOFF_SECRET in "
                "the backend .env to the same value as HANDOFF_SECRET in the summarizer's "
                ".env, then restart the backend."
            ),
        )

    return secret


@summarizer_router.post(
    "/ticket",
    response_model=TicketResponse,
)
def create_summarizer_ticket(
    current_user: User = Depends(get_current_user),
):
    """
    Ask the Data Summarizer for a sign-in ticket for the person who signed in here.

    The person is named by the `username` of this platform's own user table. The role is
    not taken from the browser: the summarizer decides it, from the list of accounts that
    are administrators there.
    """
    secret = _require_sentinel_secret()

    payload = {
        "username": current_user.username,
        "full_name": current_user.username,
        "embed": True,
    }

    try:
        response = httpx.post(
            _sentinel_handoff_url(),
            json=payload,
            headers={"X-Handoff-Secret": secret},
            timeout=settings.kpi_request_timeout,
        )
    except httpx.HTTPError as exc:
        logger.warning("The Data Summarizer could not be reached: %s", exc)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The Data Summarizer could not be reached. Check that it is running and "
                f"that SENTINEL_APP_URL points at it (currently {settings.sentinel_app_url})."
            ),
        )

    if response.status_code != 200:
        detail = "The Data Summarizer refused the sign-in."

        try:
            detail = response.json().get("detail", detail)
        except ValueError:
            pass

        logger.warning(
            "The Data Summarizer refused the sign-in for %s: %s",
            current_user.username,
            response.status_code,
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )

    data = response.json()

    return TicketResponse(
        ticket=data["ticket"],
        role=data.get("role", "analyst"),
        roleLabel=data.get("role", "analyst").capitalize(),
        expiresIn=int(data.get("expires_in", 120)),
        tab="overview",
    )


@summarizer_router.get(
    "/manifest",
    response_model=ManifestResponse,
)
def summarizer_manifest():
    """
    The navigation of the Data Summarizer, for the landing page's own rail.

    It names the screens and nothing else. Everything behind them stays behind the role
    checks of the summarizer itself.
    """
    try:
        response = httpx.get(
            _sentinel_manifest_url(),
            timeout=settings.kpi_request_timeout,
        )
    except httpx.HTTPError as exc:
        logger.warning("The Data Summarizer manifest could not be read: %s", exc)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The Data Summarizer could not be reached.",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The Data Summarizer did not return its navigation.",
        )

    data = response.json()

    return ManifestResponse(
        service=data.get("service", "data-summarizer"),
        title=data.get("title", "Data Summarizer"),
        defaultSection=data.get("defaultSection", "overview"),
        sections=[Section(**section) for section in data.get("sections", [])],
    )
