# Installation — Windows 10/11

## 1. Prepare MetaTrader 5

1. Install MT5 Desktop from the broker or MetaQuotes.
2. Sign in to the intended **real-money** account inside MT5 yourself.
3. Confirm the broker permits algorithmic trading.
4. Leave the authenticated terminal running.

ZeroTrace does not request or store MT5 passwords and does not perform an
automatic login.

## 2. Install the Python engine

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
```

Review risk settings and keep `ACCOUNT_MODE=LIVE` and `REAL_ONLY=true`.

## 3. Start

```powershell
python main.py doctor
python main.py dashboard
# or
python main.py trade
```

If MT5 is not attached to an authenticated real account, the dashboard stays
safe and shows: `Waiting for authenticated MT5 session...`.

## 4. Electron workstation

Install Node.js 20+ and run:

```powershell
npm install
npm start
```

The Electron main process starts the Python API as a child process, keeps the
bearer token in memory, and exposes only a narrow context-isolated bridge to the
renderer.

## 5. Verification

```powershell
python -m compileall -q main.py core config market smart_money strategy execution risk live remote mt5 database
python -m pytest tests/ -q
npm run lint
```

The deterministic tests include strategy mathematics and broker-adapter
regressions. They are not available as production UI modes.
