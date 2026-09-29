"""Confidence scoring facade."""
from strategy.ai_engine import DEFAULT_WEIGHTS, AIDecisionEngine


def score(features, threshold: float = 85.0):
    return AIDecisionEngine(threshold=threshold).score(features)
