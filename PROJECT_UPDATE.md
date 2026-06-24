# Phase 10 - Round Evolution Interpretability Metrics

Date: 2026-06-24
Commit: e1eed0afa6ec48d2b633e62160f0a0d0e86d9c27
Branch: master

## Goal

Add lightweight experiment interpretability metrics that help researchers see whether each round meaningfully changes draft/revised/judge text, without changing prompts, provider behavior, scoring semantics, or stop conditions.

## What Changed

New runs now write text evolution metrics into `score_history.json`, `round_metrics.json`, and `run_summary.json`. Run comparison and the Streamlit UI surface aggregate similarity and low-change indicators while preserving legacy metadata compatibility.

## Code

* Added standard-library similarity and changed-line metrics in `src/metrics.py`.
* Recorded per-round `evolution_metrics` in the runner after each scored round.
* Added run-level aggregate evolution totals and comparison fallbacks for legacy or partial metadata.

## UI

* Added average revised similarity and low-change round counts to latest run metadata and run comparison rows.
* Added score delta and similarity fields to the score history table helper.

## Tests

* Added pure metrics tests for similarity, score deltas, and aggregate evolution summaries.
* Extended round-loop tests to verify evolution metrics are written for first and later rounds.
* Extended run comparison and UI helper tests for aggregate similarity fields and privacy-safe display.

## Docs

* Updated README, USER_GUIDE, DEVELOPER_GUIDE, quickstart_zh, and runbook_zh to describe the new interpretability fields and their limits.

## Validation

* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `.venv/bin/python -m pytest tests/test_metrics.py tests/test_round_loop.py::RoundLoopTests::test_round_loop_writes_outputs_and_keeps_best_score tests/test_run_compare.py tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_score_history_rows_flatten_metrics_for_display tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_run_metadata_rows_summarize_latest_run_without_absolute_paths tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_run_comparison_helpers_mask_paths_and_flatten_fields -q`
* `make check`

## Risks / Limitations

* Similarity metrics are interpretability aids only. They do not prove research quality, novelty, or correctness.
* The low-change threshold is a conservative fixed heuristic and should not be treated as a benchmark score.
* Existing old runs remain readable but will only show these fields when round metrics include `evolution_metrics`.

## Recommended Next Phase

Phase 11 - Rubric trend preservation and comparison display.

## Suggested Codex Prompt

Continue with Phase 11. Add schema-additive rubric trend summaries from existing Judge rubric subscores, surface them in run comparison/UI where practical, preserve scoring semantics, update tests/docs/PROJECT_UPDATE.md, validate with `git diff --check`, `.venv/bin/python -m src.main --help`, targeted tests, and `make check`, then commit and push.

# Phase 9 - Partial Next-Round Resume Safety

Date: 2026-06-24
Commit: 770d89fe50351a7908081ae2bfd61e89458b799e
Branch: master

## Goal

Make partial next-round resume behavior safer and more explicit while preserving completed rounds, legacy checkpoint compatibility, and existing research semantics.

## What Changed

Resume now inspects the next-round directory before continuing a run. Missing or empty next-round directories remain resumable, while non-empty next-round directories block resume with a clear fail-safe message that requires user action.

## Code

* Added next-round directory inspection and fail-safe resume blocking in `src/resume.py`.
* Recorded next-round resume safety metadata in runner resume metadata for checkpoint, run config, and summary propagation.
* Preserved completed round files and avoided automatic movement or deletion of partial next-round artifacts.

## UI

* Added partial next-round status to the Streamlit resume helper state.
* Updated resume wording to show next-round status, safety action, and privacy-safe paths.

## Tests

* Added resume tests for partial next-round detection and fail-safe blocking.
* Extended resume tests to verify completed rounds are preserved.
* Added UI helper coverage for partial next-round status display.

## Docs

* Updated README resume guidance.
* Updated `docs/USER_GUIDE.md`, `docs/DEVELOPER_GUIDE.md`, `docs/quickstart_zh.md`, and `docs/runbook_zh.md`.

## Validation

* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `.venv/bin/python -m pytest tests/test_round_loop.py::RoundLoopTests::test_resume_starts_after_last_real_completed_round tests/test_round_loop.py::RoundLoopTests::test_resume_blocks_partial_next_round_without_overwriting tests/test_round_loop.py::RoundLoopTests::test_resume_preview_reports_missing_and_stale_checkpoints tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_progress_resume_and_output_helpers -q`
* `make check`

## Risks / Limitations

* The fail-safe behavior is conservative: users must manually inspect, move, or delete non-empty next-round directories before resuming.
* No automatic quarantine is performed, which avoids hidden file movement but leaves cleanup to the operator.

## Recommended Next Phase

Phase 10 - Documentation and release polish.

## Suggested Codex Prompt

Continue with Phase 10. Update documentation and release notes, preserve existing research semantics, validate with `git diff --check`, `.venv/bin/python -m src.main --help`, targeted documentation checks if applicable, and `make check`, then update `PROJECT_UPDATE.md`, commit, and push.
