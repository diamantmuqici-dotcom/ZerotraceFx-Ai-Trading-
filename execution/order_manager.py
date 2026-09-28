"""Order manager: spread/slippage guards, retry with backoff and verification."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from core.types import CloseAllResult, CloseResult, OrderResult, SignalAction
from execution.base import BrokerInterface
from utils.common import pip_size
from utils.logging_setup import get_logger

logger = get_logger("app")
exec_logger = get_logger("execution")


@dataclass
class ExecutionCheck:
    """Pre-execution validation outcome."""

    ok: bool = True
    reasons: list[str] = field(default_factory=list)
    spread_pips: float = 0.0
    price: float = 0.0


class OrderManager:
    """Verified execution wrapper around any broker implementation."""

    def __init__(
        self,
        broker: BrokerInterface,
        max_retries: int = 3,
        retry_delay_sec: float = 0.5,
        verify_delay_sec: float = 0.15,
    ) -> None:
        """Bind the manager to a broker with retry/verify timing."""
        self.broker = broker
        self.max_retries = max(1, max_retries)
        self.retry_delay_sec = retry_delay_sec
        self.verify_delay_sec = verify_delay_sec
        self.last_latency_ms: float = 0.0

    # -- guards ----------------------------------------------------------
    def check_conditions(
        self,
        symbol: str,
        action: SignalAction,
        max_spread_pips: float,
    ) -> ExecutionCheck:
        """Validate live spread/price before an order is attempted."""
        check = ExecutionCheck()
        quote = self.broker.current_price(symbol)
        if quote is None:
            check.ok = False
            check.reasons.append("no price available")
            return check
        bid, ask = quote
        check.price = ask if action is SignalAction.BUY else bid
        check.spread_pips = abs(ask - bid) / pip_size(symbol)
        if check.spread_pips > max_spread_pips:
            check.ok = False
            check.reasons.append(
                f"spread {check.spread_pips:.1f} pips exceeds limit {max_spread_pips:.1f}"
            )
        return check

    # -- verified execution ----------------------------------------------
    def place_market(
        self,
        symbol: str,
        action: SignalAction,
        volume: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "",
        max_spread_pips: float = 999.0,
    ) -> OrderResult:
        """Place a market order with spread guard, retries and verification."""
        check = self.check_conditions(symbol, action, max_spread_pips)
        if not check.ok:
            return OrderResult(False, message="; ".join(check.reasons))
        last: OrderResult = OrderResult(False, message="not attempted")
        for attempt in range(1, self.max_retries + 1):
            last = self.broker.place_market_order(
                symbol, action, volume, stop_loss, take_profit, comment
            )
            last.retries = attempt - 1
            self.last_latency_ms = last.latency_ms
            if last.success and self._verify_open(symbol, last.ticket, action, volume):
                exec_logger.info(
                    "Order verified %s %s %.2f @ %.5f (attempt %d, %.0fms)",
                    symbol, action.value, volume, last.price, attempt, last.latency_ms,
                )
                return last
            if last.success:
                last.success = False
                last.message = f"{last.message}; verification failed".strip("; ")
            exec_logger.warning(
                "Order attempt %d/%d failed for %s: %s",
                attempt, self.max_retries, symbol, last.message,
            )
            time.sleep(self.retry_delay_sec * attempt)
        return last

    def _verify_open(
        self, symbol: str, ticket: str, action: SignalAction, volume: float
    ) -> bool:
        """Confirm the new position exists on the venue."""
        time.sleep(self.verify_delay_sec)
        try:
            positions = self.broker.get_positions(symbol)
        except Exception as exc:  # noqa: BLE001 - verification must not raise
            logger.warning("Verification read failed: %s", exc)
            return False
        if ticket:
            return any(p.ticket == ticket for p in positions)
        return any(
            p.symbol == symbol and p.action is action and abs(p.volume - volume) < 1e-9
            for p in positions
        )

    def close_position_verified(
        self, ticket: str, volume: Optional[float] = None
    ) -> CloseResult:
        """Close (partially) with retries until the venue confirms."""
        last = CloseResult(False, ticket=ticket, message="not attempted")
        for attempt in range(1, self.max_retries + 1):
            last = self.broker.close_position(ticket, volume)
            if last.success:
                return last
            exec_logger.warning(
                "Close attempt %d/%d failed for #%s: %s",
                attempt, self.max_retries, ticket, last.message,
            )
            time.sleep(self.retry_delay_sec * attempt)
        return last

    def close_all_verified(self, symbol: Optional[str] = None) -> CloseAllResult:
        """Close everything; repeat once when the first sweep leaves residue."""
        outcome = self.broker.close_all(symbol)
        remaining = self.broker.get_positions(symbol)
        if remaining:
            exec_logger.warning(
                "%d position(s) survived close-all; retrying sweep", len(remaining)
            )
            time.sleep(self.retry_delay_sec)
            second = self.broker.close_all(symbol)
            outcome.closed += second.closed
            outcome.failed = len(self.broker.get_positions(symbol))
            outcome.total_profit += second.total_profit
            outcome.message = f"closed {outcome.closed}/{outcome.requested} after retry"
        return outcome

    def modify_verified(
        self, ticket: str, stop_loss: float, take_profit: float
    ) -> bool:
        """Modify SL/TP with one retry; returns the venue confirmation."""
        if self.broker.modify_position(ticket, stop_loss, take_profit):
            return True
        time.sleep(self.retry_delay_sec)
        return self.broker.modify_position(ticket, stop_loss, take_profit)
