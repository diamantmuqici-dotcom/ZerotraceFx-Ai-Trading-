"""Open-position queries from the official terminal."""
from market.mt5_client import MT5Client


def open_positions(client: MT5Client, symbol: str | None = None):
    return client.open_positions(symbol)
