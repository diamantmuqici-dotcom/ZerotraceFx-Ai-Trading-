"""Idempotent local database schema migrations."""
from __future__ import annotations

import sqlite3


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS trade_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL, event_time TEXT NOT NULL, symbol TEXT, action TEXT, ticket TEXT, volume REAL, entry REAL, exit REAL, profit REAL, confidence REAL, reason TEXT)""",
    """CREATE INDEX IF NOT EXISTS idx_trade_events_time ON trade_events(event_time)""",
    """CREATE INDEX IF NOT EXISTS idx_trade_events_symbol ON trade_events(symbol)""",
    """CREATE TABLE IF NOT EXISTS cache_entries (key TEXT PRIMARY KEY, value BLOB NOT NULL, expires_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY, sort_order INTEGER NOT NULL DEFAULT 0, favorite INTEGER NOT NULL DEFAULT 1)""",
    """CREATE TABLE IF NOT EXISTS themes (name TEXT PRIMARY KEY, definition TEXT NOT NULL, updated_at TEXT NOT NULL)""",
)


def apply_migrations(connection: sqlite3.Connection) -> None:
    """Apply all current schema statements in one transaction."""
    connection.execute("BEGIN")
    try:
        for statement in SCHEMA:
            connection.execute(statement)
        connection.execute("PRAGMA user_version=1")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
