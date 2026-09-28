"""Smart Money engine: full per-timeframe and multi-timeframe analysis."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from core.types import Direction, MTFAnalysis, MTF_ORDER, TimeframeAnalysis
from market.indicators import (
    atr_mean,
    atr_value,
    momentum_value,
    validate_ohlc,
)
from market.indicators import atr as atr_series_fn
from smart_money.fvg import detect_fvgs
from smart_money.liquidity import detect_equal_pools, detect_liquidity_sweeps
from smart_money.order_blocks import detect_order_blocks
from smart_money.structure import detect_structure
from smart_money.swings import detect_swings
from smart_money.zones import dealing_range, premium_discount, zones_from_order_blocks
from utils.common import utcnow
from utils.logging_setup import get_logger

logger = get_logger("app")


class SMCEngine:
    """Computes institutional order-flow analysis for any symbol/timeframe."""

    def __init__(
        self,
        swing_left: int = 3,
        swing_right: int = 3,
        atr_period: int = 14,
        ob_lookback: int = 120,
        ob_displacement_mult: float = 1.0,
        fvg_min_size_atr: float = 0.05,
        eq_tolerance_atr: float = 0.25,
    ) -> None:
        """Store detection parameters (all configurable via Settings)."""
        self.swing_left = swing_left
        self.swing_right = swing_right
        self.atr_period = atr_period
        self.ob_lookback = ob_lookback
        self.ob_displacement_mult = ob_displacement_mult
        self.fvg_min_size_atr = fvg_min_size_atr
        self.eq_tolerance_atr = eq_tolerance_atr

    # -- single timeframe ----------------------------------------------
    def analyze(self, symbol: str, timeframe: str, df: pd.DataFrame) -> TimeframeAnalysis:
        """Run the complete SMC pipeline on one timeframe frame."""
        clean = validate_ohlc(df)
        analysis = TimeframeAnalysis(timeframe=timeframe)
        if clean.empty or len(clean) < 10:
            return analysis
        analysis.bar_count = len(clean)
        analysis.current_price = float(clean["close"].iloc[-1])
        atr_now = atr_value(clean, self.atr_period)
        analysis.atr = atr_now
        analysis.atr_mean = atr_mean(clean, self.atr_period)
        analysis.momentum = momentum_value(clean)

        atr_s = atr_series_fn(clean, self.atr_period)
        ext_left, ext_right = self.swing_left + 2, self.swing_right + 2
        swings = detect_swings(clean, ext_left, ext_right, atr=atr_s)
        internal = detect_swings(
            clean, max(1, self.swing_left - 1), max(1, self.swing_right - 1), atr=atr_s
        )
        analysis.swings = swings
        analysis.internal_swings = internal

        external = detect_structure(clean, swings, timeframe, scope="EXTERNAL")
        inner = detect_structure(clean, internal, timeframe, scope="INTERNAL")
        analysis.trend_external = external.trend
        analysis.trend_internal = inner.trend
        analysis.bos_external = external.bos_events
        analysis.choch_external = external.choch_events
        analysis.bos_internal = inner.bos_events
        analysis.choch_internal = inner.choch_events

        structure_events = external.events + inner.events
        blocks = detect_order_blocks(
            clean, timeframe,
            displacement_mult=self.ob_displacement_mult,
            lookback=self.ob_lookback,
            structure_events=structure_events,
        )
        analysis.order_blocks = blocks
        analysis.fvgs = detect_fvgs(clean, timeframe, min_size_atr=self.fvg_min_size_atr)
        analysis.sweeps = detect_liquidity_sweeps(clean, swings, timeframe)
        eq_highs, eq_lows = detect_equal_pools(
            swings, timeframe, tolerance_atr=self.eq_tolerance_atr, atr_ref=atr_now
        )
        analysis.equal_highs = eq_highs
        analysis.equal_lows = eq_lows
        supply, demand = zones_from_order_blocks(blocks)
        analysis.supply_zones = supply
        analysis.demand_zones = demand

        rng_high, rng_low = dealing_range(clean, swings)
        analysis.premium_discount = premium_discount(analysis.current_price, rng_high, rng_low)
        analysis.bias = self.resolve_bias(analysis)
        return analysis

    @staticmethod
    def resolve_bias(a: TimeframeAnalysis) -> Direction:
        """Combine structure trend with dealing-range position into one bias.

        With-trend entries are only endorsed in the correct half of the range:
        bullish flow in discount, bearish flow in premium. Counter-range flow
        yields NEUTRAL (wait for a better price), never a reversal signal.
        """
        trend = a.trend_external
        if trend is Direction.NEUTRAL:
            trend = a.trend_internal
        if trend is Direction.NEUTRAL:
            return Direction.NEUTRAL
        pd_state = a.premium_discount.state if a.premium_discount else "EQUILIBRIUM"
        if trend is Direction.BULLISH:
            if pd_state in ("DISCOUNT", "EQUILIBRIUM"):
                return Direction.BULLISH
            return Direction.NEUTRAL
        if pd_state in ("PREMIUM", "EQUILIBRIUM"):
            return Direction.BEARISH
        return Direction.NEUTRAL

    # -- multi timeframe -------------------------------------------------
    def analyze_mtf(
        self, symbol: str, mtf_data: dict[str, pd.DataFrame], when: datetime | None = None
    ) -> MTFAnalysis:
        """Analyse every available timeframe and derive the combined bias."""
        result = MTFAnalysis(symbol=symbol, time=when or utcnow())
        for timeframe in MTF_ORDER:
            frame = mtf_data.get(timeframe)
            if frame is None or (hasattr(frame, "empty") and frame.empty):
                continue
            try:
                result.analyses[timeframe] = self.analyze(symbol, timeframe, frame)
            except Exception as exc:  # noqa: BLE001 - one bad TF must not kill MTF
                logger.warning("SMC failed for %s %s: %s", symbol, timeframe, exc)
        result.higher_tf_trend = self._combined_trend(result, ["D1", "H4"])
        result.overall_bias = self._combined_bias(result)
        return result

    @staticmethod
    def _combined_trend(mtf: MTFAnalysis, timeframes: list[str]) -> Direction:
        """Higher-timeframe trend from external structure agreement."""
        votes = [
            mtf.analyses[tf].trend_external
            for tf in timeframes
            if tf in mtf.analyses
            and mtf.analyses[tf].trend_external is not Direction.NEUTRAL
        ]
        if not votes:
            return Direction.NEUTRAL
        bull = sum(1 for v in votes if v is Direction.BULLISH)
        bear = sum(1 for v in votes if v is Direction.BEARISH)
        if bull > bear:
            return Direction.BULLISH
        if bear > bull:
            return Direction.BEARISH
        return Direction.NEUTRAL

    def _combined_bias(self, mtf: MTFAnalysis) -> Direction:
        """Overall bias: HTF trend confirmed by H1 bias, else neutral."""
        htf = self._combined_trend(mtf, ["D1", "H4"])
        h1 = mtf.analyses.get("H1")
        h1_bias = h1.bias if h1 else Direction.NEUTRAL
        if htf is Direction.BULLISH and h1_bias is Direction.BULLISH:
            return Direction.BULLISH
        if htf is Direction.BEARISH and h1_bias is Direction.BEARISH:
            return Direction.BEARISH
        if htf is not Direction.NEUTRAL and h1_bias is Direction.NEUTRAL:
            return htf
        return Direction.NEUTRAL
