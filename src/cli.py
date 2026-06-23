"""Command-line entrypoint and mode dispatch."""

from __future__ import annotations

import argparse
import os
from dataclasses import asdict, replace
from pathlib import Path
from typing import List, Optional

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
    DEFAULT_GEMINI_MAX_PROMPT_CHARS,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OLLAMA_MAX_PROMPT_CHARS,
    MODEL_PROVIDER_GEMINI,
    MODEL_PROVIDER_OLLAMA,
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
from .project_input import ProjectInputError, load_project_input
from .resume import run_resume_mode
from .runner import run_iterative_rounds
from .runtime import acquire_run_lock, release_run_lock
from .session import run_session_mode


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local iterative research agent")
    parser.add_argument(
        "--session",
        action="store_true",
        help="Run focused nightly research session workflow.",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Run lightweight one-round diagnostic workflow.",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuous round-by-round mode with safe stop support.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from projects/<project>/checkpoint.json.",
    )
    parser.add_argument(
        "--survey",
        action="store_true",
        help="Run local Literature Survey Mode without provider calls.",
    )
    parser.add_argument(
        "--survey-output",
        type=str,
        default=None,
        help="Override survey report path. Relative paths resolve under the selected project.",
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
        "--project",
        type=str,
        default=None,
        help="Override project folder name under projects/.",
    )
    parser.add_argument(
        "--cloud-free-discover",
        action="store_true",
        help="Discover safe free-run Gemini/Gemma text models and save an ignored artifact.",
    )
    parser.add_argument(
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
        type=float,
        default=None,
        help="Override cloud free scheduler minimum delay.",
    )
    parser.add_argument(
        "--max-delay-seconds",
        type=float,
        default=None,
        help="Override cloud free scheduler maximum delay.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="Override cloud free scheduler retry count.",
    )
    parser.add_argument(
        "--prompt-budget-chars",
        type=int,
        default=None,
        help="Override cloud free prompt budget in characters.",
    )
    parser.add_argument(
        "--max-prompt-chars",
        type=int,
        default=None,
        help="Override maximum prompt size before an LLM call fails fast.",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Override round count for normal/session/resume, or cap continuous mode.",
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
        type=int,
        default=2,
        help="Stop after this many consecutive provider quota/rate-limit failed rounds.",
    )
    return parser.parse_args(argv)


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
        updates["min_delay_seconds"] = max(0.0, args.min_delay_seconds)
    if args.max_delay_seconds is not None:
        updates["max_delay_seconds"] = max(0.0, args.max_delay_seconds)
    if args.max_retries is not None:
        updates["max_retries"] = max(0, args.max_retries)
    if args.prompt_budget_chars is not None:
        updates["prompt_budget_chars"] = max(1000, args.prompt_budget_chars)
    if updates:
        cloud_free_config = replace(cloud_free_config, **updates)
    return cloud_free_config


def main() -> None:
    args = parse_args()
    configure_logging()
    console = Console()
    root = Path(__file__).resolve().parent.parent
    try:
        config = load_app_config(root / "config.yaml")
    except (ConfigValidationError, FileNotFoundError) as exc:
        console.print(f"[red]Config error: {exc}[/red]")
        return

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
    cloud_free_config = _apply_cloud_free_arg_overrides(config, args)
    model_label = format_model_label(provider, model_name)
    base_url = config.ollama_base_url
    project_name = args.project.strip() if args.project else config.project_name
    project_error = _validate_project_override(project_name)
    if project_error:
        console.print(f"[red]{project_error}[/red]")
        return
    benchmark_preset = getattr(args, "benchmark_preset", None)
    max_rounds_override = getattr(args, "max_rounds", None)
    max_provider_quota_failures = max(0, getattr(args, "max_provider_quota_failures", 2))
    preset_rounds = benchmark_preset_rounds(benchmark_preset)
    max_rounds = config.max_rounds
    if preset_rounds is not None:
        max_rounds = preset_rounds
    if max_rounds_override is not None:
        max_rounds = max(1, max_rounds_override)
    continuous_max_rounds = 9999
    if preset_rounds is not None:
        continuous_max_rounds = preset_rounds
    if max_rounds_override is not None:
        continuous_max_rounds = max(1, max_rounds_override)
    stop_if_no_improvement_rounds = config.stop_if_no_improvement_rounds
    normal_max_runtime_seconds, continuous_max_runtime_seconds = resolve_runtime_limits(config)
    temperature = config_temperature
    top_p = config.top_p
    timeout_seconds = config_timeout
    if args.max_prompt_chars is not None:
        max_prompt_chars = max(1000, args.max_prompt_chars)
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
    topic_snapshot = {
        "title": config.topic.title,
        "description": config.topic.description,
        "keywords": list(config.topic.keywords),
    }

    project_dir = root / "projects" / project_name
    memory_path = project_dir / "memory.md"
    prompts_dir = root / "prompts"

    try:
        project_input = load_project_input(
            root=root,
            project_name=project_name,
            explicit_project=args.project is not None,
        )
    except ProjectInputError as exc:
        console.print(f"[red]Project input error: {exc}[/red]")
        return
    project_dir = project_input.project_dir
    memory_path = project_dir / "memory.md"
    task_text = project_input.task_text
    project_metadata = project_input.as_metadata()
    console.print(
        "[bold cyan]Project input:[/bold cyan] "
        f"kind={project_input.source_kind} | name={project_input.project_name} | "
        f"title={project_input.project_title} | task={project_input.task_path}"
    )

    if getattr(args, "survey", False):
        survey_output = getattr(args, "survey_output", None)
        survey_output_path = Path(survey_output).expanduser() if survey_output else None
        if survey_output_path is not None and not survey_output_path.is_absolute():
            survey_output_path = project_dir / survey_output_path
        run_lock_path, lock_error = acquire_run_lock(
            project_dir,
            mode="literature_survey",
            model_name="local-deterministic",
        )
        if lock_error:
            console.print(f"[red]{lock_error}[/red]")
            console.print(
                f"[yellow]If this is stale, remove {project_dir / RUN_LOCK_FILENAME} and retry.[/yellow]"
            )
            return
        try:
            run_literature_survey_mode(
                console=console,
                project_input=project_input,
                config=config.literature_survey,
                output_path=survey_output_path,
            )
        finally:
            release_run_lock(run_lock_path)
        return

    if provider == MODEL_PROVIDER_OLLAMA:
        installed_models, ollama_error = list_installed_ollama_models()
        if ollama_error:
            console.print(f"[red]{ollama_error}[/red]")
            console.print("[yellow]Start Ollama service, then retry.[/yellow]")
            return
        if model_name not in installed_models:
            console.print(
                f"[red]Model {model_name} is not installed. Run: ollama pull {model_name}[/red]"
            )
            if args.model is None and "llama3.1:8b" in installed_models:
                console.print("[yellow]Suggestion: fallback available -> llama3.1:8b[/yellow]")
            return
    elif provider == MODEL_PROVIDER_GEMINI:
        if not _has_gemini_api_key_source(
            api_key_env=gemini_api_key_env,
            config_api_key=gemini_config.api_key,
        ):
            console.print(
                "[red]Gemini API key is missing. Set the configured environment variable, "
                "GEMINI_API_KEY, or GOOGLE_API_KEY, then retry.[/red]"
            )
            return
    else:
        console.print(f"[red]Unsupported model provider: {provider}[/red]")
        return

    if args.cloud_free_discover:
        discovered, error = discover_free_cloud_models(
            api_key_env=gemini_api_key_env,
            api_key=gemini_config.api_key,
            config=cloud_free_config,
        )
        if error:
            console.print(f"[red]Cloud model discovery failed: {error}[/red]")
            return
        artifact = save_discovery_artifact(project_dir, discovered)
        candidates = build_candidate_pool(
            discovered_models=discovered,
            configured_models=gemini_config.models,
            config=cloud_free_config,
        )
        console.print(f"[green]Discovered {len(discovered)} cloud models.[/green]")
        console.print(f"[green]Safe free-run candidates: {len(candidates)}[/green]")
        _print_cloud_model_table(console, candidates)
        console.print(f"[cyan]Saved discovery artifact:[/cyan] {artifact}")
        return

    if args.cloud_free_profile:
        discovered, error = discover_free_cloud_models(
            api_key_env=gemini_api_key_env,
            api_key=gemini_config.api_key,
            config=cloud_free_config,
        )
        if error:
            console.print(
                f"[yellow]Discovery failed; profiling configured seeds only: {error}[/yellow]"
            )
            discovered = []
        else:
            save_discovery_artifact(project_dir, discovered)
        candidates = build_candidate_pool(
            discovered_models=discovered,
            configured_models=gemini_config.models,
            config=cloud_free_config,
        )
        safe_candidates = filter_safe_text_models(candidates, include_unavailable=True)
        profiles = profile_free_cloud_models(
            candidates=safe_candidates,
            api_key_env=gemini_api_key_env,
            api_key=gemini_config.api_key,
            timeout_seconds=timeout_seconds,
        )
        artifact = save_profile_artifact(project_dir, profiles)
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
        console.print(f"[cyan]Saved profile artifact:[/cyan] {artifact}")
        return

    if (
        provider == MODEL_PROVIDER_GEMINI
        and cloud_free_config.cloud_free_mode
        and cloud_free_config.free_runner_preset != FREE_RUNNER_MANUAL
        and args.model is None
    ):
        discovered = load_discovery_artifact(project_dir)
        profiles = load_profile_artifact(project_dir)
        candidates = build_candidate_pool(
            discovered_models=discovered,
            configured_models=gemini_config.models,
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

    run_lock_path, lock_error = acquire_run_lock(
        project_dir,
        mode=requested_mode,
        model_name=model_label,
    )
    if lock_error:
        console.print(f"[red]{lock_error}[/red]")
        console.print(
            f"[yellow]If this is stale, remove {project_dir / RUN_LOCK_FILENAME} and retry.[/yellow]"
        )
        return

    llm = create_llm_client(
        provider=provider,
        model_name=model_name,
        ollama_base_url=base_url,
        timeout_seconds=timeout_seconds,
        max_prompt_chars=max_prompt_chars,
        gemini_config=gemini_config,
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

    try:
        if args.resume:
            run_resume_mode(
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
                max_consecutive_provider_quota_failures=max_provider_quota_failures,
            )
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
            max_consecutive_provider_quota_failures=max_provider_quota_failures,
        )
    except KeyboardInterrupt:
        console.print(
            "[red]Manual interrupt detected in main loop. Stop reason: MANUAL_INTERRUPT[/red]"
        )
    finally:
        release_run_lock(run_lock_path)
