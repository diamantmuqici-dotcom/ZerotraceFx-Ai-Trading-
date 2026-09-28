"""Trading diagnostics — ``python main.py doctor``.

Answers the question "why isn't it trading?" by walking every gate between
the market and an order: venue/mode, MT5 connection and account type, symbol
data freshness, spread/news/session filters, the AI confidence verdict and
the risk-manager locks. Each line is printed as ``[ ok ] / [warn] / [FAIL]``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from config.settings import env_file_status
from core.types import MarketState
from market.filters import current_sessions, is_session_allowed, session_strength
from utils.common import utcnow

OK, WARN, FAIL = "OK", "WARN", "FAIL"
MARKS = {OK: "[ ok ]", WARN: "[warn]", FAIL: "[FAIL]"}
TRADE_MODES = {0: "REAL money", 1: "contest", 2: "DEMO money"}


@dataclass
class Check:
    """One diagnostic line."""

    area: str
    status: str
    detail: str


def _bar_age_minutes(last_bar: Any, now: datetime) -> float:
    when = last_bar.to_pydatetime() if hasattr(last_bar, "to_pydatetime") else last_bar
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (now - when).total_seconds() / 60.0)


async def collect(engine: Any) -> list[Check]:
    """Run every diagnostic against a constructed (and connected) engine."""
    checks: list[Check] = []
    settings = engine.settings
    now = utcnow()

    # --- config file ------------------------------------------------------
    env_status, env_path = env_file_status()
    if env_status == "misnamed":
        checks.append(Check("config", FAIL,
                            f"{os.path.basename(env_path or '.env.txt')} found but no "
                            ".env - Windows Notepad saved it with a .txt extension, so "
                            "the app never reads it. Rename the file to exactly `.env` "
                            "(no extension) next to main.py / ZeroTraceFXAI.exe."))
    elif env_status == "missing":
        checks.append(Check("config", FAIL,
                            "no .env found - the app is running on built-in defaults "
                            "(PAPER mode). Copy .env.example to .env next to main.py "
                            "(or ZeroTraceFXAI.exe) and set ACCOUNT_MODE=LIVE."))
    else:
        checks.append(Check("config", OK, f"config loaded from {env_path}"))

    # --- venue / mode ---------------------------------------------------
    if settings.mode == "LIVE":
        checks.append(Check("mode", OK,
                            "ACCOUNT_MODE=LIVE - orders route to the MetaTrader 5 terminal"))
    else:
        checks.append(Check("mode", FAIL,
                            f"ACCOUNT_MODE={settings.mode} - fills come from the internal "
                            "simulator; MT5 is never sent orders. Set ACCOUNT_MODE=LIVE in "
                            ".env to trade your MT5 account (demo or real)."))
    if settings.mode == "LIVE":
        if not engine.mt5.available:
            checks.append(Check("mt5", FAIL,
                                "MetaTrader5 python package not importable "
                                "(needs Windows + `pip install MetaTrader5`)"))
        elif not engine.mt5.is_connected():
            info = engine.mt5.terminal_info()
            if info is not None:
                checks.append(Check("mt5", WARN,
                                    f"terminal running (build {getattr(info, 'build', '?')}) "
                                    "but session not initialised - check MT5_LOGIN/MT5_SERVER"))
            elif engine.mt5.terminal_process_running():
                checks.append(Check("mt5", WARN,
                                    "terminal64.exe process is running but initialize() "
                                    "failed - restart MT5 or set MT5_PATH to terminal64.exe"))
            else:
                checks.append(Check("mt5", FAIL,
                                    "MetaTrader 5 terminal is NOT running - start it (or set "
                                    "MT5_PATH so initialize() can launch it), then retry"))
        else:
            raw = engine.mt5.raw_account_info()
            kind = TRADE_MODES.get(int(getattr(raw, "trade_mode", -1)), "unknown type")
            info = engine.mt5.terminal_info()
            build = getattr(info, "build", "?") if info is not None else "?"
            checks.append(Check("mt5", OK,
                                f"terminal running (build {build}) - login "
                                f"{getattr(raw, 'login', '?')} @ "
                                f"{getattr(raw, 'server', '?')} ({kind})"))
    else:
        checks.append(Check("mt5", WARN if engine.mt5.is_connected() else OK,
                            "prices: " + ("live MT5 ticks" if engine.mt5.is_connected()
                                          else "offline CSV feeds in data/")))

    # --- risk locks (global) ---------------------------------------------
    if engine.state.kill_switch or engine.risk.kill_switch:
        checks.append(Check("risk", FAIL,
                            f"kill switch latched: {engine.risk.kill_reason or 'manual'} "
                            "- reset from the dashboard"))
    if engine.state.paused:
        checks.append(Check("risk", WARN, "entries paused by operator"))
    if engine.risk.consecutive_losses >= settings.max_consecutive_losses:
        checks.append(Check("risk", FAIL,
                            f"consecutive-loss lock ({engine.risk.consecutive_losses}/"
                            f"{settings.max_consecutive_losses})"))
    open_positions = engine.broker.get_positions()
    if len(open_positions) >= settings.max_positions:
        checks.append(Check("risk", WARN,
                            f"max positions reached ({len(open_positions)}/"
                            f"{settings.max_positions})"))
    closes = engine.journal.read_closes()
    checks.append(Check("history", OK if closes else WARN,
                        f"{len(closes)} realised trade(s) in journal - the History tab "
                        "shows the latest 20 and survives restarts"
                        if closes else
                        "no closed trades journaled yet - History fills after the "
                        "first position closes"))

    # --- per symbol --------------------------------------------------------
    sessions = current_sessions(now)
    strength = session_strength(now)
    session_gate = (not settings.session_filter_enabled
                    or is_session_allowed(now, settings.allowed_session_list))
    if settings.session_filter_enabled and not session_gate:
        checks.append(Check("session", WARN,
                            f"outside allowed sessions ({settings.allowed_sessions}); "
                            f"now: {','.join(sessions) or 'off-session'}"))
    for symbol in settings.symbol_list:
        spec = engine.broker.symbol_spec(symbol)
        if spec is None:
            checks.append(Check(symbol, FAIL,
                                "no symbol spec - broker does not list it "
                                "(wrong suffix? e.g. EURUSD.pro / EURUSD.a)"))
            continue
        frame = await engine.data.get_candles(symbol, "M5", 200)
        if frame.empty:
            checks.append(Check(symbol, FAIL,
                                "no M5 bars - add it to Market Watch or drop a CSV "
                                f"in data/{symbol}_M5.csv"))
            continue
        source = "offline CSV (static history)" if engine.data.has_offline(symbol, "M5") \
            else "live MT5"
        age = _bar_age_minutes(frame["time"].iloc[-1], now)
        fresh = source.startswith("offline") or age <= 20
        checks.append(Check(symbol, OK if fresh else WARN,
                            f"{len(frame)} M5 bars from {source}, last bar "
                            f"{age:.0f} min old"))
        spread = await engine.data.get_spread_pips(symbol)
        spread_pips = spread if spread is not None else 999.0
        spread_ok = spread_pips <= settings.spread_limit_pips
        checks.append(Check(symbol, OK if spread_ok else WARN,
                            f"spread {spread_pips:.1f} pips vs limit "
                            f"{settings.spread_limit_pips:.1f}"))
        news_ok = (not settings.news_filter_enabled
                   or not engine.calendar.is_blocked(symbol, now))
        if not news_ok:
            checks.append(Check(symbol, WARN, "high-impact news blackout active"))
        market = MarketState(
            symbol=symbol, spread_pips=spread_pips, spread_ok=spread_ok,
            news_ok=news_ok, session=",".join(sessions) or "Off",
            session_strength=strength, timestamp=now,
        )
        try:
            signal = await engine.strategy.evaluate(symbol, engine.data, market, spec)
        except Exception as exc:  # noqa: BLE001 - report, never crash
            checks.append(Check(symbol, FAIL, f"strategy error: {exc}"))
            continue
        if signal.is_entry:
            checks.append(Check(symbol, OK,
                                f"ENTRY signal at confidence {signal.confidence:.1f} "
                                f"(threshold {settings.confidence_threshold:.0f})"))
        else:
            head = "; ".join(signal.reasoning[:2]) if signal.reasoning else "no setup"
            checks.append(Check(symbol, WARN,
                                f"no entry - confidence {signal.confidence:.1f} of "
                                f"{settings.confidence_threshold:.0f} required ({head})"))
    return checks


def render(checks: list[Check]) -> str:
    """Format checks as a readable console report."""
    width = max((len(c.area) for c in checks), default=8)
    lines = ["ZeroTrace FX AI - trading diagnostics",
             "=" * 47]
    for check in checks:
        lines.append(f"{MARKS[check.status]} {check.area:<{width}}  {check.detail}")
    failing = sum(1 for c in checks if c.status == FAIL)
    lines.append("-" * 47)
    lines.append(f"{failing} blocking issue(s); warnings are normal between setups."
                 if failing else
                 "No blockers - the engine is scanning; entries fire only at "
                 f"confidence >= the threshold (see CONFIDENCE_THRESHOLD).")
    return "\n".join(lines)
