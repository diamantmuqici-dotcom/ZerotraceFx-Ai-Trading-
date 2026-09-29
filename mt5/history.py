"""Settled broker deal-history facade."""
from market.mt5_client import MT5Client


def position_profit(client: MT5Client, ticket: str):
    return client.position_deals_profit(ticket)
