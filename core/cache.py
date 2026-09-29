"""Thread-safe bounded TTL cache for derived market/AI computations."""
from __future__ import annotations

import time
from threading import Lock
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: float = 30.0, capacity: int = 256) -> None:
        self.ttl_seconds = max(0.0, ttl_seconds); self.capacity = max(1, capacity)
        self._items: dict[str, tuple[float, Any]] = {}; self._lock = Lock()

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._items) >= self.capacity and key not in self._items:
                self._items.pop(next(iter(self._items)))
            self._items[key] = (time.monotonic() + self.ttl_seconds, value)

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._items.get(key)
            if item is None: return None
            if item[0] < time.monotonic(): self._items.pop(key, None); return None
            return item[1]
