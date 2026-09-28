"""Backtest charting: PNG equity/drawdown charts plus optional HTML export."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def plot_equity_curve(
    equity_curve: Sequence[tuple[datetime, float]],
    path: str,
    title: str = "ZeroTrace FX AI - Backtest Equity",
) -> str:
    """Render equity + drawdown subplots to PNG; returns the saved path."""
    if not equity_curve:
        raise ValueError("Cannot chart an empty equity curve")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    times = [t for t, _ in equity_curve]
    equities = [float(e) for _, e in equity_curve]
    peak = -float("inf")
    drawdown = []
    for equity in equities:
        peak = max(peak, equity)
        drawdown.append((peak - equity) / peak * 100.0 if peak > 0 else 0.0)
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1]})
    axes[0].plot(times, equities, color="#22c55e", linewidth=1.4)
    axes[0].set_title(title)
    axes[0].set_ylabel("Equity")
    axes[0].grid(alpha=0.25)
    axes[1].fill_between(times, drawdown, color="#ef4444", alpha=0.6)
    axes[1].set_ylabel("DD %")
    axes[1].set_xlabel("Time")
    axes[1].grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    # Optional interactive HTML when plotly is installed (progressive enhancement).
    try:
        import plotly.graph_objects as go  # type: ignore[import]

        html_path = os.path.splitext(path)[0] + ".html"
        fig_html = go.Figure()
        fig_html.add_trace(go.Scatter(x=times, y=equities, mode="lines", name="Equity"))
        fig_html.update_layout(title=title, xaxis_title="Time", yaxis_title="Equity")
        fig_html.write_html(html_path, include_plotlyjs="cdn")
    except Exception:  # noqa: BLE001 - HTML export is best-effort
        pass
    return path
