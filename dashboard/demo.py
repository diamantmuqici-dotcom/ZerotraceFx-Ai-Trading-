"""Runnable dashboard preview driven by a simulated market feed.

Useful for UI work and demos on machines without MetaTrader 5:

    python -m dashboard.demo                # live animated preview
    python -m dashboard.demo --screenshot out.png --size 1600x1000

The simulated view-model mirrors :class:`core.state.RuntimeState.snapshot`
exactly, so anything the dashboard renders here renders identically with the
real engine.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.types import Direction, SignalAction

_SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD", "USDJPY"]
_BASE = {"EURUSD": 1.0842, "GBPUSD": 1.2661, "XAUUSD": 2384.5, "USDJPY": 157.32}
_DIGITS = {"EURUSD": 5, "GBPUSD": 5, "XAUUSD": 2, "USDJPY": 3}

_REASONS = [
    "H4 structure bullish — BOS printed above 1.08420 swing high",
    "M15 fair value gap at 1.08310 mitigated and holding as support",
    "D1 premium/discount: price in discount zone (0.38 retracement)",
    "London killzone open — session filter passed",
    "Liquidity sweep of Asian lows confirmed on M5 (equal lows taken)",
    "Order block M15 1.08265-1.08290 unmitigated, entry zone valid",
    "Spread 0.9 pips inside 1.5 pip filter; latency 38 ms",
    "Basket exposure 0.6% of equity, below 1% cap — sizing approved",
    "H1 CHoCH against M15 entry — component scored down (watch)",
    "News blackout: FOMC minutes in 42 min — entries blocked (reject)",
]


class SimulatedFeed:
    """Random-walk market that produces realistic engine snapshots."""

    def __init__(self, seed: int = 7) -> None:
        self.rng = random.Random(seed)
        self.balance = 25_000.0
        self.ticks = 0
        self.equity_curve: list[float] = []
        self.equity_times: list[str] = []
        self.trades: list[dict[str, Any]] = []
        self.reasoning = _REASONS[:8]
        self.signal = SignalAction.BUY.value
        self.confidence = 91.4
        self.paused = False
        self.kill_switch = False
        self.running = True
        self.positions = self._seed_positions()
        start = datetime.now(timezone.utc) - timedelta(minutes=180)
        for i in range(180):
            self.equity_curve.append(self.balance + self._walk(i))
            self.equity_times.append((start + timedelta(minutes=i)).strftime("%H:%M:%S"))
        self._seed_trades(start)

    # -- internals -------------------------------------------------------
    @staticmethod
    def _walk(i: int) -> float:
        return (180.0 * math.sin(i / 22.0) + 34.0 * math.sin(i / 5.5)
                + i * 2.35 + 12.0 * math.cos(i / 3.1))

    def _seed_positions(self) -> list[dict[str, Any]]:
        rows = [
            ("EURUSD", "BUY", 0.40, 12.4),
            ("GBPUSD", "BUY", 0.25, -4.1),
            ("XAUUSD", "SELL", 0.10, 31.8),
            ("USDJPY", "BUY", 0.30, 6.2),
        ]
        out = []
        for ticket, (symbol, action, volume, profit) in enumerate(rows, start=4821103):
            base = _BASE[symbol]
            digits = _DIGITS[symbol]
            entry = base * (1 - 0.0008)
            current = entry + profit / (volume * 100_000) if digits == 5 else entry + profit / volume
            sl, tp = entry - base * 0.0022, entry + base * 0.0046
            out.append({
                "ticket": ticket, "symbol": symbol, "action": action,
                "volume": volume, "entry": round(entry, digits),
                "current": round(current, digits), "sl": round(sl, digits),
                "tp": round(tp, digits), "profit": round(profit, 2),
                "confidence": self.rng.uniform(86.0, 96.0),
            })
        return out

    def _seed_trades(self, start: datetime) -> None:
        actions = ["BUY", "SELL"]
        for i in range(14):
            profit = self.rng.choice([1, 1, 1, -1]) * self.rng.uniform(6, 84)
            self.trades.append({
                "time": (start + timedelta(minutes=i * 11)).strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": self.rng.choice(_SYMBOLS),
                "action": f"{self.rng.choice(actions)} → CLOSE",
                "profit": round(profit, 2),
                "reason": self.rng.choice(_REASONS),
            })
        self.trades.reverse()

    # -- public api (mirrors DashboardViewModel) --------------------------
    def tick(self) -> None:
        self.ticks += 1
        drift = self.rng.uniform(-14.0, 15.0)
        for pos in self.positions:
            pos["profit"] = round(pos["profit"] + self.rng.uniform(-3.0, 3.2), 2)
            step = self.rng.uniform(-0.4, 0.4) / 1000
            pos["current"] = round(pos["current"] * (1 + step), _DIGITS[pos["symbol"]])
        floating = sum(p["profit"] for p in self.positions)
        self.equity_curve.append(self.equity_curve[-1] + drift)
        self.equity_curve = self.equity_curve[-500:]
        self.equity_times.append(datetime.now(timezone.utc).strftime("%H:%M:%S"))
        self.equity_times = self.equity_times[-500:]
        if self.ticks % 9 == 0:
            self.signal = self.rng.choice(
                [SignalAction.BUY.value, SignalAction.SELL.value, SignalAction.HOLD.value])
            self.confidence = self.rng.uniform(58.0, 97.0)
            self.reasoning = self.rng.sample(_REASONS, 7)
        self._floating = floating

    def snapshot(self) -> dict[str, Any]:
        floating = getattr(self, "_floating", sum(p["profit"] for p in self.positions))
        wins = sum(1 for t in self.trades if t["profit"] > 0)
        total = len(self.trades) or 1
        curve = self.equity_curve
        peak = max(curve) if curve else 1.0
        dd = max(0.0, (peak - curve[-1]) / peak * 100.0) if curve else 0.0
        return {
            "running": self.running,
            "paused": self.paused,
            "mode": "PAPER",
            "balance": self.balance,
            "equity": round(self.balance + floating, 2),
            "free_margin": round(self.balance * 0.94 + floating, 2),
            "margin": round(self.balance * 0.06, 2),
            "floating": round(floating, 2),
            "basket_profit": round(floating, 2),
            "basket_target": 250.0,
            "basket_highest": round(max(floating, 96.4), 2),
            "trailing_active": floating > 120.0,
            "win_rate": round(100.0 * wins / total, 1),
            "total_trades": len(self.trades),
            "drawdown_pct": round(dd, 2),
            "daily_pnl": round(floating + 318.6, 2),
            "weekly_pnl": round(floating + 1204.9, 2),
            "open_positions": [dict(p) for p in self.positions],
            "last_signal": self.signal,
            "last_confidence": round(self.confidence, 1),
            "last_reasoning": list(self.reasoning),
            "ai_trades_learned": 148,
            "active_symbol": "EURUSD",
            "session": "London",
            "equity_curve": list(curve),
            "equity_times": list(self.equity_times),
            "recent_trades": [dict(t) for t in self.trades],
            "status_message": "Engine running — scanning 4 symbols",
            "kill_switch": self.kill_switch,
            "basket_direction": Direction.BULLISH.value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    def close_all(self) -> dict[str, Any]:
        closed = len(self.positions)
        self.positions = []
        return {"requested": closed, "closed": closed,
                "message": f"{closed} positions closed at market"}

    def reset_kill_switch(self) -> None:
        self.kill_switch = False

    def diagnostics(self) -> str:
        """Canned gate report so the Diagnostics tab is populated in previews."""
        from core.diagnostics import OK, WARN, Check, render

        snap = self.snapshot()
        conf = snap["last_confidence"]
        checks = [
            Check("mode", WARN,
                  "preview feed - simulated market, no venue attached "
                  "(run `python main.py doctor` against the real engine)"),
            Check("mt5", OK, "n/a in preview"),
            Check(snap.get("active_symbol") or "EURUSD",
                  OK if conf >= 85 else WARN,
                  f"confidence {conf:.1f} of 85 required - last signal "
                  f"{snap['last_signal']}"),
            Check("risk", OK,
                  f"drawdown {snap['drawdown_pct']:.2f}%, no locks, "
                  f"{len(snap['open_positions'])} open positions"),
        ]
        return render(checks)


def run_demo(viewmodel: Optional[SimulatedFeed] = None, refresh_ms: int = 700,
             screenshot: str = "", size: tuple[int, int] = (1600, 1000),
             tab: int = 0) -> int:
    """Run the dashboard against the simulated feed (or grab a screenshot)."""
    if screenshot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from dashboard.app import _require_qt, create_application

    QtCore, _QtGui, _QtWidgets, _canvas = _require_qt()
    feed = viewmodel or SimulatedFeed()
    app, window = create_application(feed, refresh_ms=refresh_ms)
    window.resize(*size)
    if tab:
        window.tabs.setCurrentIndex(tab)
    window.show()

    if screenshot:
        for _ in range(3):
            feed.tick()
            window.refresh()
        thread = getattr(window, "_diag_thread", None)
        if thread is not None:  # let a pending diagnostics run land in the shot
            thread.wait(3000)
        app.processEvents()
        app.processEvents()
        window.grab().save(screenshot)
        print(f"saved {screenshot}")
        return 0

    ticker = QtCore.QTimer(window)
    ticker.timeout.connect(lambda: (feed.tick(), window.refresh()))
    ticker.start(refresh_ms)
    return int(app.exec())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ZeroTrace dashboard preview")
    parser.add_argument("--screenshot", default="", help="Render once and save PNG")
    parser.add_argument("--size", default="1600x1000", help="Window size WxH")
    parser.add_argument("--tab", type=int, default=0, help="Tab index to capture")
    parser.add_argument("--refresh", type=int, default=700, help="Refresh ms")
    parser.add_argument("--seed", type=int, default=7, help="Random seed")
    args = parser.parse_args(argv)
    width, _, height = args.size.partition("x")
    size = (int(width), int(height or 1000))
    return run_demo(SimulatedFeed(seed=args.seed), refresh_ms=args.refresh,
                    screenshot=args.screenshot, size=size, tab=args.tab)


if __name__ == "__main__":
    sys.exit(main())
