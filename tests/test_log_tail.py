"""Log tails stay bounded while retaining safe artifact reads and line semantics."""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest

from src import storage


@pytest.mark.parametrize("limit", [1, 2, 10, 120, 0, -1, -3])
@pytest.mark.parametrize(
    "content",
    [
        "",
        "one line",
        "one\ntwo\nthree\n",
        "\n\n\n",
        "one\r\ntwo\rthree\nfour\vfive\fsix\x1cseven\x1deight\x1enine\x85ten\u2028十一\u2029末尾",
        "very long " + "字" * 10000 + "\nlast\n",
    ],
)
def test_tail_matches_full_read_line_slicing(tmp_path: Path, limit: int, content: str) -> None:
    path = tmp_path / "run.log"
    path.write_bytes(content.encode("utf-8"))
    assert storage.tail_file_lines(path, limit) == "\n".join(content.splitlines()[-limit:])


@pytest.mark.parametrize("character", ["é", "字", "𐀀", "\u0085", "\u2028", "\u2029"])
def test_tail_handles_utf8_and_line_separator_window_boundaries(
    tmp_path: Path, character: str
) -> None:
    path = tmp_path / "run.log"
    encoded = character.encode("utf-8")
    for offset in range(len(encoded)):
        # Put the first 8 KiB window at each byte of a multibyte character.
        suffix = b"x" * (8192 - len(encoded) + offset - 4) + b"\nend"
        content = b"old\n" * 3000 + encoded + suffix
        path.write_bytes(content)
        expected = "\n".join(content.decode("utf-8").splitlines()[-2:])
        assert storage.tail_file_lines(path, 2) == expected


def test_tail_only_validates_inspected_utf8_suffix(tmp_path: Path) -> None:
    path = tmp_path / "run.log"
    path.write_bytes(b"\xff\n" + b"valid historical line\n" * 2000 + b"current\n")
    assert storage.tail_file_lines(path, 1) == "current"
    assert storage.tail_file_lines(path, 0) == ""
    path.write_bytes(b"old\n" * 3000 + b"\xff\ncurrent\n")
    assert storage.tail_file_lines(path, 1) == ""


class CountingReader(io.BytesIO):
    def __init__(self, content: bytes):
        super().__init__(content)
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        assert size >= 0, "log tails must not request an unbounded read"
        content = super().read(size)
        self.bytes_read += len(content)
        return content


def test_tail_read_volume_depends_on_suffix_not_history() -> None:
    suffix = b"current status\n" * 120
    for history_lines in (1000, 100000):
        reader = CountingReader(b"historical status\n" * history_lines + suffix)
        assert storage._tail_binary_lines(reader, 120) == "\n".join(["current status"] * 120)
        assert reader.bytes_read == 8192


def test_tail_grows_window_for_long_returned_lines() -> None:
    content = b"historical status\n" * 100000 + b"x" * 30000 + b"\nlast"
    reader = CountingReader(content)
    assert storage._tail_binary_lines(reader, 2) == "x" * 30000 + "\nlast"
    assert reader.bytes_read < 2 * 32768


def test_tail_missing_directory_and_unsafe_leaf_return_empty(tmp_path: Path) -> None:
    path = tmp_path / "run.log"
    assert storage.tail_file_lines(path) == ""
    path.mkdir()
    assert storage.tail_file_lines(path) == ""
    path.rmdir()
    source = tmp_path / "source.log"
    source.write_text("must not expose", encoding="utf-8")
    path.symlink_to(source)
    assert storage.tail_file_lines(path) == ""
    path.unlink()
    os.link(source, path)
    assert storage.tail_file_lines(path) == ""
    path.unlink()
    if hasattr(os, "mkfifo"):
        os.mkfifo(path)
        assert storage.tail_file_lines(path) == ""


def test_tail_rejects_symlinked_parent_under_anchor(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "run.log").write_text("must not expose", encoding="utf-8")
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    assert storage.tail_file_lines(linked / "run.log", anchor=tmp_path) == ""


def test_tail_rejects_leaf_swapped_between_metadata_and_open(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "run.log"
    path.write_text("original", encoding="utf-8")
    replacement = tmp_path / "replacement.log"
    replacement.write_text("must not expose", encoding="utf-8")
    real_metadata = storage._entry_metadata

    def replace_after_metadata(target, descriptor):
        metadata = real_metadata(target, descriptor)
        if target == path:
            replacement.replace(path)
        return metadata

    monkeypatch.setattr(storage, "_entry_metadata", replace_after_metadata)
    assert storage.tail_file_lines(path, anchor=tmp_path) == ""
    assert not replacement.exists()
