"""LiveTrader: one engine cycle over all symbols (signals, risk, exits, basket)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config.settings import Settings
from core.events import Event, get_event_bus
from core.state import RuntimeState
from core.types import MarketState, Position, SignalAction
from execution.order_manager import OrderManager
from market.data_engine import MarketDataEngine
from market.filters import (
    EconomicCalendar,
    current_sessions,
    is_session_allowed,
    session_strength,
)
from paper.paper_broker import PaperBroker
from risk.basket import BasketManager
from risk.position_sizing import lots_for_risk, risk_amount_for_lots
from risk.risk_manager import RiskManager
from strategy.strategy import Strategy
from utils.common import from_pips, utcnow
from utils.journal import TradeJournal
from utils.logging_setup import get_logger, log_trade_event

logger = get_logger("app")
trade_logger = get_logger("trades")


@dataclass
class CycleResult:
    """Summary of a single trading-loop iteration."""

    ran_at: datetime
    symbols_checked: int = 0
    signals: int = 0
    orders_placed: int = 0
    basket_closed: bool = False
    basket_profit: float = 0.0
    notes: list[str] = field(default_factory=list)


class LiveTrader:
    """Owns the realtime loop; shared by PAPER and LIVE modes."""

    def __init__(
        self,
        settings: Settings,
        data: MarketDataEngine,
        strategy: Strategy,
        orders: OrderManager,
        risk: RiskManager,
        basket: BasketManager,
        journal: TradeJournal,
        state: RuntimeState,
        calendar: EconomicCalendar,
    ) -> None:
        """Wire every engine component into the trading loop."""
        self.settings = settings
        self.data = data
        self.strategy = strategy
        self.orders = orders
        self.risk = risk
        self.basket = basket
        self.journal = journal
        self.state = state
        self.calendar = calendar
        self._partialed: set[str] = set()
        self._initial_risk: dict[str, float] = {}
        self._equity_points = 0

    # -- main loop ---------------------------------------------------------
    async def run_forever(self) -> None:
        """Run cycles until the state is stopped (headless trade mode)."""
        self.state.update(running=True, status_message="Trading loop started")
        try:
            while self.state.running:
                if self.state.paused or self.state.kill_switch:
                    await asyncio.sleep(1.0)
                    continue
                try:
                    await self.cycle()
                except Exception as exc:  # noqa: BLE001 - loop must survive
                    logger.exception("Trading cycle failed: %s", exc)
                    self.state.update(status_message=f"Cycle error: {exc}")
                await asyncio.sleep(max(1, self.settings.poll_interval_sec))
        finally:
            self.state.update(running=False, status_message="Trading loop stopped")

    async def cycle(self, now: Optional[datetime] = None) -> CycleResult:
        """Execute one full iteration over every configured symbol."""
        now = now or utcnow()
        result = CycleResult(ran_at=now)
        broker = self.orders.broker
        await self._feed_paper_prices()
        account = broker.account_info()
        if account is None:
            result.notes.append("no account info")
            self.state.update(status_message="Waiting for broker connection")
            return result
        positions = broker.get_positions()
        self.risk.on_equity_update(account.equity, account.balance, now)
        if self.risk.kill_switch:
            self.state.update(kill_switch=True,
                              status_message=f"Halted: {self.risk.kill_reason}")
        # --- basket first: an achieved target closes EVERYTHING instantly ---
        snap = self.basket.update(positions, now)
        should_close, reason = self.basket.should_close()
        if should_close:
            await self._close_basket(reason, result)
            positions = broker.get_positions()
            snap = self.basket.update(positions, now)
        else:
            self._manage_exits(positions)
        # --- fresh signals per symbol --------------------------------------
        sessions = current_sessions(now)
        strength = session_strength(now)
        session_ok_global = (
            not self.settings.session_filter_enabled
            or is_session_allowed(now, self.settings.allowed_session_list)
        )
        for symbol in self.settings.symbol_list:
            result.symbols_checked += 1
            spread = await self.data.get_spread_pips(symbol)
            spread_pips = spread if spread is not None else 999.0
            spread_ok = spread_pips <= self.settings.spread_limit_pips
            news_ok = (
                not self.settings.news_filter_enabled
                or not self.calendar.is_blocked(symbol, now)
            )
            if self.settings.news_filter_enabled and not news_ok:
                result.notes.append(f"{symbol}: news blackout")
            market = MarketState(
                symbol=symbol, spread_pips=spread_pips, spread_ok=spread_ok,
                news_ok=news_ok, session=",".join(sessions) or "Off",
                session_strength=strength, timestamp=now,
            )
            try:
                spec = broker.symbol_spec(symbol)
                signal = await self.strategy.evaluate(symbol, self.data, market, spec)
            except Exception as exc:  # noqa: BLE001 - per-symbol isolation
                logger.warning("Strategy failed for %s: %s", symbol, exc)
                continue
            self.state.update(
                last_signal=signal.action.value, last_confidence=signal.confidence,
                last_reasoning=signal.reasoning[:8], active_symbol=symbol,
                session=market.session,
            )
            if not signal.is_entry:
                continue
            result.signals += 1
            self.journal.record_signal(signal)
            if self.risk.kill_switch:
                continue
            if spec is None or signal.risk_distance <= 0:
                result.notes.append(f"{symbol}: cannot size (no spec/SL)")
                continue
            lots = lots_for_risk(account.balance, self.settings.risk_percent,
                                 signal.entry, signal.stop_loss, spec)
            total_lots = sum(p.volume for p in positions if p.symbol == symbol)
            check = self.risk.pre_trade_check(
                open_positions=len(positions), total_lots=total_lots,
                new_lots=lots, spread_pips=spread_pips,
                latency_ms=self.orders.last_latency_ms,
                news_ok=news_ok, session_ok=session_ok_global,
            )
            if not check.allowed:
                result.notes.append(f"{symbol}: blocked ({'; '.join(check.reasons)})")
                await get_event_bus().publish(
                    Event.RISK_BLOCK, {"symbol": symbol, "reasons": check.reasons})
                continue
            fill = self.orders.place_market(
                symbol, signal.action, lots, signal.stop_loss,
                signal.take_profit, comment=f"ZT {signal.setup_id}"[:31],
                max_spread_pips=self.settings.spread_limit_pips,
            )
            if fill.success:
                result.orders_placed += 1
                positions = broker.get_positions()
                self._initial_risk[fill.ticket] = abs(signal.entry - signal.stop_loss)
                self.journal.record_fill(
                    symbol, signal.action.value, fill.ticket, fill.volume,
                    fill.price, signal.stop_loss, signal.take_profit,
                    signal.confidence, signal.setup_id,
                    "; ".join(signal.reasoning[:4]), now,
                )
                log_trade_event(
                    trade_logger, event="ENTRY", symbol=symbol,
                    action=signal.action.value, ticket=fill.ticket,
                    volume=fill.volume, entry=fill.price, sl=signal.stop_loss,
                    tp=signal.take_profit, confidence=round(signal.confidence, 1),
                )
                await get_event_bus().publish(Event.ORDER_PLACED, {
                    "symbol": symbol, "ticket": fill.ticket,
                    "action": signal.action.value, "volume": fill.volume,
                    "price": fill.price, "confidence": signal.confidence,
                })
            else:
                result.notes.append(f"{symbol}: order failed ({fill.message})")
        # --- publish state ----------------------------------------------------
        account = broker.account_info() or account
        positions = broker.get_positions()
        snap = self.basket.update(positions, now)
        if not result.basket_closed:
            result.basket_profit = snap.floating
        self.state.update(
            balance=account.balance, equity=account.equity,
            free_margin=account.free_margin, margin=account.margin,
            floating=account.profit, basket_profit=snap.floating,
            basket_target=snap.target, basket_highest=snap.highest,
            trailing_active=snap.trailing_active,
            basket_direction=snap.direction,
            drawdown_pct=round(self.risk.drawdown_pct, 2),
            daily_pnl=round(self.risk.daily_pnl, 2),
            weekly_pnl=round(self.risk.weekly_pnl, 2),
            open_positions=positions,
            status_message=f"Cycle ok: {result.signals} signals, "
                           f"{result.orders_placed} fills @ {now:%H:%M:%S}",
        )
        self._equity_points += 1
        if self._equity_points % 3 == 1:
            self.state.append_equity(account.equity, now)
        return result

    # -- basket close ----------------------------------------------------------
    async def _close_basket(self, reason: str, result: CycleResult) -> None:
        """Close all positions immediately, journal, update stats and reset."""
        positions = self.orders.broker.get_positions()
        entries = {p.ticket: p.entry for p in positions}
        outcome = self.orders.close_all_verified()
        result.basket_closed = True
        result.basket_profit = outcome.total_profit
        self.basket.reset()
        self._partialed.clear()
        self._initial_risk.clear()
        self.risk.record_closed_profit(outcome.total_profit)
        self.journal.record_basket("CLOSED", {
            "reason": reason, "closed": outcome.closed,
            "failed": outcome.failed, "profit": round(outcome.total_profit, 2),
        })
        log_trade_event(
            trade_logger, event="BASKET_CLOSE", reason=reason,
            closed=outcome.closed, profit=round(outcome.total_profit, 2),
        )
        self.state.push_trade({
            "time": utcnow().isoformat(), "symbol": "BASKET",
            "action": "CLOSE_ALL", "profit": round(outcome.total_profit, 2),
            "reason": reason, "entries": entries,
        })
        await get_event_bus().publish(Event.BASKET_CLOSED, {
            "reason": reason, "profit": outcome.total_profit,
            "closed": outcome.closed,
        })
        logger.info("Basket closed: %s (%+.2f)", reason, outcome.total_profit)

    # -- exit management ---------------------------------------------------------
    def _manage_exits(self, positions: list[Position]) -> None:
        """Apply break-even, trailing stop and partial take-profit per position."""
        for position in positions:
            if position.ticket not in self._initial_risk:
                risk_dist = abs(position.entry - position.stop_loss) if position.has_stop else 0.0
                if risk_dist <= 0:
                    continue
                self._initial_risk[position.ticket] = risk_dist
            risk_dist = self._initial_risk[position.ticket]
            current = position.current_price or position.entry
            if position.action is SignalAction.BUY:
                profit_dist = current - position.entry
                new_sl_be = position.entry + from_pips(position.symbol, self.settings.break_even_offset_pips)
            else:
                profit_dist = position.entry - current
                new_sl_be = position.entry - from_pips(position.symbol, self.settings.break_even_offset_pips)
            rr = profit_dist / risk_dist if risk_dist > 0 else 0.0
            # Break-even: lock entry+offset once the trigger RR is reached.
            if rr >= self.settings.break_even_trigger_rr and position.has_stop:
                better = (
                    new_sl_be > position.stop_loss
                    if position.action is SignalAction.BUY
                    else new_sl_be < position.stop_loss
                )
                if better:
                    self.orders.modify_verified(position.ticket, new_sl_be, position.take_profit)
                    position.stop_loss = new_sl_be
            # Trailing stop: ratchet SL behind price after the start RR.
            if rr >= self.settings.trailing_start_rr:
                step = from_pips(position.symbol, self.settings.trailing_step_pips)
                if position.action is SignalAction.BUY:
                    trail_sl = current - step
                    if (not position.has_stop) or trail_sl > position.stop_loss + step / 2:
                        self.orders.modify_verified(position.ticket, trail_sl, position.take_profit)
                        position.stop_loss = trail_sl
                else:
                    trail_sl = current + step
                    if (not position.has_stop) or trail_sl < position.stop_loss - step / 2:
                        self.orders.modify_verified(position.ticket, trail_sl, position.take_profit)
                        position.stop_loss = trail_sl
            # Partial take-profit: bank a slice once, at the configured RR.
            if (
                self.settings.partial_tp_enabled
                and position.ticket not in self._partialed
                and rr >= self.settings.partial_tp_rr
            ):
                fraction = max(0.05, min(0.95, self.settings.partial_tp_pct / 100.0))
                spec = self.orders.broker.symbol_spec(position.symbol)
                raw_volume = position.volume * fraction
                if spec is not None:
                    import math as _math
                    steps = _math.floor(raw_volume / spec.volume_step)
                    raw_volume = steps * spec.volume_step
                if raw_volume >= (spec.volume_min if spec else 0.01):
                    closed = self.orders.close_position_verified(position.ticket, raw_volume)
                    if closed.success:
                        self._partialed.add(position.ticket)
                        self.risk.record_closed_profit(closed.profit)
                        self.journal.record_close(
                            position.symbol, position.action.value, position.ticket,
                            raw_volume, position.entry, closed.price, closed.profit,
                            reason="PARTIAL_TP",
                        )

    # -- paper pricing --------------------------------------------------------------
    async def _feed_paper_prices(self) -> None:
        """Push latest quotes into the paper broker from the data engine."""
        broker = self.orders.broker
        if not isinstance(broker, PaperBroker):
            return
        for symbol in self.settings.symbol_list:
            quote = await self.data.get_latest_price(symbol)
            if quote is not None:
                broker.set_price(symbol, quote[0], quote[1])
