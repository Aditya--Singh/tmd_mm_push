"""The bridge to Peer Benchmarking.

Peer Benchmarking is a separate application with its own database, its own sessions and its own
audit trail. The landing page does not replace any of that. It does two things:

1. It asks the benchmarking app, on the person's behalf, for a single-use sign-in ticket. The
   ticket is handed to the frame over the message bridge, and the benchmarking app swaps it for
   a session of its own. The ticket never appears in a URL, and the shared secret never reaches
   a browser.
2. It asks the benchmarking app for its navigation, so that the landing page can offer the same
   list of screens in its own rail.

Both calls go from this server to the benchmarking server. A browser never calls the
benchmarking app directly, so no cross-origin allowance is needed there.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.roles import benchmarking_role, role_label
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

    The role is read from this platform's own user table and mapped to the role Peer
    Benchmarking uses. A browser can never choose the role: it is taken from the signed-in
    person, not from the request.
    """
    secret = _require_secret()

    role = benchmarking_role(current_user.role)

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
        roleLabel=role_label(current_user.role),
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
