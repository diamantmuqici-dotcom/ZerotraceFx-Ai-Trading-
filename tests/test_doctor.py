"""`main.py doctor` diagnostics contract (runs without MetaTrader5)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from core.diagnostics import MARKS, Check, _bar_age_minutes, collect, render
from core.engine import ZeroTraceEngine


def test_bar_age_handles_naive_and_aware_timestamps():
    now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
    naive = now.replace(tzinfo=None) - timedelta(minutes=30)
    aware = now - timedelta(minutes=5)
    assert 29.9 <= _bar_age_minutes(naive, now) <= 30.1
    assert 4.9 <= _bar_age_minutes(aware, now) <= 5.1


def test_doctor_collects_mode_and_per_symbol_checks(settings):
    engine = ZeroTraceEngine(settings, allow_research=True)
    engine.connect()
    try:
        checks = asyncio.run(collect(engine))
    finally:
        engine.shutdown()
    areas = [check.area for check in checks]
    assert "mode" in areas
    assert "mt5" in areas
    for symbol in settings.symbol_list:
        assert symbol in areas
    assert all(check.status in MARKS for check in checks)


def test_doctor_render_reports_blockers(settings):
    checks = [
        Check("mode", "FAIL", "simulator only"),
        Check("EURUSD", "WARN", "no entry - confidence 41.0 of 85 required"),
    ]
    text = render(checks)
    assert "[FAIL]" in text and "[warn]" in text
    assert "1 blocking issue(s)" in text


def test_doctor_render_clean_run():
    text = render([Check("mode", "OK", "live"), Check("EURUSD", "OK", "fresh")])
    assert "No blockers" in text
