"""Structured application logger facade."""
from __future__ import annotations

import logging
from typing import Any

from utils.logging_setup import get_logger


def event_logger(name: str = "app") -> logging.Logger:
    return get_logger(name)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info("%s %s", event, " ".join(f"{key}={value}" for key, value in fields.items()))
