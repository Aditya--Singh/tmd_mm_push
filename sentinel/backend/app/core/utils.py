"""Small shared helpers."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime | None) -> str | None:
    dt = as_utc(dt)
    return dt.isoformat() if dt else None


def truncate(value: Any, limit: int = 4000) -> Any:
    """Keep trace payloads readable and bounded."""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"… [+{len(value) - limit} chars]"
    if isinstance(value, dict):
        return {k: truncate(v, limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [truncate(v, limit) for v in list(value)[:50]]
        if len(value) > 50:
            items.append(f"… [+{len(value) - 50} items]")
        return items
    return value


def jsonable(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return str(value)


_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def extract_json(text: str) -> dict | None:
    """Parse the first JSON object in an LLM response (tolerates code fences and chatter)."""
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK.search(cleaned)
    if not m:
        return None
    candidate = m.group(0)
    # progressively trim trailing text until it parses
    for end in range(len(candidate), 0, -1):
        if candidate[end - 1] != "}":
            continue
        try:
            obj = json.loads(candidate[:end])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            continue
    return None


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
