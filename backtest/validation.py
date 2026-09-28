"""Statistical validation: Monte Carlo resampling and walk-forward analysis."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np
import pandas as pd


@dataclass
class MonteCarloResult:
    """Distribution of simulated equity outcomes from resampled trades."""

    simulations: int = 0
    median_final: float = 0.0
    mean_final: float = 0.0
    percentile_5: float = 0.0
    percentile_95: float = 0.0
    prob_profit: float = 0.0
    median_max_drawdown: float = 0.0
    worst_drawdown: float = 0.0


def monte_carlo(
    trade_nets: Sequence[float],
    initial_balance: float = 10000.0,
    simulations: int = 1000,
    seed: int = 42,
) -> MonteCarloResult:
    """Resample trades with replacement to estimate outcome distributions."""
    result = MonteCarloResult(simulations=simulations)
    if not trade_nets or simulations <= 0:
        return result
    rng = random.Random(seed)
    nets = list(trade_nets)
    finals: list[float] = []
    drawdowns: list[float] = []
    for _ in range(simulations):
        equity = initial_balance
        peak = equity
        max_dd = 0.0
        order = [rng.choice(nets) for _ in range(len(nets))]
        for net in order:
            equity += net
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        finals.append(equity)
        drawdowns.append(max_dd)
    arr = np.array(finals, dtype=float)
    result.median_final = round(float(np.median(arr)), 2)
    result.mean_final = round(float(arr.mean()), 2)
    result.percentile_5 = round(float(np.percentile(arr, 5)), 2)
    result.percentile_95 = round(float(np.percentile(arr, 95)), 2)
    result.prob_profit = round(float((arr > initial_balance).mean() * 100.0), 1)
    result.median_max_drawdown = round(float(np.median(drawdowns)), 2)
    result.worst_drawdown = round(float(np.max(drawdowns)), 2)
    return result


@dataclass
class WalkForwardWindow:
    """One train/test window outcome."""

    index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_params: dict[str, object] = field(default_factory=dict)
    train_net: float = 0.0
    test_net: float = 0.0


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward optimisation outcome."""

    windows: list[WalkForwardWindow] = field(default_factory=list)
    total_test_net: float = 0.0
    efficient: bool = False

    def summary_lines(self) -> list[str]:
        """Human-readable lines per window plus the aggregate verdict."""
        lines = [
            f"W{i.index}: train {w.train_net:+.2f} -> test {w.test_net:+.2f} "
            f"params={w.best_params}"
            for i, w in zip(range(len(self.windows)), self.windows)
        ]
        lines.append(
            f"Total out-of-sample: {self.total_test_net:+.2f} "
            f"({'EFFICIENT' if self.efficient else 'NOT EFFICIENT'})"
        )
        return lines


def walk_forward(
    data: pd.DataFrame,
    run_segment: Callable[[pd.DataFrame, dict[str, object]], float],
    param_grid: list[dict[str, object]],
    n_windows: int = 4,
    train_ratio: float = 0.7,
) -> WalkForwardResult:
    """Anchored walk-forward: pick best params in-sample, test out-of-sample.

    `run_segment` receives a data slice and a parameter dict and must return
    the segment net profit. The strategy is deemed efficient when aggregate
    out-of-sample profit is positive.
    """
    result = WalkForwardResult()
    if data is None or data.empty or not param_grid or n_windows <= 0:
        return result
    n = len(data)
    fold = n // (n_windows + 1)
    if fold < 20:
        return result
    for w in range(n_windows):
        train_end = fold * (w + 1)
        test_end = min(n, fold * (w + 2))
        train = data.iloc[:train_end]
        test = data.iloc[train_end:test_end]
        best: Optional[dict[str, object]] = None
        best_train = -float("inf")
        for params in param_grid:
            net = run_segment(train, params)
            if net > best_train:
                best_train = net
                best = params
        test_net = run_segment(test, best or {}) if best is not None else 0.0
        window = WalkForwardWindow(
            index=w,
            train_start=str(train["time"].iloc[0]) if "time" in train else "",
            train_end=str(train["time"].iloc[-1]) if "time" in train else "",
            test_start=str(test["time"].iloc[0]) if "time" in test else "",
            test_end=str(test["time"].iloc[-1]) if "time" in test else "",
            best_params=dict(best or {}),
            train_net=round(best_train, 2),
            test_net=round(test_net, 2),
        )
        result.windows.append(window)
    result.total_test_net = round(sum(w.test_net for w in result.windows), 2)
    result.efficient = result.total_test_net > 0
    return result
