"""Bounded expiring local cache for non-sensitive derived AI data."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from database.sqlite import SQLiteStore


class CacheRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def put(self, key: str, value: object, expires_at: datetime | None = None) -> None:
        self.store.execute("INSERT OR REPLACE INTO cache_entries(key,value,expires_at) VALUES (?,?,?)", (key, json.dumps(value), expires_at.isoformat() if expires_at else None))

    def get(self, key: str) -> object | None:
        row = self.store.fetch_one("SELECT value, expires_at FROM cache_entries WHERE key=?", (key,))
        if not row or (row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc)):
            return None
        return json.loads(row["value"])
