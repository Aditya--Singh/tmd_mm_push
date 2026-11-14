"""Settings an administrator can change from the UI without a restart. Defaults come from the environment."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.models import AppSetting, utcnow


def defaults() -> dict[str, Any]:
    s = get_settings()
    return {
        "subscribers": s.recipient_list,
        "sync_interval_minutes": s.sync_interval_minutes,
        "notifications_enabled": s.email_enabled,
        "digest_threshold": s.digest_threshold,
        "notify_priorities": ["High", "Medium", "Low"],
        "baseline_done": False,
    }


def get_all(db: Session) -> dict[str, Any]:
    out = defaults()
    for row in db.query(AppSetting).all():
        out[row.key] = row.value
    return out


def get(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    return row.value if row is not None else defaults().get(key)


def put(db: Session, key: str, value: Any, actor: str | None = None) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value, updated_by=actor, updated_at=utcnow()))
    else:
        row.value = value
        row.updated_by = actor
        row.updated_at = utcnow()
    db.flush()
