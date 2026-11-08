from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from src import legacy_migration as legacy_migration_module
from src.legacy_migration import (
    LEGACY_MIGRATION_CLASSIFICATIONS,
    LEGACY_MIGRATION_REPORT_KEYS,
    LEGACY_MIGRATION_REPORT_SCHEMA_VERSION,
    LegacyMigrationInspection,
    build_legacy_migration_report,
    classify_legacy_history_migration,
    format_legacy_migration_report,
)
from src.round_attempts import (
    STAGE_ORDER,
    create_round_attempt,
    mark_attempt_ready_to_publish,
    mark_attempt_stopped,
    persist_attempt_stage,
    publish_attempt,
)
from src.round_commit_recovery import RoundCommitRecoveryInspection


class LegacyMigrationClassifierTests(unittest.TestCase):
    def _fixture(
        self,
        root: Path,
        *,
        rounds: int = 1,
        score_history: list[object] | None = None,
        round_metrics: list[object] | None = None,
        external_runs: bool = False,
    ) -> tuple[Path, Path]:
        project_dir = root / "project"
        project_dir.mkdir()
        if external_runs:
            external_root = root / "external-runs"
            external_root.mkdir()
            (project_dir / "runs").symlink_to(external_root, target_is_directory=True)
            run_root = external_root / "run-001"
        else:
            run_root = project_dir / "runs" / "run-001"
        run_root.mkdir(parents=True)
        checkpoint = {
            "run_id": "run-001",
            "run_root": str(run_root),
            "last_completed_round": rounds,
            "best_score": 81.0,
            "best_round": 1,
            "best_round_path": str(run_root / "round_01"),
        }
        self._write_json(project_dir / "checkpoint.json", checkpoint)
        if score_history is not None:
            self._write_json(project_dir / "score_history.json", score_history)
        if round_metrics is not None:
            self._write_json(run_root / "round_metrics.json", round_metrics)
        return project_dir, run_root

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")

    @staticmethod
    def _history(*rounds: int, scores: tuple[float, ...] | None = None) -> list[object]:
        selected_scores = scores or tuple(80.0 + round_index for round_index in rounds)
        return [
            {
                "round": round_index,
                "score": score,
                "improved": round_index == 1,
                "successful_research_round": True,
            }
            for round_index, score in zip(rounds, selected_scores, strict=True)
        ]

    @staticmethod
    def _snapshot(root: Path) -> dict[str, tuple[str, bytes | None]]:
        snapshot: dict[str, tuple[str, bytes | None]] = {}
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                snapshot[relative] = ("link", os.readlink(path).encode())
            elif path.is_dir():
                snapshot[relative] = ("directory", None)
            else:
                snapshot[relative] = ("file", path.read_bytes())
        return snapshot

    def _attempt(self, run_root: Path, *, state: str) -> None:
        attempt_dir = create_round_attempt(
            run_root=run_root,
            round_index=2,
            run_config_sha256="0" * 64,
            attempt_id="attempt01",
            created_at="2026-07-24T00:00:00+00:00",
        )
        if state == "active":
            return
        if state == "stopped":
            mark_attempt_stopped(
                attempt_dir,
                "USER_STOPPED",
                updated_at="2026-07-24T00:00:01+00:00",
            )
            return
        for stage in STAGE_ORDER:
            persist_attempt_stage(
                attempt_dir,
                stage,
                f"{stage} output",
                updated_at="2026-07-24T00:00:01+00:00",
            )
        mark_attempt_ready_to_publish(
            attempt_dir,
            updated_at="2026-07-24T00:00:02+00:00",
        )
        if state == "ready":
            return
        if state == "published":
            publish_attempt(
                attempt_dir,
                updated_at="2026-07-24T00:00:03+00:00",
            )

    def _design_row(
        self,
        root: Path,
        row: str,
        *,
        external_runs: bool,
    ) -> tuple[Path, Path]:
        exact = self._history(1, scores=(81.0,))
        if row == "L01":
            project_dir, run_root = self._fixture(
                root,
                score_history=exact,
                round_metrics=exact,
                external_runs=external_runs,
            )
        elif row == "L02":
            project_dir, run_root = self._fixture(
                root,
                score_history=exact,
                external_runs=external_runs,
            )
        elif row in {"L03", "L08"}:
            project_dir, run_root = self._fixture(
                root,
                rounds=2,
                score_history=exact,
                external_runs=external_runs,
            )
            if row == "L08":
                checkpoint = json.loads(
                    (project_dir / "checkpoint.json").read_text(encoding="utf-8")
                )
                checkpoint.pop("best_score")
                self._write_json(project_dir / "checkpoint.json", checkpoint)
        elif row == "L04":
            project_dir, run_root = self._fixture(
                root,
                score_history=exact,
                round_metrics=[],
                external_runs=external_runs,
            )
        elif row == "L05":
            project_dir, run_root = self._fixture(
                root,
                score_history=exact,
                round_metrics=self._history(1, scores=(80.0,)),
                external_runs=external_runs,
            )
        elif row == "L06":
            project_dir, run_root = self._fixture(
                root,
                score_history=self._history(1, 2, scores=(81.0, 82.0)),
                external_runs=external_runs,
            )
        elif row == "L07":
            project_dir, run_root = self._fixture(
                root,
                score_history=self._history(1, scores=(80.0,)),
                external_runs=external_runs,
            )
        elif row in {"L09", "L10", "L11", "L12", "L13", "L14", "L15"}:
            project_dir, run_root = self._fixture(
                root,
                score_history=exact,
                external_runs=external_runs,
            )
            if row == "L09":
                self._attempt(run_root, state="published")
            elif row == "L10":
                canonical = run_root / "round_02"
                canonical.mkdir()
                (canonical / "01_draft.md").write_text("draft", encoding="utf-8")
            elif row == "L11":
                (run_root / "round_02").mkdir()
            elif row == "L12":
                self._attempt(run_root, state="active")
            elif row == "L13":
                self._attempt(run_root, state="active")
                canonical = run_root / "round_02"
                canonical.mkdir()
                (canonical / "01_draft.md").write_text("draft", encoding="utf-8")
            elif row == "L14":
                self._write_json(
                    run_root / "run_summary.json",
                    {"run_id": "run-001", "completed_rounds": 0},
                )
            elif row == "L15":
                self._write_json(
                    run_root / "run_config.json",
                    {
                        "schema_version": 1,
                        "run_id": "run-001",
                        "mode": "diagnostic",
                        "completed_rounds": 0,
                    },
                )
        else:
            project_dir, run_root = self._fixture(
                root,
                external_runs=external_runs,
            )
            if row == "L00":
                self._write_json(
                    project_dir / ".round_commit_transaction.json",
                    {"schema_version": 1, "kind": "round_commit"},
                )
            elif row == "L16":
                self._write_json(
                    run_root / "run_manifest.json",
                    {"run_id": "run-001", "mode": "iterative"},
                )
            elif row == "L17":
                private_checkpoint = root / "private-checkpoint.json"
                private_checkpoint.write_text("{}", encoding="utf-8")
                (project_dir / "checkpoint.json").unlink()
                (project_dir / "checkpoint.json").symlink_to(private_checkpoint)
            elif row == "L18":
                (project_dir / "score_history.json").write_text("{", encoding="utf-8")
            elif row == "L19":
                self._write_json(
                    project_dir / ".round_commit_transaction.json",
                    {"schema_version": 999, "kind": "round_commit"},
                )
            elif row == "L20":
                (project_dir / "checkpoint.json").unlink()
            else:
                self.fail(f"unknown design row fixture: {row}")
        return project_dir, run_root

    def test_all_design_rows_are_read_only_internal_and_external(self) -> None:
        expected = {
            "L00": "current_transaction_pending",
            "L01": "already_transaction_eligible",
            "L02": "exact_missing_history_twin",
            "L03": "incomplete_history_evidence",
            "L04": "history_sequence_conflict",
            "L05": "history_value_conflict",
            "L06": "history_ahead_of_checkpoint",
            "L07": "history_checkpoint_conflict",
            "L08": "partial_history_uncorrelated",
            "L09": "journal_less_published_round",
            "L10": "canonical_without_provenance",
            "L11": "supported_empty_canonical",
            "L12": "attempt_state_owned",
            "L13": "attempt_evidence_conflict",
            "L14": "journal_less_finalize_split",
            "L15": "journal_less_diagnostic_split",
            "L16": "legacy_manifest_compatible",
            "L17": "unsafe_storage_identity",
            "L18": "unsafe_serialization",
            "L19": "unknown_schema",
            "L20": "run_identity_unavailable",
        }
        supported = {"L00", "L01", "L11", "L12", "L16"}
        unsafe = {"L17", "L18"}
        for external_runs in (False, True):
            for row, expected_classification in expected.items():
                with self.subTest(row=row, external_runs=external_runs):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        project_dir, _ = self._design_row(
                            root,
                            row,
                            external_runs=external_runs,
                        )
                        before = self._snapshot(root)
                        if row == "L00":
                            current = RoundCommitRecoveryInspection(
                                status="apply_pending",
                                can_recover=True,
                                journal_present=True,
                                run_id="run-001",
                                round_index=1,
                            )
                            context = patch(
                                "src.legacy_migration.classify_round_commit_recovery",
                                return_value=current,
                            )
                        else:
                            context = nullcontext()
                        with context:
                            inspection = classify_legacy_history_migration(project_dir)
                        report = build_legacy_migration_report(inspection)

                        self.assertEqual(
                            inspection.classification,
                            expected_classification,
                        )
                        expected_status = (
                            "eligible_candidate"
                            if row == "L02"
                            else "already_supported"
                            if row in supported
                            else "unsafe"
                            if row in unsafe
                            else "not_migratable"
                        )
                        self.assertEqual(inspection.status, expected_status)
                        self.assertFalse(report["execution_authorized"])
                        self.assertNotIn(str(root), json.dumps(report, sort_keys=True))
                        self.assertEqual(before, self._snapshot(root))

    def test_exact_missing_history_twin_is_path_redacted_and_read_only(self) -> None:
        for external_runs in (False, True):
            for source_name in ("score_history", "round_metrics"):
                with self.subTest(
                    external_runs=external_runs,
                    source_name=source_name,
                ):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        history = self._history(1, scores=(81.0,))
                        project_dir, run_root = self._fixture(
                            root,
                            score_history=(history if source_name == "score_history" else None),
                            round_metrics=(history if source_name == "round_metrics" else None),
                            external_runs=external_runs,
                        )
                        before = self._snapshot(root)
                        source_path = (
                            project_dir / "score_history.json"
                            if source_name == "score_history"
                            else run_root / "round_metrics.json"
                        )
                        source_bytes = source_path.read_bytes()

                        inspection = classify_legacy_history_migration(project_dir)
                        report = build_legacy_migration_report(inspection)

                        self.assertEqual(inspection.status, "eligible_candidate")
                        self.assertEqual(
                            inspection.classification,
                            "exact_missing_history_twin",
                        )
                        self.assertEqual(inspection.source_artifact, source_name)
                        self.assertEqual(inspection.completed_rounds, 1)
                        self.assertEqual(
                            inspection.source_sha256,
                            hashlib.sha256(source_bytes).hexdigest(),
                        )
                        self.assertEqual(inspection.source_size, len(source_bytes))
                        self.assertEqual(tuple(report), LEGACY_MIGRATION_REPORT_KEYS)
                        self.assertEqual(
                            report["schema_version"],
                            LEGACY_MIGRATION_REPORT_SCHEMA_VERSION,
                        )
                        self.assertFalse(report["execution_authorized"])
                        serialized = json.dumps(report, sort_keys=True)
                        self.assertNotIn(str(root), serialized)
                        self.assertNotIn(str(project_dir), repr(inspection))
                        self.assertEqual(before, self._snapshot(root))

    def test_history_serialization_failures_are_bounded_and_fail_closed(self) -> None:
        nested: object = "private-value"
        for _ in range(130):
            nested = [nested]
        cases: tuple[tuple[str, bytes, int | None], ...] = (
            ("malformed_utf8", b"\xff", None),
            ("malformed_json", b"{", None),
            ("duplicate_key", b'[{"round":1,"round":1}]', None),
            ("nonfinite", b'[{"round":1,"score":NaN}]', None),
            (
                "deep",
                json.dumps([{"round": 1, "nested": nested}]).encode(),
                None,
            ),
            ("bounded", b'[{"round":1,"score":81}]', 8),
        )
        for external_runs in (False, True):
            for name, content, byte_limit in cases:
                with self.subTest(
                    name=name,
                    external_runs=external_runs,
                ):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        project_dir, _ = self._fixture(
                            root,
                            external_runs=external_runs,
                        )
                        (project_dir / "score_history.json").write_bytes(content)
                        before = self._snapshot(root)
                        context = (
                            patch(
                                "src.legacy_migration.MAX_LEGACY_HISTORY_BYTES",
                                byte_limit,
                            )
                            if byte_limit is not None
                            else nullcontext()
                        )
                        with context:
                            inspection = classify_legacy_history_migration(project_dir)
                        self.assertEqual(
                            inspection.classification,
                            "unsafe_serialization",
                        )
                        self.assertEqual(inspection.status, "unsafe")
                        report = build_legacy_migration_report(inspection)
                        self.assertNotIn("private-value", json.dumps(report))
                        self.assertEqual(before, self._snapshot(root))

    def test_unsafe_history_storage_identity_is_never_read_or_reported(self) -> None:
        for external_runs in (False, True):
            for kind in ("symlink", "hard_link", "special_file", "unreadable"):
                with self.subTest(kind=kind, external_runs=external_runs):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        project_dir, _ = self._fixture(
                            root,
                            external_runs=external_runs,
                        )
                        private_source = root / "private-source.json"
                        private_source.write_text(
                            json.dumps(self._history(1, scores=(81.0,))),
                            encoding="utf-8",
                        )
                        history_path = project_dir / "score_history.json"
                        if kind == "symlink":
                            history_path.symlink_to(private_source)
                        elif kind == "hard_link":
                            os.link(private_source, history_path)
                        elif kind == "special_file":
                            if not hasattr(os, "mkfifo"):
                                self.skipTest("FIFO creation is unavailable")
                            os.mkfifo(history_path)
                        else:
                            history_path.write_bytes(private_source.read_bytes())
                            history_path.chmod(0)

                        try:
                            inspection = classify_legacy_history_migration(project_dir)
                            report = build_legacy_migration_report(inspection)
                        finally:
                            if kind == "unreadable":
                                history_path.chmod(0o600)

                        self.assertEqual(
                            inspection.classification,
                            "unsafe_storage_identity",
                        )
                        self.assertEqual(inspection.status, "unsafe")
                        serialized = json.dumps(report, sort_keys=True)
                        self.assertNotIn(str(root), serialized)
                        self.assertNotIn("private-source", serialized)

    def test_missing_target_must_be_a_safe_absent_leaf(self) -> None:
        for external_runs in (False, True):
            for source_name in ("score_history", "round_metrics"):
                with self.subTest(
                    external_runs=external_runs,
                    source_name=source_name,
                ):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        history = self._history(1, scores=(81.0,))
                        project_dir, run_root = self._fixture(
                            root,
                            score_history=(history if source_name == "score_history" else None),
                            round_metrics=(history if source_name == "round_metrics" else None),
                            external_runs=external_runs,
                        )
                        private_target = root / "private-target.json"
                        private_target.write_text("[]", encoding="utf-8")
                        target_path = (
                            run_root / "round_metrics.json"
                            if source_name == "score_history"
                            else project_dir / "score_history.json"
                        )
                        target_path.symlink_to(private_target)

                        inspection = classify_legacy_history_migration(project_dir)
                        report = build_legacy_migration_report(inspection)

                        self.assertEqual(
                            inspection.classification,
                            "unsafe_storage_identity",
                        )
                        serialized = json.dumps(report, sort_keys=True)
                        self.assertNotIn(str(root), serialized)
                        self.assertNotIn("private-target", serialized)

    def test_changed_storage_identity_exception_is_path_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, _ = self._fixture(
                root,
                score_history=self._history(1, scores=(81.0,)),
            )
            original_reader = legacy_migration_module.read_regular_text_bounded
            secret = str(root / "private-secret.json")

            def changed_reader(
                path: Path,
                *,
                max_bytes: int,
                anchor: Path | None = None,
            ) -> str:
                if path.name == "score_history.json":
                    raise OSError(f"changed anchor: {secret}")
                return original_reader(path, max_bytes=max_bytes, anchor=anchor)

            with patch(
                "src.legacy_migration.read_regular_text_bounded",
                side_effect=changed_reader,
            ):
                inspection = classify_legacy_history_migration(project_dir)
            report = build_legacy_migration_report(inspection)

            self.assertEqual(
                inspection.classification,
                "unsafe_storage_identity",
            )
            self.assertNotIn(secret, repr(inspection))
            self.assertNotIn(secret, json.dumps(report, sort_keys=True))

    def test_best_authorities_metadata_and_history_shapes_are_strict(self) -> None:
        cases = (
            ("tolerance_inside", 81.004, None, "exact_missing_history_twin"),
            ("tolerance_outside", 81.006, None, "history_checkpoint_conflict"),
            ("boolean_round", 81.0, True, "incomplete_history_evidence"),
            ("string_round", 81.0, "1", "incomplete_history_evidence"),
            ("missing_best", 81.0, None, "history_checkpoint_conflict"),
            ("matching_metadata", 81.0, None, "exact_missing_history_twin"),
            ("conflicting_metadata", 81.0, None, "journal_less_finalize_split"),
            ("unknown_config", 81.0, None, "unknown_schema"),
        )
        for name, score, round_override, expected in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    history = self._history(1, scores=(score,))
                    if round_override is not None:
                        assert isinstance(history[0], dict)
                        history[0]["round"] = round_override
                    project_dir, run_root = self._fixture(
                        root,
                        score_history=history,
                    )
                    if name == "missing_best":
                        checkpoint = json.loads(
                            (project_dir / "checkpoint.json").read_text(encoding="utf-8")
                        )
                        checkpoint.pop("best_score")
                        self._write_json(project_dir / "checkpoint.json", checkpoint)
                    elif name == "matching_metadata":
                        self._write_json(
                            run_root / "run_config.json",
                            {
                                "schema_version": 1,
                                "run_id": "run-001",
                                "completed_rounds": 1,
                                "best_score": 81.0,
                                "best_round": 1,
                            },
                        )
                        self._write_json(
                            run_root / "run_summary.json",
                            {
                                "run_id": "run-001",
                                "round_count": 1,
                                "best_score": 81.0,
                                "best_round": 1,
                            },
                        )
                    elif name == "conflicting_metadata":
                        self._write_json(
                            run_root / "run_summary.json",
                            {"run_id": "run-001", "best_round": 2},
                        )
                    elif name == "unknown_config":
                        self._write_json(
                            run_root / "run_config.json",
                            {"schema_version": 2, "run_id": "run-001"},
                        )

                    inspection = classify_legacy_history_migration(project_dir)
                    self.assertEqual(inspection.classification, expected)

    def test_attempt_owned_substates_map_without_modification(self) -> None:
        for external_runs in (False, True):
            for state in ("active", "ready", "stopped"):
                with self.subTest(state=state, external_runs=external_runs):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        project_dir, run_root = self._fixture(
                            root,
                            score_history=self._history(1, scores=(81.0,)),
                            external_runs=external_runs,
                        )
                        self._attempt(run_root, state=state)
                        before = self._snapshot(root)

                        inspection = classify_legacy_history_migration(project_dir)

                        self.assertEqual(
                            inspection.classification,
                            "attempt_state_owned",
                        )
                        self.assertEqual(inspection.status, "already_supported")
                        self.assertEqual(before, self._snapshot(root))

    def test_all_current_journal_kinds_distinguish_valid_invalid_and_unknown(
        self,
    ) -> None:
        journal_specs = (
            (
                ".round_commit_transaction.json",
                "round_commit",
                "classify_round_commit_recovery",
            ),
            (
                ".run_finalize_transaction.json",
                "run_finalize",
                "classify_run_finalize_recovery",
            ),
            (
                ".diagnostic_finalize_transaction.json",
                "diagnostic_finalize",
                "classify_diagnostic_finalize_recovery",
            ),
        )
        for journal_name, kind, classifier_name in journal_specs:
            for state in ("valid", "invalid", "unknown"):
                with self.subTest(journal=journal_name, state=state):
                    with tempfile.TemporaryDirectory() as temporary:
                        project_dir, _ = self._fixture(Path(temporary))
                        schema_version = 2 if state == "unknown" else 1
                        self._write_json(
                            project_dir / journal_name,
                            {"schema_version": schema_version, "kind": kind},
                        )
                        if state == "valid":
                            current = RoundCommitRecoveryInspection(
                                status="apply_pending",
                                can_recover=True,
                                journal_present=True,
                                run_id="run-001",
                                round_index=1,
                            )
                            context = patch(
                                f"src.legacy_migration.{classifier_name}",
                                return_value=current,
                            )
                        else:
                            context = nullcontext()
                        with context:
                            inspection = classify_legacy_history_migration(project_dir)
                        expected = (
                            "current_transaction_pending"
                            if state == "valid"
                            else "unsafe_serialization"
                            if state == "invalid"
                            else "unknown_schema"
                        )
                        self.assertEqual(inspection.classification, expected)

    def test_discovery_uses_no_recursive_scan_network_or_mutation_primitive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, _ = self._fixture(
                root,
                score_history=self._history(1, scores=(81.0,)),
            )
            before = self._snapshot(root)
            with (
                patch.object(
                    Path,
                    "rglob",
                    side_effect=AssertionError("recursive scan attempted"),
                ),
                patch.object(
                    Path,
                    "write_text",
                    side_effect=AssertionError("write attempted"),
                ),
                patch.object(
                    Path,
                    "unlink",
                    side_effect=AssertionError("unlink attempted"),
                ),
                patch("socket.socket", side_effect=AssertionError("network attempted")),
            ):
                inspection = classify_legacy_history_migration(project_dir)
            human = format_legacy_migration_report(inspection)

            self.assertEqual(
                inspection.classification,
                "exact_missing_history_twin",
            )
            self.assertNotIn(str(root), human)
            self.assertNotIn("private", human)
            self.assertIn("execution_authorized: false", human)
            self.assertEqual(before, self._snapshot(root))

    def test_stale_and_malformed_locks_are_preserved(self) -> None:
        for state in ("stale", "malformed"):
            with self.subTest(state=state):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    project_dir, _ = self._fixture(
                        root,
                        score_history=self._history(1, scores=(81.0,)),
                    )
                    lock_path = project_dir / "active_run.json"
                    if state == "stale":
                        self._write_json(lock_path, {"pid": 4294967295})
                    else:
                        lock_path.write_text("{", encoding="utf-8")
                    before = lock_path.read_bytes()

                    context = (
                        patch(
                            "src.legacy_migration.is_pid_running",
                            return_value=False,
                        )
                        if state == "stale"
                        else nullcontext()
                    )
                    with context:
                        inspection = classify_legacy_history_migration(project_dir)

                    expected = (
                        "exact_missing_history_twin" if state == "stale" else "unsafe_serialization"
                    )
                    self.assertEqual(inspection.classification, expected)
                    self.assertEqual(lock_path.read_bytes(), before)
                    self.assertTrue(lock_path.exists())

    def test_fixed_classification_matrix_for_history_and_metadata_states(self) -> None:
        cases = (
            (
                "paired_history",
                "already_transaction_eligible",
                self._paired_history,
            ),
            (
                "sparse_single",
                "incomplete_history_evidence",
                self._sparse_single,
            ),
            ("sequence_conflict", "history_sequence_conflict", self._sequence_conflict),
            ("value_conflict", "history_value_conflict", self._value_conflict),
            ("future_round", "history_ahead_of_checkpoint", self._future_round),
            (
                "best_mismatch",
                "history_checkpoint_conflict",
                self._best_mismatch,
            ),
            ("partial_uncorrelated", "partial_history_uncorrelated", self._partial),
            ("finalize_split", "journal_less_finalize_split", self._finalize_split),
            ("diagnostic_split", "journal_less_diagnostic_split", self._diagnostic_split),
            ("legacy_manifest", "legacy_manifest_compatible", self._legacy_manifest),
        )
        self.assertEqual(
            set(LEGACY_MIGRATION_CLASSIFICATIONS),
            {
                "current_transaction_pending",
                "already_transaction_eligible",
                "exact_missing_history_twin",
                "incomplete_history_evidence",
                "history_sequence_conflict",
                "history_value_conflict",
                "history_ahead_of_checkpoint",
                "history_checkpoint_conflict",
                "partial_history_uncorrelated",
                "journal_less_published_round",
                "canonical_without_provenance",
                "supported_empty_canonical",
                "attempt_state_owned",
                "attempt_evidence_conflict",
                "journal_less_finalize_split",
                "journal_less_diagnostic_split",
                "legacy_manifest_compatible",
                "unsafe_storage_identity",
                "unsafe_serialization",
                "unknown_schema",
                "run_identity_unavailable",
            },
        )
        for name, expected, factory in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as temporary:
                    project_dir = factory(Path(temporary))
                    inspection = classify_legacy_history_migration(project_dir)
                    self.assertEqual(inspection.classification, expected)
                    self.assertNotEqual(inspection.status, "eligible_candidate")

    def _paired_history(self, root: Path) -> Path:
        history = self._history(1, scores=(81.0,))
        return self._fixture(
            root,
            score_history=history,
            round_metrics=history,
        )[0]

    def _sparse_single(self, root: Path) -> Path:
        return self._fixture(
            root,
            rounds=2,
            score_history=self._history(1, scores=(81.0,)),
        )[0]

    def _sequence_conflict(self, root: Path) -> Path:
        return self._fixture(
            root,
            score_history=self._history(1, scores=(81.0,)),
            round_metrics=[],
        )[0]

    def _value_conflict(self, root: Path) -> Path:
        return self._fixture(
            root,
            score_history=self._history(1, scores=(81.0,)),
            round_metrics=self._history(1, scores=(80.0,)),
        )[0]

    def _future_round(self, root: Path) -> Path:
        return self._fixture(
            root,
            score_history=self._history(1, 2, scores=(81.0, 82.0)),
        )[0]

    def _best_mismatch(self, root: Path) -> Path:
        return self._fixture(
            root,
            score_history=self._history(1, scores=(80.0,)),
        )[0]

    def _partial(self, root: Path) -> Path:
        project_dir, _ = self._fixture(
            root,
            rounds=2,
            score_history=self._history(1, scores=(81.0,)),
        )
        checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint.pop("best_score")
        self._write_json(project_dir / "checkpoint.json", checkpoint)
        return project_dir

    def _finalize_split(self, root: Path) -> Path:
        project_dir, run_root = self._fixture(
            root,
            score_history=self._history(1, scores=(81.0,)),
        )
        self._write_json(
            run_root / "run_summary.json",
            {"run_id": "run-001", "completed_rounds": 0},
        )
        return project_dir

    def _diagnostic_split(self, root: Path) -> Path:
        project_dir, run_root = self._fixture(
            root,
            score_history=self._history(1, scores=(81.0,)),
        )
        self._write_json(
            run_root / "run_config.json",
            {
                "schema_version": 1,
                "run_id": "run-001",
                "mode": "diagnostic",
                "completed_rounds": 0,
            },
        )
        return project_dir

    def _legacy_manifest(self, root: Path) -> Path:
        project_dir, run_root = self._fixture(root)
        self._write_json(
            run_root / "run_manifest.json",
            {"run_id": "run-001", "mode": "iterative"},
        )
        return project_dir

    def test_current_unknown_unsafe_and_identity_states_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, _ = self._fixture(root)
            journal_path = project_dir / ".round_commit_transaction.json"
            self._write_json(
                journal_path,
                {"schema_version": 999, "kind": "round_commit"},
            )
            inspection = classify_legacy_history_migration(project_dir)
            self.assertEqual(inspection.classification, "unknown_schema")
            self.assertEqual(inspection.status, "not_migratable")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, _ = self._fixture(root)
            (project_dir / "score_history.json").write_text("{", encoding="utf-8")
            inspection = classify_legacy_history_migration(project_dir)
            self.assertEqual(inspection.classification, "unsafe_serialization")
            self.assertEqual(inspection.status, "unsafe")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, _ = self._fixture(root)
            (project_dir / "checkpoint.json").unlink()
            inspection = classify_legacy_history_migration(project_dir)
            self.assertEqual(inspection.classification, "run_identity_unavailable")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, _ = self._fixture(root)
            target = root / "private-checkpoint.json"
            target.write_text("{}", encoding="utf-8")
            (project_dir / "checkpoint.json").unlink()
            (project_dir / "checkpoint.json").symlink_to(target)
            inspection = classify_legacy_history_migration(project_dir)
            self.assertEqual(inspection.classification, "unsafe_storage_identity")
            self.assertNotIn(str(root), json.dumps(build_legacy_migration_report(inspection)))

    def test_valid_current_journal_takes_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_dir, _ = self._fixture(Path(temporary))
            self._write_json(
                project_dir / ".round_commit_transaction.json",
                {"schema_version": 1, "kind": "round_commit"},
            )
            current = RoundCommitRecoveryInspection(
                status="apply_pending",
                can_recover=True,
                journal_present=True,
                run_id="run-001",
                round_index=1,
            )
            with patch(
                "src.legacy_migration.classify_round_commit_recovery",
                return_value=current,
            ):
                inspection = classify_legacy_history_migration(project_dir)
            self.assertEqual(inspection.classification, "current_transaction_pending")
            self.assertEqual(inspection.status, "already_supported")

    def test_live_lock_is_busy_and_never_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir, _ = self._fixture(
                root,
                score_history=self._history(1, scores=(81.0,)),
            )
            lock_path = project_dir / "active_run.json"
            self._write_json(
                lock_path,
                {"schema_version": 1, "pid": os.getpid(), "run_id": "run-001"},
            )
            before = lock_path.read_bytes()

            inspection = classify_legacy_history_migration(project_dir)

            self.assertEqual(inspection.status, "busy")
            self.assertIsNone(inspection.classification)
            self.assertEqual(inspection.reason_codes, ("live_run_lock",))
            self.assertEqual(lock_path.read_bytes(), before)
            self.assertTrue(lock_path.exists())

    def test_next_round_state_mapping_covers_legacy_and_attempt_blockers(self) -> None:
        cases = (
            ("legacy_partial", "canonical_without_provenance"),
            ("legacy_empty_canonical", "supported_empty_canonical"),
            ("attempt_unverifiable", "attempt_evidence_conflict"),
        )
        for state, expected in cases:
            with self.subTest(state=state):
                with tempfile.TemporaryDirectory() as temporary:
                    project_dir, run_root = self._fixture(
                        Path(temporary),
                        score_history=self._history(1, scores=(81.0,)),
                    )
                    if state == "legacy_partial":
                        canonical = run_root / "round_02"
                        canonical.mkdir()
                        (canonical / "01_draft.md").write_text("draft", encoding="utf-8")
                    elif state == "legacy_empty_canonical":
                        (run_root / "round_02").mkdir()
                    else:
                        invalid_attempt = run_root / "partial_rounds" / "round_02" / "unexpected"
                        invalid_attempt.mkdir(parents=True)

                    inspection = classify_legacy_history_migration(project_dir)
                    self.assertEqual(inspection.classification, expected)

    def test_report_builder_enforces_the_fixed_schema(self) -> None:
        inspection = LegacyMigrationInspection(
            status="eligible_candidate",
            classification="exact_missing_history_twin",
            run_id="run-001",
            completed_rounds=1,
            source_artifact="score_history",
            target_artifact="round_metrics",
            source_sha256="0" * 64,
            source_size=2,
            reason_codes=("exact_history_sequence",),
        )
        report = build_legacy_migration_report(inspection)
        self.assertEqual(tuple(report), LEGACY_MIGRATION_REPORT_KEYS)
        self.assertEqual(report["classification"], "exact_missing_history_twin")
        self.assertFalse(report["execution_authorized"])
        invalid_inspections = (
            replace(inspection, status="invented"),
            replace(inspection, classification="invented"),
            replace(inspection, target_artifact=None),
            replace(inspection, source_sha256=None),
            replace(inspection, reason_codes=("private/path",)),
            replace(inspection, run_id="../private"),
        )
        for invalid in invalid_inspections:
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "legacy migration|invalid|unknown"):
                    build_legacy_migration_report(invalid)


if __name__ == "__main__":
    unittest.main()
