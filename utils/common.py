"""Shared math, price and time helpers used across the platform."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from core.types import SignalAction


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def ms_now() -> float:
    """Current time in milliseconds (monotonic-friendly wall clock)."""
    return utcnow().timestamp() * 1000.0


def clamp(value: float, low: float, high: float) -> float:
    """Clamp a value into the inclusive [low, high] range."""
    return max(low, min(high, value))


def pip_size(symbol: str) -> float:
    """Pip size for a symbol (JPY pairs 0.01, metals 0.1, else 0.0001)."""
    sym = symbol.upper()
    if "JPY" in sym:
        return 0.01
    if sym.startswith("XAU") or sym.startswith("XAG"):
        return 0.1
    return 0.0001


def to_pips(symbol: str, price_distance: float) -> float:
    """Convert a price distance to pips for the given symbol."""
    return abs(price_distance) / pip_size(symbol)


def from_pips(symbol: str, pips: float) -> float:
    """Convert pips to a price distance for the given symbol."""
    return pips * pip_size(symbol)


def normalize_lots(volume: float, volume_min: float, volume_max: float, step: float) -> float:
    """Round a lot size down to the broker step and clamp to min/max."""
    if step <= 0:
        step = 0.01
    steps = math.floor((volume + 1e-9) / step)
    lots = steps * step
    lots = round(lots, 8)
    if lots < volume_min:
        return 0.0
    return min(lots, volume_max)


def position_profit(
    entry: float,
    current: float,
    action: SignalAction,
    volume: float,
    tick_value: float,
    tick_size: float,
) -> float:
    """Profit in account currency for a position at the current price."""
    if tick_size <= 0 or tick_value <= 0:
        return 0.0
    direction = 1.0 if action is SignalAction.BUY else -1.0
    ticks = (current - entry) * direction / tick_size
    return ticks * tick_value * volume


def reward_risk(entry: float, stop_loss: float, take_profit: float) -> float:
    """Planned reward-to-risk ratio for entry/SL/TP levels."""
    risk = abs(entry - stop_loss)
    if risk <= 0:
        return 0.0
    return abs(take_profit - entry) / risk


def round_price(price: float, digits: int) -> float:
    """Round a price to the symbol digit count."""
    return round(float(price), max(0, int(digits)))
