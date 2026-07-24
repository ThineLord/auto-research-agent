from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PytestSubtestExitTests(unittest.TestCase):
    def _run_sentinel(self, source: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sentinel = root / "test_subtest_sentinel.py"
            sentinel.write_text(textwrap.dedent(source), encoding="utf-8")
            env = os.environ.copy()
            env.pop("PYTEST_ADDOPTS", None)
            env.pop("PYTEST_PLUGINS", None)
            env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            return subprocess.run(
                [sys.executable, "-m", "pytest", "-q", str(sentinel)],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

    def test_subtest_only_failure_returns_tests_failed_status(self) -> None:
        result = self._run_sentinel(
            """
            import unittest


            class FailingSubtestSentinel(unittest.TestCase):
                def test_subtest_only_failure(self) -> None:
                    with getattr(self, "subTest")(case="only"):
                        self.assertEqual(1, 2)
            """
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("SUBFAILED", result.stdout)
        self.assertIn("1 failed", result.stdout)

    def test_passing_subtests_return_success(self) -> None:
        result = self._run_sentinel(
            """
            import unittest


            class PassingSubtestSentinel(unittest.TestCase):
                def test_passing_subtests(self) -> None:
                    for case in range(2):
                        with getattr(self, "subTest")(case=case):
                            self.assertGreaterEqual(case, 0)
            """
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("SUBFAILED", result.stdout)
        self.assertIn("1 passed", result.stdout)
