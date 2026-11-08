"""One project boundary for flat workspaces and unmoved legacy projects."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .storage import (
    ensure_artifact_directory,
    list_artifact_directories,
    read_json_file,
    write_json_file,
)

RESERVED = frozenset(
    {
        "app",
        "projects",
        "src",
        "ui",
        "prompts",
        "scripts",
        "tests",
        "docs",
        "node_modules",
        "venv",
        "env",
    }
)


def validate_project_reference(name: str) -> str:
    """The historical single-component boundary, independent of new-folder policy."""
    if (
        not isinstance(name, str)
        or not name.strip()
        or name in {".", ".."}
        or any(c in name for c in ("/", "\\", "\0"))
    ):
        raise ValueError("Project name must be a simple folder name.")
    return name


def validate_project_name(name: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or name != name.strip()
        or name.startswith(".")
        or len(name) > 100
        or any(ord(c) < 32 or c in '/\\:*?"<>|' for c in name)
        or name.endswith(".")
        or name.split(".")[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
    ):
        raise ValueError("Project name must be a simple folder name (not hidden).")
    return name


def resolve_project_dir(root: Path, name: str) -> Path:
    """Legacy wins even if invalid: never silently substitute a different project."""
    validate_project_reference(name)
    root = root.resolve()
    legacy = root / "projects"
    if os.path.lexists(legacy):
        ensure_artifact_directory(legacy, anchor=root)
        if os.path.lexists(legacy / name):
            ensure_artifact_directory(legacy / name, anchor=root)
            return legacy / name
    validate_project_name(name)
    if name.casefold() in RESERVED:
        raise ValueError("This folder name is reserved for application files.")
    path = root / name
    if os.path.lexists(path):
        ensure_artifact_directory(path, anchor=root)
    return path


def discover_projects(root: Path) -> list[str]:
    root = root.resolve()
    names = set()
    # Legacy directories remain visible even with a missing task, for recovery/inspection.
    for parent, legacy in ((root, False), (root / "projects", True)):
        if not os.path.lexists(parent):
            continue
        try:
            entries = [path for _mtime, _name, path in list_artifact_directories(parent)]
        except OSError:
            continue
        for path in entries:
            try:
                (validate_project_reference if legacy else validate_project_name)(path.name)
                if not legacy and (
                    path.name.casefold() in RESERVED or not (path / "task.md").is_file()
                ):
                    continue
                ensure_artifact_directory(path, anchor=root)
                resolve_project_dir(root, path.name)
            except (ValueError, OSError):
                continue
            names.add(path.name)
    return sorted(names)


def create_project(root: Path, name: str, task: str) -> Path:
    """Publish a complete new flat project atomically, with no replacement or migration."""
    from .package_resources import _rename_directory_noreplace

    validate_project_name(name)
    if name.casefold() in RESERVED:
        raise ValueError("This folder name is reserved for application files.")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("A research task is required.")
    root = root.resolve()
    ensure_artifact_directory(root, anchor=root)
    legacy = root / "projects"
    if os.path.lexists(legacy):
        ensure_artifact_directory(legacy, anchor=root)
    target = root / name
    if os.path.lexists(target) or os.path.lexists(legacy / name):
        raise FileExistsError("A folder with this name already exists; nothing was changed.")
    staging = Path(tempfile.mkdtemp(prefix=".ara-create-", dir=root))
    try:
        for filename, text in [("task.md", task.strip() + "\n"), ("memory.md", "")]:
            with (staging / filename).open("x", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        # Check the legacy namespace again before atomic publication.
        if os.path.lexists(legacy / name):
            raise FileExistsError("A legacy project with this name already exists.")
        _rename_directory_noreplace(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


def selected_project(root: Path, fallback: str) -> str:
    try:
        value = read_json_file(root / ".ara-workspace.json").get("selected_project", fallback)
        validate_project_reference(value)
        return value if value in discover_projects(root) else fallback
    except (OSError, ValueError, TypeError):
        return fallback


def select_project(root: Path, name: str) -> None:
    resolve_project_dir(root, name)
    if name not in discover_projects(root):
        raise ValueError("Unknown project")
    write_json_file(root / ".ara-workspace.json", {"schema_version": 1, "selected_project": name})
