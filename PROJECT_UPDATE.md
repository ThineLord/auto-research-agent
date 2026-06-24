# Phase 14 - Mock/Fake Run Mode

Date: 2026-06-24
Commit: fd9f0f88b64cb778aa8d55772a31724dacc51fda
Branch: master

## Goal

Add a deterministic provider-free demo run mode that writes normal run artifacts for CI/docs smoke
coverage without changing real provider behavior, prompt semantics, scoring semantics, or evaluation
logic.

## What Changed

Added `--mock` and `make mock`. Mock mode injects deterministic fake Draft/Review/Revise/Judge
agents into the existing runner, defaults to two rounds unless `--max-rounds` is provided, and marks
artifacts with provider/model metadata `mock` / `mock-deterministic`.

## Code

* Added `src/mock_run.py` with provider-free fake agents and explicit deterministic metadata.
* Wired `--mock` into `src/cli.py` before provider validation so no Ollama, Gemini, network, or API
  key checks are required.
* Added a `make mock` convenience target.

## UI

* No Streamlit UI changes in this phase.

## Tests

* Added focused mock-run tests for CLI parsing, normal artifact writing, and skipped provider client
  creation/discovery.
* Extended CLI argument parsing coverage for `--mock`.

## Docs

* Updated README, USER_GUIDE, DEVELOPER_GUIDE, quickstart_zh, and runbook_zh with mock mode usage
  and limitations.

## Validation

* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `.venv/bin/python -m pytest tests/test_mock_run.py tests/test_round_loop.py::RoundLoopTests::test_parse_args_accepts_mode_and_model_flags -q`
* `make check`

## Risks / Limitations

* Mock scores and rubric fields are synthetic demo signals and must not be interpreted as research
  evaluation results.
* Mock mode writes ignored project runtime artifacts like a normal run; users should inspect outputs
  locally and avoid committing generated run directories.

## Recommended Next Phase

Phase 15 - UI Analytics Dashboard, if a human review agrees that additional dashboard visualization
is more valuable than pausing for release packaging.

## Suggested Codex Prompt

Continue with Phase 15. Design a compact Streamlit analytics dashboard for score, rubric,
similarity, timeout/error, timing, and estimated-token trends using existing artifacts only. Preserve
scoring semantics, keep paths privacy-safe, update tests/docs/PROJECT_UPDATE.md, validate, commit,
and push.

# Phase 13 - Autonomous Cycle Closeout

Date: 2026-06-24
Commit: 80e81fd899eff38741600811b60b2fe66e3ab9d8
Branch: master

## Goal

Close the current autonomous improvement cycle with a repository-level summary, explicit remaining risks, and a practical next roadmap while keeping `PROJECT_UPDATE.md` as the canonical progress log.

## What Changed

Added this closeout section summarizing the safe phases completed in the cycle and identifying where further work becomes lower-value or requires architectural, UX, or methodology decisions.

## Code

* No code changes in this phase.

## UI

* No UI changes in this phase.

## Tests

* No new tests in this phase because this is documentation-only.

## Docs

* Added the autonomous-cycle final summary below.

## Validation

* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `sed -n '1,140p' PROJECT_UPDATE.md`
* `make check`

## Risks / Limitations

* Further dashboard work would benefit from a small UI design pass before adding more columns or charts.
* Real provider token usage and pricing still require provider-level usage metadata or explicit pricing assumptions.
* Any change to evaluation methodology, scoring semantics, prompt behavior, or benchmark interpretation should receive human review.

## Recommended Next Phase

Pause autonomous implementation. Next high-value work should be selected after human review of `PROJECT_UPDATE.md` and the pushed artifacts.

## Suggested Codex Prompt

Review `PROJECT_UPDATE.md`, inspect the current run metadata/analytics features, and decide whether the next safe priority is UI dashboard design, real provider token usage capture, mock run mode, or release packaging.

## Autonomous Cycle Final Summary

### Phases Completed

* Phase 10 - Round Evolution Interpretability Metrics: added per-round text evolution metrics, run-level similarity summaries, comparison/UI fields, tests, and docs.
* Phase 11 - Rubric Trend Summaries: aggregated structured Judge rubric subscores into averages/latest/best/deltas, exposed compact comparison/UI fields, and documented the non-semantic role of these summaries.
* Phase 12 - Single-Run Analytics Export: added provider-free `--analyze-run` / `--analyze-output`, grouped score/robustness/cost/interpretability/rubric fields, and ignored generated analysis/comparison JSON artifacts.

### Major Improvements

* Experiment interpretability improved through text similarity, changed-line, score-delta, low-change, and rubric trend metadata.
* Research reproducibility improved by making single-run and multi-run inspection possible without provider calls.
* Run comparison quality improved with cost-ready, similarity, and rubric fields while preserving legacy metadata compatibility.
* Runtime safety posture remained intact: no provider behavior, prompt semantics, scoring semantics, sanitizer logic, or benchmark assumptions were changed.
* Documentation now points users to `round_metrics.json`, `run_summary.json`, `--compare-runs`, and `--analyze-run` for reproducible inspection.

### Remaining Technical Debt

* Real token usage and cost accounting still use estimates unless providers expose usage data.
* UI comparison is useful but table-oriented; richer dashboard charts need a deliberate layout pass.
* Mock/fake CLI run mode is still not implemented as a user-facing command.
* Old run artifacts remain readable, but only newer runs include evolution/rubric analytics.
* `PROJECT_UPDATE.md` records exact implementation commits, with small follow-up commits used only to fill hashes after commit creation.

### Recommended Human Review Items

* Confirm that the fixed low-change threshold is acceptable as a descriptive heuristic.
* Review whether rubric average fields are the right UI/comparison subset or should be made configurable.
* Decide whether `--analyze-run` output should become a UI panel, a release artifact, or remain CLI-only.
* Decide whether future work should prioritize mock mode, real provider usage capture, or a dashboard redesign.

### Recommended Future Roadmap

* Phase 14 - Mock/Fake Run Mode: add a deterministic provider-free demo run that writes normal artifacts and is safe for CI/docs.
* Phase 15 - UI Analytics Dashboard: design a compact dashboard for score, rubric, similarity, timeout/error, timing, and token estimate trends.
* Phase 16 - Provider Usage Capture: record real token usage when providers expose it, while keeping estimate-only fallbacks.
* Phase 17 - Release Packaging: consolidate changelog/release notes, update examples, and prepare a stable tagged release.

# Phase 12 - Single-Run Analytics Export

Date: 2026-06-24
Commit: 3273785ebdc91619b7967a5519b792050a05ec0e
Branch: master

## Goal

Add a CI-safe, provider-free way to inspect one run's score trend, robustness, cost-ready estimates, interpretability metrics, rubric summaries, and artifact paths without needing a comparison run.

## What Changed

Added a single-run analytics helper and CLI wrapper. `--analyze-run` reads existing run artifacts, tolerates missing or legacy metadata, prints privacy-safe JSON, and can save an ignored project-local analysis artifact.

## Code

* Added `src/run_analytics.py` for single-run analytics grouping.
* Added CLI flags `--analyze-run` and `--analyze-output` that dispatch before config/provider validation.
* Added narrow `.gitignore` rules for generated `run_analysis.json` and `run_comparison.json` project artifacts.

## UI

* No Streamlit UI changes in this phase; the feature is CLI/provider-free.

## Tests

* Added run analytics tests for score trend, robustness, cost-ready fields, interpretability, rubric summaries, missing metadata, and privacy-safe CLI output.
* Extended CLI argument parsing tests for the new flags.

## Docs

* Updated README, USER_GUIDE, DEVELOPER_GUIDE, quickstart_zh, and runbook_zh with `--analyze-run` usage.

## Validation

* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `.venv/bin/python -m pytest tests/test_run_analytics.py tests/test_round_loop.py::RoundLoopTests::test_parse_args_accepts_mode_and_model_flags -q`
* `make check`

## Risks / Limitations

* Analytics are derived summaries of existing artifacts; they do not add new evaluation semantics.
* Missing or legacy artifacts produce partial JSON rather than a hard failure, so users should check `metadata_status` and `metadata_sources`.

## Recommended Next Phase

Phase 13 - Documentation and release polish, including a final autonomous-cycle summary.

## Suggested Codex Prompt

Continue with Phase 13. Polish release documentation, update PROJECT_UPDATE.md with an autonomous-cycle final summary, avoid new research semantics, validate, commit, push, and stop if remaining improvements are low-value or require architecture decisions.

# Phase 11 - Rubric Trend Summaries

Date: 2026-06-24
Commit: 745ba31fb70d1caeceac7fea8b48a57809e39b21
Branch: master

## Goal

Preserve and summarize structured Judge rubric subscores across rounds so researchers can compare quality dimensions without changing score parsing, scoring semantics, prompts, providers, or benchmark behavior.

## What Changed

Runs now aggregate existing `judge_rubric` dictionaries into rubric averages, latest values, best values, and first-to-latest deltas. Run comparison and the Streamlit UI expose compact rubric fields while continuing to tolerate missing or legacy metadata.

## Code

* Added rubric aggregation helpers in `src/metrics.py`.
* Wrote rubric trend summaries into `run_summary.json`.
* Added run comparison fallback logic for runs that only have `round_metrics.json`.

## UI

* Added rubric round count and evaluation/actionability averages to run comparison rows.
* Added rubric round count and average evaluation rubric to latest run metadata.
* Added per-round evaluation/actionability rubric fields to the score history helper.

## Tests

* Added metrics tests for rubric averages, latest values, and first-to-latest deltas.
* Extended round-loop, run comparison, and UI helper tests for rubric summary fields.

## Docs

* Updated README, USER_GUIDE, DEVELOPER_GUIDE, quickstart_zh, and runbook_zh to explain rubric trend summaries and their non-semantic role.

## Validation

* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `.venv/bin/python -m pytest tests/test_metrics.py tests/test_round_loop.py::RoundLoopTests::test_round_loop_writes_outputs_and_keeps_best_score tests/test_run_compare.py tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_score_history_rows_flatten_metrics_for_display tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_run_metadata_rows_summarize_latest_run_without_absolute_paths tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_run_comparison_helpers_mask_paths_and_flatten_fields -q`
* `make check`

## Risks / Limitations

* Rubric summaries depend on Judge returning structured JSON with a `rubric` object; legacy text-only Judge outputs will show missing or empty rubric fields.
* Rubric averages are descriptive summaries and should not be treated as independent benchmark scores.

## Recommended Next Phase

Phase 12 - Run analytics export and diagnostics polish.

## Suggested Codex Prompt

Continue with Phase 12. Add a small schema-additive run analytics export or diagnostics helper that summarizes score, rubric, similarity, timeout/error, and token estimate fields for one run without provider calls. Update tests/docs/PROJECT_UPDATE.md, validate, commit, and push.

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
