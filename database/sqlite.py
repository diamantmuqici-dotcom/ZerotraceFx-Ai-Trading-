"""Small WAL-backed SQLite store with one connection per operation."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from database.migrations import apply_migrations


class SQLiteStore:
    """Thread-safe local database facade; no network or secret storage."""

    def __init__(self, path: str = "logs/zerotrace.sqlite3") -> None:
        self.path = str(Path(path))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.migrate()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            try:
                yield connection
            finally:
                connection.close()

    def migrate(self) -> None:
        with self.connection() as connection:
            apply_migrations(connection)

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.connection() as connection:
            return int(connection.execute(sql, tuple(params)).rowcount)

    def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self.connection() as connection:
            return [dict(row) for row in connection.execute(sql, tuple(params)).fetchall()]

    def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None
