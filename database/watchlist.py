"""Favorite-symbol persistence."""
from __future__ import annotations

from database.sqlite import SQLiteStore


class WatchlistRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def replace(self, symbols: list[str]) -> None:
        with self.store.connection() as connection:
            connection.execute("DELETE FROM watchlist")
            connection.executemany("INSERT INTO watchlist(symbol,sort_order) VALUES (?,?)", [(s.strip().upper(), i) for i, s in enumerate(symbols) if s.strip()])

    def list(self) -> list[str]:
        return [row["symbol"] for row in self.store.fetch_all("SELECT symbol FROM watchlist WHERE favorite=1 ORDER BY sort_order")]
