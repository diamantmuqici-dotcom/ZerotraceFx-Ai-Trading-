"""Trend facade over the multi-timeframe SMC output."""
from core.types import Direction, MTFAnalysis
from strategy.confluence import evaluate_mtf_confluence


def resolve(mtf: MTFAnalysis) -> Direction:
    return evaluate_mtf_confluence(mtf).direction
