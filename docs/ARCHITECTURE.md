# Architecture — ZeroTrace FX AI 2.0.0

## Production boundary

The only released execution path is:

```text
Electron / PySide dashboard → RuntimeState → LiveTrader
      → OrderManager → MT5Executor → official MetaTrader5 API
```

`MT5Client` calls `initialize` only. It does not accept or store a login,
server or password and never calls `mt5.login`. The operator authenticates MT5
Desktop separately. The engine validates `account.trade_mode == REAL` before
allowing a connection.

When no authenticated real session is available, the engine remains safe and
reports **Waiting for authenticated MT5 session...**. Browser process detection
is informational only because MT5 Web has no supported Python order API.

## Components

- `core/` — composition root, immutable-safe runtime state, event bus,
  diagnostics and non-invasive process discovery.
- `market/` — closed-bar MT5 data, ticks, indicators, sessions and news gates.
- `smart_money/` — swings, structure, liquidity, order blocks, FVGs and zones.
- `strategy/` — MTF confluence, explainable scoring and signal construction.
- `risk/` — sizing, exposure, daily/weekly/drawdown and basket controls.
- `execution/` — official MT5 order adapter with spread checks, retries and
  verification.
- `live/` — real-time cycle, broker-side close reconciliation and journal.
- `database/` — WAL SQLite store for shared local settings, audit events,
  watchlists, themes and backup.
- `remote/` — bearer-token API used by the Android companion and Electron main
  process. It never accepts MT5 credentials.
- `electron/`, `ui/`, `css/`, `js/` — sandboxed workstation shell and
  responsive CSS-variable terminal.
- `android/` — remote monitor/control companion; the Python engine stays on
  the authenticated Windows host.

## Data integrity

Only completed MT5 candles are passed into the strategy. The forming candle is
removed in `MT5Client.copy_rates`, preventing a live decision from using data
that can still change. Position outcomes are reconciled from broker history so
SL/TP closes reach risk counters, learning memory and the persistent journal.
