"""Traces, logs, audit trail, e-mail log, feedback, live events and admin settings."""
from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agents.notifier import EMAIL_RE, _shell, send_email
from app.api.deps import admin_user, client_ip, current_user
from app.config import get_settings
from app.core import runtime_settings as rs
from app.core.db import get_db
from app.core.models import AuditEvent, EmailLog, Feedback, Message, Span, Trace, User
from app.core.utils import iso
from app.llm.embeddings import get_embedder, get_reranker
from app.llm.provider import get_llm
from app.observability import audit
from app.observability.events import bus
from app.observability.logging import read_log_file, recent_logs
from app.observability.tracer import tracer
from app.rag.index import index

router = APIRouter(prefix="/api", tags=["observability"])


# ------------------------------------------------------------------ traces
def trace_out(t: Trace) -> dict:
    return {
        "id": t.id, "kind": t.kind, "name": t.name, "actor": t.actor, "status": t.status,
        "started_at": iso(t.started_at), "ended_at": iso(t.ended_at), "duration_ms": t.duration_ms,
        "tokens_in": t.tokens_in, "tokens_out": t.tokens_out, "error": t.error,
    }


@router.get("/traces")
def list_traces(
    kind: str | None = None,
    status: str | None = None,
    agent: str | None = None,
    q: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Trace)
    if user.role != "admin":  # analysts see their own chats plus system work
        query = query.filter((Trace.actor == user.email) | (Trace.kind.in_(["sync", "system"])))
    if kind:
        query = query.filter(Trace.kind == kind)
    if status:
        query = query.filter(Trace.status == status)
    if q:
        query = query.filter(Trace.name.ilike(f"%{q}%"))
    if agent:
        query = query.filter(Trace.id.in_(db.query(Span.trace_id).filter(Span.agent == agent)))
    total = query.count()
    rows = query.order_by(Trace.started_at.desc()).offset(offset).limit(limit).all()
    counts = dict(db.query(Span.trace_id, func.count(Span.id)).filter(Span.trace_id.in_([r.id for r in rows])).group_by(Span.trace_id).all())
    return {"total": total, "items": [{**trace_out(t), "spans": counts.get(t.id, 0)} for t in rows]}


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.get(Trace, trace_id)
    if not t:
        raise HTTPException(404, "Trace not found.")
    if user.role != "admin" and t.kind == "chat" and t.actor != user.email:
        raise HTTPException(403, "This trace belongs to another user.")
    spans = db.query(Span).filter(Span.trace_id == trace_id).order_by(Span.started_at).all()
    return {
        **trace_out(t),
        "input": t.input,
        "output": t.output,
        "attributes": t.attributes,
        "spans": [
            {
                "id": s.id, "parent_id": s.parent_id, "agent": s.agent, "name": s.name, "status": s.status,
                "started_at": iso(s.started_at), "ended_at": iso(s.ended_at), "duration_ms": s.duration_ms,
                "input": s.input, "output": s.output, "attributes": s.attributes, "error": s.error,
            }
            for s in spans
        ],
        "audit": [
            {"ts": iso(a.ts), "actor": a.actor, "action": a.action, "resource": a.resource}
            for a in db.query(AuditEvent).filter(AuditEvent.trace_id == trace_id).order_by(AuditEvent.id)
        ],
    }


# -------------------------------------------------------------------- logs
@router.get("/logs")
def get_logs(level: str | None = None, q: str | None = None, trace_id: str | None = None, limit: int = Query(300, le=2000),
             _: User = Depends(admin_user)):
    entries = recent_logs(2000)
    if len(entries) < limit:
        entries = read_log_file(get_settings().data_dir / "logs" / "app.jsonl", limit=2000)
    order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    if level:
        entries = [e for e in entries if order.get(e.get("level"), 0) >= order.get(level.upper(), 0)]
    if trace_id:
        entries = [e for e in entries if e.get("trace_id") == trace_id]
    if q:
        ql = q.lower()
        entries = [e for e in entries if ql in json.dumps(e, default=str).lower()]
    return entries[-limit:][::-1]


# ------------------------------------------------------------------- audit
@router.get("/audit")
def list_audit(action: str | None = None, actor: str | None = None, limit: int = Query(100, le=500), offset: int = 0,
               _: User = Depends(admin_user), db: Session = Depends(get_db)):
    q = db.query(AuditEvent)
    if action:
        q = q.filter(AuditEvent.action.ilike(f"{action}%"))
    if actor:
        q = q.filter(AuditEvent.actor.ilike(f"%{actor}%"))
    total = q.count()
    rows = q.order_by(AuditEvent.id.desc()).offset(offset).limit(limit).all()
    actions = [a for (a,) in db.query(AuditEvent.action).distinct().order_by(AuditEvent.action)]
    return {
        "total": total,
        "actions": actions,
        "items": [
            {"id": a.id, "ts": iso(a.ts), "actor": a.actor, "action": a.action, "resource": a.resource, "details": a.details,
             "ip": a.ip, "trace_id": a.trace_id, "hash": a.hash, "prev_hash": a.prev_hash}
            for a in rows
        ],
    }


@router.get("/audit/verify")
def verify_audit(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return audit.verify_chain(db)


@router.get("/audit/export.csv")
def export_audit(request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "ts_utc", "actor", "action", "resource", "details", "ip", "trace_id", "prev_hash", "hash"])
    for a in db.query(AuditEvent).order_by(AuditEvent.id).yield_per(500):
        w.writerow([a.id, iso(a.ts), a.actor, a.action, a.resource, json.dumps(a.details, default=str), a.ip, a.trace_id, a.prev_hash, a.hash])
    db.rollback()
    audit.record(admin.email, "audit.export", ip=client_ip(request))
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=audit-{datetime.now():%Y%m%d-%H%M}.csv"})


# ------------------------------------------------------------------ emails
@router.get("/emails")
def list_emails(limit: int = Query(100, le=500), _: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        {"id": e.id, "ts": iso(e.ts), "kind": e.kind, "recipients": e.recipients, "subject": e.subject, "status": e.status,
         "error": e.error, "circular_ids": e.circular_ids, "trace_id": e.trace_id, "triggered_by": e.triggered_by}
        for e in db.query(EmailLog).order_by(EmailLog.id.desc()).limit(limit)
    ]


# ---------------------------------------------------------------- feedback
class FeedbackIn(BaseModel):
    message_id: int | None = None
    rating: int = Field(ge=-1, le=5)
    category: str = "answer"
    tags: list[str] = []
    comment: str | None = Field(default=None, max_length=2000)


@router.post("/feedback")
def submit_feedback(body: FeedbackIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    trace_id = None
    if body.message_id:
        m = db.get(Message, body.message_id)
        if not m:
            raise HTTPException(404, "Message not found.")
        trace_id = m.trace_id
        existing = db.query(Feedback).filter(Feedback.message_id == m.id, Feedback.user_id == user.id).first()
        if existing:
            existing.rating, existing.tags, existing.comment = body.rating, body.tags, body.comment
            db.commit()
            audit.record(user.email, "feedback.update", resource=f"message:{m.id}", details={"rating": body.rating, "tags": body.tags}, ip=client_ip(request))
            return {"id": existing.id, "updated": True}
    fb = Feedback(user_id=user.id, message_id=body.message_id, rating=body.rating, category=body.category,
                  tags=body.tags, comment=body.comment, trace_id=trace_id)
    db.add(fb)
    db.commit()
    audit.record(user.email, "feedback.submit", resource=f"message:{body.message_id}" if body.message_id else body.category,
                 details={"rating": body.rating, "tags": body.tags}, ip=client_ip(request))
    return {"id": fb.id, "updated": False}


@router.get("/feedback")
def list_feedback(limit: int = Query(200, le=1000), user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(Feedback, User.email).join(User, Feedback.user_id == User.id)
    if user.role != "admin":
        q = q.filter(Feedback.user_id == user.id)
    rows = q.order_by(Feedback.id.desc()).limit(limit).all()
    items, tags = [], {}
    up = down = 0
    general = []
    for fb, email in rows:
        msg = db.get(Message, fb.message_id) if fb.message_id else None
        question = None
        if msg:
            prev = db.query(Message).filter(Message.conversation_id == msg.conversation_id, Message.id < msg.id, Message.role == "user").order_by(Message.id.desc()).first()
            question = prev.content if prev else None
        if fb.category == "answer":
            up += fb.rating > 0
            down += fb.rating < 0
        else:
            general.append(fb.rating)
        for t in fb.tags or []:
            tags[t] = tags.get(t, 0) + 1
        items.append({
            "id": fb.id, "user": email, "rating": fb.rating, "category": fb.category, "tags": fb.tags or [], "comment": fb.comment,
            "trace_id": fb.trace_id, "created_at": iso(fb.created_at), "message_id": fb.message_id,
            "question": question, "answer": msg.content[:600] if msg else None,
            "verification": (msg.meta or {}).get("verification", {}).get("verdict") if msg else None,
        })
    return {
        "stats": {"positive": up, "negative": down, "satisfaction": round(up / (up + down), 3) if up + down else None,
                  "general_avg": round(sum(general) / len(general), 2) if general else None, "tags": tags},
        "items": items,
    }


# ------------------------------------------------------------- live events
@router.get("/events/stream")
async def events_stream(request: Request, _: User = Depends(current_user)):
    q = bus.subscribe()

    async def gen():
        try:
            yield "data: " + json.dumps({"type": "hello", "recent": bus.recent(60)}, default=str) + "\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield "data: " + json.dumps(ev, default=str) + "\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- settings
class SettingsIn(BaseModel):
    subscribers: list[str] | None = None
    sync_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    notifications_enabled: bool | None = None
    digest_threshold: int | None = Field(default=None, ge=2, le=50)
    notify_priorities: list[str] | None = None


@router.get("/settings")
def get_settings_api(_: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_settings()
    return {
        "runtime": rs.get_all(db),
        "system": {
            "feeds": [{"source": src, "url": url} for src, url in list(s.feeds) + list(s.page_sources)],
            "max_items_per_sync": s.max_items_per_sync,
            "llm": get_llm().describe(),
            "embedding_model": get_embedder().name,
            "embedding_fallback": get_embedder().fallback_reason,
            "reranker": get_reranker().name,
            "index_chunks": index.size,
            "smtp": {"host": s.smtp_host, "port": s.smtp_port, "username": s.smtp_username, "from": s.email_from,
                     "password_configured": not s.smtp_dry_run},
            "notify_on_first_sync": s.notify_on_first_sync,
            "public_url": s.public_url,
        },
    }


@router.put("/settings")
def update_settings(body: SettingsIn, request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_none=True)
    if "subscribers" in changes:
        bad = [e for e in changes["subscribers"] if not EMAIL_RE.match(e.strip())]
        if bad:
            raise HTTPException(400, f"Not valid e-mail addresses: {', '.join(bad)}")
        changes["subscribers"] = list(dict.fromkeys(e.strip().lower() for e in changes["subscribers"]))
    if "notify_priorities" in changes and not set(changes["notify_priorities"]) <= {"High", "Medium", "Low"}:
        raise HTTPException(400, "Priorities must be High, Medium or Low.")
    before = rs.get_all(db)
    for k, v in changes.items():
        rs.put(db, k, v, actor=admin.email)
    db.commit()
    if "sync_interval_minutes" in changes:
        from app.scheduler import reschedule

        reschedule(changes["sync_interval_minutes"])
    audit.record(admin.email, "settings.update", resource="runtime-settings",
                 details={k: {"from": before.get(k), "to": v} for k, v in changes.items()}, ip=client_ip(request))
    return rs.get_all(db)


@router.post("/settings/test-email")
async def test_email(request: Request, admin: User = Depends(admin_user)):
    from app.core.db import session_scope

    with session_scope() as db:
        recipients = rs.get(db, "subscribers") or [admin.email]
    async with tracer.trace("email", "Test e-mail", actor=admin.email) as tr:
        body = ('<p style="font-size:14px">This is a test message from RBI Regulatory Sentinel. If you can read it, '
                'alert e-mails will reach this mailbox.</p>')
        result = await send_email("test", recipients, "[RBI Sentinel] Test e-mail", _shell("Delivery test", body, tr.id),
                                  "Test message from RBI Regulatory Sentinel.", triggered_by=admin.email)
        tr.output = result
    return result


@router.get("/health")
def health():
    return {"status": "ok", "index_chunks": index.size, "llm": get_llm().describe()["provider"], "time": datetime.now(timezone.utc).isoformat()}


@router.post("/system/llm-check")
async def llm_check(_: User = Depends(admin_user)):
    async with tracer.trace("system", "LLM health check"):
        return await get_llm().health_check()


@router.post("/system/reindex")
async def reindex(request: Request, admin: User = Depends(admin_user)):
    from app.agents.ingestion import reembed_stale

    async with tracer.trace("system", "Rebuild index", actor=admin.email) as tr:
        info = await index.rebuild()
        if info["stale"]:
            await reembed_stale(info["stale"])
            info = await index.rebuild()
        tr.output = {"chunks": info["chunks"]}
    audit.record(admin.email, "index.rebuild", details={"chunks": info["chunks"]}, ip=client_ip(request))
    return {"chunks": info["chunks"]}
