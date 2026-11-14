"""Sync orchestrator: Watcher -> Ingestion -> Summarizer -> Indexer -> Notifier, all inside one trace."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.agents.ingestion import PAGE_SOURCES, ingest_item, mark_superseded, reembed_stale, summarize_circular, watch_feeds
from app.agents.notifier import compose_alert, compose_digest, send_email
from app.config import get_settings
from app.core import runtime_settings as rs
from app.core.db import session_scope
from app.core.models import Circular
from app.observability import audit
from app.observability.events import bus
from app.observability.tracer import tracer
from app.rag.index import index

log = logging.getLogger("sentinel.pipeline")


class SyncState:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.running = False
        self.last_started: datetime | None = None
        self.last_finished: datetime | None = None
        self.last_result: dict | None = None
        self.last_trace_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "last_started": self.last_started.isoformat() if self.last_started else None,
            "last_finished": self.last_finished.isoformat() if self.last_finished else None,
            "last_result": self.last_result,
            "last_trace_id": self.last_trace_id,
        }


state = SyncState()


async def run_sync(trigger: str = "schedule", actor: str = "scheduler") -> dict:
    if state.lock.locked():
        return {"status": "skipped", "reason": "a sync is already running", **state.to_dict()}
    async with state.lock:
        state.running = True
        state.last_started = datetime.now(timezone.utc)
        bus.publish({"type": "sync", "phase": "start", "trigger": trigger})
        try:
            async with tracer.trace("sync", f"RBI sync ({trigger})", actor=actor, input={"trigger": trigger}) as tr:
                state.last_trace_id = tr.id
                result = await _run(tr.id, actor)
                tr.output = result
                if result.get("failed"):
                    tr.attributes["partial_failures"] = len(result["failed"])
            state.last_result = result
            if result.get("deferred") and get_settings().backfill_continuous:
                asyncio.get_running_loop().call_later(3, lambda: asyncio.ensure_future(run_sync(trigger="backfill", actor="scheduler")))
            audit.record(actor, "sync.run", resource="rbi-feeds", details={"trigger": trigger, **{k: v for k, v in result.items() if k != "items"}})
            return result
        except Exception as exc:
            log.exception("sync failed")
            state.last_result = {"status": "error", "error": str(exc)}
            return state.last_result
        finally:
            state.running = False
            state.last_finished = datetime.now(timezone.utc)
            bus.publish({"type": "sync", "phase": "end", "result": state.last_result})


def _baselined(settings: dict) -> set[str]:
    done = set(settings.get("baselined_sources") or [])
    if settings.get("baseline_done") and not settings.get("baselined_sources"):
        done |= {"notification", "press_release"}  # databases created before per-source baselines existed
    return done


async def _run(trace_id: str, actor: str) -> dict:
    from app.config import get_settings

    s = get_settings()
    with session_scope() as db:
        settings = rs.get_all(db)
    baselined = _baselined(settings)

    found, feed_report = await watch_feeds()

    # Feeds first (small, time-sensitive), then revisions, then listing-page backlog newest first.
    feeds = [i for i in found if i.source not in PAGE_SOURCES]
    revisions = [i for i in found if i.source in PAGE_SOURCES and i.update_of]
    backlog = sorted(
        (i for i in found if i.source in PAGE_SOURCES and not i.update_of),
        key=lambda i: i.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    feeds.sort(key=lambda i: i.published_at or datetime.min.replace(tzinfo=timezone.utc))
    queue = feeds + revisions + backlog
    todo, deferred = queue[: s.max_items_per_sync], queue[s.max_items_per_sync :]

    ingested: list[int] = []
    silent: set[int] = set()
    failed: list[dict] = []
    for item in todo:
        try:
            cid = await ingest_item(item)
            if cid:
                ingested.append(cid)
                if item.source not in baselined and not s.notify_on_first_sync:
                    silent.add(cid)
        except Exception as exc:
            failed.append({"title": item.title, "source": item.source, "error": f"{type(exc).__name__}: {exc}"})
            log.exception("ingestion failed", extra={"title": item.title})

    for cid in ingested:
        try:
            # first-time backlog gets fast rule-based briefs; new items get the model's brief
            await summarize_circular(cid, use_llm=(cid not in silent) or s.summarize_baseline_with_llm)
        except Exception as exc:
            failed.append({"circular_id": cid, "stage": "summarize", "error": str(exc)})

    async with tracer.span("Indexer", "mark superseded master circulars") as sp:
        sp.output = {"changed": mark_superseded()}

    async with tracer.span("Indexer", "rebuild hybrid index") as sp:
        info = await index.rebuild()
        if info["stale"]:
            await reembed_stale(info["stale"])
            info = await index.rebuild()
        sp.output = {"chunks_indexed": info["chunks"]}

    # a source's baseline is complete once a run reads it successfully and leaves nothing of it waiting
    ok_sources = {f["source"] for f in feed_report if f.get("ok")}
    waiting = {i.source for i in deferred}
    newly_baselined = sorted(src for src in ok_sources - waiting - baselined)
    if newly_baselined:
        with session_scope() as db:
            rs.put(db, "baselined_sources", sorted(baselined | set(newly_baselined)), actor="system")
            rs.put(db, "baseline_done", True, actor="system")

    to_notify = [c for c in ingested if c not in silent]
    notify = await _notify(to_notify, actor, settings)
    if silent:
        notify = {**notify, "baseline_silent": len(silent)}
    return {
        "status": "ok" if not failed else "partial",
        "feeds": feed_report,
        "new_items": sum(1 for i in found if not i.update_of),
        "revised_items": len(revisions),
        "ingested": len(ingested),
        "deferred": len(deferred),
        "deferred_by_source": {src: sum(1 for i in deferred if i.source == src) for src in waiting},
        "baselined_sources": sorted(baselined | set(newly_baselined)),
        "items": ingested,
        "failed": failed,
        "notification": notify,
        "index_size": index.size,
    }


async def _notify(ids: list[int], actor: str, settings: dict) -> dict:
    if not ids:
        return {"status": "nothing new to alert"}
    if not settings.get("notifications_enabled", True):
        return {"status": "disabled"}
    recipients = settings.get("subscribers") or []
    prios = set(settings.get("notify_priorities") or ["High", "Medium", "Low"])
    with session_scope() as db:
        circs = [c for c in db.query(Circular).filter(Circular.id.in_(ids)).all() if c.priority in prios]
    if not circs:
        return {"status": "filtered", "detail": "no items matched the notification priorities"}
    threshold = int(settings.get("digest_threshold") or 4)
    results = []
    from app.observability.logging import current_trace_id

    tid = current_trace_id.get()
    if len(circs) >= threshold:
        subject, html_body, text = compose_digest(circs, tid)
        results.append(await send_email("digest", recipients, subject, html_body, text, circular_ids=[c.id for c in circs], triggered_by=actor))
    else:
        for c in circs:
            subject, html_body, text = compose_alert(c, tid)
            results.append(await send_email("alert", recipients, subject, html_body, text, circular_ids=[c.id], triggered_by=actor))
    return {"status": "sent", "emails": results}


_summary_lock = asyncio.Lock()


async def run_summary_queue() -> dict:
    """Background: give documents that only have a rule-based brief an AI summary, newest first, a few per round."""
    from app.llm.provider import get_llm

    s = get_settings()
    if not get_llm().available or _summary_lock.locked():
        return {"status": "skipped"}
    async with _summary_lock:
        with session_scope() as db:
            ids = [
                cid
                for (cid,) in db.query(Circular.id)
                .filter(Circular.superseded_by.is_(None))
                .filter((Circular.summary_model.is_(None)) | (~Circular.summary_model.like("llm%")))
                .order_by(Circular.published_at.desc().nullslast(), Circular.id.desc())
                .limit(s.ai_summary_batch)
                .all()
            ]
            remaining = (
                db.query(Circular.id)
                .filter(Circular.superseded_by.is_(None))
                .filter((Circular.summary_model.is_(None)) | (~Circular.summary_model.like("llm%")))
                .count()
            )
        if not ids:
            return {"status": "all summarised"}
        done = 0
        async with tracer.trace("system", f"AI summary queue ({len(ids)} of {remaining} waiting)", actor="scheduler") as tr:
            for cid in ids:
                try:
                    out = await summarize_circular(cid, use_llm=True)
                    done += str(out.get("generated_by", "")).startswith("llm")
                except Exception as exc:
                    log.warning("queued summary failed", extra={"circular_id": cid, "error": str(exc)[:200]})
            tr.output = {"summarised": done, "remaining_before": remaining}
        bus.publish({"type": "summaries", "done": done, "remaining": remaining - done})
        return {"status": "ok", "summarised": done, "remaining": remaining - done}
