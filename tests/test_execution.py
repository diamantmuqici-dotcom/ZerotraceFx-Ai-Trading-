"""Tests for the order manager: guards, retry, verification and close-all."""
from __future__ import annotations

import pytest

from core.engine import default_spec
from core.types import SignalAction
from execution.order_manager import OrderManager
from paper.paper_broker import PaperBroker


@pytest.fixture()
def manager() -> OrderManager:
    """Order manager over a quoting paper broker."""
    venue = PaperBroker({"EURUSD": default_spec("EURUSD")}, balance=10000.0)
    venue.connect()
    venue.set_price("EURUSD", 1.1000, 1.1001)
    return OrderManager(venue, max_retries=2, retry_delay_sec=0.01,
                        verify_delay_sec=0.0)


def test_place_market_verified(manager):
    """A clean order fills and verifies against the venue book."""
    result = manager.place_market("EURUSD", SignalAction.BUY, 0.20,
                                  stop_loss=1.0900, take_profit=1.1200,
                                  max_spread_pips=3.0)
    assert result.success is True
    assert result.retries == 0
    assert manager.last_latency_ms >= 0


def test_spread_guard_blocks_wide_market(manager):
    """Excessive spread blocks before any order reaches the venue."""
    manager.broker.set_price("EURUSD", 1.1000, 1.1060)  # 60-pip spread
    result = manager.place_market("EURUSD", SignalAction.BUY, 0.20,
                                  max_spread_pips=3.0)
    assert result.success is False
    assert "spread" in result.message.lower()
    assert manager.broker.get_positions() == []


def test_failed_order_returns_after_retries(manager):
    """Impossible orders exhaust retries and report failure."""
    result = manager.place_market("EURUSD", SignalAction.BUY, 0.00001,
                                  max_spread_pips=999.0)
    assert result.success is False
    assert result.retries == 1  # max_retries=2 -> one retry


def test_close_all_verified_sweeps_book(manager):
    """Verified close-all empties the book completely."""
    manager.place_market("EURUSD", SignalAction.BUY, 0.10, max_spread_pips=99.0)
    manager.place_market("EURUSD", SignalAction.SELL, 0.10, max_spread_pips=99.0)
    outcome = manager.close_all_verified()
    assert outcome.all_closed is True
    assert manager.broker.get_positions() == []


def test_modify_verified_round_trip(manager):
    """SL/TP modification confirms through the manager."""
    result = manager.place_market("EURUSD", SignalAction.BUY, 0.10,
                                  stop_loss=1.0900, max_spread_pips=99.0)
    assert manager.modify_verified(result.ticket, 1.0950, 1.1200) is True
    assert manager.modify_verified("nope", 1.0, 2.0) is False
