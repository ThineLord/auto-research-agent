from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.resume import run_resume_mode
from src.storage import write_json_file
from tests.helpers import NullConsole, make_project_fixture


class ResumeModeTests(unittest.TestCase):
    def test_resume_mode_continues_from_checkpoint_round_and_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = make_project_fixture(Path(tmp))
            run_root = fixture.project_dir / "runs" / "existing-run"
            run_root.mkdir(parents=True)
            write_json_file(
                fixture.project_dir / "checkpoint.json",
                {
                    "can_resume": True,
                    "run_root": str(run_root),
                    "last_completed_round": 2,
                    "best_score": 72.5,
                },
            )

            with patch("src.resume.run_iterative_rounds") as run_rounds:
                run_resume_mode(
                    console=NullConsole(),
                    agents=object(),
                    task_text="Resume this project.",
                    project_dir=fixture.project_dir,
                    memory_path=fixture.memory_path,
                    model_name="fake-model",
                    max_rounds=2,
                    stop_if_no_improvement_rounds=4,
                    global_max_runtime_seconds=60,
                    per_agent_timeout_seconds=300,
                )

            run_rounds.assert_called_once()
            kwargs = run_rounds.call_args.kwargs
            self.assertEqual(kwargs["mode"], "resume")
            self.assertEqual(kwargs["start_round"], 3)
            self.assertEqual(kwargs["max_rounds"], 3)
            self.assertEqual(kwargs["run_root_override"], run_root)
            self.assertEqual(kwargs["initial_best_score"], 72.5)

    def test_resume_mode_rejects_invalid_checkpoints_without_running(self) -> None:
        invalid_checkpoints = [
            {},
            {"can_resume": False, "run_root": "unused"},
            {"can_resume": True, "run_root": ""},
            {"can_resume": True, "run_root": "/path/that/does/not/exist"},
        ]

        for checkpoint in invalid_checkpoints:
            with self.subTest(checkpoint=checkpoint):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = make_project_fixture(Path(tmp))
                    if checkpoint:
                        write_json_file(fixture.project_dir / "checkpoint.json", checkpoint)
                    console = NullConsole()

                    with patch("src.resume.run_iterative_rounds") as run_rounds:
                        run_resume_mode(
                            console=console,
                            agents=object(),
                            task_text="Resume this project.",
                            project_dir=fixture.project_dir,
                            memory_path=fixture.memory_path,
                            model_name="fake-model",
                            max_rounds=5,
                            stop_if_no_improvement_rounds=4,
                            global_max_runtime_seconds=60,
                            per_agent_timeout_seconds=300,
                        )

                    run_rounds.assert_not_called()
                    self.assertTrue(any("Cannot resume" in message for message in console.messages))


if __name__ == "__main__":
    unittest.main()
