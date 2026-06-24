from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rich.console import Console

from src.diagnostic import run_diagnostic_mode


class FakeDiagnosticLLM:
    timeout_seconds = 300
    max_prompt_chars = 12000

    def generate(
        self,
        *,
        agent_name: str = "unknown",
        system_prompt: str | None = None,
        user_prompt: str = "",
        temperature: float = 0.4,
        top_p: float = 0.9,
        response_format: dict[str, object] | None = None,
    ) -> str:
        if agent_name == "judge":
            return json.dumps(
                {
                    "score": 81,
                    "rubric": {
                        "evaluation_design_quality": 12,
                        "tomorrow_actionability": 13,
                    },
                    "reasons": ["provider-free diagnostic fixture"],
                    "blockers": [],
                    "next_step": "STOP",
                }
            )
        return f"{agent_name} output"


class DiagnosticTests(unittest.TestCase):
    def test_diagnostic_artifacts_include_resume_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "demo"
            project_dir.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("memory", encoding="utf-8")

            run_diagnostic_mode(
                console=Console(),
                llm=FakeDiagnosticLLM(),
                task_text="diagnostic task",
                project_dir=project_dir,
                memory_path=memory_path,
                model_name="fake-model",
                model_provider="ollama",
            )

            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            run_root = Path(checkpoint["run_root"])
            run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
            run_summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))

        for artifact in (checkpoint, run_config, run_summary):
            resume_metadata = artifact["resume_metadata"]
            self.assertEqual(resume_metadata["lifecycle_action"], "start_new_run")
            self.assertFalse(resume_metadata["resume_from_checkpoint"])
            self.assertFalse(resume_metadata["can_resume"])
            self.assertEqual(resume_metadata["last_completed_round"], 1)
            self.assertIsNone(resume_metadata["next_round"])

    def test_diagnostic_masks_paths_in_console_and_run_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "projects" / "demo"
            project_dir.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("memory", encoding="utf-8")
            metadata = {
                "project_name": "demo",
                "project_dir": str(project_dir),
                "task_path": str(project_dir / "task.md"),
                "project_title": "Demo",
                "source_kind": "user_provided",
            }
            console = Console(record=True, width=200)

            run_diagnostic_mode(
                console=console,
                llm=FakeDiagnosticLLM(),
                task_text="diagnostic task",
                project_dir=project_dir,
                memory_path=memory_path,
                model_name="fake-model",
                model_provider="ollama",
                project_metadata=metadata,
                repo_root=repo_root,
            )

            output = console.export_text(styles=False)
            run_log = (project_dir / "run.log").read_text(encoding="utf-8")
            self.assertIn("Saved diagnostic round outputs: projects/demo/runs/", output)
            self.assertIn("Run root: projects/demo/runs/", output)
            self.assertIn("project_dir=projects/demo", run_log)
            self.assertIn("task_path=projects/demo/task.md", run_log)
            self.assertNotIn(str(project_dir), output)
            self.assertNotIn(str(project_dir), run_log)


if __name__ == "__main__":
    unittest.main()
