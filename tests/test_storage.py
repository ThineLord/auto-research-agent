from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import src.storage as storage_module
from src.storage import (
    append_log_line,
    ensure_project_runtime_paths_safe,
    get_memory_for_prompt,
    list_artifact_regular_files,
    make_round_dir,
    make_run_root,
    parse_score,
    read_json_file,
    summarize_round_memory,
    update_project_memory,
    update_research_state,
    write_interrupted_report,
    write_json_file,
)


class StorageTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_recursive_artifact_listing_is_sorted_and_skips_linked_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "projects" / "selected"
            nested = project / "a"
            nested.mkdir(parents=True)
            (project / "a.md").write_text("root\n", encoding="utf-8")
            (nested / "z.md").write_text("nested\n", encoding="utf-8")
            outside = root / "outside"
            outside.mkdir()
            (outside / "private.md").write_text("private\n", encoding="utf-8")
            (project / "linked").symlink_to(outside, target_is_directory=True)
            ensure_project_runtime_paths_safe(project)

            files = list_artifact_regular_files(project)

            self.assertEqual(files, [project / "a.md", nested / "z.md"])

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_recursive_artifact_listing_keeps_open_directory_during_ancestor_swap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            project = projects / "selected"
            project.mkdir(parents=True)
            (project / "safe.md").write_text("safe\n", encoding="utf-8")
            outside_project = root / "outside-projects" / "selected"
            outside_project.mkdir(parents=True)
            (outside_project / "private.md").write_text("private\n", encoding="utf-8")
            trusted_projects = root / "trusted-projects"
            ensure_project_runtime_paths_safe(project)
            original_listdir = storage_module.os.listdir
            swapped = False

            def swap_then_list(directory: object) -> list[str]:
                nonlocal swapped
                if not swapped and isinstance(directory, int):
                    projects.rename(trusted_projects)
                    projects.symlink_to(root / "outside-projects", target_is_directory=True)
                    swapped = True
                return original_listdir(directory)

            with patch.object(storage_module.os, "listdir", side_effect=swap_then_list):
                files = list_artifact_regular_files(project)

            self.assertTrue(swapped)
            self.assertEqual([path.name for path in files], ["safe.md"])
            self.assertNotIn("private.md", [path.name for path in files])

    def test_windows_reparse_attribute_is_classified_as_a_link(self) -> None:
        metadata = SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=0x0400,
        )
        with patch.object(storage_module.os, "name", "nt"):
            self.assertTrue(
                storage_module._path_is_link_or_junction(
                    Path("automatic-directory"),
                    metadata,
                )
            )

    @unittest.skipIf(os.name == "nt", "POSIX fail-closed behavior only")
    def test_automatic_boundary_fails_closed_without_descriptor_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "projects" / "selected"
            project.mkdir(parents=True)

            with (
                patch.object(
                    storage_module,
                    "_supports_descriptor_relative_io",
                    return_value=False,
                ),
                self.assertRaises(OSError),
            ):
                ensure_project_runtime_paths_safe(project)

    def test_parse_score_accepts_legacy_score_lines_and_clamps_range(self) -> None:
        self.assertEqual(parse_score("SCORE: 88.5\nGood direction."), 88.5)
        self.assertEqual(parse_score("score: 120"), 100.0)
        self.assertEqual(parse_score("SCORE: 0"), 0.0)
        self.assertIsNone(parse_score("No score here."))

    def test_parse_score_accepts_json_score_outputs(self) -> None:
        self.assertEqual(parse_score('{"score": 88.5, "next_step": "CONTINUE"}'), 88.5)
        self.assertEqual(parse_score('```json\n{"score": 72}\n```'), 72.0)
        self.assertEqual(parse_score('Result:\n{"score": "63.25"}\nDone.'), 63.25)
        self.assertEqual(parse_score('{"score": 120}'), 100.0)

    def test_parse_score_rejects_invalid_json_scores(self) -> None:
        self.assertIsNone(parse_score('{"next_step": "CONTINUE"}'))
        self.assertIsNone(parse_score('{"score": true}'))
        self.assertIsNone(parse_score('{"score": "not numeric"}'))
        self.assertIsNone(parse_score('{"score": NaN}'))
        self.assertIsNone(parse_score("[88]"))

    def test_json_helpers_return_empty_dict_for_missing_or_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.json"
            invalid = root / "invalid.json"
            invalid_utf8 = root / "invalid-utf8.json"
            stale_directory = root / "checkpoint.json"
            invalid.write_text("{not json", encoding="utf-8")
            invalid_utf8.write_bytes(b"\xff\xfe")
            stale_directory.mkdir()

            self.assertEqual(read_json_file(missing), {})
            self.assertEqual(read_json_file(invalid), {})
            self.assertEqual(read_json_file(invalid_utf8), {})
            self.assertEqual(read_json_file(stale_directory), {})

            valid = root / "valid.json"
            valid.write_text('{"round": 1}', encoding="utf-8")
            for error in (ValueError("oversized integer"), RecursionError("too deeply nested")):
                with (
                    self.subTest(error=error.__class__.__name__),
                    patch(
                        "src.storage.json.loads",
                        side_effect=error,
                    ),
                ):
                    self.assertEqual(read_json_file(valid), {})

            target = root / "nested" / "state.json"
            write_json_file(target, {"round": 2, "score": 91})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["score"], 91)

    def test_json_write_preserves_previous_state_when_atomic_commit_fails(self) -> None:
        for failing_call in ("fsync", "replace"):
            with self.subTest(failing_call=failing_call), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                target = root / "checkpoint.json"
                previous = {"last_completed_round": 7, "can_resume": True}
                target.write_text(json.dumps(previous), encoding="utf-8")

                with (
                    patch.object(
                        os,
                        failing_call,
                        side_effect=OSError(f"simulated {failing_call} failure"),
                    ),
                    self.assertRaisesRegex(OSError, f"simulated {failing_call} failure"),
                ):
                    write_json_file(target, {"last_completed_round": 8, "can_resume": True})

                self.assertEqual(json.loads(target.read_text(encoding="utf-8")), previous)
                self.assertEqual(list(root.glob(".checkpoint.json.*.tmp")), [])

    def test_append_log_line_tolerates_stale_directory_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "run.log"
            log_path.mkdir()

            append_log_line(log_path, "hello")

            self.assertTrue(log_path.is_dir())

    def test_project_preflight_preserves_stale_nested_cloud_cache_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            artifacts = project / "artifacts"
            (artifacts / "cloud_free_models.json").mkdir(parents=True)
            (artifacts / "cloud_free_profile.json").mkdir()

            ensure_project_runtime_paths_safe(project)

            self.assertTrue((artifacts / "cloud_free_models.json").is_dir())
            self.assertTrue((artifacts / "cloud_free_profile.json").is_dir())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_project_artifact_helpers_reject_static_symlinks_without_external_io(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            outside = root / "outside"
            project.mkdir()
            outside.mkdir()

            external_memory = outside / "memory.md"
            external_memory.write_text("PRIVATE_MEMORY_SENTINEL\n", encoding="utf-8")
            memory_path = project / "memory.md"
            memory_path.symlink_to(external_memory)
            with self.assertRaises(OSError):
                get_memory_for_prompt(memory_path)
            self.assertEqual(
                external_memory.read_text(encoding="utf-8"), "PRIVATE_MEMORY_SENTINEL\n"
            )

            external_checkpoint = outside / "checkpoint.json"
            external_checkpoint.write_text('{"trusted": true}\n', encoding="utf-8")
            checkpoint_path = project / "checkpoint.json"
            checkpoint_path.symlink_to(external_checkpoint)
            with self.assertRaises(OSError):
                write_json_file(checkpoint_path, {"trusted": False})
            self.assertTrue(checkpoint_path.is_symlink())
            self.assertEqual(
                external_checkpoint.read_text(encoding="utf-8"),
                '{"trusted": true}\n',
            )

            external_log = outside / "run.log"
            external_log.write_text("before\n", encoding="utf-8")
            log_path = project / "run.log"
            log_path.symlink_to(external_log)
            append_log_line(log_path, "SHOULD_NOT_ESCAPE")
            self.assertTrue(log_path.is_symlink())
            self.assertEqual(external_log.read_text(encoding="utf-8"), "before\n")

    @unittest.skipUnless(hasattr(os, "link"), "hard links are unavailable")
    def test_project_artifact_helpers_reject_static_hardlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            external_memory = root / "external-memory.md"
            external_memory.write_text("PRIVATE_MEMORY_SENTINEL\n", encoding="utf-8")
            os.link(external_memory, project / "memory.md")

            with self.assertRaises(OSError):
                ensure_project_runtime_paths_safe(project)
            with self.assertRaises(OSError):
                get_memory_for_prompt(project / "memory.md")
            self.assertEqual(
                external_memory.read_text(encoding="utf-8"),
                "PRIVATE_MEMORY_SENTINEL\n",
            )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_atomic_write_and_round_creation_reject_symlinked_parents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            outside = root / "outside"
            run_root = project / "runs" / "run1"
            project.mkdir()
            outside.mkdir()

            artifacts_path = project / "artifacts"
            artifacts_path.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(OSError):
                write_json_file(artifacts_path / "cloud.json", {"safe": True})
            self.assertFalse((outside / "cloud.json").exists())

            run_root.mkdir(parents=True)
            outside_round = outside / "round"
            outside_round.mkdir()
            (run_root / "round_01").symlink_to(outside_round, target_is_directory=True)
            with self.assertRaises(OSError):
                make_round_dir(run_root, 1)
            self.assertEqual(list(outside_round.iterdir()), [])

    @unittest.skipUnless(
        storage_module._supports_descriptor_relative_io(),
        "descriptor-relative filesystem operations are unavailable",
    )
    def test_atomic_write_stays_on_pinned_parent_during_path_swap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "project"
            moved_parent = root / "original-project"
            outside = root / "outside"
            parent.mkdir()
            outside.mkdir()
            target = parent / "checkpoint.json"
            original_open_parent = storage_module._open_parent_directory

            def open_then_swap(
                path: Path,
                *,
                create: bool,
                anchor: Path | None = None,
            ) -> int | None:
                descriptor = original_open_parent(path, create=create, anchor=anchor)
                parent.rename(moved_parent)
                parent.symlink_to(outside, target_is_directory=True)
                return descriptor

            with patch.object(
                storage_module,
                "_open_parent_directory",
                side_effect=open_then_swap,
            ):
                write_json_file(target, {"last_completed_round": 1})

            self.assertFalse((outside / "checkpoint.json").exists())
            self.assertEqual(
                read_json_file(moved_parent / "checkpoint.json"),
                {"last_completed_round": 1},
            )

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs are unavailable")
    def test_runtime_preflight_and_io_reject_fifo_artifacts_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            memory_path = project / "memory.md"
            log_path = project / "run.log"
            os.mkfifo(memory_path)
            os.mkfifo(log_path)
            script = """
from pathlib import Path
import sys
from src.storage import ensure_project_runtime_paths_safe, get_memory_for_prompt, open_append_text_file

project = Path(sys.argv[1])
operations = (
    lambda: ensure_project_runtime_paths_safe(project),
    lambda: get_memory_for_prompt(project / "memory.md"),
    lambda: open_append_text_file(project / "run.log"),
)
for operation in operations:
    try:
        operation()
    except OSError:
        print("blocked")
    else:
        raise SystemExit("unsafe FIFO operation unexpectedly succeeded")
"""
            result = subprocess.run(
                [sys.executable, "-c", script, str(project)],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["blocked", "blocked", "blocked"])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_new_run_preserves_configured_external_runs_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            runs_storage = root / "configured-runs"
            project.mkdir()
            runs_storage.mkdir()
            (project / "runs").symlink_to(runs_storage, target_is_directory=True)

            run_root = make_run_root(project)
            round_dir = make_round_dir(run_root, 1)
            write_json_file(round_dir / "result.json", {"ok": True})

            self.assertEqual(run_root.parent, runs_storage.resolve())
            self.assertEqual(read_json_file(round_dir / "result.json"), {"ok": True})

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_registered_project_boundary_rejects_ancestor_and_nested_link_swaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            project = projects / "selected"
            outside_projects = root / "outside-projects"
            outside_project = outside_projects / "selected"
            project.mkdir(parents=True)
            outside_project.mkdir(parents=True)
            ensure_project_runtime_paths_safe(project)

            moved_projects = root / "original-projects"
            projects.rename(moved_projects)
            projects.symlink_to(outside_projects, target_is_directory=True)
            with self.assertRaises(OSError):
                write_json_file(project / "artifacts" / "cloud.json", {"escaped": True})
            self.assertFalse((outside_project / "artifacts" / "cloud.json").exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "projects" / "selected"
            outputs = project / "outputs"
            outside = root / "outside"
            outputs.mkdir(parents=True)
            outside.mkdir()
            (outputs / "linked").symlink_to(outside, target_is_directory=True)
            ensure_project_runtime_paths_safe(project)

            with self.assertRaises(OSError):
                write_json_file(
                    outputs / "linked" / "nested" / "report.json",
                    {"escaped": True},
                )
            self.assertFalse((outside / "nested").exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_registered_boundary_is_shared_with_worker_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "projects" / "selected"
            outputs = project / "outputs"
            nested_outside = root / "outside" / "nested"
            outputs.mkdir(parents=True)
            nested_outside.mkdir(parents=True)
            ensure_project_runtime_paths_safe(project)
            outputs.rename(project / "trusted-outputs")
            outputs.symlink_to(root / "outside", target_is_directory=True)
            target = outputs / "nested" / "thread.json"

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(write_json_file, target, {"escaped": True})
                with self.assertRaises(OSError):
                    future.result(timeout=2)

            self.assertFalse((nested_outside / "thread.json").exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_nested_run_boundaries_inherit_and_rebase_to_project_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            project = projects / "selected"
            storage = project / "storage"
            storage.mkdir(parents=True)
            (project / "runs").symlink_to(storage, target_is_directory=True)
            run_root = make_run_root(project)
            round_dir = make_round_dir(run_root, 1)
            outside_round = (
                root / "outside-projects" / "selected" / "storage" / run_root.name / round_dir.name
            )
            outside_round.mkdir(parents=True)
            projects.rename(root / "trusted-projects")
            projects.symlink_to(root / "outside-projects", target_is_directory=True)

            with self.assertRaises(OSError):
                write_json_file(round_dir / "escape.json", {"escaped": True})

            self.assertFalse((outside_round / "escape.json").exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            project = projects / "selected"
            run_root = project / "runs" / "manual-run"
            run_root.mkdir(parents=True)
            round_dir = make_round_dir(run_root, 1)
            ensure_project_runtime_paths_safe(project)
            outside_round = (
                root / "outside-projects" / "selected" / "runs" / "manual-run" / round_dir.name
            )
            outside_round.mkdir(parents=True)
            projects.rename(root / "trusted-projects")
            projects.symlink_to(root / "outside-projects", target_is_directory=True)

            with self.assertRaises(OSError):
                write_json_file(round_dir / "escape.json", {"escaped": True})

            self.assertFalse((outside_round / "escape.json").exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_registered_run_boundary_rejects_run_root_swap_before_round_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "projects" / "selected"
            run_root = project / "runs" / "run1"
            moved_run = project / "runs" / "moved-run"
            outside_run = root / "outside-run"
            run_root.mkdir(parents=True)
            (outside_run / "round_01").mkdir(parents=True)
            ensure_project_runtime_paths_safe(project)
            make_round_dir(run_root, 1)

            run_root.rename(moved_run)
            run_root.symlink_to(outside_run, target_is_directory=True)
            with self.assertRaises(OSError):
                write_json_file(run_root / "round_01" / "result.json", {"escaped": True})

            self.assertFalse((outside_run / "round_01" / "result.json").exists())
            self.assertTrue((moved_run / "round_01").is_dir())

    @unittest.skipUnless(
        storage_module._supports_descriptor_relative_io(),
        "descriptor-relative filesystem operations are unavailable",
    )
    def test_round_creation_stale_path_cannot_redirect_followup_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "projects" / "selected"
            run_root = project / "runs" / "run1"
            moved_run = project / "runs" / "moved-run"
            outside_run = root / "outside-run"
            run_root.mkdir(parents=True)
            outside_run.mkdir()
            ensure_project_runtime_paths_safe(project)
            original_open_parent = storage_module._open_parent_directory

            def open_then_swap(
                path: Path,
                *,
                create: bool,
                anchor: Path | None = None,
            ) -> int | None:
                descriptor = original_open_parent(path, create=create, anchor=anchor)
                if path.name == "round_01":
                    run_root.rename(moved_run)
                    run_root.symlink_to(outside_run, target_is_directory=True)
                return descriptor

            with patch.object(
                storage_module,
                "_open_parent_directory",
                side_effect=open_then_swap,
            ):
                round_dir = make_round_dir(run_root, 1)

            with self.assertRaises(OSError):
                write_json_file(round_dir / "result.json", {"escaped": True})
            self.assertFalse((outside_run / "round_01" / "result.json").exists())
            self.assertTrue((moved_run / "round_01").is_dir())

    def test_update_project_memory_preserves_manual_notes_and_limits_auto_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_path = Path(tmp) / "memory.md"
            memory_path.write_text("Manual research context stays here.\n", encoding="utf-8")

            for round_index in range(1, 15):
                update_project_memory(
                    memory_path=memory_path,
                    round_index=round_index,
                    summary={
                        "strongest": f"Strong idea {round_index}",
                        "criticism": f"Main criticism {round_index}",
                        "unresolved": f"Open issue {round_index}",
                        "next_action": f"Next action {round_index}",
                        "best_score": f"{round_index:.2f}",
                    },
                )

            content = memory_path.read_text(encoding="utf-8")
            self.assertIn("Manual research context stays here.", content)
            self.assertIn("## Iteration Memory (auto-managed)", content)
            self.assertNotIn("### Round 01", content)
            self.assertNotIn("### Round 02", content)
            self.assertIn("### Round 03", content)
            self.assertIn("### Round 14", content)

    def test_get_memory_for_prompt_returns_recent_tail_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_path = Path(tmp) / "memory.md"
            words = [f"word{i}" for i in range(1605)]
            memory_path.write_text(" ".join(words), encoding="utf-8")

            prompt_memory = get_memory_for_prompt(memory_path)

            self.assertEqual(len(prompt_memory.split()), 1500)
            self.assertTrue(prompt_memory.startswith("word105 "))
            self.assertTrue(prompt_memory.endswith("word1604"))

    def test_custom_topic_keywords_guide_memory_and_state_extraction(self) -> None:
        summary = summarize_round_memory(
            revised_output=(
                "A plain opening sentence without configured cues.\n"
                "Graph signal fusion is the strongest route for this benchmark."
            ),
            review_output="The retrieval baseline remains under-specified.",
            judge_output="The graph ablation is the main unresolved blocker.",
            current_best_score=81.0,
            topic_keywords=["graph"],
        )

        self.assertIn("Graph signal fusion", summary["strongest"])

        with tempfile.TemporaryDirectory() as tmp:
            state = update_research_state(
                state_path=Path(tmp) / "research_state.json",
                round_index=1,
                best_score=81.0,
                revised_output=(
                    "A plain opening sentence without configured cues.\n"
                    "Graph signal fusion is the strongest route for this benchmark."
                ),
                review_output="The retrieval baseline remains under-specified.",
                judge_output="The graph ablation is the main unresolved blocker.",
                topic_keywords=["graph"],
            )

        self.assertIn("Graph signal fusion", state["current_strongest_hypothesis"])

    def test_write_interrupted_report_records_resume_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "interrupted_report.md"
            best_output_path = root / "best_output.md"

            write_interrupted_report(
                report_path=report_path,
                last_completed_round=3,
                last_successful_agent="revise",
                best_score=72.25,
                best_output_path=best_output_path,
                resume_command=".venv/bin/python -m src.main --resume",
                stop_time="2026-05-15T12:00:00",
            )

            content = report_path.read_text(encoding="utf-8")
            self.assertIn("last completed round: 3", content)
            self.assertIn("last successful agent: revise", content)
            self.assertIn("best score so far: 72.25", content)
            self.assertIn("best output path: <repo>/best_output.md", content)
            self.assertIn(".venv/bin/python -m src.main --resume", content)


if __name__ == "__main__":
    unittest.main()
