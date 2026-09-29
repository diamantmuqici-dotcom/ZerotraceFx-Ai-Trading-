"""Web-terminal observation only; no unsupported browser order automation."""
from __future__ import annotations

from core.process_detector import discover_sessions


def status() -> str:
    discovery = discover_sessions()
    return "MT5 Web terminal detected" if discovery.web_running else "Waiting for authenticated MT5 session..."
