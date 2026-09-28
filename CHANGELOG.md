# Changelog — ZeroTrace FX AI

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-28

First production release: the complete institutional Smart Money autonomous
Forex trading platform.

### Added

- **Smart Money Concepts engine**: fractal swings (internal + external),
  BOS/CHoCH structure tracking, order blocks with mitigation/invalidation,
  fair value gaps with fill tracking, liquidity sweeps, equal highs/lows,
  supply/demand zones and premium/discount dealing-range positioning.
- **Multi-timeframe stack**: D1 macro, H4 primary, H1 structure, M15 setup,
  M5 execution — entries require stacked confluence, never one timeframe.
- **AI decision engine**: 11-component weighted 0–100 confidence score with
  full per-component reasoning and a configurable execution threshold (85).
- **Institutional entry checklists** for BUY/SELL: HTF bias, BOS/CHoCH,
  discount/premium zones, liquidity sweep, FVG alignment, spread + news gates.
- **Multi-position basket system**: average entry, floating PnL, total lots,
  instant close-all at `BASKET_TARGET`, optional trailing-basket mode.
- **Risk management**: 1% dynamic sizing, ATR stops, min RR 1:2, break-even,
  trailing stop, partial TP, exposure caps, daily/weekly/drawdown limits,
  consecutive-loss lock, spread/latency filters, emergency kill switch.
- **News filter**: CSV + manual economic calendar with before/after blackout
  windows, impact threshold and per-symbol currency matching.
- **Session engine**: UTC session detection, killzones and activity scoring.
- **MT5 execution**: login/reconnect, market + pending orders, SL/TP modify,
  partial close, close-all with pending cancel, filling-mode detection,
  retry with backoff, verification and latency logging.
- **Market data engine**: async candles/ticks/spreads, OHLC validation,
  gap repair, timeframe resampling, offline CSV feeds.
- **Backtesting suite**: event-driven simulator reusing the live strategy,
  equity curve, win rate, profit factor, Sharpe/Sortino, expectancy,
  drawdown, monthly/yearly returns, Monte Carlo and walk-forward validation,
  PNG + optional interactive HTML charts.
- **Paper trading**: simulated broker with spreads, commission, slippage,
  margin checks and intrabar SL/TP through an identical interface.
- **Desktop dashboard**: dark PySide6 UI with balance/equity/basket cards,
  positions, equity curve, trade history, pause/close-all/kill-switch controls.
- **Configuration**: everything via `.env` (pydantic-settings), zero hardcoding.
- **Logging**: rotating app/trades/errors/execution/performance logs plus a
  JSONL + CSV trade journal recording every decision.
- **Build & release**: PyInstaller spec producing `ZeroTraceFXAI.exe`,
  app icon, GitHub Actions CI (Linux + Windows, Python 3.11/3.13) and an
  automated tag-triggered release workflow with release notes.
- **Tests**: ~100 unit/integration tests covering SMC, strategy, basket,
  risk, execution, paper, backtest, market data and configuration.
- **Docs**: README, installation, architecture, strategy and configuration
  guides, `.env.example`, MIT license.

### Security

- No credentials in source; MT5 login flows only through `.env`/environment.
- Kill switch defaults halt trading before damage compounds.
