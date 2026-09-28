"""Tests for swings, structure (BOS/CHoCH), order blocks, FVGs and liquidity."""
from __future__ import annotations

import pandas as pd

from core.types import Direction
from market.indicators import atr as atr_fn
from smart_money.fvg import detect_fvgs
from smart_money.liquidity import detect_equal_pools, detect_liquidity_sweeps
from smart_money.order_blocks import detect_order_blocks
from smart_money.smc_engine import SMCEngine
from smart_money.structure import detect_structure
from smart_money.swings import detect_swings
from smart_money.zones import dealing_range, premium_discount
from tests.conftest import make_df


def test_swings_found_on_uptrend(uptrend_df):
    """An uptrend must produce both swing highs and swing lows."""
    swings = detect_swings(uptrend_df, 3, 3)
    kinds = {s.kind for s in swings}
    assert kinds == {"HIGH", "LOW"}
    assert all(s.strength >= 0 for s in swings)
    assert [s.index for s in swings] == sorted(s.index for s in swings)


def test_swings_empty_frame():
    """Empty input yields no swings (never raises)."""
    assert detect_swings(pd.DataFrame()) == []


def test_structure_uptrend_is_bullish_with_bos(uptrend_df):
    """Steady uptrend: bullish external trend with at least one BOS."""
    swings = detect_swings(uptrend_df, 5, 5)
    result = detect_structure(uptrend_df, swings, "H1")
    assert result.trend is Direction.BULLISH
    assert len(result.bos_events) >= 1
    assert all(e.kind == "BOS" for e in result.bos_events)


def test_structure_downtrend_is_bearish(downtrend_df):
    """Steady downtrend reads bearish."""
    swings = detect_swings(downtrend_df, 5, 5)
    result = detect_structure(downtrend_df, swings, "H1")
    assert result.trend is Direction.BEARISH


def test_structure_reversal_produces_choch(reversal_df):
    """Trend rollover flips the trend through a CHoCH event."""
    swings = detect_swings(reversal_df, 5, 5)
    result = detect_structure(reversal_df, swings, "H1")
    assert result.trend is Direction.BEARISH
    assert len(result.choch_events) >= 1
    assert result.choch_events[0].direction is Direction.BEARISH


def test_order_block_detects_displacement_leg():
    """A big bullish candle after a down candle creates a bullish OB."""
    closes = [1.1000] * 12 + [1.0994, 1.1022] + [1.1020, 1.1018, 1.1016]
    df = make_df(closes, range_pips=0.0002, seed=3)
    # Force the displacement candle body for determinism.
    df.loc[13, "open"] = 1.0994
    df.loc[13, "close"] = 1.1024
    df.loc[13, "high"] = 1.1026
    df.loc[13, "low"] = 1.0992
    df.loc[12, "open"] = 1.1000
    df.loc[12, "close"] = 1.0994
    blocks = detect_order_blocks(df, "M15", displacement_mult=0.8, lookback=15)
    bullish = [b for b in blocks if b.direction is Direction.BULLISH]
    assert len(bullish) >= 1
    block = bullish[-1]
    assert block.top == 1.1000  # origin candle open
    assert block.bottom <= 1.0994
    assert 0 < block.strength <= 100


def test_fvg_detects_bullish_gap():
    """A textbook 3-candle gap is detected with correct bounds."""
    df = make_df([1.1000, 1.1005, 1.1010, 1.1042, 1.1045], seed=3)
    df.loc[0, ["open", "high", "low", "close"]] = [1.1000, 1.1010, 1.0990, 1.1002]
    df.loc[1, ["open", "high", "low", "close"]] = [1.1002, 1.1030, 1.1000, 1.1028]
    df.loc[2, ["open", "high", "low", "close"]] = [1.1028, 1.1040, 1.1035, 1.1038]
    df.loc[3, ["open", "high", "low", "close"]] = [1.1038, 1.1046, 1.1036, 1.1042]
    df.loc[4, ["open", "high", "low", "close"]] = [1.1042, 1.1049, 1.1040, 1.1045]
    gaps = detect_fvgs(df, "M15", min_size_atr=0.01, lookback=10)
    bullish = [g for g in gaps if g.direction is Direction.BULLISH]
    assert len(bullish) >= 1
    gap = bullish[0]
    assert gap.bottom == 1.1010  # candle i-2 high
    assert gap.top == 1.1035  # candle i low
    assert gap.size_atr > 0


def test_fvg_mitigation_marks_fill():
    """Price returning into the gap records mitigation progress."""
    df = make_df([1.1000, 1.1005, 1.1010, 1.1042, 1.1045, 1.1020, 1.1030], seed=3)
    df.loc[0, ["open", "high", "low", "close"]] = [1.1000, 1.1010, 1.0990, 1.1002]
    df.loc[1, ["open", "high", "low", "close"]] = [1.1002, 1.1030, 1.1000, 1.1028]
    df.loc[2, ["open", "high", "low", "close"]] = [1.1028, 1.1040, 1.1035, 1.1038]
    df.loc[3, ["open", "high", "low", "close"]] = [1.1038, 1.1046, 1.1036, 1.1042]
    df.loc[4, ["open", "high", "low", "close"]] = [1.1042, 1.1049, 1.1040, 1.1045]
    # Partial fill: wick enters the gap (top 1.1035) but body holds above bottom.
    df.loc[5, ["open", "high", "low", "close"]] = [1.1045, 1.1046, 1.1020, 1.1025]
    df.loc[6, ["open", "high", "low", "close"]] = [1.1025, 1.1032, 1.1022, 1.1030]
    gaps = detect_fvgs(df, "M15", min_size_atr=0.01, lookback=10)
    assert gaps and gaps[0].mitigated and not gaps[0].invalidated


def test_liquidity_sweep_of_swing_high():
    """A wick above a swing high closing back inside is a sweep."""
    closes = [1.1000, 1.1010, 1.1020, 1.1030, 1.1040, 1.1030, 1.1020,
              1.1010, 1.1005, 1.1015, 1.1025, 1.1010]
    df = make_df(closes, range_pips=0.0001, seed=5)
    df.loc[4, "high"] = 1.1045  # peak wick -> swing high
    df.loc[4, "close"] = 1.1035
    df.loc[10, "high"] = 1.1050  # sweep wick above the swing
    df.loc[10, "close"] = 1.1025
    swings = detect_swings(df, 2, 2)
    assert any(s.kind == "HIGH" for s in swings)
    sweeps = detect_liquidity_sweeps(df, swings, "H1")
    highs = [s for s in sweeps if s.side == "HIGH"]
    assert len(highs) >= 1
    assert highs[0].bias is Direction.BEARISH


def test_equal_pools_cluster():
    """Repeated swing highs at one level form an equal-highs pool."""
    closes = [1.1000, 1.1020, 1.1010, 1.1020, 1.1005, 1.1020, 1.1000]
    df = make_df(closes, range_pips=0.00005, seed=9)
    for i in (1, 3, 5):
        df.loc[i, "high"] = 1.10205
    swings = detect_swings(df, 1, 1)
    atr_now = float(atr_fn(df).iloc[-1])
    highs, _lows = detect_equal_pools(swings, "M15", tolerance_atr=0.5, atr_ref=atr_now)
    assert any(p.count >= 2 for p in highs)


def test_premium_discount_states():
    """Range positioning classifies premium/discount/equilibrium."""
    assert premium_discount(80, 100, 0).state == "PREMIUM"
    assert premium_discount(20, 100, 0).state == "DISCOUNT"
    assert premium_discount(50, 100, 0).state == "EQUILIBRIUM"


def test_smc_engine_full_analysis(pullback_df):
    """The engine pipeline returns a complete, internally consistent analysis."""
    engine = SMCEngine()
    analysis = engine.analyze("EURUSD", "H1", pullback_df)
    assert analysis.bar_count == len(pullback_df)
    assert analysis.atr > 0
    assert analysis.atr_mean > 0
    # Pullback breaks internal structure while external trend holds bullish.
    assert analysis.trend_external is Direction.BULLISH
    assert analysis.trend_internal is Direction.BEARISH
    # Price still in premium -> engine refuses to chase (NEUTRAL, not bull).
    assert analysis.premium_discount is not None
    assert analysis.premium_discount.state == "PREMIUM"
    assert analysis.bias is Direction.NEUTRAL
    assert len(analysis.swings) > 0
    assert len(analysis.order_blocks) > 0
    assert len(analysis.fvgs) > 0
    rng_high, rng_low = dealing_range(pullback_df, analysis.swings)
    assert rng_high > rng_low


def test_resolve_bias_matrix():
    """Bias logic: with-trend only in the correct half of the range."""
    from core.types import PremiumDiscount, TimeframeAnalysis

    def _frame(trend, state):
        return TimeframeAnalysis(
            timeframe="H1", trend_external=trend,
            premium_discount=PremiumDiscount(state, 50.0, 2.0, 1.0, 1.5),
        )

    assert SMCEngine.resolve_bias(_frame(Direction.BULLISH, "DISCOUNT")) is Direction.BULLISH
    assert SMCEngine.resolve_bias(_frame(Direction.BULLISH, "EQUILIBRIUM")) is Direction.BULLISH
    assert SMCEngine.resolve_bias(_frame(Direction.BULLISH, "PREMIUM")) is Direction.NEUTRAL
    assert SMCEngine.resolve_bias(_frame(Direction.BEARISH, "PREMIUM")) is Direction.BEARISH
    assert SMCEngine.resolve_bias(_frame(Direction.BEARISH, "EQUILIBRIUM")) is Direction.BEARISH
    assert SMCEngine.resolve_bias(_frame(Direction.BEARISH, "DISCOUNT")) is Direction.NEUTRAL
    assert SMCEngine.resolve_bias(_frame(Direction.NEUTRAL, "DISCOUNT")) is Direction.NEUTRAL


def test_smc_engine_mtf_bias():
    """MTF analysis combines per-TF structure into an overall bias."""
    from tests.conftest import drift_closes

    engine = SMCEngine()
    closes = drift_closes(400, 1.1000, 0.00012, 0.0002, seed=21)
    m5 = make_df(closes)
    from market.indicators import resample_ohlc

    mtf = {"M5": m5, "M15": resample_ohlc(m5, "M15"),
           "H1": resample_ohlc(m5, "H1"), "H4": resample_ohlc(m5, "H4")}
    result = engine.analyze_mtf("EURUSD", mtf)
    assert "H1" in result.analyses
    assert result.higher_tf_trend in (Direction.BULLISH, Direction.NEUTRAL)
    assert result.overall_bias in (Direction.BULLISH, Direction.NEUTRAL)
