"""Tests for the simulated paper broker: fills, costs, stops and margin."""
from __future__ import annotations

import pytest

from core.engine import default_spec
from core.types import SignalAction
from paper.paper_broker import PaperBroker


@pytest.fixture()
def broker() -> PaperBroker:
    """A funded paper broker quoting EURUSD."""
    venue = PaperBroker({"EURUSD": default_spec("EURUSD")}, balance=10000.0)
    assert venue.connect() is True
    venue.set_price("EURUSD", 1.1000, 1.1001)
    return venue


def test_market_fill_marks_profit(broker):
    """A BUY shows profit when price rises, including slippage cost."""
    result = broker.place_market_order("EURUSD", SignalAction.BUY, 1.00,
                                       stop_loss=1.0900, take_profit=1.1200)
    assert result.success is True
    assert result.ticket
    positions = broker.get_positions("EURUSD")
    assert len(positions) == 1
    assert positions[0].commission > 0  # half commission on open
    broker.set_price("EURUSD", 1.1050, 1.1051)
    profit = broker.get_positions()[0].profit
    assert profit > 400.0  # ~50 pips x $10/pip/lot minus costs


def test_stop_loss_closes_at_level(broker):
    """A breached stop closes the position and books the loss."""
    broker.place_market_order("EURUSD", SignalAction.BUY, 0.50,
                              stop_loss=1.0950, take_profit=1.1200)
    broker.set_price("EURUSD", 1.0940, 1.0941)
    assert broker.get_positions() == []
    account = broker.account_info()
    assert account is not None and account.balance < 10000.0


def test_take_profit_closes_at_level(broker):
    """A reached target closes the position and books the gain."""
    broker.place_market_order("EURUSD", SignalAction.SELL, 0.50,
                              stop_loss=1.1100, take_profit=1.0950)
    broker.set_price("EURUSD", 1.0960, 1.0961)
    broker.set_price("EURUSD", 1.0940, 1.0941)
    assert broker.get_positions() == []
    account = broker.account_info()
    assert account is not None and account.balance > 10000.0


def test_intrabar_stops_on_bar(broker):
    """on_bar triggers stops from candle extremes before marking the close."""
    broker.place_market_order("EURUSD", SignalAction.BUY, 0.50,
                              stop_loss=1.0950, take_profit=1.1200)
    broker.on_bar("EURUSD", bar_high=1.1010, bar_low=1.0940, bar_close=1.1005)
    assert broker.get_positions() == []  # SL traded inside the bar


def test_partial_close_reduces_volume(broker):
    """Partial closes bank profit and leave a runner."""
    result = broker.place_market_order("EURUSD", SignalAction.BUY, 1.00)
    broker.set_price("EURUSD", 1.1050, 1.1051)
    closed = broker.close_position(result.ticket, 0.40)
    assert closed.success is True and closed.profit > 0
    remaining = broker.get_positions()
    assert len(remaining) == 1
    assert remaining[0].volume == pytest.approx(0.60)


def test_close_all_empties_book(broker):
    """close_all closes every position and reports the aggregate."""
    broker.place_market_order("EURUSD", SignalAction.BUY, 0.10)
    broker.place_market_order("EURUSD", SignalAction.SELL, 0.10)
    outcome = broker.close_all()
    assert outcome.requested == 2
    assert outcome.all_closed is True
    assert broker.get_positions() == []


def test_rejects_unknown_symbol_and_dust(broker):
    """Unknown symbols and sub-minimum volume fail cleanly."""
    assert broker.place_market_order("NOPE", SignalAction.BUY, 0.1).success is False
    assert broker.place_market_order("EURUSD", SignalAction.BUY, 0.001).success is False
    assert broker.place_market_order("EURUSD", SignalAction.BUY, 0.1).success is True


def test_modify_updates_stops(broker):
    """SL/TP modification persists on the simulated position."""
    result = broker.place_market_order("EURUSD", SignalAction.BUY, 0.10,
                                       stop_loss=1.0900, take_profit=1.1200)
    assert broker.modify_position(result.ticket, 1.0950, 1.1150) is True
    position = broker.get_positions()[0]
    assert position.stop_loss == 1.0950
    assert position.take_profit == 1.1150
    assert broker.modify_position("999999", 1.0, 2.0) is False


def test_account_equity_tracks_floating(broker):
    """Equity equals balance plus floating profit."""
    broker.place_market_order("EURUSD", SignalAction.BUY, 1.00)
    broker.set_price("EURUSD", 1.1100, 1.1101)
    account = broker.account_info()
    assert account is not None
    assert account.equity > account.balance
    assert account.free_margin <= account.equity
