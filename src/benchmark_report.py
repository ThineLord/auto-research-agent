"""Benchmark report analysis helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean
from typing import Any

from .storage import parse_score, read_text, write_text


@dataclass(frozen=True)
class RoundClassification:
    round_index: int
    score: float | None
    successful_research_round: bool
    failed_provider_round: bool
    skipped_placeholder_round: bool
    revised_chars: int
    similarity_to_previous_success: float


@dataclass(frozen=True)
class BenchmarkReportAnalysis:
    successful_research_rounds: list[int]
    failed_provider_rounds: list[int]
    skipped_placeholder_rounds: list[int]
    convergence_start_round: int | None
    diminishing_returns_start_round: int | None
    mode_collapse_detected: bool
    high_similarity_success_rounds: list[int]
    classifications: list[RoundClassification]


def _provider_failure_text(text: str) -> bool:
    normalized = text.lower()
    return any(
        marker in normalized
        for marker in (
            "provider_quota_exhausted",
            "failed to call gemini api",
            "gemini request failed",
            "resource_exhausted",
            "rate limit",
            "rate-limit",
            "quota",
            "429",
        )
    )


def _placeholder_text(text: str) -> bool:
    normalized = text.lower()
    return any(
        marker in normalized
        for marker in (
            "[review skipped]",
            "[revise skipped]",
            "judge skipped",
            "draft agent failed",
            "draft/review agent failed",
        )
    )


def _words(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text.lower()))


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a[:12000], b[:12000]).ratio()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _round_index(round_dir: Path) -> int:
    match = re.search(r"round_(\d+)$", round_dir.name)
    return int(match.group(1)) if match else 0


def analyze_benchmark_run(run_root: Path) -> BenchmarkReportAnalysis:
    round_dirs = sorted(
        [path for path in run_root.glob("round_*") if path.is_dir()],
        key=_round_index,
    )
    classifications: list[RoundClassification] = []
    successful_scores: list[tuple[int, float]] = []
    successful_new_terms: list[tuple[int, int]] = []
    successful_revised_previous = ""
    successful_words_seen: set[str] = set()
    high_similarity_success_rounds: list[int] = []

    for round_dir in round_dirs:
        round_index = _round_index(round_dir)
        draft = read_text(round_dir / "01_draft.md")
        review = read_text(round_dir / "02_review.md")
        revised = read_text(round_dir / "03_revised.md")
        judge = read_text(round_dir / "04_judge.md")
        combined = "\n".join([draft, review, revised, judge])
        score = parse_score(judge)
        failed_provider = _provider_failure_text(combined)
        skipped_placeholder = _placeholder_text(combined)
        successful = (
            score is not None
            and not failed_provider
            and not skipped_placeholder
            and bool(revised.strip())
        )
        similarity_to_previous = (
            _similarity(successful_revised_previous, revised) if successful else 0.0
        )
        if successful and similarity_to_previous >= 0.82:
            high_similarity_success_rounds.append(round_index)
        classifications.append(
            RoundClassification(
                round_index=round_index,
                score=score,
                successful_research_round=successful,
                failed_provider_round=failed_provider,
                skipped_placeholder_round=skipped_placeholder,
                revised_chars=len(revised),
                similarity_to_previous_success=similarity_to_previous,
            )
        )
        if successful and score is not None:
            successful_scores.append((round_index, score))
            current_words = _words(revised)
            successful_new_terms.append((round_index, len(current_words - successful_words_seen)))
            successful_words_seen |= current_words
            successful_revised_previous = revised

    convergence_start_round = None
    if len(successful_scores) >= 4:
        running_best: list[tuple[int, float]] = []
        current_best = -1.0
        for round_index, score in successful_scores:
            current_best = max(current_best, score)
            running_best.append((round_index, current_best))
        for index in range(3, len(running_best)):
            window = [score for _, score in running_best[index - 2 : index + 1]]
            if max(window) - min(window) <= 1.0:
                convergence_start_round = running_best[index - 2][0]
                break

    diminishing_returns_start_round = None
    if len(successful_new_terms) >= 6:
        baseline = mean(count for _, count in successful_new_terms[:3])
        threshold = max(10.0, baseline * 0.35)
        for index in range(3, len(successful_new_terms)):
            window = [count for _, count in successful_new_terms[index - 2 : index + 1]]
            if mean(window) <= threshold:
                diminishing_returns_start_round = successful_new_terms[index - 2][0]
                break

    return BenchmarkReportAnalysis(
        successful_research_rounds=[
            item.round_index for item in classifications if item.successful_research_round
        ],
        failed_provider_rounds=[
            item.round_index for item in classifications if item.failed_provider_round
        ],
        skipped_placeholder_rounds=[
            item.round_index for item in classifications if item.skipped_placeholder_round
        ],
        convergence_start_round=convergence_start_round,
        diminishing_returns_start_round=diminishing_returns_start_round,
        mode_collapse_detected=len(high_similarity_success_rounds) >= 3,
        high_similarity_success_rounds=high_similarity_success_rounds,
        classifications=classifications,
    )


def write_benchmark_report(*, run_root: Path, output_path: Path) -> BenchmarkReportAnalysis:
    analysis = analyze_benchmark_run(run_root)
    checkpoint = _read_json(run_root.parent.parent / "checkpoint.json")
    lines = [
        "# Auto Research Agent Benchmark Report",
        "",
        "## Experiment Overview",
        "",
        f"- Run root: `{run_root}`",
        f"- Stop reason: `{checkpoint.get('stop_reason', 'unknown')}`",
        f"- Successful research rounds: {len(analysis.successful_research_rounds)}",
        f"- Failed provider rounds: {len(analysis.failed_provider_rounds)}",
        f"- Skipped placeholder rounds: {len(analysis.skipped_placeholder_rounds)}",
        "",
        "## Convergence Analysis",
        "",
        f"- Convergence start round: {analysis.convergence_start_round or 'not detected'}",
        "- Basis: successful research rounds only.",
        "",
        "## Redundancy Analysis",
        "",
        f"- Mode collapse detected: {'yes' if analysis.mode_collapse_detected else 'no'}",
        f"- High-similarity successful rounds: {analysis.high_similarity_success_rounds or 'none'}",
        "- Placeholder failures are excluded from mode-collapse analysis.",
        "",
        "## Gemini Provider Evaluation",
        "",
        f"- Failed provider rounds: {analysis.failed_provider_rounds or 'none'}",
    ]
    write_text(output_path, "\n".join(lines))
    return analysis
