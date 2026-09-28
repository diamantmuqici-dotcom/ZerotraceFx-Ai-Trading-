"""Thread-safe runtime state shared by the engine, trader loop and dashboard."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.types import AccountMode, Direction, Position


@dataclass
class RuntimeState:
    """Live snapshot of everything the dashboard and engine need to share."""

    running: bool = False
    ai_trades_learned: int = 0
    paused: bool = False
    mode: str = AccountMode.PAPER.value
    balance: float = 0.0
    equity: float = 0.0
    free_margin: float = 0.0
    margin: float = 0.0
    floating: float = 0.0
    basket_profit: float = 0.0
    basket_target: float = 0.0
    basket_highest: float = 0.0
    trailing_active: bool = False
    win_rate: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    drawdown_pct: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    open_positions: list[Position] = field(default_factory=list)
    last_signal: str = "HOLD"
    last_confidence: float = 0.0
    last_reasoning: list[str] = field(default_factory=list)
    active_symbol: str = ""
    session: str = ""
    equity_curve: list[float] = field(default_factory=list)
    equity_times: list[str] = field(default_factory=list)
    recent_trades: list[dict[str, Any]] = field(default_factory=list)
    status_message: str = "Initialising"
    kill_switch: bool = False
    basket_direction: Direction = Direction.NEUTRAL
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **kwargs: Any) -> None:
        """Atomically update state fields and refresh the timestamp."""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)
            self.updated_at = datetime.now(timezone.utc)

    def append_equity(self, equity: float, when: datetime, max_points: int = 500) -> None:
        """Append an equity point, keeping the curve bounded in memory."""
        with self._lock:
            self.equity_curve.append(float(equity))
            self.equity_times.append(when.strftime("%H:%M:%S"))
            if len(self.equity_curve) > max_points:
                self.equity_curve = self.equity_curve[-max_points:]
                self.equity_times = self.equity_times[-max_points:]

    def push_trade(self, trade: dict[str, Any], max_items: int = 100) -> None:
        """Record a closed trade in the recent-trades ring buffer."""
        with self._lock:
            self.recent_trades.insert(0, trade)
            self.recent_trades = self.recent_trades[:max_items]
            self.total_trades += 1
            if float(trade.get("profit", 0.0)) > 0:
                self.winning_trades += 1
            if self.total_trades > 0:
                self.win_rate = 100.0 * self.winning_trades / self.total_trades

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable copy of the public state fields."""
        with self._lock:
            return {
                "running": self.running,
                "paused": self.paused,
                "mode": self.mode,
                "balance": self.balance,
                "equity": self.equity,
                "free_margin": self.free_margin,
                "margin": self.margin,
                "floating": self.floating,
                "basket_profit": self.basket_profit,
                "basket_target": self.basket_target,
                "basket_highest": self.basket_highest,
                "trailing_active": self.trailing_active,
                "win_rate": self.win_rate,
                "total_trades": self.total_trades,
                "drawdown_pct": self.drawdown_pct,
                "daily_pnl": self.daily_pnl,
                "weekly_pnl": self.weekly_pnl,
                "open_positions": [
                    {
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "action": p.action.value,
                        "volume": p.volume,
                        "entry": p.entry,
                        "current": p.current_price,
                        "sl": p.stop_loss,
                        "tp": p.take_profit,
                        "profit": p.profit,
                        "confidence": p.confidence,
                    }
                    for p in self.open_positions
                ],
                "last_signal": self.last_signal,
                "last_confidence": self.last_confidence,
                "last_reasoning": list(self.last_reasoning),
                "ai_trades_learned": self.ai_trades_learned,
                "active_symbol": self.active_symbol,
                "session": self.session,
                "equity_curve": list(self.equity_curve),
                "equity_times": list(self.equity_times),
                "recent_trades": list(self.recent_trades[:20]),
                "status_message": self.status_message,
                "kill_switch": self.kill_switch,
                "basket_direction": self.basket_direction.value,
                "updated_at": self.updated_at.isoformat(),
            }
