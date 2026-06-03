"""Strict project input resolution for CLI and UI-launched runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import DEFAULT_PROJECT_NAME


class ProjectInputError(ValueError):
    """Raised when a selected project cannot provide a usable task input."""


@dataclass(frozen=True)
class ProjectInput:
    project_name: str
    project_dir: Path
    task_path: Path
    task_text: str
    project_title: str
    source_kind: str
    explicit_project: bool
    is_example_project: bool

    def as_metadata(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "project_dir": str(self.project_dir),
            "task_path": str(self.task_path),
            "project_title": self.project_title,
            "source_kind": self.source_kind,
            "explicit_project": self.explicit_project,
            "is_example_project": self.is_example_project,
        }


def extract_project_title(task_text: str, fallback: str) -> str:
    for raw_line in task_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            if title:
                return title
        return line[:120]
    return fallback


def classify_project_source(project_name: str, *, explicit_project: bool) -> str:
    if explicit_project:
        return "example_explicit" if project_name == DEFAULT_PROJECT_NAME else "user_provided"
    if project_name == DEFAULT_PROJECT_NAME:
        return "example_default"
    return "configured"


def load_project_input(
    *,
    root: Path,
    project_name: str,
    explicit_project: bool,
) -> ProjectInput:
    project_dir = (root / "projects" / project_name).resolve()
    task_path = project_dir / "task.md"

    if not project_dir.exists():
        raise ProjectInputError(
            f"Project '{project_name}' was not found at {project_dir}. "
            f"Create {task_path} or pass --project with an existing folder under projects/."
        )
    if not project_dir.is_dir():
        raise ProjectInputError(f"Project path is not a directory: {project_dir}")
    if not task_path.exists():
        raise ProjectInputError(
            f"Task file not found for project '{project_name}': {task_path}. "
            "Create task.md for this project before running."
        )
    if not task_path.is_file():
        raise ProjectInputError(f"Task path is not a file: {task_path}")

    try:
        task_text = task_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ProjectInputError(f"Task file is not readable: {task_path}: {exc}") from exc

    if not task_text:
        raise ProjectInputError(f"Task file is empty: {task_path}")

    return ProjectInput(
        project_name=project_name,
        project_dir=project_dir,
        task_path=task_path,
        task_text=task_text,
        project_title=extract_project_title(task_text, project_name),
        source_kind=classify_project_source(project_name, explicit_project=explicit_project),
        explicit_project=explicit_project,
        is_example_project=project_name == DEFAULT_PROJECT_NAME,
    )
