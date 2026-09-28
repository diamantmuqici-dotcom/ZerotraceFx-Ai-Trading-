"""Broker abstraction: one interface for live MT5, paper and backtest fills."""
from __future__ import annotations

from abc import ABC, abstractmethod
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


class BrokerInterface(ABC):
    """Contract every execution venue must implement."""

    name: str = "broker"

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the venue. Returns True on success."""
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        """True when the venue is ready to trade."""
        raise NotImplementedError

    @abstractmethod
    def account_info(self) -> Optional[AccountInfo]:
        """Current account snapshot."""
        raise NotImplementedError

    @abstractmethod
    def symbol_spec(self, symbol: str) -> Optional[SymbolSpec]:
        """Contract specification for a symbol."""
        raise NotImplementedError

    @abstractmethod
    def current_price(self, symbol: str) -> Optional[tuple[float, float]]:
        """Current (bid, ask) or None when unavailable."""
        raise NotImplementedError

    @abstractmethod
    def get_positions(self, symbol: Optional[str] = None) -> list[Position]:
        """Open positions, optionally filtered to one symbol."""
        raise NotImplementedError

    @abstractmethod
    def place_market_order(
        self,
        symbol: str,
        action: SignalAction,
        volume: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "",
    ) -> OrderResult:
        """Open a market position with optional SL/TP."""
        raise NotImplementedError

    @abstractmethod
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
        """Place a stop/limit pending order."""
        raise NotImplementedError

    @abstractmethod
    def modify_position(self, ticket: str, stop_loss: float, take_profit: float) -> bool:
        """Modify SL/TP of an open position."""
        raise NotImplementedError

    @abstractmethod
    def close_position(self, ticket: str, volume: Optional[float] = None) -> CloseResult:
        """Close a position fully or partially (volume in lots)."""
        raise NotImplementedError

    @abstractmethod
    def close_all(self, symbol: Optional[str] = None) -> CloseAllResult:
        """Close every open position (and cancel pending orders)."""
        raise NotImplementedError

    def closed_profit(self, ticket: str) -> Optional[float]:
        """Realised net profit of a fully closed position, if known."""
        return None

    def shutdown(self) -> None:
        """Release venue resources (optional)."""
        return None
