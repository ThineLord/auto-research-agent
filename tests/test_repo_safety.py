from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.check_repo_safety import (
    RepoSafetyError,
    find_findings_in_bytes,
    find_findings_in_text,
    main,
    run_self_tests,
    scan_repository,
)


def _mac_home(account: str) -> str:
    return "/" + "Users" + f"/{account}/workspace/file.txt"


def _linux_home(account: str) -> str:
    return "/" + "home" + f"/{account}/workspace/file.txt"


def _windows_home(account: str) -> str:
    separator = "\\"
    return "C:" + separator + "Users" + separator + account + separator + "workspace"


def _secret_samples() -> dict[str, str]:
    return {
        "google-api-key": "AI" + "za" + "A" * 34 + "-",
        "github-token": "gh" + "p_" + "A" * 36,
        "aws-access-key": "AK" + "IA" + "A" * 16,
        "aws-session-key": "AS" + "IA" + "A" * 16,
        "slack-token": "xo" + "xb-" + "A" * 20,
        "openai-api-key": "s" + "k-" + "A" * 32,
        "private-key": "-----BEGIN " + "PRIVATE KEY-----",
    }


class RepoSafetyTests(unittest.TestCase):
    def test_detects_personal_home_paths_and_high_confidence_secrets(self) -> None:
        text = "\n".join(
            [
                _mac_home("private-account"),
                _linux_home("private-account"),
                _windows_home("private-account"),
                *_secret_samples().values(),
            ]
        )

        findings = find_findings_in_text("tracked.txt", text)

        self.assertEqual(
            {finding.kind for finding in findings},
            {
                "personal-home-path",
                "google-api-key",
                "github-token",
                "aws-access-key",
                "slack-token",
                "openai-api-key",
                "private-key",
            },
        )

    def test_allows_placeholders_and_environment_variable_names(self) -> None:
        text = "\n".join(
            [
                "/Users/<username>/workspace",
                "/home/${USER}/workspace",
                r"C:\Users\<username>\workspace",
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "api_key: ''",
                "token: ${TOKEN}",
            ]
        )

        self.assertEqual(find_findings_in_text("safe.md", text), [])

    def test_repository_scan_reads_only_tracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "tracked.txt").write_text("/Users/<username>/workspace", encoding="utf-8")
            (root / "untracked.txt").write_text(_secret_samples()["github-token"], encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
            (root / "tracked.txt").write_text(_mac_home("tracked-account"), encoding="utf-8")

            worktree_result = scan_repository(root)
            staged_before_add = scan_repository(root, staged=True)
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
            staged_after_add = scan_repository(root, staged=True)

        self.assertEqual(len(worktree_result.findings), 1)
        self.assertEqual(worktree_result.findings[0].path, "tracked.txt")
        self.assertEqual(worktree_result.findings[0].kind, "personal-home-path")
        self.assertEqual(worktree_result.scanned_files, 1)
        self.assertEqual(staged_before_add.findings, [])
        self.assertEqual(len(staged_after_add.findings), 1)
        self.assertEqual(staged_after_add.findings[0].path, "tracked.txt")

    def test_repository_scan_does_not_follow_symlinks_and_scans_binary_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            outside = root / "untracked-target.txt"
            outside.write_text(_mac_home("outside-account"), encoding="utf-8")
            link = root / "tracked-link"
            try:
                os.symlink(outside, link)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {type(exc).__name__}")
            personal_link = root / "personal-link"
            os.symlink(_mac_home("linked-account"), personal_link)
            binary = root / "tracked.bin"
            binary.write_bytes(b"\x00" + _secret_samples()["google-api-key"].encode("ascii"))
            subprocess.run(
                ["git", "add", "tracked-link", "personal-link", "tracked.bin"],
                cwd=root,
                check=True,
            )

            result = scan_repository(root)

        self.assertEqual(
            [(finding.path, finding.kind) for finding in result.findings],
            [
                ("personal-link", "personal-home-path"),
                ("tracked.bin", "google-api-key"),
            ],
        )
        self.assertEqual(result.scanned_files, 3)
        self.assertEqual(result.binary_files_scanned, 1)

    def test_repository_scan_rejects_symlinked_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root = Path(tmp)
            outside = Path(outside_tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            nested = root / "nested"
            nested.mkdir()
            tracked = nested / "tracked.txt"
            tracked.write_text("safe", encoding="utf-8")
            subprocess.run(["git", "add", "nested/tracked.txt"], cwd=root, check=True)
            tracked.unlink()
            nested.rmdir()
            (outside / "tracked.txt").write_text(_mac_home("outside-account"), encoding="utf-8")
            try:
                os.symlink(outside, nested, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks unavailable: {type(exc).__name__}")

            with self.assertRaises(RepoSafetyError):
                scan_repository(root)
            staged_result = scan_repository(root, staged=True)

        self.assertEqual(staged_result.findings, [])
        self.assertEqual(staged_result.scanned_files, 1)

    def test_worktree_scan_fails_closed_without_secure_directory_walk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "tracked.txt").write_text("safe", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)

            with patch(
                "scripts.check_repo_safety._supports_secure_directory_walk",
                return_value=False,
            ):
                with self.assertRaisesRegex(RepoSafetyError, "secure worktree traversal"):
                    scan_repository(root)
                staged_result = scan_repository(root, staged=True)

        self.assertEqual(staged_result.findings, [])
        self.assertEqual(staged_result.scanned_files, 1)

    def test_bytes_scan_detects_secret_after_invalid_utf8_and_nul(self) -> None:
        data = b"\xff\xfe\0" + _secret_samples()["google-api-key"].encode("ascii")

        findings = find_findings_in_bytes("invalid.bin", data)

        self.assertEqual([finding.kind for finding in findings], ["google-api-key"])

    def test_missing_tracked_worktree_file_fails_closed_but_index_remains_scannable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            tracked = root / "tracked.txt"
            tracked.write_text("safe", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
            tracked.unlink()

            with self.assertRaises(RepoSafetyError):
                scan_repository(root)
            staged_result = scan_repository(root, staged=True)

        self.assertEqual(staged_result.findings, [])
        self.assertEqual(staged_result.scanned_files, 1)

    def test_bundled_self_tests_cover_safe_and_unsafe_controls(self) -> None:
        run_self_tests()

    def test_cli_reports_location_and_category_without_echoing_match_or_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            matched_value = _mac_home("private-account")
            (root / "tracked.txt").write_text(matched_value, encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
            stderr = StringIO()

            with redirect_stderr(stderr):
                exit_code = main(["--repo-root", str(root)])

        output = stderr.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("tracked.txt:1: personal-home-path", output)
        self.assertNotIn(matched_value, output)
        self.assertNotIn(str(root), output)

    def test_cli_operational_error_is_generic_and_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stderr = StringIO()

            with redirect_stderr(stderr):
                exit_code = main(["--repo-root", tmp])

        output = stderr.getvalue()
        self.assertEqual(exit_code, 2)
        self.assertIn("unable to enumerate tracked files", output)
        self.assertNotIn(tmp, output)


if __name__ == "__main__":
    unittest.main()
