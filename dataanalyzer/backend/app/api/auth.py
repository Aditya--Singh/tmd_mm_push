"""The bridge to the Executive Intelligence Hub.

The hub embeds this app in a frame and owns the sign-in. This app keeps its own sessions.
The hub does two things:

1. It asks this server, on the person's behalf, for a single-use sign-in ticket. The ticket
   is handed to the frame over the message bridge, and the frame swaps it for a session of
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
import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.handoff import consume_ticket, make_ticket
from app.core.security import ROLE_ADMIN, ROLE_USER, create_access_token, role_label

log = logging.getLogger("analyzer.handoff")

router = APIRouter(prefix="/api", tags=["handoff"])


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
    it: the role is taken from the signed-in person, not from the request.
    """
    role = str(requested or "").strip().lower()

    if role in (ROLE_ADMIN, ROLE_USER):
        return role

    return ROLE_USER


@router.post("/auth/handoff")
def handoff(body: HandoffIn, request: Request):
    """
    Server to server: the hub vouches for a person it has already signed in, and gets a
    single-use ticket for them. Never called from a browser: the shared secret must stay on
    the hub's server.
    """
    settings = get_settings()

    if len(settings.handoff_secret.strip()) < 32:
        raise HTTPException(
            404,
            "One-click sign-in is not enabled (set HANDOFF_SECRET, 32+ characters)",
        )

    if not hmac.compare_digest(
        request.headers.get("x-handoff-secret", ""), settings.handoff_secret
    ):
        log.warning("a sign-in was refused: the secret did not match")

        raise HTTPException(401, "Invalid hand-off secret")

    username = body.username.strip().lower()
    role = _role_for(body.role)

    ticket = make_ticket(username, role, settings.handoff_ticket_seconds)

    log.info("a sign-in ticket was issued for %s with the role %s", username, role)

    return {
        "ticket": ticket,
        "expires_in": settings.handoff_ticket_seconds,
        "role": role,
        "role_label": role_label(role),
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
            "This sign-in ticket has expired or was already used. "
            "Open the service again from the hub.",
        )

    username = payload.get("u", "")
    role = payload.get("r") or ROLE_USER

    token = create_access_token(username, role)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"username": username, "role": role, "role_label": role_label(role)},
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
        "defaultSection": "documents",
        "sections": [
            {"id": "documents", "title": "Documents", "icon": "📊", "path": "/"},
        ],
    }
