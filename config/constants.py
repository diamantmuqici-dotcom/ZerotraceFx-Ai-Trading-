"""Application-wide constants and offline instrument defaults."""
from __future__ import annotations

APP_NAME = "ZeroTrace FX AI"
APP_VERSION = "1.2.0"
APP_TAGLINE = "Institutional Smart Money Autonomous Forex Trading Platform"
MAGIC_DEFAULT = 240901

DEFAULT_SYMBOLS: list[str] = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]

# Offline/paper fallback contract specs (live mode always uses broker specs).
# tick_value = account-currency profit of one tick move for 1.00 lot.
DEFAULT_SPECS: dict[str, dict[str, float]] = {
    "XAUUSD": {"tick_value": 1.0, "tick_size": 0.01, "point": 0.01, "digits": 2,
               "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "EURUSD": {"tick_value": 1.0, "tick_size": 0.00001, "point": 0.00001, "digits": 5,
               "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "GBPUSD": {"tick_value": 1.0, "tick_size": 0.00001, "point": 0.00001, "digits": 5,
               "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "USDJPY": {"tick_value": 0.68, "tick_size": 0.001, "point": 0.001, "digits": 3,
               "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
}

# Typical spreads in pips used by paper/backtest simulation.
DEFAULT_SPREADS_PIPS: dict[str, float] = {
    "XAUUSD": 3.5,
    "EURUSD": 1.2,
    "GBPUSD": 1.8,
    "USDJPY": 1.5,
}

# Trading sessions in UTC hours (start inclusive, end exclusive; may wrap).
SESSIONS_UTC: dict[str, tuple[int, int]] = {
    "Sydney": (21, 6),
    "Tokyo": (0, 8),
    "London": (7, 16),
    "NewYork": (12, 20),
}

# Institutional killzones in UTC hours.
KILLZONES_UTC: dict[str, tuple[int, int]] = {
    "London Killzone": (7, 10),
    "NewYork Killzone": (12, 15),
}

MIN_BARS_MACRO_TF = 30  # below this a higher TF falls back to the next-lower TF
