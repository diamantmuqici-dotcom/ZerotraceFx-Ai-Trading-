"""Shared domain types for ZeroTrace FX AI.

This module is intentionally dependency-light (stdlib + pandas only) so every
other package can import it without creating import cycles.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Direction(str, Enum):
    """Market direction / bias."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

    def opposite(self) -> "Direction":
        """Return the opposite directional bias."""
        if self is Direction.BULLISH:
            return Direction.BEARISH
        if self is Direction.BEARISH:
            return Direction.BULLISH
        return Direction.NEUTRAL


class SignalAction(str, Enum):
    """Strategy signal action."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class AccountMode(str, Enum):
    """Trading account mode."""

    PAPER = "PAPER"
    LIVE = "LIVE"
    BACKTEST = "BACKTEST"


class Timeframe(str, Enum):
    """Supported chart timeframes."""

    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


TIMEFRAME_MINUTES: dict[str, int] = {
    Timeframe.M5.value: 5,
    Timeframe.M15.value: 15,
    Timeframe.H1.value: 60,
    Timeframe.H4.value: 240,
    Timeframe.D1.value: 1440,
}

TIMEFRAME_PANDAS: dict[str, str] = {
    Timeframe.M5.value: "5min",
    Timeframe.M15.value: "15min",
    Timeframe.H1.value: "1h",
    Timeframe.H4.value: "4h",
    Timeframe.D1.value: "1D",
}

MTF_ORDER: list[str] = [
    Timeframe.M5.value,
    Timeframe.M15.value,
    Timeframe.H1.value,
    Timeframe.H4.value,
    Timeframe.D1.value,
]


# ---------------------------------------------------------------------------
# Market data types
# ---------------------------------------------------------------------------

@dataclass
class TickData:
    """A single bid/ask tick."""

    symbol: str
    time: datetime
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        """Mid price between bid and ask."""
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        """Raw spread in price units."""
        return self.ask - self.bid


@dataclass
class SymbolSpec:
    """Tradable instrument specification (broker contract properties)."""

    symbol: str
    tick_value: float = 1.0
    tick_size: float = 0.00001
    point: float = 0.00001
    digits: int = 5
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    spread_points: float = 12.0
    currency_profit: str = "USD"
    trade_allowed: bool = True


@dataclass
class AccountInfo:
    """Trading account snapshot."""

    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    free_margin: float = 0.0
    currency: str = "USD"
    leverage: int = 100
    profit: float = 0.0


@dataclass
class MarketState:
    """Point-in-time market context used by the strategy layer."""

    symbol: str
    spread_pips: float = 0.0
    spread_ok: bool = True
    news_ok: bool = True
    session: str = "Unknown"
    session_strength: float = 50.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Smart Money Concept types
# ---------------------------------------------------------------------------

@dataclass
class SwingPoint:
    """A confirmed fractal swing high/low."""

    index: int
    time: datetime
    price: float
    kind: str  # "HIGH" or "LOW"
    strength: float = 0.0  # displacement in ATR multiples


@dataclass
class StructureEvent:
    """A Break of Structure (BOS) or Change of Character (CHoCH) event."""

    kind: str  # "BOS" or "CHOCH"
    scope: str  # "EXTERNAL" or "INTERNAL"
    direction: Direction
    index: int
    time: datetime
    price: float
    broken_level: float
    timeframe: str


@dataclass
class OrderBlock:
    """An institutional order block zone."""

    id: str
    direction: Direction
    timeframe: str
    created_index: int
    created_time: datetime
    top: float
    bottom: float
    ref_open: float = 0.0
    ref_close: float = 0.0
    strength: float = 0.0  # 0-100 quality score
    mitigated: bool = False
    mitigation_pct: float = 0.0  # 0-100
    invalidated: bool = False
    origin: str = ""

    @property
    def mid(self) -> float:
        """Midpoint of the zone."""
        return (self.top + self.bottom) / 2.0

    @property
    def size(self) -> float:
        """Zone height in price units."""
        return abs(self.top - self.bottom)

    @property
    def active(self) -> bool:
        """True when the zone is still valid and not fully consumed."""
        return not self.invalidated and self.mitigation_pct < 100.0


@dataclass
class FairValueGap:
    """A fair value gap (imbalance) zone."""

    id: str
    direction: Direction
    timeframe: str
    created_index: int
    created_time: datetime
    top: float
    bottom: float
    size_atr: float = 0.0
    mitigated: bool = False
    mitigation_pct: float = 0.0
    invalidated: bool = False

    @property
    def mid(self) -> float:
        """Midpoint of the gap."""
        return (self.top + self.bottom) / 2.0

    @property
    def size(self) -> float:
        """Gap height in price units."""
        return abs(self.top - self.bottom)

    @property
    def active(self) -> bool:
        """True when the gap still offers an unfilled imbalance."""
        return not self.invalidated and self.mitigation_pct < 100.0


@dataclass
class LiquiditySweep:
    """A wick beyond a swing level that closes back inside (liquidity grab)."""

    time: datetime
    index: int
    side: str  # "HIGH" (buy-side swept) or "LOW" (sell-side swept)
    swept_level: float
    wick_price: float
    close_price: float
    timeframe: str
    displacement: bool = False
    bias: Direction = Direction.NEUTRAL
    strength: float = 0.0


@dataclass
class EqualPool:
    """Equal highs or equal lows liquidity pool."""

    kind: str  # "HIGH" or "LOW"
    price: float
    count: int
    timeframe: str
    times: list[datetime] = field(default_factory=list)


@dataclass
class Zone:
    """Supply or demand zone derived from order blocks."""

    kind: str  # "SUPPLY" or "DEMAND"
    timeframe: str
    top: float
    bottom: float
    strength: float
    created_time: datetime
    mitigated: bool = False
    invalidated: bool = False
    origin: str = ""


@dataclass
class PremiumDiscount:
    """Position of price inside the current dealing range."""

    state: str  # "PREMIUM" | "DISCOUNT" | "EQUILIBRIUM"
    position_pct: float  # 0 = range low, 100 = range high
    range_high: float
    range_low: float
    equilibrium: float


@dataclass
class TimeframeAnalysis:
    """Complete Smart Money analysis for one symbol/timeframe."""

    timeframe: str
    bias: Direction = Direction.NEUTRAL
    trend_external: Direction = Direction.NEUTRAL
    trend_internal: Direction = Direction.NEUTRAL
    current_price: float = 0.0
    atr: float = 0.0
    atr_mean: float = 0.0
    bar_count: int = 0
    momentum: float = 0.0
    swings: list[SwingPoint] = field(default_factory=list)
    internal_swings: list[SwingPoint] = field(default_factory=list)
    bos_external: list[StructureEvent] = field(default_factory=list)
    choch_external: list[StructureEvent] = field(default_factory=list)
    bos_internal: list[StructureEvent] = field(default_factory=list)
    choch_internal: list[StructureEvent] = field(default_factory=list)
    order_blocks: list[OrderBlock] = field(default_factory=list)
    fvgs: list[FairValueGap] = field(default_factory=list)
    sweeps: list[LiquiditySweep] = field(default_factory=list)
    equal_highs: list[EqualPool] = field(default_factory=list)
    equal_lows: list[EqualPool] = field(default_factory=list)
    supply_zones: list[Zone] = field(default_factory=list)
    demand_zones: list[Zone] = field(default_factory=list)
    premium_discount: Optional[PremiumDiscount] = None

    @property
    def all_bos(self) -> list[StructureEvent]:
        """External + internal BOS events ordered by bar index."""
        return sorted(self.bos_external + self.bos_internal, key=lambda e: e.index)

    @property
    def all_choch(self) -> list[StructureEvent]:
        """External + internal CHoCH events ordered by bar index."""
        return sorted(self.choch_external + self.choch_internal, key=lambda e: e.index)


@dataclass
class MTFAnalysis:
    """Multi-timeframe Smart Money analysis for one symbol."""

    symbol: str
    time: datetime
    analyses: dict[str, TimeframeAnalysis] = field(default_factory=dict)
    overall_bias: Direction = Direction.NEUTRAL
    higher_tf_trend: Direction = Direction.NEUTRAL

    def get(self, timeframe: str) -> Optional[TimeframeAnalysis]:
        """Return the analysis for a timeframe, if present."""
        return self.analyses.get(timeframe)


# ---------------------------------------------------------------------------
# Strategy / signal types
# ---------------------------------------------------------------------------

@dataclass
class TradeSignal:
    """A strategy decision for one symbol at one point in time."""

    action: SignalAction
    symbol: str
    confidence: float = 0.0
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    reasoning: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)
    timeframe: str = Timeframe.M15.value
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    setup_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_entry(self) -> bool:
        """True for actionable BUY/SELL signals."""
        return self.action in (SignalAction.BUY, SignalAction.SELL)

    @property
    def direction(self) -> Direction:
        """Signal direction as a Direction enum."""
        if self.action is SignalAction.BUY:
            return Direction.BULLISH
        if self.action is SignalAction.SELL:
            return Direction.BEARISH
        return Direction.NEUTRAL

    @property
    def risk_distance(self) -> float:
        """Entry to stop-loss distance in price units."""
        return abs(self.entry - self.stop_loss)

    @property
    def reward_distance(self) -> float:
        """Entry to take-profit distance in price units."""
        return abs(self.take_profit - self.entry)

    @property
    def reward_risk(self) -> float:
        """Planned reward-to-risk ratio."""
        risk = self.risk_distance
        if risk <= 0:
            return 0.0
        return self.reward_distance / risk


# ---------------------------------------------------------------------------
# Execution types
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """An open trading position."""

    ticket: str
    symbol: str
    action: SignalAction
    volume: float
    entry: float
    stop_loss: float = 0.0
    take_profit: float = 0.0
    open_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    comment: str = ""
    magic: int = 0
    current_price: float = 0.0
    profit: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    confidence: float = 0.0

    @property
    def direction(self) -> Direction:
        """Position direction as a Direction enum."""
        if self.action is SignalAction.BUY:
            return Direction.BULLISH
        return Direction.BEARISH

    @property
    def net_profit(self) -> float:
        """Floating profit after costs."""
        return self.profit + self.swap - self.commission

    @property
    def has_stop(self) -> bool:
        """True when a stop-loss is attached."""
        return self.stop_loss > 0.0

    @property
    def has_take_profit(self) -> bool:
        """True when a take-profit is attached."""
        return self.take_profit > 0.0


@dataclass
class OrderResult:
    """Result of an order placement attempt."""

    success: bool
    ticket: str = ""
    price: float = 0.0
    volume: float = 0.0
    message: str = ""
    latency_ms: float = 0.0
    retries: int = 0


@dataclass
class CloseResult:
    """Result of a position close attempt."""

    success: bool
    ticket: str = ""
    price: float = 0.0
    profit: float = 0.0
    message: str = ""
    latency_ms: float = 0.0


@dataclass
class CloseAllResult:
    """Aggregate result of a close-all operation."""

    requested: int = 0
    closed: int = 0
    failed: int = 0
    total_profit: float = 0.0
    message: str = ""

    @property
    def all_closed(self) -> bool:
        """True when every requested position was closed."""
        return self.requested > 0 and self.failed == 0 and self.closed == self.requested


@dataclass
class BasketSnapshot:
    """Point-in-time snapshot of the multi-position basket."""

    count: int = 0
    total_lots: float = 0.0
    avg_entry: float = 0.0
    floating: float = 0.0
    highest: float = 0.0
    target: float = 0.0
    trailing_active: bool = False
    trail_level: float = 0.0
    direction: Direction = Direction.NEUTRAL
    duration_sec: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
