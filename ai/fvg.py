"""Fair-value-gap facade."""
from smart_money.fvg import detect_fvgs, update_fvg

update_fvg_mitigation = update_fvg
__all__ = ["detect_fvgs", "update_fvg", "update_fvg_mitigation"]
