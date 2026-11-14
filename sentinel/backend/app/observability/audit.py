"""Hash-chained audit trail.

Each event's hash = SHA-256(canonical JSON of the event + previous event's hash). Altering, inserting or deleting any
historical row breaks every hash after it, which `verify_chain` detects and pinpoints.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.db import session_scope
from app.core.models import AuditEvent, utcnow
from app.core.utils import as_utc, jsonable
from app.observability.events import bus
from app.observability.logging import current_trace_id

GENESIS = "0" * 64
_lock = threading.Lock()
log = logging.getLogger("sentinel.audit")


def _canon_ts(dt) -> str:
    return as_utc(dt).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


def _digest(ts: str, actor: str, action: str, resource: str, details: Any, prev_hash: str) -> str:
    payload = json.dumps(
        {"ts": ts, "actor": actor, "action": action, "resource": resource, "details": details, "prev": prev_hash},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def record(
    actor: str,
    action: str,
    resource: str = "",
    details: dict | None = None,
    ip: str | None = None,
) -> None:
    """Append an audit event in its own short transaction.

    Callers must commit their own pending writes first (SQLite allows one writer at a time)."""
    details = jsonable(details or {})
    with _lock:
        with session_scope() as s:
            _append(s, actor, action, resource, details, ip)
    bus.publish({"type": "audit", "actor": actor, "action": action, "resource": resource})
    log.info("audit %s", action, extra={"actor": actor, "resource": resource})


def _append(db: Session, actor: str, action: str, resource: str, details: Any, ip: str | None) -> None:
    last = db.query(AuditEvent).order_by(AuditEvent.id.desc()).first()
    prev_hash = last.hash if last else GENESIS
    now = utcnow()
    ts = now.replace(microsecond=(now.microsecond // 1000) * 1000)
    h = _digest(_canon_ts(ts), actor, action, resource, details, prev_hash)
    db.add(
        AuditEvent(
            ts=ts,
            actor=actor,
            action=action,
            resource=resource,
            details=details,
            ip=ip,
            trace_id=current_trace_id.get(),
            prev_hash=prev_hash,
            hash=h,
        )
    )


def verify_chain(db: Session) -> dict[str, Any]:
    prev = GENESIS
    count = 0
    for ev in db.query(AuditEvent).order_by(AuditEvent.id.asc()).yield_per(500):
        expected = _digest(_canon_ts(ev.ts), ev.actor, ev.action, ev.resource, ev.details, prev)
        if ev.prev_hash != prev or ev.hash != expected:
            return {
                "intact": False,
                "verified": count,
                "broken_at_id": ev.id,
                "reason": "previous-hash mismatch" if ev.prev_hash != prev else "content hash mismatch",
            }
        prev = ev.hash
        count += 1
    return {"intact": True, "verified": count, "head": prev}
