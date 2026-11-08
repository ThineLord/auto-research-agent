#!/usr/bin/env python3
"""Check local release metadata and tracked Markdown file links without network calls."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"


def release_errors(root: Path, tag: str | None = None) -> list[str]:
    errors = []
    metadata = (root / "pyproject.toml").read_text(encoding="utf-8")
    project = re.search(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)", metadata)
    match = re.search(rf'^version = "({VERSION})"$', project[1] if project else "", re.M)
    if not match:
        return ["pyproject.toml: expected a stable MAJOR.MINOR.PATCH project version"]
    version = match[1]
    if tag is not None and tag != f"v{version}":
        errors.append(f"tag {tag!r} does not match package version v{version}")
    required = {
        "README.md": f"Current version: **{version}**",
        "README.zh-CN.md": f"当前版本：**{version}**",
        "CHANGELOG.md": f"## [{version}] - ",
        f"docs/releases/{version}.md": f"# Auto Research Agent {version}\n",
        f"docs/releases/{version}.zh-CN.md": f"# Auto Research Agent {version}\n",
    }
    for name, marker in required.items():
        path = root / name
        if not path.is_file():
            errors.append(f"{name}: missing required release document")
        elif marker not in path.read_text(encoding="utf-8"):
            errors.append(f"{name}: missing expected version marker for {version}")
    return errors


def markdown_link_errors(root: Path, tracked: list[str]) -> list[str]:
    """Validate inline relative file destinations; skip URLs, anchors, and historical records.

    This is deliberately a file-link check, not a full Markdown parser or anchor validator.
    Only tracked destinations count, so an ignored local file cannot hide a broken public link.
    """
    errors = []
    root = root.resolve()
    tracked_set = set(tracked)
    for name in tracked:
        if not name.endswith(".md") or name.startswith("docs/archive/"):
            continue
        path = root / name
        if not path.is_file():
            errors.append(f"{name}: tracked Markdown file is missing")
            continue
        content = re.sub(r"(?ms)^```.*?^```[^\n]*$", "", path.read_text(encoding="utf-8"))
        for match in re.finditer(r"\[[^\]\n]*\]\(([^)\n]+)\)", content):
            destination = match[1].strip()
            if destination.startswith("<"):
                destination = destination.split(">", 1)[0][1:]
            else:
                destination = destination.split()[0]
            parsed = urlsplit(destination)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (path.parent / unquote(parsed.path)).resolve()
            try:
                relative = target.relative_to(root).as_posix()
            except ValueError:
                errors.append(f"{name}: relative link leaves repository: {destination}")
                continue
            tracked_target = relative in tracked_set or any(
                item.startswith(relative + "/") for item in tracked_set
            )
            if not target.exists() or not tracked_target:
                errors.append(f"{name}: missing tracked link target: {destination}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Expected release tag, for example v0.2.0")
    args = parser.parse_args()
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=REPO_ROOT, text=True).split(
        "\0"
    )
    errors = release_errors(REPO_ROOT, args.tag) + markdown_link_errors(
        REPO_ROOT, [name for name in tracked if name]
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Release metadata and tracked Markdown file links passed (no network/provider calls).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
