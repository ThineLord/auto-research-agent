"""Entry point for the local iterative research pipeline."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml
from rich.console import Console

from .agents import ResearchAgents
from .llm import OllamaClient
from .storage import (
    get_memory_for_prompt,
    make_round_dir,
    make_run_root,
    parse_score,
    read_text,
    save_round_outputs,
    summarize_round_memory,
    update_project_memory,
    write_score_history,
    write_text,
)


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _normalize_judge_text(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("score:"):
            continue
        lines.append(line.lower())
    merged = " ".join(lines)
    return re.sub(r"\s+", " ", merged).strip()


def _is_repetitive_judge(current: str, history: List[str]) -> bool:
    if not history:
        return False
    current_norm = _normalize_judge_text(current)
    if not current_norm:
        return False
    previous_norm = _normalize_judge_text(history[-1])
    if current_norm == previous_norm:
        return True
    similarity = SequenceMatcher(None, current_norm, previous_norm).ratio()
    return similarity >= 0.95


def _run_agent_step(
    *,
    console: Console,
    round_index: int,
    agent_name: str,
    call: Callable[[], str],
) -> Tuple[str, Optional[str]]:
    console.print(f"[Round {round_index}] Running {agent_name} agent...")
    try:
        output = call()
        console.print(f"[Round {round_index}] {agent_name.capitalize()} finished.")
        return output, None
    except RuntimeError as exc:
        console.print(f"[red][Round {round_index}] {agent_name} failed: {exc}[/red]")
        return f"[{agent_name.upper()} ERROR] {exc}", str(exc)


def main() -> None:
    console = Console()
    root = Path(__file__).resolve().parent.parent
    config = load_config(root / "config.yaml")

    model = config.get("model", "llama3.1:8b")
    base_url = config.get("ollama_base_url", "http://localhost:11434")
    project_name = config.get("project_name", "pama")
    max_rounds = int(config.get("max_rounds", 5))
    stop_if_no_improvement_rounds = int(config.get("stop_if_no_improvement_rounds", 2))
    temperature = float(config.get("temperature", 0.4))
    top_p = float(config.get("top_p", 0.9))
    timeout_seconds = int(config.get("timeout_seconds", 120))

    project_dir = root / "projects" / project_name
    memory_path = project_dir / "memory.md"
    prompts_dir = root / "prompts"

    task_text = read_text(project_dir / "task.md")
    memory_text = get_memory_for_prompt(memory_path)
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
    best_round: Optional[int] = None
    previous_judge = ""
    judge_history: List[str] = []
    score_history: List[Dict[str, Any]] = []
    score_history_path = project_dir / "score_history.json"
    non_improve_streak = 0
    stop_reason = "max_rounds reached"
    completed_rounds = 0

    for round_index in range(1, max_rounds + 1):
        console.rule(f"Round {round_index}")
        round_dir = make_round_dir(run_root, round_index)

        draft_output, draft_error = _run_agent_step(
            console=console,
            round_index=round_index,
            agent_name="draft",
            call=lambda: agents.draft(
                task=task_text,
                memory=memory_text,
                round_index=round_index,
                previous_best=best_output,
                previous_judge=previous_judge,
            ),
        )
        if draft_error:
            review_output = "[REVIEW SKIPPED] draft agent failed."
            review_error = "skipped due to draft failure"
            console.print(
                f"[yellow][Round {round_index}] Skipping review agent due to draft failure.[/yellow]"
            )
        else:
            review_output, review_error = _run_agent_step(
                console=console,
                round_index=round_index,
                agent_name="review",
                call=lambda: agents.review(
                    task=task_text,
                    memory=memory_text,
                    draft_output=draft_output,
                ),
            )

        if draft_error or review_error:
            revised_output = "[REVISE SKIPPED] draft/review agent failed."
            revise_error = "skipped due to upstream failure"
            console.print(
                f"[yellow][Round {round_index}] Skipping revise agent due to upstream failure.[/yellow]"
            )
        else:
            revised_output, revise_error = _run_agent_step(
                console=console,
                round_index=round_index,
                agent_name="revise",
                call=lambda: agents.revise(
                    task=task_text,
                    memory=memory_text,
                    draft_output=draft_output,
                    review_output=review_output,
                ),
            )

        if revise_error:
            judge_output = "SCORE: 0\n- Judge skipped because revise step failed."
            judge_error = "skipped due to revise failure"
            console.print(
                f"[yellow][Round {round_index}] Skipping judge agent due to revise failure (score=0).[/yellow]"
            )
        else:
            judge_output, judge_error = _run_agent_step(
                console=console,
                round_index=round_index,
                agent_name="judge",
                call=lambda: agents.judge(
                    task=task_text,
                    memory=memory_text,
                    revised_output=revised_output,
                ),
            )

        round_errors = [err for err in [draft_error, review_error, revise_error, judge_error] if err]
        if round_errors:
            console.print(
                f"[yellow][Round {round_index}] Agent errors detected: {len(round_errors)}[/yellow]"
            )

        save_round_outputs(
            round_dir,
            draft=draft_output,
            review=review_output,
            revised=revised_output,
            judge=judge_output,
        )
        console.print(f"[green]Saved round outputs:[/green] {round_dir}")

        parsed_score = parse_score(judge_output)
        if parsed_score is None:
            score = 0.0
            console.print(
                "[yellow]Judge score parsing failed; fallback score = 0.00[/yellow]"
            )
        else:
            score = parsed_score
        console.print(f"[yellow]Judge score:[/yellow] {score:.2f}")
        completed_rounds = round_index

        improved = score > best_score
        if improved:
            best_score = score
            best_round = round_index
            best_output = revised_output
            write_text(project_dir / "best_output.md", best_output)
            non_improve_streak = 0
            console.print(
                f"[bold green]New best score:[/bold green] {best_score:.2f} -> updated best_output.md"
            )
        else:
            non_improve_streak += 1

        repetitive_judge = _is_repetitive_judge(judge_output, judge_history)
        judge_history.append(judge_output)

        score_history.append(
            {
                "round": round_index,
                "score": score,
                "improved": improved,
                "non_improve_streak": non_improve_streak,
                "repetitive_judge": repetitive_judge,
            }
        )
        write_score_history(score_history_path, score_history)

        memory_summary = summarize_round_memory(
            revised_output=revised_output,
            review_output=review_output,
            judge_output=judge_output,
            current_best_score=best_score,
        )
        update_project_memory(
            memory_path=memory_path,
            round_index=round_index,
            summary=memory_summary,
        )
        memory_text = get_memory_for_prompt(memory_path)
        console.print(f"[blue]Updated memory:[/blue] {memory_path}")

        if repetitive_judge:
            stop_reason = "judge output became repetitive"
            console.print("[magenta]Stopping: repetitive judge output.[/magenta]")
            break

        if non_improve_streak >= stop_if_no_improvement_rounds:
            stop_reason = (
                f"score did not improve for {stop_if_no_improvement_rounds} rounds"
            )
            console.print(
                "[magenta]Stopping: score did not improve enough.[/magenta]"
            )
            break

        previous_judge = judge_output
    else:
        stop_reason = "max_rounds reached"

    best_output_path = project_dir / "best_output.md"
    best_round_text = "N/A" if best_round is None else str(best_round)
    best_score_text = "N/A" if best_score < 0 else f"{best_score:.2f}"
    best_output_path_text = str(best_output_path) if best_output_path.exists() else "N/A"

    console.rule("Run Summary")
    console.print(f"[bold]Completed rounds:[/bold] {completed_rounds}")
    console.print(f"[bold]Best round:[/bold] {best_round_text}")
    console.print(f"[bold]Best score:[/bold] {best_score_text}")
    console.print(f"[bold]Stop reason:[/bold] {stop_reason}")
    console.print(f"[bold]Best output path:[/bold] {best_output_path_text}")
    console.print(f"[bold]Score history path:[/bold] {score_history_path}")

    if best_output:
        console.print(f"[bold cyan]Best score:[/bold cyan] {best_score:.2f}")
    else:
        console.print(
            "[red]No valid score found from judge output. best_output.md was not updated.[/red]"
        )


if __name__ == "__main__":
    main()
