"""Tests for settings, constants, events, state and the journal."""
from __future__ import annotations

import json

from config.constants import APP_NAME, APP_VERSION, DEFAULT_SYMBOLS
from config.settings import Settings, env_file_status, get_settings, reset_settings
from core.events import Event, get_event_bus
from core.state import RuntimeState
from utils.journal import TradeJournal


def test_app_constants():
    """Product identity constants are set."""
    assert APP_NAME == "ZeroTrace FX AI"
    assert APP_VERSION == "1.2.2"
    assert DEFAULT_SYMBOLS == ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]


def test_settings_defaults():
    """Defaults match the institutional specification."""
    # _env_file=None: a developer's local .env (ACCOUNT_MODE=LIVE, ...)
    # must not change what the *defaults* are.
    settings = Settings(_env_file=None)
    assert settings.mode == "PAPER"
    assert settings.symbol_list == ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]
    assert settings.confidence_threshold == 85.0
    assert settings.risk_percent == 1.0
    assert settings.basket_target == 100.0
    assert settings.min_rr == 2.0
    assert settings.news_csv_path is None


def test_settings_env_override(monkeypatch):
    """Environment variables override every default."""
    monkeypatch.setenv("ACCOUNT_MODE", "live")
    monkeypatch.setenv("SYMBOLS", "EURUSD, XAUUSD")
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "90")
    monkeypatch.setenv("BASKET_TARGET", "250")
    reset_settings()
    settings = get_settings()
    assert settings.mode == "LIVE"
    assert settings.symbol_list == ["EURUSD", "XAUUSD"]
    assert settings.confidence_threshold == 90.0
    assert settings.basket_target == 250.0
    reset_settings()


def test_settings_cached_singleton():
    """get_settings returns one cached instance until reset."""
    reset_settings()
    assert get_settings() is get_settings()
    reset_settings()
    assert get_settings() is get_settings()


async def test_event_bus_pub_sub():
    """Handlers receive published payloads; failures never propagate."""
    bus = get_event_bus()
    received = []

    async def _ok(event, payload):
        received.append((event, payload))

    async def _boom(event, payload):
        raise RuntimeError("handler bug")

    await bus.subscribe(Event.SIGNAL, _ok)
    await bus.subscribe(Event.SIGNAL, _boom)
    await bus.publish(Event.SIGNAL, {"symbol": "EURUSD"})
    await bus.unsubscribe(Event.SIGNAL, _ok)
    await bus.unsubscribe(Event.SIGNAL, _boom)
    assert received == [(Event.SIGNAL, {"symbol": "EURUSD"})]


def test_runtime_state_snapshot_and_trades():
    """State tracks equity, trades and win rate for the dashboard."""
    state = RuntimeState()
    assert state.snapshot()["mode"] == "PAPER"
    state.update(balance=10000.0, equity=10100.0)
    state.push_trade({"symbol": "EURUSD", "profit": 50.0})
    state.push_trade({"symbol": "EURUSD", "profit": -20.0})
    snap = state.snapshot()
    assert snap["total_trades"] == 2
    assert snap["win_rate"] == 50.0
    assert snap["balance"] == 10000.0


def test_trade_journal_records(tmp_path):
    """Journal persists signals, fills and closes to JSONL + CSV."""
    from datetime import datetime, timezone

    from core.types import SignalAction, TradeSignal

    journal = TradeJournal(str(tmp_path))
    signal = TradeSignal(action=SignalAction.BUY, symbol="EURUSD",
                         confidence=92.5, entry=1.1, stop_loss=1.09,
                         take_profit=1.12, reasoning=["test"],
                         timestamp=datetime.now(timezone.utc), setup_id="s1")
    journal.record_signal(signal)
    journal.record_fill("EURUSD", "BUY", "1", 0.2, 1.1, 1.09, 1.12, 92.5, "s1")
    journal.record_close("EURUSD", "BUY", "1", 0.2, 1.1, 1.12, 40.0, "TP")
    journal.record_basket("CLOSED", {"profit": 40.0})
    lines = (tmp_path / "journal.jsonl").read_text().strip().split("\n")
    assert len(lines) == 4
    assert json.loads(lines[0])["event"] == "SIGNAL"
    assert "CLOSE" in (tmp_path / "journal.csv").read_text()


def test_env_file_status_found(tmp_path, monkeypatch):
    """A real .env is reported as found with its path."""
    from config import settings as settings_module

    (tmp_path / ".env").write_text("ACCOUNT_MODE=LIVE\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings_module, "app_dir", lambda: str(tmp_path))
    status, path = env_file_status()
    assert status == "found"
    assert path == str(tmp_path / ".env")


def test_env_file_status_misnamed_env_txt(tmp_path, monkeypatch):
    """.env.txt (the Windows Notepad gotcha) is flagged as misnamed."""
    from config import settings as settings_module

    (tmp_path / ".env.txt").write_text("ACCOUNT_MODE=LIVE\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings_module, "app_dir", lambda: str(tmp_path))
    status, path = env_file_status()
    assert status == "misnamed"
    assert path and path.endswith(".env.txt")


def test_env_file_status_missing(tmp_path, monkeypatch):
    """No .env anywhere means the app silently runs on PAPER defaults."""
    from config import settings as settings_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings_module, "app_dir", lambda: str(tmp_path))
    status, path = env_file_status()
    assert status == "missing"
    assert path is None
