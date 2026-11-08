"""Revision-checked input editing shared by both local dashboards."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .round_commit_recovery import round_commit_read_blocker
from .runtime import acquire_run_lock, release_run_lock
from .storage import (
    artifact_path_exists,
    ensure_project_runtime_paths_safe,
    read_regular_text,
    write_file_text,
)

FIELDS = ("task", "memory")


class InputEditConflict(ValueError):
    def __init__(self, code: str, current: dict | None = None):
        self.code = code
        self.current = current
        super().__init__(code)


def read_inputs(project_dir: Path) -> dict:
    ensure_project_runtime_paths_safe(project_dir, anchor=project_dir.parent)
    result: dict = {"revisions": {}}
    for field in FIELDS:
        path = project_dir / f"{field}.md"
        exists = artifact_path_exists(path)
        text = read_regular_text(path, missing_ok=True)
        result[field] = text
        result["revisions"][field] = hashlib.sha256(
            (str(exists) + "\0" + text).encode("utf-8")
        ).hexdigest()
    return result


def save_inputs(project_dir: Path, changes: dict, revisions: dict) -> dict:
    if (
        not isinstance(changes, dict)
        or not changes
        or set(changes) - set(FIELDS)
        or not all(isinstance(value, str) for value in changes.values())
        or not isinstance(revisions, dict)
        or any(not isinstance(revisions.get(field), str) for field in changes)
    ):
        raise ValueError("Input changes and their base revisions are required")
    handle, error = acquire_run_lock(project_dir, mode="input_edit", model_name="")
    if error or handle is None:
        raise InputEditConflict("input_busy")
    try:
        if round_commit_read_blocker(project_dir)[0]:
            raise InputEditConflict("input_recovery_pending")
        current = read_inputs(project_dir)
        if any(revisions[field] != current["revisions"][field] for field in changes):
            raise InputEditConflict("input_conflict", current)
        # Validate every submitted revision before writing any field.
        for field, text in changes.items():
            write_file_text(project_dir / f"{field}.md", text)
        return read_inputs(project_dir)
    finally:
        release_run_lock(handle)
