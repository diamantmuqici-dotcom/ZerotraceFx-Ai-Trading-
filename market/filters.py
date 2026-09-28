"""Session detection and the high-impact economic-news filter."""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from config.constants import KILLZONES_UTC, SESSIONS_UTC
from utils.logging_setup import get_logger

logger = get_logger("app")

IMPACT_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _in_window(hour: int, start: int, end: int) -> bool:
    """True when an hour falls inside a (possibly wrapping) UTC window."""
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def current_sessions(now: Optional[datetime] = None) -> list[str]:
    """Names of the forex sessions open at the given (UTC) time."""
    now = now or datetime.now(timezone.utc)
    hour = now.hour
    return [name for name, (s, e) in SESSIONS_UTC.items() if _in_window(hour, s, e)]


def in_killzone(now: Optional[datetime] = None) -> Optional[str]:
    """Killzone name when inside one, else None."""
    now = now or datetime.now(timezone.utc)
    hour = now.hour
    for name, (start, end) in KILLZONES_UTC.items():
        if _in_window(hour, start, end):
            return name
    return None


def session_strength(now: Optional[datetime] = None) -> float:
    """Institutional-activity score 0-100 for the current session mix."""
    sessions = set(current_sessions(now))
    if {"London", "NewYork"} <= sessions:
        score = 100.0
    elif "London" in sessions or "NewYork" in sessions:
        score = 80.0
    elif "Tokyo" in sessions:
        score = 45.0
    elif "Sydney" in sessions:
        score = 30.0
    else:
        score = 15.0
    if in_killzone(now):
        score = min(100.0, score + 10.0)
    return score


def is_session_allowed(now: Optional[datetime], allowed: list[str]) -> bool:
    """True when at least one open session is in the allowed list."""
    if not allowed:
        return True
    open_now = set(current_sessions(now))
    return bool(open_now & {s.strip() for s in allowed})


def symbol_currencies(symbol: str) -> set[str]:
    """Currency codes driving a symbol (XAUUSD -> {USD}, EURUSD -> {EUR, USD})."""
    letters = re.sub(r"[^A-Za-z]", "", symbol).upper()
    if len(letters) < 6:
        return set()
    base, quote = letters[:3], letters[3:6]
    if base in ("XAU", "XAG", "XPT", "BTC", "ETH", "USO", "UST"):
        return {quote}
    return {base, quote}


@dataclass
class NewsEvent:
    """A single scheduled economic release."""

    title: str
    currency: str
    impact: str  # LOW | MEDIUM | HIGH
    time: datetime

    def __post_init__(self) -> None:
        """Normalise currency/impact codes."""
        self.currency = self.currency.upper()
        self.impact = self.impact.upper()

    @property
    def rank(self) -> int:
        """Numeric impact rank for threshold comparison."""
        return IMPACT_RANK.get(self.impact, 0)


@dataclass
class EconomicCalendar:
    """High-impact news blackout filter fed by CSV and/or manual events."""

    before_min: int = 30
    after_min: int = 30
    min_impact: str = "HIGH"
    events: list[NewsEvent] = field(default_factory=list)

    def load_csv(self, path: str) -> int:
        """Load events from CSV (title,currency,impact,time ISO). Returns count."""
        if not path or not os.path.exists(path):
            return 0
        loaded = 0
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    when = datetime.fromisoformat(str(row["time"]).replace("Z", "+00:00"))
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    self.events.append(
                        NewsEvent(
                            title=str(row.get("title", "")),
                            currency=str(row.get("currency", "")),
                            impact=str(row.get("impact", "LOW")),
                            time=when,
                        )
                    )
                    loaded += 1
                except Exception as exc:  # noqa: BLE001 - skip bad rows, keep going
                    logger.warning("Skipping bad news row %s: %s", row, exc)
        logger.info("Loaded %d news events from %s", loaded, path)
        return loaded

    def add_event(self, title: str, currency: str, impact: str, when: datetime) -> None:
        """Manually register one news event."""
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        self.events.append(NewsEvent(title, currency, impact, when))

    def blocking_events(
        self, symbol: str, now: Optional[datetime] = None
    ) -> list[NewsEvent]:
        """Events currently blacking out new entries for the symbol."""
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        currencies = symbol_currencies(symbol)
        threshold = IMPACT_RANK.get(self.min_impact.upper(), 3)
        blocked: list[NewsEvent] = []
        for event in self.events:
            if event.rank < threshold or event.currency not in currencies:
                continue
            window_start = event.time - timedelta(minutes=self.before_min)
            window_end = event.time + timedelta(minutes=self.after_min)
            if window_start <= now <= window_end:
                blocked.append(event)
        return blocked

    def is_blocked(self, symbol: str, now: Optional[datetime] = None) -> bool:
        """True when new entries for the symbol must be paused for news."""
        return len(self.blocking_events(symbol, now)) > 0

    def upcoming(
        self, symbol: str, hours: int = 24, now: Optional[datetime] = None
    ) -> list[NewsEvent]:
        """Events affecting the symbol in the next N hours, sorted by time."""
        now = now or datetime.now(timezone.utc)
        currencies = symbol_currencies(symbol)
        horizon = now + timedelta(hours=hours)
        return sorted(
            [e for e in self.events if e.currency in currencies and now <= e.time <= horizon],
            key=lambda e: e.time,
        )
