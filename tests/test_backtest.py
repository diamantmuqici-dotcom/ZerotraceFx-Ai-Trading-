"""Tests for metrics, validation, charts and the simulation engine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from backtest.charts import plot_equity_curve
from backtest.engine import BacktestEngine, BacktestTrade
from backtest.metrics import compute_report
from backtest.validation import monte_carlo, walk_forward
from core.types import SignalAction, TradeSignal
from strategy.strategy import Strategy


def _trade(net: float, day: int = 1) -> BacktestTrade:
    """Build a trade booking a fixed net profit."""
    when = datetime(2026, 1, day, 12, 0, tzinfo=timezone.utc)
    return BacktestTrade(
        symbol="EURUSD", action=SignalAction.BUY, entry_time=when,
        exit_time=when + timedelta(hours=1), entry=1.1000, exit=1.1010,
        volume=0.2, stop_loss=1.0990, take_profit=1.1020,
        profit=net + 1.4, commission=1.4, exit_reason="TP",
    )


def _equity(nets: list[float], balance0: float = 10000.0):
    """Equity curve compounding trade nets across January days."""
    curve = []
    equity = balance0
    for i, net in enumerate(nets):
        equity += net
        curve.append((datetime(2026, 1, 1 + i, 12, 0, tzinfo=timezone.utc), equity))
    return curve


def test_metrics_known_values():
    """Win rate, profit factor and expectancy match hand-computed values."""
    trades = [_trade(100.0, 1), _trade(-50.0, 2), _trade(100.0, 3), _trade(-50.0, 4)]
    report = compute_report(trades, _equity([100, -50, 100, -50]))
    assert report.trades == 4
    assert report.win_rate == 50.0
    assert report.loss_rate == 50.0
    assert report.profit_factor == pytest.approx(2.0)
    assert report.expectancy == pytest.approx(25.0)
    assert report.net_profit == pytest.approx(100.0)
    assert report.total_return_pct == pytest.approx(1.0)
    assert "2026-01" in report.monthly_returns
    assert "2026" in report.yearly_returns


def test_metrics_empty_run():
    """A run with no trades reports zeros without raising."""
    report = compute_report([], [])
    assert report.trades == 0
    assert report.win_rate == 0.0
    assert report.profit_factor == 0.0


def test_metrics_all_winners_infinite_pf():
    """No losses yields an infinite profit factor and positive Sharpe."""
    trades = [_trade(50.0, d) for d in range(1, 8)]
    report = compute_report(trades, _equity([50.0] * 7))
    assert report.win_rate == 100.0
    assert report.profit_factor == float("inf")
    assert report.max_drawdown == 0.0


def test_monte_carlo_deterministic():
    """Monte Carlo is seeded: identical inputs give identical outputs."""
    nets = [100.0, -50.0, 80.0, -30.0, 60.0] * 10
    first = monte_carlo(nets, 10000.0, simulations=200, seed=42)
    second = monte_carlo(nets, 10000.0, simulations=200, seed=42)
    assert first.median_final == second.median_final
    assert first.percentile_5 < first.median_final < first.percentile_95
    assert 0.0 <= first.prob_profit <= 100.0
    assert monte_carlo([], 10000.0).simulations == 1000


def test_walk_forward_selects_and_tests():
    """Walk-forward picks the best in-sample params and scores out-of-sample."""
    frame = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=400, freq="h", tz="UTC"),
        "value": range(400),
    })

    def _run_segment(slice_df: pd.DataFrame, params: dict) -> float:
        mult = float(params.get("mult", 1.0))
        return float(slice_df["value"].sum()) * mult - 1_000_000.0 * (mult - 1.0)

    result = walk_forward(
        frame, _run_segment,
        [{"mult": 1.0}, {"mult": 2.0}], n_windows=3,
    )
    assert len(result.windows) == 3
    assert all(w.best_params for w in result.windows)
    assert isinstance(result.efficient, bool)


def test_charts_write_png(tmp_path):
    """Equity charting renders a PNG artefact."""
    path = plot_equity_curve(
        _equity([10.0, -5.0, 20.0, -3.0, 15.0]), str(tmp_path / "equity.png"))
    import os

    assert os.path.exists(path) and os.path.getsize(path) > 1000


def test_charts_reject_empty_curve():
    """Charting an empty curve raises instead of writing a blank file."""
    with pytest.raises(ValueError):
        plot_equity_curve([], "/tmp/never.png")


def _buy_once_signal(entry_offset: int = 5):
    """Signal function opening one BUY just after warmup."""
    fired = {"done": False}

    def _fn(mtf, i, row):
        if fired["done"]:
            return None
        fired["done"] = True
        entry = float(row["close"])
        return TradeSignal(
            action=SignalAction.BUY, symbol="EURUSD", confidence=90.0,
            entry=entry, stop_loss=entry - 0.0050, take_profit=entry + 0.0100,
            setup_id="test-1",
        )

    return _fn


def test_engine_runs_custom_signal_to_completion(settings, eurusd_spec, uptrend_df):
    """The simulator fills, manages and reports a scripted trade."""
    from tests.conftest import drift_closes, make_df

    closes = drift_closes(700, 1.1000, 0.00010, 0.0004, seed=31)
    m5 = make_df(closes, range_pips=0.0003, seed=31)
    engine = BacktestEngine(Strategy(settings), settings, eurusd_spec)
    result = engine.run("EURUSD", m5, signal_fn=_buy_once_signal(),
                        warmup_bars=200, signal_every=1)
    assert len(result.trades) >= 1
    assert result.report is not None and result.report.trades >= 1
    assert len(result.equity_curve) == len(m5) - 200
    assert result.final_equity > 0


def test_engine_rejects_short_history(settings, eurusd_spec, uptrend_df):
    """Too little history raises a clear error instead of mis-running."""
    engine = BacktestEngine(Strategy(settings), settings, eurusd_spec)
    with pytest.raises(ValueError):
        engine.run("EURUSD", uptrend_df, warmup_bars=5000)


def test_engine_default_strategy_smoke(settings, eurusd_spec):
    """The live strategy path executes end-to-end inside the simulator."""
    from tests.conftest import drift_closes, make_df

    closes = drift_closes(450, 1.1000, 0.00015, 0.0005, seed=41)
    m5 = make_df(closes, range_pips=0.0004, seed=41)
    settings.partial_tp_enabled = False
    engine = BacktestEngine(Strategy(settings), settings, eurusd_spec)
    result = engine.run("EURUSD", m5, warmup_bars=150, signal_every=10,
                        max_lookback_m5=450)
    assert result.report is not None
    assert len(result.equity_curve) == len(m5) - 150
