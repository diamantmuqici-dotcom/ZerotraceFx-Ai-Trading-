"""Bounded in-process memory for recent UI events, not credentials."""
from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any


class EventMemory:
    def __init__(self, capacity: int = 500) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=max(1, capacity))
        self._lock = Lock()

    def add(self, item: dict[str, Any]) -> None:
        with self._lock:
            self._items.append(dict(item))

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._items]
