"""Adaptive learning memory: the AI improves from every trade it takes.

Every entry registers the feature vector that produced it. When the trade
closes (TP, SL, basket close, manual, backtest) the realised outcome is
converted into an R-multiple and used to:

1. **Re-weight components** — features that were strong on winners gain
   weight, features that were strong on losers lose weight (bounded online
   multiplicative update, so the engine can never drift to extremes).
2. **Calibrate confidence per symbol** — an exponentially-weighted win rate
   and expectancy per symbol nudge that symbol's execution threshold up
   (stricter after losses) or down (slightly looser after proven edge).
3. **Remember session edge** — per-session expectancy is tracked and exposed
   as a small score adjustment.

Rejected/inspected signals are counted too, so the memory reports how
selective the engine is. All state persists to ``logs/ai_memory.json`` and is
reloaded on start, so learning accumulates across runs.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from utils.common import clamp
from utils.logging_setup import get_logger

logger = get_logger("app")

MEMORY_VERSION = 1


@dataclass
class SymbolStats:
    """Rolling performance memory for one symbol (or session)."""

    trades: int = 0
    wins: int = 0
    ew_winrate: float = 0.5
    ew_expectancy_r: float = 0.0
    total_r: float = 0.0

    def update(self, r_multiple: float, alpha: float) -> None:
        """Fold one realised outcome into the rolling statistics."""
        win = 1.0 if r_multiple > 0 else 0.0
        self.trades += 1
        self.wins += int(win)
        self.total_r = round(self.total_r + r_multiple, 4)
        self.ew_winrate = round((1 - alpha) * self.ew_winrate + alpha * win, 5)
        self.ew_expectancy_r = round(
            (1 - alpha) * self.ew_expectancy_r + alpha * r_multiple, 5)


@dataclass
class PendingTrade:
    """Features captured at entry, awaiting an outcome."""

    symbol: str
    direction: str
    confidence: float
    components: dict[str, float]
    risk_money: float = 0.0
    session: str = ""


@dataclass
class LearningState:
    """Serializable learner state."""

    version: int = MEMORY_VERSION
    multipliers: dict[str, float] = field(default_factory=dict)
    symbols: dict[str, SymbolStats] = field(default_factory=dict)
    sessions: dict[str, SymbolStats] = field(default_factory=dict)
    pending: dict[str, PendingTrade] = field(default_factory=dict)
    trades_learned: int = 0
    signals_inspected: int = 0
    signals_rejected: int = 0


class AdaptiveLearner:
    """Online learner shared by the AI engine, live trader and backtester."""

    def __init__(
        self,
        path: Optional[str] = None,
        learning_rate: float = 0.05,
        min_multiplier: float = 0.5,
        max_multiplier: float = 2.0,
        ew_alpha: float = 0.15,
        min_trades_for_calibration: int = 5,
        max_threshold_raise: float = 8.0,
        max_threshold_lower: float = 4.0,
        enabled: bool = True,
    ) -> None:
        """Load persisted memory (if any) and configure update rules."""
        self.path = path
        self.learning_rate = learning_rate
        self.min_multiplier = min_multiplier
        self.max_multiplier = max_multiplier
        self.ew_alpha = ew_alpha
        self.min_trades = min_trades_for_calibration
        self.max_raise = max_threshold_raise
        self.max_lower = max_threshold_lower
        self.enabled = enabled
        self._lock = threading.RLock()
        self.state = LearningState()
        if path:
            self.load()

    # -- persistence -------------------------------------------------------
    def load(self) -> None:
        """Load memory from disk; corrupt files are backed up and reset."""
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as fh:
                raw = json.load(fh)
            self.state = LearningState(
                version=int(raw.get("version", MEMORY_VERSION)),
                multipliers={k: float(v) for k, v in raw.get("multipliers", {}).items()},
                symbols={k: SymbolStats(**v) for k, v in raw.get("symbols", {}).items()},
                sessions={k: SymbolStats(**v) for k, v in raw.get("sessions", {}).items()},
                pending={k: PendingTrade(**v) for k, v in raw.get("pending", {}).items()},
                trades_learned=int(raw.get("trades_learned", 0)),
                signals_inspected=int(raw.get("signals_inspected", 0)),
                signals_rejected=int(raw.get("signals_rejected", 0)),
            )
            logger.info("AI memory loaded: %d trades learned", self.state.trades_learned)
        except Exception as exc:  # noqa: BLE001 - never crash on bad memory
            logger.warning("AI memory unreadable (%s); starting fresh", exc)
            try:
                os.replace(self.path, self.path + ".corrupt")
            except OSError:
                pass
            self.state = LearningState()

    def save(self) -> None:
        """Atomically persist memory to disk."""
        if not self.path:
            return
        with self._lock:
            payload = asdict(self.state)
            directory = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2)
                os.replace(tmp, self.path)
            except OSError as exc:
                logger.warning("Could not save AI memory: %s", exc)
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    # -- inference-time hooks ----------------------------------------------
    def multiplier(self, component: str) -> float:
        """Learned weight multiplier for a component (1.0 = untouched)."""
        return self.state.multipliers.get(component, 1.0)

    def adjusted_weights(self, base: dict[str, float]) -> dict[str, float]:
        """Base weights scaled by learned multipliers, re-normalised to 100."""
        if not self.enabled:
            return dict(base)
        scaled = {k: v * self.multiplier(k) for k, v in base.items()}
        total = sum(scaled.values()) or 1.0
        return {k: v / total * 100.0 for k, v in scaled.items()}

    def threshold_offset(self, symbol: Optional[str]) -> float:
        """Per-symbol threshold nudge from calibrated live results."""
        if not self.enabled or not symbol:
            return 0.0
        stats = self.state.symbols.get(symbol.upper())
        if stats is None or stats.trades < self.min_trades:
            return 0.0
        # Negative expectancy -> stricter; strong positive -> slightly looser.
        exp_r = stats.ew_expectancy_r
        if exp_r < 0:
            return round(clamp(-exp_r * 10.0, 0.0, self.max_raise), 2)
        return round(-clamp(exp_r * 4.0, 0.0, self.max_lower), 2)

    def session_adjustment(self, session: Optional[str]) -> float:
        """Small +/- score adjustment for sessions with proven edge."""
        if not self.enabled or not session:
            return 0.0
        stats = self.state.sessions.get(session)
        if stats is None or stats.trades < self.min_trades:
            return 0.0
        return round(clamp(stats.ew_expectancy_r * 3.0, -3.0, 3.0), 2)

    def note_inspection(self, passed: bool) -> None:
        """Count every scored candidate (called by the AI engine)."""
        with self._lock:
            self.state.signals_inspected += 1
            if not passed:
                self.state.signals_rejected += 1

    # -- training hooks ----------------------------------------------------
    def register_entry(
        self,
        key: str,
        symbol: str,
        direction: str,
        confidence: float,
        components: dict[str, float],
        risk_money: float = 0.0,
        session: str = "",
    ) -> None:
        """Remember the features behind an opened trade until it closes."""
        if not self.enabled or not key:
            return
        with self._lock:
            self.state.pending[str(key)] = PendingTrade(
                symbol=symbol.upper(), direction=direction,
                confidence=float(confidence),
                components={k: float(v) for k, v in components.items()},
                risk_money=abs(float(risk_money)), session=session,
            )
        self.save()

    def has_pending(self, key: str) -> bool:
        """True when an entry is awaiting its outcome."""
        return str(key) in self.state.pending

    def record_outcome(
        self,
        key: str,
        profit: float,
        r_multiple: Optional[float] = None,
        persist: bool = True,
    ) -> Optional[float]:
        """Learn from a closed trade; returns the R-multiple used (or None)."""
        if not self.enabled:
            return None
        with self._lock:
            pending = self.state.pending.pop(str(key), None)
            if pending is None:
                return None
            if r_multiple is None:
                if pending.risk_money > 0:
                    r_multiple = profit / pending.risk_money
                else:
                    r_multiple = 1.0 if profit > 0 else (-1.0 if profit < 0 else 0.0)
            r = clamp(float(r_multiple), -3.0, 5.0)
            self._update_weights(pending.components, r)
            self.state.symbols.setdefault(pending.symbol, SymbolStats()).update(r, self.ew_alpha)
            if pending.session:
                for sess in pending.session.split(","):
                    if sess and sess != "Off":
                        self.state.sessions.setdefault(sess, SymbolStats()).update(r, self.ew_alpha)
            self.state.trades_learned += 1
        logger.info("AI learned from %s %s: profit %+.2f (R=%+.2f)",
                    pending.symbol, pending.direction, profit, r)
        if persist:
            self.save()
        return r

    def _update_weights(self, components: dict[str, float], r: float) -> None:
        """Bounded multiplicative update: reward features present on winners."""
        signal = clamp(r, -2.0, 2.0) / 2.0  # -1 .. +1
        if signal == 0:
            return
        for name, value in components.items():
            # Centre the feature: strong (>50) features share credit/blame.
            centred = (clamp(value, 0.0, 100.0) - 50.0) / 50.0
            step = self.learning_rate * signal * centred
            current = self.multiplier(name)
            updated = clamp(current * (1.0 + step), self.min_multiplier, self.max_multiplier)
            self.state.multipliers[name] = round(updated, 5)

    # -- reporting ---------------------------------------------------------
    def summary(self) -> dict[str, Any]:
        """Human-friendly snapshot for the dashboard/CLI."""
        s = self.state
        return {
            "trades_learned": s.trades_learned,
            "signals_inspected": s.signals_inspected,
            "signals_rejected": s.signals_rejected,
            "pending": len(s.pending),
            "multipliers": dict(sorted(s.multipliers.items())),
            "symbols": {
                k: {"trades": v.trades, "winrate": round(v.wins / v.trades * 100, 1) if v.trades else 0.0,
                    "ew_expectancy_r": v.ew_expectancy_r,
                    "threshold_offset": self.threshold_offset(k)}
                for k, v in s.symbols.items()
            },
        }
