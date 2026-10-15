"""Compare local hot paths with their original algorithms using synthetic data only."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from difflib import SequenceMatcher
from pathlib import Path
from unittest.mock import patch


def legacy_similarity(left: str, right: str) -> float | None:
    left = " ".join(str(left or "").lower().split())
    right = " ".join(str(right or "").lower().split())
    if not left or not right:
        return None
    return round(SequenceMatcher(None, left, right).ratio(), 3)


def legacy_changed_lines(before: str, after: str) -> int | None:
    if not before.strip() and not after.strip():
        return None
    return sum(
        end_a - start_a + end_b - start_b
        for tag, start_a, end_a, start_b, end_b in SequenceMatcher(
            None, before.splitlines(), after.splitlines()
        ).get_opcodes()
        if tag != "equal"
    )


def measure(call, repeats: int) -> dict:
    call()  # Warm both implementations before collecting timings.
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        call()
        samples.append((time.perf_counter() - started) * 1000)
    # Allocation tracing runs separately so it does not distort the timing samples.
    tracemalloc.start()
    try:
        call()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {"median_ms": round(statistics.median(samples), 3), "peak_python_bytes": peak}


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=positive_int, default=5)
    parser.add_argument("--log-lines", type=positive_int, default=100_000)
    parser.add_argument("--text-lines", type=positive_int, default=1000)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src import metrics, storage

    result = {"python": sys.version.split()[0], "repeats": args.repeats, "synthetic_only": True}
    with tempfile.TemporaryDirectory(prefix="ara-performance-") as temporary:
        log = Path(temporary) / "run.log"
        line = "2026-10-15 round=12 stage=review 研究进度 " + "x" * 80 + "\n"
        log.write_text(line * args.log_lines, encoding="utf-8")

        def original_tail():
            return "\n".join(storage.read_regular_text(log).splitlines()[-120:])

        def optimized_tail():
            return storage.tail_file_lines(log, 120)

        if original_tail() != optimized_tail():
            raise AssertionError("log tail output differs")
        result["log_tail"] = {
            "file_bytes": log.stat().st_size,
            "returned_lines": min(args.log_lines, 120),
            "original": measure(original_tail, args.repeats),
            "optimized": measure(optimized_tail, args.repeats),
        }

        roots = {Path(temporary) / f"project-{i}": Path(temporary) for i in range(500)}
        target = Path(temporary) / "project-499" / "runs" / "run" / "output.json"

        def original_lookup():
            values = []
            for _ in range(50):
                path = storage._lexical_absolute(target)
                matches = []
                for root, anchor in roots.items():
                    try:
                        path.relative_to(root)
                    except ValueError:
                        continue
                    matches.append((len(root.parts), anchor))
                values.append(max(matches, default=(0, None), key=lambda item: item[0])[1])
            return values

        def optimized_lookup():
            return [storage._registered_artifact_anchor(target) for _ in range(50)]

        with patch.object(storage, "_ARTIFACT_BOUNDARIES", roots):
            if original_lookup() != optimized_lookup():
                raise AssertionError("artifact boundary lookup differs")
            result["artifact_boundary_lookup"] = {
                "registered_roots": len(roots),
                "lookups_per_sample": 50,
                "original": measure(original_lookup, args.repeats),
                "optimized": measure(optimized_lookup, args.repeats),
            }

    text = "Research plan with reproducible evaluation and clear limitations.\n" * args.text_lines

    def evolution():
        return metrics.build_round_evolution_metrics(
            current_draft=text,
            current_revised=text,
            current_judge=text,
            previous_draft=text,
            previous_revised=text,
            previous_judge=text,
            current_score=80,
            previous_score=80,
        )

    optimized_output = evolution()
    optimized = measure(evolution, args.repeats)
    with (
        patch.object(metrics, "_similarity_ratio", legacy_similarity),
        patch.object(metrics, "_changed_line_count", legacy_changed_lines),
    ):
        if evolution() != optimized_output:
            raise AssertionError("evolution metrics differ")
        original = measure(evolution, args.repeats)
    result["unchanged_round_metrics"] = {
        "chars_per_output": len(text),
        "original": original,
        "optimized": optimized,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
