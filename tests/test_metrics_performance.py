from __future__ import annotations

import random
import unittest
from difflib import SequenceMatcher
from unittest.mock import patch

import src.metrics as metrics


def reference_similarity(left: str, right: str) -> float | None:
    left_normalized = " ".join(str(left or "").lower().split())
    right_normalized = " ".join(str(right or "").lower().split())
    if not left_normalized or not right_normalized:
        return None
    return round(SequenceMatcher(None, left_normalized, right_normalized).ratio(), 3)


def reference_changed_lines(before: str, after: str) -> int | None:
    if not before.strip() and not after.strip():
        return None
    return sum(
        (before_end - before_start) + (after_end - after_start)
        for tag, before_start, before_end, after_start, after_end in SequenceMatcher(
            None, before.splitlines(), after.splitlines()
        ).get_opcodes()
        if tag != "equal"
    )


class MetricsPerformanceTests(unittest.TestCase):
    def test_fast_paths_preserve_existing_difflib_results(self) -> None:
        corpus = [
            "",
            " \t\n",
            "a",
            "A",
            "a\n",
            "a\r\n",
            "a\n\n",
            "a b",
            " A\tB ",
            "a\nb",
            "a\r\nb",
            "a\v b",
            "研究方法\n实验结果",
            "STRASSE",
            "Straße",
            "A\u00a0B",
            "same line\n" * 40,
            "same line\n" * 39 + "changed line",
            "alpha\nbeta\nalpha\ngamma",
            "gamma\nalpha\nbeta\nalpha",
        ]
        random_source = random.Random(20261015)
        corpus.extend(
            "".join(random_source.choices("abCD 文\n\r\t", k=size))
            for size in (1, 2, 5, 20, 80, 210)
        )
        for left in corpus:
            for right in corpus:
                with self.subTest(left=left, right=right):
                    self.assertEqual(
                        metrics._similarity_ratio(left, right), reference_similarity(left, right)
                    )
                    self.assertEqual(
                        metrics._changed_line_count(left, right),
                        reference_changed_lines(left, right),
                    )

    def test_unchanged_round_avoids_sequence_matching(self) -> None:
        text = "Research plan with reproducible evaluation and clear limitations.\n" * 1000
        with patch.object(
            metrics, "SequenceMatcher", side_effect=AssertionError("unnecessary sequence match")
        ):
            result = metrics.build_round_evolution_metrics(
                current_draft=text,
                current_revised=text,
                current_judge=text,
                previous_draft=text,
                previous_revised=text,
                previous_judge=text,
                current_score=80,
                previous_score=80,
            )
        self.assertTrue(result["has_previous_round"])
        for key in (
            "draft_to_revised_similarity",
            "draft_similarity_to_previous",
            "revised_similarity_to_previous",
            "judge_similarity_to_previous",
        ):
            self.assertEqual(result[key], 1.0)
        self.assertEqual(result["draft_to_revised_changed_lines"], 0)
        self.assertEqual(result["revised_changed_lines_vs_previous"], 0)
        self.assertEqual(result["score_delta_vs_previous"], 0.0)

    def test_equivalent_text_and_empty_inputs_avoid_sequence_matching(self) -> None:
        with patch.object(
            metrics, "SequenceMatcher", side_effect=AssertionError("unnecessary sequence match")
        ):
            self.assertEqual(metrics._similarity_ratio(" A\tB ", "a\nb"), 1.0)
            self.assertIsNone(metrics._similarity_ratio(" \n", "a"))
            self.assertIsNone(metrics._changed_line_count(" \n", "\t"))
            self.assertEqual(metrics._changed_line_count("a\r\nb\r\n", "a\nb\n"), 0)
            self.assertEqual(metrics._changed_line_count("", "a\nb\n"), 2)
            self.assertEqual(metrics._changed_line_count("a\nb\n", ""), 2)
