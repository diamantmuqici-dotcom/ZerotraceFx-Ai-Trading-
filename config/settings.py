"""Environment-driven application settings (pydantic-settings, `.env` file)."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All tunable behaviour of ZeroTrace FX AI. No hardcoded strategy values."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Account / mode ---
    account_mode: str = Field(default="PAPER", alias="ACCOUNT_MODE")
    mt5_login: int = Field(default=0, alias="MT5_LOGIN")
    mt5_password: str = Field(default="", alias="MT5_PASSWORD")
    mt5_server: str = Field(default="", alias="MT5_SERVER")
    mt5_path: str = Field(default="", alias="MT5_PATH")
    symbols: str = Field(default="XAUUSD,EURUSD,GBPUSD,USDJPY", alias="SYMBOLS")
    magic_number: int = Field(default=240901, alias="MAGIC_NUMBER")

    # --- AI / strategy ---
    confidence_threshold: float = Field(default=85.0, alias="CONFIDENCE_THRESHOLD")
    atr_period: int = Field(default=14, alias="ATR_PERIOD")
    atr_sl_mult: float = Field(default=1.5, alias="ATR_SL_MULT")
    min_rr: float = Field(default=2.0, alias="MIN_RR")
    swing_left: int = Field(default=3, alias="SWING_LEFT")
    swing_right: int = Field(default=3, alias="SWING_RIGHT")
    structure_lookback: int = Field(default=50, alias="STRUCTURE_LOOKBACK")
    structure_recency_bars: int = Field(default=30, alias="STRUCTURE_RECENCY_BARS")
    fvg_min_size_atr: float = Field(default=0.05, alias="FVG_MIN_SIZE_ATR")
    eq_tolerance_atr: float = Field(default=0.25, alias="EQ_TOLERANCE_ATR")
    ob_lookback: int = Field(default=120, alias="OB_LOOKBACK")
    ob_displacement_mult: float = Field(default=1.0, alias="OB_DISPLACEMENT_MULT")
    sweep_recency_bars: int = Field(default=30, alias="SWEEP_RECENCY_BARS")
    fvg_proximity_atr: float = Field(default=1.5, alias="FVG_PROXIMITY_ATR")

    # --- Remote API (Android companion app) ---
    remote_api_enabled: bool = Field(default=False, alias="REMOTE_API_ENABLED")
    remote_api_host: str = Field(default="0.0.0.0", alias="REMOTE_API_HOST")
    remote_api_port: int = Field(default=8765, alias="REMOTE_API_PORT")
    remote_api_token: str = Field(default="", alias="REMOTE_API_TOKEN")

    # --- Adaptive learning ---
    learning_enabled: bool = Field(default=True, alias="LEARNING_ENABLED")
    learning_rate: float = Field(default=0.05, alias="LEARNING_RATE")
    learning_memory_file: str = Field(default="ai_memory.json", alias="LEARNING_MEMORY_FILE")
    learning_min_trades: int = Field(default=5, alias="LEARNING_MIN_TRADES")

    # --- Risk ---
    risk_percent: float = Field(default=1.0, alias="RISK_PERCENT")
    max_positions: int = Field(default=8, alias="MAX_POSITIONS")
    max_total_lots: float = Field(default=5.0, alias="MAX_TOTAL_LOTS")
    max_daily_loss_pct: float = Field(default=3.0, alias="MAX_DAILY_LOSS_PCT")
    max_weekly_loss_pct: float = Field(default=6.0, alias="MAX_WEEKLY_LOSS_PCT")
    max_drawdown_pct: float = Field(default=10.0, alias="MAX_DRAWDOWN_PCT")
    max_consecutive_losses: int = Field(default=4, alias="MAX_CONSECUTIVE_LOSSES")
    spread_limit_pips: float = Field(default=3.0, alias="SPREAD_LIMIT_PIPS")
    slippage_max_pips: float = Field(default=2.0, alias="SLIPPAGE_MAX_PIPS")
    latency_max_ms: float = Field(default=800.0, alias="LATENCY_MAX_MS")
    break_even_trigger_rr: float = Field(default=1.0, alias="BREAK_EVEN_TRIGGER_RR")
    break_even_offset_pips: float = Field(default=2.0, alias="BREAK_EVEN_OFFSET_PIPS")
    trailing_start_rr: float = Field(default=1.5, alias="TRAILING_START_RR")
    trailing_step_pips: float = Field(default=10.0, alias="TRAILING_STEP_PIPS")
    partial_tp_enabled: bool = Field(default=True, alias="PARTIAL_TP_ENABLED")
    partial_tp_rr: float = Field(default=1.5, alias="PARTIAL_TP_RR")
    partial_tp_pct: float = Field(default=50.0, alias="PARTIAL_TP_PCT")

    # --- Basket ---
    basket_target: float = Field(default=100.0, alias="BASKET_TARGET")
    basket_trailing_enabled: bool = Field(default=False, alias="BASKET_TRAILING_ENABLED")
    basket_trailing_pct: float = Field(default=15.0, alias="BASKET_TRAILING_PCT")

    # --- News / sessions ---
    news_filter_enabled: bool = Field(default=True, alias="NEWS_FILTER_ENABLED")
    news_before_min: int = Field(default=30, alias="NEWS_BEFORE_MIN")
    news_after_min: int = Field(default=30, alias="NEWS_AFTER_MIN")
    news_min_impact: str = Field(default="HIGH", alias="NEWS_MIN_IMPACT")
    news_csv: str = Field(default="", alias="NEWS_CSV")
    session_filter_enabled: bool = Field(default=False, alias="SESSION_FILTER_ENABLED")
    allowed_sessions: str = Field(default="London,NewYork", alias="ALLOWED_SESSIONS")

    # --- Costs / paper ---
    commission_per_lot: float = Field(default=7.0, alias="COMMISSION_PER_LOT")
    slippage_pips: float = Field(default=0.5, alias="SLIPPAGE_PIPS")
    paper_balance: float = Field(default=10000.0, alias="PAPER_BALANCE")
    leverage: int = Field(default=100, alias="LEVERAGE")

    # --- Runtime ---
    poll_interval_sec: int = Field(default=5, alias="POLL_INTERVAL_SEC")
    candles_count: int = Field(default=500, alias="CANDLES_COUNT")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    data_dir: str = Field(default="data", alias="DATA_DIR")
    logs_dir: str = Field(default="logs", alias="LOGS_DIR")
    reports_dir: str = Field(default="reports", alias="REPORTS_DIR")

    @property
    def symbol_list(self) -> list[str]:
        """Configured symbols as a cleaned upper-case list."""
        return [s.strip().upper() for s in self.symbols.split(",") if s.strip()]

    @property
    def allowed_session_list(self) -> list[str]:
        """Configured allowed sessions as a cleaned list."""
        return [s.strip() for s in self.allowed_sessions.split(",") if s.strip()]

    @property
    def mode(self) -> str:
        """Normalised account mode (PAPER/LIVE/BACKTEST)."""
        return self.account_mode.strip().upper()

    @property
    def news_csv_path(self) -> Optional[str]:
        """News CSV path or None when not configured."""
        return self.news_csv.strip() or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process-wide settings instance."""
    return Settings()


def reset_settings() -> None:
    """Clear the cached settings (used by tests)."""
    get_settings.cache_clear()
