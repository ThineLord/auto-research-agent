"""Command-line entrypoint and mode dispatch."""

from __future__ import annotations

import argparse
import math
import os
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, List, Optional

from rich.console import Console

from .agents import ResearchAgents
from .benchmarking import (
    BENCHMARK_PRESETS,
    benchmark_preset_rounds,
    estimate_request_budget,
    format_request_budget_estimate,
)
from .cloud_free import (
    FREE_RUNNER_MANUAL,
    FREE_RUNNER_PRESETS,
    build_cached_candidate_pool,
    build_candidate_pool,
    discover_free_cloud_models,
    filter_safe_text_models,
    load_discovery_artifact,
    load_profile_artifact,
    profile_free_cloud_models,
    recommend_free_cloud_model,
    save_discovery_artifact,
    save_profile_artifact,
)
from .config import (
    DEFAULT_DRAFTING_MODE,
    DEFAULT_GEMINI_MAX_PROMPT_CHARS,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OLLAMA_MAX_PROMPT_CHARS,
    MODEL_PROVIDER_GEMINI,
    MODEL_PROVIDER_OLLAMA,
    SUPPORTED_DRAFTING_MODES,
    SUPPORTED_MODEL_PROVIDERS,
    ConfigValidationError,
    format_model_label,
    format_topic_context,
    list_installed_ollama_models,
    load_app_config,
    resolve_model_provider_settings,
    resolve_runtime_limits,
)
from .constants import RUN_LOCK_FILENAME
from .diagnostic import run_diagnostic_mode
from .literature_survey import run_literature_survey_mode
from .llm import create_llm_client
from .logging_config import configure_logging
from .mock_run import (
    MOCK_DEFAULT_ROUNDS,
    MOCK_MODEL_NAME,
    MOCK_MODEL_PROVIDER,
    build_mock_agents,
    mock_model_parameters,
)
from .package_resources import (
    PackageResourceError,
    resolve_runtime_layout,
    seed_default_mock_project,
    validate_generation_resources,
)
from .project_input import ProjectInputError, load_project_input
from .resume import run_resume_mode
from .round_commit_recovery import (
    RoundCommitReadError,
    RoundCommitRecoveryInspection,
    classify_round_commit_recovery,
    recover_round_commit,
)
from .run_analytics import analyze_run
from .run_compare import compare_runs
from .runner import ResumeHistoryError, run_iterative_rounds
from .runtime import RUN_LOCK_GUARD_FILENAME, acquire_run_lock, release_run_lock
from .session import run_session_mode
from .storage import (
    artifact_path_is_safe,
    ensure_artifact_directory,
    ensure_project_runtime_paths_safe,
    write_json_file,
)

_EXIT_OPERATION_ERROR = 1
_EXIT_STARTUP_ERROR = 2
_EXIT_INTERRUPTED = 130


class NumericCliOverrideError(ValueError):
    """Raised when individually valid numeric overrides conflict after config resolution."""


def _positive_round_count(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer >= 1") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def _non_negative_finite_seconds(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a finite number >= 0") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be a finite number >= 0")
    return parsed


def _bounded_max_delay_seconds(value: str) -> float:
    parsed = _non_negative_finite_seconds(value)
    if parsed > 86400:
        raise argparse.ArgumentTypeError("must be <= 86400")
    return parsed


def _bounded_retry_count(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer in [0, 20]") from exc
    if not 0 <= parsed <= 20:
        raise argparse.ArgumentTypeError("must be in range [0, 20]")
    return parsed


def _minimum_prompt_chars(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer >= 1000") from exc
    if parsed < 1000:
        raise argparse.ArgumentTypeError("must be >= 1000")
    return parsed


def _non_negative_count(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer >= 0") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local iterative research agent")
    primary_modes = parser.add_mutually_exclusive_group()
    primary_modes.add_argument(
        "--session",
        action="store_true",
        help="Run focused nightly research session workflow.",
    )
    primary_modes.add_argument(
        "--diagnostic",
        action="store_true",
        help="Run lightweight one-round diagnostic workflow.",
    )
    primary_modes.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuous round-by-round mode with safe stop support.",
    )
    primary_modes.add_argument(
        "--resume",
        action="store_true",
        help="Resume from projects/<project>/checkpoint.json.",
    )
    primary_modes.add_argument(
        "--survey",
        action="store_true",
        help="Run local Literature Survey Mode without provider calls.",
    )
    primary_modes.add_argument(
        "--mock",
        action="store_true",
        help=(
            "Run a deterministic provider-free demo workflow that writes normal run artifacts. "
            "Defaults to 2 rounds unless --max-rounds is provided."
        ),
    )
    parser.add_argument(
        "--survey-output",
        type=str,
        default=None,
        help="Override survey report path. Relative paths resolve under the selected project.",
    )
    primary_modes.add_argument(
        "--compare-runs",
        nargs="+",
        default=None,
        metavar="RUN_DIR",
        help="Compare two or more run directories without provider calls.",
    )
    parser.add_argument(
        "--compare-output",
        type=str,
        default=None,
        help="Optional JSON output path for --compare-runs. Relative paths resolve from repo root.",
    )
    primary_modes.add_argument(
        "--analyze-run",
        type=str,
        default=None,
        metavar="RUN_DIR",
        help="Analyze one run directory without provider calls.",
    )
    parser.add_argument(
        "--analyze-output",
        type=str,
        default=None,
        help="Optional JSON output path for --analyze-run. Relative paths resolve from repo root.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override model name, e.g. qwen3:8b or gemini-3.5-flash",
    )
    parser.add_argument(
        "--provider",
        choices=sorted(SUPPORTED_MODEL_PROVIDERS),
        default=None,
        help="Override model provider.",
    )
    parser.add_argument(
        "--gemini-api-key-env",
        type=str,
        default=None,
        help="Environment variable name that contains the Gemini API key.",
    )
    parser.add_argument(
        "--gemini-api-key-override-env",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Override project folder name under projects/.",
    )
    primary_modes.add_argument(
        "--cloud-free-discover",
        action="store_true",
        help="Discover safe free-run Gemini/Gemma text models and save an ignored artifact.",
    )
    primary_modes.add_argument(
        "--cloud-free-profile",
        action="store_true",
        help="Profile safe free-run Gemini/Gemma candidates and save an ignored artifact.",
    )
    parser.add_argument(
        "--free-runner-preset",
        choices=FREE_RUNNER_PRESETS,
        default=None,
        help="Cloud free runner preset.",
    )
    parser.add_argument(
        "--disable-cloud-free-mode",
        action="store_true",
        help="Disable Gemini free-tier pacing/retry scheduler for this run.",
    )
    parser.add_argument(
        "--min-delay-seconds",
        type=_non_negative_finite_seconds,
        default=None,
        help="Override cloud free scheduler minimum delay with a finite value >= 0.",
    )
    parser.add_argument(
        "--max-delay-seconds",
        type=_bounded_max_delay_seconds,
        default=None,
        help="Override cloud free scheduler maximum delay in [0, 86400].",
    )
    parser.add_argument(
        "--max-retries",
        type=_bounded_retry_count,
        default=None,
        help="Override cloud free scheduler retry count in [0, 20].",
    )
    parser.add_argument(
        "--prompt-budget-chars",
        type=_minimum_prompt_chars,
        default=None,
        help="Override cloud free prompt budget in characters (>= 1000).",
    )
    parser.add_argument(
        "--max-prompt-chars",
        type=_minimum_prompt_chars,
        default=None,
        help="Override maximum prompt size before an LLM call fails fast (>= 1000).",
    )
    parser.add_argument(
        "--max-rounds",
        type=_positive_round_count,
        default=None,
        help="Override positive round count for normal/session/resume, or cap continuous mode.",
    )
    parser.add_argument(
        "--drafting-mode",
        choices=SUPPORTED_DRAFTING_MODES,
        default=None,
        help=f"Draft context mode. Default from config.yaml: {DEFAULT_DRAFTING_MODE}.",
    )
    parser.add_argument(
        "--benchmark-preset",
        choices=sorted(BENCHMARK_PRESETS),
        default=None,
        help=(
            "Benchmark-safe iteration preset: free_smoke=4, free_eval=5, "
            "paid_benchmark=25, stress_test=50."
        ),
    )
    parser.add_argument(
        "--max-provider-quota-failures",
        type=_non_negative_count,
        default=2,
        help="Stop after this many consecutive provider quota/rate-limit failed rounds.",
    )
    args = parser.parse_args(argv)
    if args.compare_runs is not None and len(args.compare_runs) < 2:
        parser.error("--compare-runs requires at least two RUN_DIR arguments")
    if (
        args.min_delay_seconds is not None
        and args.max_delay_seconds is not None
        and args.max_delay_seconds < args.min_delay_seconds
    ):
        parser.error("--max-delay-seconds must be >= --min-delay-seconds")
    output_dependencies = (
        ("--survey-output", args.survey_output, "--survey", args.survey),
        ("--compare-output", args.compare_output, "--compare-runs", args.compare_runs),
        ("--analyze-output", args.analyze_output, "--analyze-run", args.analyze_run),
    )
    for output_option, output_value, mode_option, mode_value in output_dependencies:
        if output_value is not None and not mode_value:
            parser.error(f"{output_option} requires {mode_option}")
    if args.gemini_api_key_override_env is not None:
        override_env = args.gemini_api_key_override_env.strip()
        try:
            override_value = os.environ.get(override_env, "")
        except (OSError, ValueError):
            override_value = ""
        if not override_env or not override_value.strip():
            parser.error("--gemini-api-key-override-env must name a populated environment variable")
        args.gemini_api_key_override_env = override_env
    return args


def _has_gemini_api_key_source(*, api_key_env: str, config_api_key: str = "") -> bool:
    if config_api_key.strip():
        return True
    for env_name in (api_key_env.strip(), "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if env_name and os.environ.get(env_name, "").strip():
            return True
    return False


def _validate_project_override(project_name: str) -> Optional[str]:
    normalized = project_name.strip()
    if not normalized:
        return "Project name must be a non-empty folder name under projects/."
    if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
        return "Project name must be a simple folder name under projects/."
    return None


def _print_cloud_model_table(console: Console, models: list[object]) -> None:
    for model in models:
        model_id = str(getattr(model, "model_id", ""))
        safe = bool(getattr(model, "safe_text_generation", False))
        source = str(getattr(model, "source", ""))
        blocked = str(getattr(model, "blocked_reason", ""))
        console.print(
            f"- {model_id} | safe={safe} | source={source}"
            + (f" | blocked={blocked}" if blocked else "")
        )


def _apply_cloud_free_arg_overrides(config, args: argparse.Namespace):
    cloud_free_config = config.cloud_free
    updates = {}
    if args.free_runner_preset:
        updates["free_runner_preset"] = args.free_runner_preset
    if args.disable_cloud_free_mode:
        updates["cloud_free_mode"] = False
    if args.min_delay_seconds is not None:
        updates["min_delay_seconds"] = args.min_delay_seconds
    if args.max_delay_seconds is not None:
        updates["max_delay_seconds"] = args.max_delay_seconds
    if args.max_retries is not None:
        updates["max_retries"] = args.max_retries
    if args.prompt_budget_chars is not None:
        updates["prompt_budget_chars"] = args.prompt_budget_chars
    if updates:
        cloud_free_config = replace(cloud_free_config, **updates)
    if (
        cloud_free_config.min_delay_seconds is not None
        and cloud_free_config.max_delay_seconds < cloud_free_config.min_delay_seconds
    ):
        raise NumericCliOverrideError(
            "--max-delay-seconds must be >= the effective --min-delay-seconds"
        )
    return cloud_free_config


def _resolve_repo_relative_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def _display_repo_path(root: Path, value: object) -> str:
    path = Path(str(value or ""))
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return f"<repo>/{path.name}"


def _print_run_lock_recovery_hint(console: Console, root: Path, project_dir: Path) -> None:
    metadata_path = _display_repo_path(root, project_dir / RUN_LOCK_FILENAME)
    guard_path = _display_repo_path(root, project_dir / RUN_LOCK_GUARD_FILENAME)
    console.print(
        "[yellow]If no run process is active, inspect and move aside stale lock paths "
        f"{metadata_path} and {guard_path}, then retry.[/yellow]"
    )


def _recover_pending_round_commit(
    *,
    console: Console,
    project_dir: Path,
) -> RoundCommitRecoveryInspection:
    """Recover one valid journal after the caller acquires the project lock."""
    inspection = classify_round_commit_recovery(project_dir)
    if inspection.status == "absent":
        return inspection
    if not inspection.can_recover:
        console.print(
            "[red]Round commit recovery is blocked; preserved artifacts require inspection.[/red]"
        )
        raise SystemExit(_EXIT_STARTUP_ERROR)
    try:
        recovered = recover_round_commit(project_dir)
    except (OSError, RuntimeError):
        console.print(
            "[red]Round commit recovery failed; preserved artifacts require inspection.[/red]"
        )
        raise SystemExit(_EXIT_STARTUP_ERROR) from None
    console.print(
        "[yellow]Recovered pending round commit before starting new runner work.[/yellow]"
    )
    return recovered


def _unsafe_lock_path_message(project_dir: Path) -> str | None:
    """Preserve actionable lock diagnostics when project-wide preflight fails first."""
    try:
        ensure_artifact_directory(project_dir, anchor=project_dir.parent)
    except OSError:
        return None
    if not artifact_path_is_safe(
        project_dir / RUN_LOCK_FILENAME,
        allow_missing=True,
        anchor=project_dir.parent,
    ):
        return (
            f"Stale run lock could not be cleared: {RUN_LOCK_FILENAME} is not removable. "
            "Move it aside manually and retry."
        )
    if not artifact_path_is_safe(
        project_dir / RUN_LOCK_GUARD_FILENAME,
        allow_missing=True,
        anchor=project_dir.parent,
    ):
        return "Run lock guard could not be acquired: unsafe or unavailable guard path."
    return None


def _privacy_safe_comparison(comparison: dict[str, Any], root: Path) -> dict[str, Any]:
    safe_comparison = dict(comparison)
    safe_runs: list[dict[str, Any]] = []
    for run in comparison.get("runs", []):
        if not isinstance(run, dict):
            continue
        safe_run = dict(run)
        for key in ("run_path", "run_root", "run_config_path", "run_summary_path"):
            if safe_run.get(key):
                safe_run[key] = _display_repo_path(root, safe_run[key])
        safe_runs.append(safe_run)
    safe_comparison["runs"] = safe_runs
    return safe_comparison


def _privacy_safe_run_analysis(analysis: dict[str, Any], root: Path) -> dict[str, Any]:
    safe_analysis = dict(analysis)
    if safe_analysis.get("run_path"):
        safe_analysis["run_path"] = _display_repo_path(root, safe_analysis["run_path"])
    artifacts = safe_analysis.get("artifacts")
    if isinstance(artifacts, dict):
        safe_artifacts = dict(artifacts)
        for key in ("run_config_path", "run_summary_path"):
            if safe_artifacts.get(key):
                safe_artifacts[key] = _display_repo_path(root, safe_artifacts[key])
        safe_analysis["artifacts"] = safe_artifacts
    return safe_analysis


def _run_compare_cli(args: argparse.Namespace, console: Console, root: Path) -> dict[str, object]:
    run_roots = [
        _resolve_repo_relative_path(root, run_root)
        for run_root in (getattr(args, "compare_runs", None) or [])
    ]
    try:
        comparison = _privacy_safe_comparison(compare_runs(run_roots), root)
    except RoundCommitReadError as exc:
        console.print(f"[red]Run comparison blocked: {exc.code}.[/red]")
        raise SystemExit(_EXIT_STARTUP_ERROR) from None
    output_arg = getattr(args, "compare_output", None)
    if output_arg:
        try:
            output_path = _resolve_repo_relative_path(root, output_arg)
            authorized_output_path = output_path.parent.resolve(strict=False) / output_path.name
            write_json_file(authorized_output_path, comparison)
        except (OSError, RuntimeError):
            console.print(
                "[red]Run comparison output error: output path is unsafe or unavailable.[/red]"
            )
            raise SystemExit(_EXIT_OPERATION_ERROR) from None
        console.print(
            f"[green]Saved run comparison:[/green] {_display_repo_path(root, output_path)}"
        )
    console.print_json(data=comparison)
    return comparison


def _run_analyze_cli(args: argparse.Namespace, console: Console, root: Path) -> dict[str, object]:
    run_root = _resolve_repo_relative_path(root, str(getattr(args, "analyze_run", "")))
    try:
        analysis = _privacy_safe_run_analysis(analyze_run(run_root), root)
    except RoundCommitReadError as exc:
        console.print(f"[red]Run analysis blocked: {exc.code}.[/red]")
        raise SystemExit(_EXIT_STARTUP_ERROR) from None
    output_arg = getattr(args, "analyze_output", None)
    if output_arg:
        try:
            output_path = _resolve_repo_relative_path(root, output_arg)
            authorized_output_path = output_path.parent.resolve(strict=False) / output_path.name
            write_json_file(authorized_output_path, analysis)
        except (OSError, RuntimeError):
            console.print(
                "[red]Run analysis output error: output path is unsafe or unavailable.[/red]"
            )
            raise SystemExit(_EXIT_OPERATION_ERROR) from None
        console.print(f"[green]Saved run analysis:[/green] {_display_repo_path(root, output_path)}")
    console.print_json(data=analysis)
    return analysis


def _requires_generation_resources(args: argparse.Namespace) -> bool:
    return not any(
        getattr(args, mode, False)
        for mode in (
            "compare_runs",
            "analyze_run",
            "survey",
            "cloud_free_discover",
            "cloud_free_profile",
        )
    )


def _validate_model_provider_startup(
    *,
    args: argparse.Namespace,
    console: Console,
    provider: str,
    model_name: str,
    gemini_api_key_env: str,
    effective_gemini_api_key: str,
) -> None:
    if provider == MODEL_PROVIDER_OLLAMA:
        installed_models, ollama_error = list_installed_ollama_models()
        if ollama_error:
            console.print(f"[red]{ollama_error}[/red]")
            console.print("[yellow]Start Ollama service, then retry.[/yellow]")
            raise SystemExit(_EXIT_STARTUP_ERROR)
        if model_name not in installed_models:
            console.print(
                f"[red]Model {model_name} is not installed. Run: ollama pull {model_name}[/red]"
            )
            if args.model is None and "llama3.1:8b" in installed_models:
                console.print("[yellow]Suggestion: fallback available -> llama3.1:8b[/yellow]")
            raise SystemExit(_EXIT_STARTUP_ERROR)
    elif provider == MODEL_PROVIDER_GEMINI:
        if not _has_gemini_api_key_source(
            api_key_env=gemini_api_key_env,
            config_api_key=effective_gemini_api_key,
        ):
            console.print(
                "[red]Gemini API key is missing. Set the configured environment variable, "
                "GEMINI_API_KEY, or GOOGLE_API_KEY, then retry.[/red]"
            )
            raise SystemExit(_EXIT_STARTUP_ERROR)
    else:
        console.print(f"[red]Unsupported model provider: {provider}[/red]")
        raise SystemExit(_EXIT_STARTUP_ERROR)


def main() -> None:
    args = parse_args()
    configure_logging()
    console = Console()
    try:
        layout = resolve_runtime_layout(cli_file=__file__)
    except PackageResourceError as exc:
        console.print(f"[red]Package resource error: {exc}[/red]")
        raise SystemExit(_EXIT_STARTUP_ERROR) from None
    root = layout.workspace_root
    if getattr(args, "compare_runs", None):
        _run_compare_cli(args, console, root)
        return
    if getattr(args, "analyze_run", None):
        _run_analyze_cli(args, console, root)
        return
    if _requires_generation_resources(args):
        try:
            validate_generation_resources(layout)
        except PackageResourceError as exc:
            console.print(f"[red]Package resource error: {exc}[/red]")
            raise SystemExit(_EXIT_STARTUP_ERROR) from None

    config_path = root / "config.yaml"
    try:
        config = load_app_config(config_path)
    except (ConfigValidationError, FileNotFoundError) as exc:
        if getattr(args, "mock", False) and isinstance(exc, FileNotFoundError):
            config_path = layout.config_example_path
            try:
                config = load_app_config(config_path)
            except (ConfigValidationError, FileNotFoundError) as fallback_exc:
                console.print(f"[red]Config error: {fallback_exc}[/red]")
                raise SystemExit(_EXIT_STARTUP_ERROR) from None
            console.print(
                "[yellow]config.yaml not found; mock mode is using config.example.yaml "
                "without creating local config.[/yellow]"
            )
        else:
            console.print(f"[red]Config error: {exc}[/red]")
            raise SystemExit(_EXIT_STARTUP_ERROR) from None

    (
        config_provider,
        config_model_name,
        config_temperature,
        config_timeout,
        config_gemini,
    ) = resolve_model_provider_settings(config)
    provider = args.provider or config_provider
    model_name = args.model or config_model_name
    if args.cloud_free_discover or args.cloud_free_profile:
        provider = MODEL_PROVIDER_GEMINI
        if args.model is None:
            model_name = DEFAULT_GEMINI_MODEL
    gemini_api_key_env = args.gemini_api_key_env or config_gemini.api_key_env
    gemini_config = replace(config_gemini, api_key_env=gemini_api_key_env)
    gemini_api_key_override = ""
    gemini_api_key_override_env = getattr(args, "gemini_api_key_override_env", None)
    if gemini_api_key_override_env:
        gemini_api_key_override = os.environ.get(
            gemini_api_key_override_env,
            "",
        ).strip()
    effective_gemini_api_key = gemini_api_key_override or gemini_config.api_key
    try:
        cloud_free_config = _apply_cloud_free_arg_overrides(config, args)
    except NumericCliOverrideError as exc:
        console.print(f"[red]Argument error: {exc}.[/red]")
        raise SystemExit(_EXIT_STARTUP_ERROR) from None
    model_label = format_model_label(provider, model_name)
    base_url = config.ollama_base_url
    project_name = args.project.strip() if args.project else config.project_name
    project_error = _validate_project_override(project_name)
    if project_error:
        console.print(f"[red]{project_error}[/red]")
        raise SystemExit(_EXIT_STARTUP_ERROR)
    benchmark_preset = getattr(args, "benchmark_preset", None)
    max_rounds_override = getattr(args, "max_rounds", None)
    max_provider_quota_failures = getattr(args, "max_provider_quota_failures", 2)
    preset_rounds = benchmark_preset_rounds(benchmark_preset)
    max_rounds = config.max_rounds
    if preset_rounds is not None:
        max_rounds = preset_rounds
    if max_rounds_override is not None:
        max_rounds = max_rounds_override
    if getattr(args, "mock", False) and max_rounds_override is None:
        max_rounds = min(max_rounds, MOCK_DEFAULT_ROUNDS)
    continuous_max_rounds = 9999
    if preset_rounds is not None:
        continuous_max_rounds = preset_rounds
    if max_rounds_override is not None:
        continuous_max_rounds = max_rounds_override
    stop_if_no_improvement_rounds = config.stop_if_no_improvement_rounds
    normal_max_runtime_seconds, continuous_max_runtime_seconds = resolve_runtime_limits(config)
    temperature = config_temperature
    top_p = config.top_p
    timeout_seconds = config_timeout
    if args.max_prompt_chars is not None:
        max_prompt_chars = args.max_prompt_chars
    elif args.provider and provider != config_provider:
        max_prompt_chars = (
            DEFAULT_GEMINI_MAX_PROMPT_CHARS
            if provider == MODEL_PROVIDER_GEMINI
            else DEFAULT_OLLAMA_MAX_PROMPT_CHARS
        )
    else:
        max_prompt_chars = config.model.max_prompt_chars
    model_parameters = {
        "temperature": temperature,
        "top_p": top_p,
        "timeout_seconds": timeout_seconds,
        "max_prompt_chars": max_prompt_chars,
    }
    topic_context = format_topic_context(config.topic)
    topic_keywords = config.topic.keywords
    drafting_mode = getattr(args, "drafting_mode", None) or config.drafting_mode
    topic_snapshot = {
        "title": config.topic.title,
        "description": config.topic.description,
        "keywords": list(config.topic.keywords),
    }

    try:
        project_seeded = seed_default_mock_project(
            layout,
            mock_mode=getattr(args, "mock", False),
            project_name=project_name,
            explicit_project=args.project is not None,
        )
    except PackageResourceError as exc:
        console.print(f"[red]Project input error: {exc}[/red]")
        raise SystemExit(_EXIT_STARTUP_ERROR) from None
    if project_seeded:
        console.print(
            "[yellow]Installed mock workspace seeded projects/example/task.md from the "
            "bundled example; existing files were not changed.[/yellow]"
        )

    project_dir = root / "projects" / project_name
    memory_path = project_dir / "memory.md"
    prompts_dir = layout.prompts_dir

    try:
        project_input = load_project_input(
            root=root,
            project_name=project_name,
            explicit_project=args.project is not None,
        )
    except ProjectInputError as exc:
        console.print(f"[red]Project input error: {exc}[/red]")
        raise SystemExit(_EXIT_STARTUP_ERROR) from None
    project_dir = project_input.project_dir
    memory_path = project_dir / "memory.md"
    task_text = project_input.task_text
    project_metadata = project_input.as_metadata()
    console.print(
        "[bold cyan]Project input:[/bold cyan] "
        f"kind={project_input.source_kind} | name={project_input.project_name} | "
        f"title={project_input.project_title} | "
        f"task={_display_repo_path(root, project_input.task_path)}"
    )
    try:
        ensure_project_runtime_paths_safe(project_dir)
    except OSError:
        lock_message = _unsafe_lock_path_message(project_dir)
        if lock_message:
            console.print(f"[red]{lock_message}[/red]")
            _print_run_lock_recovery_hint(console, root, project_dir)
        else:
            console.print(
                "[red]Project artifact error: an automatic project path is unsafe or "
                "unavailable.[/red]"
            )
        raise SystemExit(_EXIT_STARTUP_ERROR) from None

    if getattr(args, "survey", False):
        survey_output = getattr(args, "survey_output", None)
        survey_output_path = Path(survey_output).expanduser() if survey_output else None
        if survey_output_path is not None and not survey_output_path.is_absolute():
            survey_output_path = project_dir / survey_output_path
        run_lock_path = None
        try:
            run_lock_path, lock_error = acquire_run_lock(
                project_dir,
                mode="literature_survey",
                model_name="local-deterministic",
            )
            if lock_error:
                console.print(f"[red]{lock_error}[/red]")
                _print_run_lock_recovery_hint(console, root, project_dir)
                raise SystemExit(_EXIT_STARTUP_ERROR)
            run_literature_survey_mode(
                console=console,
                project_input=project_input,
                config=config.literature_survey,
                output_path=survey_output_path,
            )
        except KeyboardInterrupt:
            console.print(
                "[red]Manual interrupt detected in literature survey. "
                "Stop reason: MANUAL_INTERRUPT[/red]"
            )
            raise SystemExit(_EXIT_INTERRUPTED) from None
        except OSError:
            console.print(
                "[red]Survey artifact error: an automatic output path is unsafe or "
                "unavailable.[/red]"
            )
            raise SystemExit(_EXIT_OPERATION_ERROR) from None
        finally:
            release_run_lock(run_lock_path)
        return

    if getattr(args, "mock", False):
        provider = MOCK_MODEL_PROVIDER
        model_name = MOCK_MODEL_NAME
        model_label = MOCK_MODEL_NAME
        model_parameters = mock_model_parameters(max_prompt_chars=max_prompt_chars)
        project_metadata["mock_mode"] = {
            "provider_free": True,
            "deterministic": True,
            "config_path": _display_repo_path(root, config_path),
            "default_rounds": MOCK_DEFAULT_ROUNDS,
            "rounds_limited_by_default": max_rounds_override is None,
        }
        console.print(
            "[bold cyan]Mock mode:[/bold cyan] deterministic provider-free run; "
            "no Ollama, Gemini, network, or API key calls will be made."
        )
        console.print(
            f"[cyan]Mock mode will write normal run artifacts for {max_rounds} round(s).[/cyan]"
        )
        requested_mode = "mock"
        run_lock_path = None
        try:
            run_lock_path, lock_error = acquire_run_lock(
                project_dir,
                mode=requested_mode,
                model_name=model_label,
            )
            if lock_error:
                console.print(f"[red]{lock_error}[/red]")
                _print_run_lock_recovery_hint(console, root, project_dir)
                raise SystemExit(_EXIT_STARTUP_ERROR)
            _recover_pending_round_commit(
                console=console,
                project_dir=project_dir,
            )
            agents = build_mock_agents(topic_context=topic_context)
            run_iterative_rounds(
                console=console,
                agents=agents,
                task_text=task_text,
                project_dir=project_dir,
                memory_path=memory_path,
                mode=requested_mode,
                model_name=model_label,
                max_rounds=max_rounds,
                stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
                global_max_runtime_seconds=normal_max_runtime_seconds,
                per_agent_timeout_seconds=1,
                topic_keywords=topic_keywords,
                project_metadata=project_metadata,
                model_provider=provider,
                model_parameters=model_parameters,
                topic_snapshot=topic_snapshot,
                prompt_dir=prompts_dir,
                repo_root=root,
                git_root=layout.git_root,
                drafting_mode=drafting_mode,
                max_consecutive_provider_quota_failures=max_provider_quota_failures,
            )
        except KeyboardInterrupt:
            console.print(
                "[red]Manual interrupt detected in mock loop. Stop reason: MANUAL_INTERRUPT[/red]"
            )
            raise SystemExit(_EXIT_INTERRUPTED) from None
        finally:
            release_run_lock(run_lock_path)
        return

    if args.cloud_free_discover or args.cloud_free_profile:
        _validate_model_provider_startup(
            args=args,
            console=console,
            provider=provider,
            model_name=model_name,
            gemini_api_key_env=gemini_api_key_env,
            effective_gemini_api_key=effective_gemini_api_key,
        )

    if args.cloud_free_discover:
        discovered, error = discover_free_cloud_models(
            api_key_env=gemini_api_key_env,
            api_key=effective_gemini_api_key,
            config=cloud_free_config,
        )
        if error:
            console.print(f"[red]Cloud model discovery failed: {error}[/red]")
            raise SystemExit(_EXIT_OPERATION_ERROR)
        try:
            artifact = save_discovery_artifact(project_dir, discovered)
        except OSError:
            console.print(
                "[red]Cloud artifact error: automatic output is unsafe or unavailable.[/red]"
            )
            raise SystemExit(_EXIT_OPERATION_ERROR) from None
        candidates = build_candidate_pool(
            discovered_models=discovered,
            configured_models=gemini_config.models,
            config=cloud_free_config,
        )
        console.print(f"[green]Discovered {len(discovered)} cloud models.[/green]")
        console.print(f"[green]Safe free-run candidates: {len(candidates)}[/green]")
        _print_cloud_model_table(console, candidates)
        console.print(
            f"[cyan]Saved discovery artifact:[/cyan] {_display_repo_path(root, artifact)}"
        )
        return

    if args.cloud_free_profile:
        discovered, error = discover_free_cloud_models(
            api_key_env=gemini_api_key_env,
            api_key=effective_gemini_api_key,
            config=cloud_free_config,
        )
        if error:
            console.print(
                f"[yellow]Discovery failed; profiling configured seeds only: {error}[/yellow]"
            )
            discovered = []
        else:
            try:
                save_discovery_artifact(project_dir, discovered)
            except OSError:
                console.print(
                    "[red]Cloud artifact error: automatic output is unsafe or unavailable.[/red]"
                )
                raise SystemExit(_EXIT_OPERATION_ERROR) from None
        candidates = build_candidate_pool(
            discovered_models=discovered,
            configured_models=gemini_config.models,
            config=cloud_free_config,
        )
        safe_candidates = filter_safe_text_models(candidates, include_unavailable=True)
        profiles = profile_free_cloud_models(
            candidates=safe_candidates,
            api_key_env=gemini_api_key_env,
            api_key=effective_gemini_api_key,
            timeout_seconds=timeout_seconds,
        )
        try:
            artifact = save_profile_artifact(project_dir, profiles)
        except OSError:
            console.print(
                "[red]Cloud artifact error: automatic output is unsafe or unavailable.[/red]"
            )
            raise SystemExit(_EXIT_OPERATION_ERROR) from None
        recommendation = recommend_free_cloud_model(
            candidates=safe_candidates,
            profiles=profiles,
            preset=cloud_free_config.free_runner_preset,
        )
        console.print(f"[green]Profiled {len(profiles)} safe free-run candidates.[/green]")
        if recommendation:
            console.print(
                "[cyan]Recommended model:[/cyan] "
                f"{recommendation.model_id} ({recommendation.reason})"
            )
        console.print(f"[cyan]Saved profile artifact:[/cyan] {_display_repo_path(root, artifact)}")
        return

    if (
        provider == MODEL_PROVIDER_GEMINI
        and cloud_free_config.cloud_free_mode
        and cloud_free_config.free_runner_preset != FREE_RUNNER_MANUAL
        and args.model is None
    ):
        discovered = load_discovery_artifact(project_dir)
        profiles = load_profile_artifact(project_dir)
        candidates = build_cached_candidate_pool(
            discovered_models=discovered,
            configured_models=gemini_config.models,
            profiles=profiles,
            config=cloud_free_config,
        )
        recommendation = recommend_free_cloud_model(
            candidates=candidates,
            profiles=profiles,
            preset=cloud_free_config.free_runner_preset,
        )
        if recommendation:
            model_name = recommendation.model_id
            model_label = format_model_label(provider, model_name)
            console.print(
                f"[cyan]Cloud free runner selected {model_name}: {recommendation.reason}[/cyan]"
            )

    provider_label = "Local" if provider == MODEL_PROVIDER_OLLAMA else "Cloud"
    console.print(
        f"[bold cyan]{provider_label}: Using provider: {provider} | model: {model_name}[/bold cyan]"
    )

    requested_mode = "normal"
    if args.continuous:
        requested_mode = "continuous"
    elif args.diagnostic:
        requested_mode = "diagnostic"
    elif args.session:
        requested_mode = "session"
    elif args.resume:
        requested_mode = "resume"

    planned_rounds_for_budget = max_rounds
    if requested_mode == "diagnostic":
        planned_rounds_for_budget = 1
    elif requested_mode == "continuous":
        planned_rounds_for_budget = continuous_max_rounds
    request_budget = estimate_request_budget(
        provider=provider,
        mode=requested_mode,
        planned_rounds=planned_rounds_for_budget,
    )
    for line in format_request_budget_estimate(request_budget):
        console.print(f"[yellow]{line}[/yellow]" if "warning" in line else f"[cyan]{line}[/cyan]")
    project_metadata["request_budget"] = asdict(request_budget)
    if benchmark_preset:
        project_metadata["benchmark_preset"] = benchmark_preset

    run_lock_path = None
    try:
        run_lock_path, lock_error = acquire_run_lock(
            project_dir,
            mode=requested_mode,
            model_name=model_label,
        )
        if lock_error:
            console.print(f"[red]{lock_error}[/red]")
            _print_run_lock_recovery_hint(console, root, project_dir)
            raise SystemExit(_EXIT_STARTUP_ERROR)
        if requested_mode != "diagnostic":
            _recover_pending_round_commit(
                console=console,
                project_dir=project_dir,
            )
        _validate_model_provider_startup(
            args=args,
            console=console,
            provider=provider,
            model_name=model_name,
            gemini_api_key_env=gemini_api_key_env,
            effective_gemini_api_key=effective_gemini_api_key,
        )
        llm = create_llm_client(
            provider=provider,
            model_name=model_name,
            ollama_base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_prompt_chars=max_prompt_chars,
            gemini_config=gemini_config,
            explicit_gemini_api_key=gemini_api_key_override,
            cloud_free_config=cloud_free_config
            if provider == MODEL_PROVIDER_GEMINI and cloud_free_config.cloud_free_mode
            else None,
        )
        agents = ResearchAgents.from_prompt_dir(
            llm=llm,
            prompt_dir=prompts_dir,
            temperature=temperature,
            top_p=top_p,
            topic_context=topic_context,
        )

        if args.resume:
            try:
                resume_started = run_resume_mode(
                    console=console,
                    agents=agents,
                    task_text=task_text,
                    project_dir=project_dir,
                    memory_path=memory_path,
                    model_name=model_label,
                    max_rounds=max_rounds,
                    stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
                    global_max_runtime_seconds=normal_max_runtime_seconds,
                    per_agent_timeout_seconds=timeout_seconds,
                    topic_keywords=topic_keywords,
                    project_metadata=project_metadata,
                    model_provider=provider,
                    model_parameters=model_parameters,
                    topic_snapshot=topic_snapshot,
                    prompt_dir=prompts_dir,
                    repo_root=root,
                    git_root=layout.git_root,
                    drafting_mode=drafting_mode,
                    max_consecutive_provider_quota_failures=max_provider_quota_failures,
                )
            except ResumeHistoryError:
                raise SystemExit(2) from None
            if not resume_started:
                raise SystemExit(2)
            return

        if args.continuous:
            run_iterative_rounds(
                console=console,
                agents=agents,
                task_text=task_text,
                project_dir=project_dir,
                memory_path=memory_path,
                mode="continuous",
                model_name=model_label,
                max_rounds=continuous_max_rounds,
                stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
                global_max_runtime_seconds=continuous_max_runtime_seconds,
                per_agent_timeout_seconds=timeout_seconds,
                disable_no_improvement_stop=True,
                disable_timeout_stop=True,
                topic_keywords=topic_keywords,
                project_metadata=project_metadata,
                model_provider=provider,
                model_parameters=model_parameters,
                topic_snapshot=topic_snapshot,
                prompt_dir=prompts_dir,
                repo_root=root,
                git_root=layout.git_root,
                drafting_mode=drafting_mode,
                max_consecutive_provider_quota_failures=max_provider_quota_failures,
            )
            return

        if args.diagnostic:
            run_diagnostic_mode(
                console=console,
                llm=llm,
                task_text=task_text,
                project_dir=project_dir,
                memory_path=memory_path,
                model_name=model_label,
                topic_context=topic_context,
                project_metadata=project_metadata,
                model_provider=provider,
                model_parameters=model_parameters,
                topic_snapshot=topic_snapshot,
                prompt_dir=prompts_dir,
                repo_root=root,
                git_root=layout.git_root,
                drafting_mode=drafting_mode,
            )
            return

        if args.session:
            run_session_mode(
                console=console,
                llm=llm,
                agents=agents,
                task_text=task_text,
                project_dir=project_dir,
                memory_path=memory_path,
                model_name=model_label,
                max_rounds=max_rounds,
                stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
                global_max_runtime_seconds=normal_max_runtime_seconds,
                per_agent_timeout_seconds=timeout_seconds,
                topic_context=topic_context,
                topic_title=config.topic.title,
                topic_keywords=topic_keywords,
                project_metadata=project_metadata,
                model_provider=provider,
                model_parameters=model_parameters,
                topic_snapshot=topic_snapshot,
                prompt_dir=prompts_dir,
                repo_root=root,
                git_root=layout.git_root,
                drafting_mode=drafting_mode,
                max_consecutive_provider_quota_failures=max_provider_quota_failures,
            )
            return

        run_iterative_rounds(
            console=console,
            agents=agents,
            task_text=task_text,
            project_dir=project_dir,
            memory_path=memory_path,
            mode="normal",
            model_name=model_label,
            max_rounds=max_rounds,
            stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
            global_max_runtime_seconds=normal_max_runtime_seconds,
            per_agent_timeout_seconds=timeout_seconds,
            topic_keywords=topic_keywords,
            project_metadata=project_metadata,
            model_provider=provider,
            model_parameters=model_parameters,
            topic_snapshot=topic_snapshot,
            prompt_dir=prompts_dir,
            repo_root=root,
            git_root=layout.git_root,
            drafting_mode=drafting_mode,
            max_consecutive_provider_quota_failures=max_provider_quota_failures,
        )
    except KeyboardInterrupt:
        console.print(
            "[red]Manual interrupt detected in main loop. Stop reason: MANUAL_INTERRUPT[/red]"
        )
        raise SystemExit(_EXIT_INTERRUPTED) from None
    finally:
        release_run_lock(run_lock_path)
