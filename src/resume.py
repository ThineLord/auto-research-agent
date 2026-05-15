"""Checkpoint resume workflow."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from .agents import ResearchAgents
from .runner import run_iterative_rounds
from .storage import read_json_file


def run_resume_mode(
    *,
    console: Console,
    agents: ResearchAgents,
    task_text: str,
    project_dir: Path,
    memory_path: Path,
    model_name: str,
    max_rounds: int,
    stop_if_no_improvement_rounds: int,
    global_max_runtime_seconds: int,
    per_agent_timeout_seconds: int,
) -> None:
    checkpoint_path = project_dir / "checkpoint.json"
    checkpoint = read_json_file(checkpoint_path)
    if not checkpoint or not checkpoint.get("can_resume"):
        console.print("[red]Cannot resume: checkpoint.json missing or can_resume is false.[/red]")
        return
    run_root_str = str(checkpoint.get("run_root", "")).strip()
    if not run_root_str:
        console.print("[red]Cannot resume: checkpoint run_root is missing.[/red]")
        return
    run_root_path = Path(run_root_str)
    if not run_root_path.exists():
        console.print("[red]Cannot resume: checkpoint run_root does not exist.[/red]")
        return
    start_round = int(checkpoint.get("last_completed_round", 0)) + 1
    initial_best_score = float(checkpoint.get("best_score", -1.0))
    console.print(
        f"[cyan]Resuming from checkpoint:[/cyan] start_round={start_round}, "
        f"run_root={run_root_path}"
    )
    run_iterative_rounds(
        console=console,
        agents=agents,
        task_text=task_text,
        project_dir=project_dir,
        memory_path=memory_path,
        mode="resume",
        model_name=model_name,
        max_rounds=max(max_rounds, start_round),
        stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
        global_max_runtime_seconds=global_max_runtime_seconds,
        per_agent_timeout_seconds=per_agent_timeout_seconds,
        start_round=start_round,
        run_root_override=run_root_path,
        initial_best_score=initial_best_score,
    )
