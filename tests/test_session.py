from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

import src.session as session_module


class FakeSessionLLM:
    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        if "research planner" in system_prompt:
            return "Review stale session artifacts"
        if "technical planning" in system_prompt:
            return "## Main Objective\n- Review stale session artifacts"
        return "# Final Session Report\n\nTomorrow: continue."


class SessionModeTests(unittest.TestCase):
    def test_session_mode_tolerates_stale_research_state_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("memory", encoding="utf-8")
            (project_dir / "research_state.json").mkdir()
            captured: dict[str, object] = {}

            def fake_report(**kwargs: object) -> str:
                captured["research_state"] = kwargs["research_state"]
                return "# Final Session Report\n\nTomorrow: continue."

            with (
                patch.object(
                    session_module,
                    "run_iterative_rounds",
                    return_value={"best_output": "best", "last_revised_output": ""},
                ),
                patch.object(
                    session_module,
                    "generate_final_session_report",
                    side_effect=fake_report,
                ),
            ):
                session_module.run_session_mode(
                    console=Console(file=io.StringIO(), force_terminal=False),
                    llm=FakeSessionLLM(),
                    agents=object(),
                    task_text="task",
                    project_dir=project_dir,
                    memory_path=memory_path,
                    model_name="mock-model",
                    max_rounds=1,
                    stop_if_no_improvement_rounds=1,
                    global_max_runtime_seconds=60,
                    per_agent_timeout_seconds=60,
                    repo_root=project_dir,
                )

            self.assertEqual(captured["research_state"], {})


if __name__ == "__main__":
    unittest.main()
