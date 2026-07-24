"""Strict project input resolution for CLI and UI-launched runs."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import DEFAULT_PROJECT_NAME
from .storage import UnsafeArtifactPathError, display_path, read_regular_text


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
    trusted_root = root.resolve()
    projects_dir = trusted_root / "projects"
    project_dir = projects_dir / project_name
    task_path = project_dir / "task.md"
    project_display_path = display_path(project_dir, root)
    task_display_path = display_path(task_path, root)

    try:
        projects_metadata = projects_dir.lstat()
    except FileNotFoundError:
        projects_metadata = None
    except OSError as exc:
        reason = exc.strerror or exc.__class__.__name__
        raise ProjectInputError(f"Projects directory is not readable: {reason}") from exc
    if projects_metadata is not None and stat.S_ISLNK(projects_metadata.st_mode):
        raise ProjectInputError("Project selection has an unsafe project path under projects/.")
    if projects_metadata is not None and not stat.S_ISDIR(projects_metadata.st_mode):
        raise ProjectInputError("Projects path is not a directory: projects/")

    try:
        project_metadata = project_dir.lstat()
    except FileNotFoundError:
        project_metadata = None
    except OSError as exc:
        reason = exc.strerror or exc.__class__.__name__
        raise ProjectInputError(f"Project path is not readable: {reason}") from exc
    if project_metadata is None:
        raise ProjectInputError(
            f"Project '{project_name}' was not found at {project_display_path}. "
            f"Create {task_display_path} or pass --project with an existing folder under projects/."
        )
    if stat.S_ISLNK(project_metadata.st_mode):
        raise ProjectInputError("Project selection has an unsafe project path under projects/.")
    if not stat.S_ISDIR(project_metadata.st_mode):
        raise ProjectInputError(f"Project path is not a directory: {project_display_path}")

    task_path = project_dir / "task.md"
    task_display_path = display_path(task_path, root)
    try:
        task_text = read_regular_text(task_path, anchor=trusted_root)
    except FileNotFoundError:
        raise ProjectInputError(
            f"Task file not found for project '{project_name}': {task_display_path}. "
            "Create task.md for this project before running."
        ) from None
    except UnsafeArtifactPathError:
        raise ProjectInputError(
            "Project selection has an unsafe task path under projects/."
        ) from None
    except UnicodeError as exc:
        raise ProjectInputError(f"Task file must be valid UTF-8 text: {task_display_path}") from exc
    except OSError as exc:
        reason = getattr(exc, "strerror", None) or exc.__class__.__name__
        raise ProjectInputError(
            f"Task file is not readable: {task_display_path}: {reason}"
        ) from exc

    task_text = task_text.strip()
    if not task_text:
        raise ProjectInputError(f"Task file is empty: {task_display_path}")

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
