"""Asynchronous market-data services: candles, ticks, spreads and CSV feeds."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Optional

import pandas as pd

from config.constants import DEFAULT_SPREADS_PIPS
from core.types import MTF_ORDER, TickData
from market.indicators import repair_missing_bars, validate_ohlc
from market.mt5_client import MT5Client
from utils.common import pip_size, utcnow
from utils.logging_setup import get_logger

logger = get_logger("app")


class MarketDataEngine:
    """Unified async access to live MT5 data and offline (CSV/paper) feeds."""

    def __init__(
        self,
        mt5_client: Optional[MT5Client] = None,
        candles_count: int = 500,
    ) -> None:
        """Create the engine; offline feeds can be injected for tests/paper."""
        self.mt5 = mt5_client or MT5Client()
        self.candles_count = candles_count
        self._offline: dict[tuple[str, str], pd.DataFrame] = {}
        self._cache: dict[tuple[str, str], pd.DataFrame] = {}
        self._lock = asyncio.Lock()

    # -- offline feed management ----------------------------------------
    def set_offline(self, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
        """Inject an offline candle feed (used by paper mode, backtests, tests)."""
        self._offline[(symbol.upper(), timeframe.upper())] = validate_ohlc(df)

    def load_csv(self, symbol: str, timeframe: str, path: str) -> int:
        """Load an offline feed from CSV; returns the number of bars loaded."""
        if not os.path.exists(path):
            logger.warning("CSV data file not found: %s", path)
            return 0
        frame = pd.read_csv(path)
        if "time" not in frame.columns:
            raise ValueError(f"CSV {path} must contain a 'time' column")
        clean = validate_ohlc(frame)
        if clean.empty:
            return 0
        self.set_offline(symbol, timeframe, clean)
        return len(clean)

    def has_offline(self, symbol: str, timeframe: str) -> bool:
        """True when an offline feed exists for symbol/timeframe."""
        frame = self._offline.get((symbol.upper(), timeframe.upper()))
        return frame is not None and not frame.empty

    # -- async data access ----------------------------------------------
    async def get_candles(
        self, symbol: str, timeframe: str, count: Optional[int] = None
    ) -> pd.DataFrame:
        """Return the last N validated bars, preferring offline, then live MT5."""
        symbol = symbol.upper()
        timeframe = timeframe.upper()
        limit = count or self.candles_count
        key = (symbol, timeframe)
        offline = self._offline.get(key)
        if offline is not None and not offline.empty:
            repaired = repair_missing_bars(offline, timeframe)
            return repaired.tail(limit).reset_index(drop=True)
        if self.mt5.is_connected():
            frame = await asyncio.to_thread(
                self.mt5.copy_rates, symbol, timeframe, limit + 5
            )
            clean = validate_ohlc(frame)
            if not clean.empty:
                async with self._lock:
                    self._cache[key] = clean
                return repair_missing_bars(clean, timeframe).tail(limit).reset_index(drop=True)
        async with self._lock:
            cached = self._cache.get(key)
        if cached is not None and not cached.empty:
            return cached.tail(limit).reset_index(drop=True)
        return pd.DataFrame(columns=["time", "open", "high", "low", "close"])

    async def get_mtf_data(
        self, symbol: str, timeframes: Optional[list[str]] = None, count: Optional[int] = None
    ) -> dict[str, pd.DataFrame]:
        """Fetch all timeframe frames for a symbol concurrently."""
        frames = timeframes or list(MTF_ORDER)
        results = await asyncio.gather(
            *(self.get_candles(symbol, tf, count) for tf in frames)
        )
        return dict(zip(frames, results, strict=False))

    async def get_tick(self, symbol: str) -> Optional[TickData]:
        """Latest tick from MT5, else synthesised from the offline M5 close."""
        symbol = symbol.upper()
        if self.mt5.is_connected():
            tick = await asyncio.to_thread(self.mt5.current_tick, symbol)
            if tick is not None:
                return tick
        price = await self.get_latest_price(symbol)
        if price is None:
            return None
        bid, ask = price
        frame = self._offline.get((symbol, "M5"))
        when = frame["time"].iloc[-1].to_pydatetime() if frame is not None and not frame.empty else utcnow()
        if isinstance(when, datetime) and when.tzinfo is None:
            when = when.replace(tzinfo=None)
        return TickData(symbol=symbol, time=utcnow(), bid=bid, ask=ask)

    async def get_latest_price(self, symbol: str) -> Optional[tuple[float, float]]:
        """Latest (bid, ask); falls back to offline close +/- half spread."""
        symbol = symbol.upper()
        if self.mt5.is_connected():
            tick = await asyncio.to_thread(self.mt5.current_tick, symbol)
            if tick is not None:
                return (tick.bid, tick.ask)
        for tf in ("M5", "M15", "H1"):
            frame = self._offline.get((symbol, tf))
            if frame is not None and not frame.empty:
                close = float(frame["close"].iloc[-1])
                half = DEFAULT_SPREADS_PIPS.get(symbol, 2.0) * pip_size(symbol) / 2.0
                return (close - half, close + half)
        return None

    async def get_spread_pips(self, symbol: str) -> Optional[float]:
        """Current spread in pips, or None when no price is available."""
        price = await self.get_latest_price(symbol)
        if price is None:
            return None
        bid, ask = price
        return abs(ask - bid) / pip_size(symbol)
