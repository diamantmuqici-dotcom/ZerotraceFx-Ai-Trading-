"""ZeroTraceEngine: builds and owns every component for paper/live/backtest."""
from __future__ import annotations

import os

from config.constants import DEFAULT_SPECS
from config.settings import Settings
from core.state import RuntimeState
from core.types import MTF_ORDER, SymbolSpec
from execution.mt5_executor import MT5Executor
from execution.order_manager import OrderManager
from live.live_trader import LiveTrader
from market.data_engine import MarketDataEngine
from market.filters import EconomicCalendar
from market.mt5_client import MT5Client
from paper.paper_broker import PaperBroker
from risk.basket import BasketManager
from risk.risk_manager import RiskManager
from strategy.ai_engine import AIDecisionEngine
from strategy.learning import AdaptiveLearner
from strategy.strategy import Strategy
from utils.journal import TradeJournal
from utils.logging_setup import get_logger, setup_logging

logger = get_logger("app")


def default_spec(symbol: str) -> SymbolSpec:
    """Offline contract spec for a symbol (paper/backtest fallback)."""
    symbol = symbol.upper()
    params = dict(DEFAULT_SPECS.get(symbol, DEFAULT_SPECS["EURUSD"]))
    digits = int(params.pop("digits", 5))
    return SymbolSpec(symbol=symbol, digits=digits, **params)  # type: ignore[arg-type]


class ZeroTraceEngine:
    """Composition root: constructs the full trading stack from Settings."""

    def __init__(self, settings: Settings) -> None:
        """Build all components; connect() brings venues online."""
        self.settings = settings
        setup_logging(settings.logs_dir, settings.log_level)
        self.state = RuntimeState(mode=settings.mode, basket_target=settings.basket_target)
        self.mt5 = MT5Client(
            login=settings.mt5_login, password=settings.mt5_password,
            server=settings.mt5_server, path=settings.mt5_path,
        )
        self.data = MarketDataEngine(self.mt5, candles_count=settings.candles_count)
        self.learner = AdaptiveLearner(
            path=os.path.join(settings.logs_dir, settings.learning_memory_file),
            learning_rate=settings.learning_rate,
            min_trades_for_calibration=settings.learning_min_trades,
            enabled=settings.learning_enabled,
        )
        self.strategy = Strategy(
            settings,
            ai=AIDecisionEngine(threshold=settings.confidence_threshold, learner=self.learner),
        )
        self.risk = RiskManager(settings)
        self.basket = BasketManager(
            target=settings.basket_target,
            trailing_enabled=settings.basket_trailing_enabled,
            trailing_pct=settings.basket_trailing_pct,
        )
        self.journal = TradeJournal(settings.logs_dir)
        self.calendar = EconomicCalendar(
            before_min=settings.news_before_min, after_min=settings.news_after_min,
            min_impact=settings.news_min_impact,
        )
        if settings.news_csv_path:
            self.calendar.load_csv(settings.news_csv_path)
        self.broker: MT5Executor | PaperBroker
        if settings.mode == "LIVE":
            self.broker = MT5Executor(self.mt5, magic=settings.magic_number)
        else:
            specs = {s: default_spec(s) for s in settings.symbol_list}
            self.broker = PaperBroker(
                specs, balance=settings.paper_balance, leverage=settings.leverage,
                commission_per_lot=settings.commission_per_lot,
                slippage_pips=settings.slippage_pips,
            )
        self.orders = OrderManager(self.broker, max_retries=settings.max_retries)
        self.trader = LiveTrader(
            settings, self.data, self.strategy, self.orders, self.risk,
            self.basket, self.journal, self.state, self.calendar,
            learner=self.learner,
        )
        self.state.update(ai_trades_learned=self.learner.state.trades_learned)
        self.seed_history()

    def seed_history(self, recent: int = 20) -> int:
        """Re-populate dashboard history/win-rate from the on-disk journal.

        Without this every restart shows an empty History tab even though
        ``logs/journal.*`` holds every realised trade.
        """
        closes = self.journal.read_closes()
        if not closes:
            return 0
        self.state.recent_trades = list(reversed(closes[-recent:]))
        wins = sum(1 for row in closes if row["profit"] > 0)
        self.state.update(
            total_trades=len(closes),
            winning_trades=wins,
            win_rate=100.0 * wins / len(closes),
        )
        return len(closes)

    def connect(self) -> bool:
        """Connect the venue and preload offline CSV data for paper mode."""
        if isinstance(self.broker, MT5Executor):
            ok = self.broker.connect()
            self.state.update(
                status_message="Live MT5 connected" if ok else "MT5 connection FAILED",
                running=False,
            )
            return ok
        assert isinstance(self.broker, PaperBroker)
        self.broker.connect()
        loaded = self._preload_csv_feeds()
        account = self.broker.account_info()
        if account is not None:
            self.state.update(balance=account.balance, equity=account.equity)
        self.state.update(status_message=(
            f"Paper ready ({loaded} offline feeds)" if loaded or not self._needs_data()
            else "Paper ready - waiting for data (connect MT5 or add data/*.csv)"
        ))
        return True

    def _needs_data(self) -> bool:
        """True when no pricing source is currently available."""
        if self.mt5.is_connected():
            return False
        return not any(
            self.data.has_offline(s, tf)
            for s in self.settings.symbol_list for tf in MTF_ORDER
        )

    def _preload_csv_feeds(self) -> int:
        """Load data/{SYMBOL}_{TF}.csv files into the offline feeds."""
        loaded = 0
        for symbol in self.settings.symbol_list:
            for timeframe in MTF_ORDER:
                path = os.path.join(self.settings.data_dir, f"{symbol}_{timeframe}.csv")
                if os.path.exists(path):
                    try:
                        if self.data.load_csv(symbol, timeframe, path) > 0:
                            loaded += 1
                    except Exception as exc:  # noqa: BLE001 - keep loading others
                        logger.warning("Could not load %s: %s", path, exc)
        if loaded:
            logger.info("Preloaded %d offline CSV feeds", loaded)
        return loaded

    async def run(self) -> None:
        """Connect and run the trading loop until stopped."""
        if not self.connect():
            raise RuntimeError("Could not connect to the trading venue")
        await self.trader.run_forever()

    def manual_close_all(self) -> dict:
        """Operator close-all (dashboard button / remote app)."""
        outcome = self.orders.close_all_verified()
        self.basket.reset()
        self.journal.record_basket("MANUAL_CLOSE", {
            "closed": outcome.closed, "failed": outcome.failed,
            "profit": round(outcome.total_profit, 2),
            "reason": "operator close-all",
        })
        if outcome.closed:
            self.trader.adopt_manual_close(
                outcome.total_profit, f"operator close-all ({outcome.closed} positions)")
        return {"requested": outcome.requested, "closed": outcome.closed,
                "failed": outcome.failed, "message": outcome.message}

    def start_remote_api(self) -> bool:
        """Start the token-protected remote API if enabled in settings."""
        if not self.settings.remote_api_enabled:
            return False
        try:
            from remote.api import build_app, start_in_thread

            app = build_app(
                self.state, self.settings.remote_api_token,
                on_close_all=self.manual_close_all,
                ai_summary=self.learner.summary,
            )
            start_in_thread(app, self.settings.remote_api_host, self.settings.remote_api_port)
            return True
        except Exception as exc:  # noqa: BLE001 - never block trading
            logger.error("Remote API not started: %s", exc)
            return False

    def shutdown(self) -> None:
        """Stop the loop and release venue resources."""
        self.state.update(running=False)
        self.learner.save()
        try:
            self.broker.shutdown()
        except Exception:  # noqa: BLE001
            pass
