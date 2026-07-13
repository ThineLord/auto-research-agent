from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit

import requests
import streamlit as st

from src.benchmarking import BENCHMARK_PRESETS
from src.cloud_free import (
    DISCOVERY_ARTIFACT_NAME,
    FREE_RUNNER_AUTO,
    FREE_RUNNER_MANUAL,
    FREE_RUNNER_PRESETS,
    FREE_RUNNER_QUALITY,
    FREE_RUNNER_VOLUME,
    PROFILE_ARTIFACT_NAME,
    build_cached_candidate_pool,
    build_candidate_pool,
    discover_free_cloud_models,
    filter_safe_text_models,
    initial_delay_seconds,
    load_discovery_artifact,
    load_profile_artifact,
    profile_free_cloud_models,
    recommend_free_cloud_model,
    save_discovery_artifact,
    save_profile_artifact,
)
from src.config import (
    DEFAULT_DRAFTING_MODE,
    DEFAULT_GEMINI_API_KEY_ENV,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_MODELS,
    DEFAULT_MODEL_NAME,
    MODEL_PROVIDER_GEMINI,
    MODEL_PROVIDER_OLLAMA,
    SUPPORTED_DRAFTING_MODES,
    SUPPORTED_MODEL_PROVIDERS,
    ConfigValidationError,
    format_model_label,
    load_app_config,
    query_ollama_models,
    save_default_model_name,
    save_default_model_selection,
)
from src.constants import UI_GEMINI_API_KEY_ENV
from src.llm import GeminiClient
from src.resume import build_resume_preview
from src.resume_safety import (
    resume_artifact_links_are_safe,
    validate_project_run_root,
    validate_resume_round_dir,
)
from src.run_analytics import analyze_run
from src.run_compare import compare_runs
from src.runtime import (
    get_active_process_meta,
    model_job_meta_path,
    run_meta_path,
    run_project_tests,
    start_background_process,
)
from src.storage import (
    artifact_path_exists,
    artifact_path_is_safe,
    ensure_artifact_paths_safe,
    ensure_project_runtime_paths_safe,
    list_artifact_directories,
    read_file_text,
    read_json_file,
    read_regular_text,
    tail_file_lines,
    write_file_text,
)
from ui.i18n import LANGUAGE_LABELS, translate
from ui.theme import DEFAULT_THEME, THEME_LABEL_KEYS, build_theme_css, normalize_theme

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT / "projects"
CONFIG_PATH = ROOT / "config.yaml"
CONFIG_EXAMPLE_PATH = ROOT / "config.example.yaml"
PUBLIC_SAFE_PROJECT_NAME = "example"
CANONICAL_ROOT = Path(
    os.environ.get(
        "AUTO_RESEARCH_AGENT_ROOT",
        str(ROOT),
    )
).resolve()
SUGGESTED_SMALLER_MODELS = ("llama3.2:3b", "phi3:mini", "qwen2.5:3b", "gemma2:2b")

AGENT_LOG_RE = re.compile(
    r"round=(?P<round>\d+)\s+\|\s+agent=(?P<agent>\w+)\s+\|\s+status=(?P<status>\w+)"
)
ROUND_ENTER_RE = re.compile(r"round_enter round=(?P<round>\d+)")
DELETE_NONE = "__none__"
FREE_RUNNER_LABEL_KEYS = {
    FREE_RUNNER_AUTO: "free_runner_auto",
    FREE_RUNNER_QUALITY: "free_runner_quality",
    FREE_RUNNER_VOLUME: "free_runner_volume",
    FREE_RUNNER_MANUAL: "free_runner_manual",
}
BENCHMARK_PRESET_LABEL_KEYS = {
    "free_smoke": "benchmark_preset_free_smoke",
    "free_eval": "benchmark_preset_free_eval",
    "paid_benchmark": "benchmark_preset_paid_benchmark",
    "stress_test": "benchmark_preset_stress_test",
}
DRAFTING_MODE_LABEL_KEYS = {
    "best_guided": "drafting_mode_best_guided",
    "fresh_from_task_with_review": "drafting_mode_fresh_with_review",
    "continue_from_previous_draft": "drafting_mode_continue_from_previous",
}
CLOUD_FREE_CACHE_IDENTITY_KEY = "cloud_free_cache_identity"
CLOUD_FREE_DISCOVERY_SESSION_KEY = "cloud_free_discovered_models"
CLOUD_FREE_PROFILE_SESSION_KEY = "cloud_free_profile_results"
OLLAMA_HEALTH_SESSION_KEY = "model_health"
GEMINI_HEALTH_SESSION_KEY = "gemini_model_health"
HEALTH_MESSAGE_REQUIRED_ARGS = {
    "health_no_model": frozenset(),
    "health_timeout": frozenset({"base_url"}),
    "health_api_unhealthy": frozenset({"base_url", "error"}),
    "health_model_missing": frozenset({"model"}),
    "health_model_ok": frozenset({"model"}),
    "gemini_health_missing_key": frozenset(),
    "gemini_health_failed": frozenset({"error"}),
    "gemini_health_ok": frozenset({"model"}),
}
SAFE_OLLAMA_HEALTH_PATH_SEGMENTS = frozenset({"api", "ollama", "proxy", "service"})


def relative_repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return f"<repo>/{path.name}"


def project_display_path(project_dir: Path) -> str:
    return relative_repo_path(project_dir)


def output_display_path(path: Path) -> str:
    return relative_repo_path(path)


def create_stop_signal(stop_signal_path: Path) -> bool:
    try:
        ensure_project_runtime_paths_safe(
            stop_signal_path.parent,
            anchor=stop_signal_path.parent.parent,
        )
        write_file_text(stop_signal_path, "STOP_REQUESTED\n")
    except OSError:
        return False
    return True


def load_ui_config() -> tuple[Any, bool]:
    try:
        return load_app_config(CONFIG_PATH), False
    except FileNotFoundError:
        return load_app_config(CONFIG_EXAMPLE_PATH), True


def default_project_index(projects: list[str], configured_project_name: str) -> int:
    if not projects:
        return 0
    if configured_project_name in projects:
        return projects.index(configured_project_name)
    if PUBLIC_SAFE_PROJECT_NAME in projects:
        return projects.index(PUBLIC_SAFE_PROJECT_NAME)
    return 0


def discover_project_names(projects_dir: Path) -> list[str]:
    try:
        return sorted(name for _mtime, name, _path in list_artifact_directories(projects_dir))
    except OSError:
        return []


def input_text_or_placeholder(path: Path, placeholder_key: str) -> str:
    if artifact_path_is_safe(path, allow_missing=False):
        return read_file_text(path)
    return t(placeholder_key)


def current_language() -> str:
    language = st.session_state.get("ui_language", "en")
    return str(language) if language in LANGUAGE_LABELS else "en"


def current_theme() -> str:
    return normalize_theme(str(st.session_state.get("ui_theme", DEFAULT_THEME)))


def t(key: str, **kwargs: Any) -> str:
    return translate(current_language(), key, **kwargs)


def ensure_ui_preferences() -> None:
    if st.session_state.get("ui_language") not in LANGUAGE_LABELS:
        st.session_state["ui_language"] = "en"
    st.session_state["ui_theme"] = current_theme()


def render_interface_controls() -> None:
    st.sidebar.header(t("sidebar_interface"))
    st.sidebar.selectbox(
        t("language_selector"),
        list(LANGUAGE_LABELS),
        format_func=lambda language: LANGUAGE_LABELS[language],
        key="ui_language",
    )
    st.sidebar.selectbox(
        t("theme_selector"),
        list(THEME_LABEL_KEYS),
        format_func=lambda theme: t(THEME_LABEL_KEYS[theme]),
        key="ui_theme",
    )


def localized_message(payload: dict[str, Any]) -> str:
    message_key = payload.get("message_key")
    if not message_key:
        return str(payload.get("message", ""))

    message_args = dict(payload.get("message_args", {}))
    if payload.get("model_mismatch"):
        message_args["model_note"] = t(
            "resume_model_note",
            checkpoint_model=payload.get("checkpoint_model", ""),
            selected_model=payload.get("selected_model", ""),
        )
    else:
        message_args.setdefault("model_note", "")
    return t(str(message_key), **message_args)


def localize_ollama_models_error(error: str) -> str:
    if error == "Ollama is not installed or not in PATH.":
        return t("ollama_not_installed")
    if error.startswith("Failed to query Ollama: "):
        return t("ollama_query_failed", detail=error.removeprefix("Failed to query Ollama: "))
    if error.startswith("Ollama is not available: "):
        return t("ollama_unavailable", detail=error.removeprefix("Ollama is not available: "))
    return error


def choose_model_picker_default(
    *,
    installed_model_names: Sequence[str],
    session_model: str | None,
    config_model: str,
    default_model: str = DEFAULT_MODEL_NAME,
) -> str:
    installed = [name.strip() for name in installed_model_names if name.strip()]
    if not installed:
        return ""

    for candidate in (session_model, config_model, default_model):
        model_name = str(candidate or "").strip()
        if model_name in installed:
            return model_name
    return installed[0]


def resolve_effective_model(
    *,
    selected_model: str | None,
    manual_model: str | None,
    config_model: str,
) -> str:
    manual_model = str(manual_model or "").strip()
    if manual_model:
        return manual_model
    selected_model = str(selected_model or "").strip()
    if selected_model:
        return selected_model
    return config_model.strip()


def resolve_effective_cloud_model(
    selected_model: str | None,
    manual_model: str | None,
    default_model: str,
) -> str:
    manual_model = str(manual_model or "").strip()
    if manual_model:
        return manual_model
    selected_model = str(selected_model or "").strip()
    if selected_model:
        return selected_model
    return default_model.strip()


def provider_model_label(provider: str, model: str) -> str:
    return format_model_label(provider, model)


def build_run_command(
    provider: str,
    mode: str,
    model: str,
    gemini_api_key_env: str | None = None,
    project: str | None = None,
    free_runner_preset: str | None = None,
    benchmark_preset: str | None = None,
    max_provider_quota_failures: int | None = None,
    drafting_mode: str | None = None,
    gemini_api_key_override_env: str | None = None,
) -> list[str]:
    mode_flags = {
        "diagnostic": ["--diagnostic"],
        "normal": [],
        "continuous": ["--continuous"],
        "resume": ["--resume"],
    }
    if mode not in mode_flags:
        raise ValueError(f"Unsupported run mode: {mode}")

    command = [
        sys.executable,
        "-m",
        "src.main",
        *mode_flags[mode],
        "--provider",
        provider,
        "--model",
        model,
    ]
    if project:
        command.extend(["--project", project])
    if provider == MODEL_PROVIDER_GEMINI and gemini_api_key_env:
        command.extend(["--gemini-api-key-env", gemini_api_key_env])
    if provider == MODEL_PROVIDER_GEMINI and gemini_api_key_override_env:
        command.extend(["--gemini-api-key-override-env", gemini_api_key_override_env])
    if provider == MODEL_PROVIDER_GEMINI and free_runner_preset:
        command.extend(["--free-runner-preset", free_runner_preset])
    if benchmark_preset:
        command.extend(["--benchmark-preset", benchmark_preset])
    if max_provider_quota_failures is not None:
        command.extend(["--max-provider-quota-failures", str(max(0, max_provider_quota_failures))])
    if drafting_mode:
        command.extend(["--drafting-mode", drafting_mode])
    return command


def build_provider_env_overrides(
    provider: str,
    api_key_env: str,
    api_key_value: str,
) -> dict[str, str]:
    if provider != MODEL_PROVIDER_GEMINI:
        return {}
    _ = api_key_env  # Retained for compatibility with existing helper callers.
    return {UI_GEMINI_API_KEY_ENV: api_key_value.strip()}


def has_gemini_api_key_source(
    *,
    api_key_env: str,
    api_key_value: str = "",
    config_api_key: str = "",
) -> bool:
    if api_key_value.strip() or config_api_key.strip():
        return True
    for env_name in (
        api_key_env.strip(),
        DEFAULT_GEMINI_API_KEY_ENV,
        "GOOGLE_API_KEY",
    ):
        if env_name and os.environ.get(env_name, "").strip():
            return True
    return False


def refresh_ollama_model_cache(*, base_url: str, timeout_seconds: int = 5) -> None:
    models, error = query_ollama_models(timeout_seconds=timeout_seconds, base_url=base_url)
    st.session_state["ollama_models"] = models
    st.session_state["ollama_models_error"] = error or ""


def _cloud_free_artifact_content_identity(
    project_dir: Path,
    artifact_name: str,
) -> tuple[str, str]:
    artifact_path = project_dir / "artifacts" / artifact_name
    try:
        content = read_regular_text(artifact_path, missing_ok=False)
    except FileNotFoundError:
        return ("missing", "")
    except UnicodeError:
        return ("unreadable", "")
    except OSError:
        return ("unsafe_or_unreadable", "")
    return ("sha256", hashlib.sha256(content.encode("utf-8")).hexdigest())


def cloud_free_cache_identity(project_dir: Path) -> tuple[object, ...]:
    project_dir = Path(project_dir)
    ensure_project_runtime_paths_safe(project_dir, anchor=project_dir.parent)
    canonical_project = project_dir.resolve(strict=True)
    project_metadata = project_dir.lstat()
    return (
        canonical_project.as_posix(),
        project_metadata.st_dev,
        project_metadata.st_ino,
        _cloud_free_artifact_content_identity(project_dir, DISCOVERY_ARTIFACT_NAME),
        _cloud_free_artifact_content_identity(project_dir, PROFILE_ARTIFACT_NAME),
    )


def _clear_cloud_free_session_cache(session_state: MutableMapping[str, Any]) -> None:
    session_state.pop(CLOUD_FREE_CACHE_IDENTITY_KEY, None)
    session_state.pop(CLOUD_FREE_DISCOVERY_SESSION_KEY, None)
    session_state.pop(CLOUD_FREE_PROFILE_SESSION_KEY, None)


def load_scoped_cloud_free_cache(
    project_dir: Path,
    session_state: MutableMapping[str, Any],
) -> tuple[list[Any], list[Any]]:
    try:
        identity = cloud_free_cache_identity(project_dir)
    except (OSError, RuntimeError):
        _clear_cloud_free_session_cache(session_state)
        return [], []
    discovered_models = session_state.get(CLOUD_FREE_DISCOVERY_SESSION_KEY)
    profile_results = session_state.get(CLOUD_FREE_PROFILE_SESSION_KEY)
    if (
        session_state.get(CLOUD_FREE_CACHE_IDENTITY_KEY) != identity
        or not isinstance(discovered_models, list)
        or not isinstance(profile_results, list)
    ):
        _clear_cloud_free_session_cache(session_state)
        try:
            for _attempt in range(2):
                discovered_models = load_discovery_artifact(project_dir)
                profile_results = load_profile_artifact(project_dir)
                observed_identity = cloud_free_cache_identity(project_dir)
                if observed_identity == identity:
                    session_state[CLOUD_FREE_DISCOVERY_SESSION_KEY] = discovered_models
                    session_state[CLOUD_FREE_PROFILE_SESSION_KEY] = profile_results
                    session_state[CLOUD_FREE_CACHE_IDENTITY_KEY] = identity
                    return discovered_models, profile_results
                identity = observed_identity
        except (OSError, RuntimeError):
            pass
        _clear_cloud_free_session_cache(session_state)
        return [], []
    return discovered_models, profile_results


def ollama_health_connection_scope(base_url: str) -> tuple[str, ...]:
    try:
        parsed = urlsplit(str(base_url or "").strip())
        hostname = parsed.hostname
    except ValueError:
        return ("invalid_endpoint",)
    if not parsed.scheme or not hostname:
        return ("invalid_endpoint",)
    try:
        port = parsed.port
    except ValueError:
        netloc_without_userinfo = parsed.netloc.rsplit("@", 1)[-1]
        numeric_port = re.search(r":([0-9]+)$", netloc_without_userinfo)
        port_scope = f"invalid_port:{numeric_port.group(1)}" if numeric_port else "invalid_port"
    else:
        if port is None:
            if parsed.scheme.lower() == "http":
                port = 80
            elif parsed.scheme.lower() == "https":
                port = 443
        port_scope = "" if port is None else str(port)
    normalized_path = parsed.path.rstrip("/") or "/"
    path_segments = tuple(segment for segment in normalized_path.split("/") if segment)
    path_is_non_secret = all(
        segment.lower() in SAFE_OLLAMA_HEALTH_PATH_SEGMENTS
        or re.fullmatch(r"v[0-9]+", segment.lower())
        for segment in path_segments
    )
    path_scope = (
        ("path", normalized_path)
        if path_is_non_secret
        else ("redacted_path", *(str(len(segment)) for segment in path_segments))
    )
    return (
        "endpoint",
        parsed.scheme.lower(),
        hostname.lower(),
        port_scope,
        *path_scope,
        "userinfo" if parsed.username is not None or parsed.password is not None else "anonymous",
        "query" if parsed.query else "no_query",
    )


def ollama_health_display_endpoint(base_url: str) -> str:
    scope = ollama_health_connection_scope(base_url)
    if not scope or scope[0] != "endpoint":
        return "<configured endpoint>"
    _label, scheme, hostname, port, *_non_secret_details = scope
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    if port.startswith("invalid_port"):
        return f"{scheme}://{display_host}:<invalid-port>"
    return f"{scheme}://{display_host}:{port}" if port else f"{scheme}://{display_host}"


def resolve_ui_gemini_api_key(session_value: str, config_value: str) -> str:
    return str(session_value or "").strip() or str(config_value or "").strip()


def gemini_health_connection_scope(
    *,
    api_key_env: str,
    session_key_present: bool,
    config_key_present: bool,
    environment: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    if session_key_present:
        return ("session_key",)
    if config_key_present:
        return ("config_key",)
    environment = os.environ if environment is None else environment
    configured_env = str(api_key_env or "").strip()
    built_in_envs = {DEFAULT_GEMINI_API_KEY_ENV, "GOOGLE_API_KEY"}
    if (
        configured_env
        and configured_env not in built_in_envs
        and str(environment.get(configured_env, "")).strip()
    ):
        return ("environment", configured_env)
    for env_name in ("GOOGLE_API_KEY", DEFAULT_GEMINI_API_KEY_ENV):
        if str(environment.get(env_name, "")):
            return ("environment", env_name)
    return ("missing",)


def build_model_health_identity(
    *,
    provider: str,
    model: str,
    connection_scope: Sequence[str],
) -> tuple[str, str, tuple[str, ...]]:
    return (
        str(provider or "").strip().lower(),
        str(model or "").strip(),
        tuple(str(part) for part in connection_scope),
    )


def store_scoped_health_result(
    session_state: MutableMapping[str, Any],
    *,
    key: str,
    identity: tuple[str, str, tuple[str, ...]],
    result: dict[str, Any],
) -> None:
    session_state[key] = {"identity": identity, "result": result}


def load_scoped_health_result(
    session_state: MutableMapping[str, Any],
    *,
    key: str,
    identity: tuple[str, str, tuple[str, ...]],
) -> dict[str, Any] | None:
    cached = session_state.get(key)
    if not isinstance(cached, Mapping) or cached.get("identity") != identity:
        session_state.pop(key, None)
        return None
    result = cached.get("result")
    message_key = result.get("message_key") if isinstance(result, dict) else None
    message_args = result.get("message_args") if isinstance(result, dict) else None
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("ok"), bool)
        or not isinstance(result.get("message"), str)
        or not isinstance(message_key, str)
        or message_key not in HEALTH_MESSAGE_REQUIRED_ARGS
        or not isinstance(message_args, Mapping)
        or not HEALTH_MESSAGE_REQUIRED_ARGS[message_key].issubset(message_args)
    ):
        session_state.pop(key, None)
        return None
    return result


def clear_session_health_result(key: str) -> None:
    st.session_state.pop(key, None)


def localized_stage(stage: Any) -> str:
    stage_text = str(stage)
    if stage_text == "Idle":
        return t("stage_idle")
    if stage_text == "starting":
        return t("stage_starting")
    if stage_text == "starting round":
        return t("stage_starting_round")
    if stage_text.startswith("after "):
        return t("stage_after_agent", agent=stage_text.removeprefix("after "))
    return stage_text


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _read_json_list_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(read_file_text(path))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [entry for entry in payload if isinstance(entry, dict)]


def check_ollama_model_health(
    *,
    base_url: str,
    selected_model: str,
    installed_model_names: Sequence[str],
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    model_name = selected_model.strip()
    if not model_name:
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": "No model selected.",
            "message_key": "health_no_model",
            "message_args": {},
        }

    display_endpoint = ollama_health_display_endpoint(base_url)
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        response = requests.get(url, timeout=timeout_seconds)
        response.raise_for_status()
        payload = response.json()
    except requests.Timeout:
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": f"Ollama API timed out at {display_endpoint}.",
            "message_key": "health_timeout",
            "message_args": {"base_url": display_endpoint},
        }
    except (requests.RequestException, ValueError) as exc:
        error_type = type(exc).__name__
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": f"Ollama API is not healthy at {display_endpoint}: {error_type}",
            "message_key": "health_api_unhealthy",
            "message_args": {"base_url": display_endpoint, "error": error_type},
        }

    api_models = [
        str(model.get("name", "")).strip()
        for model in payload.get("models", [])
        if isinstance(model, dict)
    ]
    available_models = {name for name in installed_model_names if name} | {
        name for name in api_models if name
    }
    model_ok = model_name in available_models
    if not model_ok:
        return {
            "ok": False,
            "api_ok": True,
            "model_ok": False,
            "message": f"Ollama is reachable, but `{model_name}` is not installed.",
            "message_key": "health_model_missing",
            "message_args": {"model": model_name},
        }
    return {
        "ok": True,
        "api_ok": True,
        "model_ok": True,
        "message": f"Ollama is reachable and `{model_name}` is installed.",
        "message_key": "health_model_ok",
        "message_args": {"model": model_name},
    }


def check_gemini_model_health(
    *,
    selected_model: str,
    api_key_env: str,
    api_key_value: str = "",
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    model_name = selected_model.strip()
    if not model_name:
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": "No model selected.",
            "message_key": "health_no_model",
            "message_args": {},
        }
    if not has_gemini_api_key_source(
        api_key_env=api_key_env,
        api_key_value=api_key_value,
    ):
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": "Gemini API key is missing.",
            "message_key": "gemini_health_missing_key",
            "message_args": {},
        }

    try:
        output = GeminiClient(
            model=model_name,
            api_key_env=api_key_env,
            api_key=api_key_value.strip(),
            timeout_seconds=timeout_seconds,
        ).generate(
            agent_name="health",
            system_prompt="Reply only with OK.",
            user_prompt="Reply with OK.",
            temperature=0.0,
            top_p=0.9,
        )
    except RuntimeError as exc:
        error_type = type(exc).__name__
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": f"Gemini health check failed: {error_type}",
            "message_key": "gemini_health_failed",
            "message_args": {"error": error_type},
        }

    if not output.strip():
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": "Gemini health check returned an empty response.",
            "message_key": "gemini_health_failed",
            "message_args": {"error": "empty response"},
        }
    return {
        "ok": True,
        "api_ok": True,
        "model_ok": True,
        "message": f"Gemini is reachable and `{model_name}` responded.",
        "message_key": "gemini_health_ok",
        "message_args": {"model": model_name},
    }


def check_model_health(
    *,
    provider: str = MODEL_PROVIDER_OLLAMA,
    base_url: str = "",
    selected_model: str,
    installed_model_names: Sequence[str] = (),
    api_key_env: str = DEFAULT_GEMINI_API_KEY_ENV,
    api_key_value: str = "",
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    if provider == MODEL_PROVIDER_GEMINI:
        return check_gemini_model_health(
            selected_model=selected_model,
            api_key_env=api_key_env,
            api_key_value=api_key_value,
            timeout_seconds=timeout_seconds,
        )
    return check_ollama_model_health(
        base_url=base_url,
        selected_model=selected_model,
        installed_model_names=installed_model_names,
        timeout_seconds=timeout_seconds,
    )


def infer_running_stage(
    *,
    log_text: str,
    checkpoint: dict[str, Any],
    run_meta: dict[str, Any],
) -> dict[str, Any]:
    run_active = bool(run_meta)
    latest_round = _safe_int(checkpoint.get("last_completed_round"))
    stage = "Idle"
    stage_status = "idle"

    for line in reversed(log_text.splitlines()):
        agent_match = AGENT_LOG_RE.search(line)
        if agent_match:
            latest_round = _safe_int(agent_match.group("round"), latest_round)
            agent = agent_match.group("agent")
            status = agent_match.group("status")
            if status == "start":
                stage = agent
                stage_status = "running"
            elif run_active:
                stage = f"after {agent}"
                stage_status = status
            else:
                stage = "Idle"
                stage_status = status
            break
        round_match = ROUND_ENTER_RE.search(line)
        if round_match:
            latest_round = _safe_int(round_match.group("round"), latest_round)
            if run_active:
                stage = "starting round"
                stage_status = "running"
            break

    if run_active and stage == "Idle":
        stage = "starting"
        stage_status = "running"

    return {
        "run_active": run_active,
        "pid": run_meta.get("pid", "N/A") if run_active else "N/A",
        "mode": run_meta.get("mode") or checkpoint.get("mode", "N/A"),
        "model": run_meta.get("model") or checkpoint.get("model", "N/A"),
        "round": latest_round or "N/A",
        "stage": stage,
        "stage_status": stage_status,
        "last_successful_agent": checkpoint.get("last_successful_agent", "N/A"),
        "best_score": checkpoint.get("best_score", "N/A"),
        "stop_reason": checkpoint.get("stop_reason", "N/A"),
        "can_resume": bool(checkpoint.get("can_resume", False)),
        "drafting_mode": run_meta.get("drafting_mode") or checkpoint.get("drafting_mode", "N/A"),
    }


def describe_resume_state(
    *,
    project_dir: Path,
    checkpoint: dict[str, Any],
    run_active: bool,
    selected_model: str,
) -> dict[str, Any]:
    if not checkpoint:
        return {
            "can_resume": False,
            "level": "info",
            "message": "No checkpoint exists yet. Run a workflow before resuming.",
            "message_key": "resume_no_checkpoint",
            "message_args": {},
            "details": {},
        }
    if run_active:
        return {
            "can_resume": False,
            "level": "warning",
            "message": "A run is active. Resume is blocked until the current run exits.",
            "message_key": "resume_blocked_active",
            "message_args": {},
            "details": {},
        }

    checkpoint_model = str(checkpoint.get("model", "")).strip()
    selected_model = selected_model.strip()
    model_note = ""
    model_mismatch = bool(
        checkpoint_model and selected_model and checkpoint_model != selected_model
    )
    if checkpoint_model and selected_model and checkpoint_model != selected_model:
        model_note = (
            f" Checkpoint model was `{checkpoint_model}`; selected model is `{selected_model}`."
        )

    preview = build_resume_preview(
        project_dir=project_dir,
        checkpoint=checkpoint,
        repo_root=ROOT,
    )
    run_id = str(preview.get("run_id") or checkpoint.get("run_id") or "N/A")
    last_completed_round = _safe_int(preview.get("last_completed_round"))
    next_round = _safe_int(preview.get("next_round"), last_completed_round + 1)
    stop_reason = str(preview.get("stop_reason") or checkpoint.get("stop_reason") or "unknown")
    details = {
        "run_id": run_id,
        "run_root": str(preview.get("run_root_display") or "N/A"),
        "last_completed_round": last_completed_round,
        "next_round": next_round,
        "stop_reason": stop_reason,
        "can_resume": bool(preview.get("can_resume")),
        "completed_round_files_preserved": bool(checkpoint.get("can_resume")),
        "next_round_status": preview.get("next_round_status", "unknown"),
        "next_round_safety_action": preview.get("next_round_safety_action", "none"),
        "next_round_path": preview.get("next_round_display", "N/A"),
        "next_round_blocks_resume": bool(preview.get("next_round_blocks_resume")),
        "next_round_existing_files": ", ".join(
            str(name) for name in preview.get("next_round_existing_files", [])
        )
        or "none",
    }
    if checkpoint.get("can_resume") and not preview.get("can_resume"):
        details["can_resume"] = False
        blocked_reason = str(preview.get("blocked_reason") or "unsafe_run_root")
        message_key = {
            "missing_run_root": "resume_missing_run_root",
            "stale_run_root": "resume_stale_checkpoint",
            "partial_next_round_exists": "resume_partial_next_round",
        }.get(blocked_reason, "resume_unsafe_checkpoint")
        message_args = (
            {
                "next_round_path": details["next_round_path"],
                "status": details["next_round_status"],
                "action": details["next_round_safety_action"],
            }
            if blocked_reason == "partial_next_round_exists"
            else {"run_root": details["run_root"]}
            if blocked_reason == "stale_run_root"
            else {}
        )
        return {
            "can_resume": False,
            "level": "warning",
            "message": str(preview.get("message") or "Resume checkpoint is unsafe."),
            "message_key": message_key,
            "message_args": message_args,
            "model_mismatch": model_mismatch,
            "checkpoint_model": checkpoint_model,
            "selected_model": selected_model,
            "details": details,
        }

    if preview.get("can_resume"):
        return {
            "can_resume": True,
            "level": "success",
            "message": f"Resume available from round {next_round}.{model_note}",
            "message_key": "resume_available",
            "message_args": {"next_round": next_round},
            "model_mismatch": model_mismatch,
            "checkpoint_model": checkpoint_model,
            "selected_model": selected_model,
            "details": details,
        }

    return {
        "can_resume": False,
        "level": "info",
        "message": f"Resume is unavailable. Last stop reason: `{stop_reason}`.{model_note}",
        "message_key": "resume_unavailable",
        "message_args": {"stop_reason": stop_reason},
        "model_mismatch": model_mismatch,
        "checkpoint_model": checkpoint_model,
        "selected_model": selected_model,
        "details": details,
    }


def detect_output_kind(path: Path) -> str:
    if path.suffix == ".json":
        return "json"
    if path.suffix == ".log":
        return "log"
    if path.suffix in {".md", ".markdown"}:
        return "markdown"
    return "text"


def resolve_run_artifact_paths(project_dir: Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Resolve UI run artifacts without trusting redundant checkpoint path fields."""
    run_root_text = str(checkpoint.get("run_root", "")).strip()
    run_root_requested = bool(run_root_text)
    run_root: Path | None
    run_scope_valid = True
    if run_root_requested:
        run_root, run_root_error = validate_project_run_root(
            project_dir=project_dir,
            run_root_value=run_root_text,
        )
        run_scope_valid = run_root_error is None and run_root is not None
    else:
        # Older project layouts stored these files directly in the selected project.
        run_root = project_dir

    artifact_root = run_root if run_scope_valid and run_root is not None else project_dir
    run_config_path = artifact_root / "run_config.json"
    run_summary_path = artifact_root / "run_summary.json"
    round_metrics_path = artifact_root / "round_metrics.json"
    run_manifest_path = artifact_root / "run_manifest.json"

    if run_scope_valid and run_root_requested:
        artifact_safety = {
            name: resume_artifact_links_are_safe(parent_dir=artifact_root, paths=(path,))
            for name, path in (
                ("run_config", run_config_path),
                ("run_summary", run_summary_path),
                ("round_metrics", round_metrics_path),
                ("run_manifest", run_manifest_path),
            )
        }
    elif run_scope_valid:
        artifact_safety = {
            name: artifact_path_is_safe(path, allow_missing=True)
            for name, path in (
                ("run_config", run_config_path),
                ("run_summary", run_summary_path),
                ("round_metrics", round_metrics_path),
                ("run_manifest", run_manifest_path),
            )
        }
    else:
        artifact_safety = {
            "run_config": False,
            "run_summary": False,
            "round_metrics": False,
            "run_manifest": False,
        }

    return {
        "run_root": artifact_root,
        "run_root_requested": run_root_requested,
        "run_scope_valid": run_scope_valid,
        "run_config": run_config_path,
        "run_summary": run_summary_path,
        "round_metrics": round_metrics_path,
        "run_manifest": run_manifest_path,
        **{f"{name}_safe": safe for name, safe in artifact_safety.items()},
    }


def _display_value(value: Any, default: str = "N/A") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value).strip()
    return text if text else default


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _short_commit(value: Any) -> str:
    commit = str(value or "").strip()
    return commit[:12] if commit else "N/A"


def build_run_metadata_rows(project_dir: Path, checkpoint: dict[str, Any]) -> list[dict[str, str]]:
    paths = resolve_run_artifact_paths(project_dir, checkpoint)
    run_config = (
        read_json_file(paths["run_config"])
        if paths["run_config_safe"] and paths["run_config"].exists()
        else {}
    )
    run_summary = (
        read_json_file(paths["run_summary"])
        if paths["run_summary_safe"] and paths["run_summary"].exists()
        else {}
    )
    if not run_config and not run_summary:
        return []

    model = run_config.get("model") if isinstance(run_config.get("model"), dict) else {}
    runtime = run_config.get("runtime") if isinstance(run_config.get("runtime"), dict) else {}
    git_meta = run_config.get("git") if isinstance(run_config.get("git"), dict) else {}
    resume = run_config.get("resume_eligibility")
    resume = resume if isinstance(resume, dict) else {}
    low_change_rounds = run_summary.get("low_previous_revised_change_rounds")
    low_change_count = len(low_change_rounds) if isinstance(low_change_rounds, list) else None
    rubric_averages = run_summary.get("rubric_subscore_averages")
    rubric_averages = rubric_averages if isinstance(rubric_averages, dict) else {}

    values = [
        ("run_meta_run_id", _first_present(run_config.get("run_id"), run_summary.get("run_id"))),
        (
            "run_meta_mode",
            _first_present(run_config.get("mode"), run_summary.get("mode"), checkpoint.get("mode")),
        ),
        (
            "run_meta_provider",
            _first_present(model.get("provider"), checkpoint.get("provider")),
        ),
        (
            "run_meta_model",
            _first_present(model.get("name"), run_summary.get("model"), checkpoint.get("model")),
        ),
        (
            "run_meta_drafting_mode",
            _first_present(
                run_config.get("drafting_mode"),
                run_summary.get("drafting_mode"),
                checkpoint.get("drafting_mode"),
            ),
        ),
        (
            "run_meta_max_rounds",
            _first_present(runtime.get("max_rounds"), checkpoint.get("max_rounds")),
        ),
        (
            "run_meta_completed_rounds",
            _first_present(
                run_config.get("completed_rounds"),
                run_summary.get("completed_rounds"),
                checkpoint.get("last_completed_round"),
            ),
        ),
        (
            "run_meta_best_score",
            _first_present(run_config.get("best_score"), run_summary.get("best_score")),
        ),
        (
            "run_meta_avg_revised_similarity",
            run_summary.get("avg_revised_similarity_to_previous"),
        ),
        (
            "run_meta_low_change_rounds",
            low_change_count,
        ),
        ("run_meta_rubric_rounds", run_summary.get("rubric_round_count")),
        (
            "run_meta_rubric_avg_evaluation",
            rubric_averages.get("evaluation_design_quality"),
        ),
        (
            "run_meta_stop_reason",
            _first_present(
                run_config.get("stop_reason"),
                run_summary.get("stop_reason"),
                checkpoint.get("stop_reason"),
            ),
        ),
        (
            "run_meta_resume",
            resume.get("can_resume")
            if "can_resume" in resume
            else run_config.get("can_resume", run_summary.get("can_resume")),
        ),
        ("run_meta_git_commit", _short_commit(git_meta.get("commit"))),
        ("run_meta_started_at", run_config.get("started_at")),
        ("run_meta_ended_at", run_config.get("ended_at")),
        (
            "run_meta_run_config_path",
            output_display_path(paths["run_config"]) if paths["run_config_safe"] else None,
        ),
        (
            "run_meta_run_summary_path",
            output_display_path(paths["run_summary"]) if paths["run_summary_safe"] else None,
        ),
        (
            "run_meta_round_metrics_path",
            output_display_path(paths["round_metrics"]) if paths["round_metrics_safe"] else None,
        ),
    ]
    return [{"field_key": field_key, "value": _display_value(value)} for field_key, value in values]


def discover_project_run_roots(project_dir: Path, *, limit: int = 12) -> list[Path]:
    try:
        runs_root = ensure_project_runtime_paths_safe(project_dir)
        if runs_root is None:
            return []
        run_roots = list_artifact_directories(runs_root)
    except OSError:
        return []
    return [
        path
        for _, _, path in sorted(
            run_roots,
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )[:limit]
    ]


def _count_text(value: Any) -> str:
    if isinstance(value, list):
        return str(len(value))
    return _display_value(value, "0")


def _artifact_path_display(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "N/A"
    return output_display_path(Path(text))


def build_run_comparison_rows(run_roots: Sequence[Path]) -> list[dict[str, Any]]:
    safe_run_roots = []
    for run_root_value in run_roots:
        run_root = Path(run_root_value)
        try:
            root_metadata = run_root.lstat()
        except OSError:
            continue
        if not stat.S_ISDIR(root_metadata.st_mode):
            continue
        if all(
            artifact_path_is_safe(run_root / filename, allow_missing=True)
            for filename in (
                "run_config.json",
                "run_summary.json",
                "run_manifest.json",
                "round_metrics.json",
            )
        ):
            safe_run_roots.append(run_root)
    comparison = compare_runs(safe_run_roots, safe_artifacts=True)
    rows: list[dict[str, Any]] = []
    for run in comparison.get("runs", []):
        if not isinstance(run, dict):
            continue
        rows.append(
            {
                "run_id": _display_value(run.get("run_id")),
                "run_path": _artifact_path_display(run.get("run_path") or run.get("run_root")),
                "provider": _display_value(run.get("provider")),
                "model": _display_value(run.get("model")),
                "drafting_mode": _display_value(run.get("drafting_mode")),
                "max_rounds": _display_value(run.get("max_rounds")),
                "completed_rounds": _display_value(run.get("completed_rounds")),
                "best_score": run.get("best_score"),
                "average_score": run.get("average_score"),
                "stop_reason": _display_value(run.get("stop_reason")),
                "timeout_count": _count_text(run.get("timeout_count")),
                "error_count": _count_text(run.get("error_count")),
                "agent_elapsed_s": _display_value(run.get("total_agent_elapsed_seconds")),
                "estimated_tokens": _display_value(run.get("total_estimated_tokens")),
                "avg_revised_similarity": _display_value(
                    run.get("avg_revised_similarity_to_previous")
                ),
                "low_change_rounds": _display_value(run.get("low_previous_revised_change_count")),
                "rubric_rounds": _display_value(run.get("rubric_round_count")),
                "rubric_avg_evaluation": _display_value(run.get("rubric_avg_evaluation")),
                "rubric_avg_actionability": _display_value(run.get("rubric_avg_actionability")),
                "run_config_path": _artifact_path_display(run.get("run_config_path")),
                "run_summary_path": _artifact_path_display(run.get("run_summary_path")),
                "metadata_status": _display_value(run.get("metadata_status")),
            }
        )
    return rows


def _has_run_artifacts(run_root: Path) -> bool:
    return any(
        (run_root / filename).exists()
        for filename in ("run_config.json", "run_summary.json", "round_metrics.json")
    )


def build_run_analytics_dashboard(project_dir: Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    paths = resolve_run_artifact_paths(project_dir, checkpoint)
    run_root = paths["run_root"]
    run_summary = (
        read_json_file(paths["run_summary"])
        if paths["run_summary_safe"] and paths["run_summary"].exists()
        else {}
    )
    round_metric_entries = (
        _read_json_list_file(paths["round_metrics"]) if paths["round_metrics_safe"] else []
    )
    use_legacy_project_history = paths["run_scope_valid"] and not paths["run_root_requested"]
    score_rows = (
        load_score_history_rows(project_dir / "score_history.json")
        if use_legacy_project_history
        else []
    )
    if not score_rows and round_metric_entries:
        score_rows = _flatten_metric_rows(round_metric_entries)

    analysis: dict[str, Any] = {}
    analysis_artifacts_safe = all(
        paths[f"{name}_safe"]
        for name in ("run_config", "run_summary", "round_metrics", "run_manifest")
    )
    if (
        paths["run_scope_valid"]
        and analysis_artifacts_safe
        and run_root.exists()
        and _has_run_artifacts(run_root)
    ):
        analysis = analyze_run(run_root, safe_artifacts=True)
    rounds = analysis.get("rounds") if isinstance(analysis.get("rounds"), dict) else {}
    score = analysis.get("score") if isinstance(analysis.get("score"), dict) else {}
    robustness = analysis.get("robustness") if isinstance(analysis.get("robustness"), dict) else {}
    cost_ready = analysis.get("cost_ready") if isinstance(analysis.get("cost_ready"), dict) else {}

    completed_rounds = _first_present(
        rounds.get("completed_rounds"),
        run_summary.get("completed_rounds"),
        checkpoint.get("last_completed_round"),
        len(score_rows) if score_rows else None,
    )
    best_score = _first_present(
        score.get("best_score"),
        run_summary.get("best_score"),
        _max_numeric(score_rows, "score"),
    )
    timeout_count = _first_present(
        robustness.get("timeout_count"),
        run_summary.get("timeout_count"),
        sum(1 for row in score_rows if row.get("timeout")),
    )
    error_count = _first_present(
        robustness.get("error_count"),
        run_summary.get("error_count"),
        sum(_safe_int(row.get("errors")) for row in score_rows),
    )
    total_agent_elapsed = _first_present(
        cost_ready.get("total_agent_elapsed_seconds"),
        run_summary.get("total_agent_elapsed_seconds"),
        _sum_numeric(score_rows, "round_s"),
    )
    total_estimated_tokens = _first_present(
        cost_ready.get("total_estimated_tokens"),
        run_summary.get("total_estimated_tokens"),
        _sum_numeric(score_rows, "estimated_total_tokens"),
    )
    cards = [
        {"label_key": "analytics_best_score", "value": best_score},
        {"label_key": "analytics_completed_rounds", "value": completed_rounds},
        {
            "label_key": "analytics_timeout_errors",
            "value": f"{_display_value(timeout_count, '0')} / {_display_value(error_count, '0')}",
        },
        {"label_key": "analytics_agent_elapsed", "value": _format_seconds(total_agent_elapsed)},
        {"label_key": "analytics_estimated_tokens", "value": total_estimated_tokens},
    ]
    source_candidates = (
        (paths["run_summary"], paths["run_summary_safe"]),
        (paths["round_metrics"], paths["round_metrics_safe"]),
        (project_dir / "score_history.json", use_legacy_project_history),
    )
    source_paths = [
        output_display_path(path)
        for path, path_safe in source_candidates
        if path_safe and path.exists()
    ]
    return {
        "available": bool(score_rows or run_summary or round_metric_entries),
        "cards": cards,
        "score_rows": _score_trend_rows(score_rows),
        "rubric_rows": _rubric_trend_rows(score_rows),
        "similarity_rows": _similarity_trend_rows(score_rows),
        "agent_timing_rows": _agent_timing_rows(score_rows),
        "token_rows": _token_rows(score_rows),
        "sources": source_paths,
    }


def _flatten_metric_rows(entries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        timings = entry.get("agent_timings_seconds")
        timings = timings if isinstance(timings, dict) else {}
        evolution = entry.get("evolution_metrics")
        evolution = evolution if isinstance(evolution, dict) else {}
        rubric = entry.get("judge_rubric")
        rubric = rubric if isinstance(rubric, dict) else {}
        rows.append(
            {
                "round": entry.get("round"),
                "score": entry.get("score"),
                "timeout": entry.get("timeout_this_round", False),
                "errors": len(entry.get("errors") or []),
                "draft_s": timings.get("draft", 0.0),
                "review_s": timings.get("review", 0.0),
                "revise_s": timings.get("revise", 0.0),
                "judge_s": timings.get("judge", 0.0),
                "round_s": entry.get("round_runtime_seconds", 0.0),
                "estimated_input_tokens": entry.get("estimated_input_tokens"),
                "estimated_output_tokens": entry.get("estimated_output_tokens"),
                "estimated_total_tokens": entry.get("estimated_total_tokens"),
                "score_delta_vs_previous": evolution.get("score_delta_vs_previous"),
                "draft_to_revised_similarity": evolution.get("draft_to_revised_similarity"),
                "revised_similarity_to_previous": evolution.get("revised_similarity_to_previous"),
                "rubric_evaluation_design_quality": rubric.get("evaluation_design_quality"),
                "rubric_tomorrow_actionability": rubric.get("tomorrow_actionability"),
            }
        )
    return rows


def _sum_numeric(rows: Sequence[dict[str, Any]], key: str) -> float | int | None:
    values = [_safe_float(row.get(key)) for row in rows]
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    total = sum(numbers)
    return round(total, 3)


def _max_numeric(rows: Sequence[dict[str, Any]], key: str) -> float | None:
    values = [_safe_float(row.get(key)) for row in rows]
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return round(max(numbers), 3)


def _format_seconds(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    return f"{numeric:.2f}s"


def _score_trend_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    trend_rows: list[dict[str, Any]] = []
    for row in rows:
        score = _safe_float(row.get("score"))
        if score is None:
            continue
        trend_rows.append(
            {
                "round": row.get("round"),
                "score": score,
                "score_delta": row.get("score_delta_vs_previous"),
            }
        )
    return trend_rows


def _rubric_trend_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    trend_rows: list[dict[str, Any]] = []
    for row in rows:
        evaluation = _safe_float(row.get("rubric_evaluation_design_quality"))
        actionability = _safe_float(row.get("rubric_tomorrow_actionability"))
        if evaluation is None and actionability is None:
            continue
        trend_rows.append(
            {
                "round": row.get("round"),
                "evaluation": evaluation,
                "actionability": actionability,
            }
        )
    return trend_rows


def _similarity_trend_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    trend_rows: list[dict[str, Any]] = []
    for row in rows:
        draft_revised = _safe_float(row.get("draft_to_revised_similarity"))
        revised_previous = _safe_float(row.get("revised_similarity_to_previous"))
        if draft_revised is None and revised_previous is None:
            continue
        trend_rows.append(
            {
                "round": row.get("round"),
                "draft_to_revised": draft_revised,
                "revised_to_previous": revised_previous,
            }
        )
    return trend_rows


def _agent_timing_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "round": row.get("round"),
            "draft_s": row.get("draft_s"),
            "review_s": row.get("review_s"),
            "revise_s": row.get("revise_s"),
            "judge_s": row.get("judge_s"),
            "round_s": row.get("round_s"),
        }
        for row in rows
        if any(
            _safe_float(row.get(key)) is not None
            for key in ("draft_s", "review_s", "revise_s", "judge_s")
        )
    ]


def _token_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "round": row.get("round"),
            "input_tokens": row.get("estimated_input_tokens"),
            "output_tokens": row.get("estimated_output_tokens"),
            "total_tokens": row.get("estimated_total_tokens"),
        }
        for row in rows
        if _safe_float(row.get("estimated_total_tokens")) is not None
    ]


def render_run_analytics_dashboard(project_dir: Path, checkpoint: dict[str, Any]) -> None:
    dashboard = build_run_analytics_dashboard(project_dir, checkpoint)
    st.subheader(t("run_analytics_dashboard"))
    if not dashboard["available"]:
        st.info(t("run_analytics_empty"))
        return

    metric_columns = st.columns(len(dashboard["cards"]))
    for column, card in zip(metric_columns, dashboard["cards"]):
        column.metric(t(str(card["label_key"])), _display_value(card.get("value")))

    score_tab, rubric_tab, similarity_tab, timing_tab, token_tab = st.tabs(
        [
            t("analytics_score_trend"),
            t("analytics_rubric_trend"),
            t("analytics_similarity_trend"),
            t("analytics_agent_timing"),
            t("analytics_token_estimates"),
        ]
    )
    _render_dashboard_table_chart(
        score_tab,
        dashboard["score_rows"],
        empty_key="analytics_score_empty",
        x="round",
        y=["score"],
    )
    _render_dashboard_table_chart(
        rubric_tab,
        dashboard["rubric_rows"],
        empty_key="analytics_rubric_empty",
        x="round",
        y=["evaluation", "actionability"],
    )
    _render_dashboard_table_chart(
        similarity_tab,
        dashboard["similarity_rows"],
        empty_key="analytics_similarity_empty",
        x="round",
        y=["draft_to_revised", "revised_to_previous"],
    )
    _render_dashboard_table_chart(
        timing_tab,
        dashboard["agent_timing_rows"],
        empty_key="analytics_timing_empty",
        x="round",
        y=["draft_s", "review_s", "revise_s", "judge_s"],
    )
    _render_dashboard_table_chart(
        token_tab,
        dashboard["token_rows"],
        empty_key="analytics_tokens_empty",
        x="round",
        y=["input_tokens", "output_tokens", "total_tokens"],
    )
    if dashboard["sources"]:
        st.caption(t("analytics_artifact_sources"))
        st.code("\n".join(dashboard["sources"]), language="text")


def _render_dashboard_table_chart(
    tab: Any,
    rows: list[dict[str, Any]],
    *,
    empty_key: str,
    x: str,
    y: list[str],
) -> None:
    with tab:
        if not rows:
            st.info(t(empty_key))
            return
        st.dataframe(rows, width="stretch", hide_index=True)
        chart_y = [key for key in y if any(_safe_float(row.get(key)) is not None for row in rows)]
        if chart_y:
            st.line_chart(rows, x=x, y=chart_y)


def build_output_catalog(project_dir: Path, checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    paths = resolve_run_artifact_paths(project_dir, checkpoint)
    run_root = (
        paths["run_root"] if paths["run_scope_valid"] and paths["run_root"] != project_dir else None
    )
    catalog = [
        {
            "label": "Best output",
            "label_key": "output_best",
            "path": project_dir / "best_output.md",
        },
        {
            "label": "Final session report",
            "label_key": "output_final_report",
            "path": project_dir / "final_session_report.md",
        },
        {
            "label": "Interrupted report",
            "label_key": "output_interrupted_report",
            "path": project_dir / "interrupted_report.md",
        },
        {
            "label": "Checkpoint",
            "label_key": "output_checkpoint",
            "path": project_dir / "checkpoint.json",
        },
        {
            "label": "Run config",
            "label_key": "output_run_config",
            "path": paths["run_config"] if paths["run_config_safe"] else None,
            "path_safe": paths["run_config_safe"],
            "missing_key": "missing_run_config",
        },
        {
            "label": "Run summary",
            "label_key": "output_run_summary",
            "path": paths["run_summary"] if paths["run_summary_safe"] else None,
            "path_safe": paths["run_summary_safe"],
            "missing_key": "missing_run_summary",
        },
        {
            "label": "Round metrics",
            "label_key": "output_round_metrics",
            "path": paths["round_metrics"] if paths["round_metrics_safe"] else None,
            "path_safe": paths["round_metrics_safe"],
            "missing_key": "missing_round_metrics",
        },
        {
            "label": "Score history",
            "label_key": "output_score_history",
            "path": project_dir / "score_history.json",
        },
        {"label": "Run log", "label_key": "output_run_log", "path": project_dir / "run.log"},
        {
            "label": "Model operation log",
            "label_key": "output_model_ops_log",
            "path": project_dir / "model_ops.log",
        },
        {
            "label": "Cloud free discovery",
            "label_key": "output_cloud_free_discovery",
            "path": project_dir / "artifacts" / "cloud_free_models.json",
        },
        {
            "label": "Cloud free profile",
            "label_key": "output_cloud_free_profile",
            "path": project_dir / "artifacts" / "cloud_free_profile.json",
        },
    ]

    round_index = _safe_int(checkpoint.get("last_completed_round"))
    if run_root and round_index > 0 and run_root.exists():
        round_dir = run_root / f"round_{round_index:02d}"
        safe_round_dir, round_error = validate_resume_round_dir(
            run_root=run_root,
            round_dir=round_dir,
        )
        if round_error is None and safe_round_dir is not None:
            round_outputs = [
                {
                    "label": "Latest round draft",
                    "label_key": "output_latest_draft",
                    "path": safe_round_dir / "01_draft.md",
                },
                {
                    "label": "Latest round review",
                    "label_key": "output_latest_review",
                    "path": safe_round_dir / "02_review.md",
                },
                {
                    "label": "Latest round revised",
                    "label_key": "output_latest_revised",
                    "path": safe_round_dir / "03_revised.md",
                },
                {
                    "label": "Latest round judge",
                    "label_key": "output_latest_judge",
                    "path": safe_round_dir / "04_judge.md",
                },
            ]
            for item in round_outputs:
                path_safe = resume_artifact_links_are_safe(
                    parent_dir=safe_round_dir,
                    paths=(item["path"],),
                )
                item["path_safe"] = path_safe
                if not path_safe:
                    item["path"] = None
            catalog.extend(round_outputs)

    resolved_catalog = []
    for item in catalog:
        path = item["path"]
        path_safe = bool(item.get("path_safe", True)) and (
            path is None or artifact_path_is_safe(path, allow_missing=True)
        )
        path_exists = bool(
            path_safe and path is not None and artifact_path_is_safe(path, allow_missing=False)
        )
        resolved_catalog.append(
            {
                "label": item["label"],
                "label_key": item["label_key"],
                "path": path if path_safe else None,
                "kind": detect_output_kind(path) if path is not None else "text",
                "exists": path_exists,
                "missing_key": item.get("missing_key", "output_not_generated"),
            }
        )
    return resolved_catalog


def load_score_history_rows(score_history_path: Path) -> list[dict[str, Any]]:
    try:
        content = read_file_text(score_history_path)
        if not content:
            return []
        payload = json.loads(content)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []

    rows: list[dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        timings = entry.get("agent_timings_seconds")
        timings = timings if isinstance(timings, dict) else {}
        evolution = entry.get("evolution_metrics")
        evolution = evolution if isinstance(evolution, dict) else {}
        rubric = entry.get("judge_rubric")
        rubric = rubric if isinstance(rubric, dict) else {}
        rows.append(
            {
                "round": entry.get("round"),
                "score": entry.get("score"),
                "improved": entry.get("improved"),
                "drafting_mode": entry.get("drafting_mode", ""),
                "timeout": entry.get("timeout_this_round", False),
                "invalid_score": entry.get("invalid_score_this_round", False),
                "errors": len(entry.get("errors") or []),
                "draft_s": timings.get("draft", 0.0),
                "review_s": timings.get("review", 0.0),
                "revise_s": timings.get("revise", 0.0),
                "judge_s": timings.get("judge", 0.0),
                "round_s": entry.get("round_runtime_seconds", 0.0),
                "estimated_input_tokens": entry.get("estimated_input_tokens"),
                "estimated_output_tokens": entry.get("estimated_output_tokens"),
                "estimated_total_tokens": entry.get("estimated_total_tokens"),
                "score_delta_vs_previous": evolution.get("score_delta_vs_previous"),
                "draft_to_revised_similarity": evolution.get("draft_to_revised_similarity"),
                "revised_similarity_to_previous": evolution.get("revised_similarity_to_previous"),
                "rubric_evaluation_design_quality": rubric.get("evaluation_design_quality"),
                "rubric_tomorrow_actionability": rubric.get("tomorrow_actionability"),
            }
        )
    return rows


def live_refresh_interval(auto_refresh: bool) -> str | None:
    return "2s" if auto_refresh else None


def project_path(project_name: str) -> Path:
    return PROJECTS_DIR / project_name


def is_canonical_root() -> bool:
    return ROOT.resolve() == CANONICAL_ROOT


def render_runtime_location_check() -> None:
    st.sidebar.caption(t("app_root_label"))
    st.sidebar.code("<repo>", language="text")
    if is_canonical_root():
        st.sidebar.success(t("canonical_root_success"))
    else:
        st.error(t("canonical_root_error"))
    with st.sidebar.expander(t("advanced_paths")):
        st.caption(t("current_root_path"))
        st.code(str(ROOT), language="text")
        st.caption(t("canonical_root_path"))
        st.code(str(CANONICAL_ROOT), language="text")


def render_process_result(result, success_key: str, **kwargs: Any) -> None:
    if result.error:
        st.error(t("process_error_prefix", error=result.error))
    elif result.pid:
        st.success(t(success_key, pid=result.pid, **kwargs))


def render_live_progress_and_logs(
    *,
    proj_path: Path,
    run_log_path: Path,
    model_job_log_path: Path,
    checkpoint_path: Path,
    stop_signal_path: Path,
    default_model: str,
) -> None:
    try:
        ensure_project_runtime_paths_safe(proj_path, anchor=proj_path.parent)
    except OSError:
        st.warning(t("unsafe_project_paths"))
        return
    run_meta = get_active_process_meta(run_meta_path(proj_path))
    checkpoint = read_json_file(checkpoint_path)
    run_log_text = tail_file_lines(run_log_path, max_lines=240)

    progress = infer_running_stage(
        log_text=run_log_text,
        checkpoint=checkpoint,
        run_meta=run_meta,
    )
    p1, p2, p3, p4 = st.columns(4)
    p1.metric(t("metric_mode"), str(progress["mode"]))
    p2.metric(t("metric_round"), str(progress["round"]))
    p3.metric(t("metric_stage"), localized_stage(progress["stage"]))
    p4.metric(t("metric_best_score"), str(progress["best_score"]))
    st.write(t("pid_line", pid=progress["pid"]))
    st.write(t("model_line", model=progress["model"]))
    st.write(t("drafting_mode_line", mode=progress["drafting_mode"]))
    st.write(t("last_successful_agent", agent=progress["last_successful_agent"]))
    st.write(t("stop_reason", reason=progress["stop_reason"]))
    st.write(
        t(
            "stop_signal_present",
            present=artifact_path_exists(stop_signal_path, allow_directory=True),
        )
    )
    st.write(t("selected_model", model=st.session_state.get("selected_model", default_model)))
    cloud_free_status = checkpoint.get("cloud_free", {})
    if isinstance(cloud_free_status, dict) and cloud_free_status:
        st.caption(t("cloud_free_runtime_status"))
        cf1, cf2, cf3, cf4 = st.columns(4)
        cf1.metric(t("cloud_free_status"), str(cloud_free_status.get("status", "N/A")))
        cf2.metric(
            t("cloud_free_delay"),
            str(cloud_free_status.get("current_delay_seconds", "N/A")),
        )
        cf3.metric(
            t("cloud_free_recent_429"),
            str(cloud_free_status.get("recent_429_count", "N/A")),
        )
        cf4.metric(
            t("cloud_free_rounds_hour"),
            str(cloud_free_status.get("estimated_completed_rounds_per_hour", "N/A")),
        )
    if checkpoint.get("paused_until_reset"):
        st.warning(str(checkpoint.get("pause_message", "")))

    st.subheader(t("live_logs_panel"))
    st.code(run_log_text or t("no_logs_yet"), language="text")
    st.caption(t("model_operation_logs"))
    st.code(
        tail_file_lines(model_job_log_path, max_lines=120) or t("no_model_operation_logs"),
        language="text",
    )


def main() -> None:
    st.set_page_config(page_title="Auto Research Agent", layout="wide")
    ensure_ui_preferences()
    st.markdown(build_theme_css(current_theme()), unsafe_allow_html=True)
    render_interface_controls()
    st.title(t("app_title"))
    render_runtime_location_check()
    try:
        app_config, using_example_config = load_ui_config()
    except ConfigValidationError as exc:
        st.error(t("config_error", error=exc))
        st.stop()
    if using_example_config:
        st.info(t("using_example_config"))

    st.subheader(t("quick_actions"))
    quick_test_col, quick_status_col = st.columns([1, 3])
    with quick_test_col:
        if st.button(t("run_tests"), key="run_tests_quick"):
            st.session_state["test_result"] = run_project_tests(ROOT)
    with quick_status_col:
        quick_test_result = st.session_state.get("test_result")
        if quick_test_result:
            if quick_test_result["ok"]:
                st.success(t("tests_passed_short", elapsed=quick_test_result["elapsed"]))
            else:
                st.error(t("tests_failed_short", elapsed=quick_test_result["elapsed"]))
        else:
            st.info(t("quick_tests_help"))

    projects = discover_project_names(PROJECTS_DIR)
    default_index = default_project_index(projects, app_config.project_name)
    selected_project = st.selectbox(
        t("project_selector"), projects, index=default_index if projects else None
    )
    if not selected_project:
        st.warning(t("no_project_found"))
        return
    if app_config.project_name and app_config.project_name not in projects:
        st.warning(t("configured_project_missing", project=app_config.project_name))
    elif selected_project != app_config.project_name and app_config.project_name in projects:
        st.info(
            t(
                "using_public_safe_project",
                selected=selected_project,
                configured=app_config.project_name,
            )
        )

    proj_path = project_path(selected_project)
    try:
        ensure_project_runtime_paths_safe(proj_path, anchor=PROJECTS_DIR)
    except OSError:
        st.error(t("unsafe_project_paths"))
        return
    st.write(t("project_path", path=project_display_path(proj_path)))

    task_path = proj_path / "task.md"
    memory_path = proj_path / "memory.md"
    run_log_path = proj_path / "run.log"
    model_job_log_path = proj_path / "model_ops.log"
    checkpoint_path = proj_path / "checkpoint.json"
    stop_signal_path = proj_path / "STOP_REQUESTED"
    run_meta = get_active_process_meta(run_meta_path(proj_path))
    model_job_meta = get_active_process_meta(model_job_meta_path(proj_path))
    checkpoint = read_json_file(checkpoint_path)

    col_input_left, col_input_right = st.columns(2)
    with col_input_left:
        task_text = st.text_area(
            t("input_editor_task"),
            value=input_text_or_placeholder(task_path, "task_placeholder"),
            height=260,
        )
        if not artifact_path_is_safe(task_path, allow_missing=False):
            st.caption(t("task_missing_help"))
    with col_input_right:
        memory_text = st.text_area(
            t("input_editor_memory"),
            value=input_text_or_placeholder(memory_path, "memory_placeholder"),
            height=260,
        )
        if not artifact_path_is_safe(memory_path, allow_missing=False):
            st.caption(t("memory_optional_help"))
    if st.button(t("save_input")):
        try:
            ensure_artifact_paths_safe((task_path, memory_path))
            write_file_text(task_path, task_text)
            write_file_text(memory_path, memory_text)
        except OSError:
            st.error(t("input_save_failed"))
        else:
            st.success(t("input_saved"))

    st.subheader(t("run_controls"))
    run_active = bool(run_meta)
    model_job_active = bool(model_job_meta)
    blocked = run_active or model_job_active
    if run_active:
        st.info(t("run_active", pid=run_meta.get("pid"), command=run_meta.get("command")))
    if model_job_active:
        st.warning(
            t(
                "model_job_active",
                pid=model_job_meta.get("pid"),
                command=model_job_meta.get("command"),
            )
        )

    default_model = app_config.model.name
    default_provider = (
        app_config.model.provider
        if app_config.model.provider in SUPPORTED_MODEL_PROVIDERS
        else MODEL_PROVIDER_OLLAMA
    )
    if st.session_state.get("selected_provider") not in SUPPORTED_MODEL_PROVIDERS:
        st.session_state["selected_provider"] = default_provider
    selected_provider = st.selectbox(
        t("model_provider"),
        [MODEL_PROVIDER_OLLAMA, MODEL_PROVIDER_GEMINI],
        format_func=lambda provider: (
            t("provider_local_ollama")
            if provider == MODEL_PROVIDER_OLLAMA
            else t("provider_cloud_gemini")
        ),
        key="selected_provider",
    )
    run_process_blocked = run_active or (
        model_job_active and selected_provider == MODEL_PROVIDER_OLLAMA
    )

    models: list[dict[str, Any]] = []
    models_error = ""
    installed_model_names: list[str] = []
    effective_model = ""
    model_label = ""
    run_model_blocked = True
    gemini_api_key_env = app_config.model.gemini.api_key_env
    provider_env_overrides: dict[str, str] = {}

    if selected_provider == MODEL_PROVIDER_OLLAMA:
        if "ollama_models" not in st.session_state or "ollama_models_error" not in st.session_state:
            refresh_ollama_model_cache(base_url=app_config.ollama_base_url)

        st.markdown(f"**{t('installed_ollama_models')}**")
        refresh_col, model_status_col = st.columns([1, 4])
        with refresh_col:
            if st.button(t("refresh_models")):
                st.session_state.pop(OLLAMA_HEALTH_SESSION_KEY, None)
                refresh_ollama_model_cache(base_url=app_config.ollama_base_url)
                st.session_state["model_list_refreshed"] = True

        models = list(st.session_state.get("ollama_models", []))
        models_error = str(st.session_state.get("ollama_models_error", "") or "")
        model_list_refreshed = bool(st.session_state.pop("model_list_refreshed", False))
        installed_model_names = [m["name"] for m in models if str(m.get("name", "")).strip()]

        with model_status_col:
            if models_error:
                st.error(
                    t(
                        "ollama_models_error_prefix",
                        error=localize_ollama_models_error(models_error),
                    )
                )
            elif not installed_model_names:
                st.warning(t("no_ollama_models_detected"))
                st.caption(
                    t("suggested_smaller_models", models=", ".join(SUGGESTED_SMALLER_MODELS))
                )
            elif model_list_refreshed:
                st.success(t("model_list_refreshed"))
            else:
                st.info(t("use_selected_model"))

        dropdown_default = choose_model_picker_default(
            installed_model_names=installed_model_names,
            session_model=st.session_state.get("selected_model_picker")
            or st.session_state.get("selected_model"),
            config_model=default_model,
        )
        if (
            installed_model_names
            and st.session_state.get("selected_model_picker") not in installed_model_names
        ):
            st.session_state["selected_model_picker"] = dropdown_default
        st.session_state.setdefault("manual_model_name", "")

        picker_col, manual_col, effective_col = st.columns([2, 2, 2])
        with picker_col:
            if installed_model_names:
                selected_model = st.selectbox(
                    t("model_selector"),
                    installed_model_names,
                    index=installed_model_names.index(dropdown_default)
                    if dropdown_default in installed_model_names
                    else 0,
                    key="selected_model_picker",
                )
            else:
                selected_model = ""
                st.caption(t("no_installed_model"))
        with manual_col:
            manual_model_name = st.text_input(
                t("manual_model_name"),
                key="manual_model_name",
                placeholder=default_model,
                help=t("manual_model_help"),
            )
        effective_model = resolve_effective_model(
            selected_model=selected_model,
            manual_model=manual_model_name,
            config_model=default_model,
        )
        model_label = provider_model_label(selected_provider, effective_model)
        st.session_state["selected_model"] = model_label
        with effective_col:
            st.write(t("effective_model", model=effective_model or t("none_option")))
        run_model_blocked = bool(models_error) or not effective_model
    else:
        st.markdown(f"**{t('cloud_model_settings')}**")
        st.caption(t("cloud_model_management_note"))
        gemini_api_key_env = st.text_input(
            t("gemini_api_key_env"),
            value=app_config.model.gemini.api_key_env,
            key="gemini_api_key_env",
            on_change=clear_session_health_result,
            args=(GEMINI_HEALTH_SESSION_KEY,),
        )
        gemini_api_key_password = st.text_input(
            t("gemini_api_key_password"),
            type="password",
            key="gemini_api_key_password",
            help=t("gemini_api_key_password_help"),
            on_change=clear_session_health_result,
            args=(GEMINI_HEALTH_SESSION_KEY,),
        )
        gemini_session_api_key = gemini_api_key_password.strip()
        gemini_config_api_key = app_config.model.gemini.api_key.strip()
        gemini_inline_api_key = resolve_ui_gemini_api_key(
            gemini_session_api_key,
            gemini_config_api_key,
        )
        cloud_models = list(app_config.model.gemini.models or DEFAULT_GEMINI_MODELS)
        cloud_default_model = (
            app_config.model.name
            if app_config.model.provider == MODEL_PROVIDER_GEMINI
            else DEFAULT_GEMINI_MODEL
        )
        key_available = has_gemini_api_key_source(
            api_key_env=gemini_api_key_env,
            api_key_value=gemini_inline_api_key,
        )
        if not key_available:
            st.warning(t("gemini_health_missing_key"))
        provider_env_overrides = build_provider_env_overrides(
            selected_provider,
            gemini_api_key_env,
            gemini_session_api_key,
        )

        st.markdown(f"**{t('cloud_free_runner')}**")
        st.warning(t("cloud_free_zero_cost_warning"))
        st.caption(t("cloud_free_limits_warning"))
        preset_default = (
            app_config.cloud_free.free_runner_preset
            if app_config.cloud_free.free_runner_preset in FREE_RUNNER_PRESETS
            else FREE_RUNNER_AUTO
        )
        if st.session_state.get("free_runner_preset") not in FREE_RUNNER_PRESETS:
            st.session_state["free_runner_preset"] = preset_default
        selected_free_runner_preset = st.selectbox(
            t("free_runner_preset"),
            list(FREE_RUNNER_PRESETS),
            format_func=lambda preset: t(FREE_RUNNER_LABEL_KEYS[preset]),
            key="free_runner_preset",
        )

        discovered_models, profile_results = load_scoped_cloud_free_cache(
            proj_path,
            st.session_state,
        )

        discover_col, profile_col, recommendation_col = st.columns([1, 1, 3])
        with discover_col:
            if st.button(t("discover_free_cloud_models"), disabled=not key_available):
                with st.spinner(t("discovering_free_cloud_models")):
                    discovered, error = discover_free_cloud_models(
                        api_key_env=gemini_api_key_env,
                        api_key=gemini_inline_api_key,
                        config=app_config.cloud_free,
                    )
                if error:
                    st.error(t("cloud_free_discovery_failed", error=error))
                else:
                    save_discovery_artifact(proj_path, discovered)
                    st.session_state.pop(CLOUD_FREE_CACHE_IDENTITY_KEY, None)
                    st.session_state[CLOUD_FREE_DISCOVERY_SESSION_KEY] = discovered
                    discovered_models = discovered
                    st.success(t("cloud_free_discovery_saved", count=len(discovered)))
        with profile_col:
            if st.button(t("profile_safe_free_models"), disabled=not key_available):
                profile_candidates = build_candidate_pool(
                    discovered_models=discovered_models,
                    configured_models=cloud_models,
                    config=app_config.cloud_free,
                )
                safe_candidates = filter_safe_text_models(
                    profile_candidates,
                    include_unavailable=True,
                )
                with st.spinner(t("profiling_free_cloud_models")):
                    profiles = profile_free_cloud_models(
                        candidates=safe_candidates,
                        api_key_env=gemini_api_key_env,
                        api_key=gemini_inline_api_key,
                    )
                save_profile_artifact(proj_path, profiles)
                st.session_state.pop(CLOUD_FREE_CACHE_IDENTITY_KEY, None)
                st.session_state[CLOUD_FREE_PROFILE_SESSION_KEY] = profiles
                profile_results = profiles
                st.success(t("cloud_free_profile_saved", count=len(profiles)))

        cloud_candidates = build_cached_candidate_pool(
            discovered_models=discovered_models,
            configured_models=cloud_models,
            profiles=profile_results,
            config=app_config.cloud_free,
        )
        cloud_free_recommendation = recommend_free_cloud_model(
            candidates=cloud_candidates,
            profiles=profile_results,
            preset=selected_free_runner_preset,
        )
        with recommendation_col:
            if cloud_free_recommendation:
                st.info(
                    t(
                        "cloud_free_recommendation",
                        model=cloud_free_recommendation.model_id,
                        reason=cloud_free_recommendation.reason,
                    )
                )
            elif selected_free_runner_preset == FREE_RUNNER_MANUAL:
                st.info(t("cloud_free_manual_mode"))
            else:
                st.info(t("cloud_free_no_eligible_recommendation"))

        selected_cloud_model = st.session_state.get("selected_cloud_model_picker")
        if selected_cloud_model not in cloud_models:
            selected_cloud_model = (
                cloud_default_model if cloud_default_model in cloud_models else cloud_models[0]
            )
            st.session_state["selected_cloud_model_picker"] = selected_cloud_model

        cloud_picker_col, cloud_manual_col, cloud_effective_col = st.columns([2, 2, 2])
        with cloud_picker_col:
            selected_cloud_model = st.selectbox(
                t("gemini_model_selector"),
                cloud_models,
                index=cloud_models.index(selected_cloud_model),
                key="selected_cloud_model_picker",
            )
        with cloud_manual_col:
            manual_cloud_model = st.text_input(
                t("manual_cloud_model_name"),
                key="manual_cloud_model_name",
                placeholder=cloud_default_model,
            )
        effective_model = resolve_effective_cloud_model(
            selected_cloud_model,
            manual_cloud_model,
            cloud_default_model,
        )
        if (
            selected_free_runner_preset != FREE_RUNNER_MANUAL
            and cloud_free_recommendation is not None
        ):
            effective_model = cloud_free_recommendation.model_id
        model_label = provider_model_label(selected_provider, effective_model)
        st.session_state["selected_model"] = model_label
        with cloud_effective_col:
            st.write(t("effective_cloud_model", model=effective_model or t("none_option")))
        st.caption(t("gemini_temperature_note"))
        run_model_blocked = not effective_model or not key_available

        selected_profile = next(
            (
                profile
                for profile in profile_results
                if getattr(profile, "model_id", "") == effective_model
            ),
            None,
        )
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        metric_col1.metric(t("cloud_free_selected_model"), effective_model or "N/A")
        metric_col2.metric(
            t("cloud_free_delay"),
            f"{initial_delay_seconds(effective_model, selected_free_runner_preset):.1f}",
        )
        metric_col3.metric(
            t("cloud_free_recent_429"),
            str(getattr(selected_profile, "rate_limited", False)),
        )
        metric_col4.metric(
            t("cloud_free_rounds_hour"),
            f"{3600 / max(initial_delay_seconds(effective_model, selected_free_runner_preset), 1) / 4:.2f}",
        )

        gemini_health_col, gemini_health_result_col = st.columns([1, 3])
        gemini_health_identity = build_model_health_identity(
            provider=MODEL_PROVIDER_GEMINI,
            model=effective_model,
            connection_scope=gemini_health_connection_scope(
                api_key_env=gemini_api_key_env,
                session_key_present=bool(gemini_session_api_key),
                config_key_present=bool(gemini_config_api_key),
            ),
        )
        with gemini_health_col:
            if st.button(t("check_gemini_health")):
                gemini_health = check_gemini_model_health(
                    selected_model=effective_model,
                    api_key_env=gemini_api_key_env,
                    api_key_value=gemini_inline_api_key,
                )
                store_scoped_health_result(
                    st.session_state,
                    key=GEMINI_HEALTH_SESSION_KEY,
                    identity=gemini_health_identity,
                    result=gemini_health,
                )
        with gemini_health_result_col:
            gemini_health = load_scoped_health_result(
                st.session_state,
                key=GEMINI_HEALTH_SESSION_KEY,
                identity=gemini_health_identity,
            )
            if gemini_health:
                if gemini_health["ok"]:
                    st.success(localized_message(gemini_health))
                else:
                    st.error(localized_message(gemini_health))
            else:
                st.info(t("health_check_help"))

        if st.button(t("save_cloud_model")):
            model_to_save = effective_model.strip()
            if not model_to_save:
                st.error(t("model_name_empty"))
            else:
                err = save_default_model_selection(
                    CONFIG_PATH,
                    provider=MODEL_PROVIDER_GEMINI,
                    model_name=model_to_save,
                    gemini_api_key_env=gemini_api_key_env,
                )
                if err:
                    st.error(err)
                else:
                    st.success(t("saved_cloud_model", model=model_to_save))

    st.markdown(f"**{t('continuous_benchmark_settings')}**")
    benchmark_preset_options = list(BENCHMARK_PRESETS)
    if st.session_state.get("benchmark_preset") not in benchmark_preset_options:
        st.session_state["benchmark_preset"] = "free_smoke"
    benchmark_col, quota_col = st.columns([2, 1])
    with benchmark_col:
        selected_benchmark_preset = st.selectbox(
            t("benchmark_preset"),
            benchmark_preset_options,
            format_func=lambda preset: t(
                BENCHMARK_PRESET_LABEL_KEYS.get(preset, "benchmark_preset")
            ),
            key="benchmark_preset",
        )
    with quota_col:
        selected_max_provider_quota_failures = int(
            st.number_input(
                t("max_provider_quota_failures"),
                min_value=0,
                max_value=20,
                value=2,
                step=1,
            )
        )
    configured_drafting_mode = (
        app_config.drafting_mode
        if app_config.drafting_mode in SUPPORTED_DRAFTING_MODES
        else DEFAULT_DRAFTING_MODE
    )
    if st.session_state.get("drafting_mode") not in SUPPORTED_DRAFTING_MODES:
        st.session_state["drafting_mode"] = configured_drafting_mode
    selected_drafting_mode = st.selectbox(
        t("drafting_mode"),
        list(SUPPORTED_DRAFTING_MODES),
        format_func=lambda mode: t(DRAFTING_MODE_LABEL_KEYS[mode]),
        key="drafting_mode",
    )

    def launch_run(mode: str, success_key: str) -> None:
        result = start_background_process(
            command=build_run_command(
                selected_provider,
                mode,
                effective_model,
                gemini_api_key_env if selected_provider == MODEL_PROVIDER_GEMINI else None,
                selected_project,
                selected_free_runner_preset if selected_provider == MODEL_PROVIDER_GEMINI else None,
                selected_benchmark_preset if mode == "continuous" else None,
                selected_max_provider_quota_failures if mode == "continuous" else None,
                selected_drafting_mode,
                gemini_api_key_override_env=(
                    UI_GEMINI_API_KEY_ENV
                    if selected_provider == MODEL_PROVIDER_GEMINI and gemini_session_api_key
                    else None
                ),
            ),
            cwd=ROOT,
            log_path=run_log_path,
            meta_path=run_meta_path(proj_path),
            kind="run",
            extra={
                "model": model_label,
                "mode": mode,
                "provider": selected_provider,
                "drafting_mode": selected_drafting_mode,
            },
            env_overrides=provider_env_overrides,
        )
        render_process_result(result, success_key, model=model_label)

    run_buttons_disabled = run_process_blocked or run_model_blocked
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        if st.button(t("run_diagnostic"), disabled=run_buttons_disabled):
            launch_run("diagnostic", "started_diagnostic")
    with c2:
        if st.button(t("run_normal"), disabled=run_buttons_disabled):
            launch_run("normal", "started_normal")
    with c3:
        if st.button(t("run_continuous"), disabled=run_buttons_disabled):
            launch_run("continuous", "started_continuous")
    with c4:
        if st.button(t("pause_stop_safely"), disabled=not run_active):
            stop_signal_display = output_display_path(stop_signal_path)
            if create_stop_signal(stop_signal_path):
                st.warning(t("stop_signal_created", path=stop_signal_display))
            else:
                st.error(t("stop_signal_failed", path=stop_signal_display))
    resume_state = describe_resume_state(
        project_dir=proj_path,
        checkpoint=checkpoint,
        run_active=run_active,
        selected_model=model_label,
    )
    with c5:
        if st.button(
            t("resume"),
            disabled=run_buttons_disabled or not resume_state["can_resume"],
        ):
            launch_run("resume", "started_resume")
    with c6:
        if st.button(t("run_tests"), disabled=run_active, key="run_tests_top"):
            st.session_state["test_result"] = run_project_tests(ROOT)

    if resume_state["level"] == "success":
        st.success(localized_message(resume_state))
    elif resume_state["level"] == "warning":
        st.warning(localized_message(resume_state))
    else:
        st.info(localized_message(resume_state))
    resume_details = resume_state.get("details")
    if isinstance(resume_details, dict) and resume_details:
        st.caption(
            t(
                "resume_details",
                run_id=resume_details.get("run_id", "N/A"),
                run_root=resume_details.get("run_root", "N/A"),
                last_completed_round=resume_details.get("last_completed_round", "N/A"),
                next_round=resume_details.get("next_round", "N/A"),
                stop_reason=resume_details.get("stop_reason", "N/A"),
                can_resume=resume_details.get("can_resume", False),
                preserved=resume_details.get("completed_round_files_preserved", False),
                next_round_status=resume_details.get("next_round_status", "N/A"),
                next_round_action=resume_details.get("next_round_safety_action", "N/A"),
                next_round_path=resume_details.get("next_round_path", "N/A"),
            )
        )

    st.subheader(t("project_tests"))
    st.caption(t("project_tests_help"))
    test_col_left, test_col_right = st.columns([1, 3])
    with test_col_left:
        if st.button(t("run_tests"), disabled=run_active, key="run_tests_panel"):
            st.session_state["test_result"] = run_project_tests(ROOT)
    with test_col_right:
        last_test = st.session_state.get("test_result")
        if last_test:
            if last_test["ok"]:
                st.success(
                    t(
                        "tests_passed_detail",
                        elapsed=last_test["elapsed"],
                        command=last_test["command"],
                    )
                )
            else:
                returncode = last_test["returncode"]
                st.error(
                    t(
                        "tests_failed_detail",
                        elapsed=last_test["elapsed"],
                        returncode=returncode,
                    )
                )
        else:
            st.info(t("no_test_run"))
    if st.session_state.get("test_result"):
        with st.expander(t("test_output"), expanded=True):
            st.code(st.session_state["test_result"]["output"], language="text")

    if selected_provider == MODEL_PROVIDER_OLLAMA:
        st.subheader(t("model_management"))
        st.caption(t("model_management_help"))
        rec = {
            "qwen3:8b": "model_quality_balanced",
            "llama3.2:3b": "model_smaller_if_available",
            "phi3:mini": "model_smaller_if_available",
            "qwen2.5:3b": "model_smaller_if_available",
            "gemma2:2b": "model_smaller_if_available",
        }
        st.markdown(f"**{t('recommended_models')}**")
        for name, desc_key in rec.items():
            installed_tag = t("installed_tag") if name in installed_model_names else ""
            st.write(f"- `{name}` - {t(desc_key)}{installed_tag}")

        st.markdown(f"**{t('installed_models')}**")
        if models:
            st.dataframe(
                [
                    {
                        t("models_table_name"): m["name"],
                        t("models_table_size"): m["size"],
                        t("models_table_modified"): m["modified"],
                    }
                    for m in models
                ],
                width="stretch",
            )
        else:
            st.caption(t("no_installed_model"))

        health_col, health_result_col = st.columns([1, 3])
        ollama_health_identity = build_model_health_identity(
            provider=MODEL_PROVIDER_OLLAMA,
            model=effective_model,
            connection_scope=ollama_health_connection_scope(app_config.ollama_base_url),
        )
        with health_col:
            if st.button(t("check_model_health")):
                model_health = check_model_health(
                    provider=MODEL_PROVIDER_OLLAMA,
                    base_url=app_config.ollama_base_url,
                    selected_model=effective_model,
                    installed_model_names=installed_model_names,
                )
                store_scoped_health_result(
                    st.session_state,
                    key=OLLAMA_HEALTH_SESSION_KEY,
                    identity=ollama_health_identity,
                    result=model_health,
                )
        with health_result_col:
            model_health = load_scoped_health_result(
                st.session_state,
                key=OLLAMA_HEALTH_SESSION_KEY,
                identity=ollama_health_identity,
            )
            if model_health:
                if model_health["ok"]:
                    st.success(localized_message(model_health))
                else:
                    st.error(localized_message(model_health))
            else:
                st.info(t("health_check_help"))

        if st.button(t("save_default_model"), disabled=bool(models_error)):
            model_to_save = effective_model.strip()
            if not model_to_save:
                st.error(t("model_name_empty"))
            else:
                err = save_default_model_name(CONFIG_PATH, model_to_save)
                if err:
                    st.error(err)
                else:
                    st.success(t("saved_default_model", model=model_to_save))

        pull_model_name = st.text_input(t("pull_model_by_name"), value="qwen3:8b")
        if st.button(t("pull_model"), disabled=blocked):
            pull_model_name = pull_model_name.strip()
            if not pull_model_name:
                st.error(t("enter_model_name"))
            else:
                result = start_background_process(
                    command=["ollama", "pull", pull_model_name],
                    cwd=ROOT,
                    log_path=model_job_log_path,
                    meta_path=model_job_meta_path(proj_path),
                    kind="model_pull",
                    extra={"model": pull_model_name},
                )
                render_process_result(
                    result,
                    "started_pull_model",
                    model=pull_model_name,
                )

        delete_target = st.selectbox(
            t("delete_model"),
            installed_model_names if installed_model_names else [DELETE_NONE],
            format_func=lambda model: t("none_option") if model == DELETE_NONE else model,
        )
        confirm_delete = st.checkbox(t("confirm_delete"))
        if st.button(t("delete_selected_model"), disabled=blocked or not installed_model_names):
            if not confirm_delete:
                st.error(t("confirm_delete_first"))
            elif run_active and delete_target == str(run_meta.get("model", "")):
                st.error(t("cannot_delete_running_model"))
            elif delete_target == DELETE_NONE:
                st.error(t("no_deletable_model"))
            else:
                result = start_background_process(
                    command=["ollama", "rm", delete_target],
                    cwd=ROOT,
                    log_path=model_job_log_path,
                    meta_path=model_job_meta_path(proj_path),
                    kind="model_delete",
                    extra={"model": delete_target},
                )
                render_process_result(
                    result,
                    "started_delete_model",
                    model=delete_target,
                )

    st.subheader(t("progress_panel"))
    auto_refresh = st.checkbox(
        t("auto_refresh_logs"),
        value=True,
        key="auto_refresh_logs",
    )
    live_panel = st.fragment(run_every=live_refresh_interval(auto_refresh))(
        render_live_progress_and_logs
    )
    live_panel(
        proj_path=proj_path,
        run_log_path=run_log_path,
        model_job_log_path=model_job_log_path,
        checkpoint_path=checkpoint_path,
        stop_signal_path=stop_signal_path,
        default_model=default_model,
    )

    st.subheader(t("run_metadata_summary"))
    run_metadata_rows = [
        {"field": t(str(row["field_key"])), "value": row["value"]}
        for row in build_run_metadata_rows(proj_path, checkpoint)
    ]
    if run_metadata_rows:
        st.dataframe(run_metadata_rows, width="stretch", hide_index=True)
    else:
        st.info(t("run_metadata_empty"))

    render_run_analytics_dashboard(proj_path, checkpoint)

    score_rows = load_score_history_rows(proj_path / "score_history.json")
    st.subheader(t("score_history_table"))
    if score_rows:
        st.dataframe(score_rows, width="stretch")
        st.caption(t("score_history_trend"))
        st.line_chart(score_rows, x="round", y="score")
    else:
        st.info(t("score_history_empty"))

    st.subheader(t("run_comparison"))
    run_roots = discover_project_run_roots(proj_path)
    if len(run_roots) < 2:
        st.info(t("run_comparison_empty"))
    else:
        run_options = {
            f"{run_root.name} - {output_display_path(run_root)}": run_root for run_root in run_roots
        }
        default_labels = list(run_options)[:2]
        selected_run_labels = st.multiselect(
            t("run_comparison_runs"),
            list(run_options),
            default=default_labels,
        )
        selected_run_roots = [run_options[label] for label in selected_run_labels]
        if len(selected_run_roots) < 2:
            st.info(t("run_comparison_select_two"))
        else:
            comparison_rows = build_run_comparison_rows(selected_run_roots)
            st.dataframe(comparison_rows, width="stretch", hide_index=True)
            chart_rows = [
                {
                    "run_id": row["run_id"],
                    "best_score": row["best_score"],
                    "average_score": row["average_score"],
                }
                for row in comparison_rows
                if isinstance(row.get("best_score"), (int, float))
            ]
            if chart_rows:
                st.caption(t("run_comparison_score_chart"))
                st.bar_chart(chart_rows, x="run_id", y=["best_score", "average_score"])

    st.subheader(t("output_browser"))
    output_catalog = build_output_catalog(proj_path, checkpoint)
    selected_output_index = st.selectbox(
        t("output_file"),
        range(len(output_catalog)),
        format_func=lambda idx: (
            t(str(output_catalog[idx]["label_key"]))
            if output_catalog[idx]["exists"]
            else f"{t(str(output_catalog[idx]['label_key']))}{t('not_generated_suffix')}"
        ),
    )
    selected_output = output_catalog[selected_output_index]
    selected_path = selected_output["path"]
    if selected_path is not None:
        st.caption(output_display_path(selected_path))
    if not selected_output["exists"]:
        st.info(t(str(selected_output.get("missing_key", "output_not_generated"))))
    else:
        content = read_file_text(selected_path)
        if selected_output["kind"] == "json":
            try:
                st.json(json.loads(content))
            except json.JSONDecodeError:
                st.code(content, language="text")
        elif selected_output["kind"] == "markdown":
            st.markdown(content or t("empty_markdown"))
        else:
            st.code(content or t("empty_text"), language="text")


if __name__ == "__main__":
    main()
