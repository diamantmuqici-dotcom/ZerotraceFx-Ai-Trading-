"""Tests for the live trading loop: cycles, exits and basket closes."""
from __future__ import annotations

import pytest

from config.settings import Settings
from core.engine import default_spec
from core.state import RuntimeState
from core.types import SignalAction
from execution.order_manager import OrderManager
from live.live_trader import LiveTrader
from market.data_engine import MarketDataEngine
from market.filters import EconomicCalendar
from paper.paper_broker import PaperBroker
from risk.basket import BasketManager
from risk.risk_manager import RiskManager
from strategy.strategy import Strategy
from utils.journal import TradeJournal


def _trader(settings: Settings, tmp_path, symbols: str = "EURUSD") -> LiveTrader:
    """Assemble a LiveTrader over a paper broker with offline data."""
    from tests.conftest import drift_closes, make_df

    settings.symbols = symbols
    data = MarketDataEngine()
    for symbol in settings.symbol_list:
        closes = drift_closes(400, 1.1000, 0.00005, 0.0004, seed=51)
        data.set_offline(symbol, "M5", make_df(closes, seed=51))
    specs = {s: default_spec(s) for s in settings.symbol_list}
    broker = PaperBroker(specs, balance=settings.paper_balance)
    broker.connect()
    orders = OrderManager(broker, max_retries=1, retry_delay_sec=0.0,
                          verify_delay_sec=0.0)
    return LiveTrader(
        settings, data, Strategy(settings), orders, RiskManager(settings),
        BasketManager(target=settings.basket_target), TradeJournal(str(tmp_path)),
        RuntimeState(mode="PAPER"), EconomicCalendar(),
    )


async def test_cycle_runs_and_updates_state(settings, tmp_path):
    """A cycle scans symbols and publishes fresh dashboard state."""
    trader = _trader(settings, tmp_path)
    result = await trader.cycle()
    assert result.symbols_checked == 1
    assert trader.state.balance == settings.paper_balance
    assert "Cycle ok" in trader.state.status_message


async def test_cycle_closes_basket_at_target(settings, tmp_path):
    """A basket over target is closed instantly with stats updated."""
    settings.basket_target = 5.0
    trader = _trader(settings, tmp_path)
    broker = trader.orders.broker
    assert isinstance(broker, PaperBroker)
    broker.set_price("EURUSD", 1.1000, 1.1001)
    opened = broker.place_market_order("EURUSD", SignalAction.BUY, 1.00)
    assert opened.success
    broker.set_price("EURUSD", 1.1100, 1.1101)  # ~+$1000 floating
    result = await trader.cycle()
    assert result.basket_closed is True
    assert result.basket_profit > 5.0
    assert broker.get_positions() == []
    assert trader.state.total_trades == 1
    assert trader.risk.daily_pnl > 0


async def test_cycle_blocks_entries_on_news(settings, tmp_path):
    """News blackout notes the block and opens nothing."""
    from datetime import timedelta

    from utils.common import utcnow

    trader = _trader(settings, tmp_path)
    trader.calendar.add_event("NFP", "USD", "HIGH", utcnow() + timedelta(minutes=5))
    result = await trader.cycle()
    assert any("news blackout" in n for n in result.notes)
    assert trader.orders.broker.get_positions() == []


async def test_cycle_opens_on_stubbed_signal(settings, tmp_path, eurusd_spec):
    """A stubbed BUY signal flows through sizing into a verified fill."""
    from core.types import TradeSignal

    trader = _trader(settings, tmp_path)

    class _StubStrategy:
        async def evaluate(self, symbol, data_engine, market, spec=None):
            return TradeSignal(
                action=SignalAction.BUY, symbol=symbol, confidence=95.0,
                entry=1.1000, stop_loss=1.0950, take_profit=1.1100,
                reasoning=["stub"], setup_id="stub-1",
            )

    trader.strategy = _StubStrategy()  # type: ignore[assignment]
    result = await trader.cycle()
    assert result.orders_placed == 1
    positions = trader.orders.broker.get_positions()
    assert len(positions) == 1
    assert positions[0].volume == pytest.approx(0.20)  # 1% of 10k on 50-pip stop
