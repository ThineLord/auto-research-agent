"""Storage utilities for pipeline inputs and outputs."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def make_run_root(project_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
    match = re.search(r"SCORE:\s*([0-9]+(?:\.[0-9]+)?)", judge_text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        score = float(match.group(1))
    except ValueError:
        return None
    return max(0.0, min(100.0, score))
