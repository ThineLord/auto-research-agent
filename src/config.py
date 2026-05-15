"""Configuration and local model discovery helpers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .constants import (
    DEFAULT_CONTINUOUS_MAX_RUNTIME_SECONDS,
    DEFAULT_NORMAL_MAX_RUNTIME_SECONDS,
)


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_model_settings(config: Dict[str, Any]) -> Tuple[str, float, int]:
    model_cfg = config.get("model", {})
    if isinstance(model_cfg, dict):
        model_name = str(model_cfg.get("name", "qwen3:8b"))
        temperature = float(model_cfg.get("temperature", config.get("temperature", 0.4)))
        timeout_seconds = int(model_cfg.get("timeout_seconds", config.get("timeout_seconds", 300)))
    else:
        model_name = str(model_cfg) if model_cfg else "qwen3:8b"
        temperature = float(config.get("temperature", 0.4))
        timeout_seconds = int(config.get("timeout_seconds", 300))
    return model_name, temperature, timeout_seconds


def resolve_runtime_limits(config: Dict[str, Any]) -> Tuple[int, int]:
    runtime_cfg = config.get("runtime", {})
    if not isinstance(runtime_cfg, dict):
        runtime_cfg = {}
    normal_max_runtime_seconds = max(
        60,
        int(runtime_cfg.get("normal_max_runtime_seconds", DEFAULT_NORMAL_MAX_RUNTIME_SECONDS)),
    )
    continuous_max_runtime_seconds = max(
        normal_max_runtime_seconds,
        int(
            runtime_cfg.get(
                "continuous_max_runtime_seconds",
                DEFAULT_CONTINUOUS_MAX_RUNTIME_SECONDS,
            )
        ),
    )
    return normal_max_runtime_seconds, continuous_max_runtime_seconds


def list_installed_ollama_models() -> Tuple[List[str], Optional[str]]:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except FileNotFoundError:
        return [], "Ollama is not installed or not in PATH."
    except subprocess.SubprocessError as exc:
        return [], f"Failed to query Ollama: {exc}"

    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip() or "Unknown error from ollama list."
        return [], f"Ollama is not available: {err}"

    models: List[str] = []
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        cols = re.split(r"\s{2,}", line)
        name = cols[0].strip() if cols else ""
        if name:
            models.append(name)
    return models, None
