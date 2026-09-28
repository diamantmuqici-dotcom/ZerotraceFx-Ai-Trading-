"""Institutional entry rules: every BUY/SELL needs full multi-TF confirmation."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.types import Direction, MTFAnalysis, StructureEvent, TimeframeAnalysis
from smart_money.zones import distance_to_zone_atr
from strategy.confluence import ConfluenceResult, effective_bias


@dataclass
class RuleResult:
    """Outcome of one direction's entry-rule checklist."""

    direction: Direction
    passed: bool = False
    confirmations: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def check(self, name: str, ok: bool) -> None:
        """Record one named rule outcome."""
        (self.confirmations if ok else self.failures).append(name)


def _latest(
    events: list[StructureEvent], direction: Direction
) -> StructureEvent | None:
    """Most recent event in the direction, or None."""
    matches = [e for e in events if e.direction is direction]
    return max(matches, key=lambda e: e.index) if matches else None


def is_recent_event(
    event: StructureEvent | None, bar_count: int, lookback: int
) -> bool:
    """True when the event fired within the trailing lookback bars."""
    if event is None:
        return False
    return (bar_count - 1 - event.index) <= lookback


def recent_bos(a: TimeframeAnalysis | None, direction: Direction, lookback: int) -> bool:
    """True when a BOS in the direction fired recently on the timeframe."""
    if a is None:
        return False
    return is_recent_event(_latest(a.all_bos, direction), a.bar_count, lookback)


def recent_choch(a: TimeframeAnalysis | None, direction: Direction, lookback: int) -> bool:
    """True when a CHoCH in the direction fired recently on the timeframe."""
    if a is None:
        return False
    return is_recent_event(_latest(a.all_choch, direction), a.bar_count, lookback)


def recent_sweep(
    a: TimeframeAnalysis | None, side: str, lookback: int,
    require_displacement: bool = False,
) -> bool:
    """True when the liquidity side was swept recently (optionally displaced)."""
    if a is None:
        return False
    for sweep in a.sweeps:
        if sweep.side != side:
            continue
        if (a.bar_count - 1 - sweep.index) > lookback:
            continue
        if require_displacement and not sweep.displacement:
            continue
        return True
    return False


def price_at_zone(
    a: TimeframeAnalysis | None, direction: Direction, proximity_atr: float
) -> tuple[bool, str]:
    """True when price sits at a supporting OB/demand(supply) zone."""
    if a is None or a.atr <= 0:
        return False, "no data"
    pools = a.demand_zones if direction is Direction.BULLISH else a.supply_zones
    blocks = [b for b in a.order_blocks if b.direction is direction and b.active]
    for zone in pools:
        dist = distance_to_zone_atr(a.current_price, zone.top, zone.bottom, a.atr)
        if dist <= proximity_atr:
            kind = "demand" if direction is Direction.BULLISH else "supply"
            return True, f"price at {kind} zone ({dist:.2f} ATR)"
    for block in blocks:
        dist = distance_to_zone_atr(a.current_price, block.top, block.bottom, a.atr)
        if dist <= proximity_atr:
            return True, f"price at {direction.value} order block ({dist:.2f} ATR)"
    return False, "no supporting zone nearby"


def fvg_aligned(a: TimeframeAnalysis | None, direction: Direction, proximity_atr: float) -> bool:
    """True when an active directional FVG supports the entry zone/timing."""
    if a is None or a.atr <= 0:
        return False
    for gap in a.fvgs:
        if gap.direction is not direction or not gap.active:
            continue
        # Fresh gaps confirm momentum; nearby unfilled gaps confirm the zone.
        fresh = (a.bar_count - 1 - gap.created_index) <= 10
        near = distance_to_zone_atr(a.current_price, gap.top, gap.bottom, a.atr) <= proximity_atr
        if fresh or near:
            return True
    return False


def evaluate_buy_rules(
    mtf: MTFAnalysis,
    confluence: ConfluenceResult,
    spread_ok: bool,
    news_ok: bool,
    structure_recency: int = 30,
    sweep_recency: int = 30,
    fvg_proximity_atr: float = 1.5,
) -> RuleResult:
    """Check every institutional condition required for a BUY entry."""
    result = RuleResult(direction=Direction.BULLISH)
    d1, _ = effective_bias(mtf, "D1")
    h4, _ = effective_bias(mtf, "H4")
    h1 = mtf.get("H1")
    m15 = mtf.get("M15")

    result.check("D1 macro bias bullish", d1 is Direction.BULLISH)
    result.check("H4 primary trend bullish", h4 is Direction.BULLISH)
    h1_struct = recent_bos(h1, Direction.BULLISH, structure_recency) or recent_choch(
        h1, Direction.BULLISH, structure_recency
    )
    result.check("H1 bullish BOS/CHoCH", h1_struct)

    pd_state = (h1.premium_discount.state if h1 and h1.premium_discount else "")
    m15_state = (m15.premium_discount.state if m15 and m15.premium_discount else "")
    in_discount = pd_state == "DISCOUNT" or m15_state == "DISCOUNT"
    at_zone_h1, zone_msg_h1 = price_at_zone(h1, Direction.BULLISH, fvg_proximity_atr)
    at_zone_m15, zone_msg_m15 = price_at_zone(m15, Direction.BULLISH, fvg_proximity_atr)
    at_zone = at_zone_h1 or at_zone_m15
    result.check(
        f"Discount/demand zone ({pd_state}/{m15_state}; {zone_msg_h1 if at_zone_h1 else zone_msg_m15})",
        in_discount or at_zone,
    )
    swept = recent_sweep(h1, "LOW", sweep_recency) or recent_sweep(m15, "LOW", sweep_recency)
    result.check("Sell-side liquidity swept below", swept)
    fvg_ok = fvg_aligned(h1, Direction.BULLISH, fvg_proximity_atr) or fvg_aligned(
        m15, Direction.BULLISH, fvg_proximity_atr
    )
    result.check("Bullish FVG alignment", fvg_ok)
    result.check(
        "HTF trend confirmation",
        confluence.htf_bias is Direction.BULLISH or confluence.direction is Direction.BULLISH,
    )
    result.check("Spread filter passed", spread_ok)
    result.check("News filter passed", news_ok)
    result.passed = not result.failures
    return result


def evaluate_sell_rules(
    mtf: MTFAnalysis,
    confluence: ConfluenceResult,
    spread_ok: bool,
    news_ok: bool,
    structure_recency: int = 30,
    sweep_recency: int = 30,
    fvg_proximity_atr: float = 1.5,
) -> RuleResult:
    """Check every institutional condition required for a SELL entry."""
    result = RuleResult(direction=Direction.BEARISH)
    d1, _ = effective_bias(mtf, "D1")
    h4, _ = effective_bias(mtf, "H4")
    h1 = mtf.get("H1")
    m15 = mtf.get("M15")

    result.check("D1 macro bias bearish", d1 is Direction.BEARISH)
    result.check("H4 primary trend bearish", h4 is Direction.BEARISH)
    h1_struct = recent_bos(h1, Direction.BEARISH, structure_recency) or recent_choch(
        h1, Direction.BEARISH, structure_recency
    )
    result.check("H1 bearish BOS/CHoCH", h1_struct)

    pd_state = (h1.premium_discount.state if h1 and h1.premium_discount else "")
    m15_state = (m15.premium_discount.state if m15 and m15.premium_discount else "")
    in_premium = pd_state == "PREMIUM" or m15_state == "PREMIUM"
    at_zone_h1, zone_msg_h1 = price_at_zone(h1, Direction.BEARISH, fvg_proximity_atr)
    at_zone_m15, zone_msg_m15 = price_at_zone(m15, Direction.BEARISH, fvg_proximity_atr)
    at_zone = at_zone_h1 or at_zone_m15
    result.check(
        f"Premium/supply zone ({pd_state}/{m15_state}; {zone_msg_h1 if at_zone_h1 else zone_msg_m15})",
        in_premium or at_zone,
    )
    swept = recent_sweep(h1, "HIGH", sweep_recency) or recent_sweep(m15, "HIGH", sweep_recency)
    result.check("Buy-side liquidity swept above", swept)
    fvg_ok = fvg_aligned(h1, Direction.BEARISH, fvg_proximity_atr) or fvg_aligned(
        m15, Direction.BEARISH, fvg_proximity_atr
    )
    result.check("Bearish FVG alignment", fvg_ok)
    result.check(
        "HTF trend confirmation",
        confluence.htf_bias is Direction.BEARISH or confluence.direction is Direction.BEARISH,
    )
    result.check("Spread filter passed", spread_ok)
    result.check("News filter passed", news_ok)
    result.passed = not result.failures
    return result
