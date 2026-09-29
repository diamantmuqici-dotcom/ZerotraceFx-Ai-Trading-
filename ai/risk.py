"""AI risk feature facade; enforcement remains in ``risk.risk_manager``."""
from risk.position_sizing import lots_for_risk
from strategy.strategy import volatility_score

__all__ = ["lots_for_risk", "volatility_score"]
