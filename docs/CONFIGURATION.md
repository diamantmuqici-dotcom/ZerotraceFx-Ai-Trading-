# Configuration — every knob lives in `.env`

Copy `.env.example` to `.env`. Nothing trading-related is hardcoded.

## Account & venues

| Key | Default | Meaning |
|---|---|---|
| `ACCOUNT_MODE` | `PAPER` | `PAPER` \| `LIVE` \| `BACKTEST` |
| `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` | — | Live terminal credentials |
| `MT5_PATH` | — | Optional `terminal64.exe` path |
| `SYMBOLS` | `XAUUSD,EURUSD,GBPUSD,USDJPY` | Any symbols; architecture is unlimited |
| `MAGIC_NUMBER` | `240901` | Order magic for live trades |

## AI & strategy

| Key | Default | Meaning |
|---|---|---|
| `CONFIDENCE_THRESHOLD` | `85` | Minimum AI score to execute |
| `ATR_PERIOD` / `ATR_SL_MULT` / `MIN_RR` | `14` / `1.5` / `2.0` | Volatility stop + minimum RR |
| `SWING_LEFT` / `SWING_RIGHT` | `3` / `3` | Fractal confirmation bars |
| `STRUCTURE_LOOKBACK` / `STRUCTURE_RECENCY_BARS` | `50` / `30` | BOS/CHoCH memory |
| `FVG_MIN_SIZE_ATR` | `0.05` | Smallest tradeable gap |
| `EQ_TOLERANCE_ATR` | `0.25` | Equal-high/low clustering band |
| `OB_LOOKBACK` / `OB_DISPLACEMENT_MULT` | `120` / `1.0` | OB scan window / impulse size |
| `SWEEP_RECENCY_BARS` / `FVG_PROXIMITY_ATR` | `30` / `1.5` | Sweep memory / zone proximity |

## Risk

| Key | Default | Meaning |
|---|---|---|
| `RISK_PERCENT` | `1.0` | % of balance risked per trade |
| `MAX_POSITIONS` / `MAX_TOTAL_LOTS` | `8` / `5.0` | Exposure caps |
| `MAX_DAILY_LOSS_PCT` / `MAX_WEEKLY_LOSS_PCT` / `MAX_DRAWDOWN_PCT` | `3` / `6` / `10` | Kill-switch trip levels |
| `MAX_CONSECUTIVE_LOSSES` | `4` | Loss-streak lock |
| `SPREAD_LIMIT_PIPS` / `SLIPPAGE_MAX_PIPS` / `LATENCY_MAX_MS` | `3.0` / `2.0` / `800` | Execution quality filters |
| `BREAK_EVEN_TRIGGER_RR` / `BREAK_EVEN_OFFSET_PIPS` | `1.0` / `2.0` | BE lock |
| `TRAILING_START_RR` / `TRAILING_STEP_PIPS` | `1.5` / `10.0` | Trailing stop |
| `PARTIAL_TP_ENABLED` / `PARTIAL_TP_RR` / `PARTIAL_TP_PCT` | `true` / `1.5` / `50` | Partial banking |

## Basket

| Key | Default | Meaning |
|---|---|---|
| `BASKET_TARGET` | `100.0` | Combined-profit target (account currency) |
| `BASKET_TRAILING_ENABLED` / `BASKET_TRAILING_PCT` | `false` / `15.0` | Trailing-basket mode + give-back % |

## News, sessions, costs, runtime

| Key | Default | Meaning |
|---|---|---|
| `NEWS_FILTER_ENABLED` / `NEWS_BEFORE_MIN` / `NEWS_AFTER_MIN` / `NEWS_MIN_IMPACT` | `true` / `30` / `30` / `HIGH` | Blackout window |
| `NEWS_CSV` | — | `title,currency,impact,time` calendar file |
| `SESSION_FILTER_ENABLED` / `ALLOWED_SESSIONS` | `false` / `London,NewYork` | Session gate |
| `COMMISSION_PER_LOT` / `SLIPPAGE_PIPS` | `7.0` / `0.5` | Paper/backtest realism |
| `PAPER_BALANCE` / `LEVERAGE` | `10000` / `100` | Simulated account |
| `POLL_INTERVAL_SEC` / `CANDLES_COUNT` / `MAX_RETRIES` | `5` / `500` / `3` | Loop tuning |
| `LOG_LEVEL` / `DATA_DIR` / `LOGS_DIR` / `REPORTS_DIR` | `INFO` / `data` / `logs` / `reports` | Runtime paths |
