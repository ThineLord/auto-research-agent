"""Entry point for the local iterative research pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
from rich.console import Console

from .agents import ResearchAgents
from .llm import OllamaClient
from .storage import (
    make_round_dir,
    make_run_root,
    parse_score,
    read_text,
    save_round_outputs,
    write_text,
)


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> None:
    console = Console()
    root = Path(__file__).resolve().parent.parent
    config = load_config(root / "config.yaml")

    model = config.get("model", "llama3.1:8b")
    base_url = config.get("ollama_base_url", "http://localhost:11434")
    project_name = config.get("project_name", "pama")
    max_rounds = int(config.get("max_rounds", 5))
    temperature = float(config.get("temperature", 0.4))
    top_p = float(config.get("top_p", 0.9))
    timeout_seconds = int(config.get("timeout_seconds", 120))

    project_dir = root / "projects" / project_name
    prompts_dir = root / "prompts"

    task_text = read_text(project_dir / "task.md")
    memory_text = read_text(project_dir / "memory.md")
    if not task_text:
        raise ValueError(f"Task file is empty: {project_dir / 'task.md'}")

    llm = OllamaClient(
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    agents = ResearchAgents.from_prompt_dir(
        llm=llm,
        prompt_dir=prompts_dir,
        temperature=temperature,
        top_p=top_p,
    )

    run_root = make_run_root(project_dir)
    console.print(f"[cyan]Run directory:[/cyan] {run_root}")

    best_score = -1.0
    best_output = ""
    previous_judge = ""

    for round_index in range(1, max_rounds + 1):
        console.rule(f"Round {round_index}")
        round_dir = make_round_dir(run_root, round_index)

        draft_output = agents.draft(
            task=task_text,
            memory=memory_text,
            round_index=round_index,
            previous_best=best_output,
            previous_judge=previous_judge,
        )
        review_output = agents.review(
            task=task_text,
            memory=memory_text,
            draft_output=draft_output,
        )
        revised_output = agents.revise(
            task=task_text,
            memory=memory_text,
            draft_output=draft_output,
            review_output=review_output,
        )
        judge_output = agents.judge(
            task=task_text,
            memory=memory_text,
            revised_output=revised_output,
        )

        save_round_outputs(
            round_dir,
            draft=draft_output,
            review=review_output,
            revised=revised_output,
            judge=judge_output,
        )
        console.print(f"[green]Saved round outputs:[/green] {round_dir}")

        score = parse_score(judge_output)
        shown_score = "N/A" if score is None else f"{score:.2f}"
        console.print(f"[yellow]Judge score:[/yellow] {shown_score}")

        improved = score is not None and score > best_score
        if improved:
            best_score = score  # type: ignore[assignment]
            best_output = revised_output
            write_text(project_dir / "best_output.md", best_output)
            console.print(
                f"[bold green]New best score:[/bold green] {best_score:.2f} -> updated best_output.md"
            )
        else:
            console.print(
                "[magenta]No score improvement detected. Stopping early.[/magenta]"
            )
            break

        previous_judge = judge_output

    if best_output:
        console.print(f"[bold cyan]Best score:[/bold cyan] {best_score:.2f}")
    else:
        console.print(
            "[red]No valid score found from judge output. best_output.md was not updated.[/red]"
        )


if __name__ == "__main__":
    main()
