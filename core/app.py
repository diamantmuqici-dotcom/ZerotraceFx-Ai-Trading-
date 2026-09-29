"""Application lifecycle service for desktop, Electron and headless hosts."""
from __future__ import annotations

from dataclasses import dataclass

from core.engine import ZeroTraceEngine


@dataclass
class ApplicationStatus:
    running: bool
    message: str
    mode: str


class TradingApplication:
    """Own one production engine and expose a small lifecycle contract."""

    def __init__(self, engine: ZeroTraceEngine) -> None:
        self.engine = engine

    def start(self) -> ApplicationStatus:
        self.engine.connect()
        return self.status()

    def stop(self) -> ApplicationStatus:
        self.engine.shutdown()
        return self.status()

    def status(self) -> ApplicationStatus:
        snapshot = self.engine.state.snapshot()
        return ApplicationStatus(bool(snapshot["running"]), str(snapshot["status_message"]), str(snapshot["mode"]))
