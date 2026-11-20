"""The sessions of this app.

The app keeps no accounts of its own. The hub signs a person in, vouches for them with a
single-use ticket, and the person is given a token of this app. The token carries the role
the person holds in the News Feed of the platform: `admin` or `user`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

ALGORITHM = "HS256"

#: The roles of this app. They are the roles of the News Feed of the platform.
ROLE_ADMIN = "admin"
ROLE_USER = "user"

ROLE_LABELS: dict[str, str] = {
    ROLE_ADMIN: "Administrator",
    ROLE_USER: "Reader",
}

bearer = HTTPBearer(auto_error=False)


def create_access_token(username: str, role: str) -> str:
    """A token for a person, carrying the role the hub stated."""
    settings = get_settings()
    now = datetime.now(timezone.utc)

    payload = {
        "sub": username,
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expiry_minutes)).timestamp()),
        "iss": "pnb-data-analyzer",
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """What a token says, or an error when it is not a valid one."""
    settings = get_settings()

    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITHM],
        issuer="pnb-data-analyzer",
    )


def role_label(role: str) -> str:
    """The name of a role, to show to a person."""
    return ROLE_LABELS.get(role, role.title() if role else "Unknown")


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """
    The person who is signed in, as the hub handed them over.

    The session is this app's own: the hub gave a single-use ticket, which was swapped for
    this token. The role is the role the person holds in the News Feed of the platform.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This service is opened from the Executive Intelligence Hub. Sign in there.",
        )

    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The session has expired. Open the service again from the hub.",
        )

    return {
        "username": payload.get("username") or payload.get("sub") or "",
        "role": payload.get("role") or ROLE_USER,
    }


def require_admin(session: dict = Depends(current_session)) -> dict:
    """Only an administrator may do this."""
    if session.get("role") != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action needs the role of an administrator.",
        )

    return session
