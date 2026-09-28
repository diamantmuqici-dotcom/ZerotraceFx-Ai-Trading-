"""AI decision engine: weighted 0-100 confidence scoring with full reasoning."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from core.types import Direction, SignalAction
from utils.common import clamp

if TYPE_CHECKING:  # pragma: no cover
    from strategy.learning import AdaptiveLearner

DEFAULT_WEIGHTS: dict[str, float] = {
    "htf_trend": 18.0,
    "structure": 12.0,
    "bos": 10.0,
    "choch": 8.0,
    "ob_quality": 12.0,
    "fvg_quality": 8.0,
    "liquidity_sweep": 10.0,
    "volatility": 5.0,
    "session": 5.0,
    "spread": 5.0,
    "momentum": 7.0,
}

COMPONENT_LABELS = {
    "htf_trend": "Higher-TF trend",
    "structure": "Market structure",
    "bos": "Break of structure",
    "choch": "Change of character",
    "ob_quality": "Order block quality",
    "fvg_quality": "FVG quality",
    "liquidity_sweep": "Liquidity sweep",
    "volatility": "ATR volatility regime",
    "session": "Session strength",
    "spread": "Spread quality",
    "momentum": "Momentum",
}


@dataclass
class AIFeatures:
    """Normalised 0-100 input features for one candidate direction."""

    direction: Direction = Direction.NEUTRAL
    htf_trend: float = 0.0
    structure: float = 0.0
    bos: float = 0.0
    choch: float = 0.0
    ob_quality: float = 0.0
    fvg_quality: float = 0.0
    liquidity_sweep: float = 0.0
    volatility: float = 0.0
    session: float = 0.0
    spread: float = 0.0
    momentum: float = 0.0

    def as_dict(self) -> dict[str, float]:
        """Feature values keyed by component name."""
        return {
            "htf_trend": self.htf_trend, "structure": self.structure,
            "bos": self.bos, "choch": self.choch, "ob_quality": self.ob_quality,
            "fvg_quality": self.fvg_quality, "liquidity_sweep": self.liquidity_sweep,
            "volatility": self.volatility, "session": self.session,
            "spread": self.spread, "momentum": self.momentum,
        }


@dataclass
class AIDecision:
    """Scored decision with per-component contributions and reasoning."""

    action: SignalAction
    direction: Direction
    confidence: float
    components: dict[str, float] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    reasoning: list[str] = field(default_factory=list)
    passed: bool = False
    threshold: float = 85.0


class AIDecisionEngine:
    """Pure weighted scorer: features in, audited decision out."""

    def __init__(
        self, weights: dict[str, float] | None = None, threshold: float = 85.0,
        learner: "Optional[AdaptiveLearner]" = None,
    ) -> None:
        """Configure component weights and the execution threshold."""
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        total = sum(self.weights.values())
        if total <= 0:
            raise ValueError("AI weights must sum to a positive value")
        # Normalise so custom weight sets still produce a 0-100 score.
        self.weights = {k: v / total * 100.0 for k, v in self.weights.items()}
        self.threshold = threshold
        self.learner = learner

    def score(
        self, features: AIFeatures, symbol: Optional[str] = None,
        session: Optional[str] = None,
    ) -> AIDecision:
        """Score one candidate direction and explain every contribution.

        When an AdaptiveLearner is attached, learned weight multipliers,
        per-symbol threshold calibration and session edge are applied.
        """
        values = features.as_dict()
        weights = self.learner.adjusted_weights(self.weights) if self.learner else self.weights
        threshold = self.threshold
        if self.learner is not None:
            threshold = clamp(threshold + self.learner.threshold_offset(symbol), 50.0, 99.0)
        contributions: dict[str, float] = {}
        reasoning: list[str] = []
        total = 0.0
        for name, weight in weights.items():
            value = clamp(float(values.get(name, 0.0)), 0.0, 100.0)
            part = value * weight / 100.0
            contributions[name] = round(part, 2)
            total += part
            label = COMPONENT_LABELS.get(name, name)
            reasoning.append(f"{label}: {value:.0f}/100 x {weight:.1f}% = +{part:.1f}")
        if self.learner is not None:
            session_adj = self.learner.session_adjustment(session)
            if session_adj:
                total += session_adj
                reasoning.append(f"Learned session edge ({session}): {session_adj:+.1f}")
            if threshold != self.threshold:
                reasoning.append(
                    f"Learned threshold for {symbol}: {self.threshold:.0f} -> {threshold:.1f}")
        confidence = round(clamp(total, 0.0, 100.0), 2)
        if features.direction is Direction.BULLISH:
            action = SignalAction.BUY
        elif features.direction is Direction.BEARISH:
            action = SignalAction.SELL
        else:
            action = SignalAction.HOLD
        passed = action is not SignalAction.HOLD and confidence >= threshold
        verdict = "PASS" if passed else "REJECT"
        reasoning.append(
            f"Total confidence {confidence:.1f} vs threshold {threshold:.1f} -> {verdict}"
        )
        decision = AIDecision(
            action=action, direction=features.direction, confidence=confidence,
            components={k: round(clamp(float(v), 0, 100), 1) for k, v in values.items()},
            contributions=contributions, reasoning=reasoning,
            passed=passed, threshold=threshold,
        )
        if self.learner is not None and action is not SignalAction.HOLD:
            self.learner.note_inspection(passed)
        return decision
