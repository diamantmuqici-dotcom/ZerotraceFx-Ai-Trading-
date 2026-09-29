"""Production-only safety contracts."""
from __future__ import annotations

from core.engine import ZeroTraceEngine
from core.process_detector import ProcessMatch, discover_sessions
from market.mt5_client import MT5Client


def test_mt5_client_never_keeps_credentials():
    client = MT5Client()
    assert not hasattr(client, "password")
    assert not hasattr(client, "login")
    assert not hasattr(client, "server")


def test_production_engine_forces_real_broker(settings):
    engine = ZeroTraceEngine(settings, allow_research=False)
    try:
        assert engine.settings.mode == "LIVE"
        assert engine.broker.__class__.__name__ == "MT5Executor"
        assert "Waiting for authenticated MT5 session" in engine.state.status_message
    finally:
        engine.shutdown()


def test_browser_detection_requires_mt5_window_title():
    browser = ProcessMatch("chrome.exe", 1, "Personal - Google")
    assert not discover_sessions([browser]).web_running
    terminal = ProcessMatch("chrome.exe", 2, "MetaTrader 5 Web Terminal")
    assert discover_sessions([terminal]).web_running
