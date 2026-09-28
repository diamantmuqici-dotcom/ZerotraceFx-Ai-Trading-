"""Strategy orchestrator: SMC -> confluence -> entry rules -> AI score -> signal."""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

import pandas as pd

from config.settings import Settings
from core.types import (
    Direction,
    MarketState,
    MTFAnalysis,
    SignalAction,
    SymbolSpec,
    TimeframeAnalysis,
    TradeSignal,
)
from smart_money.smc_engine import SMCEngine
from smart_money.zones import distance_to_zone_atr
from strategy.ai_engine import AIDecisionEngine, AIDecision, AIFeatures
from strategy.confluence import ConfluenceResult, effective_bias, evaluate_mtf_confluence
from strategy.entry_rules import (
    RuleResult,
    evaluate_buy_rules,
    evaluate_sell_rules,
    fvg_aligned,
    recent_bos,
    recent_choch,
    recent_sweep,
)
from utils.common import clamp, utcnow
from utils.logging_setup import get_logger

logger = get_logger("app")


def volatility_score(atr_now: float, atr_mean: float) -> float:
    """Score the volatility regime: tradeable band earns 100, extremes fade."""
    if atr_now <= 0 or atr_mean <= 0:
        return 0.0
    ratio = atr_now / atr_mean
    if 0.7 <= ratio <= 1.5:
        return 100.0
    if ratio < 0.4 or ratio > 2.5:
        return 25.0
    if ratio < 0.7:
        return 40.0 + (ratio - 0.4) / 0.3 * 60.0
    return 100.0 - (ratio - 1.5) / 1.0 * 75.0


def spread_score(spread_pips: float, limit_pips: float) -> float:
    """Spread quality 0-100: full marks below half the limit, zero above it."""
    if limit_pips <= 0:
        return 50.0
    if spread_pips <= 0:
        return 100.0
    if spread_pips >= limit_pips:
        return 0.0
    if spread_pips <= limit_pips / 2:
        return 100.0
    return round((1.0 - (spread_pips - limit_pips / 2) / (limit_pips / 2)) * 100.0, 1)


def momentum_score(momentum_pct: float, direction: Direction) -> float:
    """Directional momentum score from M15 rate-of-change."""
    aligned = momentum_pct if direction is Direction.BULLISH else -momentum_pct
    if aligned >= 0.30:
        return 100.0
    if aligned >= 0.10:
        return 75.0
    if aligned >= -0.10:
        return 45.0
    if aligned >= -0.30:
        return 25.0
    return 10.0


def extract_features(
    mtf: MTFAnalysis,
    direction: Direction,
    market: MarketState,
    spread_limit_pips: float,
    structure_recency: int = 30,
    sweep_recency: int = 30,
) -> AIFeatures:
    """Translate SMC + market context into normalised AI features."""
    d1, _ = effective_bias(mtf, "D1")
    h4, _ = effective_bias(mtf, "H4")
    h1 = mtf.get("H1")
    m15 = mtf.get("M15")
    htf_hits = sum(1 for b in (d1, h4) if b is direction)
    htf = 100.0 if htf_hits == 2 else (60.0 if htf_hits == 1 else 10.0)

    h1_ext = h1.trend_external if h1 else Direction.NEUTRAL
    h1_int = h1.trend_internal if h1 else Direction.NEUTRAL
    if h1_ext is direction:
        structure = 100.0
    elif h1_int is direction:
        structure = 80.0
    elif h1_ext is Direction.NEUTRAL and h1_int is Direction.NEUTRAL:
        structure = 40.0
    else:
        structure = 15.0

    bos = 100.0 if recent_bos(h1, direction, structure_recency) else (
        70.0 if recent_bos(m15, direction, structure_recency) else 10.0)
    if recent_choch(h1, direction, structure_recency) or recent_choch(m15, direction, structure_recency):
        choch = 100.0
    elif recent_choch(h1, direction.opposite(), structure_recency):
        choch = 10.0
    else:
        choch = 55.0

    ob_best = 0.0
    for tf_a in (h1, m15):
        if tf_a is None:
            continue
        for block in tf_a.order_blocks:
            if block.direction is direction and block.active:
                ob_best = max(ob_best, block.strength)
    ob_quality = ob_best if ob_best > 0 else 15.0

    fvg_best = 0.0
    for tf_a in (h1, m15):
        if tf_a is None:
            continue
        for gap in tf_a.fvgs:
            if gap.direction is direction and gap.active:
                freshness = max(0.0, 100.0 - gap.mitigation_pct)
                size_bonus = min(20.0, gap.size_atr * 10.0)
                fvg_best = max(fvg_best, min(100.0, 60.0 + freshness * 0.3 + size_bonus))
    fvg_quality = fvg_best if fvg_aligned(h1, direction, 1.5) or fvg_aligned(m15, direction, 1.5) else min(fvg_best, 45.0)
    if fvg_best <= 0:
        fvg_quality = 15.0

    side = "LOW" if direction is Direction.BULLISH else "HIGH"
    if recent_sweep(h1, side, sweep_recency, require_displacement=True) or recent_sweep(
        m15, side, sweep_recency, require_displacement=True
    ):
        sweep = 100.0
    elif recent_sweep(h1, side, sweep_recency) or recent_sweep(m15, side, sweep_recency):
        sweep = 75.0
    else:
        sweep = 15.0

    ref = m15 or h1
    volatility = volatility_score(ref.atr, ref.atr_mean) if ref else 0.0
    momentum = momentum_score(ref.momentum, direction) if ref else 0.0
    return AIFeatures(
        direction=direction, htf_trend=htf, structure=structure, bos=bos,
        choch=choch, ob_quality=round(ob_quality, 1),
        fvg_quality=round(fvg_quality, 1), liquidity_sweep=sweep,
        volatility=round(volatility, 1),
        session=round(clamp(market.session_strength, 0, 100), 1),
        spread=spread_score(market.spread_pips, spread_limit_pips),
        momentum=momentum,
    )


def compute_sl_tp(
    direction: Direction,
    entry: float,
    atr_ref: float,
    atr_mult: float,
    min_rr: float,
    min_distance: float = 0.0,
) -> tuple[float, float]:
    """ATR stop-loss with minimum-RR take-profit for a direction/entry."""
    stop_dist = max(atr_ref * atr_mult, min_distance)
    if direction is Direction.BULLISH:
        stop = entry - stop_dist
        target = entry + stop_dist * min_rr
    else:
        stop = entry + stop_dist
        target = entry - stop_dist * min_rr
    return stop, target


class Strategy:
    """End-to-end signal generator shared by live, paper and backtest modes."""

    def __init__(self, settings: Settings, smc: SMCEngine | None = None,
                 ai: AIDecisionEngine | None = None) -> None:
        """Wire SMC analysis and AI scoring with the given settings."""
        self.settings = settings
        self.smc = smc or SMCEngine(
            swing_left=settings.swing_left, swing_right=settings.swing_right,
            atr_period=settings.atr_period, ob_lookback=settings.ob_lookback,
            ob_displacement_mult=settings.ob_displacement_mult,
            fvg_min_size_atr=settings.fvg_min_size_atr,
            eq_tolerance_atr=settings.eq_tolerance_atr,
        )
        self.ai = ai or AIDecisionEngine(threshold=settings.confidence_threshold)

    # -- synchronous core (used by backtests and live alike) -------------
    def analyze_data(
        self,
        symbol: str,
        mtf_data: dict[str, pd.DataFrame],
        market: MarketState,
        spec: SymbolSpec | None = None,
    ) -> TradeSignal:
        """Produce a TradingSignal from raw MTF frames plus market context."""
        mtf = self.smc.analyze_mtf(symbol, mtf_data)
        confluence = evaluate_mtf_confluence(mtf)
        buy_rules = evaluate_buy_rules(
            mtf, confluence, market.spread_ok, market.news_ok,
            self.settings.structure_recency_bars, self.settings.sweep_recency_bars,
            self.settings.fvg_proximity_atr,
        )
        sell_rules = evaluate_sell_rules(
            mtf, confluence, market.spread_ok, market.news_ok,
            self.settings.structure_recency_bars, self.settings.sweep_recency_bars,
            self.settings.fvg_proximity_atr,
        )
        exec_tf = self._execution_frame(mtf)
        entry = exec_tf.current_price if exec_tf else 0.0
        candidates: list[tuple[Direction, RuleResult]] = []
        if buy_rules.passed:
            candidates.append((Direction.BULLISH, buy_rules))
        if sell_rules.passed:
            candidates.append((Direction.BEARISH, sell_rules))
        if not candidates or entry <= 0:
            return self._hold_signal(symbol, mtf, confluence, buy_rules, sell_rules, market)
        # Score every passing direction; the strongest audited decision wins.
        best_decision: AIDecision | None = None
        best_rules: RuleResult = candidates[0][1]
        for direction, rules in candidates:
            features = extract_features(
                mtf, direction, market, self.settings.spread_limit_pips,
                self.settings.structure_recency_bars, self.settings.sweep_recency_bars,
            )
            decision = self.ai.score(features)
            if best_decision is None or decision.confidence > best_decision.confidence:
                best_decision, best_rules = decision, rules
        assert best_decision is not None
        if not best_decision.passed:
            signal = self._hold_signal(symbol, mtf, confluence, buy_rules, sell_rules, market)
            signal.confidence = best_decision.confidence
            signal.components = best_decision.components
            signal.reasoning = (
                [f"Best candidate {best_decision.direction.value} rejected by AI threshold:"]
                + best_decision.reasoning
            )
            return signal
        atr_ref = exec_tf.atr if exec_tf and exec_tf.atr > 0 else entry * 0.001
        min_dist = market.spread_pips * 0.0  # spread guard handled by filters
        stop, target = compute_sl_tp(
            best_decision.direction, entry, atr_ref,
            self.settings.atr_sl_mult, self.settings.min_rr, min_dist,
        )
        if spec is not None and spec.digits:
            entry = round(entry, spec.digits)
            stop = round(stop, spec.digits)
            target = round(target, spec.digits)
        reasoning = (
            [f"MTF confluence: {'; '.join(confluence.details)}"]
            + [f"Rule OK: {c}" for c in best_rules.confirmations]
            + best_decision.reasoning
        )
        return TradeSignal(
            action=best_decision.action, symbol=symbol,
            confidence=best_decision.confidence, entry=entry,
            stop_loss=stop, take_profit=target, reasoning=reasoning,
            components=best_decision.components, timeframe="M15",
            timestamp=utcnow(), setup_id=f"{symbol}-{uuid4().hex[:8]}",
            metadata={
                "direction": best_decision.direction.value,
                "overall_bias": mtf.overall_bias.value,
                "htf_trend": mtf.higher_tf_trend.value,
                "confluence_score": confluence.score,
            },
        )

    def _hold_signal(
        self, symbol: str, mtf: MTFAnalysis, confluence: ConfluenceResult,
        buy_rules: RuleResult, sell_rules: RuleResult, market: MarketState,
    ) -> TradeSignal:
        """Explain why no trade is taken (auditable HOLD)."""
        exec_tf = self._execution_frame(mtf)
        reasoning = [f"MTF confluence: {'; '.join(confluence.details)}"]
        # Report the closer checklist so the journal shows what was missing.
        closer, other = (buy_rules, sell_rules) if len(buy_rules.failures) <= len(sell_rules.failures) else (sell_rules, buy_rules)
        reasoning.append(f"Closest setup: {closer.direction.value} "
                         f"({len(closer.confirmations)} ok / {len(closer.failures)} missing)")
        reasoning.extend(f"Missing: {f}" for f in closer.failures[:5])
        reasoning.append(f"Opposite setup missing {len(other.failures)} rules")
        return TradeSignal(
            action=SignalAction.HOLD, symbol=symbol, confidence=0.0,
            entry=exec_tf.current_price if exec_tf else 0.0,
            reasoning=reasoning, timeframe="M15", timestamp=utcnow(),
            setup_id=f"{symbol}-hold-{uuid4().hex[:6]}",
            metadata={"overall_bias": mtf.overall_bias.value,
                      "htf_trend": mtf.higher_tf_trend.value},
        )

    @staticmethod
    def _execution_frame(mtf: MTFAnalysis) -> TimeframeAnalysis | None:
        """Preferred execution-timeframe analysis (M15, else M5, else H1)."""
        for tf in ("M15", "M5", "H1"):
            frame = mtf.get(tf)
            if frame is not None and frame.bar_count > 0:
                return frame
        return None

    # -- async live path ---------------------------------------------------
    async def evaluate(
        self,
        symbol: str,
        data_engine: object,
        market: MarketState,
        spec: SymbolSpec | None = None,
    ) -> TradeSignal:
        """Fetch fresh MTF data asynchronously, then run the sync core."""
        from market.data_engine import MarketDataEngine  # local: avoids import cycle

        engine = data_engine if isinstance(data_engine, MarketDataEngine) else None
        if engine is None:
            raise TypeError("evaluate() requires a MarketDataEngine instance")
        mtf_data = await engine.get_mtf_data(symbol)
        return self.analyze_data(symbol, mtf_data, market, spec)
