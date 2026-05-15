"""Compatibility entry point for the local iterative research pipeline."""

from __future__ import annotations

from .cli import main, parse_args
from .config import (
    ConfigValidationError,
    list_installed_ollama_models,
    load_app_config,
    load_config,
)
from .constants import (
    DEFAULT_CONTINUOUS_MAX_RUNTIME_SECONDS,
    DEFAULT_NORMAL_MAX_RUNTIME_SECONDS,
    RUN_LOCK_FILENAME,
    STOP_EXCEPTION,
    STOP_INVALID_SCORE,
    STOP_MANUAL_INTERRUPT,
    STOP_MAX_ROUNDS,
    STOP_NO_IMPROVEMENT,
    STOP_OLLAMA_TIMEOUT,
    STOP_USER_REQUESTED,
)
from .diagnostic import run_diagnostic_mode
from .runner import run_iterative_rounds
from .session import run_session_mode

__all__ = [
    "DEFAULT_CONTINUOUS_MAX_RUNTIME_SECONDS",
    "DEFAULT_NORMAL_MAX_RUNTIME_SECONDS",
    "RUN_LOCK_FILENAME",
    "STOP_EXCEPTION",
    "STOP_INVALID_SCORE",
    "STOP_MANUAL_INTERRUPT",
    "STOP_MAX_ROUNDS",
    "STOP_NO_IMPROVEMENT",
    "STOP_OLLAMA_TIMEOUT",
    "STOP_USER_REQUESTED",
    "ConfigValidationError",
    "list_installed_ollama_models",
    "load_app_config",
    "load_config",
    "main",
    "parse_args",
    "run_diagnostic_mode",
    "run_iterative_rounds",
    "run_session_mode",
]


if __name__ == "__main__":
    main()
