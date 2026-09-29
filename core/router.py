"""Typed command routing shared by local control surfaces."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class CommandRouter:
    """Allow-list operator commands; unknown actions are rejected."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}

    def register(self, name: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        if not name or name.startswith("_"):
            raise ValueError("command names must be public")
        self._handlers[name] = handler

    def dispatch(self, name: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            handler = self._handlers[name]
        except KeyError as exc:
            raise ValueError(f"unsupported command: {name}") from exc
        return handler(payload or {})
