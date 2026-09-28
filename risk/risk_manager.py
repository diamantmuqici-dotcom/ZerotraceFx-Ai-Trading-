"""Institutional account protection: limits, locks, filters and kill switch."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from config.settings import Settings
from utils.common import utcnow
from utils.logging_setup import get_logger

logger = get_logger("app")


@dataclass
class RiskCheck:
    """Pre-trade risk verdict with human-readable reasons."""

    allowed: bool = True
    reasons: list[str] = field(default_factory=list)

    def block(self, reason: str) -> None:
        """Mark the check as failed with a reason."""
        self.allowed = False
        self.reasons.append(reason)


class RiskManager:
    """Tracks realised PnL/locks and gates every new position."""

    def __init__(self, settings: Settings) -> None:
        """Initialise counters and limits from settings."""
        self.settings = settings
        self._day_key = ""
        self._week_key = ""
        self._day_start_balance = 0.0
        self._week_start_balance = 0.0
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.peak_equity = 0.0
        self.drawdown_pct = 0.0
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.kill_switch = False
        self.kill_reason = ""
        self._initialised = False

    # -- periodic updates -------------------------------------------------
    def on_equity_update(self, equity: float, balance: float,
                         now: datetime | None = None) -> None:
        """Track day/week rollover, peak equity and running drawdown."""
        now = now or utcnow()
        day_key = now.strftime("%Y-%m-%d")
        week_key = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
        if not self._initialised:
            self._initialised = True
            self._day_key, self._week_key = day_key, week_key
            self._day_start_balance = balance
            self._week_start_balance = balance
            self.peak_equity = equity
        if day_key != self._day_key:
            self._day_key = day_key
            self._day_start_balance = balance
            self.daily_pnl = 0.0
        if week_key != self._week_key:
            self._week_key = week_key
            self._week_start_balance = balance
            self.weekly_pnl = 0.0
        if equity > self.peak_equity:
            self.peak_equity = equity
        if self.peak_equity > 0:
            self.drawdown_pct = max(
                0.0, (self.peak_equity - equity) / self.peak_equity * 100.0
            )
        if self.drawdown_pct >= self.settings.max_drawdown_pct:
            self.trigger_kill_switch(
                f"Max drawdown breached ({self.drawdown_pct:.2f}% >= "
                f"{self.settings.max_drawdown_pct:.2f}%)"
            )

    def record_closed_profit(self, profit: float) -> None:
        """Fold a realised result into day/week PnL and streak counters."""
        self.daily_pnl += profit
        self.weekly_pnl += profit
        if profit > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        elif profit < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        else:
            self.consecutive_losses = 0
            self.consecutive_wins = 0
        if self._day_start_balance > 0:
            day_loss_pct = -min(0.0, self.daily_pnl) / self._day_start_balance * 100.0
            if day_loss_pct >= self.settings.max_daily_loss_pct:
                self.trigger_kill_switch(
                    f"Max daily loss breached ({day_loss_pct:.2f}%)"
                )
        if self._week_start_balance > 0:
            week_loss_pct = -min(0.0, self.weekly_pnl) / self._week_start_balance * 100.0
            if week_loss_pct >= self.settings.max_weekly_loss_pct:
                self.trigger_kill_switch(
                    f"Max weekly loss breached ({week_loss_pct:.2f}%)"
                )
        if self.consecutive_losses >= self.settings.max_consecutive_losses:
            self.trigger_kill_switch(
                f"Consecutive loss lock ({self.consecutive_losses} losses)"
            )

    # -- kill switch -------------------------------------------------------
    def trigger_kill_switch(self, reason: str) -> None:
        """Halt all new trading until a manual reset."""
        if not self.kill_switch:
            logger.error("KILL SWITCH ENGAGED: %s", reason)
        self.kill_switch = True
        self.kill_reason = reason

    def reset_kill_switch(self) -> None:
        """Manually clear the kill switch after review."""
        logger.warning("Kill switch manually reset (was: %s)", self.kill_reason)
        self.kill_switch = False
        self.kill_reason = ""
        self.consecutive_losses = 0

    # -- pre-trade gate ----------------------------------------------------
    def pre_trade_check(
        self,
        open_positions: int,
        total_lots: float,
        new_lots: float,
        spread_pips: float,
        latency_ms: float = 0.0,
        news_ok: bool = True,
        session_ok: bool = True,
    ) -> RiskCheck:
        """Gate a candidate order against every configured limit."""
        check = RiskCheck()
        if self.kill_switch:
            check.block(f"Kill switch active: {self.kill_reason}")
            return check
        if open_positions >= self.settings.max_positions:
            check.block(
                f"Max positions reached ({open_positions}/{self.settings.max_positions})"
            )
        if total_lots + new_lots > self.settings.max_total_lots:
            check.block(
                f"Max total lots exceeded "
                f"({total_lots + new_lots:.2f}/{self.settings.max_total_lots:.2f})"
            )
        if new_lots <= 0:
            check.block("Invalid lot size (below broker minimum)")
        if spread_pips > self.settings.spread_limit_pips:
            check.block(
                f"Spread {spread_pips:.1f} pips above limit "
                f"{self.settings.spread_limit_pips:.1f}"
            )
        if latency_ms > self.settings.latency_max_ms:
            check.block(
                f"Execution latency {latency_ms:.0f}ms above limit "
                f"{self.settings.latency_max_ms:.0f}ms"
            )
        if not news_ok:
            check.block("High-impact news blackout")
        if not session_ok:
            check.block("Outside allowed trading sessions")
        if self.consecutive_losses >= self.settings.max_consecutive_losses:
            check.block("Consecutive-loss lock active")
        return check
