from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import src.package_resources as package_resources
from src.package_resources import RuntimeLayout, resolve_runtime_layout, seed_default_mock_project

REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCE_PAIRS = {
    "config.example.yaml": "config.example.yaml",
    "prompts/draft.md": "prompts/draft.md",
    "prompts/review.md": "prompts/review.md",
    "prompts/revise.md": "prompts/revise.md",
    "prompts/judge.md": "prompts/judge.md",
    "projects/example/task.md": "projects/example/task.md",
}


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InstalledPackageResourceTests(unittest.TestCase):
    def _copy_installed_package(self, root: Path) -> Path:
        package_parent = root / "site-packages"
        shutil.copytree(
            REPO_ROOT / "src",
            package_parent / "src",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        return package_parent

    def _run_installed(
        self,
        *,
        package_parent: Path,
        workspace: Path,
        argv: list[str],
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "CLI_ARGS": json.dumps(argv),
                "EXPECTED_PACKAGE_PARENT": str(package_parent.resolve()),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(package_parent.resolve()),
            }
        )
        script = """
import json
import os
import sys
from pathlib import Path

import src
from src.cli import main

package_parent = Path(os.environ["EXPECTED_PACKAGE_PARENT"]).resolve()
assert Path(src.__file__).resolve().is_relative_to(package_parent)
sys.argv = ["auto-research-agent", *json.loads(os.environ["CLI_ARGS"])]
main()
"""
        return subprocess.run(
            [sys.executable, "-c", script],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    def test_bundled_resources_match_canonical_bytes(self) -> None:
        bundle_root = REPO_ROOT / "src" / "_bundled"
        self.assertEqual(
            sorted(path.relative_to(bundle_root).as_posix() for path in bundle_root.rglob("*")),
            sorted(
                [
                    "config.example.yaml",
                    "projects",
                    "projects/example",
                    "projects/example/task.md",
                    "prompts",
                    "prompts/draft.md",
                    "prompts/judge.md",
                    "prompts/review.md",
                    "prompts/revise.md",
                ]
            ),
        )
        for canonical, bundled in RESOURCE_PAIRS.items():
            with self.subTest(resource=canonical):
                self.assertEqual(
                    (REPO_ROOT / canonical).read_bytes(),
                    (bundle_root / bundled).read_bytes(),
                )

    def test_setuptools_package_data_is_an_exact_allowlist(self) -> None:
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("include-package-data = false", pyproject)
        _, marker, remainder = pyproject.partition("[tool.setuptools.package-data]")
        self.assertTrue(marker)
        package_data_section = remainder.split("\n[", 1)[0]
        _, assignment, value = package_data_section.partition("src =")
        self.assertTrue(assignment)
        self.assertEqual(
            ast.literal_eval(value.strip()),
            [f"_bundled/{path}" for path in RESOURCE_PAIRS.values()],
        )

    def test_runtime_layout_preserves_source_and_uses_cwd_when_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_layout = resolve_runtime_layout(
                cli_file=REPO_ROOT / "src" / "cli.py",
                cwd=root,
            )
            self.assertTrue(source_layout.source_layout)
            self.assertEqual(source_layout.workspace_root, REPO_ROOT)
            self.assertEqual(source_layout.resource_root, REPO_ROOT)
            self.assertEqual(source_layout.git_root, REPO_ROOT)

            installed_cli = root / "site-packages" / "src" / "cli.py"
            installed_cli.parent.mkdir(parents=True)
            installed_cli.write_text("# installed marker\n", encoding="utf-8")
            (installed_cli.parent.parent / "pyproject.toml").write_text(
                "[project]\nname = 'unrelated'\n",
                encoding="utf-8",
            )
            workspace = root / "workspace"
            workspace.mkdir()
            installed_layout = resolve_runtime_layout(
                cli_file=installed_cli,
                cwd=workspace,
            )
            self.assertFalse(installed_layout.source_layout)
            self.assertEqual(installed_layout.workspace_root, workspace.resolve())
            self.assertEqual(installed_layout.resource_root, REPO_ROOT / "src" / "_bundled")
            self.assertIsNone(installed_layout.git_root)

            missing_cli_layout = resolve_runtime_layout(
                cli_file=root / "missing" / "src" / "cli.py",
                cwd=workspace,
            )
            self.assertFalse(missing_cli_layout.source_layout)
            self.assertEqual(missing_cli_layout.workspace_root, workspace.resolve())

    def test_interrupted_seed_never_publishes_a_partial_project(self) -> None:
        class InterruptingWriter:
            def __init__(self, path: Path) -> None:
                self._handle = original_open(path, "xb")

            def __enter__(self) -> InterruptingWriter:
                return self

            def __exit__(self, *args: object) -> None:
                self._handle.close()

            def write(self, data: bytes) -> int:
                self._handle.write(data[:1])
                self._handle.flush()
                raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            layout = RuntimeLayout(
                workspace_root=workspace,
                resource_root=REPO_ROOT / "src" / "_bundled",
                git_root=None,
                source_layout=False,
            )
            original_open = Path.open

            def interrupt_staging_write(
                path: Path,
                mode: str = "r",
                *args: object,
                **kwargs: object,
            ) -> object:
                if path.name == "task.md" and path.parent.name.startswith(".example-seed-"):
                    return InterruptingWriter(path)
                return original_open(path, mode, *args, **kwargs)

            with patch.object(Path, "open", new=interrupt_staging_write):
                with self.assertRaises(KeyboardInterrupt):
                    seed_default_mock_project(
                        layout,
                        mock_mode=True,
                        project_name="example",
                        explicit_project=False,
                    )

            project_dir = workspace / "projects" / "example"
            self.assertFalse(project_dir.exists())
            projects_dir = workspace / "projects"
            if projects_dir.exists():
                self.assertEqual(list(projects_dir.iterdir()), [])

            self.assertTrue(
                seed_default_mock_project(
                    layout,
                    mock_mode=True,
                    project_name="example",
                    explicit_project=False,
                )
            )
            self.assertEqual(
                (project_dir / "task.md").read_bytes(),
                (REPO_ROOT / "projects" / "example" / "task.md").read_bytes(),
            )

    def test_interrupted_open_cleans_an_owned_staging_path(self) -> None:
        class InterruptingEnter:
            def __init__(self, path: Path) -> None:
                self._path = path

            def __enter__(self) -> object:
                handle = original_open(self._path, "xb")
                handle.write(b"partial")
                handle.close()
                raise KeyboardInterrupt

            def __exit__(self, *args: object) -> None:
                raise AssertionError("__exit__ must not run when __enter__ raises")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            layout = RuntimeLayout(
                workspace_root=workspace,
                resource_root=REPO_ROOT / "src" / "_bundled",
                git_root=None,
                source_layout=False,
            )
            original_open = Path.open

            def interrupt_staging_open(
                path: Path,
                mode: str = "r",
                *args: object,
                **kwargs: object,
            ) -> object:
                if path.name == "task.md" and path.parent.name.startswith(".example-seed-"):
                    return InterruptingEnter(path)
                return original_open(path, mode, *args, **kwargs)

            with patch.object(Path, "open", new=interrupt_staging_open):
                with self.assertRaises(KeyboardInterrupt):
                    seed_default_mock_project(
                        layout,
                        mock_mode=True,
                        project_name="example",
                        explicit_project=False,
                    )

            self.assertFalse((workspace / "projects" / "example").exists())
            projects_dir = workspace / "projects"
            if projects_dir.exists():
                self.assertEqual(list(projects_dir.iterdir()), [])

    def test_seed_publish_never_replaces_a_racing_empty_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            layout = RuntimeLayout(
                workspace_root=workspace,
                resource_root=REPO_ROOT / "src" / "_bundled",
                git_root=None,
                source_layout=False,
            )
            real_publish = package_resources._rename_directory_noreplace
            observed_inode: int | None = None

            def create_racing_target(source: Path, target: Path) -> None:
                nonlocal observed_inode
                target.mkdir()
                observed_inode = target.stat().st_ino
                real_publish(source, target)

            with patch.object(
                package_resources,
                "_rename_directory_noreplace",
                side_effect=create_racing_target,
            ):
                self.assertFalse(
                    seed_default_mock_project(
                        layout,
                        mock_mode=True,
                        project_name="example",
                        explicit_project=False,
                    )
                )

            project_dir = workspace / "projects" / "example"
            self.assertTrue(project_dir.is_dir())
            self.assertEqual(project_dir.stat().st_ino, observed_inode)
            self.assertEqual(list(project_dir.iterdir()), [])
            self.assertEqual(
                sorted(path.name for path in project_dir.parent.iterdir()),
                ["example"],
            )

    def test_concurrent_seed_has_exactly_one_atomic_publisher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            layout = RuntimeLayout(
                workspace_root=workspace,
                resource_root=REPO_ROOT / "src" / "_bundled",
                git_root=None,
                source_layout=False,
            )
            worker_count = 8
            barrier = threading.Barrier(worker_count)

            def run_seed() -> bool:
                barrier.wait(timeout=5)
                return seed_default_mock_project(
                    layout,
                    mock_mode=True,
                    project_name="example",
                    explicit_project=False,
                )

            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                results = list(executor.map(lambda _: run_seed(), range(worker_count)))

            self.assertEqual(results.count(True), 1)
            self.assertEqual(results.count(False), worker_count - 1)
            project_dir = workspace / "projects" / "example"
            self.assertEqual(
                (project_dir / "task.md").read_bytes(),
                (REPO_ROOT / "projects" / "example" / "task.md").read_bytes(),
            )
            self.assertEqual(
                sorted(path.name for path in project_dir.parent.iterdir()),
                ["example"],
            )

    def test_installed_mock_seeds_only_workspace_and_ignores_foreign_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_parent = self._copy_installed_package(root)
            package_before = _tree_hashes(package_parent)
            expected_prompt_hashes = {
                name: _sha256(REPO_ROOT / "prompts" / name)
                for name in ("draft.md", "review.md", "revise.md", "judge.md")
            }

            for workspace_kind in ("neutral", "foreign_git"):
                with self.subTest(workspace_kind=workspace_kind):
                    workspace = root / workspace_kind
                    workspace.mkdir()
                    fake_prompts = workspace / "prompts"
                    fake_prompts.mkdir()
                    (fake_prompts / "draft.md").write_text(
                        "untrusted workspace prompt\n",
                        encoding="utf-8",
                    )
                    foreign_commit = None
                    if workspace_kind == "foreign_git":
                        subprocess.run(
                            ["git", "init", "--quiet"],
                            cwd=workspace,
                            check=True,
                        )
                        subprocess.run(
                            ["git", "config", "user.email", "fixture@example.invalid"],
                            cwd=workspace,
                            check=True,
                        )
                        subprocess.run(
                            ["git", "config", "user.name", "Fixture"],
                            cwd=workspace,
                            check=True,
                        )
                        (workspace / "foreign.txt").write_text(
                            "foreign repository\n",
                            encoding="utf-8",
                        )
                        subprocess.run(
                            ["git", "add", "foreign.txt"],
                            cwd=workspace,
                            check=True,
                        )
                        subprocess.run(
                            ["git", "commit", "--quiet", "-m", "foreign fixture"],
                            cwd=workspace,
                            check=True,
                        )
                        foreign_commit = subprocess.run(
                            ["git", "rev-parse", "HEAD"],
                            cwd=workspace,
                            check=True,
                            capture_output=True,
                            text=True,
                        ).stdout.strip()

                    result = self._run_installed(
                        package_parent=package_parent,
                        workspace=workspace,
                        argv=["--mock", "--max-rounds", "1"],
                    )

                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertFalse((workspace / "config.yaml").exists())
                    project_dir = workspace / "projects" / "example"
                    self.assertEqual(
                        (project_dir / "task.md").read_bytes(),
                        (REPO_ROOT / "projects" / "example" / "task.md").read_bytes(),
                    )
                    run_configs = list((project_dir / "runs").glob("*/run_config.json"))
                    self.assertEqual(len(run_configs), 1)
                    run_config = json.loads(run_configs[0].read_text(encoding="utf-8"))
                    self.assertIsNone(run_config["git"]["commit"])
                    if foreign_commit is not None:
                        self.assertNotEqual(run_config["git"]["commit"], foreign_commit)
                    self.assertEqual(
                        {
                            name: metadata["sha256"]
                            for name, metadata in run_config["prompt_files"].items()
                        },
                        expected_prompt_hashes,
                    )

            self.assertEqual(_tree_hashes(package_parent), package_before)

    def test_installed_seed_never_overwrites_explicit_or_partial_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_parent = self._copy_installed_package(root)

            explicit_workspace = root / "explicit"
            explicit_workspace.mkdir()
            explicit_result = self._run_installed(
                package_parent=package_parent,
                workspace=explicit_workspace,
                argv=["--mock", "--project", "example", "--max-rounds", "1"],
            )
            self.assertEqual(explicit_result.returncode, 2)
            self.assertFalse((explicit_workspace / "projects" / "example").exists())

            partial_workspace = root / "partial"
            partial_project = partial_workspace / "projects" / "example"
            partial_project.mkdir(parents=True)
            marker = partial_project / "keep.txt"
            marker.write_text("keep\n", encoding="utf-8")
            partial_result = self._run_installed(
                package_parent=package_parent,
                workspace=partial_workspace,
                argv=["--mock", "--max-rounds", "1"],
            )
            self.assertEqual(partial_result.returncode, 2)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")
            self.assertFalse((partial_project / "task.md").exists())

            normal_workspace = root / "normal"
            normal_workspace.mkdir()
            normal_result = self._run_installed(
                package_parent=package_parent,
                workspace=normal_workspace,
                argv=[],
            )
            self.assertEqual(normal_result.returncode, 2)
            self.assertEqual(list(normal_workspace.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
