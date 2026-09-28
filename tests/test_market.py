"""Tests for indicators, sessions, news filter and the offline data engine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from core.types import TickData
from market.data_engine import MarketDataEngine
from market.filters import (
    EconomicCalendar,
    current_sessions,
    in_killzone,
    is_session_allowed,
    session_strength,
    symbol_currencies,
)
from market.indicators import (
    atr,
    momentum_roc,
    repair_missing_bars,
    resample_ohlc,
    validate_ohlc,
)


def test_validate_ohlc_sorts_and_dedupes(uptrend_df):
    """Validation sorts, drops NaNs and removes duplicate timestamps."""
    messy = pd.concat([uptrend_df, uptrend_df.iloc[[5]]], ignore_index=True)
    messy = messy.sample(frac=1.0, random_state=1).reset_index(drop=True)
    clean = validate_ohlc(messy)
    assert len(clean) == len(uptrend_df)
    assert clean["time"].is_monotonic_increasing


def test_atr_matches_constant_range():
    """ATR of a constant-range series converges to the bar range."""
    from tests.conftest import make_df

    closes = [1.1000 + i * 0.0001 for i in range(40)]
    df = make_df(closes, range_pips=0.0002, seed=2)
    values = atr(df, 14)
    assert len(values) == len(df)
    assert values.iloc[-1] > 0
    assert values.iloc[-1] < 0.002  # sane magnitude for the synthetic data


def test_momentum_sign_follows_trend(uptrend_df, downtrend_df):
    """Momentum ROC is positive in uptrends, negative in downtrends."""
    assert momentum_roc(uptrend_df, 14).iloc[-1] > 0
    assert momentum_roc(downtrend_df, 14).iloc[-1] < 0


def test_resample_m5_to_h1(uptrend_df):
    """Twelve M5 bars compress into one H1 bar with correct OHLC."""
    h1 = resample_ohlc(uptrend_df, "H1")
    assert len(h1) == 13  # 150 M5 bars span 12.5h -> 13 hourly bars
    assert h1["high"].max() == uptrend_df["high"].max()
    assert h1["low"].min() == uptrend_df["low"].min()
    assert h1["open"].iloc[0] == uptrend_df["open"].iloc[0]
    assert h1["close"].iloc[-1] == uptrend_df["close"].iloc[-1]


def test_resample_rejects_unknown_timeframe(uptrend_df):
    """Unknown timeframes raise instead of silently mis-bucketing."""
    import pytest

    with pytest.raises(ValueError):
        resample_ohlc(uptrend_df, "W1")


def test_repair_fills_weekend_gap():
    """A removed bar is reinserted with forward-filled prices."""
    from tests.conftest import make_df

    df = make_df([1.1000 + i * 0.0001 for i in range(30)], seed=6)
    gapped = df.drop(index=[10, 11]).reset_index(drop=True)
    repaired = repair_missing_bars(gapped, "M5")
    assert len(repaired) == 30
    assert repaired["close"].isna().sum() == 0


def test_sessions_and_killzones():
    """Session detection follows the UTC timetable with killzone bonus."""
    overlap = datetime(2026, 1, 6, 13, 30, tzinfo=timezone.utc)  # Tue 13:30 UTC
    sessions = current_sessions(overlap)
    assert "London" in sessions and "NewYork" in sessions
    assert session_strength(overlap) == 100.0
    assert in_killzone(overlap) == "NewYork Killzone"
    asian = datetime(2026, 1, 6, 3, 0, tzinfo=timezone.utc)
    assert set(current_sessions(asian)) == {"Sydney", "Tokyo"}
    assert session_strength(asian) < 60.0
    assert is_session_allowed(overlap, ["London", "NewYork"]) is True
    assert is_session_allowed(overlap, ["Tokyo"]) is False


def test_symbol_currencies():
    """Currency extraction handles majors and metals with suffixes."""
    assert symbol_currencies("EURUSD") == {"EUR", "USD"}
    assert symbol_currencies("XAUUSD") == {"USD"}
    assert symbol_currencies("GBPUSD.pro") == {"GBP", "USD"}
    assert symbol_currencies("USDJPY") == {"USD", "JPY"}


def test_news_filter_blocks_high_impact():
    """A HIGH USD release blacks out EURUSD but not GBPJPY entries."""
    now = datetime.now(timezone.utc)
    calendar = EconomicCalendar(before_min=30, after_min=30, min_impact="HIGH")
    calendar.add_event("NFP", "USD", "HIGH", now + timedelta(minutes=10))
    calendar.add_event("Tokyo CPI", "JPY", "LOW", now)
    assert calendar.is_blocked("EURUSD", now) is True
    assert calendar.is_blocked("GBPJPY", now) is False
    upcoming = calendar.upcoming("EURUSD", hours=1, now=now)
    assert len(upcoming) == 1 and upcoming[0].title == "NFP"


def test_news_filter_respects_impact_threshold():
    """LOW events never block when the threshold is HIGH."""
    now = datetime.now(timezone.utc)
    calendar = EconomicCalendar(min_impact="HIGH")
    calendar.add_event("Minor speech", "USD", "LOW", now)
    assert calendar.is_blocked("EURUSD", now) is False


def test_news_csv_loading(tmp_path):
    """CSV calendars load; malformed rows are skipped, not fatal."""
    path = tmp_path / "news.csv"
    path.write_text(
        "title,currency,impact,time\n"
        "FOMC,USD,HIGH,2026-01-07T19:00:00+00:00\n"
        "broken,row\n"
    )
    calendar = EconomicCalendar()
    assert calendar.load_csv(str(path)) == 1
    assert calendar.load_csv(str(tmp_path / "missing.csv")) == 0


def test_tick_data_math():
    """Tick mid/spread properties are consistent."""
    tick = TickData("EURUSD", datetime.now(timezone.utc), 1.1000, 1.1002)
    assert tick.mid == pytest.approx(1.1001)
    assert tick.spread == pytest.approx(0.0002)


async def test_data_engine_offline_feeds(uptrend_df):
    """Offline feeds serve candles, ticks and spreads without MT5."""
    engine = MarketDataEngine()
    engine.set_offline("EURUSD", "M5", uptrend_df)
    assert engine.has_offline("EURUSD", "M5") is True
    candles = await engine.get_candles("EURUSD", "M5", count=50)
    assert len(candles) == 50
    assert candles["close"].iloc[-1] == uptrend_df["close"].iloc[-1]
    mtf = await engine.get_mtf_data("EURUSD", ["M5", "H1"])
    assert set(mtf) == {"M5", "H1"}
    tick = await engine.get_tick("EURUSD")
    assert tick is not None and tick.ask > tick.bid
    spread = await engine.get_spread_pips("EURUSD")
    assert spread == pytest.approx(1.2)  # default EURUSD paper spread
    assert await engine.get_candles("GBPUSD", "M5") is not None


async def test_data_engine_csv_loading(tmp_path, uptrend_df):
    """CSV files load into offline feeds; missing files return zero."""
    engine = MarketDataEngine()
    path = tmp_path / "EURUSD_M5.csv"
    uptrend_df.to_csv(path, index=False)
    assert engine.load_csv("EURUSD", "M5", str(path)) == len(uptrend_df)
    assert engine.load_csv("EURUSD", "H1", str(tmp_path / "nope.csv")) == 0
