"""Enterprise logging: rotating file loggers per concern plus console output."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

_LOGGERS: dict[str, logging.Logger] = {}
_INITIALISED = False

LOG_FILES = {
    "app": "app.log",
    "trades": "trades.log",
    "errors": "errors.log",
    "execution": "execution.log",
    "performance": "performance.log",
}


def setup_logging(logs_dir: str = "logs", level: str = "INFO") -> dict[str, logging.Logger]:
    """Create rotating loggers and return them keyed by concern name."""
    global _INITIALISED
    os.makedirs(logs_dir, exist_ok=True)
    numeric = getattr(logging, str(level).upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    for name, filename in LOG_FILES.items():
        logger = logging.getLogger(f"zerotrace.{name}")
        logger.setLevel(numeric)
        logger.propagate = False
        if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
            handler = RotatingFileHandler(
                os.path.join(logs_dir, filename),
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        _LOGGERS[name] = logger
    app_logger = _LOGGERS["app"]
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
               for h in app_logger.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        app_logger.addHandler(console)
    _INITIALISED = True
    return dict(_LOGGERS)


def get_logger(name: str = "app") -> logging.Logger:
    """Return a configured logger, initialising defaults on first use."""
    if name in _LOGGERS:
        return _LOGGERS[name]
    if not _INITIALISED:
        setup_logging()
        if name in _LOGGERS:
            return _LOGGERS[name]
    logger = logging.getLogger(f"zerotrace.{name}")
    _LOGGERS[name] = logger
    return logger


def log_trade_event(logger: Optional[logging.Logger] = None, **fields: object) -> None:
    """Write one structured pipe-delimited line to the trade logger."""
    logger = logger or get_logger("trades")
    line = " | ".join(f"{key}={value}" for key, value in fields.items())
    logger.info(line)
