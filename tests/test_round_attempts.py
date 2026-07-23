from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.storage as storage_module
from src.round_attempts import (
    MAX_ATTEMPTS_PER_ROUND,
    RoundAttemptBlockedError,
    classify_round_recovery,
    create_round_attempt,
    write_attempt_stage_output,
)
from src.storage import write_json_file

CONFIG_DIGEST = "a" * 64


class RoundAttemptStorageTests(unittest.TestCase):
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
