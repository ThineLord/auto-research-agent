"""Configuration and local model discovery helpers."""

from __future__ import annotations

import math
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import yaml

from .constants import (
    DEFAULT_CONTINUOUS_MAX_RUNTIME_SECONDS,
    DEFAULT_NORMAL_MAX_RUNTIME_SECONDS,
)

DEFAULT_MODEL_NAME = "qwen3:8b"
DEFAULT_MODEL_TEMPERATURE = 0.4
DEFAULT_MODEL_TIMEOUT_SECONDS = 300
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_PROJECT_NAME = "pama"
DEFAULT_MAX_ROUNDS = 5
DEFAULT_STOP_IF_NO_IMPROVEMENT_ROUNDS = 2
DEFAULT_TOP_P = 0.9
MAX_MODEL_TIMEOUT_SECONDS = 300
MAX_MODEL_TEMPERATURE = 2.0
YAML_ERROR = getattr(yaml, "YAMLError", Exception)


class ConfigValidationError(ValueError):
    """Raised when config.yaml is readable YAML but violates the supported schema."""


@dataclass(frozen=True)
class ModelConfig:
    provider: str = "ollama"
    name: str = DEFAULT_MODEL_NAME
    temperature: float = DEFAULT_MODEL_TEMPERATURE
    timeout_seconds: int = DEFAULT_MODEL_TIMEOUT_SECONDS


@dataclass(frozen=True)
class RuntimeConfig:
    normal_max_runtime_seconds: int = DEFAULT_NORMAL_MAX_RUNTIME_SECONDS
    continuous_max_runtime_seconds: int = DEFAULT_CONTINUOUS_MAX_RUNTIME_SECONDS


@dataclass(frozen=True)
class AppConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    project_name: str = DEFAULT_PROJECT_NAME
    max_rounds: int = DEFAULT_MAX_ROUNDS
    stop_if_no_improvement_rounds: int = DEFAULT_STOP_IF_NO_IMPROVEMENT_ROUNDS
    top_p: float = DEFAULT_TOP_P
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model": {
                "provider": self.model.provider,
                "name": self.model.name,
                "temperature": self.model.temperature,
                "timeout_seconds": self.model.timeout_seconds,
            },
            "ollama_base_url": self.ollama_base_url,
            "project_name": self.project_name,
            "max_rounds": self.max_rounds,
            "stop_if_no_improvement_rounds": self.stop_if_no_improvement_rounds,
            "top_p": self.top_p,
            "runtime": {
                "normal_max_runtime_seconds": self.runtime.normal_max_runtime_seconds,
                "continuous_max_runtime_seconds": self.runtime.continuous_max_runtime_seconds,
            },
        }


ConfigInput = Union[Mapping[str, Any], AppConfig]


def _format_unknown_keys(keys: list[str]) -> str:
    return ", ".join(sorted(keys))


def _validate_mapping_keys(
    section_name: str,
    mapping: Mapping[Any, Any],
    allowed_keys: set[str],
) -> None:
    non_string_keys = [repr(key) for key in mapping if not isinstance(key, str)]
    if non_string_keys:
        raise ConfigValidationError(
            f"{section_name}: keys must be strings; got {_format_unknown_keys(non_string_keys)}"
        )
    unknown_keys = [key for key in mapping if key not in allowed_keys]
    if unknown_keys:
        raise ConfigValidationError(
            f"{section_name}: unknown key(s): {_format_unknown_keys(unknown_keys)}"
        )


def _validate_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ConfigValidationError(f"{field_name}: must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ConfigValidationError(f"{field_name}: must be a non-empty string")
    return normalized


def _validate_project_name(value: Any) -> str:
    project_name = _validate_non_empty_string(value, "config.project_name")
    if project_name in {".", ".."} or "/" in project_name or "\\" in project_name:
        raise ConfigValidationError(
            "config.project_name: must be a simple project folder name under projects/"
        )
    return project_name


def _validate_ollama_base_url(value: Any) -> str:
    base_url = _validate_non_empty_string(value, "config.ollama_base_url")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigValidationError("config.ollama_base_url: must be an absolute http or https URL")
    return base_url


def _validate_float(
    value: Any,
    field_name: str,
    *,
    min_value: float,
    max_value: float,
    min_inclusive: bool = True,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigValidationError(f"{field_name}: must be a number")
    normalized = float(value)
    if math.isnan(normalized) or math.isinf(normalized):
        raise ConfigValidationError(f"{field_name}: must be a finite number")
    min_ok = normalized >= min_value if min_inclusive else normalized > min_value
    if not min_ok or normalized > max_value:
        min_boundary = "[" if min_inclusive else "("
        raise ConfigValidationError(
            f"{field_name}: must be in range {min_boundary}{min_value}, {max_value}]"
        )
    return normalized


def _validate_int(
    value: Any,
    field_name: str,
    *,
    min_value: int,
    max_value: Optional[int] = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigValidationError(f"{field_name}: must be an integer")
    if value < min_value:
        raise ConfigValidationError(f"{field_name}: must be >= {min_value}")
    if max_value is not None and value > max_value:
        raise ConfigValidationError(f"{field_name}: must be <= {max_value}")
    return value


def _read_yaml_mapping(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except YAML_ERROR as exc:
        raise ConfigValidationError(f"{config_path}: failed to parse YAML: {exc}") from exc
    if raw_config is None:
        return {}
    if not isinstance(raw_config, Mapping):
        raise ConfigValidationError("config: top-level YAML must be a mapping")
    return dict(raw_config)


def _validate_model_config(config: Mapping[str, Any]) -> ModelConfig:
    raw_model = config.get("model", {})
    top_level_temperature = config.get("temperature", DEFAULT_MODEL_TEMPERATURE)
    top_level_timeout = config.get("timeout_seconds", DEFAULT_MODEL_TIMEOUT_SECONDS)

    if isinstance(raw_model, str):
        model_name = _validate_non_empty_string(raw_model, "config.model")
        model_mapping: Mapping[str, Any] = {}
    elif isinstance(raw_model, Mapping):
        _validate_mapping_keys(
            "config.model",
            raw_model,
            {"provider", "name", "temperature", "timeout_seconds"},
        )
        model_mapping = raw_model
        model_name = _validate_non_empty_string(
            model_mapping.get("name", DEFAULT_MODEL_NAME),
            "config.model.name",
        )
    else:
        raise ConfigValidationError("config.model: must be a mapping or model name string")

    provider = _validate_non_empty_string(
        model_mapping.get("provider", "ollama"),
        "config.model.provider",
    )
    if provider != "ollama":
        raise ConfigValidationError("config.model.provider: must be 'ollama'")

    temperature = _validate_float(
        model_mapping.get("temperature", top_level_temperature),
        "config.model.temperature",
        min_value=0.0,
        max_value=MAX_MODEL_TEMPERATURE,
    )
    timeout_seconds = _validate_int(
        model_mapping.get("timeout_seconds", top_level_timeout),
        "config.model.timeout_seconds",
        min_value=1,
        max_value=MAX_MODEL_TIMEOUT_SECONDS,
    )
    return ModelConfig(
        provider=provider,
        name=model_name,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )


def _validate_runtime_config(config: Mapping[str, Any]) -> RuntimeConfig:
    raw_runtime = config.get("runtime", {})
    if not isinstance(raw_runtime, Mapping):
        raise ConfigValidationError("config.runtime: must be a mapping")
    _validate_mapping_keys(
        "config.runtime",
        raw_runtime,
        {"normal_max_runtime_seconds", "continuous_max_runtime_seconds"},
    )

    normal_max_runtime_seconds = _validate_int(
        raw_runtime.get("normal_max_runtime_seconds", DEFAULT_NORMAL_MAX_RUNTIME_SECONDS),
        "config.runtime.normal_max_runtime_seconds",
        min_value=60,
    )
    continuous_max_runtime_seconds = _validate_int(
        raw_runtime.get(
            "continuous_max_runtime_seconds",
            DEFAULT_CONTINUOUS_MAX_RUNTIME_SECONDS,
        ),
        "config.runtime.continuous_max_runtime_seconds",
        min_value=normal_max_runtime_seconds,
    )
    return RuntimeConfig(
        normal_max_runtime_seconds=normal_max_runtime_seconds,
        continuous_max_runtime_seconds=continuous_max_runtime_seconds,
    )


def _build_app_config(raw_config: Mapping[str, Any]) -> AppConfig:
    _validate_mapping_keys(
        "config",
        raw_config,
        {
            "model",
            "ollama_base_url",
            "project_name",
            "max_rounds",
            "stop_if_no_improvement_rounds",
            "top_p",
            "runtime",
            "temperature",
            "timeout_seconds",
        },
    )

    return AppConfig(
        model=_validate_model_config(raw_config),
        ollama_base_url=_validate_ollama_base_url(
            raw_config.get("ollama_base_url", DEFAULT_OLLAMA_BASE_URL)
        ),
        project_name=_validate_project_name(raw_config.get("project_name", DEFAULT_PROJECT_NAME)),
        max_rounds=_validate_int(
            raw_config.get("max_rounds", DEFAULT_MAX_ROUNDS),
            "config.max_rounds",
            min_value=1,
        ),
        stop_if_no_improvement_rounds=_validate_int(
            raw_config.get(
                "stop_if_no_improvement_rounds",
                DEFAULT_STOP_IF_NO_IMPROVEMENT_ROUNDS,
            ),
            "config.stop_if_no_improvement_rounds",
            min_value=0,
        ),
        top_p=_validate_float(
            raw_config.get("top_p", DEFAULT_TOP_P),
            "config.top_p",
            min_value=0.0,
            max_value=1.0,
            min_inclusive=False,
        ),
        runtime=_validate_runtime_config(raw_config),
    )


def load_app_config(config_path: Path) -> AppConfig:
    return _build_app_config(_read_yaml_mapping(config_path))


def load_config(config_path: Path) -> Dict[str, Any]:
    return load_app_config(config_path).as_dict()


def resolve_model_settings(config: ConfigInput) -> Tuple[str, float, int]:
    if isinstance(config, AppConfig):
        return config.model.name, config.model.temperature, config.model.timeout_seconds
    config = _build_app_config(config)
    return config.model.name, config.model.temperature, config.model.timeout_seconds


def resolve_runtime_limits(config: ConfigInput) -> Tuple[int, int]:
    if isinstance(config, AppConfig):
        runtime = config.runtime
    else:
        runtime = _build_app_config(config).runtime
    return runtime.normal_max_runtime_seconds, runtime.continuous_max_runtime_seconds


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
    return load_app_config(config_path).model.name


def save_default_model_name(
    config_path: Path,
    model_name: str,
    default_name: str = DEFAULT_MODEL_NAME,
) -> Optional[str]:
    if not config_path.exists():
        return f"config file not found: {config_path}"
    try:
        config = _read_yaml_mapping(config_path)
        current_config = _build_app_config(config)
    except ConfigValidationError as exc:
        return f"invalid config.yaml: {exc}"
    model_cfg = config.get("model", {})
    if not isinstance(model_cfg, dict):
        model_cfg = {}
    model_cfg.setdefault("provider", current_config.model.provider)
    model_cfg["name"] = model_name.strip() or default_name
    model_cfg.setdefault("temperature", current_config.model.temperature)
    model_cfg.setdefault("timeout_seconds", current_config.model.timeout_seconds)
    config["model"] = model_cfg
    try:
        _build_app_config(config)
    except ConfigValidationError as exc:
        return f"invalid config.yaml after update: {exc}"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return None
