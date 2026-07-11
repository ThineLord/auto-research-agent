from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rich.console import Console

import src.cli as cli_module
import src.project_input as project_input_module
from src.agents import ResearchAgents
from src.config import AppConfig
from src.project_input import ProjectInputError, load_project_input


class CapturingLLM:
    timeout_seconds = 300
    max_prompt_chars = 12000

    def __init__(self) -> None:
        self.user_prompts: list[str] = []

    def generate(
        self,
        *,
        agent_name: str = "unknown",
        system_prompt: str | None,
        user_prompt: str,
        temperature: float = 0.4,
        top_p: float = 0.9,
        response_format: dict[str, object] | None = None,
    ) -> str:
        self.user_prompts.append(user_prompt)
        return "ok"


class ProjectInputTests(unittest.TestCase):
    def test_explicit_user_project_task_enters_draft_prompt_without_example_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / "projects" / "example"
            user_project = root / "projects" / "nebula_unique_task"
            example.mkdir(parents=True)
            user_project.mkdir(parents=True)
            (example / "task.md").write_text(
                "# Example bundled task\n\nSAMPLE_EXAMPLE_SENTINEL\n",
                encoding="utf-8",
            )
            unique_text = (
                "# Nebula Constraint Solver\n\n"
                "USER_PROJECT_SENTINEL_93F4C2 must appear in the draft prompt.\n"
            )
            (user_project / "task.md").write_text(unique_text, encoding="utf-8")

            project_input = load_project_input(
                root=root,
                project_name="nebula_unique_task",
                explicit_project=True,
            )
            llm = CapturingLLM()
            agents = ResearchAgents(
                llm=llm,
                draft_prompt="draft",
                review_prompt="review",
                revise_prompt="revise",
                judge_prompt="judge",
                temperature=0.1,
                top_p=0.9,
            )

            agents.draft(
                task=project_input.task_text,
                memory="",
                round_index=1,
                previous_best="",
                previous_judge="",
            )

            self.assertEqual(project_input.source_kind, "user_provided")
            self.assertIn("USER_PROJECT_SENTINEL_93F4C2", llm.user_prompts[0])
            self.assertNotIn("SAMPLE_EXAMPLE_SENTINEL", llm.user_prompts[0])

    def test_missing_explicit_project_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            example = root / "projects" / "example"
            example.mkdir(parents=True)
            (example / "task.md").write_text("# Example\n", encoding="utf-8")

            with self.assertRaisesRegex(ProjectInputError, "Project 'missing_project'"):
                load_project_input(
                    root=root,
                    project_name="missing_project",
                    explicit_project=True,
                )

    def test_missing_project_error_masks_repo_root_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "projects" / "example").mkdir(parents=True)
            (root / "projects" / "example" / "task.md").write_text("# Example\n", encoding="utf-8")

            with self.assertRaises(ProjectInputError) as context:
                load_project_input(
                    root=root,
                    project_name="missing_project",
                    explicit_project=True,
                )

            message = str(context.exception)
            self.assertIn("projects/missing_project", message)
            self.assertNotIn(str(root.resolve()), message)

    def test_rejects_non_utf8_project_task_without_leaking_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "private"
            project_dir.mkdir(parents=True)
            (project_dir / "task.md").write_bytes(b"\xff\xfe")

            with self.assertRaises(ProjectInputError) as raised:
                load_project_input(
                    root=root,
                    project_name="private",
                    explicit_project=True,
                )

            self.assertIn("Task file must be valid UTF-8 text", str(raised.exception))
            self.assertIn("projects/private/task.md", str(raised.exception))
            self.assertNotIn(str(root.resolve()), str(raised.exception))

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_rejects_symlinked_project_and_task_without_reading_external_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            projects.mkdir()

            outside_project = root / "outside-project"
            outside_project.mkdir()
            (outside_project / "task.md").write_text(
                "# PRIVATE_PROJECT_SENTINEL\n",
                encoding="utf-8",
            )
            (projects / "linked-project").symlink_to(
                outside_project,
                target_is_directory=True,
            )
            with self.assertRaisesRegex(ProjectInputError, "unsafe project path") as project_error:
                load_project_input(
                    root=root,
                    project_name="linked-project",
                    explicit_project=True,
                )
            self.assertNotIn("PRIVATE_PROJECT_SENTINEL", str(project_error.exception))
            self.assertNotIn(str(root.resolve()), str(project_error.exception))

            direct_project = projects / "direct-project"
            direct_project.mkdir()
            external_task = root / "external-task.md"
            external_task.write_text("# PRIVATE_TASK_SENTINEL\n", encoding="utf-8")
            (direct_project / "task.md").symlink_to(external_task)
            with self.assertRaisesRegex(ProjectInputError, "unsafe task path") as task_error:
                load_project_input(
                    root=root,
                    project_name="direct-project",
                    explicit_project=True,
                )
            self.assertNotIn("PRIVATE_TASK_SENTINEL", str(task_error.exception))
            self.assertNotIn(str(root.resolve()), str(task_error.exception))

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_rejects_projects_ancestor_swap_before_task_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            project = projects / "selected"
            outside_projects = root / "outside-projects"
            outside_project = outside_projects / "selected"
            project.mkdir(parents=True)
            outside_project.mkdir(parents=True)
            (project / "task.md").write_text("# SAFE_TASK\n", encoding="utf-8")
            (outside_project / "task.md").write_text(
                "# PRIVATE_EXTERNAL_TASK\n",
                encoding="utf-8",
            )
            original_read = project_input_module.read_regular_text

            def swap_then_read(path: Path, **kwargs: object) -> str:
                projects.rename(root / "original-projects")
                projects.symlink_to(outside_projects, target_is_directory=True)
                return original_read(path, **kwargs)

            with (
                patch.object(
                    project_input_module,
                    "read_regular_text",
                    side_effect=swap_then_read,
                ),
                self.assertRaisesRegex(ProjectInputError, "unsafe task path") as raised,
            ):
                load_project_input(
                    root=root,
                    project_name="selected",
                    explicit_project=True,
                )

            self.assertNotIn("PRIVATE_EXTERNAL_TASK", str(raised.exception))

    def test_cli_project_input_error_masks_repo_root_path(self) -> None:
        args = SimpleNamespace(
            session=False,
            diagnostic=False,
            continuous=False,
            resume=False,
            survey=False,
            survey_output=None,
            mock=True,
            compare_runs=None,
            compare_output=None,
            analyze_run=None,
            analyze_output=None,
            model=None,
            provider=None,
            gemini_api_key_env=None,
            project="missing_project_for_test",
            cloud_free_discover=False,
            cloud_free_profile=False,
            free_runner_preset=None,
            disable_cloud_free_mode=False,
            min_delay_seconds=None,
            max_delay_seconds=None,
            max_retries=None,
            prompt_budget_chars=None,
            max_prompt_chars=None,
            max_rounds=None,
            drafting_mode=None,
            benchmark_preset=None,
            max_provider_quota_failures=2,
        )
        console = Console(record=True, width=120)
        repo_root = Path(cli_module.__file__).resolve().parent.parent

        with (
            patch.object(cli_module, "parse_args", return_value=args),
            patch.object(cli_module, "Console", return_value=console),
            patch.object(cli_module, "load_app_config", return_value=AppConfig()),
        ):
            with self.assertRaises(SystemExit) as raised:
                cli_module.main()

        self.assertEqual(raised.exception.code, 2)
        output = console.export_text(styles=False)
        self.assertIn("projects/missing_project_for_test", output)
        self.assertNotIn(str(repo_root), output)

    def test_cli_project_input_error_happens_before_ollama_model_discovery(self) -> None:
        args = SimpleNamespace(
            session=False,
            diagnostic=False,
            continuous=False,
            resume=False,
            model=None,
            provider=None,
            gemini_api_key_env=None,
            project="missing_project",
            cloud_free_discover=False,
            cloud_free_profile=False,
            free_runner_preset=None,
            disable_cloud_free_mode=False,
            min_delay_seconds=None,
            max_delay_seconds=None,
            max_retries=None,
            prompt_budget_chars=None,
            max_prompt_chars=None,
        )

        with (
            patch.object(cli_module, "parse_args", return_value=args),
            patch.object(cli_module, "load_app_config", return_value=AppConfig()),
            patch.object(
                cli_module,
                "load_project_input",
                side_effect=ProjectInputError("Project 'missing_project' was not found"),
            ),
            patch.object(cli_module, "list_installed_ollama_models") as list_models,
        ):
            with self.assertRaises(SystemExit) as raised:
                cli_module.main()

        self.assertEqual(raised.exception.code, 2)
        list_models.assert_not_called()


if __name__ == "__main__":
    unittest.main()
