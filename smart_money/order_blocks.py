"""Order block detection: last opposite candle before an impulsive displacement leg.

Bullish OB: last bearish candle before a bullish displacement leg; the zone
spans that candle's open down to its low. Bearish OB mirrors (open up to high).
Mitigation tracks how much of the zone price has revisited; a body close
through the far edge invalidates the block.
"""
from __future__ import annotations

import pandas as pd

from core.types import Direction, OrderBlock, StructureEvent
from market.indicators import atr as atr_series


def _structure_near(
    events: list[StructureEvent], index: int, direction: Direction, window: int = 3
) -> bool:
    """True when a BOS/CHoCH in the direction fired near the bar index."""
    return any(
        e.direction is direction and abs(e.index - index) <= window for e in events
    )


def update_order_block(block: OrderBlock, df: pd.DataFrame) -> OrderBlock:
    """Refresh mitigation/invalidation of one block over subsequent candles."""
    if block.invalidated or df is None or df.empty:
        return block
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    closes = df["close"].astype(float).to_numpy()
    size = block.size
    if size <= 0:
        return block
    start = max(0, block.created_index + 1)
    for j in range(start, len(df)):
        if block.direction is Direction.BULLISH:
            if float(lows[j]) <= block.top:
                penetration = (block.top - float(lows[j])) / size
                block.mitigation_pct = round(max(block.mitigation_pct, min(1.0, penetration) * 100.0), 2)
                block.mitigated = block.mitigation_pct > 0
            if float(closes[j]) < block.bottom:
                block.invalidated = True
                block.mitigation_pct = 100.0
                break
        else:
            if float(highs[j]) >= block.bottom:
                penetration = (float(highs[j]) - block.bottom) / size
                block.mitigation_pct = round(max(block.mitigation_pct, min(1.0, penetration) * 100.0), 2)
                block.mitigated = block.mitigation_pct > 0
            if float(closes[j]) > block.top:
                block.invalidated = True
                block.mitigation_pct = 100.0
                break
    return block


def detect_order_blocks(
    df: pd.DataFrame,
    timeframe: str = "",
    displacement_mult: float = 1.0,
    lookback: int = 120,
    max_blocks: int = 12,
    structure_events: list[StructureEvent] | None = None,
) -> list[OrderBlock]:
    """Detect order blocks in the trailing lookback window (newest last)."""
    if df is None or df.empty:
        return []
    n = len(df)
    start = max(1, n - max(10, lookback))
    opens = df["open"].astype(float).to_numpy()
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    closes = df["close"].astype(float).to_numpy()
    times = pd.to_datetime(df["time"], utc=True)
    atr_vals = atr_series(df).fillna(0.0).to_numpy()
    events = structure_events or []
    blocks: list[OrderBlock] = []
    for i in range(start, n):
        atr_now = float(atr_vals[i]) if i < len(atr_vals) else 0.0
        if atr_now <= 0:
            continue
        body = float(closes[i]) - float(opens[i])
        if abs(body) < displacement_mult * atr_now:
            continue  # not a displacement leg
        bullish_leg = body > 0
        origin = -1
        for j in range(i - 1, max(start - 2, i - 6), -1):
            leg_body = float(closes[j]) - float(opens[j])
            if bullish_leg and leg_body < 0:
                origin = j
                break
            if not bullish_leg and leg_body > 0:
                origin = j
                break
        if origin < 0:
            continue
        o_open = float(opens[origin])
        if bullish_leg:
            top, bottom = o_open, float(lows[origin])
            direction = Direction.BULLISH
        else:
            top, bottom = float(highs[origin]), o_open
            direction = Direction.BEARISH
        if top <= bottom:
            continue
        # Strength: displacement size, structure break, freshness.
        strength = min(40.0, (abs(body) / atr_now) * 16.0)
        if _structure_near(events, i, direction):
            strength += 25.0
        strength += 10.0  # fresh at creation; mitigation discounts later
        strength = round(min(100.0, strength), 1)
        block = OrderBlock(
            id=f"{timeframe or 'TF'}-{direction.value}-ob-{origin}",
            direction=direction,
            timeframe=timeframe,
            created_index=i,
            created_time=times.iloc[i].to_pydatetime(),
            top=round(top, 8),
            bottom=round(bottom, 8),
            ref_open=o_open,
            ref_close=float(closes[origin]),
            strength=strength,
            origin=f"origin_bar={origin} leg_bar={i}",
        )
        update_order_block(block, df)
        if block.mitigation_pct >= 100.0 and block.invalidated:
            continue  # fully consumed long ago; not tradeable
        # Discount stale blocks that are mostly mitigated.
        block.strength = round(block.strength * (1.0 - block.mitigation_pct / 200.0), 1)
        blocks.append(block)
    # Keep the strongest recent blocks, newest last.
    blocks.sort(key=lambda b: (b.strength, b.created_index))
    blocks = blocks[-max_blocks:]
    blocks.sort(key=lambda b: b.created_index)
    return blocks
