# ZeroTrace FX AI 2.0.0

**Authenticated real-mode MetaTrader 5 execution terminal**

ZeroTrace FX AI is an explainable Smart Money Concepts trading terminal for
Windows 10/11 with a Python execution engine, Electron workstation UI and
Android companion. The production application has one execution policy:
**real MT5 account only**.

## Non-negotiable safety boundary

- The application never asks for, stores or submits an MT5 password.
- It attaches to the MetaTrader 5 Desktop terminal already authenticated by
the operator through the official `MetaTrader5` Python API.
- It never injects memory, bypasses authentication or automates credentials.
- If an authenticated real terminal cannot be confirmed, the status is
  **Waiting for authenticated MT5 session...** and no order is sent.
- MT5 Web is detected for operator visibility. Because MetaQuotes does not
  provide a supported Python trading API for Web Terminal, browser detection
  does not authorise an order.
- The released CLI, Electron shell and Android control plane do not expose a
  paper, demo, offline-feed or simulated-order mode.

Trading leveraged products can result in losses exceeding expectations. Use
appropriate broker permissions, account safeguards and independent review.

## Architecture

```text
Electron renderer (ui + css + js)
          │ context-isolated IPC
Electron main process ── local authenticated API ── Python engine
                                                       │
              ┌────────────────────────────────────────┼──────────────┐
              │                                        │              │
       official MT5 client                    SMC / AI / risk    SQLite/journal
              │                                        │              │
       authenticated account                       MT5 orders     Android API
```

The existing strategy core remains modular: market data, SMC detection,
confluence, explainable confidence, risk limits, execution retries, journal
persistence and the Android control API are separate components. The new
Electron layer consumes the same `RuntimeState` snapshot as the native
fallback dashboard.

## Quick start on Windows

1. Install MetaTrader 5 Desktop and authenticate the **real** account in MT5.
2. Start it and enable the broker's algorithmic-trading permission.
3. Install Python 3.13 and the project dependencies:

   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   copy .env.example .env
   ```

4. Review `.env`. Keep `ACCOUNT_MODE=LIVE` and `REAL_ONLY=true`.
5. Launch the production terminal:

   ```powershell
   python main.py dashboard
   ```

   Or run headless:

   ```powershell
   python main.py trade
   ```

6. Diagnose terminal, symbol, spread, news and risk gates:

   ```powershell
   python main.py doctor
   ```

The Electron shell is available after installing Node.js dependencies:

```powershell
npm install
npm start
```

The shell starts `python main.py api` with an ephemeral local API token. The
token is held in process memory and is not written to disk.

## Android companion

The Android build is a monitor and control client for the Python engine. It
never handles MT5 authentication. Enable the token-protected remote API only
on a trusted LAN or VPN:

```dotenv
REMOTE_API_ENABLED=true
REMOTE_API_HOST=0.0.0.0
REMOTE_API_PORT=8765
REMOTE_API_TOKEN=<random value with at least 16 characters>
```

Build from the `android/` directory with Gradle 8.9 and Java 17. Do not
forward the API port to the public internet. See `docs/MOBILE.md`.

## UI

The Electron terminal includes:

- dashboard, live trades, journal, analytics, AI, risk, watchlist, calendar,
  settings, themes and about pages;
- ten CSS-variable themes: Dark Carbon, AMOLED Black, TradingView, Ice Blue,
  Emerald, Crimson, Gold, Purple, Cyber Green and Light Pro;
- responsive desktop/tablet/mobile layouts, reduced-motion support, GPU-safe
  transforms, skeleton-ready surfaces and keyboard command search;
- live MT5 account KPIs, positions, equity history, AI reasoning and a
  confirmation-protected close-all action;
- no fabricated candles, prices, fills or performance charts.

## Verification

```powershell
python -m compileall -q main.py core config ai market smart_money strategy execution risk live remote mt5 database
python -m pytest tests/ -q
npm run lint
```

The test suite contains deterministic research fixtures for mathematical
strategy and risk regression. Those fixtures are not runtime execution paths;
production launch always uses the real-only boundary described above.

## Releases

Versioned tags build the Windows bundle, standalone executable and Android
APK through GitHub Actions. Release metadata is kept in `CHANGELOG.md` and
the build workflows. A signed Android keystore can be supplied through the
`ZT_KEYSTORE*` CI secrets; without it, CI produces an explicitly unsigned
engineering APK.

## License

MIT — see [LICENSE](LICENSE).
