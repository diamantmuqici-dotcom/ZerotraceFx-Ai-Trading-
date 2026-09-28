"""Simulated broker: fake balance, spreads, commission, slippage, SL/TP stops."""
from __future__ import annotations

import itertools
import math
from datetime import datetime
from typing import Optional

from config.constants import DEFAULT_SPREADS_PIPS
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
from utils.common import normalize_lots, pip_size, position_profit, utcnow
from utils.logging_setup import get_logger

logger = get_logger("app")


class PaperBroker(BrokerInterface):
    """In-memory venue mirroring live execution semantics for safe testing."""

    name = "paper"

    def __init__(
        self,
        specs: dict[str, SymbolSpec],
        balance: float = 10000.0,
        leverage: int = 100,
        commission_per_lot: float = 7.0,
        slippage_pips: float = 0.5,
        spreads_pips: Optional[dict[str, float]] = None,
    ) -> None:
        """Fund the simulated account and register instrument specs."""
        self._specs = dict(specs)
        self._balance = float(balance)
        self._leverage = max(1, leverage)
        self._commission_per_lot = max(0.0, commission_per_lot)
        self._slippage_pips = max(0.0, slippage_pips)
        self._spreads = dict(DEFAULT_SPREADS_PIPS)
        if spreads_pips:
            self._spreads.update(spreads_pips)
        self._prices: dict[str, tuple[float, float, datetime]] = {}
        self._positions: dict[str, Position] = {}
        self._tickets = itertools.count(100001)
        self._connected = False
        self._realised = 0.0

    # -- connection ------------------------------------------------------
    def connect(self) -> bool:
        """Paper venue is always ready once constructed."""
        self._connected = True
        logger.info("Paper broker connected (balance %.2f)", self._balance)
        return True

    def is_connected(self) -> bool:
        """Paper venue connectivity flag."""
        return self._connected

    # -- market data -------------------------------------------------------
    def symbol_spec(self, symbol: str) -> Optional[SymbolSpec]:
        """Registered contract spec for a symbol."""
        return self._specs.get(symbol.upper())

    def set_price(self, symbol: str, bid: float, ask: float,
                  when: Optional[datetime] = None) -> None:
        """Push a quote; marks positions and triggers stop-loss/take-profit."""
        symbol = symbol.upper()
        self._prices[symbol] = (float(bid), float(ask), when or utcnow())
        self._mark_to_market(symbol)
        self._trigger_stops(symbol, bid=float(bid), ask=float(ask))

    def on_bar(self, symbol: str, bar_high: float, bar_low: float,
               bar_close: float, when: Optional[datetime] = None) -> None:
        """Drive the venue from a candle: intrabar SL/TP then close pricing."""
        symbol = symbol.upper()
        half = self._spreads.get(symbol, 2.0) * pip_size(symbol) / 2.0
        self._trigger_stops(symbol, bar_high=bar_high, bar_low=bar_low)
        self.set_price(symbol, bar_close - half, bar_close + half, when)

    def current_price(self, symbol: str) -> Optional[tuple[float, float]]:
        """Latest (bid, ask) or None before the first quote."""
        quote = self._prices.get(symbol.upper())
        return (quote[0], quote[1]) if quote else None

    def _slippage_price(self, symbol: str) -> float:
        """Adverse slippage distance in price units (deterministic worst-case)."""
        return self._slippage_pips * pip_size(symbol)

    def _required_margin(self, symbol: str, volume: float, price: float) -> float:
        """Simplified margin: notional / leverage (contract size 100k / 100oz)."""
        contract = 100.0 if symbol.upper().startswith("XAU") else 100000.0
        quote_to_account = 1.0
        if symbol.upper().endswith("JPY"):
            quote_to_account = 1.0 / max(price, 1e-9)
        notional = volume * contract * (price if symbol.upper().startswith("XAU") else 1.0)
        if not symbol.upper().startswith("XAU"):
            notional = volume * contract * quote_to_account
        return notional / self._leverage

    # -- account -------------------------------------------------------------
    def account_info(self) -> Optional[AccountInfo]:
        """Simulated account snapshot with live equity."""
        floating = sum(p.net_profit for p in self._positions.values())
        equity = self._balance + floating
        margin = sum(
            self._required_margin(p.symbol, p.volume, p.current_price or p.entry)
            for p in self._positions.values()
        )
        return AccountInfo(
            balance=round(self._balance, 2), equity=round(equity, 2),
            margin=round(margin, 2),
            free_margin=round(max(0.0, equity - margin), 2),
            currency="USD", leverage=self._leverage, profit=round(floating, 2),
        )

    def get_positions(self, symbol: Optional[str] = None) -> list[Position]:
        """Open simulated positions, optionally filtered to one symbol."""
        positions = list(self._positions.values())
        if symbol:
            positions = [p for p in positions if p.symbol == symbol.upper()]
        return sorted(positions, key=lambda p: p.open_time)

    # -- orders ----------------------------------------------------------------
    def place_market_order(
        self,
        symbol: str,
        action: SignalAction,
        volume: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "",
    ) -> OrderResult:
        """Fill a market order at quote +/- deterministic slippage."""
        symbol = symbol.upper()
        spec = self._specs.get(symbol)
        quote = self._prices.get(symbol)
        if spec is None:
            return OrderResult(False, message=f"Unknown symbol {symbol}")
        if quote is None:
            return OrderResult(False, message="No price yet for symbol")
        lots = normalize_lots(volume, spec.volume_min, spec.volume_max, spec.volume_step)
        if lots <= 0:
            return OrderResult(False, message="Volume below minimum")
        bid, ask, _ = quote
        if action is SignalAction.BUY:
            fill = ask + self._slippage_price(symbol)
        elif action is SignalAction.SELL:
            fill = bid - self._slippage_price(symbol)
        else:
            return OrderResult(False, message="HOLD cannot be executed")
        margin = self._required_margin(symbol, lots, fill)
        account = self.account_info()
        assert account is not None
        if margin > account.free_margin:
            return OrderResult(False, message="Insufficient paper margin")
        ticket = str(next(self._tickets))
        commission = lots * self._commission_per_lot / 2.0  # half on open
        position = Position(
            ticket=ticket, symbol=symbol, action=action, volume=lots,
            entry=round(fill, spec.digits), stop_loss=stop_loss,
            take_profit=take_profit, open_time=utcnow(), comment=comment,
            current_price=round(fill, spec.digits), commission=commission,
        )
        self._positions[ticket] = position
        self._mark_to_market(symbol)
        return OrderResult(True, ticket=ticket, price=position.entry, volume=lots,
                           message="paper fill", latency_ms=2.0)

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
        """Paper pending orders fill immediately (documented simplification)."""
        logger.warning("Paper broker fills pending orders as market (simplification)")
        return self.place_market_order(symbol, action, volume, stop_loss, take_profit, comment)

    def modify_position(self, ticket: str, stop_loss: float, take_profit: float) -> bool:
        """Update SL/TP of a simulated position."""
        position = self._positions.get(str(ticket))
        if position is None:
            return False
        position.stop_loss = stop_loss
        position.take_profit = take_profit
        return True

    def close_position(self, ticket: str, volume: Optional[float] = None) -> CloseResult:
        """Close a simulated position fully or partially at current quote."""
        ticket = str(ticket)
        position = self._positions.get(ticket)
        if position is None:
            return CloseResult(False, ticket=ticket, message="Position not found")
        quote = self._prices.get(position.symbol)
        if quote is None:
            return CloseResult(False, ticket=ticket, message="No price")
        bid, ask, _ = quote
        spec = self._specs[position.symbol]
        lots = position.volume if volume is None else min(float(volume), position.volume)
        if lots <= 0:
            return CloseResult(False, ticket=ticket, message="Invalid volume")
        if position.action is SignalAction.BUY:
            fill = bid - self._slippage_price(position.symbol)
        else:
            fill = ask + self._slippage_price(position.symbol)
        gross = position_profit(position.entry, fill, position.action, lots,
                                spec.tick_value, spec.tick_size)
        commission = lots * self._commission_per_lot / 2.0  # half on close
        net = gross - commission - position.commission * (lots / position.volume)
        fraction = lots / position.volume
        position.commission = round(position.commission * (1.0 - fraction), 2)
        position.volume = round(position.volume - lots, 8)
        self._balance = round(self._balance + net, 2)
        self._realised = round(self._realised + net, 2)
        if position.volume < spec.volume_min / 2:
            del self._positions[ticket]
        else:
            self._mark_to_market(position.symbol)
        return CloseResult(True, ticket=ticket, price=round(fill, spec.digits),
                           profit=round(net, 2), message="paper close", latency_ms=2.0)

    def close_all(self, symbol: Optional[str] = None) -> CloseAllResult:
        """Close every simulated position immediately."""
        outcome = CloseAllResult()
        targets = [p.ticket for p in self.get_positions(symbol)]
        outcome.requested = len(targets)
        for ticket in targets:
            result = self.close_position(ticket)
            if result.success:
                outcome.closed += 1
                outcome.total_profit += result.profit
            else:
                outcome.failed += 1
        outcome.message = f"closed {outcome.closed}/{outcome.requested}"
        return outcome

    # -- internals ---------------------------------------------------------------
    def _mark_to_market(self, symbol: str) -> None:
        """Refresh floating profit of every position in the symbol."""
        quote = self._prices.get(symbol)
        if quote is None:
            return
        bid, ask, _ = quote
        spec = self._specs.get(symbol)
        if spec is None:
            return
        for position in self._positions.values():
            if position.symbol != symbol:
                continue
            current = bid if position.action is SignalAction.BUY else ask
            position.current_price = current
            position.profit = round(position_profit(
                position.entry, current, position.action, position.volume,
                spec.tick_value, spec.tick_size,
            ), 2)

    def _trigger_stops(
        self,
        symbol: str,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        bar_high: Optional[float] = None,
        bar_low: Optional[float] = None,
    ) -> None:
        """Close positions whose SL/TP traded (stop-loss takes priority)."""
        for position in list(self.get_positions(symbol)):
            if position.action is SignalAction.BUY:
                exit_bid = bid if bid is not None else position.current_price
                low = bar_low if bar_low is not None else exit_bid
                high = bar_high if bar_high is not None else exit_bid
                if position.has_stop and low <= position.stop_loss:
                    self._stop_close(position, position.stop_loss, "SL")
                elif position.has_take_profit and high >= position.take_profit:
                    self._stop_close(position, position.take_profit, "TP")
            else:
                exit_ask = ask if ask is not None else position.current_price
                low = bar_low if bar_low is not None else exit_ask
                high = bar_high if bar_high is not None else exit_ask
                if position.has_stop and high >= position.stop_loss:
                    self._stop_close(position, position.stop_loss, "SL")
                elif position.has_take_profit and low <= position.take_profit:
                    self._stop_close(position, position.take_profit, "TP")

    def _stop_close(self, position: Position, level: float, reason: str) -> None:
        """Force-close at an SL/TP level without extra slippage."""
        spec = self._specs[position.symbol]
        gross = position_profit(position.entry, level, position.action,
                                position.volume, spec.tick_value, spec.tick_size)
        commission = position.volume * self._commission_per_lot / 2.0
        net = gross - commission - position.commission
        self._balance = round(self._balance + net, 2)
        self._realised = round(self._realised + net, 2)
        logger.info("Paper %s #%s %s closed at %.5f (%+.2f)",
                    reason, position.ticket, position.symbol, level, net)
        del self._positions[position.ticket]

    @property
    def realised(self) -> float:
        """Lifetime realised profit of the paper account."""
        return self._realised

    def reset(self, balance: float) -> None:
        """Reset the paper account (used by tests/backtests)."""
        self._balance = float(balance)
        self._positions.clear()
        self._prices.clear()
        self._realised = 0.0
