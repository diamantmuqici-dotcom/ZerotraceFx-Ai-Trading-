"""ZeroTrace FX AI - application entry point.

Modes:
  dashboard  launch the desktop UI (default; also the .exe target)
  trade      run the headless trading loop (PAPER or LIVE from .env)
  backtest   run a historical simulation from data/{SYMBOL}_M5.csv
  version    print the version and exit
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.constants import APP_NAME, APP_VERSION  # noqa: E402
from config.settings import get_settings  # noqa: E402
from utils.logging_setup import setup_logging  # noqa: E402


def cmd_version() -> int:
    """Print version info."""
    print(f"{APP_NAME} v{APP_VERSION}")
    print("Institutional Smart Money Autonomous Forex Trading Platform")
    print(f"Python {sys.version.split()[0]} on {sys.platform}")
    return 0


def cmd_trade() -> int:
    """Run the headless trading loop."""
    from core.engine import ZeroTraceEngine

    settings = get_settings()
    setup_logging(settings.logs_dir, settings.log_level)
    engine = ZeroTraceEngine(settings)
    print(f"{APP_NAME} v{APP_VERSION} - {settings.mode} headless trading")
    print(f"Symbols: {', '.join(settings.symbol_list)} | "
          f"Basket target: ${settings.basket_target:,.2f} | "
          f"Confidence: {settings.confidence_threshold:.0f}")
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        print("\nShutdown requested - stopping...")
    finally:
        engine.shutdown()
    return 0


def cmd_dashboard() -> int:
    """Run the trading engine in the background with the desktop dashboard."""
    from core.engine import ZeroTraceEngine
    from dashboard.viewmodel import DashboardViewModel

    settings = get_settings()
    setup_logging(settings.logs_dir, settings.log_level)
    engine = ZeroTraceEngine(settings)
    if not engine.connect():
        print("WARNING: venue connection failed - dashboard will show idle state")

    def _loop() -> None:
        async def _runner() -> None:
            engine.state.update(running=True, status_message="Engine running")
            while engine.state.running:
                if not engine.state.paused and not engine.state.kill_switch:
                    try:
                        await engine.trader.cycle()
                    except Exception as exc:  # noqa: BLE001
                        engine.state.update(status_message=f"Cycle error: {exc}")
                try:
                    await asyncio.sleep(max(1, settings.poll_interval_sec))
                except asyncio.CancelledError:
                    break
            engine.state.update(running=False)

        asyncio.run(_runner())

    def _pause(paused: bool) -> None:
        engine.state.update(status_message="Paused by operator" if paused else "Resumed")

    def _close_all() -> dict:
        outcome = engine.orders.close_all_verified()
        engine.basket.reset()
        engine.journal.record_basket("MANUAL_CLOSE", {
            "closed": outcome.closed, "failed": outcome.failed,
            "profit": round(outcome.total_profit, 2),
        })
        return {"requested": outcome.requested, "closed": outcome.closed,
                "failed": outcome.failed, "message": outcome.message}

    def _reset_kill() -> None:
        engine.risk.reset_kill_switch()

    worker = threading.Thread(target=_loop, daemon=True)
    worker.start()
    try:
        from dashboard.app import launch_dashboard

        vm = DashboardViewModel(engine.state, on_pause=_pause,
                                on_close_all=_close_all, on_reset_kill=_reset_kill)
        return launch_dashboard(vm)
    finally:
        engine.state.update(running=False)
        engine.shutdown()


def cmd_backtest(args: argparse.Namespace) -> int:
    """Run a backtest from an M5 CSV file and print the performance report."""
    import pandas as pd

    from backtest.charts import plot_equity_curve
    from backtest.engine import BacktestEngine
    from backtest.validation import monte_carlo
    from core.engine import ZeroTraceEngine, default_spec

    settings = get_settings()
    setup_logging(settings.logs_dir, settings.log_level)
    symbol = args.symbol.upper()
    csv_path = args.csv or os.path.join(settings.data_dir, f"{symbol}_M5.csv")
    if not os.path.exists(csv_path):
        print(f"Data file not found: {csv_path}")
        print("Export M5 history to CSV (time,open,high,low,close) or place it in data/.")
        return 2
    frame = pd.read_csv(csv_path)
    engine = ZeroTraceEngine(settings)
    backtester = BacktestEngine(engine.strategy, settings, default_spec(symbol))
    print(f"Backtesting {symbol} on {len(frame)} M5 bars from {csv_path} ...")
    result = backtester.run(
        symbol, frame, warmup_bars=args.warmup, signal_every=args.every,
        initial_balance=args.balance, spread_pips=args.spread,
    )
    print(f"\n=== Backtest report: {symbol} ===")
    assert result.report is not None
    for line in result.report.summary_lines():
        print(line)
    mc = monte_carlo([t.net for t in result.trades],
                     initial_balance=args.balance, simulations=500)
    print(f"Monte Carlo (500): median {mc.median_final:,.2f} | "
          f"P5 {mc.percentile_5:,.2f} | P95 {mc.percentile_95:,.2f} | "
          f"P(profit) {mc.prob_profit:.1f}%")
    os.makedirs(settings.reports_dir, exist_ok=True)
    chart = os.path.join(settings.reports_dir, f"backtest_{symbol}.png")
    plot_equity_curve(result.equity_curve, chart, title=f"ZeroTrace FX AI - {symbol} Backtest")
    print(f"Equity chart saved: {chart}")
    if result.report.monthly_returns:
        print("Monthly returns (%):")
        for month, pct in sorted(result.report.monthly_returns.items()):
            print(f"  {month}: {pct:+.2f}%")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """CLI argument parser."""
    parser = argparse.ArgumentParser(description=f"{APP_NAME} v{APP_VERSION}")
    sub = parser.add_subparsers(dest="mode")
    sub.add_parser("dashboard", help="Launch the desktop dashboard (default)")
    sub.add_parser("trade", help="Run headless trading (PAPER/LIVE from .env)")
    sub.add_parser("version", help="Print version and exit")
    bt = sub.add_parser("backtest", help="Run a historical backtest from CSV")
    bt.add_argument("--symbol", default="EURUSD", help="Symbol to backtest")
    bt.add_argument("--csv", default="", help="Custom M5 CSV path")
    bt.add_argument("--warmup", type=int, default=300, help="Warmup bars")
    bt.add_argument("--every", type=int, default=3, help="Signal check stride (bars)")
    bt.add_argument("--balance", type=float, default=10000.0, help="Initial balance")
    bt.add_argument("--spread", type=float, default=1.2, help="Spread in pips")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch CLI modes (default: dashboard)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    mode = args.mode or "dashboard"
    if mode == "version":
        return cmd_version()
    if mode == "trade":
        return cmd_trade()
    if mode == "backtest":
        return cmd_backtest(args)
    return cmd_dashboard()


if __name__ == "__main__":
    raise SystemExit(main())
