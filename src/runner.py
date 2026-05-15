"""Iterative round runner for the local research pipeline."""

from __future__ import annotations

import re
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from rich.console import Console

from .agents import ResearchAgents
from .constants import (
    STOP_EXCEPTION,
    STOP_INVALID_SCORE,
    STOP_MANUAL_INTERRUPT,
    STOP_MAX_ROUNDS,
    STOP_NO_IMPROVEMENT,
    STOP_OLLAMA_TIMEOUT,
    STOP_USER_REQUESTED,
)
from .runtime import log_run as _log
from .runtime import stop_requested as _stop_requested
from .storage import (
    append_log_line,
    get_memory_for_prompt,
    make_round_dir,
    make_run_root,
    parse_score,
    read_text,
    save_round_outputs,
    summarize_round_memory,
    update_project_memory,
    update_research_state,
    write_interrupted_report,
    write_json_file,
    write_score_history,
    write_text,
)


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
    log_path: Optional[Path] = None,
    mode: str = "normal",
) -> Tuple[str, Optional[str]]:
    depth = int(getattr(_run_agent_step, "_depth", 0))
    if depth > 0:
        raise RuntimeError("Recursive agent step detected; aborting for safety.")
    _run_agent_step._depth = depth + 1  # type: ignore[attr-defined]
    console.print(f"[Round {round_index}] Running {agent_name} agent...")
    if log_path is not None:
        append_log_line(log_path, f"mode={mode} | round={round_index} | agent={agent_name} | status=start")
    try:
        output = call()
        console.print(f"[Round {round_index}] {agent_name.capitalize()} finished.")
        if log_path is not None:
            append_log_line(
                log_path,
                f"mode={mode} | round={round_index} | agent={agent_name} | status=end",
            )
        return output, None
    except RuntimeError as exc:
        console.print(f"[red][Round {round_index}] {agent_name} failed: {exc}[/red]")
        if log_path is not None:
            append_log_line(
                log_path,
                f"mode={mode} | round={round_index} | agent={agent_name} | status=error | error={exc}",
            )
        return f"[{agent_name.upper()} ERROR] {exc}", str(exc)
    finally:
        _run_agent_step._depth = depth  # type: ignore[attr-defined]


def run_iterative_rounds(
    *,
    console: Console,
    agents: ResearchAgents,
    task_text: str,
    project_dir: Path,
    memory_path: Path,
    mode: str,
    model_name: str,
    max_rounds: int,
    stop_if_no_improvement_rounds: int,
    global_max_runtime_seconds: int,
    per_agent_timeout_seconds: int,
    disable_no_improvement_stop: bool = False,
    disable_timeout_stop: bool = False,
    start_round: int = 1,
    run_root_override: Optional[Path] = None,
    initial_best_score: float = -1.0,
) -> Dict[str, Any]:
    # Termination guarantee:
    # 1) The only round loop is a bounded for-loop over [1..max_rounds].
    # 2) There is no recursive agent call path.
    # 3) No retry loop exists for failed LLM requests.
    # 4) Additional early-stop conditions (timeout/no-improvement/errors) can only reduce runtime.
    started_at = time.monotonic()
    run_root = run_root_override or make_run_root(project_dir)
    log_path = project_dir / "run.log"
    checkpoint_path = project_dir / "checkpoint.json"
    stop_signal_path = project_dir / "STOP_REQUESTED"
    best_output_path = project_dir / "best_output.md"
    interrupted_report_path = project_dir / "interrupted_report.md"
    run_id = run_root.name
    _log(
        console,
        log_path,
        mode,
        f"run_start run_id={run_id} run_root={run_root} model={model_name}",
    )
    _log(
        console,
        log_path,
        mode,
        "safety "
        f"max_rounds={max_rounds} no_improve_limit={stop_if_no_improvement_rounds} "
        f"global_runtime_limit={global_max_runtime_seconds}s",
    )

    best_score = initial_best_score
    best_output = read_text(best_output_path)
    best_round: Optional[int] = None
    previous_judge = ""
    judge_history: List[str] = []
    score_history: List[Dict[str, Any]] = []
    score_history_path = project_dir / "score_history.json"
    research_state_path = project_dir / "research_state.json"
    non_improve_streak = 0
    stop_reason = STOP_MAX_ROUNDS
    completed_rounds = 0
    last_review_output = ""
    last_revised_output = ""
    last_judge_output = ""
    last_successful_agent = "none"
    invalid_score_seen = False
    timeout_seen = False

    def _remaining_runtime_seconds() -> int:
        remaining = global_max_runtime_seconds - (time.monotonic() - started_at)
        return max(0, int(remaining))

    def _apply_dynamic_timeout() -> None:
        remaining = _remaining_runtime_seconds()
        agents.llm.timeout_seconds = max(1, min(per_agent_timeout_seconds, remaining))
        console.print(
            f"[debug] Applied per-agent timeout={agents.llm.timeout_seconds}s "
            f"(remaining_global_runtime={remaining}s)"
        )

    # round_index is strictly increasing and cannot be reset.
    for round_index in range(start_round, max_rounds + 1):
        elapsed_before_round = time.monotonic() - started_at
        if elapsed_before_round >= global_max_runtime_seconds:
            stop_reason = STOP_EXCEPTION
            _log(
                console,
                log_path,
                mode,
                "global_runtime_limit_reached_before_round",
            )
            break

        _log(console, log_path, mode, f"round_enter round={round_index}")
        console.rule(f"Round {round_index}")
        round_dir = make_round_dir(run_root, round_index)
        draft_output = ""
        review_output = ""
        revised_output = ""
        judge_output = ""

        def _persist_round_outputs(stage: str) -> None:
            save_round_outputs(
                round_dir,
                draft=draft_output,
                review=review_output,
                revised=revised_output,
                judge=judge_output,
            )
            _log(console, log_path, mode, f"round_partial_saved round={round_index} stage={stage}")

        memory_text = get_memory_for_prompt(memory_path)
        memory_words = len(memory_text.split())
        _log(
            console,
            log_path,
            mode,
            f"memory_loaded round={round_index} words={memory_words} limit=1500",
        )
        if memory_words > 1500:
            memory_text = " ".join(memory_text.split()[-1500:])
            _log(console, log_path, mode, f"memory_truncated round={round_index}")

        if _stop_requested(stop_signal_path):
            stop_reason = STOP_USER_REQUESTED
            _log(console, log_path, mode, f"user_stop_requested_before_round round={round_index}")
            break

        try:
            if time.monotonic() - started_at >= global_max_runtime_seconds:
                draft_output = "[DRAFT SKIPPED] global runtime limit reached."
                draft_error = "global runtime limit reached"
                review_output = "[REVIEW SKIPPED] global runtime limit reached."
                review_error = "global runtime limit reached"
                revised_output = "[REVISE SKIPPED] global runtime limit reached."
                revise_error = "global runtime limit reached"
                judge_output = "SCORE: 0\n- Global runtime limit reached before agent call."
                judge_error = "global runtime limit reached"
                _log(console, log_path, mode, f"global_runtime_skip_all_agents round={round_index}")
            else:
                if _stop_requested(stop_signal_path):
                    draft_output = "[DRAFT SKIPPED] user stop requested."
                    draft_error = "user stop requested"
                    _log(console, log_path, mode, f"user_stop_requested_before_draft round={round_index}")
                else:
                    _apply_dynamic_timeout()
                    draft_output, draft_error = _run_agent_step(
                        console=console,
                        round_index=round_index,
                        agent_name="draft",
                        log_path=log_path,
                        mode=mode,
                        call=lambda: agents.draft(
                            task=task_text,
                            memory=memory_text,
                            round_index=round_index,
                            previous_best=best_output,
                            previous_judge=previous_judge,
                        ),
                    )
            if not draft_error and _stop_requested(stop_signal_path):
                draft_error = "user stop requested after draft"
                _log(console, log_path, mode, f"user_stop_requested_after_draft round={round_index}")
            _persist_round_outputs("draft")
            if not draft_error:
                last_successful_agent = "draft"
            if draft_error:
                review_output = "[REVIEW SKIPPED] draft agent failed."
                review_error = "skipped due to draft failure"
                console.print(
                    f"[yellow][Round {round_index}] Skipping review agent due to draft failure.[/yellow]"
                )
            else:
                if _stop_requested(stop_signal_path):
                    review_output = "[REVIEW SKIPPED] user stop requested."
                    review_error = "user stop requested"
                    _log(console, log_path, mode, f"user_stop_requested_before_review round={round_index}")
                elif time.monotonic() - started_at >= global_max_runtime_seconds:
                    review_output = "[REVIEW SKIPPED] global runtime limit reached."
                    review_error = "global runtime limit reached"
                    console.print(
                        f"[yellow][Round {round_index}] Skipping review agent due to global runtime limit.[/yellow]"
                    )
                else:
                    _apply_dynamic_timeout()
                    review_output, review_error = _run_agent_step(
                        console=console,
                        round_index=round_index,
                        agent_name="review",
                        log_path=log_path,
                        mode=mode,
                        call=lambda: agents.review(
                            task=task_text,
                            memory=memory_text,
                            draft_output=draft_output,
                        ),
                    )
                if not review_error and _stop_requested(stop_signal_path):
                    review_error = "user stop requested after review"
                    _log(console, log_path, mode, f"user_stop_requested_after_review round={round_index}")
                _persist_round_outputs("review")
                if not review_error:
                    last_successful_agent = "review"

            if draft_error or review_error:
                revised_output = "[REVISE SKIPPED] draft/review agent failed."
                revise_error = "skipped due to upstream failure"
                console.print(
                    f"[yellow][Round {round_index}] Skipping revise agent due to upstream failure.[/yellow]"
                )
            else:
                if _stop_requested(stop_signal_path):
                    revised_output = "[REVISE SKIPPED] user stop requested."
                    revise_error = "user stop requested"
                    _log(console, log_path, mode, f"user_stop_requested_before_revise round={round_index}")
                elif time.monotonic() - started_at >= global_max_runtime_seconds:
                    revised_output = "[REVISE SKIPPED] global runtime limit reached."
                    revise_error = "global runtime limit reached"
                    console.print(
                        f"[yellow][Round {round_index}] Skipping revise agent due to global runtime limit.[/yellow]"
                    )
                else:
                    _apply_dynamic_timeout()
                    revised_output, revise_error = _run_agent_step(
                        console=console,
                        round_index=round_index,
                        agent_name="revise",
                        log_path=log_path,
                        mode=mode,
                        call=lambda: agents.revise(
                            task=task_text,
                            memory=memory_text,
                            draft_output=draft_output,
                            review_output=review_output,
                        ),
                    )
                if not revise_error and _stop_requested(stop_signal_path):
                    revise_error = "user stop requested after revise"
                    _log(console, log_path, mode, f"user_stop_requested_after_revise round={round_index}")
                _persist_round_outputs("revise")
                if not revise_error:
                    last_successful_agent = "revise"

            if revise_error:
                judge_output = "SCORE: 0\n- Judge skipped because revise step failed."
                judge_error = "skipped due to revise failure"
                console.print(
                    f"[yellow][Round {round_index}] Skipping judge agent due to revise failure (score=0).[/yellow]"
                )
            else:
                if _stop_requested(stop_signal_path):
                    judge_output = "SCORE: 0\n- Judge skipped because user stop was requested."
                    judge_error = "user stop requested"
                    _log(console, log_path, mode, f"user_stop_requested_before_judge round={round_index}")
                elif time.monotonic() - started_at >= global_max_runtime_seconds:
                    judge_output = "SCORE: 0\n- Global runtime limit reached before judge call."
                    judge_error = "global runtime limit reached"
                    console.print(
                        f"[yellow][Round {round_index}] Skipping judge agent due to global runtime limit (score=0).[/yellow]"
                    )
                else:
                    _apply_dynamic_timeout()
                    judge_output, judge_error = _run_agent_step(
                        console=console,
                        round_index=round_index,
                        agent_name="judge",
                        log_path=log_path,
                        mode=mode,
                        call=lambda: agents.judge(
                            task=task_text,
                            memory=memory_text,
                            revised_output=revised_output,
                        ),
                    )
                if not judge_error:
                    last_successful_agent = "judge"
            _persist_round_outputs("judge")
        except KeyboardInterrupt:
            stop_reason = STOP_MANUAL_INTERRUPT
            _log(console, log_path, mode, "manual_interrupt_caught")
            break
        except Exception as exc:  # noqa: BLE001
            stop_reason = STOP_EXCEPTION
            _log(console, log_path, mode, f"exception round={round_index} error={exc}")
            break

        round_errors = [err for err in [draft_error, review_error, revise_error, judge_error] if err]
        if round_errors:
            console.print(
                f"[yellow][Round {round_index}] Agent errors detected: {len(round_errors)}[/yellow]"
            )
        timeout_this_round = any("timed out" in (err or "").lower() for err in round_errors)
        if timeout_this_round:
            timeout_seen = True

        save_round_outputs(
            round_dir,
            draft=draft_output,
            review=review_output,
            revised=revised_output,
            judge=judge_output,
        )
        _log(console, log_path, mode, f"round_saved round={round_index} path={round_dir}")
        last_review_output = review_output
        last_revised_output = revised_output
        last_judge_output = judge_output

        parsed_score = parse_score(judge_output)
        if parsed_score is None:
            score = 0.0
            invalid_score_seen = True
            _log(console, log_path, mode, f"score_parse_failed round={round_index} fallback=0")
        else:
            score = parsed_score
        _log(
            console,
            log_path,
            mode,
            f"score_extracted round={round_index} parsed={parsed_score is not None} value={score:.2f}",
        )
        completed_rounds = round_index

        improved = score > best_score
        if improved:
            best_score = score
            best_round = round_index
            best_output = revised_output
            write_text(best_output_path, best_output)
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
                "errors": round_errors,
                "timeout_this_round": timeout_this_round,
                "invalid_score_this_round": parsed_score is None,
                "model": model_name,
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
        update_research_state(
            state_path=research_state_path,
            round_index=round_index,
            best_score=best_score,
            revised_output=revised_output,
            review_output=review_output,
            judge_output=judge_output,
        )
        _log(console, log_path, mode, f"memory_updated round={round_index}")
        _log(console, log_path, mode, f"research_state_updated round={round_index}")

        checkpoint_data = {
            "run_id": run_id,
            "run_root": str(run_root),
            "last_completed_round": round_index,
            "last_successful_agent": last_successful_agent,
            "best_score": round(best_score, 2),
            "best_round_path": str(run_root / f"round_{best_round:02d}") if best_round else "",
            "stop_reason": "",
            "can_resume": True,
            "updated_at": datetime.now().isoformat(),
            "mode": mode,
            "model": model_name,
        }
        write_json_file(checkpoint_path, checkpoint_data)

        elapsed_after_round = time.monotonic() - started_at
        _log(
            console,
            log_path,
            mode,
            f"stop_check round={round_index} timeout={timeout_this_round} "
            f"repetitive={repetitive_judge} non_improve_streak={non_improve_streak} "
            f"invalid_score={parsed_score is None} elapsed={elapsed_after_round:.2f}s",
        )

        # Stop conditions:
        # - OLLAMA_TIMEOUT: any agent timeout in current round.
        # - NO_IMPROVEMENT: score does not improve for configured rounds.
        # - EXCEPTION: global runtime reached or unhandled exception.
        # - MAX_ROUNDS: for-loop exhausts naturally.
        if timeout_this_round and not disable_timeout_stop:
            stop_reason = STOP_OLLAMA_TIMEOUT
            _log(console, log_path, mode, f"stop_reason={STOP_OLLAMA_TIMEOUT} round={round_index}")
            break

        if not disable_no_improvement_stop and non_improve_streak >= stop_if_no_improvement_rounds:
            stop_reason = STOP_NO_IMPROVEMENT
            _log(console, log_path, mode, f"stop_reason={STOP_NO_IMPROVEMENT} round={round_index}")
            break

        if elapsed_after_round >= global_max_runtime_seconds:
            stop_reason = STOP_EXCEPTION
            _log(console, log_path, mode, f"stop_reason={STOP_EXCEPTION} round={round_index}")
            break

        if _stop_requested(stop_signal_path):
            stop_reason = STOP_USER_REQUESTED
            _log(console, log_path, mode, f"stop_reason={STOP_USER_REQUESTED} round={round_index}")
            break

        previous_judge = judge_output
        _log(console, log_path, mode, f"round_exit round={round_index}")
    else:
        stop_reason = STOP_MAX_ROUNDS

    if stop_reason == STOP_MAX_ROUNDS and invalid_score_seen and completed_rounds == 1:
        stop_reason = STOP_INVALID_SCORE

    best_round_text = "N/A" if best_round is None else str(best_round)
    best_score_text = "N/A" if best_score < 0 else f"{best_score:.2f}"
    best_output_path_text = str(best_output_path) if best_output_path.exists() else "N/A"
    total_runtime = time.monotonic() - started_at

    console.rule("Run Summary")
    console.print(f"[bold]Completed rounds:[/bold] {completed_rounds}")
    console.print(f"[bold]Best round:[/bold] {best_round_text}")
    console.print(f"[bold]Best score:[/bold] {best_score_text}")
    console.print(f"[bold]Stop reason:[/bold] {stop_reason}")
    console.print(f"[bold]Total runtime:[/bold] {total_runtime:.2f}s")
    console.print(f"[bold]Last successful agent:[/bold] {last_successful_agent}")
    console.print(f"[bold]Best output path:[/bold] {best_output_path_text}")
    console.print(f"[bold]Score history path:[/bold] {score_history_path}")
    _log(
        console,
        log_path,
        mode,
        f"run_summary completed_rounds={completed_rounds} stop_reason={stop_reason} "
        f"best_score={best_score_text} last_successful_agent={last_successful_agent}",
    )

    checkpoint_final = {
        "run_id": run_id,
        "run_root": str(run_root),
        "last_completed_round": completed_rounds,
        "last_successful_agent": last_successful_agent,
        "best_score": round(best_score, 2),
        "best_round_path": str(run_root / f"round_{best_round:02d}") if best_round else "",
        "stop_reason": stop_reason,
        "can_resume": stop_reason in {STOP_USER_REQUESTED, STOP_MANUAL_INTERRUPT},
        "updated_at": datetime.now().isoformat(),
        "mode": mode,
        "model": model_name,
    }
    write_json_file(checkpoint_path, checkpoint_final)

    if stop_reason in {STOP_USER_REQUESTED, STOP_MANUAL_INTERRUPT}:
        write_interrupted_report(
            report_path=interrupted_report_path,
            last_completed_round=completed_rounds,
            last_successful_agent=last_successful_agent,
            best_score=max(0.0, best_score),
            best_output_path=best_output_path,
            resume_command=".venv/bin/python -m src.main --resume",
            stop_time=datetime.now().isoformat(),
        )
        if stop_signal_path.exists():
            stop_signal_path.unlink()

    if best_output:
        console.print(f"[bold cyan]Best score:[/bold cyan] {best_score:.2f}")
    else:
        console.print(
            "[red]No valid score found from judge output. best_output.md was not updated.[/red]"
        )

    return {
        "run_root": run_root,
        "best_round": best_round,
        "best_score": best_score,
        "best_output": best_output,
        "stop_reason": stop_reason,
        "completed_rounds": completed_rounds,
        "score_history_path": score_history_path,
        "best_output_path": best_output_path,
        "last_review_output": last_review_output,
        "last_revised_output": last_revised_output,
        "last_judge_output": last_judge_output,
        "total_runtime_seconds": total_runtime,
        "last_successful_agent": last_successful_agent,
        "timeout_seen": timeout_seen,
        "invalid_score_seen": invalid_score_seen,
    }
