"""Dashboard design-system and demo-feed tests (no Qt required)."""
from __future__ import annotations

import importlib

from core.state import RuntimeState
from dashboard import theme
from dashboard.demo import SimulatedFeed


def test_palette_tokens_are_hex():
    for value in (theme.BG, theme.SURFACE, theme.ACCENT, theme.LOSS, theme.WARN):
        assert value.startswith("#") and len(value) == 7


def test_tones_resolve():
    assert theme.tone_color(theme.GOOD) == theme.ACCENT
    assert theme.tone_color(theme.BAD) == theme.LOSS
    assert theme.pnl_tone(12.5) == theme.GOOD
    assert theme.pnl_tone(-1.0) == theme.BAD
    assert theme.drawdown_tone(0.4) == theme.GOOD
    assert theme.drawdown_tone(3.1) == theme.WARN_TONE
    assert theme.drawdown_tone(6.2) == theme.BAD


def test_formatting_helpers():
    assert theme.money(1234.5) == "$1,234.50"
    assert theme.money(-42.0, sign=True) == "-$42.00"
    assert theme.money(42.0, sign=True) == "+$42.00"
    assert theme.percent(1.234) == "1.23%"
    assert theme.price(1.08421) == "1.08421"


def test_qss_covers_core_widgets():
    sheet = theme.qss()
    for selector in ("QMainWindow", "QPushButton#danger", "QTableWidget",
                     "QTabBar::tab:selected", "QScrollBar:vertical",
                     "QFrame#card", "QStatusBar"):
        assert selector in sheet
    assert theme.ACCENT in sheet and theme.BG in sheet


def test_app_module_imports_without_qt():
    module = importlib.import_module("dashboard.app")
    assert callable(module.launch_dashboard)
    assert callable(module.create_application)


def test_demo_snapshot_matches_runtime_state_keys():
    feed = SimulatedFeed(seed=3)
    state_keys = set(RuntimeState().snapshot())
    feed_keys = set(feed.snapshot())
    assert feed_keys == state_keys


def test_demo_position_rows_match_state_shape():
    feed = SimulatedFeed(seed=3)
    state = RuntimeState()
    state.update(open_positions=[])
    feed_pos = feed.snapshot()["open_positions"][0]
    state_pos = {
        "ticket": 1, "symbol": "EURUSD", "action": "BUY", "volume": 0.1,
        "entry": 1.0, "current": 1.0, "sl": 0.9, "tp": 1.2, "profit": 1.0,
        "confidence": 90.0,
    }
    assert set(feed_pos) == set(state_pos)


def test_demo_feed_ticks_and_stays_bounded():
    feed = SimulatedFeed(seed=11)
    before = feed.snapshot()
    for _ in range(600):
        feed.tick()
    after = feed.snapshot()
    assert len(after["equity_curve"]) <= 500
    assert after["equity_times"][-1] != before["equity_times"][0]
    assert after["updated_at"]


def test_demo_controls_round_trip():
    feed = SimulatedFeed(seed=5)
    feed.set_paused(True)
    assert feed.snapshot()["paused"] is True
    result = feed.close_all()
    assert result["closed"] >= 0
    assert feed.snapshot()["open_positions"] == []
    feed.kill_switch = True
    feed.reset_kill_switch()
    assert feed.snapshot()["kill_switch"] is False
