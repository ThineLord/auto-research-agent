from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import src.cli as cli_module
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
            cli_module.main()

        list_models.assert_not_called()


if __name__ == "__main__":
    unittest.main()
