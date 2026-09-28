"""Async event bus for decoupled communication between engine components."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("zerotrace.events")


class Event(str, Enum):
    """Engine-wide event names."""

    TICK = "tick"
    NEW_BAR = "new_bar"
    SIGNAL = "signal"
    ORDER_PLACED = "order_placed"
    ORDER_CLOSED = "order_closed"
    BASKET_CLOSED = "basket_closed"
    RISK_BLOCK = "risk_block"
    KILL_SWITCH = "kill_switch"
    EQUITY_UPDATE = "equity_update"
    STATUS = "status"
    ERROR = "error"


Handler = Callable[[Event, dict[str, Any]], Awaitable[None]]


class EventBus:
    """Minimal async publish/subscribe bus with per-event handler lists."""

    def __init__(self) -> None:
        """Initialise an empty bus."""
        self._handlers: dict[Event, list[Handler]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, event: Event, handler: Handler) -> None:
        """Register an async handler for an event."""
        async with self._lock:
            self._handlers[event].append(handler)

    async def unsubscribe(self, event: Event, handler: Handler) -> None:
        """Remove a previously registered handler."""
        async with self._lock:
            if handler in self._handlers[event]:
                self._handlers[event].remove(handler)

    async def publish(self, event: Event, payload: Optional[dict[str, Any]] = None) -> None:
        """Publish an event to all registered handlers."""
        data = payload or {}
        async with self._lock:
            handlers = list(self._handlers.get(event, []))
        for handler in handlers:
            try:
                await handler(event, data)
            except Exception as exc:  # never let a handler kill the bus
                logger.exception("Event handler failed for %s: %s", event, exc)


_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Return the process-wide shared event bus (created on first use)."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
