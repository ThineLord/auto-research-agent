"""Storage utilities for pipeline inputs and outputs."""

from __future__ import annotations

import ctypes
import errno
import json
import os
import re
import stat
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, BinaryIO, Dict, List, Optional, Sequence, TextIO

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
_RENAME_NOREPLACE = 0x00000001
_RENAME_EXCL = 0x00000004
PROJECT_RUNTIME_FILE_NAMES = (
    "memory.md",
    "best_output.md",
    "score_history.json",
    "research_state.json",
    "run_analysis.json",
    "run_comparison.json",
    "current_plan.md",
    "final_session_report.md",
    "run.log",
    "model_ops.log",
    "checkpoint.json",
    "interrupted_report.md",
    "STOP_REQUESTED",
    "active_run.json",
    "active_run.guard",
    "ui_run_process.json",
    "ui_model_job_process.json",
    "provider_events.jsonl",
    ".round_commit_transaction.json",
    ".run_finalize_transaction.json",
    ".diagnostic_finalize_transaction.json",
)
PROJECT_RUNTIME_DIRECTORY_NAMES = ("artifacts", "outputs", "logs", "cache", "survey")
PROJECT_RUNTIME_NESTED_FILE_PATHS = (
    Path("artifacts/cloud_free_models.json"),
    Path("artifacts/cloud_free_profile.json"),
)


class UnsafeArtifactPathError(OSError):
    """Raised when automatic runtime I/O encounters a link or non-regular node."""


_ARTIFACT_BOUNDARIES: tuple[tuple[Path, Path], ...] = ()
_ARTIFACT_BOUNDARIES_LOCK = RLock()


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def _register_artifact_boundary(root: Path, anchor: Path) -> None:
    global _ARTIFACT_BOUNDARIES
    root = _lexical_absolute(root)
    anchor = _lexical_absolute(anchor)
    with _ARTIFACT_BOUNDARIES_LOCK:
        inherited_matches: list[tuple[int, Path]] = []
        for registered_root, registered_anchor in _ARTIFACT_BOUNDARIES:
            if registered_root == root:
                continue
            try:
                root.relative_to(registered_root)
            except ValueError:
                continue
            inherited_matches.append((len(registered_root.parts), registered_anchor))
        if inherited_matches:
            anchor = max(inherited_matches, key=lambda item: item[0])[1]
        try:
            root.relative_to(anchor)
        except ValueError as exc:
            raise _unsafe_path_error("boundary") from exc

        boundaries: list[tuple[Path, Path]] = []
        for registered_root, registered_anchor in _ARTIFACT_BOUNDARIES:
            if registered_root == root:
                continue
            try:
                registered_root.relative_to(root)
                anchor_is_nested = registered_anchor.is_relative_to(root)
            except ValueError:
                anchor_is_nested = False
            if anchor_is_nested:
                registered_anchor = anchor
            boundaries.append((registered_root, registered_anchor))
        boundaries.append((root, anchor))
        _ARTIFACT_BOUNDARIES = tuple(boundaries)


def _registered_artifact_anchor(path: Path) -> Path | None:
    path = _lexical_absolute(path)
    matches: list[tuple[int, Path]] = []
    with _ARTIFACT_BOUNDARIES_LOCK:
        boundaries = _ARTIFACT_BOUNDARIES
    for root, anchor in boundaries:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        matches.append((len(root.parts), anchor))
    return max(matches, default=(0, None), key=lambda item: item[0])[1]


def artifact_boundary_is_registered(path: Path) -> bool:
    """Return whether an automatic artifact path has a process-wide trusted anchor."""
    return _registered_artifact_anchor(path) is not None


def _supports_descriptor_relative_io() -> bool:
    return (
        os.name != "nt"
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks
        and os.unlink in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
    )


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )


def _unsafe_path_error(kind: str) -> UnsafeArtifactPathError:
    return UnsafeArtifactPathError(f"unsafe automatic artifact {kind}")


def _validate_regular_metadata(
    metadata: os.stat_result,
    *,
    kind: str,
    require_single_link: bool = True,
) -> None:
    if not stat.S_ISREG(metadata.st_mode) or (require_single_link and metadata.st_nlink != 1):
        raise _unsafe_path_error(kind)


def _path_is_link_or_junction(path: Path, metadata: os.stat_result) -> bool:
    if stat.S_ISLNK(metadata.st_mode):
        return True
    if os.name != "nt":
        return False
    file_attributes = int(getattr(metadata, "st_file_attributes", 0))
    reparse_attribute = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))
    if file_attributes & reparse_attribute:
        return True
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    return bool(is_junction(path)) if callable(is_junction) else False


def _open_directory_from_anchor(
    directory: Path,
    *,
    anchor: Path,
    create: bool,
) -> int | None:
    directory = _lexical_absolute(directory)
    anchor = _lexical_absolute(anchor)
    try:
        relative = directory.relative_to(anchor)
    except ValueError as exc:
        raise _unsafe_path_error("outside trusted anchor") from exc

    if _supports_descriptor_relative_io():
        descriptor = -1
        try:
            descriptor = os.open(anchor, _directory_open_flags())
            for component in relative.parts:
                try:
                    next_descriptor = os.open(
                        component,
                        _directory_open_flags(),
                        dir_fd=descriptor,
                    )
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        os.mkdir(component, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                    next_descriptor = os.open(
                        component,
                        _directory_open_flags(),
                        dir_fd=descriptor,
                    )
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except FileNotFoundError:
            if descriptor >= 0:
                os.close(descriptor)
            raise
        except OSError as exc:
            if descriptor >= 0:
                os.close(descriptor)
            raise _unsafe_path_error("parent directory") from exc

    if os.name != "nt":
        raise _unsafe_path_error("descriptor-relative I/O unavailable")

    current = anchor
    try:
        anchor_metadata = current.lstat()
    except OSError as exc:
        raise _unsafe_path_error("trusted anchor") from exc
    if _path_is_link_or_junction(current, anchor_metadata) or not stat.S_ISDIR(
        anchor_metadata.st_mode
    ):
        raise _unsafe_path_error("trusted anchor")
    for component in relative.parts:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if not create:
                raise
            try:
                current.mkdir()
            except OSError as exc:
                raise _unsafe_path_error("parent directory") from exc
            metadata = current.lstat()
        except OSError as exc:
            raise _unsafe_path_error("parent directory") from exc
        if _path_is_link_or_junction(current, metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise _unsafe_path_error("parent directory")
    return None


def _open_parent_directory(
    path: Path,
    *,
    create: bool,
    anchor: Path | None = None,
) -> int | None:
    path = _lexical_absolute(path)
    selected_anchor = anchor or _registered_artifact_anchor(path)
    if selected_anchor is not None:
        return _open_directory_from_anchor(
            path.parent,
            anchor=selected_anchor,
            create=create,
        )

    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    if _supports_descriptor_relative_io():
        try:
            return os.open(path.parent, _directory_open_flags())
        except FileNotFoundError:
            if not create:
                raise
            raise _unsafe_path_error("parent directory") from None
        except OSError as exc:
            raise _unsafe_path_error("parent directory") from exc

    # Windows keeps its historical path-based behavior but rejects every static link or
    # non-directory parent. Active hostile replacement remains a documented platform limit.
    try:
        parent_metadata = path.parent.lstat()
    except FileNotFoundError:
        if not create:
            raise
        raise _unsafe_path_error("parent directory") from None
    except OSError as exc:
        raise _unsafe_path_error("parent directory") from exc
    if _path_is_link_or_junction(path.parent, parent_metadata) or not stat.S_ISDIR(
        parent_metadata.st_mode
    ):
        raise _unsafe_path_error("parent directory")
    return None


def _entry_metadata(path: Path, parent_descriptor: int | None) -> os.stat_result | None:
    try:
        if parent_descriptor is not None:
            return os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _unsafe_path_error("path") from exc


def artifact_path_is_safe(
    path: Path,
    *,
    allow_missing: bool = True,
    anchor: Path | None = None,
) -> bool:
    """Return whether a leaf is missing or a single-link regular file without following it."""
    path = Path(path)
    parent_descriptor: int | None = None
    try:
        parent_descriptor = _open_parent_directory(path, create=False, anchor=anchor)
        metadata = _entry_metadata(path, parent_descriptor)
        if metadata is None:
            return allow_missing
        _validate_regular_metadata(metadata, kind="path")
        return True
    except OSError:
        return False
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def artifact_path_exists(
    path: Path,
    *,
    allow_directory: bool = False,
    anchor: Path | None = None,
) -> bool:
    """Check for a safe existing node without following its leaf or anchored parents."""
    path = Path(path)
    parent_descriptor: int | None = None
    try:
        parent_descriptor = _open_parent_directory(path, create=False, anchor=anchor)
        metadata = _entry_metadata(path, parent_descriptor)
        if metadata is None or _path_is_link_or_junction(path, metadata):
            return False
        if stat.S_ISDIR(metadata.st_mode):
            return allow_directory
        _validate_regular_metadata(metadata, kind="path")
        return True
    except OSError:
        return False
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def ensure_artifact_paths_safe(
    paths: Sequence[Path],
    *,
    anchor: Path | None = None,
) -> None:
    """Fail before work when automatic artifact leaves are unsafe."""
    for path_value in paths:
        path = Path(path_value)
        parent_descriptor: int | None = None
        try:
            parent_descriptor = _open_parent_directory(path, create=False, anchor=anchor)
            metadata = _entry_metadata(path, parent_descriptor)
            if metadata is None:
                continue
            if stat.S_ISDIR(metadata.st_mode):
                raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), path.name)
            _validate_regular_metadata(metadata, kind="path")
        finally:
            if parent_descriptor is not None:
                os.close(parent_descriptor)


def ensure_artifact_directory(path: Path, *, anchor: Path | None = None) -> Path:
    """Create or validate an automatic directory without following any anchored component."""
    path = _lexical_absolute(path)
    descriptor = _open_parent_directory(
        path / ".artifact-directory-probe", create=True, anchor=anchor
    )
    if descriptor is not None:
        os.close(descriptor)
    return path


def ensure_project_runtime_paths_safe(
    project_dir: Path,
    *,
    anchor: Path | None = None,
) -> Path | None:
    """Validate all fixed automatic project leaves before provider or process startup."""
    project_dir = _lexical_absolute(project_dir)
    project_anchor = _lexical_absolute(anchor or project_dir.parent)
    probe = project_dir / ".runtime-path-probe"
    parent_descriptor = _open_parent_directory(
        probe,
        create=False,
        anchor=project_anchor,
    )
    runs_metadata: os.stat_result | None = None
    existing_runtime_directories: set[str] = set()
    try:
        for name in PROJECT_RUNTIME_FILE_NAMES:
            artifact_path = project_dir / name
            metadata = _entry_metadata(artifact_path, parent_descriptor)
            if metadata is not None:
                # Preserve the historical handling of stale directories: callers may
                # treat them as an already-present stop marker or an unreadable cache.
                # Links, hard-linked files, and blocking/special nodes still fail closed.
                if _path_is_link_or_junction(artifact_path, metadata):
                    raise _unsafe_path_error("project artifact")
                if stat.S_ISREG(metadata.st_mode):
                    _validate_regular_metadata(metadata, kind="project artifact")
                elif not stat.S_ISDIR(metadata.st_mode):
                    raise _unsafe_path_error("project artifact")
        for name in PROJECT_RUNTIME_DIRECTORY_NAMES:
            artifact_directory = project_dir / name
            metadata = _entry_metadata(artifact_directory, parent_descriptor)
            if metadata is not None and (
                _path_is_link_or_junction(artifact_directory, metadata)
                or not stat.S_ISDIR(metadata.st_mode)
            ):
                raise _unsafe_path_error("project artifact directory")
            if metadata is not None:
                existing_runtime_directories.add(name)
        runs_metadata = _entry_metadata(project_dir / "runs", parent_descriptor)
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)

    _register_artifact_boundary(project_dir, project_anchor)
    nested_paths = [
        project_dir / relative_path
        for relative_path in PROJECT_RUNTIME_NESTED_FILE_PATHS
        if relative_path.parts[0] in existing_runtime_directories
    ]
    for nested_path in nested_paths:
        nested_parent_descriptor: int | None = None
        try:
            nested_parent_descriptor = _open_parent_directory(nested_path, create=False)
            nested_metadata = _entry_metadata(nested_path, nested_parent_descriptor)
            if nested_metadata is None:
                continue
            if _path_is_link_or_junction(nested_path, nested_metadata):
                raise _unsafe_path_error("project artifact")
            if stat.S_ISREG(nested_metadata.st_mode):
                _validate_regular_metadata(nested_metadata, kind="project artifact")
            elif not stat.S_ISDIR(nested_metadata.st_mode):
                raise _unsafe_path_error("project artifact")
        finally:
            if nested_parent_descriptor is not None:
                os.close(nested_parent_descriptor)
    if runs_metadata is None:
        return None
    runs_path = project_dir / "runs"
    if _path_is_link_or_junction(runs_path, runs_metadata):
        try:
            runs_root = runs_path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise _unsafe_path_error("runs directory") from exc
        if not runs_root.is_dir():
            raise _unsafe_path_error("runs directory")
        try:
            runs_relative = runs_root.relative_to(project_dir.resolve(strict=True))
        except (OSError, RuntimeError, ValueError):
            pass
        else:
            lexical_runs_root = project_dir / runs_relative
            _register_artifact_boundary(lexical_runs_root, project_anchor)
            return lexical_runs_root
        _register_artifact_boundary(runs_root, runs_root)
        return runs_root
    elif not stat.S_ISDIR(runs_metadata.st_mode):
        raise _unsafe_path_error("runs directory")
    return runs_path


def list_artifact_directories(path: Path) -> list[tuple[float, str, Path]]:
    """List real direct child directories without following directory entries."""
    path = _lexical_absolute(path)
    selected_anchor = _registered_artifact_anchor(path / ".directory-list-probe") or path
    descriptor = _open_directory_from_anchor(path, anchor=selected_anchor, create=False)
    if descriptor is not None:
        try:
            entries: list[tuple[float, str, Path]] = []
            for name in os.listdir(descriptor):
                try:
                    metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISDIR(metadata.st_mode):
                    entries.append((metadata.st_mtime, name, path / name))
            return entries
        finally:
            os.close(descriptor)

    entries = []
    for child in path.iterdir():
        metadata = child.lstat()
        if stat.S_ISDIR(metadata.st_mode) and not _path_is_link_or_junction(child, metadata):
            entries.append((metadata.st_mtime, child.name, child))
    return entries


def list_artifact_entry_names(path: Path, *, missing_ok: bool = False) -> list[str]:
    """List direct entry names through the registered no-follow directory walk."""
    path = _lexical_absolute(path)
    selected_anchor = _registered_artifact_anchor(path / ".directory-list-probe") or path
    try:
        descriptor = _open_directory_from_anchor(path, anchor=selected_anchor, create=False)
    except FileNotFoundError:
        if missing_ok:
            return []
        raise
    if descriptor is not None:
        try:
            return sorted(os.listdir(descriptor))
        finally:
            os.close(descriptor)
    return sorted(child.name for child in path.iterdir())


def list_artifact_regular_files(
    path: Path,
    *,
    allowed_top_level_directories: set[str] | None = None,
) -> list[Path]:
    """Recursively list safe regular files without following directory entries."""
    path = _lexical_absolute(path)
    selected_anchor = _registered_artifact_anchor(path / ".file-list-probe") or path
    descriptor = _open_directory_from_anchor(path, anchor=selected_anchor, create=False)
    if descriptor is not None:
        files: list[Path] = []

        def walk(directory_descriptor: int, lexical_directory: Path) -> None:
            try:
                names = sorted(os.listdir(directory_descriptor))
            except OSError as exc:
                raise _unsafe_path_error("directory traversal") from exc
            for name in names:
                try:
                    metadata = os.stat(
                        name,
                        dir_fd=directory_descriptor,
                        follow_symlinks=False,
                    )
                except OSError:
                    continue
                child = lexical_directory / name
                if stat.S_ISDIR(metadata.st_mode):
                    if (
                        lexical_directory == path
                        and allowed_top_level_directories is not None
                        and name not in allowed_top_level_directories
                    ):
                        continue
                    child_descriptor = -1
                    try:
                        child_descriptor = os.open(
                            name,
                            _directory_open_flags(),
                            dir_fd=directory_descriptor,
                        )
                        opened_metadata = os.fstat(child_descriptor)
                        if (metadata.st_dev, metadata.st_ino) != (
                            opened_metadata.st_dev,
                            opened_metadata.st_ino,
                        ):
                            continue
                        walk(child_descriptor, child)
                    except OSError:
                        continue
                    finally:
                        if child_descriptor >= 0:
                            os.close(child_descriptor)
                    continue
                try:
                    _validate_regular_metadata(metadata, kind="listed artifact")
                except OSError:
                    continue
                files.append(child)

        try:
            walk(descriptor, path)
            return sorted(files, key=lambda item: item.as_posix())
        finally:
            os.close(descriptor)

    # Windows fallback: every observed component is checked statically. Active hostile
    # replacement remains subject to the documented Windows path-race limitation.
    files = []

    def walk_path(directory: Path) -> None:
        try:
            children = sorted(directory.iterdir(), key=lambda child: child.name)
        except OSError as exc:
            raise _unsafe_path_error("directory traversal") from exc
        for child in children:
            try:
                metadata = child.lstat()
            except OSError:
                continue
            if _path_is_link_or_junction(child, metadata):
                continue
            if stat.S_ISDIR(metadata.st_mode):
                if (
                    directory == path
                    and allowed_top_level_directories is not None
                    and child.name not in allowed_top_level_directories
                ):
                    continue
                walk_path(child)
                continue
            try:
                _validate_regular_metadata(metadata, kind="listed artifact")
            except OSError:
                continue
            files.append(child)

    walk_path(path)
    return sorted(files, key=lambda item: item.as_posix())


def _atomic_write_text(path: Path, content: str, *, anchor: Path | None = None) -> None:
    """Durably replace a text file without truncating the previous version on failure."""
    path = Path(path)
    parent_descriptor: int | None = None
    temp_path: Path | None = None
    temp_name = f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        parent_descriptor = _open_parent_directory(path, create=True, anchor=anchor)
        existing_metadata = _entry_metadata(path, parent_descriptor)
        if existing_metadata is not None:
            _validate_regular_metadata(existing_metadata, kind="write target")

        if parent_descriptor is not None:
            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            descriptor = os.open(temp_name, flags, 0o600, dir_fd=parent_descriptor)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as temp_file:
                    descriptor = -1
                    temp_file.write(content)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            os.replace(
                temp_name,
                path.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
        else:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(content)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, path)
    except BaseException:
        if parent_descriptor is not None:
            try:
                os.unlink(temp_name, dir_fd=parent_descriptor)
            except OSError:
                pass
        elif temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def _create_text_exclusive(path: Path, content: str, *, anchor: Path | None = None) -> None:
    """Durably create a text file once, preserving any partial evidence after failure."""
    path = Path(path)
    parent_descriptor: int | None = None
    descriptor = -1
    try:
        parent_descriptor = _open_parent_directory(path, create=True, anchor=anchor)
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        open_target: str | Path = path.name if parent_descriptor is not None else path
        open_kwargs = {"dir_fd": parent_descriptor} if parent_descriptor is not None else {}
        descriptor = os.open(open_target, flags, 0o600, **open_kwargs)
        opened_metadata = os.fstat(descriptor)
        _validate_regular_metadata(opened_metadata, kind="create-only target")
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            descriptor = -1
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        if parent_descriptor is not None:
            os.fsync(parent_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def read_regular_text(
    path: Path,
    *,
    missing_ok: bool = False,
    anchor: Path | None = None,
    require_single_link: bool = True,
) -> str:
    """Read a regular UTF-8 leaf through an anchored parent descriptor."""
    path = Path(path)
    parent_descriptor: int | None = None
    descriptor = -1
    try:
        parent_descriptor = _open_parent_directory(path, create=False, anchor=anchor)
        metadata = _entry_metadata(path, parent_descriptor)
        if metadata is None:
            if missing_ok:
                return ""
            raise FileNotFoundError(path.name)
        _validate_regular_metadata(
            metadata,
            kind="read target",
            require_single_link=require_single_link,
        )
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        if parent_descriptor is not None:
            descriptor = os.open(path.name, flags, dir_fd=parent_descriptor)
        else:
            descriptor = os.open(path, flags)
        opened_metadata = os.fstat(descriptor)
        _validate_regular_metadata(
            opened_metadata,
            kind="read target",
            require_single_link=require_single_link,
        )
        if (metadata.st_dev, metadata.st_ino) != (
            opened_metadata.st_dev,
            opened_metadata.st_ino,
        ):
            raise _unsafe_path_error("changed read target")
        with os.fdopen(descriptor, "r", encoding="utf-8") as file:
            descriptor = -1
            return file.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def read_regular_text_bounded(
    path: Path,
    *,
    max_bytes: int,
    anchor: Path | None = None,
) -> str:
    """Read one regular UTF-8 leaf without allocating beyond a fixed byte ceiling."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0:
        raise ValueError("max_bytes must be a non-negative integer")
    path = Path(path)
    parent_descriptor: int | None = None
    descriptor = -1
    try:
        parent_descriptor = _open_parent_directory(path, create=False, anchor=anchor)
        metadata = _entry_metadata(path, parent_descriptor)
        if metadata is None:
            raise FileNotFoundError(path.name)
        _validate_regular_metadata(
            metadata,
            kind="bounded read target",
            require_single_link=True,
        )
        if metadata.st_size > max_bytes:
            raise ValueError("automatic artifact exceeds byte limit")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        open_target: str | Path = path.name if parent_descriptor is not None else path
        open_kwargs = {"dir_fd": parent_descriptor} if parent_descriptor is not None else {}
        descriptor = os.open(open_target, flags, **open_kwargs)
        opened_metadata = os.fstat(descriptor)
        _validate_regular_metadata(
            opened_metadata,
            kind="bounded read target",
            require_single_link=True,
        )
        if (metadata.st_dev, metadata.st_ino) != (
            opened_metadata.st_dev,
            opened_metadata.st_ino,
        ):
            raise _unsafe_path_error("changed bounded read target")
        with os.fdopen(descriptor, "rb") as file:
            descriptor = -1
            content = file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError("automatic artifact exceeds byte limit")
        return content.decode("utf-8", errors="strict")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def read_text(path: Path, *, anchor: Path | None = None) -> str:
    return read_regular_text(path, missing_ok=True, anchor=anchor).strip()


def write_text(path: Path, content: str, *, anchor: Path | None = None) -> None:
    _atomic_write_text(path, content.strip() + "\n", anchor=anchor)


def write_text_create_only(path: Path, content: str, *, anchor: Path | None = None) -> None:
    """Write normalized text exactly once without replacing an existing filesystem entry."""
    _create_text_exclusive(path, content.strip() + "\n", anchor=anchor)


def write_file_text_create_only(path: Path, content: str, *, anchor: Path | None = None) -> None:
    """Write exact text once without replacing an existing filesystem entry."""
    _create_text_exclusive(path, content, anchor=anchor)


def _raise_noreplace_rename_error(result: int, target: Path) -> None:
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error_number, os.strerror(error_number), target.name)
    raise OSError(error_number, os.strerror(error_number), target.name)


def _rename_child_noreplace(
    parent_descriptor: int | None,
    source_name: str,
    target_name: str,
    *,
    parent: Path,
) -> None:
    """Atomically publish one staged child without replacing the target leaf."""
    if sys.platform == "win32":
        os.rename(parent / source_name, parent / target_name)
        return
    if parent_descriptor is None:
        raise OSError(errno.ENOTSUP, "atomic no-replace publication is unavailable")
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source_name)
    target_bytes = os.fsencode(target_name)
    if sys.platform == "darwin":
        rename_exclusive = getattr(libc, "renameatx_np", None)
        if rename_exclusive is None:
            raise OSError(errno.ENOTSUP, "atomic no-replace publication is unavailable")
        rename_exclusive.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_exclusive.restype = ctypes.c_int
        _raise_noreplace_rename_error(
            rename_exclusive(
                parent_descriptor,
                source_bytes,
                parent_descriptor,
                target_bytes,
                _RENAME_EXCL,
            ),
            parent / target_name,
        )
        return
    if sys.platform.startswith("linux"):
        rename_exclusive = getattr(libc, "renameat2", None)
        if rename_exclusive is None:
            raise OSError(errno.ENOTSUP, "atomic no-replace publication is unavailable")
        rename_exclusive.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_exclusive.restype = ctypes.c_int
        _raise_noreplace_rename_error(
            rename_exclusive(
                parent_descriptor,
                source_bytes,
                parent_descriptor,
                target_bytes,
                _RENAME_NOREPLACE,
            ),
            parent / target_name,
        )
        return
    raise OSError(errno.ENOTSUP, "atomic no-replace publication is unavailable")


def write_file_text_publish_only(
    path: Path,
    content: str,
    *,
    anchor: Path | None = None,
) -> None:
    """Durably publish exact text atomically without replacing an existing leaf."""
    path = _lexical_absolute(path)
    parent_descriptor: int | None = None
    descriptor = -1
    staging_name = f".{path.name}.{uuid.uuid4().hex}.publish"
    try:
        parent_descriptor = _open_parent_directory(path, create=False, anchor=anchor)
        if _entry_metadata(path, parent_descriptor) is not None:
            raise FileExistsError(path.name)
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        open_target: str | Path = (
            staging_name if parent_descriptor is not None else path.parent / staging_name
        )
        open_kwargs = {"dir_fd": parent_descriptor} if parent_descriptor is not None else {}
        descriptor = os.open(open_target, flags, 0o600, **open_kwargs)
        _validate_regular_metadata(
            os.fstat(descriptor),
            kind="create-only publication staging",
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            descriptor = -1
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        _rename_child_noreplace(
            parent_descriptor,
            staging_name,
            path.name,
            parent=path.parent,
        )
    except BaseException:
        try:
            if parent_descriptor is not None:
                os.unlink(staging_name, dir_fd=parent_descriptor)
            else:
                (path.parent / staging_name).unlink(missing_ok=True)
        except OSError:
            pass
        if parent_descriptor is not None:
            try:
                os.fsync(parent_descriptor)
            except OSError:
                pass
        raise
    else:
        if parent_descriptor is not None:
            os.fsync(parent_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def read_file_text(path: Path, *, anchor: Path | None = None) -> str:
    """Read a text file exactly as stored, returning an empty string if missing."""
    try:
        return read_regular_text(path, missing_ok=True, anchor=anchor)
    except (OSError, UnicodeError):
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


def write_file_text(path: Path, content: str, *, anchor: Path | None = None) -> None:
    """Write text exactly as provided, creating parent directories as needed."""
    _atomic_write_text(path, content, anchor=anchor)


def tail_file_lines(path: Path, max_lines: int = 200, *, anchor: Path | None = None) -> str:
    try:
        lines = read_regular_text(path, missing_ok=True, anchor=anchor).splitlines()
    except (OSError, UnicodeError):
        return ""
    return "\n".join(lines[-max_lines:])


def make_run_root(project_dir: Path, *, anchor: Path | None = None) -> Path:
    project_dir = _lexical_absolute(project_dir)
    project_anchor = _lexical_absolute(anchor or project_dir.parent)
    existing_runs_root = ensure_project_runtime_paths_safe(project_dir, anchor=project_anchor)
    runs_path = project_dir / "runs"
    if existing_runs_root is None:
        _make_directory_child(
            project_dir,
            "runs",
            allow_existing=False,
            anchor=project_anchor,
        )
        runs_root = runs_path
        runs_anchor = project_anchor
    else:
        runs_root = existing_runs_root
        if runs_root != runs_path:
            runs_anchor = runs_root
        else:
            runs_anchor = project_anchor

    for _ in range(100):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        try:
            return _make_directory_child(
                runs_root,
                timestamp,
                allow_existing=False,
                anchor=runs_anchor,
            )
        except FileExistsError:
            continue
    raise OSError("unable to allocate a unique run directory")


def _make_directory_child(
    parent: Path,
    name: str,
    *,
    allow_existing: bool,
    anchor: Path | None = None,
    mode: int = 0o777,
) -> Path:
    parent = _lexical_absolute(parent)
    child = parent / name
    parent_descriptor = _open_parent_directory(child, create=False, anchor=anchor)
    if parent_descriptor is not None:
        try:
            try:
                os.mkdir(name, mode=mode, dir_fd=parent_descriptor)
            except FileExistsError:
                if not allow_existing:
                    raise
            metadata = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode):
                raise _unsafe_path_error("directory")
        finally:
            os.close(parent_descriptor)
        return child

    try:
        metadata = child.lstat()
    except FileNotFoundError:
        child.mkdir(mode=mode)
    else:
        if not allow_existing:
            raise FileExistsError(child.name)
        if _path_is_link_or_junction(child, metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise _unsafe_path_error("directory")
    return child


def create_artifact_directory_only(
    path: Path,
    *,
    anchor: Path | None = None,
    mode: int = 0o700,
) -> Path:
    """Create one fixed directory without replacement through an anchored parent."""
    path = _lexical_absolute(path)
    if path.name in {"", ".", ".."} or type(mode) is not int or mode != 0o700:
        raise ValueError("create-only artifact directory parameters are invalid")
    return _make_directory_child(
        path.parent,
        path.name,
        allow_existing=False,
        anchor=anchor,
        mode=mode,
    )


def make_round_dir(
    run_root: Path,
    round_index: int,
    *,
    allow_existing: bool = False,
    anchor: Path | None = None,
) -> Path:
    run_root = _lexical_absolute(run_root)
    selected_anchor = anchor or _registered_artifact_anchor(run_root / ".round-probe")
    if selected_anchor is None:
        descriptor = _open_directory_from_anchor(run_root, anchor=run_root, create=False)
        if descriptor is not None:
            os.close(descriptor)
        _register_artifact_boundary(run_root, run_root)
        selected_anchor = run_root
    return _make_directory_child(
        run_root,
        f"round_{round_index:02d}",
        allow_existing=allow_existing,
        anchor=selected_anchor,
    )


def make_round_attempt_dir(
    run_root: Path,
    round_index: int,
    attempt_id: str,
    *,
    anchor: Path | None = None,
) -> Path:
    """Exclusively allocate one restricted append-only round-attempt directory."""
    if (
        isinstance(round_index, bool)
        or not isinstance(round_index, int)
        or not 1 <= round_index <= 999999
    ):
        raise ValueError("round_index must be an integer between 1 and 999999")
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]{7,63}", attempt_id) is None:
        raise ValueError("attempt_id must use 8-64 lowercase ASCII identifier characters")

    run_root = _lexical_absolute(run_root)
    selected_anchor = anchor or _registered_artifact_anchor(run_root / ".attempt-probe")
    if selected_anchor is None:
        descriptor = _open_directory_from_anchor(run_root, anchor=run_root, create=False)
        if descriptor is not None:
            os.close(descriptor)
        _register_artifact_boundary(run_root, run_root)
        selected_anchor = run_root

    partial_root = _make_directory_child(
        run_root,
        "partial_rounds",
        allow_existing=True,
        anchor=selected_anchor,
    )
    round_root = _make_directory_child(
        partial_root,
        f"round_{round_index:02d}",
        allow_existing=True,
        anchor=selected_anchor,
    )
    attempt_dir = _make_directory_child(
        round_root,
        f"attempt_{attempt_id}",
        allow_existing=False,
        anchor=selected_anchor,
    )
    _make_directory_child(
        attempt_dir,
        "output",
        allow_existing=False,
        anchor=selected_anchor,
    )
    return attempt_dir


def save_round_outputs(
    round_dir: Path,
    *,
    draft: str,
    review: str,
    revised: str,
    judge: str,
    anchor: Path | None = None,
) -> None:
    write_text(round_dir / "01_draft.md", draft, anchor=anchor)
    write_text(round_dir / "02_review.md", review, anchor=anchor)
    write_text(round_dir / "03_revised.md", revised, anchor=anchor)
    write_text(round_dir / "04_judge.md", judge, anchor=anchor)


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


def build_project_memory_text(
    existing: str,
    *,
    round_index: int,
    summary: Dict[str, str],
) -> str:
    """Build the next memory.md contents without performing filesystem I/O."""
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
    return combined.strip() + "\n"


def update_project_memory(
    *,
    memory_path: Path,
    round_index: int,
    summary: Dict[str, str],
    anchor: Path | None = None,
) -> None:
    existing = read_text(memory_path, anchor=anchor)
    combined = build_project_memory_text(
        existing,
        round_index=round_index,
        summary=summary,
    )
    _atomic_write_text(memory_path, combined, anchor=anchor)


def build_score_history_text(history: List[Dict[str, Any]]) -> str:
    """Serialize score history exactly as the existing writer does."""
    return json.dumps(history, indent=2)


def write_score_history(
    path: Path,
    history: List[Dict[str, Any]],
    *,
    anchor: Path | None = None,
) -> None:
    _atomic_write_text(path, build_score_history_text(history), anchor=anchor)


def get_memory_for_prompt(memory_path: Path, *, anchor: Path | None = None) -> str:
    """Read memory.md and return only the latest words for prompt usage."""
    content = read_text(memory_path, anchor=anchor)
    if not content:
        return ""
    return _tail_words(content, MAX_PROMPT_MEMORY_WORDS)


def build_research_state(
    *,
    round_index: int,
    best_score: float,
    revised_output: str,
    review_output: str,
    judge_output: str,
    topic_keywords: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Build research-state data without performing filesystem I/O."""
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
    return state


def update_research_state(
    *,
    state_path: Path,
    round_index: int,
    best_score: float,
    revised_output: str,
    review_output: str,
    judge_output: str,
    topic_keywords: Optional[Sequence[str]] = None,
    anchor: Path | None = None,
) -> Dict[str, Any]:
    state = build_research_state(
        round_index=round_index,
        best_score=best_score,
        revised_output=revised_output,
        review_output=review_output,
        judge_output=judge_output,
        topic_keywords=topic_keywords,
    )
    _atomic_write_text(state_path, json.dumps(state, indent=2), anchor=anchor)
    return state


def read_json_file(path: Path, *, anchor: Path | None = None) -> Dict[str, Any]:
    try:
        content = read_regular_text(path, missing_ok=True, anchor=anchor)
        if not content:
            return {}
        data = json.loads(content)
    except (OSError, UnicodeError, ValueError, RecursionError):
        return {}
    if isinstance(data, dict):
        return data
    return {}


def write_json_file(
    path: Path,
    data: Dict[str, Any],
    *,
    anchor: Path | None = None,
) -> None:
    _atomic_write_text(path, json.dumps(data, indent=2), anchor=anchor)


def write_json_file_create_only(
    path: Path,
    data: Dict[str, Any],
    *,
    anchor: Path | None = None,
) -> None:
    """Serialize a JSON object once without replacing an existing filesystem entry."""
    _create_text_exclusive(path, json.dumps(data, indent=2), anchor=anchor)


def open_append_text_file(path: Path, *, anchor: Path | None = None) -> TextIO:
    """Open a regular append sink without following anchored components or its leaf."""
    path = Path(path)
    parent_descriptor: int | None = None
    descriptor = -1
    try:
        parent_descriptor = _open_parent_directory(path, create=True, anchor=anchor)
        metadata = _entry_metadata(path, parent_descriptor)
        if metadata is not None:
            if stat.S_ISDIR(metadata.st_mode):
                raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), path.name)
            _validate_regular_metadata(metadata, kind="append target")
        flags = (
            os.O_WRONLY
            | os.O_APPEND
            | os.O_CREAT
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        open_target: str | Path = path.name if parent_descriptor is not None else path
        open_kwargs = {"dir_fd": parent_descriptor} if parent_descriptor is not None else {}
        if metadata is None:
            try:
                descriptor = os.open(open_target, flags | os.O_EXCL, 0o600, **open_kwargs)
            except FileExistsError:
                metadata = _entry_metadata(path, parent_descriptor)
                if metadata is None:
                    raise _unsafe_path_error("changed append target") from None
                _validate_regular_metadata(metadata, kind="append target")
                descriptor = os.open(open_target, flags & ~os.O_CREAT, **open_kwargs)
        else:
            descriptor = os.open(open_target, flags & ~os.O_CREAT, **open_kwargs)
        opened_metadata = os.fstat(descriptor)
        _validate_regular_metadata(opened_metadata, kind="append target")
        if metadata is not None and (metadata.st_dev, metadata.st_ino) != (
            opened_metadata.st_dev,
            opened_metadata.st_ino,
        ):
            raise _unsafe_path_error("changed append target")
        file = os.fdopen(descriptor, "a", encoding="utf-8")
        descriptor = -1
        return file
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def append_file_text(path: Path, content: str, *, anchor: Path | None = None) -> None:
    with open_append_text_file(path, anchor=anchor) as file:
        file.write(content)


def unlink_artifact_file(
    path: Path,
    *,
    missing_ok: bool = True,
    anchor: Path | None = None,
) -> None:
    """Unlink one regular automatic artifact through its anchored parent descriptor."""
    path = Path(path)
    parent_descriptor: int | None = None
    try:
        parent_descriptor = _open_parent_directory(path, create=False, anchor=anchor)
        metadata = _entry_metadata(path, parent_descriptor)
        if metadata is None:
            if missing_ok:
                return
            raise FileNotFoundError(path.name)
        _validate_regular_metadata(metadata, kind="unlink target")
        if parent_descriptor is not None:
            os.unlink(path.name, dir_fd=parent_descriptor)
        else:
            path.unlink()
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def unlink_artifact_file_if_matches(
    path: Path,
    expected_content: str,
    *,
    anchor: Path | None = None,
) -> None:
    """Unlink a regular artifact only while its exact bytes and identity still match."""
    try:
        expected_bytes = expected_content.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("expected_content must be valid UTF-8") from exc
    path = Path(path)
    parent_descriptor: int | None = None
    descriptor = -1
    try:
        parent_descriptor = _open_parent_directory(path, create=False, anchor=anchor)
        metadata = _entry_metadata(path, parent_descriptor)
        if metadata is None:
            raise FileNotFoundError(path.name)
        _validate_regular_metadata(
            metadata,
            kind="conditional unlink target",
            require_single_link=True,
        )
        if metadata.st_size != len(expected_bytes):
            raise _unsafe_path_error("changed conditional unlink target")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        open_target: str | Path = path.name if parent_descriptor is not None else path
        open_kwargs = {"dir_fd": parent_descriptor} if parent_descriptor is not None else {}
        descriptor = os.open(open_target, flags, **open_kwargs)
        opened_metadata = os.fstat(descriptor)
        _validate_regular_metadata(
            opened_metadata,
            kind="conditional unlink target",
            require_single_link=True,
        )
        if (metadata.st_dev, metadata.st_ino) != (
            opened_metadata.st_dev,
            opened_metadata.st_ino,
        ):
            raise _unsafe_path_error("changed conditional unlink target")
        with os.fdopen(descriptor, "rb") as file:
            descriptor = -1
            current_bytes = file.read(len(expected_bytes) + 1)
        if current_bytes != expected_bytes:
            raise _unsafe_path_error("changed conditional unlink target")
        current_metadata = _entry_metadata(path, parent_descriptor)
        if current_metadata is None or (
            current_metadata.st_dev,
            current_metadata.st_ino,
            current_metadata.st_size,
        ) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
        ):
            raise _unsafe_path_error("changed conditional unlink target")
        if parent_descriptor is not None:
            os.unlink(path.name, dir_fd=parent_descriptor)
        else:
            path.unlink()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def open_binary_update_file(path: Path, *, anchor: Path | None = None) -> BinaryIO:
    """Open or create one regular binary coordination leaf without following links."""
    path = Path(path)
    parent_descriptor: int | None = None
    descriptor = -1
    try:
        parent_descriptor = _open_parent_directory(path, create=True, anchor=anchor)
        metadata = _entry_metadata(path, parent_descriptor)
        if metadata is not None:
            _validate_regular_metadata(metadata, kind="coordination target")
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        open_target: str | Path = path.name if parent_descriptor is not None else path
        open_kwargs = {"dir_fd": parent_descriptor} if parent_descriptor is not None else {}
        if metadata is None:
            try:
                descriptor = os.open(open_target, flags | os.O_EXCL, 0o600, **open_kwargs)
            except FileExistsError:
                metadata = _entry_metadata(path, parent_descriptor)
                if metadata is None:
                    raise _unsafe_path_error("changed coordination target") from None
                _validate_regular_metadata(metadata, kind="coordination target")
                descriptor = os.open(open_target, flags & ~os.O_CREAT, **open_kwargs)
        else:
            descriptor = os.open(open_target, flags & ~os.O_CREAT, **open_kwargs)
        opened_metadata = os.fstat(descriptor)
        _validate_regular_metadata(opened_metadata, kind="coordination target")
        if metadata is not None and (metadata.st_dev, metadata.st_ino) != (
            opened_metadata.st_dev,
            opened_metadata.st_ino,
        ):
            raise _unsafe_path_error("changed coordination target")
        file = os.fdopen(descriptor, "r+b")
        descriptor = -1
        return file
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def append_log_line(log_path: Path, message: str, *, anchor: Path | None = None) -> None:
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open_append_text_file(log_path, anchor=anchor) as f:
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
    anchor: Path | None = None,
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
    write_text(report_path, content, anchor=anchor)
