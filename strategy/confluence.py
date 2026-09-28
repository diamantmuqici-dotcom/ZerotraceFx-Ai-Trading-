"""Multi-timeframe confluence: alignment scoring across D1/H4/H1/M15/M5."""
from __future__ import annotations

from dataclasses import dataclass, field

from config.constants import MIN_BARS_MACRO_TF
from core.types import Direction, MTFAnalysis


@dataclass
class ConfluenceResult:
    """Outcome of the multi-timeframe alignment check."""

    aligned: bool = False
    direction: Direction = Direction.NEUTRAL
    score: float = 0.0  # 0-100 alignment score
    htf_bias: Direction = Direction.NEUTRAL
    details: list[str] = field(default_factory=list)
    fallback_used: bool = False


def effective_bias(mtf: MTFAnalysis, timeframe: str) -> tuple[Direction, bool]:
    """Bias for a timeframe with graceful fallback when history is thin.

    A higher timeframe with fewer than MIN_BARS_MACRO_TF bars cannot produce
    reliable structure, so the next-lower timeframe's bias stands in. The
    second return value reports whether a fallback was applied.
    """
    chain = {"D1": ["D1", "H4", "H1"], "H4": ["H4", "H1", "M15"],
             "H1": ["H1", "M15"], "M15": ["M15"], "M5": ["M5"]}
    for depth, candidate in enumerate(chain.get(timeframe, [timeframe])):
        analysis = mtf.analyses.get(candidate)
        if analysis is None:
            continue
        macro = candidate in ("D1", "H4")
        if macro and analysis.bar_count < MIN_BARS_MACRO_TF:
            continue
        return analysis.bias, depth > 0
    analysis = mtf.analyses.get(timeframe)
    if analysis is not None:
        return analysis.bias, True
    return Direction.NEUTRAL, True


def evaluate_mtf_confluence(mtf: MTFAnalysis) -> ConfluenceResult:
    """Score D1/H4/H1/M15 agreement; aligned needs D1+H4+H1 in one direction."""
    result = ConfluenceResult()
    d1, fb_d1 = effective_bias(mtf, "D1")
    h4, fb_h4 = effective_bias(mtf, "H4")
    h1, _fb_h1 = effective_bias(mtf, "H1")
    m15_a = mtf.analyses.get("M15")
    m15 = m15_a.bias if m15_a else Direction.NEUTRAL
    result.fallback_used = fb_d1 or fb_h4
    result.details.append(f"D1={d1.value} H4={h4.value} H1={h1.value} M15={m15.value}")

    for direction in (Direction.BULLISH, Direction.BEARISH):
        score = 0.0
        if d1 is direction and h4 is direction:
            score += 55.0
            result.details.append(f"{direction.value}: D1+H4 agree (+55)")
        elif d1 is direction or h4 is direction:
            score += 25.0
            result.details.append(f"{direction.value}: one HTF agrees (+25)")
        if h1 is direction:
            score += 30.0
            result.details.append(f"{direction.value}: H1 structure agrees (+30)")
        if m15 is direction:
            score += 15.0
            result.details.append(f"{direction.value}: M15 confirms (+15)")
        if score > result.score:
            result.score = score
            result.direction = direction

    htf_dir = Direction.NEUTRAL
    if d1 is not Direction.NEUTRAL and d1 is h4:
        htf_dir = d1
    elif d1 is not Direction.NEUTRAL:
        htf_dir = d1
    elif h4 is not Direction.NEUTRAL:
        htf_dir = h4
    result.htf_bias = htf_dir
    result.aligned = (
        result.direction is not Direction.NEUTRAL
        and d1 is result.direction
        and h4 is result.direction
        and h1 is result.direction
    )
    if result.fallback_used:
        result.details.append("Macro-TF fallback applied (limited history)")
    result.details.append(
        f"Confluence {'ALIGNED ' + result.direction.value if result.aligned else 'not aligned'} "
        f"(score {result.score:.0f})"
    )
    return result
