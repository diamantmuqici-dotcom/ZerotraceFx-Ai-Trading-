"""Reconnect policy for the official desktop client."""
from __future__ import annotations

from market.mt5_client import MT5Client


def reconnect(client: MT5Client, attempts: int = 3, delay_seconds: float = 2.0) -> bool:
    return client.reconnect(attempts=attempts, delay_sec=delay_seconds)
