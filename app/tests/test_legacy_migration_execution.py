from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

import src.cli as cli_module
from src.round_commit_recovery import round_commit_read_blocker
from src.runtime import acquire_run_lock, release_run_lock


def _execution_module():
    return importlib.import_module("src.legacy_migration_execution")


class LegacyMigrationExecutionTests(unittest.TestCase):
    @staticmethod
    def _history() -> list[dict[str, object]]:
        return [
            {
                "round": 1,
                "score": 81.0,
                "improved": True,
                "successful_research_round": True,
            }
        ]

    @staticmethod
    def _write_json(path: Path, value: object) -> bytes:
        content = json.dumps(value, indent=2).encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return content

    def _fixture(
        self,
        root: Path,
        *,
        source_artifact: str = "score_history",
        configured_external: bool = False,
        paired: bool = False,
    ) -> tuple[Path, Path, bytes]:
        project_dir = root / "projects" / "selected"
        project_dir.mkdir(parents=True)
        if configured_external:
            external_runs = root / "external-runs"
            external_runs.mkdir()
            (project_dir / "runs").symlink_to(external_runs, target_is_directory=True)
            run_root = external_runs / "run-001"
        else:
            run_root = project_dir / "runs" / "run-001"
        run_root.mkdir(parents=True)
        self._write_json(
            project_dir / "checkpoint.json",
            {
                "run_id": "run-001",
                "run_root": str(run_root),
                "last_completed_round": 1,
                "best_score": 81.0,
                "best_round": 1,
                "best_round_path": str(run_root / "round_01"),
            },
        )
        source_path = (
            project_dir / "score_history.json"
            if source_artifact == "score_history"
            else run_root / "round_metrics.json"
        )
        source_bytes = self._write_json(source_path, self._history())
        if paired:
            target_path = (
                run_root / "round_metrics.json"
                if source_artifact == "score_history"
                else project_dir / "score_history.json"
            )
            target_path.write_bytes(source_bytes)
        return project_dir, run_root, source_bytes

    @staticmethod
    def _lock(project_dir: Path):
        handle, error = acquire_run_lock(
            project_dir,
            mode="legacy_history_migration",
            model_name="provider-free",
        )
        if error or handle is None:
            raise AssertionError(error or "lock unavailable")
        return handle

    def test_strict_journal_codec_rejects_unknown_or_malformed_fields(self) -> None:
        module = _execution_module()
        payload = {
            "schema_version": 1,
            "kind": "legacy_history_migration",
            "state": "prepared",
            "migration_id": "legacy_" + ("a" * 32),
            "run_id": "run-001",
            "completed_rounds": 1,
            "source_artifact": "score_history",
            "target_artifact": "round_metrics",
            "source_sha256": "1" * 64,
            "source_size": 2,
            "checkpoint_sha256": "2" * 64,
            "checkpoint_size": 2,
            "run_config_sha256": None,
            "run_config_size": None,
            "run_summary_sha256": None,
            "run_summary_size": None,
            "run_root_identity": {
                "configured_storage": False,
                "device": 1,
                "inode": 2,
                "stat_identity_available": True,
            },
            "evidence_path": "/tmp/evidence",
            "evidence_identity": {
                "device": 3,
                "inode": 4,
                "stat_identity_available": True,
            },
            "evidence_manifest_sha256": "3" * 64,
            "target_before_present": False,
        }

        encoded = module.encode_legacy_migration_journal(payload)
        self.assertEqual(module.decode_legacy_migration_journal(encoded), payload)
        invalid = dict(payload)
        invalid["unknown"] = "field"
        with self.assertRaises(module.LegacyMigrationCodecError):
            module.encode_legacy_migration_journal(invalid)
        duplicate = encoded.replace(
            '"schema_version": 1,',
            '"schema_version": 1, "schema_version": 1,',
            1,
        )
        with self.assertRaises(module.LegacyMigrationCodecError):
            module.decode_legacy_migration_journal(duplicate)
        with self.assertRaises(module.LegacyMigrationCodecError):
            module.decode_legacy_migration_journal(
                encoded.replace('"source_size": 2', '"source_size": -1')
            )

    def test_exact_copy_both_directions_and_configured_storage(self) -> None:
        module = _execution_module()
        cases = (
            ("score_history", False),
            ("round_metrics", False),
            ("score_history", True),
            ("round_metrics", True),
        )
        for source_artifact, configured_external in cases:
            with self.subTest(
                source_artifact=source_artifact,
                configured_external=configured_external,
            ):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    project_dir, run_root, source_bytes = self._fixture(
                        root,
                        source_artifact=source_artifact,
                        configured_external=configured_external,
                    )
                    evidence_dir = root / "owner-evidence"
                    target_path = (
                        run_root / "round_metrics.json"
                        if source_artifact == "score_history"
                        else project_dir / "score_history.json"
                    )
                    checkpoint_before = (project_dir / "checkpoint.json").read_bytes()
                    handle = self._lock(project_dir)
                    try:
                        result = module.execute_legacy_history_migration(
                            project_dir,
                            evidence_dir,
                            lock_handle=handle,
                        )
                    finally:
                        release_run_lock(handle)

                    self.assertEqual(result.status, "completed")
                    self.assertFalse(result.recovered)
                    self.assertEqual(result.source_artifact, source_artifact)
                    self.assertEqual(target_path.read_bytes(), source_bytes)
                    self.assertEqual(
                        (evidence_dir / module.EVIDENCE_SOURCE_NAME).read_bytes(),
                        source_bytes,
                    )
                    manifest = json.loads(
                        (evidence_dir / module.EVIDENCE_MANIFEST_NAME).read_text(encoding="utf-8")
                    )
                    receipt = json.loads(
                        (evidence_dir / module.EVIDENCE_RECEIPT_NAME).read_text(encoding="utf-8")
                    )
                    self.assertEqual(manifest["source_sha256"], receipt["target_sha256"])
                    self.assertEqual(manifest["target_artifact"], result.target_artifact)
                    self.assertFalse(receipt["recovered"])
                    self.assertNotIn(str(root), json.dumps(manifest))
                    self.assertNotIn(str(root), json.dumps(receipt))
                    self.assertEqual(
                        (project_dir / "checkpoint.json").read_bytes(), checkpoint_before
                    )
                    self.assertFalse((project_dir / module.LEGACY_MIGRATION_JOURNAL_NAME).exists())
                    if os.name != "nt":
                        self.assertEqual(evidence_dir.stat().st_mode & 0o077, 0)

    def test_execution_requires_owned_lock_and_exact_candidate(self) -> None:
        module = _execution_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, _, _ = self._fixture(root)
            evidence_dir = root / "evidence"
            with self.assertRaises(module.LegacyMigrationExecutionError) as raised:
                module.execute_legacy_history_migration(
                    project_dir,
                    evidence_dir,
                    lock_handle=None,
                )
            self.assertEqual(raised.exception.code, "legacy_migration_lock_required")
            self.assertFalse(evidence_dir.exists())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, _, _ = self._fixture(root, paired=True)
            evidence_dir = root / "evidence"
            handle = self._lock(project_dir)
            try:
                with self.assertRaises(module.LegacyMigrationExecutionError) as raised:
                    module.execute_legacy_history_migration(
                        project_dir,
                        evidence_dir,
                        lock_handle=handle,
                    )
            finally:
                release_run_lock(handle)
            self.assertEqual(raised.exception.code, "legacy_migration_not_eligible")
            self.assertFalse(evidence_dir.exists())
            self.assertFalse((project_dir / module.LEGACY_MIGRATION_JOURNAL_NAME).exists())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, run_root, _ = self._fixture(root)
            evidence_dir = root / "evidence"
            evidence_dir.mkdir()
            marker = evidence_dir / "owner-marker"
            marker.write_text("preserve", encoding="utf-8")
            handle = self._lock(project_dir)
            try:
                with self.assertRaises(module.LegacyMigrationExecutionError) as raised:
                    module.execute_legacy_history_migration(
                        project_dir,
                        evidence_dir,
                        lock_handle=handle,
                    )
            finally:
                release_run_lock(handle)
            self.assertEqual(raised.exception.code, "legacy_migration_evidence_exists")
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
            self.assertFalse((run_root / "round_metrics.json").exists())
            self.assertFalse((project_dir / module.LEGACY_MIGRATION_JOURNAL_NAME).exists())

    def test_interruption_after_journal_recovers_target_receipt_and_cleanup(self) -> None:
        module = _execution_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, run_root, source_bytes = self._fixture(root)
            evidence_dir = root / "evidence"
            target_path = run_root / "round_metrics.json"
            handle = self._lock(project_dir)
            try:
                with (
                    patch.object(
                        module,
                        "_write_target_create_only",
                        side_effect=KeyboardInterrupt,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    module.execute_legacy_history_migration(
                        project_dir,
                        evidence_dir,
                        lock_handle=handle,
                    )
                inspection = module.classify_legacy_migration_recovery(project_dir)
                self.assertEqual(inspection.status, "apply_pending")
                self.assertTrue(inspection.can_recover)
                self.assertFalse(target_path.exists())
                blocker, _ = round_commit_read_blocker(project_dir)
                self.assertEqual(blocker, "legacy_migration_pending")

                result = module.recover_legacy_history_migration(
                    project_dir,
                    lock_handle=handle,
                )
            finally:
                release_run_lock(handle)

            self.assertEqual(result.status, "recovered")
            self.assertTrue(result.recovered)
            self.assertEqual(target_path.read_bytes(), source_bytes)
            receipt = json.loads(
                (evidence_dir / module.EVIDENCE_RECEIPT_NAME).read_text(encoding="utf-8")
            )
            self.assertTrue(receipt["recovered"])
            self.assertFalse((project_dir / module.LEGACY_MIGRATION_JOURNAL_NAME).exists())

    def test_interruption_after_atomic_target_publication_rolls_forward(self) -> None:
        module = _execution_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, run_root, source_bytes = self._fixture(root)
            evidence_dir = root / "evidence"
            target_path = run_root / "round_metrics.json"
            original_write = module._write_target_create_only

            def publish_then_interrupt(*args: object, **kwargs: object) -> None:
                original_write(*args, **kwargs)
                raise KeyboardInterrupt

            handle = self._lock(project_dir)
            try:
                with (
                    patch.object(
                        module,
                        "_write_target_create_only",
                        side_effect=publish_then_interrupt,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    module.execute_legacy_history_migration(
                        project_dir,
                        evidence_dir,
                        lock_handle=handle,
                    )
                self.assertEqual(target_path.read_bytes(), source_bytes)
                self.assertFalse((evidence_dir / module.EVIDENCE_RECEIPT_NAME).exists())
                inspection = module.classify_legacy_migration_recovery(project_dir)
                self.assertEqual(inspection.status, "apply_pending")
                self.assertEqual(inspection.target_state, "exact")

                result = module.recover_legacy_history_migration(
                    project_dir,
                    lock_handle=handle,
                )
            finally:
                release_run_lock(handle)

            self.assertTrue(result.recovered)
            self.assertEqual(target_path.read_bytes(), source_bytes)
            self.assertFalse((project_dir / module.LEGACY_MIGRATION_JOURNAL_NAME).exists())

    def test_receipt_or_cleanup_failure_leaves_a_recoverable_transaction(self) -> None:
        module = _execution_module()
        for failure_stage in ("receipt", "cleanup"):
            with self.subTest(failure_stage=failure_stage):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    project_dir, run_root, source_bytes = self._fixture(root)
                    evidence_dir = root / "evidence"
                    handle = self._lock(project_dir)
                    original_write = module.write_file_text_create_only

                    def fail_receipt(
                        path: Path,
                        content: str,
                        *,
                        anchor: Path | None = None,
                    ) -> None:
                        if path.name == module.EVIDENCE_RECEIPT_NAME:
                            raise OSError("private receipt failure")
                        original_write(path, content, anchor=anchor)

                    try:
                        selected_patch = (
                            patch.object(
                                module,
                                "write_file_text_create_only",
                                side_effect=fail_receipt,
                            )
                            if failure_stage == "receipt"
                            else patch.object(
                                module,
                                "unlink_artifact_file_if_matches",
                                side_effect=KeyboardInterrupt,
                            )
                        )
                        with selected_patch:
                            if failure_stage == "receipt":
                                with self.assertRaises(module.LegacyMigrationExecutionIOError):
                                    module.execute_legacy_history_migration(
                                        project_dir,
                                        evidence_dir,
                                        lock_handle=handle,
                                    )
                            else:
                                with self.assertRaises(KeyboardInterrupt):
                                    module.execute_legacy_history_migration(
                                        project_dir,
                                        evidence_dir,
                                        lock_handle=handle,
                                    )

                        self.assertEqual(
                            (run_root / "round_metrics.json").read_bytes(),
                            source_bytes,
                        )
                        self.assertTrue(
                            (project_dir / module.LEGACY_MIGRATION_JOURNAL_NAME).exists()
                        )
                        recovered = module.recover_legacy_history_migration(
                            project_dir,
                            lock_handle=handle,
                        )
                    finally:
                        release_run_lock(handle)

                    self.assertTrue(recovered.recovered)
                    self.assertTrue((evidence_dir / module.EVIDENCE_RECEIPT_NAME).is_file())
                    self.assertFalse((project_dir / module.LEGACY_MIGRATION_JOURNAL_NAME).exists())

    def test_third_generation_target_conflict_is_preserved(self) -> None:
        module = _execution_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, run_root, _ = self._fixture(root)
            evidence_dir = root / "evidence"
            target_path = run_root / "round_metrics.json"
            handle = self._lock(project_dir)
            try:
                with (
                    patch.object(
                        module,
                        "_write_target_create_only",
                        side_effect=KeyboardInterrupt,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    module.execute_legacy_history_migration(
                        project_dir,
                        evidence_dir,
                        lock_handle=handle,
                    )
                third_generation = b"[]\n"
                target_path.write_bytes(third_generation)

                inspection = module.classify_legacy_migration_recovery(project_dir)
                self.assertEqual(inspection.status, "conflict")
                self.assertFalse(inspection.can_recover)
                with self.assertRaises(module.LegacyMigrationRecoveryError) as raised:
                    module.recover_legacy_history_migration(
                        project_dir,
                        lock_handle=handle,
                    )
            finally:
                release_run_lock(handle)

            self.assertEqual(raised.exception.code, "legacy_migration_target_conflict")
            self.assertEqual(target_path.read_bytes(), third_generation)
            self.assertTrue((project_dir / module.LEGACY_MIGRATION_JOURNAL_NAME).exists())
            self.assertFalse((evidence_dir / module.EVIDENCE_RECEIPT_NAME).exists())

    def test_changed_checkpoint_blocks_recovery_without_target_write(self) -> None:
        module = _execution_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, run_root, _ = self._fixture(root)
            evidence_dir = root / "evidence"
            handle = self._lock(project_dir)
            try:
                with (
                    patch.object(
                        module,
                        "_write_target_create_only",
                        side_effect=KeyboardInterrupt,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    module.execute_legacy_history_migration(
                        project_dir,
                        evidence_dir,
                        lock_handle=handle,
                    )
                checkpoint = json.loads(
                    (project_dir / "checkpoint.json").read_text(encoding="utf-8")
                )
                checkpoint["best_score"] = 82.0
                self._write_json(project_dir / "checkpoint.json", checkpoint)

                inspection = module.classify_legacy_migration_recovery(project_dir)
                self.assertEqual(inspection.status, "invalid")
                self.assertFalse(inspection.can_recover)
                with self.assertRaises(module.LegacyMigrationRecoveryError):
                    module.recover_legacy_history_migration(
                        project_dir,
                        lock_handle=handle,
                    )
            finally:
                release_run_lock(handle)

            self.assertFalse((run_root / "round_metrics.json").exists())
            self.assertTrue((project_dir / module.LEGACY_MIGRATION_JOURNAL_NAME).exists())
            self.assertFalse((evidence_dir / module.EVIDENCE_RECEIPT_NAME).exists())

    def test_normal_entry_rolls_pending_migration_forward_under_new_lock(self) -> None:
        module = _execution_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, run_root, source_bytes = self._fixture(root)
            evidence_dir = root / "evidence"
            first_handle = self._lock(project_dir)
            try:
                with (
                    patch.object(
                        module,
                        "_write_target_create_only",
                        side_effect=KeyboardInterrupt,
                    ),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    module.execute_legacy_history_migration(
                        project_dir,
                        evidence_dir,
                        lock_handle=first_handle,
                    )
            finally:
                release_run_lock(first_handle)

            recovery_handle = self._lock(project_dir)
            console = Console(record=True)
            try:
                result = cli_module._recover_pending_round_commit(
                    console=console,
                    project_dir=project_dir,
                    run_lock_handle=recovery_handle,
                )
            finally:
                release_run_lock(recovery_handle)

            self.assertEqual(result.status, "recovered")
            self.assertEqual((run_root / "round_metrics.json").read_bytes(), source_bytes)
            self.assertIn("Recovered pending legacy history migration", console.export_text())
            self.assertFalse((project_dir / module.LEGACY_MIGRATION_JOURNAL_NAME).exists())

    def test_evidence_failure_never_creates_project_transaction_or_target(self) -> None:
        module = _execution_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, run_root, _ = self._fixture(root)
            evidence_dir = root / "evidence"
            handle = self._lock(project_dir)
            try:
                with (
                    patch.object(
                        module,
                        "_write_evidence_manifest",
                        side_effect=OSError("private evidence failure"),
                    ),
                    self.assertRaises(module.LegacyMigrationExecutionIOError) as raised,
                ):
                    module.execute_legacy_history_migration(
                        project_dir,
                        evidence_dir,
                        lock_handle=handle,
                    )
            finally:
                release_run_lock(handle)

            self.assertEqual(raised.exception.code, "legacy_migration_evidence_write_failed")
            self.assertFalse((project_dir / module.LEGACY_MIGRATION_JOURNAL_NAME).exists())
            self.assertFalse((run_root / "round_metrics.json").exists())
            self.assertFalse((evidence_dir / module.EVIDENCE_MANIFEST_NAME).exists())
            self.assertNotIn(str(root), str(raised.exception))


if __name__ == "__main__":
    unittest.main()
