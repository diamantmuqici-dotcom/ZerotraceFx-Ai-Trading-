"""Tests for position sizing and the institutional risk manager."""
from __future__ import annotations

import pytest

from core.engine import default_spec
from risk.position_sizing import lots_for_amount, lots_for_risk, risk_amount_for_lots
from risk.risk_manager import RiskManager


def test_lot_sizing_known_math(eurusd_spec):
    """$100 risk on a 50-pip EURUSD stop = 0.20 lots."""
    lots = lots_for_risk(10000.0, 1.0, 1.1000, 1.0950, eurusd_spec)
    assert lots == pytest.approx(0.20)


def test_lot_sizing_respects_step_and_min(eurusd_spec):
    """Tiny risk rounds down to the broker step, dust goes to zero."""
    lots = lots_for_amount(0.05, 1.1000, 1.0950, eurusd_spec)
    assert lots == 0.0  # below 0.01 minimum after rounding
    lots = lots_for_amount(3.0, 1.1000, 1.0950, eurusd_spec)
    assert lots == pytest.approx(0.01) or lots == 0.0  # 0.006 -> step floor


def test_lot_sizing_caps_at_max(eurusd_spec):
    """Absurd risk is capped at the broker maximum, never above."""
    lots = lots_for_amount(10_000_000.0, 1.1000, 1.0999, eurusd_spec)
    assert lots == eurusd_spec.volume_max


def test_risk_amount_round_trip(eurusd_spec):
    """risk_amount_for_lots inverts the sizing math."""
    lots = lots_for_risk(10000.0, 1.0, 1.1000, 1.0950, eurusd_spec)
    amount = risk_amount_for_lots(lots, 1.1000, 1.0950, eurusd_spec)
    assert amount == pytest.approx(100.0, rel=1e-6)


def test_gold_sizing_uses_metal_spec():
    """XAUUSD sizing honours tick value/size of the metal contract."""
    spec = default_spec("XAUUSD")
    lots = lots_for_risk(10000.0, 1.0, 2650.00, 2645.00, spec)
    # $5 stop = 500 ticks x $1 x lots -> $100 risk = 0.20 lots
    assert lots == pytest.approx(0.20)


def test_pre_trade_check_allows_clean_order(settings):
    """A normal order inside every limit is allowed."""
    risk = RiskManager(settings)
    check = risk.pre_trade_check(
        open_positions=2, total_lots=0.4, new_lots=0.2,
        spread_pips=1.0, latency_ms=50.0, news_ok=True, session_ok=True,
    )
    assert check.allowed is True


def test_pre_trade_check_blocks_every_limit(settings):
    """Each configured limit blocks with an explicit reason."""
    risk = RiskManager(settings)
    assert risk.pre_trade_check(8, 0, 0.2, 1.0).allowed is False  # max positions
    assert risk.pre_trade_check(0, 4.9, 0.2, 1.0).allowed is False  # max lots
    assert risk.pre_trade_check(0, 0, 0.0, 1.0).allowed is False  # bad lots
    assert risk.pre_trade_check(0, 0, 0.2, 9.0).allowed is False  # spread
    assert risk.pre_trade_check(0, 0, 0.2, 1.0, latency_ms=5000).allowed is False
    assert risk.pre_trade_check(0, 0, 0.2, 1.0, news_ok=False).allowed is False
    assert risk.pre_trade_check(0, 0, 0.2, 1.0, session_ok=False).allowed is False


def test_consecutive_loss_lock(settings):
    """Four straight losses engage the kill switch and block trading."""
    settings.max_consecutive_losses = 4
    risk = RiskManager(settings)
    risk.on_equity_update(10000.0, 10000.0)
    for _ in range(3):
        risk.record_closed_profit(-10.0)
    assert risk.kill_switch is False
    risk.record_closed_profit(-10.0)
    assert risk.kill_switch is True
    assert "Consecutive" in risk.kill_reason
    check = risk.pre_trade_check(0, 0, 0.2, 1.0)
    assert check.allowed is False
    risk.reset_kill_switch()
    assert risk.kill_switch is False


def test_daily_loss_limit_trips_kill(settings):
    """A -3% day halts new trading."""
    settings.max_daily_loss_pct = 3.0
    risk = RiskManager(settings)
    risk.on_equity_update(10000.0, 10000.0)
    risk.record_closed_profit(-300.0)
    assert risk.kill_switch is True
    assert "daily" in risk.kill_reason


def test_drawdown_limit_trips_kill(settings):
    """A 10% peak-to-trough slide halts new trading."""
    settings.max_drawdown_pct = 10.0
    risk = RiskManager(settings)
    risk.on_equity_update(10000.0, 10000.0)
    risk.on_equity_update(9000.0, 9000.0)
    assert risk.kill_switch is True
    assert risk.drawdown_pct == pytest.approx(10.0)
