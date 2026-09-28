"""Shared fixtures: deterministic synthetic OHLC data and component builders."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import Settings  # noqa: E402
from core.engine import default_spec  # noqa: E402


def make_df(
    closes: list[float],
    start: str = "2026-01-05 00:00",
    freq: str = "5min",
    range_pips: float = 0.0010,
    seed: int = 7,
) -> pd.DataFrame:
    """Build an OHLC frame from a close series with deterministic wicks."""
    rng = np.random.default_rng(seed)
    times = pd.date_range(start=start, periods=len(closes), freq=freq, tz="UTC")
    rows = []
    prev = closes[0]
    for close in closes:
        wick = abs(rng.normal(0, range_pips / 2))
        body_high = max(prev, close)
        body_low = min(prev, close)
        rows.append({
            "time": None, "open": prev,
            "high": body_high + wick, "low": body_low - wick, "close": close,
        })
        prev = close
    frame = pd.DataFrame(rows)
    frame["time"] = times
    frame["tick_volume"] = 100
    return frame[["time", "open", "high", "low", "close", "tick_volume"]]


def drift_closes(n: int, start: float, drift: float, noise: float, seed: int) -> list[float]:
    """Deterministic random-walk closes with a linear drift."""
    rng = np.random.default_rng(seed)
    return list(start + np.cumsum(rng.normal(drift, noise, n)))


@pytest.fixture()
def uptrend_df() -> pd.DataFrame:
    """Strong choppy uptrend (structure should read bullish)."""
    closes = drift_closes(150, 1.1000, 0.00022, 0.0006, seed=11)
    return make_df(closes, range_pips=0.0004, seed=11)


@pytest.fixture()
def downtrend_df() -> pd.DataFrame:
    """Strong choppy downtrend."""
    closes = drift_closes(150, 1.1000, -0.00022, 0.0006, seed=12)
    return make_df(closes, range_pips=0.0004, seed=12)


@pytest.fixture()
def reversal_df() -> pd.DataFrame:
    """Established uptrend rolling into a sharp downtrend (CHoCH expected)."""
    up = drift_closes(110, 1.1000, 0.00020, 0.0007, seed=13)
    down = drift_closes(60, up[-1], -0.00070, 0.0005, seed=14)
    return make_df(up + down, range_pips=0.0004, seed=13)


@pytest.fixture()
def pullback_df() -> pd.DataFrame:
    """Uptrend with a shallow late pullback."""
    up = drift_closes(120, 1.1000, 0.00022, 0.0006, seed=15)
    pull = drift_closes(18, up[-1], -0.00010, 0.0004, seed=16)
    return make_df(up + pull, range_pips=0.0004, seed=15)


@pytest.fixture()
def settings() -> Settings:
    """Default settings object (no .env required)."""
    return Settings()


@pytest.fixture()
def eurusd_spec():
    """Offline EURUSD contract spec."""
    return default_spec("EURUSD")
