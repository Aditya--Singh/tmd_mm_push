"""Password hashing (bcrypt), JWT issuance and a small in-memory login lock-out."""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: int, email: str, role: str) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.jwt_expiry_minutes)).timestamp()),
        "iss": "rbi-sentinel",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM], issuer="rbi-sentinel")


def password_policy_errors(password: str) -> list[str]:
    errs = []
    if len(password) < 10:
        errs.append("at least 10 characters")
    if not any(c.isupper() for c in password):
        errs.append("an uppercase letter")
    if not any(c.islower() for c in password):
        errs.append("a lowercase letter")
    if not any(c.isdigit() for c in password):
        errs.append("a digit")
    if not any(not c.isalnum() for c in password):
        errs.append("a symbol")
    return errs


class LoginGuard:
    """Counts failed logins per (email, ip) and locks the pair out for a while after too many failures."""

    def __init__(self) -> None:
        self._fails: dict[str, list[float]] = defaultdict(list)

    def _key(self, email: str, ip: str) -> str:
        return f"{email.lower()}|{ip}"

    def locked_for(self, email: str, ip: str) -> int:
        s = get_settings()
        window = s.login_lockout_minutes * 60
        now = time.time()
        fails = [t for t in self._fails[self._key(email, ip)] if now - t < window]
        self._fails[self._key(email, ip)] = fails
        if len(fails) >= s.login_max_failures:
            return int(window - (now - fails[0]))
        return 0

    def fail(self, email: str, ip: str) -> None:
        self._fails[self._key(email, ip)].append(time.time())

    def reset(self, email: str, ip: str) -> None:
        self._fails.pop(self._key(email, ip), None)


login_guard = LoginGuard()
