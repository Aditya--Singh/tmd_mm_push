"""Passwords and the sessions of this app."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.db import get_db

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
    settings = get_settings()

    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITHM],
        issuer="pnb-data-analyzer",
    )


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.title() if role else "Unknown")


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
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
