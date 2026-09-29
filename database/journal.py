"""Database-backed audit journal adapter."""
from __future__ import annotations

from database.models import TradeEvent
from database.sqlite import SQLiteStore
from database.trades import TradeRepository


class JournalRepository(TradeRepository):
    """Named adapter used by the UI and export services."""

    def __init__(self, path: str = "logs/zerotrace.sqlite3") -> None:
        super().__init__(SQLiteStore(path))

    def record(self, event: TradeEvent) -> None:
        self.append(event)
