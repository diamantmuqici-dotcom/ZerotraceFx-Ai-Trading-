"""Persistence DTOs kept independent from broker objects."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TradeEvent:
    event: str
    event_time: datetime
    symbol: str = ""
    action: str = ""
    ticket: str = ""
    volume: float = 0.0
    entry: float = 0.0
    exit: float = 0.0
    profit: float = 0.0
    confidence: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class WatchlistItem:
    symbol: str
    sort_order: int = 0
    favorite: bool = True
