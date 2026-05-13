"""Entry point for the local iterative research pipeline."""

from __future__ import annotations

import argparse
import json
import re
import time
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
    read_text,
    save_round_outputs,
    summarize_round_memory,
    update_research_state,
    update_project_memory,
    write_score_history,
    write_text,
)

STOP_MAX_ROUNDS = "MAX_ROUNDS"
STOP_NO_IMPROVEMENT = "NO_IMPROVEMENT"
STOP_OLLAMA_TIMEOUT = "OLLAMA_TIMEOUT"
STOP_INVALID_SCORE = "INVALID_SCORE"
STOP_EXCEPTION = "EXCEPTION"
STOP_MANUAL_INTERRUPT = "MANUAL_INTERRUPT"
GLOBAL_MAX_RUNTIME_SECONDS = 600


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
    depth = int(getattr(_run_agent_step, "_depth", 0))
    if depth > 0:
        raise RuntimeError("Recursive agent step detected; aborting for safety.")
    _run_agent_step._depth = depth + 1  # type: ignore[attr-defined]
    console.print(f"[Round {round_index}] Running {agent_name} agent...")
    try:
        output = call()
        console.print(f"[Round {round_index}] {agent_name.capitalize()} finished.")
        return output, None
    except RuntimeError as exc:
        console.print(f"[red][Round {round_index}] {agent_name} failed: {exc}[/red]")
        return f"[{agent_name.upper()} ERROR] {exc}", str(exc)
    finally:
        _run_agent_step._depth = depth  # type: ignore[attr-defined]


def _shorten_text_by_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def run_iterative_rounds(
    *,
    console: Console,
    agents: ResearchAgents,
    task_text: str,
    project_dir: Path,
    memory_path: Path,
    max_rounds: int,
    stop_if_no_improvement_rounds: int,
) -> Dict[str, Any]:
    # Termination guarantee:
    # 1) The only round loop is a bounded for-loop over [1..max_rounds].
    # 2) There is no recursive agent call path.
    # 3) No retry loop exists for failed LLM requests.
    # 4) Additional early-stop conditions (timeout/no-improvement/errors) can only reduce runtime.
    started_at = time.monotonic()
    run_root = make_run_root(project_dir)
    console.print(f"[cyan]Run directory:[/cyan] {run_root}")
    console.print(
        f"[cyan]Safety limits:[/cyan] max_rounds={max_rounds}, "
        f"no_improve_limit={stop_if_no_improvement_rounds}, "
        f"global_runtime_limit={GLOBAL_MAX_RUNTIME_SECONDS}s"
    )

    best_score = -1.0
    best_output = ""
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
    for round_index in range(1, max_rounds + 1):
        elapsed_before_round = time.monotonic() - started_at
        if elapsed_before_round >= GLOBAL_MAX_RUNTIME_SECONDS:
            stop_reason = STOP_EXCEPTION
            console.print(
                "[red]Global runtime limit reached before starting next round.[/red]"
            )
            break

        console.print(f"[Round {round_index}] Entering round.")
        console.rule(f"Round {round_index}")
        round_dir = make_round_dir(run_root, round_index)
        memory_text = get_memory_for_prompt(memory_path)
        memory_words = len(memory_text.split())
        console.print(
            f"[Round {round_index}] Memory loaded | words={memory_words} (limit=1500)"
        )
        if memory_words > 1500:
            memory_text = " ".join(memory_text.split()[-1500:])
            console.print(
                f"[yellow][Round {round_index}] Memory exceeded limit, truncated to 1500 words.[/yellow]"
            )

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
            else:
                _apply_dynamic_timeout()
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
            if not draft_error:
                last_successful_agent = "draft"
            if draft_error:
                review_output = "[REVIEW SKIPPED] draft agent failed."
                review_error = "skipped due to draft failure"
                console.print(
                    f"[yellow][Round {round_index}] Skipping review agent due to draft failure.[/yellow]"
                )
            else:
                if time.monotonic() - started_at >= GLOBAL_MAX_RUNTIME_SECONDS:
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
                        call=lambda: agents.review(
                            task=task_text,
                            memory=memory_text,
                            draft_output=draft_output,
                        ),
                    )
                if not review_error:
                    last_successful_agent = "review"

            if draft_error or review_error:
                revised_output = "[REVISE SKIPPED] draft/review agent failed."
                revise_error = "skipped due to upstream failure"
                console.print(
                    f"[yellow][Round {round_index}] Skipping revise agent due to upstream failure.[/yellow]"
                )
            else:
                if time.monotonic() - started_at >= GLOBAL_MAX_RUNTIME_SECONDS:
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
                        call=lambda: agents.revise(
                            task=task_text,
                            memory=memory_text,
                            draft_output=draft_output,
                            review_output=review_output,
                        ),
                    )
                if not revise_error:
                    last_successful_agent = "revise"

            if revise_error:
                judge_output = "SCORE: 0\n- Judge skipped because revise step failed."
                judge_error = "skipped due to revise failure"
                console.print(
                    f"[yellow][Round {round_index}] Skipping judge agent due to revise failure (score=0).[/yellow]"
                )
            else:
                if time.monotonic() - started_at >= GLOBAL_MAX_RUNTIME_SECONDS:
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
                        call=lambda: agents.judge(
                            task=task_text,
                            memory=memory_text,
                            revised_output=revised_output,
                        ),
                    )
                if not judge_error:
                    last_successful_agent = "judge"
        except KeyboardInterrupt:
            stop_reason = STOP_MANUAL_INTERRUPT
            console.print("[red]Manual interrupt received. Stopping gracefully.[/red]")
            break
        except Exception as exc:  # noqa: BLE001
            stop_reason = STOP_EXCEPTION
            console.print(f"[red]Unhandled exception in round {round_index}: {exc}[/red]")
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
        console.print(f"[green]Saved round outputs:[/green] {round_dir}")
        last_review_output = review_output
        last_revised_output = revised_output
        last_judge_output = judge_output

        parsed_score = parse_score(judge_output)
        if parsed_score is None:
            score = 0.0
            invalid_score_seen = True
            console.print(
                "[yellow]Judge score parsing failed; fallback score = 0.00 (INVALID_SCORE)[/yellow]"
            )
        else:
            score = parsed_score
        console.print(
            f"[yellow]Score extraction:[/yellow] parsed={parsed_score is not None}, value={score:.2f}"
        )
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
                "errors": round_errors,
                "timeout_this_round": timeout_this_round,
                "invalid_score_this_round": parsed_score is None,
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
        console.print(f"[blue]Updated memory:[/blue] {memory_path}")
        console.print(f"[blue]Updated research state:[/blue] {research_state_path}")

        elapsed_after_round = time.monotonic() - started_at
        console.print(
            f"[Round {round_index}] Stop-check | timeout={timeout_this_round} "
            f"repetitive={repetitive_judge} non_improve_streak={non_improve_streak} "
            f"invalid_score={parsed_score is None} elapsed={elapsed_after_round:.2f}s"
        )

        # Stop conditions:
        # - OLLAMA_TIMEOUT: any agent timeout in current round.
        # - NO_IMPROVEMENT: score does not improve for configured rounds.
        # - EXCEPTION: global runtime reached or unhandled exception.
        # - MAX_ROUNDS: for-loop exhausts naturally.
        if timeout_this_round:
            stop_reason = STOP_OLLAMA_TIMEOUT
            console.print("[magenta]Stopping: OLLAMA_TIMEOUT.[/magenta]")
            break

        if non_improve_streak >= stop_if_no_improvement_rounds:
            stop_reason = STOP_NO_IMPROVEMENT
            console.print(
                f"[magenta]Stopping: NO_IMPROVEMENT ({stop_if_no_improvement_rounds} rounds).[/magenta]"
            )
            break

        if elapsed_after_round >= GLOBAL_MAX_RUNTIME_SECONDS:
            stop_reason = STOP_EXCEPTION
            console.print("[magenta]Stopping: global runtime limit reached.[/magenta]")
            break

        previous_judge = judge_output
        console.print(f"[Round {round_index}] Exiting round.")
    else:
        stop_reason = STOP_MAX_ROUNDS

    if stop_reason == STOP_MAX_ROUNDS and invalid_score_seen and completed_rounds == 1:
        stop_reason = STOP_INVALID_SCORE

    best_output_path = project_dir / "best_output.md"
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
) -> None:
    console.rule("Diagnostic Mode")
    console.print(
        "[cyan]Diagnostic constraints:[/cyan] one round only, short prompts, "
        "no memory update, no retries"
    )

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
        started = time.monotonic()
        try:
            output = fn()
            error = None
            console.print(f"[Round 1] {agent_name.capitalize()} finished.")
        except RuntimeError as exc:
            output = f"[{agent_name.upper()} ERROR] {exc}"
            error = str(exc)
            console.print(f"[red][Round 1] {agent_name} failed: {exc}[/red]")
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


def run_session_mode(
    *,
    console: Console,
    llm: OllamaClient,
    agents: ResearchAgents,
    task_text: str,
    project_dir: Path,
    memory_path: Path,
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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
    timeout_seconds = min(int(config.get("timeout_seconds", 120)), 120)

    project_dir = root / "projects" / project_name
    memory_path = project_dir / "memory.md"
    prompts_dir = root / "prompts"

    task_text = read_text(project_dir / "task.md")
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

    try:
        if args.diagnostic:
            run_diagnostic_mode(
                console=console,
                llm=llm,
                task_text=task_text,
                project_dir=project_dir,
                memory_path=memory_path,
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
            max_rounds=max_rounds,
            stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
        )
    except KeyboardInterrupt:
        console.print("[red]Manual interrupt detected in main loop. Stop reason: MANUAL_INTERRUPT[/red]")


if __name__ == "__main__":
    main()
