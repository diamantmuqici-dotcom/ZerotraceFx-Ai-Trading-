"""Theme definition persistence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from database.sqlite import SQLiteStore


class ThemeRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def save(self, name: str, definition: dict) -> None:
        self.store.execute("INSERT OR REPLACE INTO themes(name,definition,updated_at) VALUES (?,?,?)", (name, json.dumps(definition), datetime.now(timezone.utc).isoformat()))

    def load(self, name: str) -> dict:
        row = self.store.fetch_one("SELECT definition FROM themes WHERE name=?", (name,))
        return json.loads(row["definition"]) if row else {}
