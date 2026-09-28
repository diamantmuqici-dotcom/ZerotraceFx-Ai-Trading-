"""Fractal swing high/low detection with ATR-normalised strength."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from core.types import SwingPoint
from market.indicators import atr as atr_series


def detect_swings(
    df: pd.DataFrame,
    left: int = 3,
    right: int = 3,
    min_strength_atr: float = 0.0,
    atr: Optional[pd.Series] = None,
) -> list[SwingPoint]:
    """Detect confirmed fractal swings; strength = wick displacement in ATRs.

    A swing high at bar i requires high[i] to be the strict maximum of the
    [i-left, i+right] window; swing lows mirror with the strict minimum.
    """
    if df is None or df.empty:
        return []
    n = len(df)
    left = max(1, int(left))
    right = max(1, int(right))
    if n < left + right + 1:
        return []
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    closes = df["close"].astype(float).to_numpy()
    times = pd.to_datetime(df["time"], utc=True)
    atr_vals: Optional[list[float]] = None
    if atr is not None and len(atr) == n:
        atr_vals = [float(v) if pd.notna(v) else 0.0 for v in atr.tolist()]
    else:
        computed = atr_series(df)
        if len(computed) == n:
            atr_vals = [float(v) if pd.notna(v) else 0.0 for v in computed.tolist()]
    swings: list[SwingPoint] = []
    for i in range(left, n - right):
        window_h = highs[i - left: i + right + 1]
        window_l = lows[i - left: i + right + 1]
        price_h = float(highs[i])
        price_l = float(lows[i])
        atr_now = atr_vals[i] if atr_vals else 0.0
        if price_h == float(window_h.max()) and (window_h == price_h).sum() == 1:
            strength = abs(price_h - float(closes[i])) / atr_now if atr_now > 0 else 0.0
            if strength >= min_strength_atr:
                swings.append(SwingPoint(
                    index=i, time=times.iloc[i].to_pydatetime(),
                    price=price_h, kind="HIGH", strength=round(strength, 3),
                ))
        if price_l == float(window_l.min()) and (window_l == price_l).sum() == 1:
            strength = abs(float(closes[i]) - price_l) / atr_now if atr_now > 0 else 0.0
            if strength >= min_strength_atr:
                swings.append(SwingPoint(
                    index=i, time=times.iloc[i].to_pydatetime(),
                    price=price_l, kind="LOW", strength=round(strength, 3),
                ))
    swings.sort(key=lambda s: s.index)
    return swings
