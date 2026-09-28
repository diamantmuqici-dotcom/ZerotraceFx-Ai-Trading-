"""Performance statistics: win rate, profit factor, Sharpe, drawdown, returns."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover - typing only
    from backtest.engine import BacktestTrade


@dataclass
class BacktestReport:
    """Complete statistical summary of a backtest run."""

    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    loss_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    total_return_pct: float = 0.0
    monthly_returns: dict[str, float] = field(default_factory=dict)
    yearly_returns: dict[str, float] = field(default_factory=dict)

    def summary_lines(self) -> list[str]:
        """Human-readable report lines for CLI output."""
        return [
            f"Trades: {self.trades} | Wins: {self.wins} | Losses: {self.losses}",
            f"Win rate: {self.win_rate:.1f}% | Loss rate: {self.loss_rate:.1f}%",
            f"Net profit: {self.net_profit:+.2f} | Profit factor: {self.profit_factor:.2f}",
            f"Expectancy: {self.expectancy:+.2f} per trade",
            f"Avg win: {self.avg_win:+.2f} | Avg loss: {self.avg_loss:+.2f}",
            f"Best: {self.best_trade:+.2f} | Worst: {self.worst_trade:+.2f}",
            f"Max drawdown: {self.max_drawdown:.2f} ({self.max_drawdown_pct:.2f}%)",
            f"Sharpe: {self.sharpe_ratio:.2f} | Sortino: {self.sortino_ratio:.2f}",
            f"Total return: {self.total_return_pct:+.2f}%",
        ]


def compute_report(
    trades: list["BacktestTrade"],
    equity_curve: list[tuple[datetime, float]],
    balance0: float = 10000.0,
    periods_per_year: int = 252,
) -> BacktestReport:
    """Compute the full statistical report from trades and the equity curve."""
    report = BacktestReport()
    if not trades:
        if equity_curve:
            report.max_drawdown, report.max_drawdown_pct = _drawdown(
                [e for _, e in equity_curve]
            )
        return report
    nets = np.array([t.net for t in trades], dtype=float)
    report.trades = len(nets)
    wins = nets[nets > 0]
    losses = nets[nets <= 0]
    report.wins = int(len(wins))
    report.losses = int(len(losses))
    report.win_rate = round(report.wins / report.trades * 100.0, 2)
    report.loss_rate = round(100.0 - report.win_rate, 2)
    report.gross_profit = round(float(wins.sum()), 2)
    report.gross_loss = round(float(losses.sum()), 2)
    report.net_profit = round(float(nets.sum()), 2)
    report.profit_factor = (
        round(abs(report.gross_profit / report.gross_loss), 3)
        if report.gross_loss < 0 else float("inf") if report.gross_profit > 0 else 0.0
    )
    report.expectancy = round(float(nets.mean()), 2)
    report.avg_win = round(float(wins.mean()), 2) if len(wins) else 0.0
    report.avg_loss = round(float(losses.mean()), 2) if len(losses) else 0.0
    report.best_trade = round(float(nets.max()), 2)
    report.worst_trade = round(float(nets.min()), 2)
    if equity_curve:
        equities = [e for _, e in equity_curve]
        report.max_drawdown, report.max_drawdown_pct = _drawdown(equities)
        report.sharpe_ratio, report.sortino_ratio = _risk_adjusted(
            equities, periods_per_year
        )
        report.monthly_returns = _period_returns(equity_curve, "M")
        report.yearly_returns = _period_returns(equity_curve, "Y")
    if balance0 > 0:
        report.total_return_pct = round(report.net_profit / balance0 * 100.0, 2)
    return report


def _drawdown(equities: list[float]) -> tuple[float, float]:
    """Max drawdown in currency and percent."""
    peak = -float("inf")
    max_dd = 0.0
    max_dd_pct = 0.0
    for equity in equities:
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
        if peak > 0:
            max_dd_pct = max(max_dd_pct, dd / peak * 100.0)
    return round(max_dd, 2), round(max_dd_pct, 2)


def _risk_adjusted(equities: list[float], periods_per_year: int) -> tuple[float, float]:
    """Annualised Sharpe and Sortino ratios from equity returns."""
    series = pd.Series(equities, dtype=float)
    returns = series.pct_change().dropna()
    if len(returns) < 2 or returns.std() == 0:
        return 0.0, 0.0
    sharpe = float(returns.mean() / returns.std() * np.sqrt(periods_per_year))
    downside = returns[returns < 0]
    if len(downside) < 2 or downside.std() == 0:
        sortino = 0.0
    else:
        sortino = float(returns.mean() / downside.std() * np.sqrt(periods_per_year))
    return round(sharpe, 3), round(sortino, 3)


def _period_returns(
    equity_curve: list[tuple[datetime, float]], freq: str
) -> dict[str, float]:
    """Calendar-period returns keyed by period label (percent)."""
    frame = pd.DataFrame(equity_curve, columns=["time", "equity"])
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.set_index("time").sort_index()
    if freq == "M":
        grouped = frame["equity"].resample("ME")
    else:
        grouped = frame["equity"].resample("YE")
    out: dict[str, float] = {}
    for period_end, group in grouped:
        if len(group) < 1:
            continue
        start, end = float(group.iloc[0]), float(group.iloc[-1])
        if start > 0:
            label = period_end.strftime("%Y-%m" if freq == "M" else "%Y")
            out[label] = round((end - start) / start * 100.0, 2)
    return out
