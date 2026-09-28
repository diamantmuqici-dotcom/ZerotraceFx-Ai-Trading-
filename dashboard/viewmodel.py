"""Dashboard view-model: exposes engine state snapshots to the Qt UI."""
from __future__ import annotations

from typing import Any, Callable, Optional

from core.state import RuntimeState


class DashboardViewModel:
    """Thin read-model over RuntimeState plus engine control callbacks."""

    def __init__(
        self,
        state: RuntimeState,
        on_pause: Optional[Callable[[bool], None]] = None,
        on_close_all: Optional[Callable[[], dict[str, Any]]] = None,
        on_reset_kill: Optional[Callable[[], None]] = None,
    ) -> None:
        """Bind the shared state and optional control callbacks."""
        self.state = state
        self._on_pause = on_pause
        self._on_close_all = on_close_all
        self._on_reset_kill = on_reset_kill

    def snapshot(self) -> dict[str, Any]:
        """Current UI snapshot."""
        return self.state.snapshot()

    def set_paused(self, paused: bool) -> None:
        """Pause or resume new entries."""
        self.state.update(paused=paused)
        if self._on_pause:
            self._on_pause(paused)

    def close_all(self) -> dict[str, Any]:
        """Request an immediate close-all; returns the outcome dict."""
        if self._on_close_all:
            return self._on_close_all()
        return {"requested": 0, "closed": 0, "message": "no handler bound"}

    def reset_kill_switch(self) -> None:
        """Clear a latched kill switch after operator review."""
        self.state.update(kill_switch=False)
        if self._on_reset_kill:
            self._on_reset_kill()
