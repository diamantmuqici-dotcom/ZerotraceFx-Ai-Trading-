"""Tests for the multi-position basket: tracking, target and trailing."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.types import Direction, Position, SignalAction
from risk.basket import BasketManager


def _pos(ticket: str, entry: float, profit: float, volume: float = 0.20,
         action: SignalAction = SignalAction.SELL, minutes_ago: int = 10) -> Position:
    """Build an open position with a preset floating profit."""
    return Position(
        ticket=ticket, symbol="EURUSD", action=action, volume=volume,
        entry=entry, current_price=entry, profit=profit,
        open_time=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )


def test_basket_tracks_four_sell_positions():
    """Four SELL 0.20 lots aggregate into one basket snapshot."""
    basket = BasketManager(target=100.0)
    positions = [_pos(str(i), 1.1000, 10.0) for i in range(4)]
    snap = basket.update(positions)
    assert snap.count == 4
    assert snap.total_lots == 0.80
    assert snap.avg_entry == 1.1000
    assert snap.floating == 40.0
    assert snap.direction is Direction.BEARISH
    assert snap.duration_sec >= 600


def test_basket_averages_mixed_entries():
    """Volume-weighted average entry across different fill prices."""
    basket = BasketManager(target=100.0)
    positions = [_pos("1", 1.1000, 0.0, 0.20), _pos("2", 1.1020, 0.0, 0.40)]
    snap = basket.update(positions)
    assert snap.avg_entry == pytest.approx(1.1000 * (0.2 / 0.6) + 1.1020 * (0.4 / 0.6))


def test_basket_target_closes_instantly():
    """Floating >= target triggers an immediate close-all verdict."""
    basket = BasketManager(target=25.0)
    basket.update([_pos("1", 1.1000, 12.0), _pos("2", 1.1000, 13.0)])
    should_close, reason = basket.should_close()
    assert should_close is True
    assert "BASKET_TARGET_HIT" in reason


def test_basket_holds_below_target():
    """Below target the basket keeps running."""
    basket = BasketManager(target=100.0)
    basket.update([_pos("1", 1.1000, 40.0)])
    assert basket.should_close() == (False, "")


def test_trailing_basket_locks_in_profit():
    """Trailing: $680 peak at 15% trails to $578 and closes on the fall."""
    basket = BasketManager(target=500.0, trailing_enabled=True, trailing_pct=15.0)
    basket.update([_pos("1", 1.1000, 510.0)])
    assert basket.trailing_active is True
    assert basket.should_close() == (False, "")  # above target: ride it
    basket.update([_pos("1", 1.1000, 680.0)])
    assert basket.highest == 680.0
    assert basket.trail_level == 680.0 * 0.85  # 578.0
    assert basket.should_close() == (False, "")
    basket.update([_pos("1", 1.1000, 578.0)])
    should_close, reason = basket.should_close()
    assert should_close is True
    assert "BASKET_TRAIL_HIT" in reason


def test_trailing_inactive_below_target():
    """Trailing never closes a basket that never reached the target."""
    basket = BasketManager(target=500.0, trailing_enabled=True, trailing_pct=15.0)
    basket.update([_pos("1", 1.1000, 200.0)])
    assert basket.trailing_active is False
    assert basket.should_close() == (False, "")


def test_basket_reset_clears_trailing():
    """Reset returns the manager to a fresh-basket state."""
    basket = BasketManager(target=10.0, trailing_enabled=True, trailing_pct=15.0)
    basket.update([_pos("1", 1.1000, 50.0)])
    assert basket.trailing_active is True
    basket.reset()
    assert basket.highest == 0.0
    assert basket.trailing_active is False
    assert basket.snapshot.count == 0


def test_empty_basket_never_closes():
    """No positions means no close verdict."""
    basket = BasketManager(target=5.0)
    snap = basket.update([])
    assert snap.count == 0
    assert basket.should_close() == (False, "")
