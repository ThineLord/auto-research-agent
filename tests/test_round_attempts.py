from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import src.storage as storage_module
from src.round_attempts import (
    MAX_ATTEMPTS_PER_ROUND,
    MAX_RETAINED_ATTEMPT_BYTES_PER_ROUND,
    MIN_FREE_BYTES_FOR_ATTEMPT,
    RoundAttemptBlockedError,
    classify_round_recovery,
    create_round_attempt,
    mark_attempt_ready_to_publish,
    mark_attempt_stopped,
    persist_attempt_stage,
    publish_attempt,
    write_attempt_stage_output,
)
from src.storage import write_json_file

CONFIG_DIGEST = "a" * 64


class RoundAttemptStorageTests(unittest.TestCase):
    def _ready_attempt(
        self,
        run_root: Path,
        *,
        round_index: int = 1,
        attempt_id: str = "12345678abcdef00",
    ) -> Path:
        attempt_dir = create_round_attempt(
            run_root=run_root,
            round_index=round_index,
            run_config_sha256=CONFIG_DIGEST,
            attempt_id=attempt_id,
        )
        for stage in ("draft", "review", "revise", "judge"):
            persist_attempt_stage(attempt_dir, stage, f"{stage} result")
        mark_attempt_ready_to_publish(attempt_dir)
        return attempt_dir

    def test_ready_attempt_atomically_publishes_without_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()
            attempt_dir = self._ready_attempt(run_root)
            expected = {path.name: path.read_bytes() for path in (attempt_dir / "output").iterdir()}

            canonical = publish_attempt(attempt_dir)

            self.assertEqual(canonical, run_root / "round_01")
            self.assertFalse((attempt_dir / "output").exists())
            self.assertEqual(
                {path.name: path.read_bytes() for path in canonical.iterdir()},
                expected,
            )
            manifest = json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["state"], "published")
            self.assertEqual(manifest["publication_mode"], "atomic_rename")
            classification = classify_round_recovery(run_root, 1)
            self.assertEqual(classification.status, "published_uncommitted")
            self.assertFalse(classification.can_create_attempt)

    def test_empty_canonical_handoff_is_create_only_and_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            canonical = run_root / "round_01"
            canonical.mkdir(parents=True)
            attempt_dir = self._ready_attempt(run_root)
            manifest = json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["canonical_handoff"], "reserved_empty")
            original_write = storage_module.write_file_text_create_only
            writes = 0

            def interrupt_after_first_write(path: Path, content: str, **kwargs: object) -> None:
                nonlocal writes
                original_write(path, content, **kwargs)
                writes += 1
                if writes == 1:
                    raise KeyboardInterrupt

            with (
                patch(
                    "src.round_attempts.write_file_text_create_only",
                    side_effect=interrupt_after_first_write,
                ),
                self.assertRaises(KeyboardInterrupt),
            ):
                publish_attempt(attempt_dir)

            self.assertEqual([path.name for path in canonical.iterdir()], ["01_draft.md"])
            self.assertEqual(
                json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))["state"],
                "ready_to_publish",
            )
            pending = classify_round_recovery(run_root, 1)
            self.assertEqual(pending.status, "publication_pending")

            publish_attempt(attempt_dir)

            self.assertEqual(
                sorted(path.name for path in canonical.iterdir()),
                ["01_draft.md", "02_review.md", "03_revised.md", "04_judge.md"],
            )
            self.assertTrue((attempt_dir / "output").is_dir())
            published = json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(published["state"], "published")
            self.assertEqual(published["publication_mode"], "retained_copy")

    def test_publication_collision_preserves_both_trees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()
            attempt_dir = self._ready_attempt(run_root)
            attempt_before = {
                path.name: path.read_bytes() for path in (attempt_dir / "output").iterdir()
            }
            canonical = run_root / "round_01"
            canonical.mkdir()
            sentinel = canonical / "user.txt"
            sentinel.write_text("preserve\n", encoding="utf-8")

            with self.assertRaises((FileExistsError, RoundAttemptBlockedError)):
                publish_attempt(attempt_dir)

            self.assertEqual(sentinel.read_bytes(), b"preserve\n")
            self.assertEqual(
                {path.name: path.read_bytes() for path in (attempt_dir / "output").iterdir()},
                attempt_before,
            )
            self.assertEqual(
                json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))["state"],
                "ready_to_publish",
            )

    def test_atomic_publication_manifest_failure_reconciles_without_republishing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()
            attempt_dir = self._ready_attempt(run_root)

            with (
                patch(
                    "src.round_attempts.write_json_file",
                    side_effect=OSError("injected publication manifest failure"),
                ),
                self.assertRaisesRegex(OSError, "injected publication manifest failure"),
            ):
                publish_attempt(attempt_dir)

            canonical = run_root / "round_01"
            self.assertTrue(canonical.is_dir())
            self.assertFalse((attempt_dir / "output").exists())
            self.assertEqual(
                json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))["state"],
                "ready_to_publish",
            )
            pending = classify_round_recovery(run_root, 1)
            self.assertEqual(pending.status, "publication_pending")

            self.assertEqual(publish_attempt(attempt_dir), canonical)
            self.assertEqual(
                json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))["state"],
                "published",
            )

    def test_manifest_transitions_record_each_stage_and_stop_immutably(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()
            attempt_dir = create_round_attempt(
                run_root=run_root,
                round_index=2,
                run_config_sha256=CONFIG_DIGEST,
                attempt_id="12345678abcdef00",
                created_at="2026-07-23T12:00:00+00:00",
            )

            draft_path = persist_attempt_stage(
                attempt_dir,
                "draft",
                " draft result ",
                updated_at="2026-07-23T12:01:00+00:00",
            )
            manifest = json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(draft_path.read_bytes(), b"draft result\n")
            self.assertEqual(manifest["completed_stages"], ["draft"])
            self.assertEqual(manifest["last_successful_agent"], "draft")
            self.assertEqual(
                manifest["outputs"]["01_draft.md"]["sha256"],
                hashlib.sha256(b"draft result\n").hexdigest(),
            )

            with self.assertRaisesRegex(RoundAttemptBlockedError, "expected review"):
                persist_attempt_stage(attempt_dir, "revise", "out of order")
            with self.assertRaisesRegex(ValueError, "move backwards"):
                persist_attempt_stage(
                    attempt_dir,
                    "review",
                    "review",
                    updated_at="2026-07-23T11:59:00+00:00",
                )
            self.assertFalse((attempt_dir / "output" / "02_review.md").exists())

            mark_attempt_stopped(
                attempt_dir,
                "MANUAL_INTERRUPT",
                updated_at="2026-07-23T12:02:00+00:00",
            )
            stopped_bytes = (attempt_dir / "attempt.json").read_bytes()
            classification = classify_round_recovery(run_root, 2)
            self.assertEqual(classification.status, "staged_partial")
            self.assertTrue(classification.can_create_attempt)
            self.assertEqual(classification.latest_verified_completed_stage, "draft")
            with self.assertRaisesRegex(RoundAttemptBlockedError, "state stopped"):
                persist_attempt_stage(attempt_dir, "review", "must not write")
            self.assertEqual((attempt_dir / "attempt.json").read_bytes(), stopped_bytes)
            self.assertFalse((attempt_dir / "output" / "02_review.md").exists())

    def test_ready_transition_requires_all_four_verified_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()
            attempt_dir = create_round_attempt(
                run_root=run_root,
                round_index=1,
                run_config_sha256=CONFIG_DIGEST,
                attempt_id="12345678abcdef00",
            )
            persist_attempt_stage(attempt_dir, "draft", "draft")
            with self.assertRaisesRegex(RoundAttemptBlockedError, "four completed stages"):
                mark_attempt_ready_to_publish(attempt_dir)

            persist_attempt_stage(
                attempt_dir,
                "review",
                "review error",
                agent_succeeded=False,
            )
            for stage in ("revise", "judge"):
                persist_attempt_stage(attempt_dir, stage, stage)
            mark_attempt_ready_to_publish(attempt_dir)

            manifest = json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["state"], "ready_to_publish")
            self.assertEqual(manifest["last_successful_agent"], "judge")
            classification = classify_round_recovery(run_root, 1)
            self.assertEqual(classification.status, "publication_pending")
            self.assertFalse(classification.can_create_attempt)

    def test_disk_and_retained_byte_budgets_block_before_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()
            with (
                patch(
                    "src.round_attempts.shutil.disk_usage",
                    return_value=SimpleNamespace(free=MIN_FREE_BYTES_FOR_ATTEMPT - 1),
                ),
                self.assertRaisesRegex(RoundAttemptBlockedError, "insufficient_disk_space"),
            ):
                create_round_attempt(
                    run_root=run_root,
                    round_index=1,
                    run_config_sha256=CONFIG_DIGEST,
                    attempt_id="12345678abcdef00",
                )
            self.assertFalse((run_root / "partial_rounds").exists())

            with patch(
                "src.round_attempts._retained_attempt_bytes",
                return_value=MAX_RETAINED_ATTEMPT_BYTES_PER_ROUND + 1,
            ):
                classification = classify_round_recovery(run_root, 1)
            self.assertEqual(classification.status, "retained_attempt_budget_exceeded")
            self.assertFalse(classification.can_create_attempt)
            self.assertGreater(
                classification.retained_attempt_bytes,
                MAX_RETAINED_ATTEMPT_BYTES_PER_ROUND,
            )

    def test_manifest_update_failure_preserves_orphan_output_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()
            attempt_dir = create_round_attempt(
                run_root=run_root,
                round_index=1,
                run_config_sha256=CONFIG_DIGEST,
                attempt_id="12345678abcdef00",
            )
            manifest_before = (attempt_dir / "attempt.json").read_bytes()

            with (
                patch(
                    "src.round_attempts.write_json_file",
                    side_effect=OSError("injected manifest failure"),
                ),
                self.assertRaisesRegex(OSError, "injected manifest failure"),
            ):
                persist_attempt_stage(attempt_dir, "draft", "orphan evidence")

            self.assertEqual((attempt_dir / "attempt.json").read_bytes(), manifest_before)
            self.assertEqual(
                (attempt_dir / "output" / "01_draft.md").read_bytes(),
                b"orphan evidence\n",
            )
            classification = classify_round_recovery(run_root, 1)
            self.assertEqual(classification.status, "attempt_unverifiable")
            self.assertFalse(classification.can_create_attempt)

    def test_attempt_creation_and_stage_outputs_are_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()

            attempt_dir = create_round_attempt(
                run_root=run_root,
                round_index=2,
                run_config_sha256=CONFIG_DIGEST,
                attempt_id="12345678abcdef00",
                created_at="2026-07-23T12:00:00+00:00",
            )

            self.assertEqual(
                attempt_dir.relative_to(run_root).as_posix(),
                "partial_rounds/round_02/attempt_12345678abcdef00",
            )
            self.assertEqual(list((attempt_dir / "output").iterdir()), [])
            manifest = json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["state"], "active")
            self.assertEqual(manifest["completed_stages"], [])
            self.assertEqual(manifest["outputs"], {})

            output_path = write_attempt_stage_output(attempt_dir, "draft", " draft result ")
            self.assertEqual(output_path.read_bytes(), b"draft result\n")
            with self.assertRaises(FileExistsError):
                write_attempt_stage_output(attempt_dir, "draft", "replacement")
            self.assertEqual(output_path.read_bytes(), b"draft result\n")

            with self.assertRaises((FileExistsError, RoundAttemptBlockedError)):
                create_round_attempt(
                    run_root=run_root,
                    round_index=2,
                    run_config_sha256=CONFIG_DIGEST,
                    attempt_id="12345678abcdef00",
                )

    def test_failed_create_is_preserved_and_cannot_be_retried_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "stage.md"
            original_fsync = storage_module.os.fsync

            def fail_file_fsync(descriptor: int) -> None:
                if os.fstat(descriptor).st_mode:
                    raise OSError("injected fsync failure")
                original_fsync(descriptor)

            with (
                patch.object(storage_module.os, "fsync", side_effect=fail_file_fsync),
                self.assertRaisesRegex(OSError, "injected fsync failure"),
            ):
                storage_module.write_text_create_only(target, "evidence")

            self.assertTrue(target.exists())
            with self.assertRaises(FileExistsError):
                storage_module.write_text_create_only(target, "replacement")
            self.assertEqual(target.read_bytes(), b"evidence\n")

    def test_attempt_identifiers_and_attempt_count_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()
            for invalid in ("short", "../escape", "UPPERCASE1", "a" * 65):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    create_round_attempt(
                        run_root=run_root,
                        round_index=1,
                        run_config_sha256=CONFIG_DIGEST,
                        attempt_id=invalid,
                    )

            attempt_root = run_root / "partial_rounds" / "round_01"
            attempt_root.mkdir(parents=True)
            for index in range(MAX_ATTEMPTS_PER_ROUND):
                (attempt_root / f"attempt_{index:08d}").mkdir()
            with self.assertRaisesRegex(RoundAttemptBlockedError, "attempt_limit_reached"):
                create_round_attempt(
                    run_root=run_root,
                    round_index=1,
                    run_config_sha256=CONFIG_DIGEST,
                    attempt_id="ffffffffffffffff",
                )
            self.assertFalse((attempt_root / "attempt_ffffffffffffffff").exists())


class RoundRecoveryClassifierTests(unittest.TestCase):
    def _stopped_attempt(
        self,
        run_root: Path,
        *,
        attempt_id: str = "12345678abcdef00",
        completed_stages: tuple[str, ...] = ("draft", "review"),
    ) -> Path:
        attempt_dir = create_round_attempt(
            run_root=run_root,
            round_index=2,
            run_config_sha256=CONFIG_DIGEST,
            attempt_id=attempt_id,
            created_at="2026-07-23T12:00:00+00:00",
        )
        outputs: dict[str, dict[str, object]] = {}
        stage_files = {
            "draft": "01_draft.md",
            "review": "02_review.md",
            "revise": "03_revised.md",
            "judge": "04_judge.md",
        }
        for stage in completed_stages:
            output_path = write_attempt_stage_output(attempt_dir, stage, f"{stage} evidence")
            content = output_path.read_bytes()
            outputs[stage_files[stage]] = {
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        write_json_file(
            attempt_dir / "attempt.json",
            {
                "schema_version": 1,
                "kind": "partial_round_attempt",
                "run_id": run_root.name,
                "round": 2,
                "attempt_id": attempt_id,
                "state": "stopped",
                "completed_stages": list(completed_stages),
                "last_successful_agent": completed_stages[-1] if completed_stages else None,
                "stop_reason": "MANUAL_INTERRUPT",
                "created_at": "2026-07-23T12:00:00+00:00",
                "updated_at": "2026-07-23T12:05:00+00:00",
                "run_config_sha256": CONFIG_DIGEST,
                "outputs": outputs,
            },
            anchor=run_root,
        )
        return attempt_dir

    def test_missing_canonical_with_no_attempts_is_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()

            classification = classify_round_recovery(run_root, 2)

            self.assertEqual(classification.status, "new_round")
            self.assertTrue(classification.can_create_attempt)
            self.assertEqual(classification.preserved_attempt_count, 0)
            self.assertIsNone(classification.blocked_reason)

    def test_verified_stopped_attempt_is_retryable_and_reports_latest_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()
            attempt_dir = self._stopped_attempt(run_root)
            before = {
                path.relative_to(run_root): path.read_bytes()
                for path in run_root.rglob("*")
                if path.is_file()
            }

            classification = classify_round_recovery(run_root, 2)

            self.assertEqual(classification.status, "staged_partial")
            self.assertTrue(classification.can_create_attempt)
            self.assertEqual(classification.safety_action, "retry_round_preserve_attempt")
            self.assertEqual(classification.preserved_attempt_count, 1)
            self.assertEqual(classification.latest_verified_completed_stage, "review")
            self.assertEqual(classification.attempts[0].attempt_id, "12345678abcdef00")
            self.assertTrue(classification.attempts[0].verified)
            after = {
                path.relative_to(run_root): path.read_bytes()
                for path in run_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)
            self.assertTrue(attempt_dir.exists())

    def test_hash_mismatch_and_unknown_entries_fail_closed_without_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "private-run-id"
            run_root.mkdir()
            attempt_dir = self._stopped_attempt(run_root)
            (attempt_dir / "output" / "01_draft.md").write_text(
                "changed evidence\n",
                encoding="utf-8",
            )
            (attempt_dir / "unexpected.txt").write_text("preserve\n", encoding="utf-8")

            classification = classify_round_recovery(run_root, 2)

            self.assertEqual(classification.status, "attempt_unverifiable")
            self.assertFalse(classification.can_create_attempt)
            self.assertEqual(classification.blocked_reason, "unverifiable_attempt")
            self.assertNotIn(str(Path(tmp)), repr(classification))
            self.assertTrue((attempt_dir / "unexpected.txt").exists())

    def test_non_scalar_manifest_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()
            attempt_dir = create_round_attempt(
                run_root=run_root,
                round_index=2,
                run_config_sha256=CONFIG_DIGEST,
                attempt_id="12345678abcdef00",
            )
            manifest = json.loads((attempt_dir / "attempt.json").read_text(encoding="utf-8"))
            manifest["state"] = ["active"]
            write_json_file(attempt_dir / "attempt.json", manifest, anchor=run_root)

            classification = classify_round_recovery(run_root, 2)

            self.assertEqual(classification.status, "attempt_unverifiable")
            self.assertFalse(classification.can_create_attempt)
            self.assertEqual(classification.blocked_reason, "unverifiable_attempt")

    def test_active_attempt_and_canonical_conflicts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-id"
            run_root.mkdir()
            create_round_attempt(
                run_root=run_root,
                round_index=2,
                run_config_sha256=CONFIG_DIGEST,
                attempt_id="12345678abcdef00",
            )
            active = classify_round_recovery(run_root, 2)
            self.assertEqual(active.status, "attempt_in_progress")
            self.assertFalse(active.can_create_attempt)

            canonical = run_root / "round_02"
            canonical.mkdir()
            (canonical / "01_draft.md").write_text("legacy partial\n", encoding="utf-8")
            conflict = classify_round_recovery(run_root, 2)
            self.assertEqual(conflict.status, "canonical_attempt_conflict")
            self.assertFalse(conflict.can_create_attempt)
            self.assertEqual(
                (canonical / "01_draft.md").read_text(encoding="utf-8"),
                "legacy partial\n",
            )

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_linked_attempt_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "run-id"
            outside = root / "outside"
            attempt_root = run_root / "partial_rounds" / "round_02"
            attempt_root.mkdir(parents=True)
            outside.mkdir()
            (attempt_root / "attempt_12345678abcdef00").symlink_to(
                outside,
                target_is_directory=True,
            )

            classification = classify_round_recovery(run_root, 2)

            self.assertEqual(classification.status, "attempt_unverifiable")
            self.assertFalse(classification.can_create_attempt)


if __name__ == "__main__":
    unittest.main()
