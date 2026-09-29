"""Deterministic candlestick pattern observations; never an order by itself."""
from __future__ import annotations

import pandas as pd


def classify_candle(row: pd.Series) -> str:
    body = abs(float(row.close) - float(row.open)); span = max(float(row.high) - float(row.low), 1e-12)
    if body / span < 0.1: return "DOJI"
    return "BULLISH_BODY" if row.close > row.open else "BEARISH_BODY"


def classify_frame(frame: pd.DataFrame) -> list[str]:
    return [classify_candle(row) for _, row in frame.iterrows()]
