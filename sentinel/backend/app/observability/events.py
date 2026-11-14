"""In-process publish/subscribe bus that feeds the live activity stream (SSE) in the UI."""
from __future__ import annotations

import asyncio
import threading
from collections import deque
from typing import Any


class EventBus:
    def __init__(self, history: int = 300) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._recent: deque[dict[str, Any]] = deque(maxlen=history)
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def recent(self, n: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._recent)[-n:]

    def _deliver(self, event: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow consumer: drop rather than block agents

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._recent.append(event)
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._deliver(event)
        else:
            loop.call_soon_threadsafe(self._deliver, event)


bus = EventBus()
