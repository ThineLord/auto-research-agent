from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_wheel_install

REPO_ROOT = Path(__file__).resolve().parents[1]


class WheelInstallSmokeSafetyTests(unittest.TestCase):
    def test_source_git_environment_drops_external_redirects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            injected = {
                "GIT_CONFIG_GLOBAL": "/outside/gitconfig",
                "GIT_DIR": "/outside/repository",
                "GIT_INDEX_FILE": "/outside/index",
                "GIT_OBJECT_DIRECTORY": "/outside/objects",
                "GIT_WORK_TREE": "/outside/worktree",
                "PATH": os.environ.get("PATH", ""),
            }

            with patch.dict(os.environ, injected, clear=True):
                env = check_wheel_install._isolated_git_environment(root / "home")

            self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
            self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
            self.assertEqual(env["GIT_OPTIONAL_LOCKS"], "0")
            for name in (
                "GIT_DIR",
                "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_WORK_TREE",
            ):
                with self.subTest(name=name):
                    self.assertNotIn(name, env)

    def test_pip_environment_ignores_external_install_redirects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            injected = {
                "GOOGLE_API_KEY": "provider-secret",
                "HTTP_PROXY": "http://proxy.example.invalid",
                "PATH": os.environ.get("PATH", ""),
                "PIP_CONFIG_FILE": "/outside/pip.conf",
                "PIP_PREFIX": "/outside/prefix",
                "PIP_TARGET": "/outside/target",
                "PIP_USER": "1",
                "PYTHONPATH": "/outside/source",
                "PYTHONUSERBASE": "/outside/userbase",
            }

            with patch.dict(os.environ, injected, clear=True):
                env = check_wheel_install._pip_environment(root)

            self.assertEqual(env["HTTP_PROXY"], injected["HTTP_PROXY"])
            self.assertEqual(env["PIP_CONFIG_FILE"], os.devnull)
            self.assertEqual(env["PIP_NO_CACHE_DIR"], "1")
            self.assertTrue(Path(env["HOME"]).is_relative_to(root))
            self.assertTrue(Path(env["TMPDIR"]).is_relative_to(root))
            for name in (
                "GOOGLE_API_KEY",
                "PIP_PREFIX",
                "PIP_TARGET",
                "PIP_USER",
                "PYTHONPATH",
                "PYTHONUSERBASE",
            ):
                with self.subTest(name=name):
                    self.assertNotIn(name, env)

    def test_runtime_environment_drops_git_redirects_and_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            injected = {
                "CUSTOM_PROVIDER_TOKEN": "provider-secret",
                "GIT_CONFIG_GLOBAL": "/outside/gitconfig",
                "GIT_DIR": "/outside/repository",
                "GIT_INDEX_FILE": "/outside/index",
                "GIT_WORK_TREE": "/outside/worktree",
                "GOOGLE_APPLICATION_CREDENTIALS": "/outside/credentials.json",
                "PATH": os.environ.get("PATH", ""),
                "http_proxy": "http://live-proxy.example.invalid",
            }

            with patch.dict(os.environ, injected, clear=True):
                env = check_wheel_install._runtime_environment(root / "venv", root / "home")

            self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
            self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
            self.assertEqual(env["HTTP_PROXY"], "http://127.0.0.1:9")
            self.assertEqual(env["http_proxy"], "http://127.0.0.1:9")
            self.assertEqual(env["NO_PROXY"], "")
            self.assertEqual(env["no_proxy"], "")
            for name in (
                "CUSTOM_PROVIDER_TOKEN",
                "GIT_DIR",
                "GIT_INDEX_FILE",
                "GIT_WORK_TREE",
                "GOOGLE_APPLICATION_CREDENTIALS",
            ):
                with self.subTest(name=name):
                    self.assertNotIn(name, env)

    def test_temp_configuration_inside_checkout_fails_before_creation(self) -> None:
        unsafe_temp = REPO_ROOT / ".unsafe-wheel-smoke-temp"
        self.assertFalse(unsafe_temp.exists())

        with patch.dict(os.environ, {"TMPDIR": str(unsafe_temp)}, clear=True):
            with self.assertRaisesRegex(
                check_wheel_install.WheelSmokeError,
                "inside the checkout",
            ):
                check_wheel_install._safe_temp_base()

        self.assertFalse(unsafe_temp.exists())

    def test_subprocess_failure_does_not_echo_child_output(self) -> None:
        secret_output = "https://user:secret@example.invalid/private"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(check_wheel_install.WheelSmokeError) as raised:
                check_wheel_install._run(
                    [sys.executable, "-c", f"print({secret_output!r}); raise SystemExit(3)"],
                    cwd=Path(tmp),
                    env={},
                    timeout=5,
                    label="fixture command",
                    deadline=time.monotonic() + 5,
                )

        message = str(raised.exception)
        self.assertEqual(message, "fixture command failed with status 3")
        self.assertNotIn(secret_output, message)


if __name__ == "__main__":
    unittest.main()
