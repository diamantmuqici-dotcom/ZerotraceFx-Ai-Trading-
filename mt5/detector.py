"""Venue/session discovery with explicit authentication boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.process_detector import SessionDiscovery, discover_sessions


class VenueStatus(str, Enum):
    """Operator-visible venue state."""

    WAITING = "waiting"
    DESKTOP_DETECTED = "desktop_detected"
    WEB_DETECTED = "web_detected"
    CONNECTED_REAL = "connected_real"
    REJECTED_NON_REAL = "rejected_non_real"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class VenueSnapshot:
    """Safe discovery snapshot; no credential fields are present."""

    status: VenueStatus
    message: str
    discovery: SessionDiscovery
    terminal_build: int | None = None
    account_login: int | None = None
    is_real_account: bool = False


class MT5SessionDetector:
    """Detect an already authenticated MT5 session without logging in.

    ``MT5Client`` owns the official API connection. This class only translates
    process/API observations into a UI-friendly status and deliberately avoids
    browser automation, memory inspection, password handling, and auto-login.
    """

    def __init__(self, client: Any) -> None:
        self.client = client

    def snapshot(self) -> VenueSnapshot:
        discovery = discover_sessions()
        if not discovery.any_terminal_present:
            return VenueSnapshot(VenueStatus.WAITING, "Waiting for authenticated MT5 session...", discovery)

        info = self.client.terminal_info()
        account = self.client.raw_account_info()
        if info is not None and account is not None:
            trade_mode = int(getattr(account, "trade_mode", -1))
            # MetaTrader5.TRADE_MODE_REAL is 0. Keep the numeric fallback so
            # this remains testable without importing the Windows-only package.
            if trade_mode == 0:
                return VenueSnapshot(
                    VenueStatus.CONNECTED_REAL,
                    "Authenticated real MT5 desktop session connected",
                    discovery,
                    terminal_build=int(getattr(info, "build", 0) or 0),
                    account_login=int(getattr(account, "login", 0) or 0),
                    is_real_account=True,
                )
            return VenueSnapshot(
                VenueStatus.REJECTED_NON_REAL,
                "MT5 session detected, but the account is not a real-money account",
                discovery,
                terminal_build=int(getattr(info, "build", 0) or 0),
                account_login=int(getattr(account, "login", 0) or 0),
            )

        if discovery.web_running and not discovery.desktop_running:
            return VenueSnapshot(
                VenueStatus.WEB_DETECTED,
                "MT5 Web terminal detected; waiting for an official authenticated trading connection",
                discovery,
            )
        return VenueSnapshot(
            VenueStatus.DESKTOP_DETECTED,
            "MT5 desktop detected; waiting for authenticated real account",
            discovery,
        )
