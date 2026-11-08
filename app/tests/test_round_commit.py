from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.round_commit import (
    MAX_ROUND_COMMIT_JOURNAL_BYTES,
    ROUND_COMMIT_ARTIFACT_NAMES,
    AfterImage,
    RoundCommitCodecError,
    build_best_output_after_image,
    build_checkpoint_after_image,
    build_history_after_image,
    build_project_memory_after_image,
    build_research_state_after_image,
    build_run_config_after_image,
    build_run_summary_after_image,
    decode_round_commit_journal,
    encode_round_commit_journal,
)
from src.storage import update_project_memory, update_research_state, write_score_history


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class RoundCommitBuilderTests(unittest.TestCase):
    def test_history_after_image_is_deterministic_and_does_not_mutate_inputs(self) -> None:
        history = [{"round": 1, "score": 50.0, "nested": {"called": True}}]
        metric = {"round": 2, "score": 60.0, "errors": []}
        original_history = copy.deepcopy(history)
        original_metric = copy.deepcopy(metric)

        first = build_history_after_image(history, metric, round_index=2)
        second = build_history_after_image(history, metric, round_index=2)

        self.assertIsInstance(first, AfterImage)
        self.assertEqual(first, second)
        self.assertEqual(first.value, [*history, metric])
        self.assertEqual(first.text, json.dumps([*history, metric], indent=2))
        self.assertEqual(first.sha256, _sha256(first.text))
        self.assertEqual(history, original_history)
        self.assertEqual(metric, original_metric)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "score_history.json"
            write_score_history(path, first.value)
            self.assertEqual(path.read_text(encoding="utf-8"), first.text)

    def test_history_builder_rejects_ambiguous_or_invalid_rounds(self) -> None:
        cases = {
            "boolean round": ([{"round": True}], {"round": 2}, 2),
            "non-increasing history": (
                [{"round": 1}, {"round": 1}],
                {"round": 2},
                2,
            ),
            "gap before append": ([{"round": 1}], {"round": 3}, 3),
            "metric mismatch": ([{"round": 1}], {"round": 3}, 2),
            "non-integer metric round": ([{"round": 1}], {"round": 2.0}, 2),
            "boolean target": ([{"round": 1}], {"round": 2}, True),
            "non-object metric": ([{"round": 1}], [], 2),
        }
        for case, (history, metric, round_index) in cases.items():
            with self.subTest(case=case), self.assertRaises(RoundCommitCodecError):
                build_history_after_image(history, metric, round_index=round_index)

    def test_best_output_builder_matches_storage_normalization(self) -> None:
        image = build_best_output_after_image("  revised result  \n")

        self.assertEqual(image.text, "revised result\n")
        self.assertEqual(image.value, "revised result\n")
        self.assertEqual(image.sha256, _sha256("revised result\n"))
        with self.assertRaises(RoundCommitCodecError):
            build_best_output_after_image("\ud800")

    def test_memory_after_image_matches_existing_writer_bytes(self) -> None:
        summary = {
            "strongest": "A bounded mechanism.",
            "criticism": "The baseline is incomplete.",
            "unresolved": "Failure recovery remains open.",
            "next_action": "Run one controlled ablation.",
            "best_score": "88.00",
        }
        existing = "Manual notes that must remain.\n"
        image = build_project_memory_after_image(
            existing,
            round_index=2,
            summary=summary,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.md"
            path.write_text(existing, encoding="utf-8")
            update_project_memory(memory_path=path, round_index=2, summary=summary)

            self.assertEqual(path.read_text(encoding="utf-8"), image.text)
        self.assertEqual(image.sha256, _sha256(image.text))

    def test_research_state_after_image_matches_existing_writer_value_and_bytes(self) -> None:
        kwargs = {
            "round_index": 2,
            "best_score": 88,
            "revised_output": "We propose a bounded mechanism and controlled experiment.",
            "review_output": "The largest blocker is missing baseline evidence.",
            "judge_output": "An open question is whether the mechanism generalizes.",
            "topic_keywords": ["bounded"],
        }
        image = build_research_state_after_image(**kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research_state.json"
            state = update_research_state(state_path=path, **kwargs)

            self.assertEqual(state, image.value)
            self.assertEqual(path.read_text(encoding="utf-8"), image.text)
        self.assertEqual(image.sha256, _sha256(image.text))

    def test_object_after_image_wrappers_are_deterministic_and_strict(self) -> None:
        value = {"run_id": "run-1", "nested": {"items": [1, True, None]}}
        builders = (
            build_checkpoint_after_image,
            build_run_summary_after_image,
            build_run_config_after_image,
        )
        for builder in builders:
            with self.subTest(builder=builder.__name__):
                original = copy.deepcopy(value)
                first = builder(value)
                second = builder(value)
                self.assertEqual(first, second)
                self.assertEqual(first.text, json.dumps(value, indent=2))
                self.assertEqual(first.value, value)
                self.assertIsNot(first.value, value)
                self.assertEqual(value, original)

        invalid_values = (
            [],
            {"nonfinite": float("nan")},
            {"nonfinite": float("inf")},
            {1: "non-string key"},
            {"unsupported": Path("private")},
            {"not strict JSON": ("tuple",)},
        )
        for value in invalid_values:
            with self.subTest(value=repr(value)), self.assertRaises(RoundCommitCodecError):
                build_checkpoint_after_image(value)  # type: ignore[arg-type]


class RoundCommitCodecTests(unittest.TestCase):
    def _valid_payload(self) -> dict[str, object]:
        metric = {"round": 2, "score": 60.0, "errors": []}
        score_history = build_history_after_image(
            [{"round": 1, "score": 50.0}],
            metric,
            round_index=2,
        )
        round_metrics = build_history_after_image(
            [{"round": 1, "score": 50.0}],
            metric,
            round_index=2,
        )
        best_output = build_best_output_after_image("revised round 2")
        memory = build_project_memory_after_image(
            "Manual notes.\n",
            round_index=2,
            summary={
                "strongest": "A bounded mechanism.",
                "criticism": "The baseline is incomplete.",
                "unresolved": "Failure recovery remains open.",
                "next_action": "Run one controlled ablation.",
                "best_score": "60.00",
            },
        )
        research_state = build_research_state_after_image(
            round_index=2,
            best_score=60.0,
            revised_output="We propose a bounded mechanism.",
            review_output="The blocker is baseline quality.",
            judge_output="An open question remains.",
        )
        checkpoint = build_checkpoint_after_image(
            {
                "run_id": "run-1",
                "last_completed_round": 2,
                "best_score": 60.0,
                "can_resume": True,
            }
        )
        before = _sha256("before")
        return {
            "schema_version": 1,
            "kind": "round_commit",
            "state": "prepared",
            "transaction_id": "txn_12345678",
            "run_id": "run-1",
            "run_root": "/tmp/project/runs/run-1",
            "run_root_identity": {
                "configured_storage": True,
                "device": 123,
                "inode": 456,
                "stat_identity_available": True,
            },
            "round": 2,
            "attempt_id": "attempt_12345678",
            "run_config_sha256": "a" * 64,
            "round_metric": metric,
            "artifacts": {
                "score_history": {
                    "before_present": True,
                    "before_sha256": before,
                    "after_sha256": score_history.sha256,
                },
                "round_metrics": {
                    "before_present": True,
                    "before_sha256": before,
                    "after_sha256": round_metrics.sha256,
                },
                "best_output": {
                    "write": True,
                    "before_present": True,
                    "before_sha256": before,
                    "after_sha256": best_output.sha256,
                },
                "memory": {
                    "before_present": True,
                    "before_sha256": before,
                    "after_sha256": memory.sha256,
                    "after_text": memory.text,
                },
                "research_state": {
                    "before_present": True,
                    "before_sha256": before,
                    "after_sha256": research_state.sha256,
                    "after_value": research_state.value,
                },
                "checkpoint": {
                    "before_present": True,
                    "before_sha256": before,
                    "after_sha256": checkpoint.sha256,
                    "after_value": checkpoint.value,
                },
            },
        }

    def test_valid_payload_round_trips_deterministically(self) -> None:
        payload = self._valid_payload()
        original = copy.deepcopy(payload)

        first = encode_round_commit_journal(payload)
        decoded = decode_round_commit_journal(first)
        second = encode_round_commit_journal(decoded)
        shuffled = {key: payload[key] for key in reversed(payload)}
        artifacts = payload["artifacts"]
        shuffled["artifacts"] = {
            name: {
                key: artifacts[name][key]  # type: ignore[index]
                for key in reversed(artifacts[name])  # type: ignore[index]
            }
            for name in reversed(artifacts)  # type: ignore[arg-type]
        }

        self.assertEqual(first, second)
        self.assertEqual(first, encode_round_commit_journal(shuffled))
        self.assertEqual(decoded, payload)
        self.assertEqual(payload, original)
        self.assertLessEqual(len(first.encode("utf-8")), MAX_ROUND_COMMIT_JOURNAL_BYTES)
        self.assertEqual(
            set(decoded["artifacts"]),
            set(ROUND_COMMIT_ARTIFACT_NAMES),
        )

    def test_codec_accepts_bytes_and_missing_before_generations(self) -> None:
        payload = self._valid_payload()
        for artifact_name in ROUND_COMMIT_ARTIFACT_NAMES:
            record = payload["artifacts"][artifact_name]  # type: ignore[index]
            record["before_present"] = False
            record["before_sha256"] = None
        identity = payload["run_root_identity"]
        identity["stat_identity_available"] = False  # type: ignore[index]
        identity["device"] = None  # type: ignore[index]
        identity["inode"] = None  # type: ignore[index]

        encoded = encode_round_commit_journal(payload)
        decoded = decode_round_commit_journal(encoded.encode("utf-8"))

        self.assertEqual(decoded, payload)

    def test_codec_rejects_unknown_or_missing_top_level_fields(self) -> None:
        base = self._valid_payload()
        mutations = {
            "unknown field": lambda value: value.update({"extra": True}),
            "missing field": lambda value: value.pop("state"),
            "wrong schema": lambda value: value.update({"schema_version": 2}),
            "boolean schema": lambda value: value.update({"schema_version": True}),
            "floating schema": lambda value: value.update({"schema_version": 1.0}),
            "wrong kind": lambda value: value.update({"kind": "run_finalize"}),
            "wrong state": lambda value: value.update({"state": "committed"}),
        }
        for case, mutate in mutations.items():
            payload = copy.deepcopy(base)
            mutate(payload)
            with self.subTest(case=case), self.assertRaises(RoundCommitCodecError):
                encode_round_commit_journal(payload)

    def test_codec_rejects_invalid_id_path_round_digest_and_metric_fields(self) -> None:
        base = self._valid_payload()
        mutations = {
            "short transaction id": lambda value: value.update({"transaction_id": "short"}),
            "invalid transaction id": lambda value: value.update(
                {"transaction_id": "INVALID VALUE"}
            ),
            "invalid run id": lambda value: value.update({"run_id": "../run"}),
            "empty root": lambda value: value.update({"run_root": ""}),
            "nul root": lambda value: value.update({"run_root": "/tmp/run\u0000tail"}),
            "identity not object": lambda value: value.update({"run_root_identity": []}),
            "identity boolean device": lambda value: value["run_root_identity"].update(  # type: ignore[union-attr]
                {"device": True}
            ),
            "unavailable identity with values": lambda value: value["run_root_identity"].update(  # type: ignore[union-attr]
                {"stat_identity_available": False}
            ),
            "boolean round": lambda value: value.update({"round": True}),
            "zero round": lambda value: value.update({"round": 0}),
            "invalid attempt": lambda value: value.update({"attempt_id": "bad"}),
            "invalid config digest": lambda value: value.update({"run_config_sha256": "A" * 64}),
            "metric round mismatch": lambda value: value.update(
                {"round_metric": {"round": 3, "score": 60}}
            ),
            "metric round not integer": lambda value: value.update(
                {"round_metric": {"round": 2.0, "score": 60}}
            ),
            "metric not object": lambda value: value.update({"round_metric": []}),
        }
        for case, mutate in mutations.items():
            payload = copy.deepcopy(base)
            mutate(payload)
            with self.subTest(case=case), self.assertRaises(RoundCommitCodecError):
                encode_round_commit_journal(payload)

    def test_codec_rejects_unknown_artifacts_and_record_fields(self) -> None:
        base = self._valid_payload()
        cases: dict[str, dict[str, object]] = {}

        missing = copy.deepcopy(base)
        missing["artifacts"].pop("memory")  # type: ignore[union-attr]
        cases["missing artifact"] = missing

        extra = copy.deepcopy(base)
        extra["artifacts"]["arbitrary_path"] = {}  # type: ignore[index]
        cases["unknown artifact"] = extra

        unknown_record_field = copy.deepcopy(base)
        unknown_record_field["artifacts"]["memory"]["path"] = "/private"  # type: ignore[index]
        cases["unknown record field"] = unknown_record_field

        missing_record_field = copy.deepcopy(base)
        missing_record_field["artifacts"]["checkpoint"].pop("after_value")  # type: ignore[index]
        cases["missing record field"] = missing_record_field

        for case, payload in cases.items():
            with self.subTest(case=case), self.assertRaises(RoundCommitCodecError):
                encode_round_commit_journal(payload)

    def test_codec_rejects_bad_before_and_after_digests(self) -> None:
        base = self._valid_payload()
        cases: dict[str, dict[str, object]] = {}

        absent_with_digest = copy.deepcopy(base)
        record = absent_with_digest["artifacts"]["memory"]  # type: ignore[index]
        record["before_present"] = False
        cases["absent with digest"] = absent_with_digest

        present_without_digest = copy.deepcopy(base)
        present_without_digest["artifacts"]["memory"]["before_sha256"] = None  # type: ignore[index]
        cases["present without digest"] = present_without_digest

        malformed_digest = copy.deepcopy(base)
        malformed_digest["artifacts"]["score_history"]["after_sha256"] = "A" * 64  # type: ignore[index]
        cases["malformed digest"] = malformed_digest

        memory_mismatch = copy.deepcopy(base)
        memory_mismatch["artifacts"]["memory"]["after_text"] += "changed"  # type: ignore[index]
        cases["memory after mismatch"] = memory_mismatch

        research_mismatch = copy.deepcopy(base)
        research_mismatch["artifacts"]["research_state"]["after_value"]["round"] = 9  # type: ignore[index]
        cases["research after mismatch"] = research_mismatch

        checkpoint_mismatch = copy.deepcopy(base)
        checkpoint_mismatch["artifacts"]["checkpoint"]["after_value"]["can_resume"] = False  # type: ignore[index]
        cases["checkpoint after mismatch"] = checkpoint_mismatch

        non_boolean_write = copy.deepcopy(base)
        non_boolean_write["artifacts"]["best_output"]["write"] = 1  # type: ignore[index]
        cases["non-boolean write"] = non_boolean_write

        for case, payload in cases.items():
            with self.subTest(case=case), self.assertRaises(RoundCommitCodecError):
                encode_round_commit_journal(payload)

    def test_decoder_rejects_duplicate_keys_nonfinite_constants_and_invalid_utf8(self) -> None:
        invalid_inputs = {
            "duplicate key": '{"schema_version":1,"schema_version":1}',
            "nan": '{"value":NaN}',
            "positive infinity": '{"value":Infinity}',
            "negative infinity": '{"value":-Infinity}',
            "invalid utf8": b"\xff\xfe",
            "unpaired surrogate": self._encoded_with_unpaired_surrogate(),
        }
        for case, data in invalid_inputs.items():
            with self.subTest(case=case), self.assertRaises(RoundCommitCodecError):
                decode_round_commit_journal(data)

    def _encoded_with_unpaired_surrogate(self) -> str:
        payload = self._valid_payload()
        payload["artifacts"]["memory"]["after_text"] = "\ud800"  # type: ignore[index]
        payload["artifacts"]["memory"]["after_sha256"] = "a" * 64  # type: ignore[index]
        return json.dumps(payload)

    def test_codec_rejects_excessive_size_and_nesting(self) -> None:
        with self.assertRaises(RoundCommitCodecError):
            decode_round_commit_journal(b" " * (MAX_ROUND_COMMIT_JOURNAL_BYTES + 1))

        payload = self._valid_payload()
        nested: object = "leaf"
        for _ in range(130):
            nested = {"child": nested}
        payload["round_metric"]["nested"] = nested  # type: ignore[index]
        with self.assertRaises(RoundCommitCodecError):
            encode_round_commit_journal(payload)


if __name__ == "__main__":
    unittest.main()
