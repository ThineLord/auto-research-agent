"""Entry point for the local iterative research pipeline."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml
from rich.console import Console

from .agents import ResearchAgents
from .llm import OllamaClient
from .session import (
    generate_current_plan,
    generate_final_session_report,
    generate_focus_objective,
)
from .storage import (
    get_memory_for_prompt,
    make_round_dir,
    make_run_root,
    parse_score,
    read_json_file,
    read_text,
    save_round_outputs,
    summarize_round_memory,
    update_research_state,
    update_project_memory,
    write_interrupted_report,
    write_json_file,
    append_log_line,
    write_score_history,
    write_text,
)

STOP_MAX_ROUNDS = "MAX_ROUNDS"
STOP_NO_IMPROVEMENT = "NO_IMPROVEMENT"
STOP_OLLAMA_TIMEOUT = "OLLAMA_TIMEOUT"
STOP_INVALID_SCORE = "INVALID_SCORE"
STOP_EXCEPTION = "EXCEPTION"
STOP_MANUAL_INTERRUPT = "MANUAL_INTERRUPT"
STOP_USER_REQUESTED = "USER_STOP_REQUESTED"
GLOBAL_MAX_RUNTIME_SECONDS = 600


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def list_installed_ollama_models() -> Tuple[List[str], Optional[str]]:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except FileNotFoundError:
        return [], "Ollama is not installed or not in PATH."
    except subprocess.SubprocessError as exc:
        return [], f"Failed to query Ollama: {exc}"

    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip() or "Unknown error from ollama list."
        return [], f"Ollama is not available: {err}"

    models: List[str] = []
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        cols = re.split(r"\s{2,}", line)
        name = cols[0].strip() if cols else ""
        if name:
            models.append(name)
    return models, None


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


def _shorten_text_by_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def _log(console: Console, log_path: Path, mode: str, message: str) -> None:
    line = f"mode={mode} | {message}"
    console.print(line)
    append_log_line(log_path, line)


def _stop_requested(stop_signal_path: Path) -> bool:
    return stop_signal_path.exists()


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
        f"global_runtime_limit={GLOBAL_MAX_RUNTIME_SECONDS}s",
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
        remaining = GLOBAL_MAX_RUNTIME_SECONDS - (time.monotonic() - started_at)
        return max(0, int(remaining))

    def _apply_dynamic_timeout() -> None:
        remaining = _remaining_runtime_seconds()
        agents.llm.timeout_seconds = max(1, min(120, remaining))
        console.print(
            f"[debug] Applied per-agent timeout={agents.llm.timeout_seconds}s "
            f"(remaining_global_runtime={remaining}s)"
        )

    # round_index is strictly increasing and cannot be reset.
    for round_index in range(start_round, max_rounds + 1):
        elapsed_before_round = time.monotonic() - started_at
        if elapsed_before_round >= GLOBAL_MAX_RUNTIME_SECONDS:
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
            if time.monotonic() - started_at >= GLOBAL_MAX_RUNTIME_SECONDS:
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
                elif time.monotonic() - started_at >= GLOBAL_MAX_RUNTIME_SECONDS:
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
                elif time.monotonic() - started_at >= GLOBAL_MAX_RUNTIME_SECONDS:
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
                elif time.monotonic() - started_at >= GLOBAL_MAX_RUNTIME_SECONDS:
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
        if timeout_this_round:
            stop_reason = STOP_OLLAMA_TIMEOUT
            _log(console, log_path, mode, f"stop_reason={STOP_OLLAMA_TIMEOUT} round={round_index}")
            break

        if non_improve_streak >= stop_if_no_improvement_rounds:
            stop_reason = STOP_NO_IMPROVEMENT
            _log(console, log_path, mode, f"stop_reason={STOP_NO_IMPROVEMENT} round={round_index}")
            break

        if elapsed_after_round >= GLOBAL_MAX_RUNTIME_SECONDS:
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
            resume_command="python -m src.main --resume",
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


def run_diagnostic_mode(
    *,
    console: Console,
    llm: OllamaClient,
    task_text: str,
    project_dir: Path,
    memory_path: Path,
    model_name: str,
) -> None:
    log_path = project_dir / "run.log"
    console.rule("Diagnostic Mode")
    console.print(
        "[cyan]Diagnostic constraints:[/cyan] one round only, short prompts, "
        "no memory update, no retries"
    )
    _log(console, log_path, "diagnostic", f"run_start model={model_name}")

    # Keep diagnostic mode fast: tighten timeout for each LLM call.
    llm.timeout_seconds = min(llm.timeout_seconds, 20)

    diagnostic_agents = ResearchAgents(
        llm=llm,
        draft_prompt=(
            "Produce a compact technical draft. "
            "Max 6 bullets. Focus only on one concrete subproblem."
        ),
        review_prompt=(
            "Critique only the most critical issues. "
            "Max 5 bullets with actionable fixes."
        ),
        revise_prompt=(
            "Revise the draft using review feedback. "
            "Return concise implementation-oriented output."
        ),
        judge_prompt=(
            "Score the revised output quickly. "
            "Output format: SCORE: <0-100> then 3 bullets."
        ),
        temperature=0.2,
        top_p=0.8,
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
            "last_successful_agent": "judge" if not judge_error else ("revise" if not revise_error else "review" if not review_error else "draft" if not draft_error else "none"),
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


def run_session_mode(
    *,
    console: Console,
    llm: OllamaClient,
    agents: ResearchAgents,
    task_text: str,
    project_dir: Path,
    memory_path: Path,
    model_name: str,
    max_rounds: int,
    stop_if_no_improvement_rounds: int,
) -> None:
    console.rule("Research Session Mode")
    memory_for_prompt = get_memory_for_prompt(memory_path)

    objective = generate_focus_objective(
        llm=llm,
        task_text=task_text,
        memory_text=memory_for_prompt,
        console=console,
    )
    console.print(f"[bold cyan]Session focus objective:[/bold cyan] {objective}")

    current_plan_path = project_dir / "current_plan.md"
    plan_text = generate_current_plan(
        llm=llm,
        objective=objective,
        task_text=task_text,
        memory_text=memory_for_prompt,
        output_path=current_plan_path,
        console=console,
    )
    console.print(f"[green]Saved current plan:[/green] {current_plan_path}")

    session_task = (
        f"{task_text}\n\n"
        "## Session Focus Mode\n"
        f"Focus objective: {objective}\n"
        "Important: stay on this single narrow subproblem for this session.\n\n"
        "## Session Plan\n"
        f"{plan_text}\n"
    )

    result = run_iterative_rounds(
        console=console,
        agents=agents,
        task_text=session_task,
        project_dir=project_dir,
        memory_path=memory_path,
        mode="session",
        model_name=model_name,
        max_rounds=max_rounds,
        stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
    )

    research_state_path = project_dir / "research_state.json"
    research_state: Dict[str, Any] = {}
    if research_state_path.exists():
        try:
            research_state = json.loads(research_state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            research_state = {}

    final_report_path = project_dir / "final_session_report.md"
    report_text = generate_final_session_report(
        llm=llm,
        objective=objective,
        plan_text=plan_text,
        best_output=result["best_output"] or result["last_revised_output"],
        research_state=research_state,
        memory_text=get_memory_for_prompt(memory_path),
        output_path=final_report_path,
        console=console,
    )
    console.print(f"[green]Saved final session report:[/green] {final_report_path}")

    if not report_text.strip():
        write_text(
            final_report_path,
            "# Final Session Report\n\nNo content generated. Please rerun the session.",
        )


def parse_args() -> argparse.Namespace:
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    console = Console()
    root = Path(__file__).resolve().parent.parent
    config = load_config(root / "config.yaml")

    model_cfg = config.get("model", {})
    if isinstance(model_cfg, dict):
        config_model_name = str(model_cfg.get("name", "qwen3:8b"))
        config_temperature = float(model_cfg.get("temperature", config.get("temperature", 0.4)))
        config_timeout = int(model_cfg.get("timeout_seconds", config.get("timeout_seconds", 120)))
    else:
        config_model_name = str(model_cfg) if model_cfg else "qwen3:8b"
        config_temperature = float(config.get("temperature", 0.4))
        config_timeout = int(config.get("timeout_seconds", 120))

    model_name = args.model or config_model_name
    base_url = config.get("ollama_base_url", "http://localhost:11434")
    project_name = config.get("project_name", "pama")
    max_rounds = int(config.get("max_rounds", 5))
    stop_if_no_improvement_rounds = int(config.get("stop_if_no_improvement_rounds", 2))
    temperature = float(config_temperature)
    top_p = float(config.get("top_p", 0.9))
    timeout_seconds = min(int(config_timeout), 120)

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
            checkpoint_path = project_dir / "checkpoint.json"
            checkpoint = read_json_file(checkpoint_path)
            if not checkpoint or not checkpoint.get("can_resume"):
                console.print(
                    "[red]Cannot resume: checkpoint.json missing or can_resume is false.[/red]"
                )
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
                start_round=start_round,
                run_root_override=run_root_path,
                initial_best_score=initial_best_score,
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
        )
    except KeyboardInterrupt:
        console.print("[red]Manual interrupt detected in main loop. Stop reason: MANUAL_INTERRUPT[/red]")


if __name__ == "__main__":
    main()
