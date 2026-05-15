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

DEFAULT_MODEL_NAME = "qwen3:8b"


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_model_settings(config: Dict[str, Any]) -> Tuple[str, float, int]:
    model_cfg = config.get("model", {})
    if isinstance(model_cfg, dict):
        model_name = str(model_cfg.get("name", DEFAULT_MODEL_NAME))
        temperature = float(model_cfg.get("temperature", config.get("temperature", 0.4)))
        timeout_seconds = int(model_cfg.get("timeout_seconds", config.get("timeout_seconds", 300)))
    else:
        model_name = str(model_cfg) if model_cfg else DEFAULT_MODEL_NAME
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


def parse_ollama_list_output(output: str) -> List[Dict[str, str]]:
    models: List[Dict[str, str]] = []
    lines = [line for line in output.splitlines() if line.strip()]
    for line in lines[1:]:
        parts = re.split(r"\s{2,}", line.strip())
        if not parts:
            continue
        name = parts[0] if len(parts) > 0 else ""
        if not name:
            continue
        models.append(
            {
                "name": name,
                "id": parts[1] if len(parts) > 1 else "",
                "size": parts[2] if len(parts) > 2 else "",
                "modified": parts[3] if len(parts) > 3 else "",
            }
        )
    return models


def query_ollama_models(timeout_seconds: int = 10) -> Tuple[List[Dict[str, str]], Optional[str]]:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return [], "Ollama is not installed or not in PATH."
    except subprocess.SubprocessError as exc:
        return [], f"Failed to query Ollama: {exc}"

    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip() or "Unknown error from ollama list."
        return [], f"Ollama is not available: {err}"

    return parse_ollama_list_output(result.stdout), None


def list_installed_ollama_models() -> Tuple[List[str], Optional[str]]:
    models, error = query_ollama_models()
    if error:
        return [], error
    return [model["name"] for model in models], None


def load_default_model_name(config_path: Path, default_name: str = DEFAULT_MODEL_NAME) -> str:
    if not config_path.exists():
        return default_name
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return default_name
    model_cfg = config.get("model", {})
    if isinstance(model_cfg, dict):
        return str(model_cfg.get("name", default_name))
    if isinstance(model_cfg, str):
        return model_cfg
    return default_name


def save_default_model_name(
    config_path: Path,
    model_name: str,
    default_name: str = DEFAULT_MODEL_NAME,
) -> Optional[str]:
    if not config_path.exists():
        return f"config file not found: {config_path}"
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return f"failed to parse config.yaml: {exc}"
    model_cfg = config.get("model", {})
    if not isinstance(model_cfg, dict):
        model_cfg = {}
    model_cfg.setdefault("provider", "ollama")
    model_cfg["name"] = model_name or default_name
    model_cfg.setdefault("temperature", 0.3)
    model_cfg.setdefault("timeout_seconds", 300)
    config["model"] = model_cfg
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return None
