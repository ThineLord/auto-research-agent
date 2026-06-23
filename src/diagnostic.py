"""Lightweight one-round diagnostic workflow."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from rich.console import Console

from .agents import ResearchAgents
from .cloud_free import CloudFreeDailyQuotaExhausted, next_pacific_reset_heuristic
from .config import DEFAULT_DRAFTING_MODE
from .constants import STOP_CLOUD_DAILY_QUOTA
from .judge_output import parse_judge_rubric
from .llm import LLMClientProtocol
from .run_config import build_initial_run_config, finalize_run_config
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
    project_metadata: Dict[str, object] | None = None,
    model_provider: str = "",
    model_parameters: Dict[str, object] | None = None,
    topic_snapshot: Dict[str, object] | None = None,
    prompt_dir: Path | None = None,
    repo_root: Path | None = None,
    drafting_mode: str = DEFAULT_DRAFTING_MODE,
) -> None:
    run_started = time.monotonic()
    started_at_iso = datetime.now().astimezone().isoformat()
    log_path = project_dir / "run.log"
    console.rule("Diagnostic Mode")
    console.print(
        "[cyan]Diagnostic constraints:[/cyan] one round only, short prompts, "
        "no memory update, no retries"
    )
    _log(console, log_path, "diagnostic", f"run_start model={model_name}")
    if project_metadata:
        _log(
            console,
            log_path,
            "diagnostic",
            "project_source "
            f"kind={project_metadata.get('source_kind', 'unknown')} "
            f"name={project_metadata.get('project_name', '')} "
            f"title={project_metadata.get('project_title', '')} "
            f"project_dir={project_metadata.get('project_dir', '')} "
            f"task_path={project_metadata.get('task_path', '')}",
        )

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
    run_config_path = run_root / "run_config.json"
    run_config = build_initial_run_config(
        run_id=run_root.name,
        run_root=run_root,
        mode="diagnostic",
        model_name=model_name,
        model_provider=model_provider,
        model_parameters=model_parameters,
        runtime_config={
            "max_rounds": 1,
            "start_round": 1,
            "per_agent_timeout_seconds": llm.timeout_seconds,
            "drafting_mode": drafting_mode,
        },
        topic_snapshot=topic_snapshot,
        project_metadata=project_metadata,
        prompt_dir=prompt_dir,
        repo_root=repo_root,
        started_at=started_at_iso,
    )
    write_json_file(run_config_path, run_config)
    write_json_file(
        run_root / "run_manifest.json",
        {
            "run_id": run_root.name,
            "run_root": str(run_root),
            "mode": "diagnostic",
            "model": model_name,
            "drafting_mode": drafting_mode,
            "started_at": started_at_iso,
            "project": project_metadata or {},
            "run_config": str(run_config_path),
        },
    )
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
        except CloudFreeDailyQuotaExhausted:
            raise
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

    try:
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
    except CloudFreeDailyQuotaExhausted as exc:
        message = str(exc)
        console.print(f"[yellow]{message}[/yellow]")
        write_json_file(
            project_dir / "checkpoint.json",
            {
                "run_id": run_root.name,
                "run_root": str(run_root),
                "run_config": str(run_config_path),
                "run_summary": str(run_root / "run_summary.json"),
                "last_completed_round": 0,
                "last_successful_agent": "none",
                "best_score": 0.0,
                "best_round_path": "",
                "stop_reason": STOP_CLOUD_DAILY_QUOTA,
                "can_resume": True,
                "updated_at": datetime.now().isoformat(),
                "mode": "diagnostic",
                "model": model_name,
                "drafting_mode": drafting_mode,
                "project": project_metadata or {},
                "status": "paused_until_reset",
                "paused_until_reset": True,
                "pause_message": message,
                "reset_heuristic": next_pacific_reset_heuristic(),
            },
        )
        run_config = finalize_run_config(
            run_config,
            stop_reason=STOP_CLOUD_DAILY_QUOTA,
            can_resume=True,
            completed_rounds=0,
            best_score=0.0,
            best_round=None,
            total_runtime_seconds=time.monotonic() - run_started,
        )
        write_json_file(run_config_path, run_config)
        write_json_file(
            run_root / "run_summary.json",
            {
                "run_id": run_root.name,
                "run_root": str(run_root),
                "mode": "diagnostic",
                "model": model_name,
                "drafting_mode": drafting_mode,
                "completed_rounds": 0,
                "best_round": None,
                "best_score": 0.0,
                "stop_reason": STOP_CLOUD_DAILY_QUOTA,
                "can_resume": True,
                "total_runtime_seconds": round(time.monotonic() - run_started, 3),
                "round_count": 0,
                "successful_rounds": [],
                "timeout_rounds": [],
                "error_rounds": [],
                "provider_failure_rounds": [],
                "invalid_score_rounds": [],
            },
        )
        return

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
    round_metrics_path = run_root / "round_metrics.json"
    errors = [e for e in [draft_error, review_error, revise_error, judge_error] if e]
    timeout_this_round = any(
        "timed out" in (e or "").lower()
        for e in [draft_error, review_error, revise_error, judge_error]
        if e
    )
    round_metric = {
        "round": 1,
        "score": parsed_score,
        "improved": True,
        "non_improve_streak": 0,
        "repetitive_judge": False,
        "errors": errors,
        "agent_errors": {
            "draft": draft_error,
            "review": review_error,
            "revise": revise_error,
            "judge": judge_error,
        },
        "agent_timings_seconds": {agent: round(elapsed, 3) for agent, elapsed in timings.items()},
        "round_runtime_seconds": round(sum(timings.values()), 3),
        "timeout_this_round": timeout_this_round,
        "invalid_score_this_round": parse_score(judge_output) is None,
        "successful_research_round": not errors and parse_score(judge_output) is not None,
        "judge_rubric": parse_judge_rubric(judge_output),
        "model": model_name,
        "drafting_mode": drafting_mode,
    }
    write_score_history(
        score_history_path,
        [round_metric],
    )
    write_score_history(round_metrics_path, [round_metric])
    write_json_file(
        project_dir / "checkpoint.json",
        {
            "run_id": run_root.name,
            "run_root": str(run_root),
            "run_config": str(run_config_path),
            "run_summary": str(run_root / "run_summary.json"),
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
            "drafting_mode": drafting_mode,
            "project": project_metadata or {},
        },
    )
    run_config = finalize_run_config(
        run_config,
        stop_reason="MAX_ROUNDS",
        can_resume=False,
        completed_rounds=1,
        best_score=parsed_score,
        best_round=1,
        total_runtime_seconds=time.monotonic() - run_started,
    )
    write_json_file(run_config_path, run_config)
    write_json_file(
        run_root / "run_summary.json",
        {
            "run_id": run_root.name,
            "run_root": str(run_root),
            "mode": "diagnostic",
            "model": model_name,
            "drafting_mode": drafting_mode,
            "completed_rounds": 1,
            "best_round": 1,
            "best_score": round(parsed_score, 2),
            "stop_reason": "MAX_ROUNDS",
            "can_resume": False,
            "total_runtime_seconds": round(time.monotonic() - run_started, 3),
            "score_history_path": str(score_history_path),
            "round_metrics_path": str(round_metrics_path),
            "run_config_path": str(run_config_path),
            "successful_rounds": [1] if round_metric["successful_research_round"] else [],
            "timeout_rounds": [1] if timeout_this_round else [],
            "error_rounds": [1] if errors else [],
            "provider_failure_rounds": [],
            "invalid_score_rounds": [1] if round_metric["invalid_score_this_round"] else [],
            "round_count": 1,
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
