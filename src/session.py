"""Session-mode helpers for focused nightly research workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from rich.console import Console

from .agents import ResearchAgents
from .llm import OllamaClient
from .runner import run_iterative_rounds
from .storage import get_memory_for_prompt, write_text


def _clip_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).strip()


def _safe_generate(
    *,
    llm: OllamaClient,
    system_prompt: str,
    user_prompt: str,
    fallback: str,
    console: Console,
    label: str,
) -> str:
    try:
        return llm.generate(system_prompt=system_prompt, user_prompt=user_prompt)
    except RuntimeError as exc:
        console.print(f"[yellow]{label} fallback used: {exc}[/yellow]")
        return fallback


def generate_focus_objective(
    *,
    llm: OllamaClient,
    task_text: str,
    memory_text: str,
    console: Console,
) -> str:
    system_prompt = (
        "You are a research planner. Output one narrow, concrete subproblem only. "
        "Avoid broad discussion. Prefer measurable engineering scope."
    )
    user_prompt = (
        "Topic context: Privacy-Aware Memory Adapter (PAMA) for Personal AI Agents.\n\n"
        "Given task and memory, generate exactly one focused objective for tonight.\n"
        "Output only one line, no bullet list.\n\n"
        f"Task:\n{task_text}\n\nMemory:\n{memory_text}"
    )
    fallback = "Design evaluation metrics for privacy-utility tradeoff in PAMA memory adaptation."
    raw = _safe_generate(
        llm=llm,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        fallback=fallback,
        console=console,
        label="Session objective",
    )
    first_line = next(
        (line.strip("- ").strip() for line in raw.splitlines() if line.strip()), fallback
    )
    return _clip_words(first_line, 20)


def generate_current_plan(
    *,
    llm: OllamaClient,
    objective: str,
    task_text: str,
    memory_text: str,
    output_path: Path,
    console: Console,
) -> str:
    system_prompt = (
        "You are a technical planning assistant. Produce a concise implementation-oriented plan."
    )
    user_prompt = (
        "Build a plan for a single-session research sprint.\n"
        "Must include:\n"
        "- main objective\n"
        "- subproblems\n"
        "- dependencies\n"
        "- measurable outputs\n\n"
        f"Focused objective:\n{objective}\n\nTask:\n{task_text}\n\nMemory:\n{memory_text}"
    )
    fallback = (
        "## Main Objective\n"
        f"- {objective}\n\n"
        "## Subproblems\n"
        "- Define metric formulas for privacy and utility.\n"
        "- Identify baseline methods for comparison.\n"
        "- Specify one minimal evaluation protocol.\n\n"
        "## Dependencies\n"
        "- Existing PAMA design notes.\n"
        "- Access to one benchmark task and logs.\n"
        "- Metric computation script scaffold.\n\n"
        "## Measurable Outputs\n"
        "- A metric spec table (privacy, utility, tradeoff).\n"
        "- A baseline comparison checklist.\n"
        "- One runnable evaluation script stub.\n"
    )
    plan = _safe_generate(
        llm=llm,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        fallback=fallback,
        console=console,
        label="Session plan",
    )
    if "## Main Objective" not in plan:
        plan = fallback
    write_text(output_path, plan)
    return plan


def generate_final_session_report(
    *,
    llm: OllamaClient,
    objective: str,
    plan_text: str,
    best_output: str,
    research_state: Dict[str, object],
    memory_text: str,
    output_path: Path,
    console: Console,
) -> str:
    system_prompt = (
        "You are generating a concise morning report for an academic research session. "
        "Be concrete, technical, and action-oriented."
    )
    user_prompt = (
        "Generate a report with exact sections:\n"
        "- best research direction found\n"
        "- strongest criticism\n"
        "- unresolved risks\n"
        "- concrete implementation ideas\n"
        "- recommended papers/topics to investigate\n"
        "- tomorrow's top 3 actions\n\n"
        f"Focused objective:\n{objective}\n\n"
        f"Current plan:\n{plan_text}\n\n"
        f"Best output:\n{best_output}\n\n"
        f"Research state:\n{research_state}\n\n"
        f"Memory:\n{memory_text}"
    )
    fallback = (
        "# Final Session Report\n\n"
        "## best research direction found\n"
        f"- {research_state.get('current_strongest_hypothesis', objective)}\n\n"
        "## strongest criticism\n"
        f"- {research_state.get('current_biggest_blocker', 'Baseline quality is still weak.')}\n\n"
        "## unresolved risks\n"
        "- Evaluation setting may not reflect real personal-agent privacy constraints.\n"
        "- Privacy metric sensitivity might be unstable across tasks.\n\n"
        "## concrete implementation ideas\n"
        f"- {research_state.get('current_next_experiment', 'Implement one baseline experiment.')}\n"
        "- Add a script to compute privacy-utility tradeoff curves.\n"
        "- Create a reproducible ablation template.\n\n"
        "## recommended papers/topics to investigate\n"
        "- Privacy-utility tradeoff metrics for ML systems.\n"
        "- Memory editing and retrieval control in personal agents.\n"
        "- Differential privacy and constrained adaptation methods.\n\n"
        "## tomorrow's top 3 actions\n"
        "1. Finalize metric definitions and thresholds.\n"
        "2. Run one baseline-vs-PAMA comparison.\n"
        "3. Document failure cases and next ablation.\n"
    )
    report = _safe_generate(
        llm=llm,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        fallback=fallback,
        console=console,
        label="Final session report",
    )
    if "tomorrow" not in report.lower():
        report = fallback
    write_text(output_path, report)
    return report


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
    global_max_runtime_seconds: int,
    per_agent_timeout_seconds: int,
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
        global_max_runtime_seconds=global_max_runtime_seconds,
        per_agent_timeout_seconds=per_agent_timeout_seconds,
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
