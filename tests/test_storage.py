from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.storage import (
    get_memory_for_prompt,
    parse_score,
    read_json_file,
    update_project_memory,
    write_interrupted_report,
    write_json_file,
)


class StorageTests(unittest.TestCase):
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
            invalid.write_text("{not json", encoding="utf-8")

            self.assertEqual(read_json_file(missing), {})
            self.assertEqual(read_json_file(invalid), {})

            target = root / "nested" / "state.json"
            write_json_file(target, {"round": 2, "score": 91})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["score"], 91)

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
            self.assertIn(".venv/bin/python -m src.main --resume", content)


if __name__ == "__main__":
    unittest.main()
