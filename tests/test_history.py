"""Trade history persistence: journal reader, restart seeding, manual close."""
from __future__ import annotations

from core.engine import ZeroTraceEngine
from utils.journal import TradeJournal


def test_journal_read_closes_round_trip(tmp_path):
    journal = TradeJournal(str(tmp_path))
    journal.record_close("EURUSD", "BUY", "4821103", 0.4, 1.0833, 1.0883, 12.9,
                         reason="TP")
    journal.record_close("XAUUSD", "SELL", "4821105", 0.1, 2382.5, 2377.3, 30.9,
                         reason="SL/TP")
    journal.record_basket("CLOSED", {"reason": "target", "closed": 2,
                                     "failed": 0, "profit": 43.8})
    rows = journal.read_closes()
    assert len(rows) == 3
    assert rows[0]["symbol"] == "EURUSD" and rows[0]["profit"] == 12.9
    assert rows[1]["action"].startswith("SELL")
    assert rows[2]["symbol"] == "BASKET" and rows[2]["profit"] == 43.8
    assert journal.read_closes(limit=1)[-1]["symbol"] == "BASKET"


def test_engine_seeds_history_from_journal(settings):
    engine = ZeroTraceEngine(settings)
    engine.journal.record_close("GBPUSD", "BUY", "1", 0.2, 1.26, 1.27, 55.0,
                                reason="TP")
    engine.journal.record_close("EURUSD", "SELL", "2", 0.2, 1.09, 1.095, -18.0,
                                reason="SL/TP")
    seeded = engine.seed_history()
    assert seeded >= 2
    snap = engine.state.snapshot()
    assert snap["recent_trades"], "history tab must survive restarts"
    assert snap["recent_trades"][0]["symbol"] in {"EURUSD", "GBPUSD"}
    assert snap["total_trades"] >= 2
    assert 0.0 < snap["win_rate"] < 100.0
    engine.shutdown()


def test_manual_close_all_reaches_history_once(settings):
    engine = ZeroTraceEngine(settings)
    before = len(engine.state.snapshot()["recent_trades"])
    result = engine.manual_close_all()
    after = engine.state.snapshot()["recent_trades"]
    assert result["closed"] == 0  # nothing open in a fresh paper book
    assert len(after) == before
    # simulate a tracked position being flattened by the operator
    engine.trader._tracked["999"] = {"booked": 0.0, "basket": False, "misses": 0,
                                     "symbol": "EURUSD", "action": "BUY",
                                     "volume": 0.1, "entry": 1.08}
    engine.trader.adopt_manual_close(21.5, "operator close-all (1 positions)")
    rows = engine.state.snapshot()["recent_trades"]
    assert rows[0]["action"] == "MANUAL CLOSE"
    assert rows[0]["profit"] == 21.5
    assert engine.trader._tracked["999"]["basket"] is True
    engine.shutdown()
