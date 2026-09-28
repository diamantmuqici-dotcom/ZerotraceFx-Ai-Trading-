"""MetaTrader 5 terminal wrapper with graceful degradation outside Windows.

On machines without the MetaTrader5 package (Linux CI, dev boxes) every method
returns a safe empty value instead of raising, so paper trading, backtesting
and the test-suite keep working. Live trading requires a real connection.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from core.types import AccountInfo, Position, SignalAction, TickData
from utils.logging_setup import get_logger

try:  # pragma: no cover - MetaTrader5 exists only on Windows
    import MetaTrader5 as mt5

    HAS_MT5 = True
except Exception:  # noqa: BLE001 - absence is an expected state
    mt5 = None  # type: ignore[assignment]
    HAS_MT5 = False

logger = get_logger("app")

_TIMEFRAME_ATTR = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}


def mt5_timeframe(timeframe: str) -> Any:
    """Map a timeframe code to the MetaTrader5 constant (None if missing)."""
    if not HAS_MT5 or mt5 is None:
        return None
    attr = _TIMEFRAME_ATTR.get(timeframe.upper())
    return getattr(mt5, attr, None) if attr else None


class MT5Client:
    """Thin resilient wrapper around the MetaTrader5 Python API."""

    def __init__(
        self,
        login: int = 0,
        password: str = "",
        server: str = "",
        path: str = "",
        timeout_ms: int = 60_000,
    ) -> None:
        """Store credentials; no connection is made until connect() is called."""
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.timeout_ms = timeout_ms
        self._connected = False

    # -- lifecycle ------------------------------------------------------
    @property
    def available(self) -> bool:
        """True when the MetaTrader5 package is importable."""
        return HAS_MT5

    def connect(self) -> bool:
        """Initialise the terminal and log in; returns True on success."""
        if not HAS_MT5 or mt5 is None:
            logger.warning("MetaTrader5 package unavailable - running without live MT5")
            return False
        try:
            kwargs: dict[str, Any] = {"timeout": self.timeout_ms}
            if self.path:
                kwargs["path"] = self.path
            if not mt5.initialize(**kwargs):
                logger.error("mt5.initialize failed: %s", mt5.last_error())
                return False
            if self.login and self.server:
                if not mt5.login(self.login, password=self.password, server=self.server):
                    logger.error("mt5.login failed: %s", mt5.last_error())
                    mt5.shutdown()
                    return False
            self._connected = True
            logger.info("Connected to MetaTrader 5")
            return True
        except Exception as exc:  # noqa: BLE001 - terminal errors must not crash
            logger.error("MT5 connect error: %s", exc)
            return False

    def reconnect(self, attempts: int = 3, delay_sec: float = 2.0) -> bool:
        """Try to re-establish a dropped terminal connection."""
        self.shutdown()
        for attempt in range(1, attempts + 1):
            if self.connect():
                return True
            logger.warning("MT5 reconnect attempt %d/%d failed", attempt, attempts)
            time.sleep(delay_sec)
        return False

    def is_connected(self) -> bool:
        """True when the terminal reports a live connection."""
        if not HAS_MT5 or mt5 is None or not self._connected:
            return False
        try:
            info = mt5.terminal_info()
            return bool(info is not None)
        except Exception:  # noqa: BLE001
            return False

    def shutdown(self) -> None:
        """Release the terminal connection."""
        self._connected = False
        if HAS_MT5 and mt5 is not None:
            try:
                mt5.shutdown()
            except Exception:  # noqa: BLE001
                pass

    # -- account / symbols ----------------------------------------------
    def account_info(self) -> Optional[AccountInfo]:
        """Current account snapshot, or None when unavailable."""
        if not self.is_connected() or mt5 is None:
            return None
        try:
            raw = mt5.account_info()
            if raw is None:
                return None
            return AccountInfo(
                balance=float(raw.balance),
                equity=float(raw.equity),
                margin=float(raw.margin),
                free_margin=float(raw.free_margin),
                currency=str(raw.currency),
                leverage=int(raw.leverage),
                profit=float(raw.profit),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("account_info error: %s", exc)
            return None

    def symbol_spec(self, symbol: str) -> Optional[dict[str, Any]]:
        """Broker contract specification for a symbol, or None."""
        if not self.is_connected() or mt5 is None:
            return None
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                return None
            return {
                "tick_value": float(info.trade_tick_value),
                "tick_size": float(info.trade_tick_size),
                "point": float(info.point),
                "digits": int(info.digits),
                "volume_min": float(info.volume_min),
                "volume_max": float(info.volume_max),
                "volume_step": float(info.volume_step),
                "spread_points": float(info.spread),
                "currency_profit": str(info.currency_profit or "USD"),
                "trade_allowed": bool(info.trade_mode in (0, 4)),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("symbol_spec error for %s: %s", symbol, exc)
            return None

    def ensure_symbol(self, symbol: str) -> bool:
        """Select a symbol in MarketWatch so data/orders work."""
        if not self.is_connected() or mt5 is None:
            return False
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                logger.error("Unknown symbol: %s", symbol)
                return False
            if not info.visible:
                return bool(mt5.symbol_select(symbol, True))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("ensure_symbol error for %s: %s", symbol, exc)
            return False

    # -- market data -----------------------------------------------------
    def copy_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Last N closed bars as an OHLC frame (UTC); empty when unavailable."""
        columns = ["time", "open", "high", "low", "close", "tick_volume", "spread"]
        if not self.is_connected() or mt5 is None:
            return pd.DataFrame(columns=columns)
        tf = mt5_timeframe(timeframe)
        if tf is None:
            return pd.DataFrame(columns=columns)
        try:
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, max(1, int(count)))
            if rates is None or len(rates) == 0:
                return pd.DataFrame(columns=columns)
            frame = pd.DataFrame(rates)
            frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
            return frame[columns]
        except Exception as exc:  # noqa: BLE001
            logger.error("copy_rates error %s %s: %s", symbol, timeframe, exc)
            return pd.DataFrame(columns=columns)

    def current_tick(self, symbol: str) -> Optional[TickData]:
        """Latest tick for a symbol, or None when unavailable."""
        if not self.is_connected() or mt5 is None:
            return None
        try:
            raw = mt5.symbol_info_tick(symbol)
            if raw is None:
                return None
            return TickData(
                symbol=symbol,
                time=datetime.fromtimestamp(raw.time, tz=timezone.utc),
                bid=float(raw.bid),
                ask=float(raw.ask),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("current_tick error for %s: %s", symbol, exc)
            return None

    # -- positions / orders (low level; OrderManager adds retry/verify) --
    def open_positions(self, symbol: Optional[str] = None) -> list[Position]:
        """Open positions, optionally filtered to one symbol."""
        if not self.is_connected() or mt5 is None:
            return []
        try:
            raw_positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
            if not raw_positions:
                return []
            out: list[Position] = []
            for raw in raw_positions:
                action = SignalAction.BUY if raw.type == mt5.POSITION_TYPE_BUY else SignalAction.SELL
                out.append(
                    Position(
                        ticket=str(raw.ticket),
                        symbol=str(raw.symbol),
                        action=action,
                        volume=float(raw.volume),
                        entry=float(raw.price_open),
                        stop_loss=float(raw.sl),
                        take_profit=float(raw.tp),
                        open_time=datetime.fromtimestamp(raw.time, tz=timezone.utc),
                        comment=str(raw.comment or ""),
                        magic=int(raw.magic),
                        current_price=float(raw.price_current),
                        profit=float(raw.profit),
                        swap=float(raw.swap),
                    )
                )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.error("open_positions error: %s", exc)
            return []

    def raw_order_send(self, request: dict[str, Any]) -> Optional[Any]:
        """Pass a raw order request to the terminal (used by the executor)."""
        if not self.is_connected() or mt5 is None:
            return None
        try:
            return mt5.order_send(request)
        except Exception as exc:  # noqa: BLE001
            logger.error("order_send error: %s", exc)
            return None

    def last_error(self) -> Any:
        """Last terminal error tuple, or None without MT5."""
        if not HAS_MT5 or mt5 is None:
            return None
        try:
            return mt5.last_error()
        except Exception:  # noqa: BLE001
            return None

    def pending_orders(self, symbol: Optional[str] = None) -> list[Any]:
        """Pending orders, optionally filtered to one symbol."""
        if not self.is_connected() or mt5 is None:
            return []
        try:
            orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
            return list(orders or [])
        except Exception as exc:  # noqa: BLE001
            logger.error("pending_orders error: %s", exc)
            return []
