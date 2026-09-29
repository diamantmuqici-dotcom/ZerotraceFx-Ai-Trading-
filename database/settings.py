"""Non-secret user preference storage.

MT5 credentials are intentionally not representable here. Settings persisted by
this repository are themes, layouts, watchlists and journal filters only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from database.sqlite import SQLiteStore


class SettingsRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def set(self, key: str, value: str) -> None:
        if not key or key.lower() in {"password", "mt5_password", "credential", "secret"}:
            raise ValueError("secret values are not supported in local settings")
        self.store.execute("INSERT OR REPLACE INTO app_settings(key,value,updated_at) VALUES (?,?,?)", (key, value, datetime.now(timezone.utc).isoformat()))

    def get(self, key: str, default: str = "") -> str:
        row = self.store.fetch_one("SELECT value FROM app_settings WHERE key=?", (key,))
        return str(row["value"]) if row else default
