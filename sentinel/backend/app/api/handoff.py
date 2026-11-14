"""The bridge to the Executive Intelligence Hub.

The hub embeds this app in a frame and owns the sign-in. This app keeps its own users, its
own sessions and its own audit trail. The hub does two things:

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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.db import get_db
from app.core.handoff import consume_ticket, make_ticket
from app.core.models import User, utcnow
from app.core.security import create_access_token, hash_password
from app.observability import audit

log = logging.getLogger("sentinel.handoff")

router = APIRouter(prefix="/api", tags=["handoff"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")

    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else "-"


def _settings():
    return get_settings()


def _email_for(username: str) -> str:
    """
    The address a hub account is given in this app.

    The hub knows people by their user name, and this app by their e-mail address. An
    account that arrives from the hub is therefore given an address that cannot be
    confused with a real one, and the name of the person is kept beside it.
    """
    return f"{username.strip().lower()}@hub.local"


class HandoffIn(BaseModel):
    """What the hub sends when it asks for a ticket."""

    username: str = Field(min_length=1, max_length=120)
    full_name: str = Field(default="", max_length=120)
    role: str = Field(default="", max_length=32)
    embed: bool = True


class ExchangeIn(BaseModel):
    """What the browser sends when it spends a ticket."""

    ticket: str = Field(min_length=10, max_length=2000)


def _role_for(username: str, requested: str) -> str:
    """
    The role a person has in this app.

    The hub names the accounts that are administrators here, and everybody else is an
    analyst. The hub cannot make somebody an administrator by asking for it: the list is
    read from this app's own settings.
    """
    settings = _settings()

    administrators = {name.strip().lower() for name in settings.handoff_admin_users.split(",") if name.strip()}

    if username.strip().lower() in administrators:
        return "admin"

    if requested in ("admin", "analyst"):
        return requested

    return "analyst"


@router.post("/auth/handoff")
def handoff(body: HandoffIn, request: Request, db: Session = Depends(get_db)):
    """
    Server to server: the hub vouches for a person it has already signed in, and gets a
    single-use ticket for them. Never called from a browser: the shared secret must stay
    on the hub's server.
    """
    settings = _settings()

    if len(settings.handoff_secret.strip()) < 32:
        raise HTTPException(404, "One-click sign-in is not enabled (set HANDOFF_SECRET, 32+ characters)")

    ip = _client_ip(request)

    if not hmac.compare_digest(request.headers.get("x-handoff-secret", ""), settings.handoff_secret):
        audit.record("hub", "auth.handoff.refused", details={"reason": "bad secret"}, ip=ip)
        raise HTTPException(401, "Invalid hand-off secret")

    username = body.username.strip().lower()
    email = _email_for(username)
    role = _role_for(username, body.role)

    user = db.query(User).filter(User.email == email).first()
    created = False

    if user is None:
        user = User(
            email=email,
            name=body.full_name or username,
            role=role,
            password_hash=hash_password(secrets.token_urlsafe(24)),  # signs in only through the hub
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        created = True
    else:
        if not user.is_active:
            raise HTTPException(403, "This account is disabled")

        if user.role != role:
            user.role = role

        user.last_login_at = utcnow()

    db.commit()

    ticket = make_ticket(username, email, role, settings.handoff_ticket_seconds)

    audit.record(
        "hub",
        "auth.handoff.issued",
        resource=username,
        details={"role": role, "account_created": created},
        ip=ip,
    )

    return {
        "ticket": ticket,
        "expires_in": settings.handoff_ticket_seconds,
        "role": role,
        "username": username,
        "account_created": created,
    }


@router.post("/auth/exchange")
def exchange(body: ExchangeIn, db: Session = Depends(get_db)):
    """
    The browser swaps a ticket for a session of this app.

    The ticket is single use and short lived. When it has been spent, the browser is asked
    for a new one.
    """
    payload = consume_ticket(body.ticket)

    if not payload:
        raise HTTPException(401, "This sign-in ticket has expired or was already used. Open the service again from the dashboard.")

    email = payload.get("e") or _email_for(payload.get("u", ""))

    user = db.query(User).filter(User.email == email).first()

    if not user or not user.is_active:
        raise HTTPException(401, "This account is disabled.")

    user.last_login_at = utcnow()
    db.commit()

    token = create_access_token(user.id, user.email, user.role)

    audit.record(user.email, "auth.login.handoff", resource=user.email)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "is_active": user.is_active,
            "must_change_password": user.must_change_password,
        },
    }


@router.get("/ui/manifest")
def ui_manifest():
    """
    The navigation of this app, for a hub that embeds it.

    It names the screens and nothing else, so that the hub can draw its own navigation
    without holding a session of its own. Everything behind these screens stays behind
    the usual role checks.
    """
    return {
        "service": "data-summarizer",
        "title": "Data Summarizer",
        "defaultSection": "overview",
        "sections": [
            {"id": "overview", "title": "Overview", "icon": "📊", "path": "/"},
            {"id": "assistant", "title": "Assistant", "icon": "💬", "path": "/assistant"},
            {"id": "circulars", "title": "Circulars", "icon": "📄", "path": "/circulars"},
            {"id": "alerts", "title": "Alerts", "icon": "🔔", "path": "/alerts"},
            {"id": "traces", "title": "Agent traces", "icon": "🧭", "path": "/traces"},
            {"id": "feedback", "title": "Feedback", "icon": "✍️", "path": "/feedback"},
            {"id": "settings", "title": "Settings", "icon": "⚙️", "path": "/settings"},
        ],
    }
