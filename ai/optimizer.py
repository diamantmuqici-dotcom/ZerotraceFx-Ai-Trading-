"""Bounded confidence-threshold optimizer from realised outcomes."""
from __future__ import annotations


def threshold(current: float, wins: int, losses: int) -> float:
    total = max(1, wins + losses); win_rate = wins / total
    adjustment = (win_rate - 0.5) * 4.0
    return max(50.0, min(99.0, current + adjustment))
