"""Multi-position basket: combined PnL target and trailing-basket mode."""
from __future__ import annotations

from datetime import datetime

from core.types import BasketSnapshot, Direction, Position, SignalAction
from utils.common import utcnow


class BasketManager:
    """Treats every open position as one basket with a single profit target."""

    def __init__(
        self,
        target: float = 100.0,
        trailing_enabled: bool = False,
        trailing_pct: float = 15.0,
    ) -> None:
        """Configure the basket target and optional trailing behaviour."""
        self.target = float(target)
        self.trailing_enabled = trailing_enabled
        self.trailing_pct = max(0.0, min(95.0, float(trailing_pct)))
        self.highest = 0.0
        self.trailing_active = False
        self.trail_level = 0.0
        self.snapshot = BasketSnapshot(target=self.target)

    def reset(self) -> None:
        """Clear trailing state after a basket close (fresh basket next)."""
        self.highest = 0.0
        self.trailing_active = False
        self.trail_level = 0.0
        self.snapshot = BasketSnapshot(target=self.target)

    def update(self, positions: list[Position], now: datetime | None = None) -> BasketSnapshot:
        """Recompute the basket snapshot from live positions."""
        now = now or utcnow()
        open_positions = [p for p in positions if p.volume > 0]
        count = len(open_positions)
        if count == 0:
            self.snapshot = BasketSnapshot(target=self.target, timestamp=now)
            return self.snapshot
        total_lots = sum(p.volume for p in open_positions)
        avg_entry = (
            sum(p.entry * p.volume for p in open_positions) / total_lots
            if total_lots > 0 else 0.0
        )
        floating = sum(p.net_profit for p in open_positions)
        buy_lots = sum(p.volume for p in open_positions if p.action is SignalAction.BUY)
        sell_lots = total_lots - buy_lots
        if buy_lots > 0 and sell_lots > 0:
            direction = Direction.NEUTRAL  # hedged/mixed basket
        elif buy_lots > 0:
            direction = Direction.BULLISH
        else:
            direction = Direction.BEARISH
        earliest = min(p.open_time for p in open_positions)
        duration = max(0.0, (now - earliest).total_seconds())
        if floating > self.highest:
            self.highest = floating
        if (
            self.trailing_enabled
            and not self.trailing_active
            and floating >= self.target
        ):
            self.trailing_active = True
        if self.trailing_active:
            self.trail_level = self.highest * (1.0 - self.trailing_pct / 100.0)
        self.snapshot = BasketSnapshot(
            count=count, total_lots=round(total_lots, 2),
            avg_entry=avg_entry, floating=floating, highest=self.highest,
            target=self.target, trailing_active=self.trailing_active,
            trail_level=self.trail_level, direction=direction,
            duration_sec=duration, timestamp=now,
        )
        return self.snapshot

    def should_close(self) -> tuple[bool, str]:
        """Decide whether the whole basket must be closed right now."""
        snap = self.snapshot
        if snap.count == 0:
            return False, ""
        if not self.trailing_enabled:
            if snap.floating >= self.target:
                return True, (
                    f"BASKET_TARGET_HIT profit={snap.floating:.2f} "
                    f"target={self.target:.2f}"
                )
            return False, ""
        if self.trailing_active and snap.floating <= self.trail_level:
            return True, (
                f"BASKET_TRAIL_HIT profit={snap.floating:.2f} "
                f"trail={self.trail_level:.2f} highest={self.highest:.2f}"
            )
        return False, ""
