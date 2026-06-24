# Bug Audit 14 - Stale Lock and Stop Signal Cleanup Safety

Date: 2026-06-24
Commit: pending phase commit
Branch: master

## Goal

Make remaining non-destructive cleanup paths fail safely when runtime sentinel paths are stale
directories or otherwise not removable as files.

## Bug / Fragility Found

* `acquire_run_lock` handled stale inactive lock files, but crashed when `active_run.json` existed as
  a directory or another non-removable path.
* `release_run_lock` and final stop-signal cleanup also assumed their sentinel paths were removable
  files.

## Reproduction

* A temporary directory at `active_run.json` reproduced `PermissionError` from `acquire_run_lock`.
* A runner fixture with `STOP_REQUESTED` as a directory exercised final stop cleanup without deleting
  the stale directory.

## Fix

* `acquire_run_lock` now returns a clear stale-lock error instead of crashing or deleting non-file
  paths.
* `release_run_lock` and stop-signal cleanup now tolerate `OSError` and leave non-file paths in place
  for manual cleanup.

## Tests Added or Updated

* Added runtime/UI helper coverage for stale directory run locks.
* Added runner coverage for stale directory `STOP_REQUESTED` cleanup.

## Validation

* `.venv/bin/python -m pytest tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_run_lock_reports_stale_directory_without_deleting_it tests/test_round_loop.py::RoundLoopTests::test_stale_stop_signal_directory_does_not_crash_cleanup -q` (`2 passed`)
* `.venv/bin/python -m ruff check src/runtime.py src/runner.py tests/test_ui_helpers.py tests/test_round_loop.py`
* Minimal stale `active_run.json` directory reproduction before and after the fix
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make check` (`134 passed, 43 subtests passed`)

## Remaining Risks

* Stale sentinel directories still require manual cleanup; this phase deliberately avoids recursive
  deletion.

## Next Audit Target

Final repository sweep and closeout once no further clear safe bugs remain.

# Bug Audit 13 - UI Process Metadata Stale Path Safety

Date: 2026-06-24
Commit: 72524fa
Branch: master

## Goal

Prevent Streamlit progress helpers from crashing when process metadata paths are stale non-file
artifacts.

## Bug / Fragility Found

* `get_active_process_meta` used the tolerant JSON reader, but still unconditionally tried to unlink
  stale inactive metadata. If `ui_run_process.json` or `ui_model_job_process.json` existed as a
  directory, cleanup raised `PermissionError`/`OSError` and could crash the UI helper path.

## Reproduction

* A temporary directory at `ui_run_process.json` reproduced `PermissionError` from
  `get_active_process_meta`.

## Fix

* Wrapped stale metadata unlink cleanup in `OSError` handling. The helper now returns no active
  process while leaving non-file stale paths untouched for manual cleanup.

## Tests Added or Updated

* Added UI/runtime helper coverage for stale directory process metadata paths.

## Validation

* `.venv/bin/python -m pytest tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_get_active_process_meta_returns_live_process_and_removes_stale_meta tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_get_active_process_meta_tolerates_stale_directory_path -q` (`2 passed`)
* `.venv/bin/python -m ruff check src/runtime.py tests/test_ui_helpers.py`
* Minimal stale `ui_run_process.json` directory reproduction before and after the fix
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make check` (`132 passed, 43 subtests passed`)

## Remaining Risks

* Non-file process metadata artifacts are left in place because deleting directories automatically
  would be destructive.

## Next Audit Target

Final repository sweep and closeout once no further clear safe bugs remain.

# Bug Audit 12 - Benchmark Report Stale Round Artifact Safety

Date: 2026-06-24
Commit: 2d112e7
Branch: master

## Goal

Keep read-only benchmark report analysis robust when old run directories contain stale unreadable
round text artifacts.

## Bug / Fragility Found

* Benchmark report analysis read `01_draft.md`, `02_review.md`, `03_revised.md`, and `04_judge.md`
  through a strict text helper, so a stale directory at one of those artifact paths crashed the
  report with `IsADirectoryError`.

## Reproduction

* A temporary run fixture with `round_01/01_draft.md` as a directory reproduced
  `IsADirectoryError` from `analyze_benchmark_run`.

## Fix

* Switched benchmark round artifact reads to the tolerant text reader and stripped the result to
  preserve the previous analysis behavior for normal files.
* Left global memory/best-output reads unchanged because some of those paths are later written back,
  and stale write targets require manual cleanup rather than silent recovery.

## Tests Added or Updated

* Added benchmark-report coverage for stale directory round markdown artifacts.

## Validation

* `.venv/bin/python -m pytest tests/test_benchmark_report.py -q` (`4 passed`)
* `.venv/bin/python -m ruff check src/benchmark_report.py tests/test_benchmark_report.py`
* Minimal stale `round_01/01_draft.md` directory reproduction before and after the fix
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make check` (`131 passed, 43 subtests passed`)

## Remaining Risks

* Stale directories at write targets such as `memory.md` or `best_output.md` still require manual
  cleanup; deleting or replacing those paths automatically would be destructive.

## Next Audit Target

Final repository sweep for CLI/docs mismatches, packaging/import safety, and remaining
compatibility-only concerns.

# Bug Audit 11 - Session and Log Stale Artifact Safety

Date: 2026-06-24
Commit: 67e83e3
Branch: master

## Goal

Harden remaining user-facing stale text/state artifact reads without changing provider, prompt,
scoring, or benchmark behavior.

## Bug / Fragility Found

* `tail_file_lines` returned an empty string for missing logs but crashed when the log path existed as
  a directory or otherwise raised `OSError`.
* Session mode handled malformed `research_state.json` but crashed after the session loop when that
  artifact existed as a stale unreadable path.

## Reproduction

* A temporary directory at `run.log` reproduced `IsADirectoryError` from `tail_file_lines`.
* A mocked session-mode run with a directory at `research_state.json` reproduced
  `IsADirectoryError` after `run_iterative_rounds` completed.

## Fix

* Updated `tail_file_lines` to return an empty fallback on `OSError`, matching the helper's
  missing-log behavior.
* Reused `read_json_file` for session-mode `research_state.json`, preserving the existing empty-state
  fallback for malformed state and extending it to stale unreadable state.

## Tests Added or Updated

* Added UI helper coverage for stale directory log paths.
* Added session-mode regression coverage for stale directory `research_state.json` with the round loop
  mocked out.

## Validation

* `.venv/bin/python -m pytest tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_text_json_and_tail_helpers_handle_missing_and_invalid_files tests/test_session.py` (`2 passed`)
* `.venv/bin/python -m ruff check src/session.py src/storage.py tests/test_session.py tests/test_ui_helpers.py`
* Minimal stale `run.log` and `research_state.json` directory reproductions before and after the fix
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make check` (`130 passed, 43 subtests passed`)

## Remaining Risks

* These fixes intentionally treat stale unreadable artifacts as absent; they do not attempt deletion,
  repair, or migration.

## Next Audit Target

Final broad sweep of docs/CLI contracts, generated artifact ignore rules, and remaining speculative
risks.

# Bug Audit 10 - Run Config Stale Artifact Safety

Date: 2026-06-24
Commit: 00df60f
Branch: master

## Goal

Harden run metadata compatibility readers against stale unreadable `run_config.json` and
`run_manifest.json` paths.

## Bug / Fragility Found

* `read_run_config` handled malformed JSON but crashed when `run_config.json` existed as a directory
  or otherwise raised an `OSError`.
* The legacy `run_manifest.json` fallback reader had the same stale directory/unreadable path gap.

## Reproduction

* A temporary run fixture with a directory at `run_config.json` reproduced `IsADirectoryError` from
  `src.run_config.read_run_config`.

## Fix

* Extended `read_run_config` to catch `OSError` alongside `json.JSONDecodeError` for both
  `run_config.json` and legacy `run_manifest.json`.

## Tests Added or Updated

* Added run-config coverage for stale directory `run_config.json` and `run_manifest.json` paths.

## Validation

* `.venv/bin/python -m pytest tests/test_run_config.py -q` (`3 passed`)
* `.venv/bin/python -m ruff check src/run_config.py tests/test_run_config.py`
* Minimal stale `run_config.json` directory reproduction before and after the fix
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make check` (`129 passed, 43 subtests passed`)

## Remaining Risks

* This fix treats unreadable run metadata as absent rather than attempting recovery.

## Next Audit Target

Continue with CLI parser contracts, docs command accuracy, and remaining speculative-risk triage.

# Bug Audit 9 - Config Error Path Privacy

Date: 2026-06-24
Commit: 39d9c9d
Branch: master

## Goal

Mask config read/parse error paths without changing config validation semantics.

## Bug / Fragility Found

* Missing config errors printed the raw local config file path.
* Malformed YAML errors prefixed the parse failure with the raw local config file path.

## Reproduction

* Temporary missing and malformed config fixtures reproduced raw temporary paths in
  `load_app_config` exception messages.

## Fix

* Rendered config file paths through `display_path` before constructing missing-file and YAML parse
  errors.

## Tests Added or Updated

* Added config validation coverage that asserts missing/malformed config errors include only the
  filename and not the temporary root path.

## Validation

* `.venv/bin/python -m pytest tests/test_config.py -q` (`15 passed, 36 subtests passed`)
* `.venv/bin/python -m ruff check src/config.py tests/test_config.py`
* Minimal missing/malformed config reproduction before and after the fix
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make check` (`128 passed, 43 subtests passed`)

## Remaining Risks

* Validation errors about bad values still include field names and values where already designed;
  this phase only masks config file path prefixes.

## Next Audit Target

Continue with CLI parser contracts, docs command accuracy, and remaining speculative-risk triage.

# Bug Audit 8 - Stale Text Artifact UI Safety

Date: 2026-06-24
Commit: a7fe400
Branch: master

## Goal

Make UI text artifact helpers robust to stale unreadable paths without changing run behavior or
artifact schemas.

## Bug / Fragility Found

* `read_file_text` returned an empty string for missing files but crashed when the path existed as a
  directory.
* `ui.app.load_score_history_rows` uses `read_file_text`, so a stale directory named
  `score_history.json` crashed the UI analytics helper.

## Reproduction

* A temporary fixture with a directory at `score_history.json` reproduced `IsADirectoryError` from
  both `read_file_text` and `load_score_history_rows`.

## Fix

* Updated `read_file_text` to return an empty string on `OSError`, matching its missing-file
  fallback.

## Tests Added or Updated

* Added storage/UI helper coverage for stale directory text paths.
* Added `load_score_history_rows` coverage for stale directory `score_history.json`.

## Validation

* Targeted pytest for UI/storage stale text path tests (`3 passed`)
* `.venv/bin/python -m ruff check src/storage.py tests/test_ui_helpers.py`
* Minimal stale `score_history.json` directory reproduction before and after the fix
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make check` (`127 passed, 43 subtests passed`)

## Remaining Risks

* This fix intentionally treats unreadable UI text artifacts as empty/missing; it does not attempt
  recovery or deletion.

## Next Audit Target

Continue with CLI parser contracts, docs command accuracy, and config validation edge cases.

# Bug Audit 7 - Stale JSON Artifact Read Safety

Date: 2026-06-24
Commit: 206dc52
Branch: master

## Goal

Make shared JSON artifact reads robust to stale unreadable paths so CLI/UI helpers degrade cleanly
instead of crashing.

## Bug / Fragility Found

* `read_json_file` returned `{}` for missing files and malformed JSON, but crashed when the target
  path existed as a directory or otherwise raised an `OSError`.
* UI helpers and resume/status paths call `read_json_file` for `checkpoint.json`, run metadata, and
  process metadata, so a stale directory named like a JSON artifact could crash those flows.

## Reproduction

* A temporary fixture with a directory at `checkpoint.json` reproduced `IsADirectoryError` from
  `src.storage.read_json_file`.

## Fix

* Extended `read_json_file` to catch `OSError` along with `json.JSONDecodeError` and return `{}`.

## Tests Added or Updated

* Added stale-directory coverage to the storage JSON helper test.

## Validation

* `.venv/bin/python -m pytest tests/test_storage.py -q` (`8 passed`)
* `.venv/bin/python -m ruff check src/storage.py tests/test_storage.py`
* Minimal stale-directory reproduction fixture before and after the fix
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make check` (`126 passed, 43 subtests passed`)

## Remaining Risks

* This fix intentionally treats unreadable JSON artifacts as absent/empty; it does not attempt
  recovery or deletion.
* Callers that need to distinguish unreadable files from malformed JSON would need a separate API,
  but current helper semantics already collapse missing and malformed files to `{}`.

## Next Audit Target

Continue with CLI parser contracts, docs command accuracy, config validation edge cases, and
additional UI helper stale-artifact scenarios.

# Bug Audit 6 - Project Input Error Path Privacy

Date: 2026-06-24
Commit: 172b85f
Branch: master

## Goal

Mask user-facing project input failure paths without changing project resolution behavior or
fallback rules.

## Bug / Fragility Found

* Missing-project CLI errors printed the absolute local repository path for the missing project
  folder and suggested `task.md` path.
* Other project input errors used the same raw path construction for not-a-directory, missing task,
  non-file task, unreadable task, and empty task cases.

## Reproduction

* `.venv/bin/python -m src.main --mock --project missing_project_for_audit` printed local absolute
  repo paths in the `Project input error` message before the fix.

## Fix

* Rendered project input error paths through the shared `display_path` helper, using the CLI root as
  the relative base.
* Replaced unreadable-file exception text with a short reason so OS errors do not reintroduce raw
  absolute paths.

## Tests Added or Updated

* Added direct `load_project_input` coverage for masked missing-project errors.
* Added CLI coverage for masked project input error output and preserved pre-provider-discovery
  behavior.

## Validation

* `.venv/bin/python -m pytest tests/test_project_input.py -q` (`5 passed`)
* `.venv/bin/python -m ruff check src/project_input.py tests/test_project_input.py`
* `.venv/bin/python -m src.main --mock --project missing_project_for_audit` with local absolute path
  grep
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make check` (`126 passed, 43 subtests passed`)

## Remaining Risks

* This phase masks project input error display; it does not change existing project metadata stored
  in run artifacts.
* The private local `config.yaml` still points at `pama`, which lacks `task.md`; provider-free
  validation uses explicit project names.

## Next Audit Target

Continue with CLI parser contracts, docs command accuracy, config validation edge cases, and UI
helper stale-artifact behavior.

# Bug Audit 5 - Run Comparison Boolean Score Handling

Date: 2026-06-24
Commit: 0903774
Branch: master

## Goal

Harden run comparison legacy metric parsing without changing scoring semantics or benchmark
behavior.

## Bug / Fragility Found

* `load_run_summary` treated boolean `score` values in legacy `round_metrics.json` as numeric
  scores (`True` -> `1.0`, `False` -> `0.0`).
* Single-run analytics already rejected booleans as invalid scores, so compare-runs and analyze-run
  could disagree on the same malformed legacy artifact.

## Reproduction

* A temporary run fixture with `round_metrics.json` containing `{"score": true}` produced
  `best_score: 1.0` and `average_score: 1.0` from `src.run_compare.load_run_summary`.

## Fix

* Updated run comparison numeric coercion to reject booleans before accepting integers/floats.

## Tests Added or Updated

* Added a run comparison regression test that verifies boolean scores are ignored rather than
  treated as numeric values.

## Validation

* `.venv/bin/python -m pytest tests/test_run_compare.py -q` (`5 passed`)
* `.venv/bin/python -m ruff check src/run_compare.py tests/test_run_compare.py`
* Minimal bool-score reproduction fixture before and after the fix
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make check` (`124 passed, 43 subtests passed`)

## Remaining Risks

* This phase intentionally does not reject other string-like numeric legacy scores; those remain
  supported for artifact compatibility.
* The CLI still accepts a single path for `--compare-runs` even though help text says two or more;
  that behavior needs a separate compatibility decision.

## Next Audit Target

Continue reviewing CLI parser contracts, docs command accuracy, config validation edge cases, and
UI helper behavior around stale artifacts.

# Bug Audit 4 - Survey Artifact Path Privacy

Date: 2026-06-24
Commit: e0d0abc
Branch: master

## Goal

Fix verified survey-mode raw path exposure in console output and generated survey artifacts without
changing paper collection, deduplication, scoring, prompt, provider, or benchmark behavior.

## Bug / Fragility Found

* Survey console output printed absolute paths for `survey_report.md`, `paper_metadata.json`, and
  `related_work.md`.
* `paper_metadata.json` serialized raw project `project_dir`, `task_path`, and per-paper
  `source_paths`.
* `survey_manifest.json` serialized raw project paths, scanned source files, and output paths.

## Reproduction

* A temporary provider-free survey fixture reproduced `console_has_raw_root=True`,
  `metadata_has_raw_root=True`, and `manifest_has_raw_root=True`.
* `.venv/bin/python -m src.main --survey --project example` reproduced the same console path class
  before the fix.

## Fix

* Reused the shared `display_path` helper for survey console paths.
* Serialized survey project metadata, paper `source_paths`, manifest `source_files`, and manifest
  output paths as repo-relative or masked display-safe strings.
* Kept internal collection paths and returned `SurveyResult` path objects unchanged for callers.

## Tests Added or Updated

* Added a survey regression test that asserts console output, `paper_metadata.json`, and
  `survey_manifest.json` avoid temporary absolute roots and use repo-relative path strings.

## Validation

* `.venv/bin/python -m pytest tests/test_literature_survey.py -q` (`4 passed`)
* `.venv/bin/python -m ruff check src/literature_survey.py tests/test_literature_survey.py`
* Minimal survey reproduction fixture with console/metadata/manifest raw-root checks
* `.venv/bin/python -m src.main --survey --project example` with local absolute path grep
* `rg` check over generated `projects/example/survey` artifacts for local absolute paths
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make check` (`123 passed, 43 subtests passed`)

## Remaining Risks

* Older survey artifacts may still contain absolute paths; this phase fixes newly generated survey
  artifacts.
* Run checkpoint/config/summary JSON path fields remain absolute for legacy resume and analytics
  compatibility.
* The private local `config.yaml` still points at `pama`, which lacks `task.md`; provider-free
  validation uses `--project example`.

## Next Audit Target

Continue with documentation command accuracy, config validation edge cases, CLI parser edge cases,
and UI helper behavior around stale or partial artifacts.

# Bug Audit 3 - Runtime Path Display Privacy

Date: 2026-06-24
Commit: e1b99d2
Branch: master

## Goal

Fix the raw absolute path display reproduced during provider-free mock validation while preserving
legacy JSON artifact path fields and run metadata compatibility.

## Bug / Fragility Found

* Runner console output and `run.log` exposed absolute `run_root`, `project_dir`, `task_path`, and
  saved round paths.
* Runner summaries exposed absolute `best_output.md` and `score_history.json` paths.
* Diagnostic output and diagnostic `run.log` exposed absolute project and run paths.
* Session-mode saved-plan/report messages, interrupted reports, and generated benchmark reports had
  the same user-facing raw path display pattern.

## Reproduction

* `.venv/bin/python -m src.main --mock --project example --max-rounds 1` printed local absolute
  home-directory paths in runner status lines and summary output before the fix.
* The latest `projects/example/run.log` block from the same mock smoke reproduced raw saved-round
  paths before the fix.
* Focused temporary fixtures reproduced the same issue in recorded runner console output,
  diagnostic console output, diagnostic `run.log`, and benchmark report content.

## Fix

* Added a shared `display_path` helper for repo-relative or masked path rendering.
* Applied it to runner and diagnostic console/log messages without changing checkpoint, manifest,
  run summary, or run config path fields.
* Applied it to session saved-file messages, interrupted report best-output path display, and
  benchmark report run-root display.

## Tests Added or Updated

* Added a runner regression test that asserts recorded console output and `run.log` avoid temporary
  absolute project paths.
* Added a diagnostic regression test for masked console and `run.log` paths.
* Added a benchmark report regression test for masked run-root display.
* Updated interrupted-report storage coverage to assert masked best-output path display.

## Validation

* Targeted pytest for the four new/updated path-display tests (`4 passed`)
* `.venv/bin/python -m ruff check` on touched source and tests
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make help`
* `make check` (`122 passed, 43 subtests passed`)
* `make mock ARGS="--project example --max-rounds 1"`
* `.venv/bin/python -m src.main --mock --project example --max-rounds 1` with grep check for no
  local absolute home-directory path in console output
* Latest `projects/example/run.log` block check for no local absolute home-directory path

## Remaining Risks

* Stored JSON metadata still contains absolute paths for legacy compatibility; this phase only
  changes user-facing display/log/report text.
* Literature survey manifests and reports still need separate review for source path display and
  schema compatibility before any safe change.
* The private local `config.yaml` still points at `pama`, which lacks `task.md`; provider-free mock
  validation uses `--project example`.

## Next Audit Target

Audit survey-mode path display and source metadata compatibility, then continue through docs command
accuracy, config edge cases, and UI helper stale-artifact behavior.

# Bug Audit 2 - Cloud-Free Artifact Resilience and CLI Path Display

Date: 2026-06-24
Commit: 7aec2f9
Branch: master

## Goal

Continue the post-stable bug audit on cloud-free artifact compatibility and user-facing CLI path
display without changing provider behavior, prompt semantics, scoring semantics, benchmark behavior,
or generated artifact schemas.

## Bug / Fragility Found

* `load_profile_artifact` and `load_discovery_artifact` handled malformed JSON but crashed if a
  stale artifact path existed as a directory or could not be read.
* `--cloud-free-discover` and `--cloud-free-profile` printed saved artifact paths as raw absolute
  filesystem paths.
* The common CLI project input banner printed `task.md` as a raw path, and stale lock guidance did
  the same for `active_run.json`.

## Reproduction

* A temporary fixture with `artifacts/cloud_free_profile.json/` and
  `artifacts/cloud_free_models.json/` directories reproduced `IsADirectoryError` from both loader
  functions.
* A patched provider-free `src.cli.main` fixture for `--cloud-free-discover` reproduced
  `contains_absolute_artifact=True` and showed the raw temporary `task.md` path in console output.
* A provider-free mock smoke showed the project input banner now renders `task=projects/example/task.md`.

## Fix

* Treat unreadable stale cloud-free artifacts the same as malformed JSON and return empty fallback
  lists.
* Render cloud-free discovery/profile artifact paths through the existing repo-relative display
  helper.
* Render the project input task path and stale lock cleanup hints through the same display helper.

## Tests Added or Updated

* Added cloud-free loader regression coverage for stale artifact paths that exist as directories.
* Added cloud-free CLI fixture tests for masked discovery artifact, profile artifact, and project
  task path display.

## Validation

* `.venv/bin/python -m pytest tests/test_cloud_free.py -q` (`16 passed`)
* `.venv/bin/python -m ruff check src/cloud_free.py src/cli.py tests/test_cloud_free.py`
* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make help`
* `make check` (`119 passed, 43 subtests passed`)
* `make mock ARGS="--project example --max-rounds 1"`
* `.venv/bin/python -m src.main --mock --project example --max-rounds 1`

## Remaining Risks

* Runner and diagnostic progress logs still include raw artifact paths in several status lines. The
  latest mock smoke reproduced this broader path-display issue, but it is separate from the
  cloud-free artifact loader/display fix and should be handled as the next focused audit cluster.
* The private local `config.yaml` still points at `pama`, which lacks `task.md`; provider-free mock
  validation therefore uses `--project example`.

## Next Audit Target

Audit and fix raw absolute path display in runner, diagnostic, session/resume, and generated report
console output where it can be changed without altering artifact schemas or research behavior.

# Bug Audit 1 - Artifact Compatibility and Path Display Hardening

Date: 2026-06-24
Commit: 3f567ff
Branch: master

## Goal

Run the first post-v0.1.0-stable bug audit pass across provider-free artifact readers, diagnostic
metadata, and UI path display behavior without changing prompt, scoring, provider, or benchmark
semantics.

## Bug / Fragility Found

* `--analyze-run` reported `trend: unknown` for legacy `round_metrics.json` files whose score values
  were numeric strings, even though run comparison already tolerated the same legacy shape.
* Diagnostic runs wrote `resume_metadata` to finalized `run_config.json` but omitted it from
  `checkpoint.json` and `run_summary.json`, despite docs and UI expectations describing the field
  across all run metadata artifacts.
* The Streamlit `Pause / Stop Safely` confirmation rendered the absolute `STOP_REQUESTED` path
  instead of a repo-relative or masked path.

## Reproduction

* Temporary legacy fixture with `"score": "60.5"` and `"score": "72.0"` reproduced
  `trend: unknown` from `src.run_analytics.analyze_run`.
* Temporary diagnostic fixture with a fake provider-free LLM reproduced missing
  `resume_metadata` in `checkpoint.json` and `run_summary.json`.
* `rg -n "stop_signal_created" ui/app.py ui/i18n.py tests/test_ui_helpers.py` showed the UI passing
  the raw `Path` object to the localized stop-signal message.

## Fix

* Reused numeric-string coercion in single-run analytics score trend parsing while still rejecting
  booleans.
* Added additive diagnostic `resume_metadata` to checkpoint and run summary outputs, including the
  cloud-free quota pause path.
* Masked the UI stop-signal confirmation with the existing `output_display_path` helper.

## Tests Added or Updated

* Added a single-run analytics regression test for legacy numeric string scores.
* Added a provider-free diagnostic artifact test that asserts checkpoint, run config, and run summary
  all expose compatible `resume_metadata`.
* Added a UI helper regression test for masked stop-signal path display.

## Validation

* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `make help`
* `make check` (`116 passed, 43 subtests passed`)
* `make mock ARGS="--project example --max-rounds 1"`
* `.venv/bin/python -m src.main --mock --project example --max-rounds 1`
* `.venv/bin/python -m src.main --analyze-run projects/example/runs/20260625_000300_779811`
* `.venv/bin/python -m src.main --compare-runs projects/example/runs/20260625_000300_779811 projects/example/runs/20260625_000300_661988`

## Remaining Risks

* The local private `config.yaml` points at `pama`, which currently lacks `task.md`; unqualified
  `make mock ARGS="--max-rounds 1"` therefore fails before provider-free execution. This was not
  changed because local config is intentionally private.
* Diagnostic console output still prints local artifact paths, matching existing CLI behavior; this
  audit only fixed the verified UI path display leak.

## Next Audit Target

Continue with CLI/Makefile/config/survey/runtime edge cases, especially provider-free command
accuracy, run metadata compatibility, and additional repo-relative path display surfaces.

# Release Review - v0.1.0-stable

Date: 2026-06-24
Commit: release review commit for tag `v0.1.0-stable`
Branch: master

## Goal

Review the Phase 16 stable milestone package and tag the repository if the release candidate is
ready, without changing runtime behavior, provider behavior, prompt semantics, scoring semantics,
benchmark behavior, or artifact schemas.

## What Changed

Reviewed the release docs and stable workflow coverage for bootstrap, mock demo, diagnostic, normal
run, resume, survey, run comparison, single-run analytics, and the Streamlit analytics dashboard.
The reviewed docs clearly distinguish mock mode from real research runs, estimated tokens from
billing tokens, rubric summaries from benchmark scores, resume from new-run context reuse, and
fail-safe partial next-round blocking.

## Code

* No runtime code changes.

## UI

* No UI code changes.

## Tests

* No new tests were needed because this was a release review and tagging pass.

## Docs

* Added this final release review entry to the canonical project progress log.
* No additional documentation fixes were required after review.

## Validation

* `git diff --check`
* `.venv/bin/python -m src.main --help`
* Release documentation smoke check for stable workflow and distinction wording
* `make check`
* Optional `make mock` was not rerun during tagging to avoid creating fresh runtime outputs.

## Risks / Limitations

* The tag is a local repository milestone tag, not a hosted GitHub Release with uploaded binaries.
* Estimated token fields remain estimate-only and should not be treated as provider billing data.

## Recommended Next Phase

Pause feature work and perform human release acceptance review. Future work should be scoped
separately, with provider usage capture and richer dashboard visuals as likely candidates.

## Suggested Codex Prompt

Review the `v0.1.0-stable` tag and `PROJECT_UPDATE.md`, then decide whether to create a hosted
GitHub Release or start a new scoped post-stable phase.

# Phase 16 - Release Packaging and Stable Milestone

Date: 2026-06-24
Commit: dc6affce2fdd54a8f3a3f614fd3fb89d687c6624
Branch: master

## Goal

Prepare a stable milestone release package after Phases 9-15 by consolidating user-facing workflow
documentation, demo guidance, and release notes without changing runtime behavior or artifact
schemas.

## What Changed

Added stable milestone documentation around the current workflow: bootstrap, mock demo, diagnostic,
normal run, resume, survey, run comparison, single-run analytics, and the Streamlit analytics
dashboard.

## Code

* No source code changes in this phase.

## UI

* No UI code changes in this phase.

## Tests

* No new tests were needed because this phase is documentation-only.

## Docs

* Added `CHANGELOG.md` with stable milestone capabilities, workflow, distinctions, and validation
  baseline.
* Added README sections for `Stable Workflow` and `What To Demo First`.
* Updated USER_GUIDE, DEVELOPER_GUIDE, quickstart_zh, and runbook_zh to align around the stable
  workflow and release boundaries.

## Validation

* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `test -f CHANGELOG.md`
* `rg -n "Stable Workflow|What To Demo First|make mock|Run analytics dashboard" README.md CHANGELOG.md docs/USER_GUIDE.md docs/DEVELOPER_GUIDE.md docs/quickstart_zh.md docs/runbook_zh.md`
* `make check`

## Risks / Limitations

* This release packaging phase does not add real provider token usage; estimated token fields remain
  estimate-only.
* Human review should confirm the milestone language matches intended release positioning before
  tagging an external release.

## Recommended Next Phase

Pause feature work for human release review, then decide whether to tag a release or start provider
usage capture in a separate, scoped phase.

## Suggested Codex Prompt

Review `CHANGELOG.md`, `README.md`, and `PROJECT_UPDATE.md` for stable milestone readiness. If the
release language is acceptable, run final validation, create a release tag, and push it without
changing runtime behavior.

# Phase 15 - UI Analytics Dashboard

Date: 2026-06-24
Commit: 2b7bf07dc20b80aa57a6f5268f6363e3dabc4895
Branch: master

## Goal

Add a compact Streamlit analytics dashboard for latest-run score, rubric, evolution/similarity,
timeout/error, agent timing, and estimated-token trends using existing artifacts only.

## What Changed

The UI now shows a single-run `Run analytics dashboard` after latest-run metadata. It reads existing
`run_summary.json`, `round_metrics.json`, and `score_history.json`, uses the provider-free
single-run analytics helper where practical, and degrades to partial empty states for missing or
legacy fields.

## Code

* Added UI helper functions that build compact dashboard cards and trend rows without writing or
  changing run artifacts.
* Reused existing artifact resolution, score-history flattening, and `src.run_analytics.analyze_run`
  for summary fields.

## UI

* Added a latest-run analytics dashboard with cards for best score, completed rounds, timeout/error
  counts, agent time, and estimated tokens.
* Added compact tabs for score, rubric, similarity/evolution, timing, and token trends.
* Kept artifact source paths repo-relative or masked.

## Tests

* Added focused UI helper tests for complete analytics artifacts and score-history-only legacy
  fallback behavior.

## Docs

* Updated README, USER_GUIDE, DEVELOPER_GUIDE, quickstart_zh, and runbook_zh with dashboard behavior
  and limitations.

## Validation

* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `.venv/bin/python -m pytest tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_run_analytics_dashboard_summarizes_existing_artifacts tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_run_analytics_dashboard_tolerates_missing_legacy_metrics -q`
* `make check`

## Risks / Limitations

* The dashboard summarizes existing artifacts only; old runs without rubric or evolution fields show
  empty tables for those tabs.
* Token values remain conservative estimates and are not billing data.

## Recommended Next Phase

Phase 16 - Provider Usage Capture, if provider APIs expose real token usage safely; otherwise pause
for release packaging and human review.

## Suggested Codex Prompt

Continue with Phase 16. Capture real provider token usage only when Ollama/Gemini expose it safely,
preserve estimate-only fallbacks, avoid vendor pricing assumptions, update tests/docs/PROJECT_UPDATE.md,
validate, commit, and push.

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
