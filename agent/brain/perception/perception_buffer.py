"""
PerceptionBuffer — Async ring buffer for raw perception events.

Receives events pushed from JS PerceptionWorker via IPC.
Thread-safe via asyncio.Lock.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class PerceptionBuffer:
    """Async ring buffer for raw perception events from JS."""

    def __init__(self, max_size: int = 500):
        self._events: list = []
        self._max_size = max_size
        self._lock = asyncio.Lock()

    @property
    def is_empty(self) -> bool:
        return len(self._events) == 0

    async def append(self, event: dict):
        """Append a single event (thread-safe)."""
        async with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_size:
                self._events = self._events[-self._max_size:]

    async def extend(self, events: list):
        """Batch append events (thread-safe)."""
        if not events:
            return
        async with self._lock:
            self._events.extend(events)
            if len(self._events) > self._max_size:
                self._events = self._events[-self._max_size:]

    async def consume(self) -> list:
        """Drain all events and return them (thread-safe)."""
        async with self._lock:
            events = self._events
            self._events = []
            return events
