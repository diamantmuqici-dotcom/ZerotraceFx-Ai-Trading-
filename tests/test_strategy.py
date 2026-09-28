"""Tests for confluence, AI scoring, entry rules and signal generation."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.types import (
    Direction,
    FairValueGap,
    LiquiditySweep,
    MarketState,
    MTFAnalysis,
    OrderBlock,
    PremiumDiscount,
    SignalAction,
    StructureEvent,
    TimeframeAnalysis,
    Zone,
)
from strategy.ai_engine import AIDecisionEngine, AIFeatures, DEFAULT_WEIGHTS
from strategy.confluence import effective_bias, evaluate_mtf_confluence
from strategy.entry_rules import evaluate_buy_rules, evaluate_sell_rules
from strategy.strategy import (
    compute_sl_tp,
    extract_features,
    momentum_score,
    spread_score,
    volatility_score,
)
from strategy.strategy import Strategy


def _tf(
    timeframe: str,
    bias: Direction,
    trend: Direction,
    price: float = 1.1000,
    atr: float = 0.0010,
    bars: int = 100,
    pd_state: str = "DISCOUNT",
    momentum: float = 0.4,
) -> TimeframeAnalysis:
    """Build a timeframe analysis shell for rule/confluence tests."""
    return TimeframeAnalysis(
        timeframe=timeframe, bias=bias, trend_external=trend,
        trend_internal=trend, current_price=price, atr=atr,
        atr_mean=atr, bar_count=bars, momentum=momentum,
        premium_discount=PremiumDiscount(pd_state, 30.0 if "DISCOUNT" in pd_state else 70.0,
                                         1.1100, 1.0900, 1.1000),
    )


def _bullish_mtf() -> MTFAnalysis:
    """A textbook bullish institutional setup across all timeframes."""
    now = datetime(2026, 1, 5, 13, 0, tzinfo=timezone.utc)
    mtf = MTFAnalysis(symbol="EURUSD", time=now)
    mtf.analyses["D1"] = _tf("D1", Direction.BULLISH, Direction.BULLISH, bars=120)
    mtf.analyses["H4"] = _tf("H4", Direction.BULLISH, Direction.BULLISH, bars=120)
    h1 = _tf("H1", Direction.BULLISH, Direction.BULLISH)
    m15 = _tf("M15", Direction.BULLISH, Direction.BULLISH, momentum=0.5)
    h1.bos_external = [StructureEvent("BOS", "EXTERNAL", Direction.BULLISH, 95, now,
                                      1.1000, 1.0980, "H1")]
    h1.choch_external = [StructureEvent("CHOCH", "EXTERNAL", Direction.BULLISH, 90, now,
                                        1.0990, 1.0975, "H1")]
    h1.sweeps = [LiquiditySweep(now, 92, "LOW", 1.0950, 1.0944, 1.0960, "H1",
                                displacement=True, bias=Direction.BULLISH, strength=80.0)]
    h1.order_blocks = [OrderBlock("H1-BULL-ob-1", Direction.BULLISH, "H1", 93, now,
                                  1.0995, 1.0985, strength=90.0)]
    h1.demand_zones = [Zone("DEMAND", "H1", 1.0995, 1.0985, 90.0, now)]
    h1.fvgs = [FairValueGap("H1-BULL-fvg-1", Direction.BULLISH, "H1", 96, now,
                             1.0998, 1.0992, size_atr=0.6)]
    m15.current_price = 1.0996  # sitting inside the demand zone / discount
    m15.order_blocks = list(h1.order_blocks)
    m15.demand_zones = list(h1.demand_zones)
    m15.fvgs = list(h1.fvgs)
    mtf.analyses["H1"] = h1
    mtf.analyses["M15"] = m15
    mtf.analyses["M5"] = _tf("M5", Direction.BULLISH, Direction.BULLISH)
    mtf.overall_bias = Direction.BULLISH
    mtf.higher_tf_trend = Direction.BULLISH
    return mtf


# -- confluence ---------------------------------------------------------------

def test_confluence_aligned_bullish():
    """Full bullish stack aligns with a perfect score."""
    result = evaluate_mtf_confluence(_bullish_mtf())
    assert result.aligned is True
    assert result.direction is Direction.BULLISH
    assert result.score == 100.0
    assert result.htf_bias is Direction.BULLISH


def test_confluence_conflicted_not_aligned():
    """Opposing H1 breaks alignment."""
    mtf = _bullish_mtf()
    mtf.analyses["H1"] = _tf("H1", Direction.BEARISH, Direction.BEARISH,
                             pd_state="PREMIUM")
    result = evaluate_mtf_confluence(mtf)
    assert result.aligned is False
    assert result.score < 100.0


def test_effective_bias_falls_back_on_thin_history():
    """D1 with too few bars falls back to H4's bias (flagged)."""
    mtf = _bullish_mtf()
    mtf.analyses["D1"] = _tf("D1", Direction.NEUTRAL, Direction.NEUTRAL, bars=5)
    bias, fallback = effective_bias(mtf, "D1")
    assert fallback is True
    assert bias is Direction.BULLISH  # H4 proxy


# -- AI engine -----------------------------------------------------------------

def test_ai_weights_sum_to_100():
    """Default weights are a proper 0-100 distribution."""
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 100.0) < 1e-9


def test_ai_perfect_features_pass():
    """Strong features clear the default 85 threshold."""
    engine = AIDecisionEngine(threshold=85.0)
    features = AIFeatures(direction=Direction.BULLISH, htf_trend=100,
                          structure=100, bos=100, choch=100, ob_quality=95,
                          fvg_quality=90, liquidity_sweep=100, volatility=100,
                          session=80, spread=100, momentum=100)
    decision = engine.score(features)
    assert decision.action is SignalAction.BUY
    assert decision.confidence >= 85.0
    assert decision.passed is True
    assert len(decision.reasoning) == len(DEFAULT_WEIGHTS) + 1


def test_ai_weak_features_rejected():
    """Mediocre features stay below the threshold with an audit trail."""
    engine = AIDecisionEngine(threshold=85.0)
    features = AIFeatures(direction=Direction.BEARISH, htf_trend=50,
                          structure=40, bos=10, choch=55, ob_quality=15,
                          fvg_quality=20, liquidity_sweep=15, volatility=60,
                          session=40, spread=80, momentum=30)
    decision = engine.score(features)
    assert decision.confidence < 85.0
    assert decision.passed is False
    assert decision.reasoning[-1].endswith("REJECT")


def test_ai_custom_weights_normalised():
    """Custom weights are normalised back to a 0-100 score."""
    engine = AIDecisionEngine(weights={"htf_trend": 1.0, "structure": 1.0})
    features = AIFeatures(direction=Direction.BULLISH, htf_trend=100, structure=0)
    assert engine.score(features).confidence == pytest.approx(50.0)


# -- entry rules -----------------------------------------------------------------

def test_buy_rules_pass_on_textbook_setup():
    """Every BUY rule passes on the textbook bullish stack."""
    mtf = _bullish_mtf()
    confluence = evaluate_mtf_confluence(mtf)
    result = evaluate_buy_rules(mtf, confluence, spread_ok=True, news_ok=True)
    assert result.failures == []
    assert result.passed is True
    assert len(result.confirmations) == 9


def test_sell_rules_fail_on_bullish_setup():
    """SELL rules reject the bullish stack."""
    mtf = _bullish_mtf()
    confluence = evaluate_mtf_confluence(mtf)
    result = evaluate_sell_rules(mtf, confluence, spread_ok=True, news_ok=True)
    assert result.passed is False
    assert len(result.failures) >= 5


def test_buy_rules_blocked_by_news_and_spread():
    """Spread/news vetoes fail the checklist even on a perfect setup."""
    mtf = _bullish_mtf()
    confluence = evaluate_mtf_confluence(mtf)
    blocked = evaluate_buy_rules(mtf, confluence, spread_ok=False, news_ok=False)
    assert blocked.passed is False
    assert any("Spread" in f for f in blocked.failures)
    assert any("News" in f for f in blocked.failures)


def test_buy_rules_need_sweep_and_structure():
    """Removing the sweep and structure breaks breaks the setup."""
    mtf = _bullish_mtf()
    mtf.analyses["H1"].sweeps = []
    mtf.analyses["H1"].bos_external = []
    mtf.analyses["H1"].choch_external = []
    confluence = evaluate_mtf_confluence(mtf)
    result = evaluate_buy_rules(mtf, confluence, spread_ok=True, news_ok=True)
    assert result.passed is False
    assert any("liquidity" in f.lower() for f in result.failures)


# -- scoring helpers --------------------------------------------------------------

def test_helper_scores():
    """Volatility/spread/momentum helpers behave across their ranges."""
    assert volatility_score(0.001, 0.001) == 100.0
    assert volatility_score(0.003, 0.001) < 60.0
    assert volatility_score(0.0, 0.001) == 0.0
    assert spread_score(1.0, 3.0) == 100.0
    assert spread_score(3.0, 3.0) == 0.0
    assert spread_score(5.0, 3.0) == 0.0
    assert momentum_score(0.5, Direction.BULLISH) == 100.0
    assert momentum_score(0.5, Direction.BEARISH) == 10.0
    assert momentum_score(0.0, Direction.BULLISH) == 45.0


def test_compute_sl_tp_math():
    """ATR stop with minimum-RR target for both directions."""
    sl, tp = compute_sl_tp(Direction.BULLISH, 1.1000, 0.0010, 1.5, 2.0)
    assert sl == pytest.approx(1.0985)
    assert tp == pytest.approx(1.1030)
    sl, tp = compute_sl_tp(Direction.BEARISH, 1.1000, 0.0010, 1.5, 2.0)
    assert sl == pytest.approx(1.1015)
    assert tp == pytest.approx(1.0970)


def test_extract_features_rewards_full_setup():
    """Feature extraction scores the textbook stack near maximum."""
    mtf = _bullish_mtf()
    market = MarketState(symbol="EURUSD", spread_pips=1.0, spread_ok=True,
                         news_ok=True, session="London", session_strength=80.0)
    features = extract_features(mtf, Direction.BULLISH, market, 3.0)
    values = features.as_dict()
    assert values["htf_trend"] == 100.0
    assert values["structure"] == 100.0
    assert values["bos"] == 100.0
    assert values["liquidity_sweep"] == 100.0
    assert values["ob_quality"] == 90.0


# -- full strategy ---------------------------------------------------------------

def test_strategy_holds_on_flat_data(settings):
    """Flat ranging data produces an explained HOLD, never a forced entry."""
    from tests.conftest import make_df

    strategy = Strategy(settings)
    closes = [1.1000 + (0.0001 if i % 2 else -0.0001) for i in range(120)]
    m5 = make_df(closes, seed=4)
    from market.indicators import resample_ohlc

    mtf_data = {"M5": m5, "M15": resample_ohlc(m5, "M15"),
                "H1": resample_ohlc(m5, "H1")}
    market = MarketState(symbol="EURUSD", spread_pips=1.0, spread_ok=True,
                         news_ok=True, session_strength=50.0)
    signal = strategy.analyze_data("EURUSD", mtf_data, market)
    assert signal.action is SignalAction.HOLD
    assert signal.reasoning  # HOLD is always explained


def test_strategy_fires_buy_on_stubbed_textbook_setup(settings, eurusd_spec):
    """End-to-end BUY with levels, confidence and audit trail on a full setup."""
    strategy = Strategy(settings)

    class _StubSMC:
        def analyze_mtf(self, symbol, mtf_data, when=None):
            return _bullish_mtf()

    strategy.smc = _StubSMC()  # type: ignore[assignment]
    market = MarketState(symbol="EURUSD", spread_pips=1.0, spread_ok=True,
                         news_ok=True, session="London", session_strength=80.0)
    signal = strategy.analyze_data("EURUSD", {}, market, eurusd_spec)
    assert signal.action is SignalAction.BUY
    assert signal.confidence >= settings.confidence_threshold
    assert signal.stop_loss < signal.entry < signal.take_profit
    assert signal.reward_risk >= settings.min_rr - 1e-9
    assert signal.setup_id.startswith("EURUSD-")
    assert any("Rule OK" in r for r in signal.reasoning)
    assert signal.components  # per-component audit


def test_strategy_rejects_below_threshold(settings):
    """A perfect setup still rejects when the threshold is set above it."""
    settings.confidence_threshold = 99.9
    strategy = Strategy(settings)

    class _StubSMC:
        def analyze_mtf(self, symbol, mtf_data, when=None):
            return _bullish_mtf()

    strategy.smc = _StubSMC()  # type: ignore[assignment]
    market = MarketState(symbol="EURUSD", spread_pips=1.0, spread_ok=True,
                         news_ok=True, session_strength=80.0)
    signal = strategy.analyze_data("EURUSD", {}, market)
    assert signal.action is SignalAction.HOLD
    assert 0 < signal.confidence < 99.9
