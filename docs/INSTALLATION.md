# Installation Guide — ZeroTrace FX AI v1.0.0

## Option A: Windows executable (recommended for live trading)

1. Download `ZeroTraceFXAI-v1.0.0-windows.zip` from the GitHub Releases page.
2. Extract it to a folder, e.g. `C:\ZeroTraceFXAI\`.
3. Copy `.env.example` to `.env` and edit your settings (see `docs/CONFIGURATION.md`).
4. Make sure MetaTrader 5 is installed and you are logged in (for LIVE; PAPER works standalone).
5. Double-click `ZeroTraceFXAI.exe` — the dashboard opens and the engine starts.

> The `.exe` is built from this exact source by the `Release` GitHub Actions workflow
> (`pyinstaller zerotrace.spec`, Python 3.13, Windows).

## Option B: Run from source (Windows 10/11, Python 3.13)

```powershell
# 1. Clone
git clone https://github.com/<you>/zerotrace-fx-ai.git
cd zerotrace-fx-ai

# 2. Virtual environment
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Dependencies (MetaTrader5 + PySide6 install automatically on Windows)
pip install -r requirements.txt

# 4. Configure
copy .env.example .env
notepad .env

# 5a. Launch the dashboard
python main.py dashboard

# 5b. Or run headless (PAPER/LIVE per .env)
python main.py trade

# 5c. Or run a backtest from CSV
python main.py backtest --symbol EURUSD --csv data/sample_EURUSD_M5.csv
```

## MetaTrader 5 setup (LIVE mode only)

1. In MT5: **Tools → Options → Expert Advisors** → enable *Allow Algo Trading*.
2. Add your account credentials to `.env` (`MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`).
3. Set `ACCOUNT_MODE=LIVE`.
4. Start with a **demo account** first. Verify fills, SL/TP and basket closes in PAPER mode before going live.

## Verifying your install

```powershell
python -m pytest tests/ -q   # full suite, ~100 tests, must be all green
python main.py version
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `MetaTrader5 package unavailable` | Normal on Linux/macOS; install on Windows or use PAPER/BACKTEST |
| Dashboard will not start | `pip install PySide6 matplotlib` (Windows) |
| `No price yet for symbol` in paper | Connect MT5 or add `data/{SYMBOL}_{TF}.csv` feeds |
| Kill switch latched | Review the reason in the dashboard, then *Reset Kill Switch* |
| `ModuleNotFoundError` | Run from the repo root so `main.py` sets `sys.path` |
