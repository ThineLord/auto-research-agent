from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_release import markdown_link_errors, release_errors


class ReleaseCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        files = {
            "pyproject.toml": '[project]\nname = "example"\nversion = "0.2.0"\n',
            "README.md": "Current version: **0.2.0**\n",
            "README.zh-CN.md": "当前版本：**0.2.0**\n",
            "CHANGELOG.md": "## [0.2.0] - 2026-11-09\n",
            "docs/releases/0.2.0.md": "# Auto Research Agent 0.2.0\n",
            "docs/releases/0.2.0.zh-CN.md": "# Auto Research Agent 0.2.0\n",
        }
        for name, content in files.items():
            self.write(name, content)

    def write(self, name: str, content: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_matching_version_and_tag_pass(self) -> None:
        self.assertEqual(release_errors(self.root, "v0.2.0"), [])

    def test_stale_readme_and_wrong_tag_fail(self) -> None:
        self.write("README.md", "Current version: **0.1.0**\n")
        errors = release_errors(self.root, "v0.1.0")
        self.assertEqual(len(errors), 2)

    def test_missing_translation_fails(self) -> None:
        (self.root / "docs/releases/0.2.0.zh-CN.md").unlink()
        self.assertIn("missing required", release_errors(self.root)[0])

    def test_version_must_come_from_project_table(self) -> None:
        self.write("pyproject.toml", '[tool.example]\nversion = "0.2.0"\n')
        self.assertIn("project version", release_errors(self.root)[0])

    def test_links_resolve_relative_to_document_and_ignore_code_urls_anchors(self) -> None:
        self.write(
            "docs/guide.md",
            "[Home](../README.md) [Top](#start) [Web](https://example.com)\n"
            "```text\n[Example](missing.md)\n```\n",
        )
        self.assertEqual(markdown_link_errors(self.root, ["README.md", "docs/guide.md"]), [])

    def test_local_untracked_file_cannot_satisfy_public_link(self) -> None:
        self.write("README.md", "[Private file](private.md)\n")
        self.write("private.md", "local data\n")
        self.assertIn("missing tracked", markdown_link_errors(self.root, ["README.md"])[0])

    def test_missing_and_escaping_links_fail(self) -> None:
        self.write("README.md", "[Missing](gone.md) [Outside](../outside.md)\n")
        self.assertEqual(len(markdown_link_errors(self.root, ["README.md"])), 2)


if __name__ == "__main__":
    unittest.main()
