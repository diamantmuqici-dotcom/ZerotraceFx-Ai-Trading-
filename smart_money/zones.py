"""Supply/demand zones plus premium/discount dealing-range positioning."""
from __future__ import annotations

import pandas as pd

from core.types import Direction, OrderBlock, PremiumDiscount, SwingPoint, Zone


def zones_from_order_blocks(
    blocks: list[OrderBlock], max_each: int = 5
) -> tuple[list[Zone], list[Zone]]:
    """Map active bearish/bullish order blocks to supply/demand zones."""
    supply = [
        Zone(kind="SUPPLY", timeframe=b.timeframe, top=b.top, bottom=b.bottom,
             strength=b.strength, created_time=b.created_time,
             mitigated=b.mitigated, invalidated=b.invalidated, origin=b.id)
        for b in blocks if b.direction is Direction.BEARISH and b.active
    ]
    demand = [
        Zone(kind="DEMAND", timeframe=b.timeframe, top=b.top, bottom=b.bottom,
             strength=b.strength, created_time=b.created_time,
             mitigated=b.mitigated, invalidated=b.invalidated, origin=b.id)
        for b in blocks if b.direction is Direction.BULLISH and b.active
    ]
    supply.sort(key=lambda z: z.strength, reverse=True)
    demand.sort(key=lambda z: z.strength, reverse=True)
    return supply[:max_each], demand[:max_each]


def dealing_range(
    df: pd.DataFrame, swings: list[SwingPoint] | None = None, window: int = 100
) -> tuple[float, float]:
    """Current dealing range (high, low) from recent price action.

    Prefers the most recent major swing pair; falls back to the rolling
    window high/low when swings are unavailable.
    """
    if df is None or df.empty:
        return (0.0, 0.0)
    if swings:
        ordered = sorted(swings, key=lambda s: s.index)
        recent = ordered[-20:] if len(ordered) > 20 else ordered
        swing_highs = [s.price for s in recent if s.kind == "HIGH"]
        swing_lows = [s.price for s in recent if s.kind == "LOW"]
        if swing_highs and swing_lows:
            return (max(swing_highs), min(swing_lows))
    window_df = df.tail(max(10, window))
    return (float(window_df["high"].max()), float(window_df["low"].min()))


def premium_discount(
    current_price: float, range_high: float, range_low: float
) -> PremiumDiscount:
    """Classify price as PREMIUM / DISCOUNT / EQUILIBRIUM within the range."""
    if range_high <= range_low:
        return PremiumDiscount("EQUILIBRIUM", 50.0, range_high, range_low,
                               (range_high + range_low) / 2.0)
    equilibrium = (range_high + range_low) / 2.0
    position = (current_price - range_low) / (range_high - range_low) * 100.0
    position = max(-50.0, min(150.0, position))
    if position >= 55.0:
        state = "PREMIUM"
    elif position <= 45.0:
        state = "DISCOUNT"
    else:
        state = "EQUILIBRIUM"
    return PremiumDiscount(
        state=state,
        position_pct=round(position, 2),
        range_high=range_high,
        range_low=range_low,
        equilibrium=equilibrium,
    )


def price_in_zone(price: float, top: float, bottom: float, buffer_atr: float = 0.0) -> bool:
    """True when price sits inside [bottom - buffer, top + buffer]."""
    return (bottom - buffer_atr) <= price <= (top + buffer_atr)


def distance_to_zone_atr(price: float, top: float, bottom: float, atr: float) -> float:
    """Distance from price to the nearest zone edge, in ATR multiples."""
    if atr <= 0:
        return 999.0
    if bottom <= price <= top:
        return 0.0
    edge = bottom if price < bottom else top
    return abs(price - edge) / atr
