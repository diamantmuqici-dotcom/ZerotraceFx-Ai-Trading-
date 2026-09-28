"""Internal/external market structure: trend tracking, BOS and CHoCH events."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from core.types import Direction, StructureEvent, SwingPoint


@dataclass
class StructureResult:
    """Trend state plus ordered structure-break events for one swing scope."""

    trend: Direction = Direction.NEUTRAL
    events: list[StructureEvent] = field(default_factory=list)
    last_swing_high: Optional[float] = None
    last_swing_low: Optional[float] = None

    @property
    def bos_events(self) -> list[StructureEvent]:
        """Only Break of Structure events."""
        return [e for e in self.events if e.kind == "BOS"]

    @property
    def choch_events(self) -> list[StructureEvent]:
        """Only Change of Character events."""
        return [e for e in self.events if e.kind == "CHOCH"]


def detect_structure(
    df: pd.DataFrame,
    swings: list[SwingPoint],
    timeframe: str = "",
    scope: str = "EXTERNAL",
    start_trend: Direction = Direction.NEUTRAL,
) -> StructureResult:
    """Walk candles tracking the active swing range; closes outside it break it.

    A close above the last confirmed swing high in an uptrend (or from neutral)
    is a bullish BOS; a close above it while in a downtrend is a bullish CHoCH
    that flips the trend. Bearish logic mirrors. Swings only become breakable
    reference levels once their bar is reached (confirmation discipline).
    """
    result = StructureResult(trend=start_trend)
    if df is None or df.empty or not swings:
        return result
    closes = df["close"].astype(float).to_numpy()
    times = pd.to_datetime(df["time"], utc=True)
    ordered = sorted(swings, key=lambda s: s.index)
    ptr = 0
    active_high: Optional[float] = None
    active_low: Optional[float] = None
    first_index = max(0, ordered[0].index)
    for i in range(first_index, len(df)):
        while ptr < len(ordered) and ordered[ptr].index <= i:
            swing = ordered[ptr]
            if swing.kind == "HIGH":
                active_high = swing.price
                result.last_swing_high = swing.price
            else:
                active_low = swing.price
                result.last_swing_low = swing.price
            ptr += 1
        price = float(closes[i])
        when = times.iloc[i].to_pydatetime()
        broken_high = active_high is not None and price > active_high
        broken_low = active_low is not None and price < active_low
        if broken_high and (not broken_low):
            if result.trend is Direction.BEARISH:
                kind = "CHOCH"
                result.trend = Direction.BULLISH
            else:
                kind = "BOS"
                result.trend = Direction.BULLISH
            result.events.append(StructureEvent(
                kind=kind, scope=scope, direction=Direction.BULLISH,
                index=i, time=when, price=price,
                broken_level=float(active_high), timeframe=timeframe,
            ))
            active_high = None  # consumed; wait for the next confirmed swing high
        elif broken_low and (not broken_high):
            if result.trend is Direction.BULLISH:
                kind = "CHOCH"
                result.trend = Direction.BEARISH
            else:
                kind = "BOS"
                result.trend = Direction.BEARISH
            result.events.append(StructureEvent(
                kind=kind, scope=scope, direction=Direction.BEARISH,
                index=i, time=when, price=price,
                broken_level=float(active_low), timeframe=timeframe,
            ))
            active_low = None
    return result
