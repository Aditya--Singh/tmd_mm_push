"""Sign-in tickets for the Executive Intelligence Hub.

The hub embeds this app in a frame and owns the sign-in. It asks this server, on the
person's behalf, for a single-use ticket, hands that ticket to the frame over the message
bridge, and the frame swaps it for a session of this app.

The ticket is never a session and never appears in a URL. The shared secret stays on the
hub's server: a browser cannot ask for a ticket.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from app.config import get_settings


def _secret() -> bytes:
    """The secret the tickets are signed with."""
    return get_settings().handoff_secret.encode("utf-8")


def make_ticket(username: str, email: str, role: str, seconds: int) -> str:
    """A short-lived, single-use sign-in ticket for the hub."""
    payload = {
        "u": username,
        "e": email,
        "r": role,
        "exp": int(time.time()) + max(15, seconds),
        "n": secrets.token_hex(12),
        "t": "ticket",
    }

    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()

    return f"{body}.{signature}"


def read_ticket(ticket: str) -> dict | None:
    """What a ticket says, or nothing when it is not a valid one."""
    try:
        body, signature = ticket.rsplit(".", 1)
    except (AttributeError, ValueError):
        return None

    expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected):
        return None

    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, json.JSONDecodeError):
        return None

    if payload.get("t") != "ticket":
        return None

    if int(payload.get("exp", 0)) < time.time():
        return None

    return payload


_used: dict[str, float] = {}


def consume_ticket(ticket: str) -> dict | None:
    """
    Spend a ticket.

    A ticket can be spent once only. The second attempt is refused, so a ticket that is
    copied out of a message cannot be used a second time.
    """
    payload = read_ticket(ticket)

    if not payload:
        return None

    now = time.time()

    for key in [key for key, exp in _used.items() if exp < now]:
        _used.pop(key, None)

    if payload["n"] in _used:
        return None

    _used[payload["n"]] = float(payload["exp"])

    return payload
