"""Event-driven backtest engine reusing the live strategy, sizing and basket."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import pandas as pd

from backtest.metrics import BacktestReport, compute_report
from config.settings import Settings
from core.types import MarketState, MTF_ORDER, SignalAction, SymbolSpec, TradeSignal
from market.filters import session_strength
from market.indicators import resample_ohlc, validate_ohlc
from risk.basket import BasketManager
from risk.position_sizing import lots_for_risk
from strategy.strategy import Strategy
from utils.common import from_pips, position_profit, utcnow
from utils.logging_setup import get_logger

logger = get_logger("app")


@dataclass
class BacktestTrade:
    """One simulated round-trip with full audit context."""

    symbol: str
    action: SignalAction
    entry_time: datetime
    exit_time: datetime
    entry: float
    exit: float
    volume: float
    stop_loss: float
    take_profit: float
    profit: float
    commission: float
    exit_reason: str
    confidence: float = 0.0
    setup_id: str = ""
    bars_held: int = 0

    @property
    def net(self) -> float:
        """Profit after commission."""
        return self.profit - self.commission


@dataclass
class _SimPosition:
    """Internal simulated open position."""

    action: SignalAction
    entry_time: datetime
    entry: float
    volume: float
    stop_loss: float
    take_profit: float
    confidence: float
    setup_id: str
    entry_bar: int
    initial_risk: float
    partialed: bool = False


@dataclass
class BacktestResult:
    """Full backtest output: trades, equity curve and performance report."""

    symbol: str
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    report: Optional[BacktestReport] = None

    @property
    def final_equity(self) -> float:
        """Last equity point (0.0 when empty)."""
        return self.equity_curve[-1][1] if self.equity_curve else 0.0


SignalFn = Callable[[dict[str, pd.DataFrame], int, pd.Series], Optional[TradeSignal]]


class BacktestEngine:
    """Bars-driven simulator: M5 execution with resampled higher timeframes."""

    def __init__(self, strategy: Strategy, settings: Settings, spec: SymbolSpec) -> None:
        """Bind the live strategy, settings and contract spec."""
        self.strategy = strategy
        self.settings = settings
        self.spec = spec

    def run(
        self,
        symbol: str,
        m5: pd.DataFrame,
        signal_fn: Optional[SignalFn] = None,
        warmup_bars: int = 300,
        signal_every: int = 3,
        initial_balance: Optional[float] = None,
        spread_pips: Optional[float] = None,
        max_lookback_m5: int = 2500,
    ) -> BacktestResult:
        """Simulate trading over M5 history; returns trades + equity + report."""
        symbol = symbol.upper()
        base = validate_ohlc(m5)
        if len(base) < warmup_bars + 10:
            raise ValueError(
                f"Need at least {warmup_bars + 10} M5 bars, got {len(base)}"
            )
        balance = initial_balance if initial_balance is not None else self.settings.paper_balance
        spread = spread_pips if spread_pips is not None else self.settings.slippage_pips
        spread_price = (spread + self.settings.slippage_pips) * _pip(symbol)
        commission = self.settings.commission_per_lot
        basket = BasketManager(
            target=self.settings.basket_target,
            trailing_enabled=self.settings.basket_trailing_enabled,
            trailing_pct=self.settings.basket_trailing_pct,
        )
        result = BacktestResult(symbol=symbol)
        open_position: Optional[_SimPosition] = None
        warmup = max(warmup_bars, 60)

        closes = base["close"].astype(float).to_numpy()
        for i in range(warmup, len(base)):
            bar = base.iloc[i]
            when = pd.to_datetime(bar["time"], utc=True).to_pydatetime()
            high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
            # --- manage the open simulated position on this bar ---
            if open_position is not None:
                closed_trade, delta = self._manage_bar(
                    open_position, high, low, close, when, i,
                    symbol, spread_price, commission,
                )
                balance = round(balance + delta, 2)
                if closed_trade is not None:
                    result.trades.append(closed_trade)
                    open_position = None
            # --- basket target across the (single-slot) simulated book ---
            if open_position is not None:
                floating = self._floating(open_position, close, symbol)
                if not basket.trailing_enabled and floating >= basket.target:
                    trade = self._close_position(
                        open_position, close, when, i, symbol,
                        spread_price, commission, "BASKET_TARGET",
                    )
                    balance = round(balance + trade.net, 2)
                    result.trades.append(trade)
                    open_position = None
                    basket.reset()
            # --- fresh signal on the evaluation grid, flat only ---
            if open_position is None and (i - warmup) % max(1, signal_every) == 0:
                signal = self._signal_at(
                    symbol, base, i, signal_fn, max_lookback_m5
                )
                if signal is not None and signal.is_entry and signal.risk_distance > 0:
                    lots = lots_for_risk(balance, self.settings.risk_percent,
                                         signal.entry, signal.stop_loss, self.spec)
                    if lots > 0:
                        fill = signal.entry + (
                            spread_price / 2 if signal.action is SignalAction.BUY
                            else -spread_price / 2
                        )
                        open_position = _SimPosition(
                            action=signal.action, entry_time=when, entry=fill,
                            volume=lots, stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit,
                            confidence=signal.confidence, setup_id=signal.setup_id,
                            entry_bar=i,
                            initial_risk=abs(fill - signal.stop_loss),
                        )
            floating_now = self._floating(open_position, close, symbol) if open_position else 0.0
            result.equity_curve.append((when, round(balance + floating_now, 2)))
        # --- close any leftover at the final close ---
        if open_position is not None:
            when = pd.to_datetime(base["time"].iloc[-1], utc=True).to_pydatetime()
            trade = self._close_position(
                open_position, closes[-1], when, len(base) - 1, symbol,
                spread_price, commission, "END_OF_DATA",
            )
            balance = round(balance + trade.net, 2)
            result.trades.append(trade)
        result.report = compute_report(
            result.trades, result.equity_curve, balance0=(
                initial_balance if initial_balance is not None else self.settings.paper_balance
            ),
        )
        logger.info("Backtest %s: %d trades, final equity %.2f",
                    symbol, len(result.trades), balance)
        return result

    # -- internals ------------------------------------------------------------
    def _signal_at(
        self,
        symbol: str,
        base: pd.DataFrame,
        i: int,
        signal_fn: Optional[SignalFn],
        max_lookback: int,
    ) -> Optional[TradeSignal]:
        """Build MTF slices ending at bar i and obtain a signal."""
        start = max(0, i + 1 - max_lookback)
        window = base.iloc[start: i + 1]
        mtf: dict[str, pd.DataFrame] = {"M5": window.reset_index(drop=True)}
        for tf in ("M15", "H1", "H4", "D1"):
            try:
                mtf[tf] = resample_ohlc(window, tf)
            except Exception:  # noqa: BLE001 - thin history degrades gracefully
                mtf[tf] = pd.DataFrame(columns=["time", "open", "high", "low", "close"])
        if signal_fn is not None:
            try:
                return signal_fn(mtf, i, base.iloc[i])
            except Exception as exc:  # noqa: BLE001 - custom fn must not kill run
                logger.warning("signal_fn failed at bar %d: %s", i, exc)
                return None
        when = pd.to_datetime(base["time"].iloc[i], utc=True).to_pydatetime()
        market = MarketState(
            symbol=symbol, spread_pips=self.settings.spread_limit_pips / 2,
            spread_ok=True, news_ok=True, session="Backtest",
            session_strength=float(session_strength(when)), timestamp=when,
        )
        try:
            return self.strategy.analyze_data(symbol, mtf, market, self.spec)
        except Exception as exc:  # noqa: BLE001 - per-bar isolation
            logger.warning("Strategy failed at bar %d: %s", i, exc)
            return None

    def _floating(self, pos: _SimPosition, close: float, symbol: str) -> float:
        """Unrealised gross profit at the bar close."""
        return position_profit(pos.entry, close, pos.action, pos.volume,
                               self.spec.tick_value, self.spec.tick_size)

    def _manage_bar(
        self,
        pos: _SimPosition,
        high: float,
        low: float,
        close: float,
        when: datetime,
        bar: int,
        symbol: str,
        spread_price: float,
        commission: float,
    ) -> Optional[tuple[BacktestTrade, float]]:
        """Apply SL/TP/BE/trailing/partial; returns (trade, balance_delta_base)."""
        # Break-even + trailing ratchet first (uses close as the traded price).
        if pos.action is SignalAction.BUY:
            profit_dist = close - pos.entry
        else:
            profit_dist = pos.entry - close
        rr = profit_dist / pos.initial_risk if pos.initial_risk > 0 else 0.0
        if rr >= self.settings.break_even_trigger_rr and pos.initial_risk > 0:
            offset = from_pips(symbol, self.settings.break_even_offset_pips)
            be = pos.entry + offset if pos.action is SignalAction.BUY else pos.entry - offset
            if pos.action is SignalAction.BUY and be > pos.stop_loss:
                pos.stop_loss = be
            elif pos.action is SignalAction.SELL and be < pos.stop_loss:
                pos.stop_loss = be
        if rr >= self.settings.trailing_start_rr:
            step = from_pips(symbol, self.settings.trailing_step_pips)
            if pos.action is SignalAction.BUY:
                trail = close - step
                if trail > pos.stop_loss + step / 2:
                    pos.stop_loss = trail
            else:
                trail = close + step
                if trail < pos.stop_loss - step / 2:
                    pos.stop_loss = trail
        # Partial TP: bank a slice, keep the rest running (single partial).
        balance_delta = 0.0
        if (
            self.settings.partial_tp_enabled
            and not pos.partialed
            and rr >= self.settings.partial_tp_rr
        ):
            fraction = max(0.05, min(0.95, self.settings.partial_tp_pct / 100.0))
            slice_vol = round(pos.volume * fraction, 8)
            if slice_vol > 0:
                exit_px = close - spread_price / 2 if pos.action is SignalAction.BUY else close + spread_price / 2
                gross = position_profit(pos.entry, exit_px, pos.action, slice_vol,
                                        self.spec.tick_value, self.spec.tick_size)
                fee = slice_vol * commission
                balance_delta += gross - fee
                pos.volume = round(pos.volume - slice_vol, 8)
                pos.partialed = True
        # Stop-loss (priority) then take-profit on the bar extremes.
        exit_px: Optional[float] = None
        reason = ""
        if pos.action is SignalAction.BUY:
            if pos.stop_loss > 0 and low <= pos.stop_loss:
                exit_px, reason = pos.stop_loss, "SL"
            elif pos.take_profit > 0 and high >= pos.take_profit:
                exit_px, reason = pos.take_profit, "TP"
        else:
            if pos.stop_loss > 0 and high >= pos.stop_loss:
                exit_px, reason = pos.stop_loss, "SL"
            elif pos.take_profit > 0 and low <= pos.take_profit:
                exit_px, reason = pos.take_profit, "TP"
        if exit_px is None:
            # Runner continues; any banked partial is settled via balance_delta.
            return None, balance_delta
        trade = self._close_position(pos, exit_px, when, bar, symbol,
                                     0.0, commission, reason)
        trade.profit = round(trade.profit + balance_delta, 2)
        return trade, trade.net

    def _close_position(
        self,
        pos: _SimPosition,
        exit_px: float,
        when: datetime,
        bar: int,
        symbol: str,
        spread_price: float,
        commission: float,
        reason: str,
    ) -> BacktestTrade:
        """Materialise a closed simulated trade."""
        if spread_price:
            exit_px = exit_px - spread_price / 2 if pos.action is SignalAction.BUY else exit_px + spread_price / 2
        gross = position_profit(pos.entry, exit_px, pos.action, pos.volume,
                                self.spec.tick_value, self.spec.tick_size)
        fee = pos.volume * commission
        return BacktestTrade(
            symbol=symbol, action=pos.action, entry_time=pos.entry_time,
            exit_time=when, entry=pos.entry, exit=exit_px, volume=pos.volume,
            stop_loss=pos.stop_loss, take_profit=pos.take_profit,
            profit=round(gross, 2), commission=round(fee, 2),
            exit_reason=reason, confidence=pos.confidence,
            setup_id=pos.setup_id, bars_held=bar - pos.entry_bar,
        )


def _pip(symbol: str) -> float:
    """Pip size helper avoiding a hard utils dependency at import time."""
    from utils.common import pip_size

    return pip_size(symbol)
