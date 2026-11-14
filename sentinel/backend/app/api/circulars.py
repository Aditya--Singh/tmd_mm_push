"""Circulars, sync control and dashboard."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.agents.ingestion import circular_brief, summarize_circular
from app.agents.notifier import compose_alert, send_email
from app.agents.pipeline import run_sync, state as sync_state
from app.api.deps import admin_user, client_ip, current_user
from app.core.db import get_db, session_scope
from app.core.models import Circular, EmailLog, Feedback, Message, Span, Trace, User
from app.core.utils import as_utc, iso
from app.llm.embeddings import get_embedder
from app.llm.provider import get_llm
from app.observability import audit
from app.observability.tracer import tracer
from app.rag.index import index

router = APIRouter(prefix="/api", tags=["circulars"])

AGENTS = [
    ("Watcher", "Reads RBI feeds and the Master Circular / Master Direction pages; detects new and revised items"),
    ("Ingestion", "Extracts text, metadata and PDF links; chunks and embeds"),
    ("Summarizer", "Writes the structured brief: key points, actions, applicability"),
    ("Indexer", "Maintains the hybrid dense + BM25 search index"),
    ("Notifier", "Composes and sends alert, digest and on-demand e-mails"),
    ("Router", "Classifies each question and rewrites it as a standalone query"),
    ("Retriever", "Hybrid search with reciprocal rank fusion"),
    ("Answer", "Drafts grounded answers with numbered citations"),
    ("Verifier", "Checks citations and grounding of every answer"),
    ("Memory", "Loads context and compresses long conversations"),
    ("Briefing", "Writes management briefings on recent publications"),
    ("LLM", "Language-model calls (provider, model, tokens, latency)"),
]


@router.get("/meta")
def meta():
    """Public branding for the login page (no secrets)."""
    from app.config import get_settings as _gs

    s = _gs()
    return {"app_name": s.app_name, "org_name": s.org_name, "org_short": s.org_short, "org_unit": s.org_unit,
            "auth_enabled": s.auth_enabled, "email_enabled": s.email_enabled,
            # The addresses the hub may drive this app from. The browser uses them to
            # decide whether a message may be trusted.
            "embed_parent_origins": [o.strip() for o in s.embed_parent_origins.split(",") if o.strip()]}


@router.get("/circulars")
def list_circulars(
    q: str | None = None,
    source: str | None = None,
    revised: bool | None = None,
    current_only: bool = False,
    financial_year: str | None = None,
    priority: str | None = None,
    applicability: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Circular)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Circular.title.ilike(like), Circular.rbi_ref.ilike(like), Circular.dept_ref.ilike(like), Circular.text.ilike(like)))
    if source:
        query = query.filter(Circular.source == source)
    if revised:
        query = query.filter(Circular.revision > 0)
    if current_only:
        query = query.filter(Circular.superseded_by.is_(None))
    if financial_year and re.fullmatch(r"\d{4}-\d{4}", financial_year):
        start = int(financial_year[:4])
        lo = datetime(start, 4, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        hi = datetime(start + 1, 4, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        query = query.filter(Circular.published_at >= lo, Circular.published_at < hi)
    if priority:
        query = query.filter(Circular.priority == priority)
    if applicability:
        query = query.filter(Circular.applicability == applicability)
    total = query.count()
    rows = query.order_by(Circular.published_at.desc().nullslast(), Circular.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"total": total, "page": page, "size": size, "items": [circular_brief(c) for c in rows]}


@router.get("/circulars/{cid}")
def get_circular(cid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Circular, cid)
    if not c:
        raise HTTPException(404, "Circular not found.")
    out = circular_brief(c)
    out["text"] = c.text
    out["signatory"] = c.signatory
    out["created_at"] = iso(c.created_at)
    out["summary_model"] = c.summary_model
    out["emails"] = [
        {"ts": iso(e.ts), "kind": e.kind, "status": e.status, "recipients": e.recipients}
        for e in db.query(EmailLog).order_by(EmailLog.id.desc()).limit(200).all()
        if e.circular_ids and cid in e.circular_ids
    ]
    return out


@router.post("/circulars/{cid}/summarize")
async def resummarize(cid: int, request: Request, user: User = Depends(current_user)):
    async with tracer.trace("system", f"Re-summarize circular {cid}", actor=user.email):
        result = await summarize_circular(cid)
    audit.record(user.email, "circular.resummarize", resource=f"circular:{cid}", ip=client_ip(request))
    return result


@router.post("/circulars/{cid}/email")
async def email_circular(cid: int, request: Request, user: User = Depends(current_user)):
    with session_scope() as db:
        c = db.get(Circular, cid)
        if not c:
            raise HTTPException(404, "Circular not found.")
    async with tracer.trace("email", f"E-mail circular {cid} to {user.email}", actor=user.email) as tr:
        if not c.summary:
            await summarize_circular(cid)
            with session_scope() as db:
                c = db.get(Circular, cid)
        subject, html_body, text = compose_alert(c, tr.id)
        result = await send_email("summary", [user.email], subject, html_body, text, circular_ids=[cid], triggered_by=user.email)
        tr.output = result
    return result


@router.post("/sync")
async def trigger_sync(request: Request, user: User = Depends(current_user)):
    if sync_state.running:
        return {"status": "running", **sync_state.to_dict()}
    import asyncio

    asyncio.create_task(run_sync(trigger="manual", actor=user.email))
    audit.record(user.email, "sync.trigger", resource="rbi-feeds", ip=client_ip(request))
    return {"status": "started"}


@router.get("/sync/status")
def sync_status(_: User = Depends(current_user)):
    return sync_state.to_dict()


@router.get("/dashboard")
def dashboard(_: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    week = now - timedelta(days=7)
    day = now - timedelta(days=1)
    total = db.query(func.count(Circular.id)).scalar() or 0
    new_week = db.query(func.count(Circular.id)).filter(Circular.published_at >= week).scalar() or 0
    high_week = db.query(func.count(Circular.id)).filter(Circular.published_at >= week, Circular.priority == "High").scalar() or 0
    emails_week = db.query(func.count(EmailLog.id)).filter(EmailLog.ts >= week, EmailLog.status.in_(["sent", "dry_run"])).scalar() or 0
    chats_week = db.query(func.count(Message.id)).filter(Message.role == "user", Message.created_at >= week).scalar() or 0
    fb = db.query(Feedback.rating).filter(Feedback.category == "answer").all()
    positive = sum(1 for (r,) in fb if r > 0)
    verifs = [m.meta.get("verification", {}) for m in db.query(Message).filter(Message.role == "assistant").order_by(Message.id.desc()).limit(200) if m.meta]
    scores = [v.get("score") for v in verifs if v and isinstance(v.get("score"), (int, float))]

    # agent health over the last 24h
    spans = db.query(Span.agent, Span.status, Span.duration_ms, Span.started_at).filter(Span.started_at >= day).all()
    last_seen = dict(db.query(Span.agent, func.max(Span.started_at)).group_by(Span.agent).all())
    per: dict[str, dict] = {}
    for agent, status, dur, _ts in spans:
        a = per.setdefault(agent, {"runs": 0, "errors": 0, "durations": []})
        a["runs"] += 1
        a["errors"] += status == "error"
        if dur is not None:
            a["durations"].append(dur)
    agents = []
    for name, desc in AGENTS:
        a = per.get(name, {"runs": 0, "errors": 0, "durations": []})
        d = sorted(a["durations"])
        agents.append({
            "name": name, "description": desc, "runs_24h": a["runs"], "errors_24h": a["errors"],
            "p50_ms": round(d[len(d) // 2], 1) if d else None,
            "p95_ms": round(d[min(len(d) - 1, int(len(d) * 0.95))], 1) if d else None,
            "last_run": iso(last_seen.get(name)),
            "health": "idle" if not a["runs"] else ("degraded" if a["errors"] / a["runs"] > 0.2 else "healthy"),
        })

    # publications per day (last 30 days)
    month = now - timedelta(days=30)
    per_day = Counter()
    by_prio = Counter()
    for pub, prio in db.query(Circular.published_at, Circular.priority).filter(Circular.published_at >= month).all():
        per_day[as_utc(pub).date().isoformat()] += 1
        by_prio[prio] += 1
    series = []
    for i in range(29, -1, -1):
        d = (now - timedelta(days=i)).date().isoformat()
        series.append({"date": d, "count": per_day.get(d, 0)})

    by_source = dict(db.query(Circular.source, func.count(Circular.id)).group_by(Circular.source).all())
    revised_week = db.query(func.count(Circular.id)).filter(Circular.updated_at >= week).scalar() or 0
    from app.config import get_settings as _gs

    _s = _gs()
    report = {f["source"]: f for f in ((sync_state.last_result or {}).get("feeds") or [])}
    deferred = (sync_state.last_result or {}).get("deferred_by_source") or {}
    with session_scope() as _db:
        from app.core import runtime_settings as _rs

        baselined = set(_rs.get(_db, "baselined_sources") or [])
    coverage = []
    for src, url in list(_s.feeds) + list(_s.page_sources):
        r = report.get(src, {})
        coverage.append({
            "source": src, "url": url, "indexed": by_source.get(src, 0),
            "last_ok": r.get("ok"), "last_entries": r.get("entries"), "last_error": r.get("error"),
            "waiting": deferred.get(src, 0), "baselined": src in baselined,
        })

    latest = db.query(Circular).order_by(Circular.published_at.desc().nullslast(), Circular.id.desc()).limit(8).all()
    recent_traces = db.query(Trace).order_by(Trace.started_at.desc()).limit(8).all()
    return {
        "kpis": {
            "indexed": total,
            "new_7d": new_week,
            "high_priority_7d": high_week,
            "emails_7d": emails_week,
            "questions_7d": chats_week,
            "feedback_positive_rate": round(positive / len(fb), 3) if fb else None,
            "feedback_count": len(fb),
            "avg_groundedness": round(sum(scores) / len(scores), 3) if scores else None,
            "chunks": index.size,
            "revised_7d": revised_week,
            "master_documents": by_source.get("master_circular", 0) + by_source.get("master_direction", 0),
            "ai_summarised": db.query(func.count(Circular.id)).filter(Circular.summary_model.like("llm%")).scalar() or 0,
            "superseded": db.query(func.count(Circular.id)).filter(Circular.superseded_by.isnot(None)).scalar() or 0,
        },
        "coverage": coverage,
        "agents": agents,
        "series": series,
        "by_priority": dict(by_prio),
        "latest": [circular_brief(c) for c in latest],
        "recent_traces": [
            {"id": t.id, "kind": t.kind, "name": t.name, "status": t.status, "duration_ms": t.duration_ms, "started_at": iso(t.started_at)}
            for t in recent_traces
        ],
        "sync": sync_state.to_dict(),
        "system": {
            "llm": get_llm().describe(),
            "embedding_model": get_embedder().name,
            "embedding_fallback": get_embedder().fallback_reason,
            "index_built_at": index.built_at.isoformat() if index.built_at else None,
        },
    }
