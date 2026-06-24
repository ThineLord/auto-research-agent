"""Storage utilities for pipeline inputs and outputs."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .judge_output import parse_judge_score

AUTO_MEMORY_HEADER = "## Iteration Memory (auto-managed)"
AUTO_MEMORY_NOTE = (
    "This section is automatically updated each round. "
    "It keeps concise, deduplicated research-state summaries."
)
ENTRY_LIMIT = 12
MAX_MEMORY_WORDS = 2000
MAX_PROMPT_MEMORY_WORDS = 1500
DEFAULT_RESEARCH_KEYWORDS = [
    "research",
    "method",
    "design",
    "architecture",
    "evaluation",
    "baseline",
    "implementation",
    "experiment",
]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def read_file_text(path: Path) -> str:
    """Read a text file exactly as stored, returning an empty string if missing."""
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def display_path(path: Path | str | None, root: Path | None = None, default: str = "N/A") -> str:
    text = str(path or "").strip()
    if not text:
        return default
    resolved_path = Path(text).expanduser()
    if root is not None:
        try:
            return resolved_path.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            pass
    return f"<repo>/{resolved_path.name}"


def write_file_text(path: Path, content: str) -> None:
    """Write text exactly as provided, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def tail_file_lines(path: Path, max_lines: int = 200) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-max_lines:])


def make_run_root(project_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_root = project_dir / "runs" / timestamp
    run_root.mkdir(parents=True, exist_ok=True)
    return run_root


def make_round_dir(run_root: Path, round_index: int) -> Path:
    round_dir = run_root / f"round_{round_index:02d}"
    round_dir.mkdir(parents=True, exist_ok=True)
    return round_dir


def save_round_outputs(
    round_dir: Path,
    *,
    draft: str,
    review: str,
    revised: str,
    judge: str,
) -> None:
    write_text(round_dir / "01_draft.md", draft)
    write_text(round_dir / "02_review.md", review)
    write_text(round_dir / "03_revised.md", revised)
    write_text(round_dir / "04_judge.md", judge)


def parse_score(judge_text: str) -> Optional[float]:
    return parse_judge_score(judge_text)


def _normalize_line(line: str) -> str:
    clean = line.strip()
    clean = re.sub(r"^[#>\-\*\d\.\)\(\s]+", "", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip(" :;-")


def _dedupe_sentences(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text)
    seen = set()
    deduped: List[str] = []
    for part in parts:
        p = part.strip()
        if not p:
            continue
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    if not deduped:
        return ""
    return " ".join(deduped)


def _clip_text(text: str, max_chars: int = 180) -> str:
    text = _dedupe_sentences(_normalize_line(text))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _collect_meaningful_lines(text: str) -> List[str]:
    lines = []
    for raw in text.splitlines():
        line = _normalize_line(raw)
        if not line:
            continue
        if len(line) < 12:
            continue
        if line.lower().startswith(("score:", "next_step:")):
            continue
        lines.append(line)
    return lines


def _pick_line(lines: List[str], keywords: List[str]) -> str:
    for line in lines:
        low = line.lower()
        if any(keyword in low for keyword in keywords):
            return line
    return lines[0] if lines else ""


def _merge_keywords(*keyword_groups: Sequence[str]) -> List[str]:
    keywords: List[str] = []
    seen = set()
    for group in keyword_groups:
        for keyword in group:
            normalized = keyword.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            keywords.append(normalized)
    return keywords


def _parse_auto_entries(memory_text: str) -> List[Dict[str, str]]:
    pattern = re.compile(
        r"### Round (?P<round>\d+)\n"
        r"- strongest idea: (?P<strongest>.*)\n"
        r"- major criticism: (?P<criticism>.*)\n"
        r"- unresolved problems: (?P<unresolved>.*)\n"
        r"- best next action: (?P<next_action>.*)\n"
        r"- current best score: (?P<best_score>.*)",
        flags=re.MULTILINE,
    )
    return [match.groupdict() for match in pattern.finditer(memory_text)]


def _build_auto_section(entries: List[Dict[str, str]]) -> str:
    blocks = [AUTO_MEMORY_HEADER, "", AUTO_MEMORY_NOTE, ""]
    for entry in entries:
        block = (
            f"### Round {entry['round']}\n"
            f"- strongest idea: {entry['strongest']}\n"
            f"- major criticism: {entry['criticism']}\n"
            f"- unresolved problems: {entry['unresolved']}\n"
            f"- best next action: {entry['next_action']}\n"
            f"- current best score: {entry['best_score']}"
        )
        blocks.append(block)
        blocks.append("")
    return "\n".join(blocks).rstrip()


def _word_count(text: str) -> int:
    return len(text.split())


def _tail_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[-max_words:]).strip()


def summarize_round_memory(
    *,
    revised_output: str,
    review_output: str,
    judge_output: str,
    current_best_score: Optional[float],
    topic_keywords: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    revised_lines = _collect_meaningful_lines(revised_output)
    review_lines = _collect_meaningful_lines(review_output)
    judge_lines = _collect_meaningful_lines(judge_output)
    research_keywords = _merge_keywords(topic_keywords or [], DEFAULT_RESEARCH_KEYWORDS)

    strongest = _pick_line(
        revised_lines,
        keywords=research_keywords,
    )
    major_criticism = _pick_line(
        review_lines + judge_lines,
        keywords=["weakness", "risk", "missing", "critic", "unclear", "blocker"],
    )
    unresolved = _pick_line(
        judge_lines + review_lines,
        keywords=["unresolved", "remaining", "blocker", "open", "risk", "limitation"],
    )
    next_action = _pick_line(
        revised_lines + review_lines,
        keywords=["tomorrow", "next", "implement", "evaluate", "ablation", "baseline", "run"],
    )

    return {
        "strongest": _clip_text(
            strongest or "Method direction is forming but still under-specified."
        ),
        "criticism": _clip_text(
            major_criticism or "Key claims need clearer evidence and baselines."
        ),
        "unresolved": _clip_text(
            unresolved or "Evaluation coverage and failure-mode analysis remain incomplete."
        ),
        "next_action": _clip_text(
            next_action or "Define one baseline experiment and implement it end-to-end."
        ),
        "best_score": "N/A" if current_best_score is None else f"{current_best_score:.2f}",
    }


def update_project_memory(
    *,
    memory_path: Path,
    round_index: int,
    summary: Dict[str, str],
) -> None:
    existing = read_text(memory_path)
    if AUTO_MEMORY_HEADER in existing:
        manual_part = existing.split(AUTO_MEMORY_HEADER, 1)[0].rstrip()
    else:
        manual_part = existing.rstrip()

    entries = _parse_auto_entries(existing)
    new_entry = {
        "round": f"{round_index:02d}",
        "strongest": summary["strongest"],
        "criticism": summary["criticism"],
        "unresolved": summary["unresolved"],
        "next_action": summary["next_action"],
        "best_score": summary["best_score"],
    }

    if not entries or (
        entries[-1].get("strongest") != new_entry["strongest"]
        or entries[-1].get("criticism") != new_entry["criticism"]
        or entries[-1].get("unresolved") != new_entry["unresolved"]
        or entries[-1].get("next_action") != new_entry["next_action"]
        or entries[-1].get("best_score") != new_entry["best_score"]
    ):
        entries.append(new_entry)
    else:
        entries[-1]["round"] = new_entry["round"]

    entries = entries[-ENTRY_LIMIT:]
    auto_section = _build_auto_section(entries)

    combined = f"{manual_part}\n\n{auto_section}".strip()
    if _word_count(combined) > MAX_MEMORY_WORDS:
        manual_tail = _tail_words(manual_part, 500) if manual_part else ""
        combined = f"{manual_tail}\n\n{auto_section}".strip()
    if _word_count(combined) > MAX_MEMORY_WORDS:
        combined = _tail_words(combined, MAX_MEMORY_WORDS)
    combined = combined.strip() + "\n"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(combined, encoding="utf-8")


def write_score_history(path: Path, history: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def get_memory_for_prompt(memory_path: Path) -> str:
    """Read memory.md and return only the latest words for prompt usage."""
    content = read_text(memory_path)
    if not content:
        return ""
    return _tail_words(content, MAX_PROMPT_MEMORY_WORDS)


def update_research_state(
    *,
    state_path: Path,
    round_index: int,
    best_score: float,
    revised_output: str,
    review_output: str,
    judge_output: str,
    topic_keywords: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    revised_lines = _collect_meaningful_lines(revised_output)
    review_lines = _collect_meaningful_lines(review_output)
    judge_lines = _collect_meaningful_lines(judge_output)
    research_keywords = _merge_keywords(
        topic_keywords or [],
        ["hypothesis", "propose", "mechanism"],
        DEFAULT_RESEARCH_KEYWORDS,
    )

    strongest_hypothesis = _pick_line(
        revised_lines,
        keywords=research_keywords,
    )
    biggest_blocker = _pick_line(
        review_lines + judge_lines,
        keywords=["blocker", "weakness", "risk", "missing", "unclear", "limitation"],
    )
    next_experiment = _pick_line(
        revised_lines + review_lines + judge_lines,
        keywords=["experiment", "ablation", "evaluate", "benchmark", "compare", "metric"],
    )
    open_question = _pick_line(
        judge_lines + review_lines + revised_lines,
        keywords=["question", "unknown", "uncertain", "assumption", "open"],
    )

    state = {
        "round": round_index,
        "current_strongest_hypothesis": _clip_text(
            strongest_hypothesis
            or "The current method direction is promising but needs stronger validation."
        ),
        "current_biggest_blocker": _clip_text(
            biggest_blocker
            or "Baseline comparison and failure-mode analysis are still insufficient."
        ),
        "current_next_experiment": _clip_text(
            next_experiment
            or "Run one controlled baseline comparison with explicit success metrics."
        ),
        "current_open_question": _clip_text(
            open_question
            or "Which mechanism gives the best tradeoff under the project constraints?"
        ),
        "current_best_score": round(best_score, 2),
    }

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def read_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict):
        return data
    return {}


def write_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_log_line(log_path: Path, message: str) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{ts} | {message}\n")
    except OSError:
        return


def write_interrupted_report(
    *,
    report_path: Path,
    last_completed_round: int,
    last_successful_agent: str,
    best_score: float,
    best_output_path: Path,
    resume_command: str,
    stop_time: str,
    repo_root: Path | None = None,
) -> None:
    content = (
        "# Interrupted Report\n\n"
        f"- last completed round: {last_completed_round}\n"
        f"- last successful agent: {last_successful_agent}\n"
        f"- best score so far: {best_score:.2f}\n"
        f"- best output path: {display_path(best_output_path, repo_root)}\n"
        f"- safe resume command: `{resume_command}`\n"
        f"- stop time: {stop_time}\n"
    )
    write_text(report_path, content)
