"""Fair Value Gap detection: 3-candle imbalances with fill tracking."""
from __future__ import annotations

import pandas as pd

from core.types import Direction, FairValueGap
from market.indicators import atr as atr_series


def update_fvg(gap: FairValueGap, df: pd.DataFrame) -> FairValueGap:
    """Refresh mitigation/invalidation of one gap over subsequent candles."""
    if gap.invalidated or df is None or df.empty:
        return gap
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    closes = df["close"].astype(float).to_numpy()
    size = gap.size
    if size <= 0:
        return gap
    start = max(0, gap.created_index + 1)
    for j in range(start, len(df)):
        if gap.direction is Direction.BULLISH:
            if float(lows[j]) <= gap.top:
                fill = (gap.top - float(lows[j])) / size
                gap.mitigation_pct = round(max(gap.mitigation_pct, min(1.0, fill) * 100.0), 2)
                gap.mitigated = gap.mitigation_pct > 0
            if float(closes[j]) < gap.bottom:
                gap.invalidated = True
                gap.mitigation_pct = 100.0
                break
        else:
            if float(highs[j]) >= gap.bottom:
                fill = (float(highs[j]) - gap.bottom) / size
                gap.mitigation_pct = round(max(gap.mitigation_pct, min(1.0, fill) * 100.0), 2)
                gap.mitigated = gap.mitigation_pct > 0
            if float(closes[j]) > gap.top:
                gap.invalidated = True
                gap.mitigation_pct = 100.0
                break
    return gap


def detect_fvgs(
    df: pd.DataFrame,
    timeframe: str = "",
    min_size_atr: float = 0.05,
    lookback: int = 200,
    max_gaps: int = 15,
) -> list[FairValueGap]:
    """Detect fair value gaps in the trailing lookback window (newest last)."""
    if df is None or df.empty or len(df) < 3:
        return []
    n = len(df)
    start = max(2, n - max(10, lookback))
    opens = df["open"].astype(float).to_numpy()
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    closes = df["close"].astype(float).to_numpy()
    times = pd.to_datetime(df["time"], utc=True)
    atr_vals = atr_series(df).fillna(0.0).to_numpy()
    gaps: list[FairValueGap] = []
    for i in range(start, n):
        atr_now = float(atr_vals[i]) if i < len(atr_vals) else 0.0
        min_size = min_size_atr * atr_now
        # Bullish FVG: gap between candle i-2 high and candle i low.
        bull_gap = float(lows[i]) - float(highs[i - 2])
        bull_impulse = float(closes[i - 1]) > float(opens[i - 1])
        if bull_gap > 0 and bull_gap >= min_size and bull_impulse:
            gaps.append(FairValueGap(
                id=f"{timeframe or 'TF'}-BULL-fvg-{i}",
                direction=Direction.BULLISH,
                timeframe=timeframe,
                created_index=i,
                created_time=times.iloc[i].to_pydatetime(),
                top=round(float(lows[i]), 8),
                bottom=round(float(highs[i - 2]), 8),
                size_atr=round(bull_gap / atr_now, 3) if atr_now > 0 else 0.0,
            ))
        # Bearish FVG: gap between candle i-2 low and candle i high.
        bear_gap = float(lows[i - 2]) - float(highs[i])
        bear_impulse = float(closes[i - 1]) < float(opens[i - 1])
        if bear_gap > 0 and bear_gap >= min_size and bear_impulse:
            gaps.append(FairValueGap(
                id=f"{timeframe or 'TF'}-BEAR-fvg-{i}",
                direction=Direction.BEARISH,
                timeframe=timeframe,
                created_index=i,
                created_time=times.iloc[i].to_pydatetime(),
                top=round(float(lows[i - 2]), 8),
                bottom=round(float(highs[i]), 8),
                size_atr=round(bear_gap / atr_now, 3) if atr_now > 0 else 0.0,
            ))
    for gap in gaps:
        update_fvg(gap, df)
    # Prefer large, fresh gaps; drop fully consumed ones.
    gaps = [g for g in gaps if g.active or g.mitigation_pct < 100.0]
    gaps.sort(key=lambda g: (g.size_atr * (1.0 - g.mitigation_pct / 100.0), g.created_index))
    gaps = gaps[-max_gaps:]
    gaps.sort(key=lambda g: g.created_index)
    return gaps
