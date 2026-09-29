"""SQLite trade-event repository."""
from __future__ import annotations

from database.models import TradeEvent
from database.sqlite import SQLiteStore


class TradeRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def append(self, event: TradeEvent) -> None:
        self.store.execute(
            "INSERT INTO trade_events(event,event_time,symbol,action,ticket,volume,entry,exit,profit,confidence,reason) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (event.event, event.event_time.isoformat(), event.symbol, event.action, event.ticket, event.volume, event.entry, event.exit, event.profit, event.confidence, event.reason),
        )

    def recent_closes(self, limit: int = 100) -> list[dict]:
        return self.store.fetch_all("SELECT * FROM trade_events WHERE event='CLOSE' ORDER BY event_time DESC LIMIT ?", (max(1, min(limit, 1000)),))
