"""Configuration and local model discovery helpers."""

from __future__ import annotations

import json
import math
import re
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import yaml

from .cloud_free import (
    FREE_RUNNER_PRESETS,
    CloudFreeConfig,
)
from .constants import (
    DEFAULT_CONTINUOUS_MAX_RUNTIME_SECONDS,
    DEFAULT_NORMAL_MAX_RUNTIME_SECONDS,
)

DEFAULT_MODEL_NAME = "qwen3:8b"
DEFAULT_MODEL_TEMPERATURE = 0.4
DEFAULT_MODEL_TIMEOUT_SECONDS = 300
DEFAULT_OLLAMA_MAX_PROMPT_CHARS = 12000
DEFAULT_GEMINI_MAX_PROMPT_CHARS = 32000
MODEL_PROVIDER_OLLAMA = "ollama"
MODEL_PROVIDER_GEMINI = "gemini"
SUPPORTED_MODEL_PROVIDERS = {MODEL_PROVIDER_OLLAMA, MODEL_PROVIDER_GEMINI}
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
DEFAULT_GEMINI_MODELS = (
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_PROJECT_NAME = "example"
DEFAULT_TOPIC_TITLE = "Configured Research Topic"
DEFAULT_TOPIC_DESCRIPTION = (
    "Use the project task file as the source of truth for this research topic."
)
DEFAULT_TOPIC_KEYWORDS = (
    "research",
    "method",
    "evaluation",
    "implementation",
    "baseline",
)
DEFAULT_MAX_ROUNDS = 5
DEFAULT_STOP_IF_NO_IMPROVEMENT_ROUNDS = 2
DEFAULT_TOP_P = 0.9
MAX_MODEL_TIMEOUT_SECONDS = 300
MAX_MODEL_TEMPERATURE = 2.0
YAML_ERROR = getattr(yaml, "YAMLError", Exception)


class ConfigValidationError(ValueError):
    """Raised when config.yaml is readable YAML but violates the supported schema."""


@dataclass(frozen=True)
class GeminiConfig:
    api_key_env: str = DEFAULT_GEMINI_API_KEY_ENV
    api_key: str = ""
    models: Tuple[str, ...] = DEFAULT_GEMINI_MODELS


@dataclass(frozen=True)
class ModelConfig:
    provider: str = MODEL_PROVIDER_OLLAMA
    name: str = DEFAULT_MODEL_NAME
    temperature: float = DEFAULT_MODEL_TEMPERATURE
    timeout_seconds: int = DEFAULT_MODEL_TIMEOUT_SECONDS
    max_prompt_chars: int = DEFAULT_OLLAMA_MAX_PROMPT_CHARS
    gemini: GeminiConfig = field(default_factory=GeminiConfig)


@dataclass(frozen=True)
class RuntimeConfig:
    normal_max_runtime_seconds: int = DEFAULT_NORMAL_MAX_RUNTIME_SECONDS
    continuous_max_runtime_seconds: int = DEFAULT_CONTINUOUS_MAX_RUNTIME_SECONDS


@dataclass(frozen=True)
class TopicConfig:
    title: str = DEFAULT_TOPIC_TITLE
    description: str = DEFAULT_TOPIC_DESCRIPTION
    keywords: Tuple[str, ...] = DEFAULT_TOPIC_KEYWORDS


@dataclass(frozen=True)
class AppConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    project_name: str = DEFAULT_PROJECT_NAME
    topic: TopicConfig = field(default_factory=TopicConfig)
    max_rounds: int = DEFAULT_MAX_ROUNDS
    stop_if_no_improvement_rounds: int = DEFAULT_STOP_IF_NO_IMPROVEMENT_ROUNDS
    top_p: float = DEFAULT_TOP_P
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    cloud_free: CloudFreeConfig = field(default_factory=CloudFreeConfig)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model": {
                "provider": self.model.provider,
                "name": self.model.name,
                "temperature": self.model.temperature,
                "timeout_seconds": self.model.timeout_seconds,
                "max_prompt_chars": self.model.max_prompt_chars,
                "gemini": {
                    "api_key_env": self.model.gemini.api_key_env,
                    "api_key": self.model.gemini.api_key,
                    "models": list(self.model.gemini.models),
                },
            },
            "ollama_base_url": self.ollama_base_url,
            "project_name": self.project_name,
            "topic": {
                "title": self.topic.title,
                "description": self.topic.description,
                "keywords": list(self.topic.keywords),
            },
            "max_rounds": self.max_rounds,
            "stop_if_no_improvement_rounds": self.stop_if_no_improvement_rounds,
            "top_p": self.top_p,
            "runtime": {
                "normal_max_runtime_seconds": self.runtime.normal_max_runtime_seconds,
                "continuous_max_runtime_seconds": self.runtime.continuous_max_runtime_seconds,
            },
            "cloud_free": {
                "cloud_free_mode": self.cloud_free.cloud_free_mode,
                "free_runner_preset": self.cloud_free.free_runner_preset,
                "min_delay_seconds": self.cloud_free.min_delay_seconds,
                "max_delay_seconds": self.cloud_free.max_delay_seconds,
                "max_retries": self.cloud_free.max_retries,
                "prompt_budget_chars": self.cloud_free.prompt_budget_chars,
                "prompt_budget_tokens": self.cloud_free.prompt_budget_tokens,
                "allow_model_fallback": self.cloud_free.allow_model_fallback,
                "allowed_model_patterns": list(self.cloud_free.allowed_model_patterns),
                "blocked_model_patterns": list(self.cloud_free.blocked_model_patterns),
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


def _validate_optional_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ConfigValidationError(f"{field_name}: must be a string")
    return value.strip()


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


def _validate_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigValidationError(f"{field_name}: must be a boolean")
    return value


def _validate_optional_float(
    value: Any,
    field_name: str,
    *,
    min_value: float,
) -> float | None:
    if value is None:
        return None
    return _validate_float(value, field_name, min_value=min_value, max_value=86400.0)


def _validate_optional_int(
    value: Any,
    field_name: str,
    *,
    min_value: int,
) -> int | None:
    if value is None:
        return None
    return _validate_int(value, field_name, min_value=min_value)


def _validate_string_list(value: Any, field_name: str) -> Tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigValidationError(f"{field_name}: must be a list of non-empty strings")
    items: list[str] = []
    seen = set()
    for index, item in enumerate(value):
        normalized = _validate_non_empty_string(item, f"{field_name}[{index}]")
        if normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return tuple(items)


def _validate_model_provider(value: Any) -> str:
    provider = _validate_non_empty_string(value, "config.model.provider").lower()
    if provider not in SUPPORTED_MODEL_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_MODEL_PROVIDERS))
        raise ConfigValidationError(f"config.model.provider: must be one of: {supported}")
    return provider


def _validate_gemini_models(value: Any) -> Tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigValidationError(
            "config.model.gemini.models: must be a list of non-empty strings"
        )
    if not value:
        raise ConfigValidationError("config.model.gemini.models: must contain at least one model")

    models: list[str] = []
    seen = set()
    for index, item in enumerate(value):
        model = _validate_non_empty_string(
            item,
            f"config.model.gemini.models[{index}]",
        )
        if model in seen:
            continue
        seen.add(model)
        models.append(model)
    return tuple(models)


def _validate_gemini_config(raw_gemini: Any) -> GeminiConfig:
    if raw_gemini is None:
        raw_gemini = {}
    if not isinstance(raw_gemini, Mapping):
        raise ConfigValidationError("config.model.gemini: must be a mapping")
    _validate_mapping_keys(
        "config.model.gemini",
        raw_gemini,
        {"api_key_env", "api_key", "models"},
    )
    return GeminiConfig(
        api_key_env=_validate_non_empty_string(
            raw_gemini.get("api_key_env", DEFAULT_GEMINI_API_KEY_ENV),
            "config.model.gemini.api_key_env",
        ),
        api_key=_validate_optional_string(
            raw_gemini.get("api_key", ""),
            "config.model.gemini.api_key",
        ),
        models=_validate_gemini_models(
            raw_gemini.get("models", list(DEFAULT_GEMINI_MODELS)),
        ),
    )


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
            {
                "provider",
                "name",
                "temperature",
                "timeout_seconds",
                "max_prompt_chars",
                "gemini",
            },
        )
        model_mapping = raw_model
    else:
        raise ConfigValidationError("config.model: must be a mapping or model name string")

    provider = _validate_model_provider(
        model_mapping.get("provider", MODEL_PROVIDER_OLLAMA),
    )
    if not isinstance(raw_model, str):
        default_model_name = (
            DEFAULT_GEMINI_MODEL if provider == MODEL_PROVIDER_GEMINI else DEFAULT_MODEL_NAME
        )
        model_name = _validate_non_empty_string(
            model_mapping.get("name", default_model_name),
            "config.model.name",
        )

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
    default_max_prompt_chars = (
        DEFAULT_GEMINI_MAX_PROMPT_CHARS
        if provider == MODEL_PROVIDER_GEMINI
        else DEFAULT_OLLAMA_MAX_PROMPT_CHARS
    )
    max_prompt_chars = _validate_int(
        model_mapping.get("max_prompt_chars", default_max_prompt_chars),
        "config.model.max_prompt_chars",
        min_value=1000,
    )
    return ModelConfig(
        provider=provider,
        name=model_name,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        max_prompt_chars=max_prompt_chars,
        gemini=_validate_gemini_config(model_mapping.get("gemini", {})),
    )


def _validate_topic_keywords(value: Any) -> Tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigValidationError("config.topic.keywords: must be a list of non-empty strings")
    if not value:
        raise ConfigValidationError("config.topic.keywords: must contain at least one keyword")

    keywords: list[str] = []
    seen = set()
    for index, item in enumerate(value):
        keyword = _validate_non_empty_string(item, f"config.topic.keywords[{index}]")
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(keyword)
    return tuple(keywords)


def _validate_topic_config(config: Mapping[str, Any]) -> TopicConfig:
    raw_topic = config.get("topic", {})
    if raw_topic is None:
        raw_topic = {}
    if not isinstance(raw_topic, Mapping):
        raise ConfigValidationError("config.topic: must be a mapping")
    _validate_mapping_keys(
        "config.topic",
        raw_topic,
        {"title", "description", "keywords"},
    )

    return TopicConfig(
        title=_validate_non_empty_string(
            raw_topic.get("title", DEFAULT_TOPIC_TITLE),
            "config.topic.title",
        ),
        description=_validate_non_empty_string(
            raw_topic.get("description", DEFAULT_TOPIC_DESCRIPTION),
            "config.topic.description",
        ),
        keywords=_validate_topic_keywords(
            raw_topic.get("keywords", list(DEFAULT_TOPIC_KEYWORDS)),
        ),
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


def _validate_free_runner_preset(value: Any) -> str:
    preset = _validate_non_empty_string(value, "config.cloud_free.free_runner_preset")
    if preset not in FREE_RUNNER_PRESETS:
        supported = ", ".join(FREE_RUNNER_PRESETS)
        raise ConfigValidationError(
            f"config.cloud_free.free_runner_preset: must be one of: {supported}"
        )
    return preset


def _validate_cloud_free_config(config: Mapping[str, Any]) -> CloudFreeConfig:
    raw_cloud_free = config.get("cloud_free", {})
    if raw_cloud_free is None:
        raw_cloud_free = {}
    if not isinstance(raw_cloud_free, Mapping):
        raise ConfigValidationError("config.cloud_free: must be a mapping")
    _validate_mapping_keys(
        "config.cloud_free",
        raw_cloud_free,
        {
            "cloud_free_mode",
            "free_runner_preset",
            "min_delay_seconds",
            "max_delay_seconds",
            "max_retries",
            "prompt_budget_chars",
            "prompt_budget_tokens",
            "allow_model_fallback",
            "allowed_model_patterns",
            "blocked_model_patterns",
        },
    )

    defaults = CloudFreeConfig()
    min_delay_seconds = _validate_optional_float(
        raw_cloud_free.get("min_delay_seconds", defaults.min_delay_seconds),
        "config.cloud_free.min_delay_seconds",
        min_value=0.0,
    )
    max_delay_seconds = _validate_float(
        raw_cloud_free.get("max_delay_seconds", defaults.max_delay_seconds),
        "config.cloud_free.max_delay_seconds",
        min_value=0.0,
        max_value=86400.0,
    )
    if min_delay_seconds is not None and max_delay_seconds < min_delay_seconds:
        raise ConfigValidationError(
            "config.cloud_free.max_delay_seconds: must be >= min_delay_seconds"
        )

    return CloudFreeConfig(
        cloud_free_mode=_validate_bool(
            raw_cloud_free.get("cloud_free_mode", defaults.cloud_free_mode),
            "config.cloud_free.cloud_free_mode",
        ),
        free_runner_preset=_validate_free_runner_preset(
            raw_cloud_free.get("free_runner_preset", defaults.free_runner_preset)
        ),
        min_delay_seconds=min_delay_seconds,
        max_delay_seconds=max_delay_seconds,
        max_retries=_validate_int(
            raw_cloud_free.get("max_retries", defaults.max_retries),
            "config.cloud_free.max_retries",
            min_value=0,
            max_value=20,
        ),
        prompt_budget_chars=_validate_int(
            raw_cloud_free.get("prompt_budget_chars", defaults.prompt_budget_chars),
            "config.cloud_free.prompt_budget_chars",
            min_value=1000,
        ),
        prompt_budget_tokens=_validate_optional_int(
            raw_cloud_free.get("prompt_budget_tokens", defaults.prompt_budget_tokens),
            "config.cloud_free.prompt_budget_tokens",
            min_value=100,
        ),
        allow_model_fallback=_validate_bool(
            raw_cloud_free.get("allow_model_fallback", defaults.allow_model_fallback),
            "config.cloud_free.allow_model_fallback",
        ),
        allowed_model_patterns=_validate_string_list(
            raw_cloud_free.get("allowed_model_patterns", list(defaults.allowed_model_patterns)),
            "config.cloud_free.allowed_model_patterns",
        ),
        blocked_model_patterns=_validate_string_list(
            raw_cloud_free.get("blocked_model_patterns", list(defaults.blocked_model_patterns)),
            "config.cloud_free.blocked_model_patterns",
        ),
    )


def _build_app_config(raw_config: Mapping[str, Any]) -> AppConfig:
    _validate_mapping_keys(
        "config",
        raw_config,
        {
            "model",
            "ollama_base_url",
            "project_name",
            "topic",
            "max_rounds",
            "stop_if_no_improvement_rounds",
            "top_p",
            "runtime",
            "cloud_free",
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
        topic=_validate_topic_config(raw_config),
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
        cloud_free=_validate_cloud_free_config(raw_config),
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


def resolve_model_provider_settings(
    config: ConfigInput,
) -> tuple[str, str, float, int, GeminiConfig]:
    if isinstance(config, AppConfig):
        model = config.model
    else:
        model = _build_app_config(config).model
    return (
        model.provider,
        model.name,
        model.temperature,
        model.timeout_seconds,
        model.gemini,
    )


def format_model_label(provider: str, model_name: str) -> str:
    provider = provider.strip().lower()
    if provider == MODEL_PROVIDER_OLLAMA:
        return model_name
    if provider == MODEL_PROVIDER_GEMINI:
        return f"{MODEL_PROVIDER_GEMINI}:{model_name}"
    raise ConfigValidationError(f"model provider is not supported: {provider}")


def resolve_runtime_limits(config: ConfigInput) -> Tuple[int, int]:
    if isinstance(config, AppConfig):
        runtime = config.runtime
    else:
        runtime = _build_app_config(config).runtime
    return runtime.normal_max_runtime_seconds, runtime.continuous_max_runtime_seconds


def format_topic_context(topic: TopicConfig) -> str:
    keywords = ", ".join(topic.keywords)
    return f"Title: {topic.title}\nDescription: {topic.description}\nKeywords: {keywords}"


def normalize_ollama_models(models: Iterable[Mapping[str, Any]]) -> List[Dict[str, str]]:
    normalized: Dict[str, Dict[str, str]] = {}
    for model in models:
        name = str(model.get("name", "")).strip()
        if not name or name in normalized:
            continue
        normalized[name] = {
            "name": name,
            "id": str(model.get("id", "") or model.get("digest", "")).strip(),
            "size": str(model.get("size", "")).strip(),
            "modified": str(model.get("modified", "") or model.get("modified_at", "")).strip(),
        }
    return sorted(normalized.values(), key=lambda model: model["name"].casefold())


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
    return normalize_ollama_models(models)


def parse_ollama_tags_payload(payload: Mapping[str, Any]) -> List[Dict[str, str]]:
    raw_models = payload.get("models", [])
    if not isinstance(raw_models, list):
        return []
    return normalize_ollama_models(model for model in raw_models if isinstance(model, Mapping))


def query_ollama_api_models(
    *,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    timeout_seconds: int = 10,
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    url = f"{base_url.rstrip('/')}/api/tags"
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return [], f"Failed to query Ollama API at {url}: {exc}"
    if not isinstance(payload, Mapping):
        return [], f"Failed to query Ollama API at {url}: response was not a JSON object"
    return parse_ollama_tags_payload(payload), None


def query_ollama_models(
    timeout_seconds: int = 10,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    command_error: str | None = None
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        command_error = "Ollama is not installed or not in PATH."
    except subprocess.SubprocessError as exc:
        command_error = f"Failed to query Ollama: {exc}"
    else:
        if result.returncode == 0:
            return parse_ollama_list_output(result.stdout), None
        command_error = (
            result.stderr.strip() or result.stdout.strip() or "Unknown error from ollama list."
        )

    api_models, api_error = query_ollama_api_models(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    if api_error is None:
        return api_models, None

    return [], f"Ollama is not available: {command_error}; API fallback failed: {api_error}"


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
    return save_default_model_selection(
        config_path,
        provider=MODEL_PROVIDER_OLLAMA,
        model_name=model_name.strip() or default_name,
    )


def save_default_model_selection(
    config_path: Path,
    *,
    provider: str,
    model_name: str,
    gemini_api_key_env: str | None = None,
) -> Optional[str]:
    if not config_path.exists():
        return f"config file not found: {config_path}"
    try:
        config = _read_yaml_mapping(config_path)
        current_config = _build_app_config(config)
    except ConfigValidationError as exc:
        return f"invalid config.yaml: {exc}"
    try:
        provider = _validate_model_provider(provider)
    except ConfigValidationError as exc:
        return f"invalid model provider: {exc}"

    model_cfg = config.get("model", {})
    if not isinstance(model_cfg, dict):
        model_cfg = {}
    default_model_name = (
        DEFAULT_GEMINI_MODEL if provider == MODEL_PROVIDER_GEMINI else DEFAULT_MODEL_NAME
    )
    model_cfg["provider"] = provider
    model_cfg["name"] = model_name.strip() or default_model_name
    model_cfg.setdefault("temperature", current_config.model.temperature)
    model_cfg.setdefault("timeout_seconds", current_config.model.timeout_seconds)
    model_cfg.setdefault("max_prompt_chars", current_config.model.max_prompt_chars)

    if (
        provider == MODEL_PROVIDER_GEMINI
        or gemini_api_key_env is not None
        or isinstance(model_cfg.get("gemini"), Mapping)
    ):
        api_key_env = (
            gemini_api_key_env.strip()
            if isinstance(gemini_api_key_env, str) and gemini_api_key_env.strip()
            else current_config.model.gemini.api_key_env
        )
        model_cfg["gemini"] = {
            "api_key_env": api_key_env,
            "api_key": "",
            "models": list(current_config.model.gemini.models),
        }

    config["model"] = model_cfg
    try:
        _build_app_config(config)
    except ConfigValidationError as exc:
        return f"invalid config.yaml after update: {exc}"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return None
