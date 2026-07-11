"""Path-safety helpers for resuming existing project runs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

MISSING_RUN_ROOT = "missing_run_root"
UNSAFE_RUN_ROOT = "unsafe_run_root"
STALE_RUN_ROOT = "stale_run_root"
INVALID_RUN_ROOT = "invalid_run_root"
INACCESSIBLE_RUN_ROOT = "inaccessible_run_root"
RUN_ID_MISMATCH = "run_id_mismatch"
UNSAFE_ROUND_PATH = "unsafe_round_path"
INVALID_ROUND_PATH = "invalid_round_path"
INACCESSIBLE_ROUND_PATH = "inaccessible_round_path"
UNSAFE_ARTIFACT_PATH = "unsafe_artifact_path"

RESUME_PATH_MESSAGES = {
    MISSING_RUN_ROOT: "checkpoint run_root is missing",
    UNSAFE_RUN_ROOT: (
        "checkpoint run_root must be an absolute per-run directory inside the selected "
        "project's runs directory"
    ),
    STALE_RUN_ROOT: "checkpoint run_root does not exist",
    INVALID_RUN_ROOT: "checkpoint run_root must be a directory",
    INACCESSIBLE_RUN_ROOT: "checkpoint run_root is not readable and writable",
    RUN_ID_MISMATCH: "checkpoint run_id must match the canonical run directory name",
    UNSAFE_ROUND_PATH: "checkpoint round paths must stay inside the selected run directory",
    INVALID_ROUND_PATH: "checkpoint round path must be a directory",
    INACCESSIBLE_ROUND_PATH: "checkpoint round directory is not safely accessible",
    UNSAFE_ARTIFACT_PATH: (
        "resume artifact paths must remain regular files inside the selected project run"
    ),
}


def validate_project_run_root(
    *,
    project_dir: Path,
    run_root_value: Any,
    require_writable: bool = False,
) -> tuple[Path | None, str | None]:
    """Return a canonical project run directory and an optional privacy-safe blocker code."""
    run_root_text = str(run_root_value or "").strip()
    if not run_root_text:
        return None, MISSING_RUN_ROOT

    candidate = Path(run_root_text)
    if not candidate.is_absolute():
        return None, UNSAFE_RUN_ROOT

    configured_runs_dir = project_dir / "runs"
    try:
        runs_root = configured_runs_dir.resolve(strict=False)
        resolved_candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None, UNSAFE_RUN_ROOT

    # Canonical runs are direct children. Equality would write run-level files into the
    # container itself; nested/manual layouts have never been emitted by this project. The
    # configured runs directory may itself be a user-controlled storage symlink, so containment
    # is checked against its resolved target rather than the project's physical parent.
    if resolved_candidate == runs_root or resolved_candidate.parent != runs_root:
        return None, UNSAFE_RUN_ROOT
    if not resolved_candidate.exists():
        return resolved_candidate, STALE_RUN_ROOT
    if not resolved_candidate.is_dir():
        return resolved_candidate, INVALID_RUN_ROOT
    access_mode = os.R_OK | os.X_OK | (os.W_OK if require_writable else 0)
    if not os.access(resolved_candidate, access_mode):
        return resolved_candidate, INACCESSIBLE_RUN_ROOT
    return resolved_candidate, None


def validate_resume_run_root(
    *,
    project_dir: Path,
    run_root_value: Any,
) -> tuple[Path | None, str | None]:
    """Validate a canonical per-run directory for resume reads and writes."""
    return validate_project_run_root(
        project_dir=project_dir,
        run_root_value=run_root_value,
        require_writable=True,
    )


def validate_resume_round_dir(
    *,
    run_root: Path,
    round_dir: Path,
    require_writable: bool = False,
) -> tuple[Path | None, str | None]:
    """Validate a direct round directory without following a leaf symlink."""
    try:
        canonical_run_root = run_root.resolve(strict=False)
        if round_dir.is_symlink():
            return None, UNSAFE_ROUND_PATH
        canonical_round_dir = round_dir.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None, UNSAFE_ROUND_PATH

    if canonical_round_dir.parent != canonical_run_root:
        return None, UNSAFE_ROUND_PATH
    if canonical_round_dir.exists() and not canonical_round_dir.is_dir():
        return canonical_round_dir, INVALID_ROUND_PATH
    if canonical_round_dir.exists():
        access_mode = os.R_OK | os.X_OK | (os.W_OK if require_writable else 0)
        if not os.access(canonical_round_dir, access_mode):
            return canonical_round_dir, INACCESSIBLE_ROUND_PATH
    return canonical_round_dir, None


def resume_artifact_links_are_safe(
    *,
    parent_dir: Path,
    paths: Iterable[Path],
) -> bool:
    """Reject leaf symlinks or paths that resolve outside their expected parent."""
    try:
        canonical_parent = parent_dir.resolve(strict=False)
        for path in paths:
            if (
                path.is_symlink()
                or path.resolve(strict=False).parent != canonical_parent
                or (path.exists() and not path.is_file())
                or (path.exists() and not os.access(path, os.R_OK))
            ):
                return False
    except (OSError, RuntimeError, ValueError):
        return False
    return True
