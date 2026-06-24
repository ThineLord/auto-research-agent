from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence

import requests
import streamlit as st

from src.benchmarking import BENCHMARK_PRESETS
from src.cloud_free import (
    FREE_RUNNER_AUTO,
    FREE_RUNNER_MANUAL,
    FREE_RUNNER_PRESETS,
    FREE_RUNNER_QUALITY,
    FREE_RUNNER_VOLUME,
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
from src.llm import GeminiClient
from src.run_compare import compare_runs
from src.runtime import (
    get_active_process_meta,
    model_job_meta_path,
    run_meta_path,
    run_project_tests,
    start_background_process,
)
from src.storage import read_file_text, read_json_file, tail_file_lines, write_file_text
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


def relative_repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return f"<repo>/{path.name}"


def project_display_path(project_dir: Path) -> str:
    return relative_repo_path(project_dir)


def output_display_path(path: Path) -> str:
    return relative_repo_path(path)


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


def input_text_or_placeholder(path: Path, placeholder_key: str) -> str:
    if path.exists():
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
    env_name = api_key_env.strip()
    key_value = api_key_value.strip()
    if not env_name or not key_value:
        return {}
    return {env_name: key_value}


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
            "message": f"Ollama API timed out at {base_url}.",
            "message_key": "health_timeout",
            "message_args": {"base_url": base_url},
        }
    except (requests.RequestException, ValueError) as exc:
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": f"Ollama API is not healthy at {base_url}: {exc}",
            "message_key": "health_api_unhealthy",
            "message_args": {"base_url": base_url, "error": exc},
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
        return {
            "ok": False,
            "api_ok": False,
            "model_ok": False,
            "message": f"Gemini health check failed: {exc}",
            "message_key": "gemini_health_failed",
            "message_args": {"error": exc},
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
        }
    if run_active:
        return {
            "can_resume": False,
            "level": "warning",
            "message": "A run is active. Resume is blocked until the current run exits.",
            "message_key": "resume_blocked_active",
            "message_args": {},
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

    if checkpoint.get("can_resume"):
        next_round = _safe_int(checkpoint.get("last_completed_round")) + 1
        return {
            "can_resume": True,
            "level": "success",
            "message": f"Resume available from round {next_round}.{model_note}",
            "message_key": "resume_available",
            "message_args": {"next_round": next_round},
            "model_mismatch": model_mismatch,
            "checkpoint_model": checkpoint_model,
            "selected_model": selected_model,
        }

    stop_reason = checkpoint.get("stop_reason", "unknown")
    return {
        "can_resume": False,
        "level": "info",
        "message": f"Resume is unavailable. Last stop reason: `{stop_reason}`.{model_note}",
        "message_key": "resume_unavailable",
        "message_args": {"stop_reason": stop_reason},
        "model_mismatch": model_mismatch,
        "checkpoint_model": checkpoint_model,
        "selected_model": selected_model,
    }


def detect_output_kind(path: Path) -> str:
    if path.suffix == ".json":
        return "json"
    if path.suffix == ".log":
        return "log"
    if path.suffix in {".md", ".markdown"}:
        return "markdown"
    return "text"


def resolve_run_artifact_paths(project_dir: Path, checkpoint: dict[str, Any]) -> dict[str, Path]:
    run_root_text = str(checkpoint.get("run_root", "")).strip()
    run_root = Path(run_root_text) if run_root_text else None
    run_config_path = (
        Path(str(checkpoint.get("run_config")))
        if checkpoint.get("run_config")
        else (run_root / "run_config.json" if run_root else project_dir / "run_config.json")
    )
    run_summary_path = (
        Path(str(checkpoint.get("run_summary")))
        if checkpoint.get("run_summary")
        else (run_root / "run_summary.json" if run_root else project_dir / "run_summary.json")
    )

    round_metrics_path = (
        run_root / "round_metrics.json" if run_root else project_dir / "round_metrics.json"
    )
    if run_summary_path.exists():
        run_summary = read_json_file(run_summary_path)
        round_metrics_text = str(run_summary.get("round_metrics_path", "")).strip()
        if round_metrics_text:
            round_metrics_path = Path(round_metrics_text)

    return {
        "run_root": run_root or project_dir,
        "run_config": run_config_path,
        "run_summary": run_summary_path,
        "round_metrics": round_metrics_path,
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
    run_config = read_json_file(paths["run_config"]) if paths["run_config"].exists() else {}
    run_summary = read_json_file(paths["run_summary"]) if paths["run_summary"].exists() else {}
    if not run_config and not run_summary:
        return []

    model = run_config.get("model") if isinstance(run_config.get("model"), dict) else {}
    runtime = run_config.get("runtime") if isinstance(run_config.get("runtime"), dict) else {}
    git_meta = run_config.get("git") if isinstance(run_config.get("git"), dict) else {}
    resume = run_config.get("resume_eligibility")
    resume = resume if isinstance(resume, dict) else {}

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
        ("run_meta_run_config_path", output_display_path(paths["run_config"])),
        ("run_meta_run_summary_path", output_display_path(paths["run_summary"])),
        ("run_meta_round_metrics_path", output_display_path(paths["round_metrics"])),
    ]
    return [{"field_key": field_key, "value": _display_value(value)} for field_key, value in values]


def discover_project_run_roots(project_dir: Path, *, limit: int = 12) -> list[Path]:
    runs_dir = project_dir / "runs"
    if not runs_dir.exists():
        return []
    run_roots = [path for path in runs_dir.iterdir() if path.is_dir()]
    return sorted(
        run_roots,
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )[:limit]


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
    comparison = compare_runs([Path(run_root) for run_root in run_roots])
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
                "run_config_path": _artifact_path_display(run.get("run_config_path")),
                "run_summary_path": _artifact_path_display(run.get("run_summary_path")),
                "metadata_status": _display_value(run.get("metadata_status")),
            }
        )
    return rows


def build_output_catalog(project_dir: Path, checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    paths = resolve_run_artifact_paths(project_dir, checkpoint)
    run_root = paths["run_root"] if paths["run_root"] != project_dir else None
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
            "path": paths["run_config"],
            "missing_key": "missing_run_config",
        },
        {
            "label": "Run summary",
            "label_key": "output_run_summary",
            "path": paths["run_summary"],
            "missing_key": "missing_run_summary",
        },
        {
            "label": "Round metrics",
            "label_key": "output_round_metrics",
            "path": paths["round_metrics"],
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
        catalog.extend(
            [
                {
                    "label": "Latest round draft",
                    "label_key": "output_latest_draft",
                    "path": round_dir / "01_draft.md",
                },
                {
                    "label": "Latest round review",
                    "label_key": "output_latest_review",
                    "path": round_dir / "02_review.md",
                },
                {
                    "label": "Latest round revised",
                    "label_key": "output_latest_revised",
                    "path": round_dir / "03_revised.md",
                },
                {
                    "label": "Latest round judge",
                    "label_key": "output_latest_judge",
                    "path": round_dir / "04_judge.md",
                },
            ]
        )

    return [
        {
            "label": item["label"],
            "label_key": item["label_key"],
            "path": item["path"],
            "kind": detect_output_kind(item["path"]),
            "exists": item["path"].exists(),
            "missing_key": item.get("missing_key", "output_not_generated"),
        }
        for item in catalog
    ]


def load_score_history_rows(score_history_path: Path) -> list[dict[str, Any]]:
    if not score_history_path.exists():
        return []
    try:
        payload = json.loads(read_file_text(score_history_path))
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
    run_meta = get_active_process_meta(run_meta_path(proj_path))
    checkpoint = read_json_file(checkpoint_path) if checkpoint_path.exists() else {}
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
    st.write(t("stop_signal_present", present=stop_signal_path.exists()))
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

    projects = (
        sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir()])
        if PROJECTS_DIR.exists()
        else []
    )
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
    st.write(t("project_path", path=project_display_path(proj_path)))

    task_path = proj_path / "task.md"
    memory_path = proj_path / "memory.md"
    run_log_path = proj_path / "run.log"
    model_job_log_path = proj_path / "model_ops.log"
    checkpoint_path = proj_path / "checkpoint.json"
    stop_signal_path = proj_path / "STOP_REQUESTED"
    run_meta = get_active_process_meta(run_meta_path(proj_path))
    model_job_meta = get_active_process_meta(model_job_meta_path(proj_path))
    checkpoint = read_json_file(checkpoint_path) if checkpoint_path.exists() else {}

    col_input_left, col_input_right = st.columns(2)
    with col_input_left:
        task_text = st.text_area(
            t("input_editor_task"),
            value=input_text_or_placeholder(task_path, "task_placeholder"),
            height=260,
        )
        if not task_path.exists():
            st.caption(t("task_missing_help"))
    with col_input_right:
        memory_text = st.text_area(
            t("input_editor_memory"),
            value=input_text_or_placeholder(memory_path, "memory_placeholder"),
            height=260,
        )
        if not memory_path.exists():
            st.caption(t("memory_optional_help"))
    if st.button(t("save_input")):
        write_file_text(task_path, task_text)
        write_file_text(memory_path, memory_text)
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
        )
        gemini_api_key_password = st.text_input(
            t("gemini_api_key_password"),
            type="password",
            key="gemini_api_key_password",
            help=t("gemini_api_key_password_help"),
        )
        cloud_models = list(app_config.model.gemini.models or DEFAULT_GEMINI_MODELS)
        cloud_default_model = (
            app_config.model.name
            if app_config.model.provider == MODEL_PROVIDER_GEMINI
            else DEFAULT_GEMINI_MODEL
        )
        key_available = has_gemini_api_key_source(
            api_key_env=gemini_api_key_env,
            api_key_value=gemini_api_key_password,
            config_api_key=app_config.model.gemini.api_key,
        )
        if not key_available:
            st.warning(t("gemini_health_missing_key"))
        provider_env_overrides = build_provider_env_overrides(
            selected_provider,
            gemini_api_key_env,
            gemini_api_key_password,
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

        discovered_models = st.session_state.get("cloud_free_discovered_models")
        if not isinstance(discovered_models, list):
            discovered_models = load_discovery_artifact(proj_path)
        profile_results = st.session_state.get("cloud_free_profile_results")
        if not isinstance(profile_results, list):
            profile_results = load_profile_artifact(proj_path)

        discover_col, profile_col, recommendation_col = st.columns([1, 1, 3])
        with discover_col:
            if st.button(t("discover_free_cloud_models"), disabled=not key_available):
                with st.spinner(t("discovering_free_cloud_models")):
                    discovered, error = discover_free_cloud_models(
                        api_key_env=gemini_api_key_env,
                        api_key=gemini_api_key_password or app_config.model.gemini.api_key,
                        config=app_config.cloud_free,
                    )
                if error:
                    st.error(t("cloud_free_discovery_failed", error=error))
                else:
                    save_discovery_artifact(proj_path, discovered)
                    st.session_state["cloud_free_discovered_models"] = discovered
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
                        api_key=gemini_api_key_password or app_config.model.gemini.api_key,
                    )
                save_profile_artifact(proj_path, profiles)
                st.session_state["cloud_free_profile_results"] = profiles
                profile_results = profiles
                st.success(t("cloud_free_profile_saved", count=len(profiles)))

        cloud_candidates = build_candidate_pool(
            discovered_models=discovered_models,
            configured_models=cloud_models,
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
            else:
                st.info(t("cloud_free_manual_mode"))

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
        with gemini_health_col:
            if st.button(t("check_gemini_health")):
                st.session_state["gemini_model_health"] = check_gemini_model_health(
                    selected_model=effective_model,
                    api_key_env=gemini_api_key_env,
                    api_key_value=gemini_api_key_password or app_config.model.gemini.api_key,
                )
        with gemini_health_result_col:
            gemini_health = st.session_state.get("gemini_model_health")
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
            write_file_text(stop_signal_path, "STOP_REQUESTED\n")
            st.warning(t("stop_signal_created", path=stop_signal_path))
    resume_state = describe_resume_state(
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
        with health_col:
            if st.button(t("check_model_health")):
                st.session_state["model_health"] = check_model_health(
                    provider=MODEL_PROVIDER_OLLAMA,
                    base_url=app_config.ollama_base_url,
                    selected_model=effective_model,
                    installed_model_names=installed_model_names,
                )
        with health_result_col:
            model_health = st.session_state.get("model_health")
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
