"""Lightweight one-round diagnostic workflow."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from rich.console import Console

from .agents import ResearchAgents
from .llm import LLMClientProtocol
from .runtime import log_run as _log
from .runtime import shorten_text_by_words as _shorten_text_by_words
from .storage import (
    append_log_line,
    get_memory_for_prompt,
    make_round_dir,
    make_run_root,
    parse_score,
    save_round_outputs,
    write_json_file,
    write_score_history,
)


def run_diagnostic_mode(
    *,
    console: Console,
    llm: LLMClientProtocol,
    task_text: str,
    project_dir: Path,
    memory_path: Path,
    model_name: str,
    topic_context: str = "",
) -> None:
    log_path = project_dir / "run.log"
    console.rule("Diagnostic Mode")
    console.print(
        "[cyan]Diagnostic constraints:[/cyan] one round only, short prompts, "
        "no memory update, no retries"
    )
    _log(console, log_path, "diagnostic", f"run_start model={model_name}")

    # Allow slower local machines/model warm-up while keeping a sane upper bound.
    llm.timeout_seconds = min(llm.timeout_seconds, 300)

    diagnostic_agents = ResearchAgents(
        llm=llm,
        draft_prompt=(
            "Produce a compact technical draft. "
            "Max 6 bullets. Focus only on one concrete subproblem."
        ),
        review_prompt=(
            "Critique only the most critical issues. Max 5 bullets with actionable fixes."
        ),
        revise_prompt=(
            "Revise the draft using review feedback. Return concise implementation-oriented output."
        ),
        judge_prompt=(
            "Score the revised output quickly. Return JSON only with keys: "
            "score, rubric, reasons, blockers, next_step."
        ),
        temperature=0.2,
        top_p=0.8,
        topic_context=topic_context,
    )

    run_root = make_run_root(project_dir)
    round_index = 1
    round_dir = make_round_dir(run_root, round_index)
    memory_text = get_memory_for_prompt(memory_path)

    diagnostic_task = _shorten_text_by_words(task_text, 180)
    diagnostic_memory = _shorten_text_by_words(memory_text, 120)
    console.print(
        f"[Round 1] Diagnostic input sizes | task_words={len(diagnostic_task.split())} "
        f"memory_words={len(diagnostic_memory.split())}"
    )

    timings: Dict[str, float] = {}

    def run_agent(agent_name: str, fn: Callable[[], str]) -> Tuple[str, Optional[str]]:
        console.print(f"[Round 1] Running {agent_name} agent...")
        append_log_line(
            log_path,
            f"mode=diagnostic | round=1 | agent={agent_name} | status=start",
        )
        started = time.monotonic()
        try:
            output = fn()
            error = None
            console.print(f"[Round 1] {agent_name.capitalize()} finished.")
            append_log_line(
                log_path,
                f"mode=diagnostic | round=1 | agent={agent_name} | status=end",
            )
        except RuntimeError as exc:
            output = f"[{agent_name.upper()} ERROR] {exc}"
            error = str(exc)
            console.print(f"[red][Round 1] {agent_name} failed: {exc}[/red]")
            append_log_line(
                log_path,
                f"mode=diagnostic | round=1 | agent={agent_name} | status=error | error={exc}",
            )
        elapsed = time.monotonic() - started
        timings[agent_name] = elapsed
        console.print(f"[Round 1] {agent_name} timing: {elapsed:.2f}s")
        return output, error

    draft_output, draft_error = run_agent(
        "draft",
        lambda: diagnostic_agents.draft(
            task=diagnostic_task,
            memory=diagnostic_memory,
            round_index=1,
            previous_best="",
            previous_judge="",
        ),
    )
    if draft_error:
        review_output = "[REVIEW SKIPPED] draft failed in diagnostic mode."
        review_error = "skipped due to draft failure"
        console.print("[Round 1] Skipping review because draft failed.")
    else:
        review_output, review_error = run_agent(
            "review",
            lambda: diagnostic_agents.review(
                task=diagnostic_task,
                memory=diagnostic_memory,
                draft_output=draft_output,
            ),
        )

    if draft_error or review_error:
        revised_output = "[REVISE SKIPPED] upstream failure in diagnostic mode."
        revise_error = "skipped due to upstream failure"
        console.print("[Round 1] Skipping revise because upstream failed.")
    else:
        revised_output, revise_error = run_agent(
            "revise",
            lambda: diagnostic_agents.revise(
                task=diagnostic_task,
                memory=diagnostic_memory,
                draft_output=draft_output,
                review_output=review_output,
            ),
        )

    if revise_error:
        judge_output = "SCORE: 0\n- Judge skipped because revise failed."
        judge_error = "skipped due to revise failure"
        console.print("[Round 1] Skipping judge because revise failed.")
    else:
        judge_output, judge_error = run_agent(
            "judge",
            lambda: diagnostic_agents.judge(
                task=diagnostic_task,
                memory=diagnostic_memory,
                revised_output=revised_output,
            ),
        )

    save_round_outputs(
        round_dir,
        draft=draft_output,
        review=review_output,
        revised=revised_output,
        judge=judge_output,
    )
    console.print(f"[green]Saved diagnostic round outputs:[/green] {round_dir}")

    expected_files = [
        round_dir / "01_draft.md",
        round_dir / "02_review.md",
        round_dir / "03_revised.md",
        round_dir / "04_judge.md",
    ]
    missing = [str(path) for path in expected_files if not path.exists()]
    if missing:
        console.print("[red]Diagnostic file check failed. Missing files:[/red]")
        for path in missing:
            console.print(f"- {path}")
    else:
        console.print("[green]Diagnostic file check passed (all round files saved).[/green]")

    parsed_score = parse_score(judge_output)
    if parsed_score is None:
        parsed_score = 0.0

    score_history_path = project_dir / "score_history.json"
    write_score_history(
        score_history_path,
        [
            {
                "round": 1,
                "score": parsed_score,
                "improved": True,
                "non_improve_streak": 0,
                "repetitive_judge": False,
                "errors": [e for e in [draft_error, review_error, revise_error, judge_error] if e],
                "timeout_this_round": any(
                    "timed out" in (e or "").lower()
                    for e in [draft_error, review_error, revise_error, judge_error]
                    if e
                ),
                "invalid_score_this_round": parse_score(judge_output) is None,
                "model": model_name,
            }
        ],
    )
    write_json_file(
        project_dir / "checkpoint.json",
        {
            "run_id": run_root.name,
            "run_root": str(run_root),
            "last_completed_round": 1,
            "last_successful_agent": (
                "judge"
                if not judge_error
                else "revise"
                if not revise_error
                else "review"
                if not review_error
                else "draft"
                if not draft_error
                else "none"
            ),
            "best_score": round(parsed_score, 2),
            "best_round_path": str(round_dir),
            "stop_reason": "MAX_ROUNDS",
            "can_resume": False,
            "updated_at": datetime.now().isoformat(),
            "mode": "diagnostic",
            "model": model_name,
        },
    )
    console.rule("Diagnostic Summary")
    console.print(f"[bold]Run root:[/bold] {run_root}")
    console.print(f"[bold]Round saved:[/bold] {round_dir}")
    console.print(f"[bold]Draft timing:[/bold] {timings.get('draft', 0.0):.2f}s")
    console.print(f"[bold]Review timing:[/bold] {timings.get('review', 0.0):.2f}s")
    console.print(f"[bold]Revise timing:[/bold] {timings.get('revise', 0.0):.2f}s")
    console.print(f"[bold]Judge timing:[/bold] {timings.get('judge', 0.0):.2f}s")
    console.print(f"[bold]Score:[/bold] {parsed_score:.2f}")
    console.print(
        f"[bold]Errors:[/bold] draft={bool(draft_error)} review={bool(review_error)} "
        f"revise={bool(revise_error)} judge={bool(judge_error)}"
    )
    console.print("[bold green]Diagnostic mode complete (terminated after round 1).[/bold green]")
    _log(console, log_path, "diagnostic", "run_end")
