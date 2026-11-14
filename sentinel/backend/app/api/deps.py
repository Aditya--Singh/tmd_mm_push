"""Authentication dependencies."""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.db import get_db
from app.core.models import User
from app.core.security import decode_token

bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "-")


def current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = creds.credentials if creds else request.query_params.get("token")
    if not get_settings().auth_enabled:
        return _default_user(db)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session expired. Sign in again.")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session token.")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account is disabled.")
    db.expunge(user)
    return user


def _default_user(db: Session) -> User:
    """Login switched off (AUTH_ENABLED=false): every request acts as the configured default user."""
    s = get_settings()
    user = db.query(User).filter(User.email == s.admin_email.lower()).first()
    if not user:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Default user not created yet; restart the app.")
    db.expunge(user)
    user.must_change_password = False
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access is required.")
    return user
