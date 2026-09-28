"""Candle-based technical calculations: ATR, momentum, resampling and repair."""
from __future__ import annotations

import pandas as pd

from core.types import TIMEFRAME_PANDAS

OHLC_COLUMNS = ["time", "open", "high", "low", "close"]


def validate_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Sort, de-duplicate and sanitise an OHLC frame; returns a clean copy."""
    if df is None or df.empty:
        return pd.DataFrame(columns=OHLC_COLUMNS)
    out = df.copy()
    out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
    out = out.dropna(subset=["time"]).sort_values("time").drop_duplicates("time")
    for col in ("open", "high", "low", "close"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return out


def true_range(df: pd.DataFrame) -> pd.Series:
    """Wilder true range series for an OHLC frame."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    prev_close = df["close"].astype(float).shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range with Wilder smoothing, aligned to the input index."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    tr = true_range(df)
    # Wilder's smoothing == EMA with alpha 1/period.
    return tr.ewm(alpha=1.0 / max(1, period), min_periods=1, adjust=False).mean()


def momentum_roc(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Rate-of-change momentum in percent over the lookback period."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    close = df["close"].astype(float)
    prev = close.shift(period)
    return ((close - prev) / prev.replace(0, float("nan"))) * 100.0


def candle_body(df: pd.DataFrame) -> pd.Series:
    """Signed candle body (close - open)."""
    return df["close"].astype(float) - df["open"].astype(float)


def candle_range(df: pd.DataFrame) -> pd.Series:
    """Full candle range (high - low)."""
    return df["high"].astype(float) - df["low"].astype(float)


def resample_ohlc(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample a lower-timeframe OHLC frame up to a higher timeframe."""
    clean = validate_ohlc(df)
    if clean.empty:
        return pd.DataFrame(columns=OHLC_COLUMNS)
    rule = TIMEFRAME_PANDAS.get(timeframe)
    if rule is None:
        raise ValueError(f"Unsupported timeframe for resample: {timeframe}")
    agg: dict[str, str] = {"open": "first", "high": "max", "low": "min", "close": "last"}
    vol_col = None
    for candidate in ("tick_volume", "volume", "real_volume"):
        if candidate in clean.columns:
            vol_col = candidate
            agg[candidate] = "sum"
            break
    if "spread" in clean.columns:
        agg["spread"] = "mean"
    resampled = (
        clean.set_index("time")
        .resample(rule, origin="start_day")
        .agg(agg)
        .dropna(subset=["open", "high", "low", "close"])
    )
    resampled = resampled.reset_index()
    if vol_col is None:
        resampled["tick_volume"] = 0
    return resampled


def repair_missing_bars(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Reindex to the expected bar grid and forward-fill weekend/data gaps."""
    clean = validate_ohlc(df)
    if clean.empty or len(clean) < 3:
        return clean
    rule = TIMEFRAME_PANDAS.get(timeframe)
    if rule is None:
        return clean
    full_index = pd.date_range(
        start=clean["time"].iloc[0], end=clean["time"].iloc[-1], freq=rule, tz="UTC"
    )
    if len(full_index) <= len(clean) + 1:
        return clean
    frame = clean.set_index("time").reindex(full_index)
    frame["close"] = frame["close"].ffill()
    for col in ("open", "high", "low"):
        frame[col] = frame[col].fillna(frame["close"])
    for col in ("tick_volume", "volume", "real_volume", "spread"):
        if col in frame.columns:
            frame[col] = frame[col].fillna(0)
    frame = frame.dropna(subset=["close"]).reset_index().rename(columns={"index": "time"})
    return frame


def atr_value(df: pd.DataFrame, period: int = 14) -> float:
    """Most recent ATR value, or 0.0 when unavailable."""
    series = atr(df, period)
    if series.empty:
        return 0.0
    value = series.iloc[-1]
    if pd.isna(value):
        return 0.0
    return float(value)


def atr_mean(df: pd.DataFrame, period: int = 14, window: int = 50) -> float:
    """Mean ATR over the trailing window (volatility regime reference)."""
    series = atr(df, period)
    if series.empty:
        return 0.0
    windowed = series.tail(max(1, window)).dropna()
    if windowed.empty:
        return 0.0
    return float(windowed.mean())


def momentum_value(df: pd.DataFrame, period: int = 14) -> float:
    """Most recent momentum ROC value in percent."""
    series = momentum_roc(df, period)
    if series.empty or pd.isna(series.iloc[-1]):
        return 0.0
    return float(series.iloc[-1])
