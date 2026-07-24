"""Resolve source/install layouts and seed the installed mock example safely."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .config import DEFAULT_PROJECT_NAME
from .storage import read_regular_text

_AT_FDCWD = -100
_RENAME_NOREPLACE = 0x00000001
_RENAME_EXCL = 0x00000004
_SOURCE_RESOURCE_MARKERS = (
    Path("config.example.yaml"),
    Path("prompts/draft.md"),
    Path("prompts/review.md"),
    Path("prompts/revise.md"),
    Path("prompts/judge.md"),
    Path("projects/example/task.md"),
)
_GENERATION_PROMPT_NAMES = ("draft.md", "review.md", "revise.md", "judge.md")


class PackageResourceError(RuntimeError):
    """Raised when required installed-package resources cannot be used safely."""


@dataclass(frozen=True)
class RuntimeLayout:
    """Separate writable workspace paths from read-only packaged resources."""

    workspace_root: Path
    resource_root: Path
    git_root: Path | None
    source_layout: bool

    @property
    def config_example_path(self) -> Path:
        return self.resource_root / "config.example.yaml"

    @property
    def prompts_dir(self) -> Path:
        return self.resource_root / "prompts"

    @property
    def example_task_path(self) -> Path:
        return self.resource_root / "projects" / DEFAULT_PROJECT_NAME / "task.md"


def _source_checkout_root(cli_file: str | Path) -> Path | None:
    cli_path = Path(cli_file).resolve()
    candidate = cli_path.parent.parent

    package_dir = Path(__file__).resolve().parent
    candidate_package = candidate / "src"
    try:
        same_package = candidate_package.resolve() == package_dir
    except OSError:
        same_package = False
    has_source_markers = (candidate / "pyproject.toml").is_file() and all(
        (candidate / marker).is_file() for marker in _SOURCE_RESOURCE_MARKERS
    )
    if same_package and has_source_markers:
        return candidate
    return None


def resolve_runtime_layout(
    *,
    cli_file: str | Path,
    cwd: Path | None = None,
) -> RuntimeLayout:
    """Resolve checkout/editable behavior or an installed writable workspace."""

    source_root = _source_checkout_root(cli_file)
    if source_root is not None:
        return RuntimeLayout(
            workspace_root=source_root,
            resource_root=source_root,
            git_root=source_root,
            source_layout=True,
        )

    package_root = files("src")
    if not isinstance(package_root, Path):
        raise PackageResourceError(
            "Installed package resources must be available from an unpacked filesystem package."
        )
    return RuntimeLayout(
        workspace_root=(cwd or Path.cwd()).resolve(),
        resource_root=package_root / "_bundled",
        git_root=None,
        source_layout=False,
    )


def validate_generation_resources(layout: RuntimeLayout) -> None:
    """Require complete, usable prompt resources before generation can write."""

    for prompt_name in _GENERATION_PROMPT_NAMES:
        prompt_path = layout.prompts_dir / prompt_name
        message = (
            f"Generation prompt {prompt_name} is unavailable or invalid; "
            "reinstall the package and retry."
        )
        try:
            prompt_text = read_regular_text(
                prompt_path,
                anchor=layout.resource_root,
                require_single_link=False,
            )
        except (OSError, UnicodeError):
            raise PackageResourceError(message) from None
        if not prompt_text.strip():
            raise PackageResourceError(message)


def _remove_staging_paths(
    *,
    staging_task_path: Path | None,
    staging_dir: Path | None,
    projects_dir: Path,
    projects_created: bool,
) -> None:
    if staging_task_path is not None:
        try:
            staging_task_path.unlink()
        except OSError:
            pass
    if staging_dir is not None:
        try:
            staging_dir.rmdir()
        except OSError:
            pass
    if projects_created:
        try:
            projects_dir.rmdir()
        except OSError:
            pass


def _raise_rename_error(result: int, target: Path) -> None:
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error_number, os.strerror(error_number), target)
    raise OSError(error_number, os.strerror(error_number), target)


def _rename_directory_noreplace(source: Path, target: Path) -> None:
    """Atomically publish a directory without replacing an existing target."""

    if sys.platform == "win32":
        os.rename(source, target)
        return

    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    target_bytes = os.fsencode(target)
    if sys.platform == "darwin":
        rename_exclusive = getattr(libc, "renamex_np", None)
        if rename_exclusive is None:
            raise PackageResourceError("Atomic no-replace project seeding is unavailable.")
        rename_exclusive.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename_exclusive.restype = ctypes.c_int
        _raise_rename_error(rename_exclusive(source_bytes, target_bytes, _RENAME_EXCL), target)
        return
    if sys.platform.startswith("linux"):
        rename_exclusive = getattr(libc, "renameat2", None)
        if rename_exclusive is None:
            raise PackageResourceError("Atomic no-replace project seeding is unavailable.")
        rename_exclusive.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_exclusive.restype = ctypes.c_int
        _raise_rename_error(
            rename_exclusive(
                _AT_FDCWD,
                source_bytes,
                _AT_FDCWD,
                target_bytes,
                _RENAME_NOREPLACE,
            ),
            target,
        )
        return
    raise PackageResourceError("Atomic no-replace project seeding is unavailable.")


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def seed_default_mock_project(
    layout: RuntimeLayout,
    *,
    mock_mode: bool,
    project_name: str,
    explicit_project: bool,
) -> bool:
    """Seed only a missing installed default mock project, without overwriting anything."""

    if (
        layout.source_layout
        or not mock_mode
        or explicit_project
        or project_name != DEFAULT_PROJECT_NAME
    ):
        return False

    projects_dir = layout.workspace_root / "projects"
    project_dir = projects_dir / DEFAULT_PROJECT_NAME
    if os.path.lexists(project_dir):
        return False
    if os.path.lexists(projects_dir) and (projects_dir.is_symlink() or not projects_dir.is_dir()):
        raise PackageResourceError(
            "Cannot seed the default mock project because workspace projects/ is not a directory."
        )

    try:
        task_bytes = layout.example_task_path.read_bytes()
    except OSError as exc:
        raise PackageResourceError(
            "Bundled example task is unavailable; reinstall the package and retry."
        ) from exc

    projects_created = False
    staging_dir: Path | None = None
    staging_task_path: Path | None = None
    try:
        if not os.path.lexists(projects_dir):
            try:
                projects_dir.mkdir(exist_ok=False)
                projects_created = True
            except FileExistsError:
                if projects_dir.is_symlink() or not projects_dir.is_dir():
                    raise PackageResourceError(
                        "Cannot seed the default mock project because workspace projects/ "
                        "is not a directory."
                    ) from None

        staging_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{DEFAULT_PROJECT_NAME}-seed-",
                dir=projects_dir,
            )
        )
        staging_task_path = staging_dir / "task.md"
        with staging_task_path.open("xb") as handle:
            handle.write(task_bytes)
            handle.flush()
            os.fsync(handle.fileno())

        if os.path.lexists(project_dir):
            _remove_staging_paths(
                staging_task_path=staging_task_path,
                staging_dir=staging_dir,
                projects_dir=projects_dir,
                projects_created=projects_created,
            )
            return False
        try:
            _rename_directory_noreplace(staging_dir, project_dir)
        except FileExistsError:
            _remove_staging_paths(
                staging_task_path=staging_task_path,
                staging_dir=staging_dir,
                projects_dir=projects_dir,
                projects_created=projects_created,
            )
            return False
        _fsync_directory(projects_dir)
    except BaseException as exc:
        _remove_staging_paths(
            staging_task_path=staging_task_path,
            staging_dir=staging_dir,
            projects_dir=projects_dir,
            projects_created=projects_created,
        )
        if isinstance(exc, PackageResourceError):
            raise
        if isinstance(exc, OSError):
            raise PackageResourceError(
                "Could not seed projects/example/task.md in the current workspace."
            ) from exc
        raise
    return True
