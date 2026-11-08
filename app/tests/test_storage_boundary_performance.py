"""Boundary indexing preserves the original inheritance and rebasing rules."""

from __future__ import annotations

import random

import pytest

from src import storage


def original_register(boundaries, root, anchor):
    inherited = [
        (len(registered.parts), selected)
        for registered, selected in boundaries.items()
        if registered != root and root.is_relative_to(registered)
    ]
    if inherited:
        anchor = max(inherited, key=lambda item: item[0])[1]
    root.relative_to(anchor)
    result = {}
    for registered, selected in boundaries.items():
        if registered == root:
            continue
        if registered.is_relative_to(root) and selected.is_relative_to(root):
            selected = anchor
        result[registered] = selected
    result[root] = anchor
    return result


def original_lookup(boundaries, path):
    matches = [
        (len(root.parts), anchor)
        for root, anchor in boundaries.items()
        if path.is_relative_to(root)
    ]
    return max(matches, default=(0, None), key=lambda item: item[0])[1]


def test_registration_orders_and_lookup_match_original_rules(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    project = projects / "example"
    run = project / "runs" / "run"
    external = tmp_path / "external"
    operations = [
        (run, run),
        (project, projects),
        (project / "runs", project),
        (projects, tmp_path),
        (external / "run", external),
        (external, tmp_path),
    ]
    queries = [root / "child" / "output.json" for root, _ in operations]
    queries += [root for root, _ in operations] + [tmp_path / "unregistered"]
    rng = random.Random(20261015)
    for _ in range(40):
        monkeypatch.setattr(storage, "_ARTIFACT_BOUNDARIES", {})
        expected = {}
        for root, anchor in rng.sample(operations, len(operations)) + operations:
            snapshot = storage._ARTIFACT_BOUNDARIES
            original_snapshot = snapshot.copy()
            expected = original_register(expected, root, anchor)
            storage._register_artifact_boundary(root, anchor)
            assert storage._ARTIFACT_BOUNDARIES == expected
            assert snapshot == original_snapshot
            for path in queries:
                assert storage._registered_artifact_anchor(path) == original_lookup(expected, path)


def test_invalid_registration_preserves_published_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_ARTIFACT_BOUNDARIES", {})
    root = tmp_path / "project"
    storage._register_artifact_boundary(root, tmp_path)
    snapshot = storage._ARTIFACT_BOUNDARIES
    with pytest.raises(storage.UnsafeArtifactPathError):
        storage._register_artifact_boundary(tmp_path / "unrelated", root)
    assert storage._ARTIFACT_BOUNDARIES is snapshot
    assert storage._registered_artifact_anchor(root / "output") == tmp_path


def test_lookup_cost_depends_on_path_depth_not_registered_projects(tmp_path, monkeypatch):
    class CountingIndex(dict):
        lookups = 0

        def get(self, key, default=None):
            self.lookups += 1
            return super().get(key, default)

        def items(self):
            raise AssertionError("lookup must not scan registered projects")

    index = CountingIndex({tmp_path / f"project-{i}": tmp_path for i in range(2000)})
    selected = tmp_path / "project-1999" / "runs" / "run" / "output.json"
    monkeypatch.setattr(storage, "_ARTIFACT_BOUNDARIES", index)
    assert storage._registered_artifact_anchor(selected) == tmp_path
    assert index.lookups == 4
    index.lookups = 0
    assert storage._registered_artifact_anchor(tmp_path / "missing") is None
    assert index.lookups <= len((tmp_path / "missing").parts)
