"""Tests for the adaptive learner and its integration with trading."""
from __future__ import annotations

from core.engine import default_spec
from core.state import RuntimeState
from core.types import Direction, SignalAction
from execution.order_manager import OrderManager
from live.live_trader import LiveTrader
from market.data_engine import MarketDataEngine
from market.filters import EconomicCalendar
from paper.paper_broker import PaperBroker
from risk.basket import BasketManager
from risk.risk_manager import RiskManager
from strategy.ai_engine import AIDecisionEngine, AIFeatures
from strategy.learning import AdaptiveLearner
from strategy.strategy import Strategy
from utils.journal import TradeJournal

STRONG = {"htf_trend": 100.0, "liquidity_sweep": 100.0, "momentum": 10.0}


def test_winners_raise_and_losers_lower_weights():
    learner = AdaptiveLearner()
    learner.register_entry("1", "EURUSD", "BUY", 90, STRONG, risk_money=100)
    learner.record_outcome("1", 200.0)
    assert learner.multiplier("htf_trend") > 1.0
    assert learner.multiplier("momentum") < 1.0
    learner.register_entry("2", "EURUSD", "BUY", 90, STRONG, risk_money=100)
    learner.record_outcome("2", -100.0)
    learner.register_entry("3", "EURUSD", "BUY", 90, STRONG, risk_money=100)
    learner.record_outcome("3", -100.0)
    assert learner.multiplier("htf_trend") < 1.0


def test_multipliers_are_bounded():
    learner = AdaptiveLearner(learning_rate=1.0)
    for i in range(200):
        learner.register_entry(str(i), "EURUSD", "BUY", 90, STRONG, risk_money=10)
        learner.record_outcome(str(i), 1000.0)
    assert learner.multiplier("htf_trend") <= 2.0
    assert learner.multiplier("momentum") >= 0.5


def test_threshold_rises_after_losing_streak():
    learner = AdaptiveLearner(min_trades_for_calibration=3)
    for i in range(6):
        learner.register_entry(str(i), "GBPUSD", "SELL", 88, STRONG, risk_money=50)
        learner.record_outcome(str(i), -50.0)
    assert learner.threshold_offset("GBPUSD") > 0
    engine = AIDecisionEngine(threshold=85.0, learner=learner)
    feats = AIFeatures(direction=Direction.BEARISH, **{k: 100.0 for k in (
        "htf_trend", "structure", "bos", "choch", "ob_quality", "fvg_quality",
        "liquidity_sweep", "volatility", "session", "spread", "momentum")})
    decision = engine.score(feats, symbol="GBPUSD")
    assert decision.threshold > 85.0
    assert learner.state.signals_inspected == 1


def test_memory_persists_and_survives_corruption(tmp_path):
    path = str(tmp_path / "mem.json")
    learner = AdaptiveLearner(path)
    learner.register_entry("9", "XAUUSD", "BUY", 90, STRONG, risk_money=10)
    learner.record_outcome("9", 25.0)
    again = AdaptiveLearner(path)
    assert again.state.trades_learned == 1
    assert again.multiplier("htf_trend") == learner.multiplier("htf_trend")
    (tmp_path / "mem.json").write_text("{not json")
    fresh = AdaptiveLearner(path)
    assert fresh.state.trades_learned == 0


async def test_live_trader_learns_from_broker_sl_tp(settings, tmp_path):
    """A position closed by its TP at the broker is detected and learned."""
    from tests.conftest import drift_closes, make_df

    settings.symbols = "EURUSD"
    settings.basket_target = 1_000_000.0
    data = MarketDataEngine()
    data.set_offline("EURUSD", "M5", make_df(drift_closes(400, 1.1, 0.00005, 0.0004, 51)))
    broker = PaperBroker({"EURUSD": default_spec("EURUSD")}, balance=10000)
    broker.connect()
    learner = AdaptiveLearner()
    orders = OrderManager(broker, max_retries=1, retry_delay_sec=0.0, verify_delay_sec=0.0)
    risk = RiskManager(settings)
    trader = LiveTrader(
        settings, data, Strategy(settings, ai=AIDecisionEngine(learner=learner)),
        orders, risk, BasketManager(target=settings.basket_target),
        TradeJournal(str(tmp_path)), RuntimeState(mode="PAPER"), EconomicCalendar(),
    )
    broker.set_price("EURUSD", 1.1000, 1.1001)
    opened = broker.place_market_order("EURUSD", SignalAction.BUY, 0.10,
                                       stop_loss=1.0950, take_profit=1.1050)
    assert opened.success
    trader._tracked[opened.ticket] = {"booked": 0.0, "basket": False, "misses": 0,
                                      "symbol": "EURUSD", "action": "BUY",
                                      "volume": 0.1, "entry": 1.1001}
    trader._adopted = True
    learner.register_entry(opened.ticket, "EURUSD", "BUY", 90, STRONG, risk_money=50)
    broker.set_price("EURUSD", 1.1060, 1.1061)  # TP hit at the broker
    assert broker.get_positions() == []
    trader._reconcile_closed([])
    assert learner.state.trades_learned == 1
    assert opened.ticket not in trader._tracked
    assert risk.daily_pnl > 0


async def test_remote_api_requires_token():
    """Remote API rejects bad tokens and serves state with the right one."""
    import pytest
    from aiohttp.test_utils import TestClient, TestServer

    from remote.api import build_app

    with pytest.raises(ValueError):
        build_app(RuntimeState(), "short")
    state = RuntimeState(mode="PAPER")
    state.update(balance=1234.0)
    app = build_app(state, "x" * 20, on_close_all=lambda: {"closed": 0})
    async with TestClient(TestServer(app)) as client:
        bad = await client.get("/api/status", headers={"Authorization": "Bearer nope"})
        assert bad.status == 401
        hdr = {"Authorization": "Bearer " + "x" * 20}
        ok = await client.get("/api/status", headers=hdr)
        assert (await ok.json())["balance"] == 1234.0
        paused = await client.post("/api/pause", json={"paused": True}, headers=hdr)
        assert (await paused.json())["paused"] is True and state.paused
        closed = await client.post("/api/close_all", headers=hdr)
        assert (await closed.json())["closed"] == 0
