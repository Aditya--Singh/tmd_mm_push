"""Agent tracing.

A *trace* is one end-to-end unit of work (a chat turn, an RBI sync run). Inside it, every agent step opens a *span*
that records who ran (agent), what it received (input), what it produced (output), how long it took, which model and
how many tokens it used, and whether it failed. Spans are persisted the moment they start (status=running) so the UI
can show live progress, and are completed when they end. Nothing is sampled: every agent action is reconstructable.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.core.db import session_scope
from app.core.models import Span, Trace, utcnow
from app.core.utils import jsonable, truncate
from app.observability.events import bus
from app.observability.logging import current_agent, current_span_id, current_trace_id

log = logging.getLogger("sentinel.tracer")

_token_totals: dict[str, list[int]] = {}


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class SpanHandle:
    id: str
    trace_id: str
    agent: str
    name: str
    output: Any = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"

    def set(self, **attrs: Any) -> None:
        self.attributes.update(attrs)

    def add_usage(self, model: str | None, tokens_in: int, tokens_out: int, provider: str | None = None) -> None:
        self.attributes["gen_ai.request.model"] = model
        if provider:
            self.attributes["gen_ai.system"] = provider
        self.attributes["gen_ai.usage.input_tokens"] = self.attributes.get("gen_ai.usage.input_tokens", 0) + tokens_in
        self.attributes["gen_ai.usage.output_tokens"] = (
            self.attributes.get("gen_ai.usage.output_tokens", 0) + tokens_out
        )
        tot = _token_totals.setdefault(self.trace_id, [0, 0])
        tot[0] += tokens_in
        tot[1] += tokens_out


@dataclass
class TraceHandle:
    id: str
    kind: str
    name: str
    output: Any = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"


class Tracer:
    @asynccontextmanager
    async def trace(
        self, kind: str, name: str, actor: str | None = None, input: Any = None, attributes: dict | None = None
    ) -> AsyncIterator[TraceHandle]:
        """Open a trace. If one is already active (nested call), this degrades to a span inside it."""
        existing = current_trace_id.get()
        if existing:
            async with self.span(kind.title(), name, input=input) as sp:
                handle = TraceHandle(id=existing, kind=kind, name=name)
                yield handle
                sp.output = handle.output
                sp.status = handle.status
            return

        trace_id = _new_id()
        started = time.perf_counter()
        with session_scope() as db:
            db.add(
                Trace(
                    id=trace_id,
                    kind=kind,
                    name=name[:255],
                    actor=actor,
                    status="running",
                    input=jsonable(truncate(input)) if input is not None else None,
                    attributes=jsonable(attributes or {}),
                )
            )
        _token_totals[trace_id] = [0, 0]
        prev_trace, prev_span, prev_agent = current_trace_id.get(), current_span_id.get(), current_agent.get()
        current_trace_id.set(trace_id)
        current_span_id.set(None)
        bus.publish({"type": "trace", "phase": "start", "trace_id": trace_id, "kind": kind, "name": name, "actor": actor})
        handle = TraceHandle(id=trace_id, kind=kind, name=name)
        error: str | None = None
        try:
            yield handle
        except BaseException as exc:  # includes cancellation of a streaming request
            handle.status = "error" if not isinstance(exc, GeneratorExit) else "cancelled"
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            duration = (time.perf_counter() - started) * 1000
            tokens = _token_totals.pop(trace_id, [0, 0])
            try:
                with session_scope() as db:
                    row = db.get(Trace, trace_id)
                    if row:
                        row.status = handle.status
                        row.ended_at = utcnow()
                        row.duration_ms = round(duration, 1)
                        row.output = jsonable(truncate(handle.output)) if handle.output is not None else None
                        row.attributes = jsonable({**(row.attributes or {}), **handle.attributes})
                        row.tokens_in, row.tokens_out = tokens
                        row.error = error
            except Exception:  # pragma: no cover
                log.exception("failed to close trace")
            bus.publish(
                {
                    "type": "trace",
                    "phase": "end",
                    "trace_id": trace_id,
                    "kind": kind,
                    "name": name,
                    "status": handle.status,
                    "duration_ms": round(duration, 1),
                }
            )
            current_trace_id.set(prev_trace)
            current_span_id.set(prev_span)
            current_agent.set(prev_agent)

    @asynccontextmanager
    async def span(
        self, agent: str, name: str, input: Any = None, attributes: dict | None = None
    ) -> AsyncIterator[SpanHandle]:
        trace_id = current_trace_id.get()
        if trace_id is None:  # span outside any trace: create an implicit system trace
            async with self.trace("system", f"{agent}: {name}") as _t:
                async with self.span(agent, name, input, attributes) as sp:
                    yield sp
            return

        span_id = _new_id()
        parent_id = current_span_id.get()
        started = time.perf_counter()
        with session_scope() as db:
            db.add(
                Span(
                    id=span_id,
                    trace_id=trace_id,
                    parent_id=parent_id,
                    agent=agent,
                    name=name[:255],
                    status="running",
                    input=jsonable(truncate(input)) if input is not None else None,
                    attributes=jsonable(attributes or {}),
                )
            )
        prev_span, prev_agent = current_span_id.get(), current_agent.get()
        current_span_id.set(span_id)
        current_agent.set(agent)
        bus.publish(
            {
                "type": "span",
                "phase": "start",
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_id": parent_id,
                "agent": agent,
                "name": name,
            }
        )
        handle = SpanHandle(id=span_id, trace_id=trace_id, agent=agent, name=name, attributes=dict(attributes or {}))
        error: str | None = None
        try:
            yield handle
        except BaseException as exc:
            handle.status = "cancelled" if isinstance(exc, GeneratorExit) else "error"
            error = f"{type(exc).__name__}: {exc}"
            if handle.status == "error":
                log.warning("agent step failed", extra={"step": name, "error": error})
            raise
        finally:
            duration = (time.perf_counter() - started) * 1000
            try:
                with session_scope() as db:
                    row = db.get(Span, span_id)
                    if row:
                        row.status = handle.status
                        row.ended_at = utcnow()
                        row.duration_ms = round(duration, 1)
                        row.output = jsonable(truncate(handle.output)) if handle.output is not None else None
                        row.attributes = jsonable(handle.attributes)
                        row.error = error
            except Exception:  # pragma: no cover
                log.exception("failed to close span")
            bus.publish(
                {
                    "type": "span",
                    "phase": "end",
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "parent_id": parent_id,
                    "agent": agent,
                    "name": name,
                    "status": handle.status,
                    "duration_ms": round(duration, 1),
                }
            )
            current_span_id.set(prev_span)
            current_agent.set(prev_agent)


tracer = Tracer()
