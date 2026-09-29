"""Consistent SQLite backups."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from database.sqlite import SQLiteStore


def backup(store: SQLiteStore, destination: str) -> str:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    with store.connection() as source, sqlite3.connect(target) as dest:
        source.backup(dest)
    return str(target)
