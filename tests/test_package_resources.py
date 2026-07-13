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

    def test_installed_conflicting_primary_modes_fail_before_workspace_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_parent = self._copy_installed_package(root)
            package_before = _tree_hashes(package_parent)
            workspace = root / "workspace"
            workspace.mkdir()

            result = self._run_installed(
                package_parent=package_parent,
                workspace=workspace,
                argv=["--mock", "--resume"],
            )
            combined = result.stdout + result.stderr

            self.assertEqual(result.returncode, 2, combined)
            self.assertIn("not allowed with argument", result.stderr)
            self.assertNotIn("Traceback", combined)
            self.assertEqual(list(workspace.iterdir()), [])
            self.assertEqual(_tree_hashes(package_parent), package_before)

    def test_installed_generation_modes_reject_missing_prompt_before_workspace_writes(
        self,
    ) -> None:
        modes = (
            ("normal", []),
            ("mock", ["--mock", "--max-rounds", "1"]),
            ("continuous", ["--continuous"]),
            ("diagnostic", ["--diagnostic"]),
            ("session", ["--session"]),
            ("resume", ["--resume"]),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_parent = self._copy_installed_package(root)
            package_before = _tree_hashes(package_parent)
            prompt_path = package_parent / "src" / "_bundled" / "prompts" / "judge.md"
            prompt_bytes = prompt_path.read_bytes()
            prompt_path.unlink()
            package_without_prompt = _tree_hashes(package_parent)
            try:
                for mode_name, argv in modes:
                    with self.subTest(mode=mode_name):
                        workspace = root / f"workspace-{mode_name}"
                        workspace.mkdir()
                        result = self._run_installed(
                            package_parent=package_parent,
                            workspace=workspace,
                            argv=argv,
                        )
                        combined = result.stdout + result.stderr

                        self.assertEqual(result.returncode, 2, combined)
                        self.assertIn("Package resource error", combined)
                        self.assertNotIn("Config error", combined)
                        self.assertNotIn("Traceback", combined)
                        self.assertNotIn(str(package_parent), combined)
                        self.assertEqual(list(workspace.iterdir()), [])
                        self.assertEqual(_tree_hashes(package_parent), package_without_prompt)
            finally:
                prompt_path.write_bytes(prompt_bytes)

            self.assertEqual(_tree_hashes(package_parent), package_before)

    def test_installed_prompt_preflight_rejects_each_invalid_resource_kind(
        self,
    ) -> None:
        cases = (
            ("missing-draft", "draft.md", "missing"),
            ("symlink-review", "review.md", "symlink"),
            ("whitespace-revise", "revise.md", "whitespace"),
            ("invalid-utf8-judge", "judge.md", "invalid_utf8"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_parent = self._copy_installed_package(root)
            package_before = _tree_hashes(package_parent)
            prompts_dir = package_parent / "src" / "_bundled" / "prompts"

            for case_name, prompt_name, mutation in cases:
                with self.subTest(case=case_name):
                    prompt_path = prompts_dir / prompt_name
                    original_bytes = prompt_path.read_bytes()
                    workspace = root / f"workspace-{case_name}"
                    workspace.mkdir()
                    try:
                        if mutation == "missing":
                            prompt_path.unlink()
                        elif mutation == "symlink":
                            prompt_path.unlink()
                            prompt_path.symlink_to("draft.md")
                        elif mutation == "whitespace":
                            prompt_path.write_bytes(b" \t\n")
                        elif mutation == "invalid_utf8":
                            prompt_path.write_bytes(b"\xff\xfe")
                        else:  # pragma: no cover - fixture contract.
                            raise AssertionError(f"unsupported mutation: {mutation}")

                        mutated_hashes = _tree_hashes(package_parent)
                        mutated_is_symlink = prompt_path.is_symlink()
                        result = self._run_installed(
                            package_parent=package_parent,
                            workspace=workspace,
                            argv=["--mock", "--max-rounds", "1"],
                        )
                        combined = result.stdout + result.stderr

                        self.assertEqual(result.returncode, 2, combined)
                        self.assertIn("Package resource error", combined)
                        self.assertNotIn("Traceback", combined)
                        self.assertNotIn(str(package_parent), combined)
                        self.assertEqual(list(workspace.iterdir()), [])
                        self.assertEqual(prompt_path.is_symlink(), mutated_is_symlink)
                        self.assertEqual(_tree_hashes(package_parent), mutated_hashes)
                    finally:
                        if prompt_path.is_symlink() or prompt_path.exists():
                            prompt_path.unlink()
                        prompt_path.write_bytes(original_bytes)

            self.assertEqual(_tree_hashes(package_parent), package_before)

    @unittest.skipUnless(hasattr(os, "link"), "hard links are unavailable")
    def test_installed_prompt_preflight_accepts_regular_hardlinked_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_parent = self._copy_installed_package(root)
            package_before = _tree_hashes(package_parent)
            prompt_path = package_parent / "src" / "_bundled" / "prompts" / "judge.md"
            prompt_bytes = prompt_path.read_bytes()
            hardlink_source = root / "hardlinked-judge.md"
            workspace = root / "workspace"
            workspace.mkdir()
            prompt_path.unlink()
            hardlink_source.write_bytes(prompt_bytes)
            os.link(hardlink_source, prompt_path)
            try:
                self.assertGreater(prompt_path.stat().st_nlink, 1)
                result = self._run_installed(
                    package_parent=package_parent,
                    workspace=workspace,
                    argv=["--mock", "--max-rounds", "1"],
                )
                combined = result.stdout + result.stderr

                self.assertEqual(result.returncode, 0, combined)
                self.assertNotIn("Package resource error", combined)
                self.assertNotIn("Traceback", combined)
                self.assertTrue((workspace / "projects" / "example" / "task.md").is_file())
                self.assertEqual(_tree_hashes(package_parent), package_before)
            finally:
                prompt_path.unlink()
                hardlink_source.unlink()
                prompt_path.write_bytes(prompt_bytes)

            self.assertEqual(_tree_hashes(package_parent), package_before)

    def test_installed_analysis_and_comparison_bypass_prompt_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_parent = self._copy_installed_package(root)
            package_before = _tree_hashes(package_parent)
            prompt_path = package_parent / "src" / "_bundled" / "prompts" / "judge.md"
            prompt_bytes = prompt_path.read_bytes()
            prompt_path.unlink()
            package_without_prompt = _tree_hashes(package_parent)
            workspace = root / "workspace"
            run_a = workspace / "run-a"
            run_b = workspace / "run-b"
            run_a.mkdir(parents=True)
            run_b.mkdir()
            workspace_before = sorted(
                path.relative_to(workspace).as_posix() for path in workspace.rglob("*")
            )
            try:
                commands = (
                    ("analyze", ["--analyze-run", str(run_a)]),
                    ("compare", ["--compare-runs", str(run_a), str(run_b)]),
                )
                for command_name, argv in commands:
                    with self.subTest(command=command_name):
                        result = self._run_installed(
                            package_parent=package_parent,
                            workspace=workspace,
                            argv=argv,
                        )
                        combined = result.stdout + result.stderr

                        self.assertEqual(result.returncode, 0, combined)
                        self.assertNotIn("Package resource error", combined)
                        self.assertNotIn("Traceback", combined)
                        self.assertFalse((workspace / "projects").exists())
                        self.assertEqual(
                            sorted(
                                path.relative_to(workspace).as_posix()
                                for path in workspace.rglob("*")
                            ),
                            workspace_before,
                        )
                        self.assertEqual(_tree_hashes(package_parent), package_without_prompt)
            finally:
                prompt_path.write_bytes(prompt_bytes)

            self.assertEqual(_tree_hashes(package_parent), package_before)

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
