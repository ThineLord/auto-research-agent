from __future__ import annotations

import pytest

from src.input_editing import InputEditConflict, read_inputs, save_inputs
from src.runtime import acquire_run_lock, release_run_lock


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "projects" / "sample"
    path.mkdir(parents=True)
    (path / "task.md").write_text("Initial task")
    (path / "memory.md").write_text("Initial memory")
    return path


def test_task_only_save_preserves_new_run_memory(project):
    old = read_inputs(project)
    (project / "memory.md").write_text("New evidence from a completed round")
    result = save_inputs(project, {"task": "研究任务"}, old["revisions"])
    assert result["memory"] == "New evidence from a completed round"
    assert result["task"] == "研究任务"


def test_conflict_checks_all_fields_before_any_write(project):
    old = read_inputs(project)
    (project / "memory.md").write_text("New memory")
    with pytest.raises(InputEditConflict) as error:
        save_inputs(project, {"task": "Changed task", "memory": "Stale edit"}, old["revisions"])
    assert error.value.current["memory"] == "New memory"
    assert (project / "task.md").read_text() == "Initial task"


def test_second_editor_cannot_silently_overwrite_first(project):
    old = read_inputs(project)
    save_inputs(project, {"task": "First editor"}, old["revisions"])
    with pytest.raises(InputEditConflict):
        save_inputs(project, {"task": "Second editor"}, old["revisions"])
    assert (project / "task.md").read_text() == "First editor"


def test_cli_run_lock_blocks_edit(project):
    old = read_inputs(project)
    lock, error = acquire_run_lock(project, mode="normal", model_name="mock")
    assert not error
    try:
        with pytest.raises(InputEditConflict, match="input_busy"):
            save_inputs(project, {"task": "Blocked"}, old["revisions"])
    finally:
        release_run_lock(lock)
    assert (project / "task.md").read_text() == "Initial task"


def test_pending_transaction_blocks_edit_without_recovery(project):
    old = read_inputs(project)
    journal = project / ".round_commit_transaction.json"
    journal.write_text("{}")
    with pytest.raises(InputEditConflict, match="input_recovery_pending"):
        save_inputs(project, {"task": "Blocked"}, old["revisions"])
    assert journal.read_text() == "{}"
    assert (project / "task.md").read_text() == "Initial task"


def test_missing_and_empty_memory_have_distinct_revisions(project):
    (project / "memory.md").unlink()
    old = read_inputs(project)
    assert old["memory"] == ""
    (project / "memory.md").write_text("")
    with pytest.raises(InputEditConflict):
        save_inputs(project, {"memory": "New"}, old["revisions"])


@pytest.mark.parametrize("changes,revisions", [({"task": "x"}, {}), ({"../x": "x"}, {}), ({}, {})])
def test_unversioned_or_unknown_fields_are_rejected(project, changes, revisions):
    with pytest.raises(ValueError):
        save_inputs(project, changes, revisions)
