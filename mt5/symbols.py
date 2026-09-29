"""Broker contract metadata facade."""
from market.mt5_client import MT5Client


def specification(client: MT5Client, symbol: str):
    return client.symbol_spec(symbol)
