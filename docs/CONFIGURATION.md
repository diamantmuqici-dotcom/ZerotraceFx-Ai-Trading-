# Configuration

Copy `.env.example` to `.env` on the Windows host running the authenticated
MetaTrader 5 Desktop terminal.

## Execution and session

| Key | Default | Meaning |
|---|---|---|
| `ACCOUNT_MODE` | `LIVE` in the template | Production execution mode; only `LIVE` is permitted by the release entry points |
| `REAL_ONLY` | `true` | Safety boundary; production does not downgrade this flag |
| `MT5_PATH` | empty | Optional path to an already installed terminal; it is not a credential or auto-login path |
| `SYMBOLS` | `XAUUSD,EURUSD,GBPUSD,USDJPY` | Broker symbols to scan |
| `MAGIC_NUMBER` | `240901` | Order magic used by the official MT5 adapter |

`MT5_LOGIN`, `MT5_PASSWORD` and credential/server login settings are not part
of the supported configuration. The terminal must be authenticated by the
operator before ZeroTrace attaches to it.

## AI, risk and filters

The AI and risk parameters remain environment-driven: `CONFIDENCE_THRESHOLD`,
`ATR_PERIOD`, `ATR_SL_MULT`, `MIN_RR`, swing/structure/FVG/order-block settings,
`RISK_PERCENT`, `MAX_POSITIONS`, `MAX_TOTAL_LOTS`, daily/weekly/drawdown limits,
spread/slippage/latency guards, break-even/trailing/partial-close settings,
`BASKET_TARGET`, news settings and session settings.

`CANDLES_COUNT`, `POLL_INTERVAL_SEC`, `MAX_RETRIES`, `LOG_LEVEL`, `LOGS_DIR` and
`REPORTS_DIR` control runtime behaviour. `DATA_DIR` is retained for research
regression fixtures but is not loaded by a production engine.

## Local API

```dotenv
REMOTE_API_ENABLED=false
REMOTE_API_HOST=0.0.0.0
REMOTE_API_PORT=8765
REMOTE_API_TOKEN=<16+ random characters>
```

The bearer token is required for every request. Keep the API on a trusted LAN
or VPN and never port-forward it. The Electron shell uses a fresh in-memory
token for its local child process.

## Local memory

Adaptive learning, journal JSONL/CSV mirrors and the WAL SQLite database are
stored under `LOGS_DIR`. The database contains preferences and audit events,
not passwords or broker credentials.
