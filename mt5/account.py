"""Account information facade with no credential access."""
from market.mt5_client import MT5Client


def snapshot(client: MT5Client):
    return client.account_info()
