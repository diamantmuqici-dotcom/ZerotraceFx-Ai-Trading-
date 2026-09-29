"""ZeroTrace FX AI production entry point.

The released application has one operating mode: authenticated real-money MT5
trading. It never asks for MT5 credentials and never falls back to paper,
demo, backtest, synthetic-feed, or simulated-order execution. If the official
terminal API cannot confirm a real account, the UI remains in the explicit
``Waiting for authenticated MT5 session...`` state.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.constants import APP_NAME, APP_VERSION  # noqa: E402
from config.settings import get_settings  # noqa: E402
from utils.logging_setup import setup_logging  # noqa: E402


def _production_engine():
    """Construct the real-only engine without importing research adapters."""
    from core.engine import ZeroTraceEngine

    return ZeroTraceEngine(get_settings(), allow_research=False)


def cmd_version() -> int:
    """Print version and runtime policy."""
    print(f"{APP_NAME} v{APP_VERSION}")
    print("Authenticated real MT5 execution only")
    print(f"Python {sys.version.split()[0]} on {sys.platform}")
    return 0


def _run_engine(engine) -> None:
    """Run the real trader loop in a worker thread for the desktop shell."""
    async def runner() -> None:
        engine.state.update(running=True, status_message="Engine running")
        while engine.state.running:
            if not engine.state.paused and not engine.state.kill_switch:
                try:
                    await engine.trader.cycle()
                except Exception as exc:  # noqa: BLE001
                    engine.state.update(status_message=f"Cycle error: {exc}")
            await asyncio.sleep(max(1, engine.settings.poll_interval_sec))
        engine.state.update(running=False)

    asyncio.run(runner())


def cmd_trade() -> int:
    """Run the headless real-money loop."""
    engine = _production_engine()
    setup_logging(engine.settings.logs_dir, engine.settings.log_level)
    print(f"{APP_NAME} v{APP_VERSION} - authenticated real MT5 execution")
    print(f"Symbols: {', '.join(engine.settings.symbol_list)} | "
          f"Basket target: ${engine.settings.basket_target:,.2f} | "
          f"Confidence: {engine.settings.confidence_threshold:.0f}")
    engine.connect()
    if engine.start_remote_api():
        print(f"Remote API on port {engine.settings.remote_api_port}")
    try:
        asyncio.run(engine.trader.run_forever())
    except KeyboardInterrupt:
        print("\nShutdown requested - stopping...")
    finally:
        engine.shutdown()
    return 0


def cmd_dashboard() -> int:
    """Run the real engine behind the native desktop dashboard."""
    from dashboard.viewmodel import DashboardViewModel
    from dashboard.app import launch_dashboard

    engine = _production_engine()
    setup_logging(engine.settings.logs_dir, engine.settings.log_level)
    engine.connect()

    worker = threading.Thread(target=_run_engine, args=(engine,), daemon=True,
                              name="zerotrace-engine")
    worker.start()
    engine.start_remote_api()

    def pause(paused: bool) -> None:
        engine.state.update(status_message="Paused by operator" if paused else "Resumed")

    def diagnostics() -> str:
        from core.diagnostics import collect, render
        return render(asyncio.run(collect(engine)))

    vm = DashboardViewModel(
        engine.state,
        on_pause=pause,
        on_close_all=engine.manual_close_all,
        on_reset_kill=engine.risk.reset_kill_switch,
        on_diagnostics=diagnostics,
    )
    try:
        return launch_dashboard(vm)
    finally:
        engine.state.update(running=False)
        worker.join(timeout=3)
        engine.shutdown()


def cmd_doctor() -> int:
    """Print authenticated-session and risk-gate diagnostics."""
    from core.diagnostics import collect, render

    engine = _production_engine()
    engine.connect()
    try:
        print(render(asyncio.run(collect(engine))))
    finally:
        engine.shutdown()
    return 0


def cmd_api() -> int:
    """Run the local/remote real-engine API for Electron or Android."""
    engine = _production_engine()
    engine.connect()
    if not engine.start_remote_api():
        print("Remote API disabled or REMOTE_API_TOKEN is missing (16+ characters).")
        engine.shutdown()
        return 2
    worker = threading.Thread(target=_run_engine, args=(engine,), daemon=True,
                              name="zerotrace-engine")
    worker.start()
    print(f"ZeroTrace API listening on {engine.settings.remote_api_host}:"
          f"{engine.settings.remote_api_port}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    finally:
        engine.state.update(running=False)
        worker.join(timeout=3)
        engine.shutdown()


def build_parser() -> argparse.ArgumentParser:
    """Build the intentionally small production CLI."""
    parser = argparse.ArgumentParser(description=f"{APP_NAME} v{APP_VERSION}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("dashboard", help="Launch the real-mode desktop dashboard")
    sub.add_parser("trade", help="Run authenticated real MT5 trading headlessly")
    sub.add_parser("doctor", help="Diagnose the MT5 session and trading gates")
    sub.add_parser("api", help="Run the authenticated API for the desktop/mobile shell")
    sub.add_parser("ai", help="Show persistent learning statistics from real trades")
    sub.add_parser("version", help="Print version and execution policy")
    return parser


def cmd_ai() -> int:
    """Print learning statistics without touching a venue."""
    import json
    from strategy.learning import AdaptiveLearner

    settings = get_settings()
    path = os.path.join(settings.logs_dir, settings.learning_memory_file)
    print(json.dumps(AdaptiveLearner(path).summary(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch production commands."""
    args = build_parser().parse_args(argv)
    command = args.command or "dashboard"
    if command == "version":
        return cmd_version()
    if command == "trade":
        return cmd_trade()
    if command == "doctor":
        return cmd_doctor()
    if command == "api":
        return cmd_api()
    if command == "ai":
        return cmd_ai()
    return cmd_dashboard()


if __name__ == "__main__":
    raise SystemExit(main())
