"""Safe public configuration projection; secrets are intentionally absent."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from config.settings import Settings


@dataclass(frozen=True)
class PublicConfig:
    mode: str
    symbols: tuple[str, ...]
    confidence_threshold: float
    risk_percent: float
    remote_api_enabled: bool


def public_config(settings: Settings) -> PublicConfig:
    return PublicConfig(settings.mode, tuple(settings.symbol_list), settings.confidence_threshold, settings.risk_percent, settings.remote_api_enabled)
