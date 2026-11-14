"""Structured JSON logging. Every line carries trace_id / span_id / agent so logs join cleanly with traces."""
from __future__ import annotations

import json
import logging
import sys
import threading
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)
current_span_id: ContextVar[str | None] = ContextVar("current_span_id", default=None)
current_agent: ContextVar[str | None] = ContextVar("current_agent", default=None)

_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {"message", "asctime"}
_ring: deque[dict[str, Any]] = deque(maxlen=3000)
_ring_lock = threading.Lock()
_in_emit = threading.local()


def _record_to_dict(record: logging.LogRecord) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
        "trace_id": getattr(record, "trace_id", None) or current_trace_id.get(),
        "span_id": getattr(record, "span_id", None) or current_span_id.get(),
        "agent": getattr(record, "agent", None) or current_agent.get(),
    }
    for k, v in record.__dict__.items():
        if k not in _RESERVED and k not in entry and not k.startswith("_"):
            entry[k] = v
    if record.exc_info:
        entry["exception"] = logging.Formatter().formatException(record.exc_info)
    return entry


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(_record_to_dict(record), default=str, ensure_ascii=False)


class RingAndBusHandler(logging.Handler):
    """Keeps recent log lines in memory and pushes them onto the live event bus."""

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(_in_emit, "active", False):
            return
        _in_emit.active = True
        try:
            entry = _record_to_dict(record)
            with _ring_lock:
                _ring.append(entry)
            from app.observability.events import bus

            bus.publish({"type": "log", **entry})
        except Exception:  # pragma: no cover - logging must never break the app
            pass
        finally:
            _in_emit.active = False


def recent_logs(limit: int = 500) -> list[dict[str, Any]]:
    with _ring_lock:
        return list(_ring)[-limit:]


def read_log_file(path: Path, limit: int = 1000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            lines.append(line)
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = JsonFormatter()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    file_handler = RotatingFileHandler(log_dir / "app.jsonl", maxBytes=20_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    ring = RingAndBusHandler()
    ring.setLevel(logging.INFO)
    root.addHandler(ring)

    for noisy in ("httpx", "httpcore", "apscheduler.executors.default", "uvicorn.access", "openai", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
