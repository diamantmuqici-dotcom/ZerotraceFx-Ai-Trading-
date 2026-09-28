"""Liquidity mapping: equal highs/lows pools and wick-rejection sweeps."""
from __future__ import annotations

import pandas as pd

from core.types import Direction, EqualPool, LiquiditySweep, SwingPoint
from market.indicators import atr as atr_series


def detect_equal_pools(
    swings: list[SwingPoint],
    timeframe: str = "",
    tolerance_atr: float = 0.25,
    atr_ref: float = 0.0,
) -> tuple[list[EqualPool], list[EqualPool]]:
    """Cluster swing highs/lows within tolerance into liquidity pools."""
    highs = sorted([s for s in swings if s.kind == "HIGH"], key=lambda s: s.price)
    lows = sorted([s for s in swings if s.kind == "LOW"], key=lambda s: s.price)
    tolerance = max(1e-12, tolerance_atr * atr_ref)

    def _cluster(points: list[SwingPoint], kind: str) -> list[EqualPool]:
        pools: list[EqualPool] = []
        cluster: list[SwingPoint] = []
        for point in points:
            if not cluster or abs(point.price - cluster[-1].price) <= tolerance:
                cluster.append(point)
            else:
                if len(cluster) >= 2:
                    pools.append(EqualPool(
                        kind=kind,
                        price=round(sum(p.price for p in cluster) / len(cluster), 8),
                        count=len(cluster),
                        timeframe=timeframe,
                        times=[p.time for p in cluster],
                    ))
                cluster = [point]
        if len(cluster) >= 2:
            pools.append(EqualPool(
                kind=kind,
                price=round(sum(p.price for p in cluster) / len(cluster), 8),
                count=len(cluster),
                timeframe=timeframe,
                times=[p.time for p in cluster],
            ))
        return pools

    return _cluster(highs, "HIGH"), _cluster(lows, "LOW")


def detect_liquidity_sweeps(
    df: pd.DataFrame,
    swings: list[SwingPoint],
    timeframe: str = "",
    max_hunt_bars: int = 60,
) -> list[LiquiditySweep]:
    """Find wicks beyond swing levels that close back inside (stop hunts)."""
    if df is None or df.empty or not swings:
        return []
    n = len(df)
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    closes = df["close"].astype(float).to_numpy()
    times = pd.to_datetime(df["time"], utc=True)
    atr_vals = atr_series(df).fillna(0.0).to_numpy()
    sweeps: list[LiquiditySweep] = []
    for swing in sorted(swings, key=lambda s: s.index):
        level = swing.price
        horizon = min(n, swing.index + 1 + max_hunt_bars)
        for j in range(swing.index + 1, horizon):
            atr_now = float(atr_vals[j]) if j < len(atr_vals) else 0.0
            if swing.kind == "HIGH":
                if float(highs[j]) > level and float(closes[j]) < level:
                    wick = float(highs[j]) - level
                    sweeps.append(LiquiditySweep(
                        time=times.iloc[j].to_pydatetime(), index=j,
                        side="HIGH", swept_level=level,
                        wick_price=float(highs[j]), close_price=float(closes[j]),
                        timeframe=timeframe,
                        displacement=_has_displacement(closes, lows, j, direction=-1, atr_ref=atr_now),
                        bias=Direction.BEARISH,
                        strength=round(min(100.0, (wick / atr_now * 40.0) if atr_now > 0 else 20.0), 1),
                    ))
                    break  # level consumed; hunt the next swing
            else:
                if float(lows[j]) < level and float(closes[j]) > level:
                    wick = level - float(lows[j])
                    sweeps.append(LiquiditySweep(
                        time=times.iloc[j].to_pydatetime(), index=j,
                        side="LOW", swept_level=level,
                        wick_price=float(lows[j]), close_price=float(closes[j]),
                        timeframe=timeframe,
                        displacement=_has_displacement(closes, highs, j, direction=1, atr_ref=atr_now),
                        bias=Direction.BULLISH,
                        strength=round(min(100.0, (wick / atr_now * 40.0) if atr_now > 0 else 20.0), 1),
                    ))
                    break
    # Bonus strength for sweeps followed by displacement.
    for sweep in sweeps:
        if sweep.displacement:
            sweep.strength = round(min(100.0, sweep.strength + 25.0), 1)
    sweeps.sort(key=lambda s: s.index)
    return sweeps


def _has_displacement(
    closes: "object", extremes: "object", index: int, direction: int, atr_ref: float
) -> bool:
    """True when price expands >=0.5 ATR in the bias direction within 3 bars."""
    import numpy as np  # local import keeps module import-light

    close_arr = np.asarray(closes, dtype=float)
    if index + 1 >= len(close_arr) or atr_ref <= 0:
        return False
    anchor = float(close_arr[index])
    for k in range(index + 1, min(len(close_arr), index + 4)):
        move = (float(close_arr[k]) - anchor) * direction
        if move >= 0.5 * atr_ref:
            return True
    return False
