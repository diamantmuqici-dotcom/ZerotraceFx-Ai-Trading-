"""Authenticated MetaTrader 5 venue adapters.

The desktop adapter uses the official MetaTrader5 Python package. Web
sessions are detected for operator visibility only; no browser automation or
credential bypass is used.
"""
from __future__ import annotations

from mt5.detector import MT5SessionDetector, VenueStatus

__all__ = ["MT5SessionDetector", "VenueStatus"]
