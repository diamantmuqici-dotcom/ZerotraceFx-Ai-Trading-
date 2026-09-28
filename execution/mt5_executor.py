"""Live MetaTrader 5 executor implementing the broker interface."""
from __future__ import annotations

import time
from typing import Optional

from core.types import (
    AccountInfo,
    CloseAllResult,
    CloseResult,
    OrderResult,
    Position,
    SignalAction,
    SymbolSpec,
)
from execution.base import BrokerInterface
from market.mt5_client import HAS_MT5, MT5Client
from utils.common import ms_now, normalize_lots
from utils.logging_setup import get_logger, log_trade_event

logger = get_logger("app")
exec_logger = get_logger("execution")


class MT5Executor(BrokerInterface):
    """Real-money execution through the MT5 terminal API."""

    name = "mt5-live"

    def __init__(
        self,
        client: MT5Client,
        magic: int = 240901,
        deviation_points: int = 20,
    ) -> None:
        """Bind the executor to a terminal client."""
        self.client = client
        self.magic = magic
        self.deviation_points = deviation_points
        self._filling_mode: Optional[int] = None

    # -- connection ------------------------------------------------------
    def connect(self) -> bool:
        """Connect the underlying terminal client."""
        return self.client.connect()

    def is_connected(self) -> bool:
        """True when the terminal is connected."""
        return self.client.is_connected()

    def shutdown(self) -> None:
        """Shut the terminal client down."""
        self.client.shutdown()

    def account_info(self) -> Optional[AccountInfo]:
        """Live account snapshot."""
        return self.client.account_info()

    def symbol_spec(self, symbol: str) -> Optional[SymbolSpec]:
        """Live contract specification from the broker."""
        raw = self.client.symbol_spec(symbol)
        if raw is None:
            return None
        return SymbolSpec(symbol=symbol, **raw)

    def current_price(self, symbol: str) -> Optional[tuple[float, float]]:
        """Live (bid, ask)."""
        tick = self.client.current_tick(symbol)
        if tick is None:
            return None
        return (tick.bid, tick.ask)

    def get_positions(self, symbol: Optional[str] = None) -> list[Position]:
        """Live open positions."""
        return self.client.open_positions(symbol)

    # -- orders ------------------------------------------------------------
    def _detect_filling_mode(self, symbol: str) -> int:
        """Detect a working filling mode once per session (cached)."""
        if self._filling_mode is not None or not HAS_MT5:
            return self._filling_mode or 0
        import MetaTrader5 as mt5  # local: only exists on Windows

        for mode in (
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_RETURN,
        ):
            tick = self.client.current_tick(symbol)
            if tick is None:
                continue
            probe = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": 0.01,
                "type": mt5.ORDER_TYPE_BUY,
                "price": tick.ask,
                "deviation": self.deviation_points,
                "magic": self.magic,
                "comment": "zerotrace-probe",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mode,
            }
            check = None
            try:
                check = mt5.order_check(probe)
            except Exception:  # noqa: BLE001
                check = None
            if check is not None and check.retcode == 0:
                self._filling_mode = mode
                return mode
        self._filling_mode = 1  # ORDER_FILLING_FOK fallback value
        return self._filling_mode

    def place_market_order(
        self,
        symbol: str,
        action: SignalAction,
        volume: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "",
    ) -> OrderResult:
        """Open a live market position; verified before returning."""
        started = ms_now()
        if not HAS_MT5:
            return OrderResult(False, message="MetaTrader5 unavailable")
        import MetaTrader5 as mt5

        if not self.client.ensure_symbol(symbol):
            return OrderResult(False, message=f"Symbol unavailable: {symbol}")
        tick = self.client.current_tick(symbol)
        if tick is None:
            return OrderResult(False, message="No tick available")
        spec = self.symbol_spec(symbol)
        lots = normalize_lots(
            volume,
            spec.volume_min if spec else 0.01,
            spec.volume_max if spec else 100.0,
            spec.volume_step if spec else 0.01,
        )
        if lots <= 0:
            return OrderResult(False, message="Volume below broker minimum")
        price = tick.ask if action is SignalAction.BUY else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if action is SignalAction.BUY else mt5.ORDER_TYPE_SELL
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lots,
            "type": order_type,
            "price": price,
            "sl": float(stop_loss),
            "tp": float(take_profit),
            "deviation": self.deviation_points,
            "magic": self.magic,
            "comment": (comment or "zerotrace")[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._detect_filling_mode(symbol),
        }
        result = self.client.raw_order_send(request)
        latency = ms_now() - started
        if result is None:
            exec_logger.error("order_send returned None for %s", symbol)
            return OrderResult(False, message="order_send failed", latency_ms=latency)
        ok = result.retcode == mt5.TRADE_RETCODE_DONE
        message = f"retcode={result.retcode} deal={result.deal} {result.comment}"
        if ok:
            log_trade_event(
                exec_logger, event="ORDER_OK", symbol=symbol,
                action=action.value, volume=lots, price=result.price,
                ticket=result.order, latency_ms=round(latency, 1),
            )
            return OrderResult(True, ticket=str(result.order), price=float(result.price),
                               volume=lots, message=message, latency_ms=latency)
        exec_logger.error("Order rejected %s: %s", symbol, message)
        return OrderResult(False, message=message, latency_ms=latency)

    def place_pending_order(
        self,
        symbol: str,
        action: SignalAction,
        volume: float,
        price: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "",
    ) -> OrderResult:
        """Place a live pending stop/limit order."""
        started = ms_now()
        if not HAS_MT5:
            return OrderResult(False, message="MetaTrader5 unavailable")
        import MetaTrader5 as mt5

        tick = self.client.current_tick(symbol)
        if tick is None:
            return OrderResult(False, message="No tick available")
        if action is SignalAction.BUY:
            order_type = mt5.ORDER_TYPE_BUY_STOP if price > tick.ask else mt5.ORDER_TYPE_BUY_LIMIT
        else:
            order_type = mt5.ORDER_TYPE_SELL_STOP if price < tick.bid else mt5.ORDER_TYPE_SELL_LIMIT
        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": float(price),
            "sl": float(stop_loss),
            "tp": float(take_profit),
            "deviation": self.deviation_points,
            "magic": self.magic,
            "comment": (comment or "zerotrace-pending")[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._detect_filling_mode(symbol),
        }
        result = self.client.raw_order_send(request)
        latency = ms_now() - started
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            message = "pending failed" if result is None else f"retcode={result.retcode}"
            return OrderResult(False, message=message, latency_ms=latency)
        return OrderResult(True, ticket=str(result.order), price=float(price),
                           volume=float(volume), message="pending placed", latency_ms=latency)

    def modify_position(self, ticket: str, stop_loss: float, take_profit: float) -> bool:
        """Modify SL/TP of a live position."""
        if not HAS_MT5:
            return False
        import MetaTrader5 as mt5

        target = next(
            (p for p in self.get_positions() if p.ticket == str(ticket)), None
        )
        if target is None:
            return False
        tick = self.client.current_tick(target.symbol)
        if tick is None:
            return False
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": target.symbol,
            "position": int(ticket) if str(ticket).isdigit() else ticket,
            "sl": float(stop_loss),
            "tp": float(take_profit),
        }
        result = self.client.raw_order_send(request)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        if not ok:
            exec_logger.warning("Modify failed for #%s", ticket)
        return ok

    def close_position(self, ticket: str, volume: Optional[float] = None) -> CloseResult:
        """Close a live position fully or partially via an opposite deal."""
        started = ms_now()
        if not HAS_MT5:
            return CloseResult(False, ticket=str(ticket), message="MT5 unavailable")
        import MetaTrader5 as mt5

        target = next(
            (p for p in self.get_positions() if p.ticket == str(ticket)), None
        )
        if target is None:
            return CloseResult(False, ticket=str(ticket), message="Position not found")
        tick = self.client.current_tick(target.symbol)
        if tick is None:
            return CloseResult(False, ticket=str(ticket), message="No tick")
        lots = target.volume if volume is None else min(float(volume), target.volume)
        if lots <= 0:
            return CloseResult(False, ticket=str(ticket), message="Invalid volume")
        opposite = mt5.ORDER_TYPE_SELL if target.action is SignalAction.BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if target.action is SignalAction.BUY else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": target.symbol,
            "volume": lots,
            "type": opposite,
            "position": int(ticket) if str(ticket).isdigit() else ticket,
            "price": price,
            "deviation": self.deviation_points,
            "magic": self.magic,
            "comment": "zerotrace-close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._detect_filling_mode(target.symbol),
        }
        result = self.client.raw_order_send(request)
        latency = ms_now() - started
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            message = "close failed" if result is None else f"retcode={result.retcode}"
            return CloseResult(False, ticket=str(ticket), message=message, latency_ms=latency)
        time.sleep(0.05)  # allow terminal profit settlement before reading back
        profit = target.profit  # best available without deal-history scan
        log_trade_event(
            exec_logger, event="CLOSE_OK", symbol=target.symbol, ticket=ticket,
            volume=lots, price=result.price, latency_ms=round(latency, 1),
        )
        return CloseResult(True, ticket=str(ticket), price=float(result.price),
                           profit=profit, message="closed", latency_ms=latency)

    def close_all(self, symbol: Optional[str] = None) -> CloseAllResult:
        """Close every live position and cancel pending orders immediately."""
        outcome = CloseAllResult()
        positions = self.get_positions(symbol)
        outcome.requested = len(positions)
        for position in positions:
            result = self.close_position(position.ticket)
            if result.success:
                outcome.closed += 1
                outcome.total_profit += result.profit
            else:
                outcome.failed += 1
        if HAS_MT5:
            import MetaTrader5 as mt5

            for pending in self.client.pending_orders(symbol):
                try:
                    self.client.raw_order_send({
                        "action": mt5.TRADE_ACTION_REMOVE,
                        "order": pending.ticket,
                    })
                except Exception:  # noqa: BLE001 - best effort cancel
                    outcome.failed += 1
        outcome.message = f"closed {outcome.closed}/{outcome.requested}"
        return outcome
