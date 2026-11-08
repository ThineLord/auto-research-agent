"""Structured logging setup for internal diagnostics."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional, TextIO

LOG_LEVEL_ENV = "AUTO_RESEARCH_LOG_LEVEL"
DEFAULT_LOG_LEVEL = "INFO"
PACKAGE_LOGGER_NAME = "src"

_STANDARD_LOG_RECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _resolve_log_level(level_name: Optional[str]) -> int:
    normalized = (level_name or os.getenv(LOG_LEVEL_ENV, DEFAULT_LOG_LEVEL)).strip().upper()
    level = getattr(logging, normalized, None)
    if isinstance(level, int):
        return level
    return logging.INFO


class JsonLogFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in sorted(record.__dict__.items()):
            if key in _STANDARD_LOG_RECORD_ATTRS or key.startswith("_"):
                continue
            payload[key] = _json_safe(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True)


def configure_logging(
    *,
    level_name: Optional[str] = None,
    stream: Optional[TextIO] = None,
) -> None:
    """Configure structured logging for the application package once."""
    level = _resolve_log_level(level_name)
    logger = logging.getLogger(PACKAGE_LOGGER_NAME)

    if getattr(configure_logging, "_configured", False):
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)
        return

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonLogFormatter())
    handler.setLevel(level)

    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    configure_logging._configured = True  # type: ignore[attr-defined]
