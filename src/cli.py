"""Command-line entrypoint and mode dispatch."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from .agents import ResearchAgents
from .config import (
    list_installed_ollama_models,
    load_config,
    resolve_model_settings,
    resolve_runtime_limits,
)
from .constants import RUN_LOCK_FILENAME
from .diagnostic import run_diagnostic_mode
from .llm import OllamaClient
from .resume import run_resume_mode
from .runner import run_iterative_rounds
from .runtime import acquire_run_lock, release_run_lock
from .session import run_session_mode
from .storage import read_text


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
        "--model",
        type=str,
        default=None,
        help="Override Ollama model name, e.g. qwen3:8b",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    console = Console()
    root = Path(__file__).resolve().parent.parent
    config = load_config(root / "config.yaml")

    config_model_name, config_temperature, config_timeout = resolve_model_settings(config)
    model_name = args.model or config_model_name
    base_url = config.get("ollama_base_url", "http://localhost:11434")
    project_name = config.get("project_name", "pama")
    max_rounds = int(config.get("max_rounds", 5))
    stop_if_no_improvement_rounds = int(config.get("stop_if_no_improvement_rounds", 2))
    normal_max_runtime_seconds, continuous_max_runtime_seconds = resolve_runtime_limits(config)
    temperature = float(config_temperature)
    top_p = float(config.get("top_p", 0.9))
    timeout_seconds = max(1, min(int(config_timeout), 300))

    project_dir = root / "projects" / project_name
    memory_path = project_dir / "memory.md"
    prompts_dir = root / "prompts"

    task_text = read_text(project_dir / "task.md")
    if not task_text:
        raise ValueError(f"Task file is empty: {project_dir / 'task.md'}")

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

    console.print(f"[bold cyan]Using model: {model_name}[/bold cyan]")

    requested_mode = "normal"
    if args.continuous:
        requested_mode = "continuous"
    elif args.diagnostic:
        requested_mode = "diagnostic"
    elif args.session:
        requested_mode = "session"
    elif args.resume:
        requested_mode = "resume"

    run_lock_path, lock_error = acquire_run_lock(
        project_dir,
        mode=requested_mode,
        model_name=model_name,
    )
    if lock_error:
        console.print(f"[red]{lock_error}[/red]")
        console.print(
            f"[yellow]If this is stale, remove {project_dir / RUN_LOCK_FILENAME} and retry.[/yellow]"
        )
        return

    llm = OllamaClient(
        base_url=base_url,
        model=model_name,
        timeout_seconds=timeout_seconds,
    )
    agents = ResearchAgents.from_prompt_dir(
        llm=llm,
        prompt_dir=prompts_dir,
        temperature=temperature,
        top_p=top_p,
    )

    try:
        if args.resume:
            run_resume_mode(
                console=console,
                agents=agents,
                task_text=task_text,
                project_dir=project_dir,
                memory_path=memory_path,
                model_name=model_name,
                max_rounds=max_rounds,
                stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
                global_max_runtime_seconds=normal_max_runtime_seconds,
                per_agent_timeout_seconds=timeout_seconds,
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
                model_name=model_name,
                max_rounds=9999,
                stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
                global_max_runtime_seconds=continuous_max_runtime_seconds,
                per_agent_timeout_seconds=timeout_seconds,
                disable_no_improvement_stop=True,
                disable_timeout_stop=True,
            )
            return

        if args.diagnostic:
            run_diagnostic_mode(
                console=console,
                llm=llm,
                task_text=task_text,
                project_dir=project_dir,
                memory_path=memory_path,
                model_name=model_name,
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
                model_name=model_name,
                max_rounds=max_rounds,
                stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
                global_max_runtime_seconds=normal_max_runtime_seconds,
                per_agent_timeout_seconds=timeout_seconds,
            )
            return

        run_iterative_rounds(
            console=console,
            agents=agents,
            task_text=task_text,
            project_dir=project_dir,
            memory_path=memory_path,
            mode="normal",
            model_name=model_name,
            max_rounds=max_rounds,
            stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
            global_max_runtime_seconds=normal_max_runtime_seconds,
            per_agent_timeout_seconds=timeout_seconds,
        )
    except KeyboardInterrupt:
        console.print("[red]Manual interrupt detected in main loop. Stop reason: MANUAL_INTERRUPT[/red]")
    finally:
        release_run_lock(run_lock_path)
