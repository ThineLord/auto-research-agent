#!/usr/bin/env python3
"""Fail when tracked files contain personal home paths or high-confidence secrets."""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class RepoSafetyError(RuntimeError):
    """Raised when the tracked-file scan cannot be completed safely."""


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str


@dataclass(frozen=True)
class ScanResult:
    findings: list[Finding]
    scanned_files: int
    binary_files_scanned: int
    skipped_gitlinks: int


@dataclass(frozen=True)
class TrackedEntry:
    path: str
    mode: str
    object_id: str


_POSIX_HOME_PATTERN = re.compile(
    rb"/(?:(?:" + b"Users" + rb")|(?:" + b"home" + rb"))/"
    rb"[A-Za-z0-9._-]+(?=$|[/\\\s`'\"|,:;)])"
)
_WINDOWS_HOME_PATTERN = re.compile(
    rb"(?i)(?:[A-Z]:)?\\+(?:" + b"Users" + rb")\\+"
    rb"[A-Za-z0-9._-]+(?=$|[/\\\s`'\"|,:;)])"
)
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    (
        "google-api-key",
        re.compile(rb"(?<![0-9A-Za-z_-])AIza[0-9A-Za-z_-]{35}(?![0-9A-Za-z_-])"),
    ),
    (
        "github-token",
        re.compile(
            rb"(?<![0-9A-Za-z_])"
            rb"(?:github_pat_[0-9A-Za-z_]{20,}|gh[pousr]_[0-9A-Za-z]{20,})"
            rb"(?![0-9A-Za-z_])"
        ),
    ),
    (
        "aws-access-key",
        re.compile(rb"(?<![0-9A-Z])(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Z])"),
    ),
    (
        "slack-token",
        re.compile(rb"(?<![0-9A-Za-z-])xox[baprs]-[0-9A-Za-z-]{10,}(?![0-9A-Za-z-])"),
    ),
    (
        "openai-api-key",
        re.compile(rb"(?<![0-9A-Za-z_-])sk-(?:proj-)?[0-9A-Za-z_-]{20,}(?![0-9A-Za-z_-])"),
    ),
    (
        "private-key",
        re.compile(
            rb"-----BEGIN (?:(?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED) )?PRIVATE KEY|"
            rb"PGP PRIVATE KEY BLOCK)-----"
        ),
    ),
)


def find_findings_in_bytes(path: str, data: bytes) -> list[Finding]:
    locations: set[tuple[int, str]] = set()

    for pattern in (_POSIX_HOME_PATTERN, _WINDOWS_HOME_PATTERN):
        for match in pattern.finditer(data):
            locations.add((data.count(b"\n", 0, match.start()) + 1, "personal-home-path"))

    for kind, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(data):
            locations.add((data.count(b"\n", 0, match.start()) + 1, kind))

    return [
        Finding(path=path, line=line, kind=kind)
        for line, kind in sorted(locations, key=lambda item: (item[0], item[1]))
    ]


def find_findings_in_text(path: str, text: str) -> list[Finding]:
    return find_findings_in_bytes(path, text.encode("utf-8"))


def _tracked_entries(repo_root: Path) -> list[TrackedEntry]:
    process = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if process.returncode != 0:
        raise RepoSafetyError("unable to enumerate tracked files")

    entries: list[TrackedEntry] = []
    for raw_entry in process.stdout.split(b"\0"):
        if not raw_entry:
            continue
        try:
            metadata, raw_path = raw_entry.split(b"\t", 1)
            raw_mode, raw_object_id, raw_stage = metadata.split(b" ", 2)
            stage = int(raw_stage)
        except (TypeError, ValueError) as exc:
            raise RepoSafetyError("git returned malformed tracked metadata") from exc
        if stage != 0:
            raise RepoSafetyError("unmerged tracked entries cannot be scanned safely")
        entries.append(
            TrackedEntry(
                path=raw_path.decode("utf-8", errors="surrogateescape"),
                mode=raw_mode.decode("ascii"),
                object_id=raw_object_id.decode("ascii"),
            )
        )
    return entries


def _display_path(path: str) -> str:
    return path.encode("unicode_escape", errors="backslashreplace").decode("ascii")


def _validate_relative_path(relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise RepoSafetyError("git returned an unsafe tracked path")
    return relative


def _read_regular_descriptor(
    descriptor: int, metadata: os.stat_result, relative_path: str
) -> bytes:
    try:
        opened_metadata = os.fstat(descriptor)
        if not stat.S_ISREG(opened_metadata.st_mode) or (
            metadata.st_dev,
            metadata.st_ino,
        ) != (opened_metadata.st_dev, opened_metadata.st_ino):
            raise RepoSafetyError(
                f"tracked file changed during scan {_display_path(relative_path)}"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    except OSError as exc:
        raise RepoSafetyError(
            f"unable to read tracked file {_display_path(relative_path)}"
        ) from exc


def _supports_secure_directory_walk() -> bool:
    return (
        hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks
        and os.readlink in os.supports_dir_fd
    )


def _read_worktree_bytes_dir_fd(repo_root: Path, relative: Path, relative_path: str) -> bytes:
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_descriptor: int | None = None
    try:
        parent_descriptor = os.open(repo_root, directory_flags)
        for component in relative.parts[:-1]:
            child_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=parent_descriptor,
            )
            os.close(parent_descriptor)
            parent_descriptor = child_descriptor

        final_component = relative.parts[-1]
        metadata = os.stat(
            final_component,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(metadata.st_mode):
            return os.readlink(final_component, dir_fd=parent_descriptor).encode(
                "utf-8", errors="surrogateescape"
            )
        if not stat.S_ISREG(metadata.st_mode):
            raise RepoSafetyError(
                f"tracked path is not a regular file {_display_path(relative_path)}"
            )

        file_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | os.O_NOFOLLOW
        descriptor = os.open(final_component, file_flags, dir_fd=parent_descriptor)
        try:
            return _read_regular_descriptor(descriptor, metadata, relative_path)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise RepoSafetyError(
            f"unable to inspect tracked file {_display_path(relative_path)}"
        ) from exc
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def _read_worktree_bytes(repo_root: Path, entry: TrackedEntry) -> bytes:
    relative_path = entry.path
    relative = _validate_relative_path(relative_path)
    if not relative.parts:
        raise RepoSafetyError("git returned an empty tracked path")
    if not _supports_secure_directory_walk():
        raise RepoSafetyError(
            "secure worktree traversal is unavailable; use --staged on this platform"
        )
    return _read_worktree_bytes_dir_fd(repo_root, relative, relative_path)


def _read_index_bytes(repo_root: Path, entry: TrackedEntry) -> bytes:
    process = subprocess.run(
        ["git", "cat-file", "blob", entry.object_id],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if process.returncode != 0:
        raise RepoSafetyError(f"unable to read staged file {_display_path(entry.path)}")
    return process.stdout


def scan_repository(repo_root: Path, *, staged: bool = False) -> ScanResult:
    repo_root = repo_root.resolve()
    findings: list[Finding] = []
    scanned_files = 0
    binary_files_scanned = 0
    skipped_gitlinks = 0

    for entry in _tracked_entries(repo_root):
        if entry.mode == "160000":
            skipped_gitlinks += 1
            continue
        data = (
            _read_index_bytes(repo_root, entry)
            if staged
            else _read_worktree_bytes(repo_root, entry)
        )
        if b"\0" in data:
            binary_files_scanned += 1
        scanned_files += 1
        findings.extend(find_findings_in_bytes(entry.path, data))

    findings.sort(key=lambda finding: (finding.path, finding.line, finding.kind))
    return ScanResult(
        findings=findings,
        scanned_files=scanned_files,
        binary_files_scanned=binary_files_scanned,
        skipped_gitlinks=skipped_gitlinks,
    )


def run_self_tests() -> None:
    separator = "\\"
    unsafe_controls = (
        ("mac-home", "/" + "Users" + "/private-account/workspace", "personal-home-path"),
        ("linux-home", "/" + "home" + "/private-account/workspace", "personal-home-path"),
        (
            "windows-home",
            "C:" + separator + "Users" + separator + "private-account" + separator,
            "personal-home-path",
        ),
        ("google", "AI" + "za" + "A" * 34 + "-", "google-api-key"),
        ("github", "gh" + "p_" + "A" * 36, "github-token"),
        ("aws-long-term", "AK" + "IA" + "A" * 16, "aws-access-key"),
        ("aws-session", "AS" + "IA" + "A" * 16, "aws-access-key"),
        ("slack", "xo" + "xb-" + "A" * 20, "slack-token"),
        ("openai", "s" + "k-" + "A" * 32, "openai-api-key"),
        ("private-key", "-----BEGIN " + "PRIVATE KEY-----", "private-key"),
        (
            "encrypted-private-key",
            "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----",
            "private-key",
        ),
        ("pgp-private-key", "-----BEGIN " + "PGP PRIVATE KEY BLOCK-----", "private-key"),
    )
    for label, value, expected_kind in unsafe_controls:
        findings = find_findings_in_text(f"{label}.txt", value)
        actual_kinds = [finding.kind for finding in findings]
        if actual_kinds != [expected_kind]:
            raise AssertionError(
                f"unsafe control {label} mismatch: expected {expected_kind}, got {actual_kinds}"
            )

    binary_control = b"\0\xff" + ("AI" + "za" + "A" * 34 + "-").encode("ascii")
    binary_kinds = [
        finding.kind for finding in find_findings_in_bytes("binary-control.bin", binary_control)
    ]
    if binary_kinds != ["google-api-key"]:
        raise AssertionError(f"binary control mismatch: got {binary_kinds}")

    safe_text = "\n".join(
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
    safe_findings = find_findings_in_text("safe-control.txt", safe_text)
    if safe_findings:
        raise AssertionError("safe placeholder controls produced findings")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan tracked files for personal home paths and high-confidence secrets."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to scan (defaults to this script's checkout).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run deterministic safe/unsafe controls instead of scanning a repository.",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Scan every stage-0 index blob instead of the tracked worktree.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.self_test:
        try:
            run_self_tests()
        except AssertionError as exc:
            print(f"repo safety self-test: failed ({exc})", file=sys.stderr)
            return 1
        print("repo safety self-test: passed")
        return 0

    try:
        result = scan_repository(args.repo_root, staged=args.staged)
    except RepoSafetyError as exc:
        print(f"repo safety: error ({exc})", file=sys.stderr)
        return 2

    if result.findings:
        print(
            f"repo safety: {len(result.findings)} finding(s) in tracked files",
            file=sys.stderr,
        )
        for finding in result.findings:
            print(
                f"{_display_path(finding.path)}:{finding.line}: {finding.kind}",
                file=sys.stderr,
            )
        return 1

    print(
        "repo safety: clean "
        f"({result.scanned_files} tracked files scanned, "
        f"{result.binary_files_scanned} binary/NUL files included, "
        f"{result.skipped_gitlinks} gitlinks skipped)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
