from __future__ import annotations

import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


class CIWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = yaml.load(CI_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        cls.test_job = cls.workflow["jobs"]["test"]

    def test_token_permissions_are_explicitly_read_only(self) -> None:
        self.assertEqual(self.workflow.get("permissions"), {"contents": "read"})
        self.assertNotIn("permissions", self.test_job)

    def test_job_timeout_is_bounded_with_install_headroom(self) -> None:
        timeout_minutes = int(self.test_job["timeout-minutes"])

        self.assertGreaterEqual(timeout_minutes, 5)
        self.assertLessEqual(timeout_minutes, 30)

    def test_supported_events_branches_and_python_matrix_are_preserved(self) -> None:
        triggers = self.workflow["on"]

        self.assertEqual(triggers["push"]["branches"], ["master", "codex/**"])
        self.assertEqual(triggers["pull_request"]["branches"], ["master"])
        self.assertEqual(
            self.test_job["strategy"]["matrix"]["python-version"],
            ["3.10", "3.13"],
        )

    def test_javascript_actions_use_supported_node24_majors(self) -> None:
        actions_by_name = {
            step["name"]: step["uses"] for step in self.test_job["steps"] if "uses" in step
        }

        self.assertEqual(actions_by_name["Check out repository"], "actions/checkout@v7")
        self.assertEqual(actions_by_name["Set up Python"], "actions/setup-python@v6")

    def test_python_matrix_builds_and_smoke_tests_one_isolated_wheel(self) -> None:
        steps = self.test_job["steps"]
        smoke_steps = [
            step for step in steps if step.get("name") == "Build and smoke-test isolated wheel"
        ]

        self.assertEqual(len(smoke_steps), 1)
        self.assertEqual(smoke_steps[0].get("run"), "python scripts/check_wheel_install.py")
        install_index = next(
            index
            for index, step in enumerate(steps)
            if step.get("name") == "Install project with development tools"
        )
        self.assertGreater(steps.index(smoke_steps[0]), install_index)


if __name__ == "__main__":
    unittest.main()
