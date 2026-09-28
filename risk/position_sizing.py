"""Dynamic lot sizing from account risk, stop distance and contract specs."""
from __future__ import annotations

from core.types import SymbolSpec
from utils.common import normalize_lots


def lots_for_risk(
    balance: float,
    risk_percent: float,
    entry: float,
    stop_loss: float,
    spec: SymbolSpec,
) -> float:
    """Lots risking `risk_percent` of balance if price hits the stop-loss."""
    risk_amount = max(0.0, balance) * max(0.0, risk_percent) / 100.0
    return lots_for_amount(risk_amount, entry, stop_loss, spec)


def lots_for_amount(
    risk_amount: float, entry: float, stop_loss: float, spec: SymbolSpec
) -> float:
    """Lots that lose exactly `risk_amount` if the stop-loss is hit."""
    distance = abs(entry - stop_loss)
    if risk_amount <= 0 or distance <= 0:
        return 0.0
    if spec.tick_size <= 0 or spec.tick_value <= 0:
        return 0.0
    ticks_at_risk = distance / spec.tick_size
    loss_per_lot = ticks_at_risk * spec.tick_value
    if loss_per_lot <= 0:
        return 0.0
    raw_lots = risk_amount / loss_per_lot
    return normalize_lots(raw_lots, spec.volume_min, spec.volume_max, spec.volume_step)


def risk_amount_for_lots(
    lots: float, entry: float, stop_loss: float, spec: SymbolSpec
) -> float:
    """Account-currency loss if the stop is hit with the given lots."""
    if spec.tick_size <= 0 or spec.tick_value <= 0:
        return 0.0
    return abs(entry - stop_loss) / spec.tick_size * spec.tick_value * lots
