# Comprehensive Test and Next-Step Review

Date: 2026-06-25
Branch: master
Current HEAD: 65495e489a6bde27a285238fe9e7933cd7bb75a2 (review target before this report commit)
Release tags checked: backup-before-history-rewrite, v0.1.0-stable, v0.1.1-hardening

## Executive Summary

The current `v0.1.1-hardening` state is provider-free release-candidate ready for local cloned-repo
testing. The full safe validation gate passed, deterministic mock/survey/analyze/compare flows work,
and generated runtime outputs remain ignored.

No critical or high-severity provider-free bugs were found. The main release-readiness issue is a
reproducible CLI contract mismatch: `--compare-runs` help/docs say "two or more" runs, but the CLI
accepts one run and returns a self-baseline comparison. The main release-management issue is that the
Git tag is `v0.1.1-hardening` while package metadata still reports version `0.1.0`.

Recommendation: do not start another feature phase yet. Run a short real-provider smoke validation
first, then move to human/user acceptance testing. Defer Dashboard 2.0, provider usage capture, and
methodology changes until after the release candidate has been tried by humans.

## Test Matrix

### Repository State

* command/check: `git status --short --branch`
* result: Pass
* evidence: `## master...origin/master`; no tracked modifications before this report was created.
* notes: Ignored local runtime artifacts exist under `projects/example/`, as expected.

* command/check: `git log --oneline -n 20`
* result: Pass
* evidence: HEAD is `65495e4 Document v0.1.1 hardening release`; recent history shows the hardening
  commits from artifact/privacy/stale-path fixes.
* notes: History matches the hardening release narrative in `PROJECT_UPDATE.md` and `CHANGELOG.md`.

* command/check: `git diff --check`
* result: Pass
* evidence: command exited 0 with no output.
* notes: No whitespace errors detected.

### CLI

* command/check: `.venv/bin/python -m src.main --help`
* result: Pass
* evidence: help lists `--mock`, `--survey`, `--analyze-run`, `--compare-runs`, provider overrides,
  benchmark presets, and drafting modes.
* notes: Help text says `--compare-runs` compares "two or more" run directories.

* command/check: `.venv/bin/auto-research-agent --help`
* result: Pass
* evidence: console script exposes the same option set as `python -m src.main`.
* notes: Editable install entrypoint is functional.

* command/check: invalid argument probes
* result: Mostly pass, with one low-risk behavior note
* evidence: invalid `--drafting-mode invalid` and `--provider bad` exit with argparse code 2;
  `--mock --project ../bad` prints `Project name must be a simple folder name under projects/.`
* notes: `--mock --project example --max-rounds 0` is accepted and coerced to one round.

### Makefile

* command/check: `make help`
* result: Pass
* evidence: help lists bootstrap, install, install-dev, format, format-check, lint, import-check,
  test, check, run, diagnostic, continuous, resume, session, survey, mock, and ui.
* notes: Target list matches the stable workflow docs.

* command/check: `make check`
* result: Pass
* evidence: Ruff format check passed, Ruff lint passed, import smoke passed, and pytest reported
  `137 passed, 43 subtests passed in 0.47s`.
* notes: This is the canonical local validation gate for this repo.

* command/check: `make mock ARGS="--project example --max-rounds 1"`
* result: Pass
* evidence: created mock run `projects/example/runs/20260625_011837_480206`, completed one round,
  stop reason `MAX_ROUNDS`, best score `73.00`.
* notes: No Ollama, Gemini, network, or API key calls were made.

* command/check: `make survey ARGS="--project example"`
* result: Pass
* evidence: scanned 80 source files, collected 4 unique papers, wrote survey report, metadata, and
  related-work draft under `projects/example/survey/`.
* notes: Provider-free survey target dispatches correctly through the Makefile.

### Mock Mode

* command/check: `.venv/bin/python -m src.main --mock --project example --max-rounds 1`
* result: Pass
* evidence: created mock run `projects/example/runs/20260625_011840_743035`, completed one round,
  wrote `run_config.json`, `round_metrics.json`, `run_summary.json`, `checkpoint.json`, and
  `score_history.json`.
* notes: Console and fresh log lines display repo-relative paths.

* command/check: `.venv/bin/python -m pytest tests/test_mock_run.py -q`
* result: Pass
* evidence: included in focused mock/survey/cloud-free run, `23 passed in 0.14s` across the selected
  suites.
* notes: Coverage verifies mock skips provider discovery/client creation.

### Survey Mode

* command/check: `.venv/bin/python -m src.main --survey --project example`
* result: Pass
* evidence: scanned 80 source files, collected 4 unique papers, saved `survey_report.md`,
  `paper_metadata.json`, and `related_work.md`.
* notes: `rg -n "/Users/hanzhiyou|/private/var|/tmp" projects/example/survey` found no local
  absolute path hits.

* command/check: `.venv/bin/python -m pytest tests/test_literature_survey.py -q`
* result: Pass
* evidence: included in focused provider-free suite, all selected tests passed.
* notes: Survey remains deterministic and local.

### Analyze-Run

* command/check: `.venv/bin/python -m src.main --analyze-run projects/example/runs/20260625_011840_743035`
* result: Pass
* evidence: JSON returned `metadata_status: ok`, sources `run_summary`, `run_config`,
  `round_metrics`, provider `mock`, completed rounds `1`, best score `73.0`, stop reason
  `MAX_ROUNDS`.
* notes: Output paths are repo-relative.

* command/check: `.venv/bin/python -m pytest tests/test_run_analytics.py -q`
* result: Pass
* evidence: included in targeted legacy/analytics run, selected suites passed with `11 passed`.
* notes: Provider-free single-run analytics path remains covered.

### Compare-Runs

* command/check: `.venv/bin/python -m src.main --compare-runs projects/example/runs/20260625_011837_480206 projects/example/runs/20260625_011840_743035`
* result: Pass
* evidence: JSON returned `run_count: 2`, both runs `metadata_status: ok`, provider `mock`,
  best score `73.0`, delta `0.0`.
* notes: Normal two-run workflow works.

* command/check: `.venv/bin/python -m src.main --compare-runs projects/example/runs/20260625_011840_743035`
* result: Issue found
* evidence: command exited 0 and returned `run_count: 1`, despite help/docs saying "two or more".
* notes: This is a contract/compatibility decision, not a data-loss bug.

### Resume/Partial-Round Safety

* command/check: targeted pytest for diagnostic/resume safety
* result: Pass
* evidence: `.venv/bin/python -m pytest tests/test_diagnostic.py` plus the resume/partial-round
  tests in `tests/test_round_loop.py` reported `6 passed in 0.11s`.
* notes: Coverage verifies diagnostic resume metadata, path masking, resume start round, partial
  next-round blocking, stale checkpoint preview, and stale stop-signal cleanup.

### Config Validation

* command/check: `.venv/bin/python -m pytest tests/test_config.py tests/test_project_input.py -q`
* result: Pass
* evidence: `20 passed, 36 subtests passed in 0.18s`.
* notes: Missing/malformed config path masking and strict project-input validation are covered.

* command/check: direct CLI project validation
* result: Pass
* evidence: `--project ../bad` is rejected; missing project errors print
  `projects/missing_project_for_review`, not the local absolute repo path.
* notes: CLI returns code 0 for validation messages because `main()` prints and returns rather than
  raising; this is current behavior.

### Path Privacy

* command/check: fresh mock console/log path review
* result: Pass for new output
* evidence: fresh mock console and recent `projects/example/run.log` entries show
  `projects/example/...` paths.
* notes: Internal JSON metadata intentionally retains absolute paths for resume/analytics
  compatibility.

* command/check: stale ignored log scan
* result: Known legacy/stale artifact risk
* evidence: old `projects/example/run.log` entries from pre-hardening runs contain
  `/Users/hanzhiyou/GitHub_Repository/...`.
* notes: This is not a current-output regression, but users should avoid sharing old ignored logs
  without review.

### Stale Artifact Robustness

* command/check: `.venv/bin/python -m pytest tests/test_storage.py tests/test_run_config.py tests/test_benchmark_report.py -q`
* result: Pass
* evidence: `16 passed in 0.04s`.
* notes: Covers stale JSON/text reads, stale run config/manifest paths, and stale benchmark round
  artifacts.

* command/check: UI/runtime stale helper coverage through `tests/test_ui_helpers.py`
* result: Pass
* evidence: `28 passed in 0.17s`.
* notes: Covers stale process metadata, run locks, stop signals, stale text/log reads, and masked
  UI error display.

### Legacy Compatibility

* command/check: `.venv/bin/python -m pytest tests/test_run_compare.py tests/test_run_analytics.py tests/test_judge_output.py -q`
* result: Pass
* evidence: `11 passed in 0.13s`.
* notes: Covers legacy score parsing, legacy manifests, and judge output fallback behavior.

* command/check: `tests/test_run_config.py`
* result: Pass
* evidence: included in stale artifact suite.
* notes: Confirms fallback to legacy `run_manifest.json`.

### UI Helpers / Streamlit

* command/check: `.venv/bin/python -m py_compile ui/app.py ui/i18n.py ui/theme.py src/cli.py src/runner.py src/resume.py src/run_compare.py src/run_analytics.py`
* result: Pass
* evidence: command exited 0 with no output.
* notes: Syntax check passed for UI and central CLI/runtime files.

* command/check: `.venv/bin/python scripts/import_check.py`
* result: Pass
* evidence: imported all `src.*` modules and `ui.app`.
* notes: Same import smoke check is included in `make check`.

* command/check: `.venv/bin/python -m streamlit --version`
* result: Pass
* evidence: `Streamlit, version 1.57.0`.
* notes: UI was not launched because that is interactive/long-running.

### Docs Accuracy

* command/check: requested docs were read and command references were grepped
* result: Mostly pass
* evidence: referenced files such as `docs/literature_survey_mode.md`, `scripts/start_ui.sh`,
  `requirements.txt`, `config.example.yaml`, and `projects/example/task.md` exist.
* notes: Safe documented commands tested in this review include `make help`, `make check`,
  `make mock`, `make survey`, CLI help, `--mock`, `--survey`, `--analyze-run`, and `--compare-runs`.

* command/check: docs roadmap/staleness review
* result: Low documentation staleness found
* evidence: `docs/quickstart_zh.md` still has older "next priorities" language about adding
  compare/dashboard/token-estimate work even though compare/dashboard/estimated-token features now
  exist.
* notes: This is not command-breaking, but it may confuse readers about current status.

### Packaging Assumptions

* command/check: `.venv/bin/python -m pip show auto-research-agent`
* result: Pass for editable install; release metadata issue found
* evidence: editable project location is the repo checkout; installed package version is `0.1.0`.
* notes: Console script works in editable mode.

* command/check: `pyproject.toml`
* result: Packaging risk
* evidence: `version = "0.1.0"` and `[tool.setuptools] packages = ["src"]`.
* notes: A non-editable wheel/package-data review is still needed if users should install outside a
  cloned checkout. UI, scripts, prompts, docs, and example project assets are repo assets today.

### Release/Tag Consistency

* command/check: `git tag --list`
* result: Pass
* evidence: tags include `backup-before-history-rewrite`, `v0.1.0-stable`, and
  `v0.1.1-hardening`.
* notes: `backup-before-history-rewrite` is still local/repo-visible history metadata.

* command/check: `git cat-file -t v0.1.1-hardening`, `git rev-parse v0.1.1-hardening^{}`,
  `git ls-remote --tags origin 'v0.1.1-hardening^{}'`
* result: Pass
* evidence: local tag is annotated; local and remote dereference to
  `65495e489a6bde27a285238fe9e7933cd7bb75a2`.
* notes: Tag points at current HEAD and is present on `origin`.

* command/check: `CHANGELOG.md`, `PROJECT_UPDATE.md`, package metadata
* result: Partial
* evidence: docs consistently describe `v0.1.1-hardening`; package metadata reports `0.1.0`.
* notes: This matters if publishing a hosted release or wheel.

## Bugs or Issues Found

### Issue 1 - `--compare-runs` accepts one run despite "two or more" contract

* severity: medium
* reproducibility: Always reproduced in this review.
* affected workflow: CLI run comparison, docs/help contract, release acceptance expectations.
* evidence: `.venv/bin/python -m src.main --compare-runs projects/example/runs/20260625_011840_743035`
  exited 0 and returned `run_count: 1`; CLI help says "Compare two or more run directories".
* recommended fix: Make an explicit compatibility decision. Either enforce a minimum of two run
  paths with a clear CLI error, or update help/docs to describe single-run self-baseline output.
* whether fixed now or deferred: Deferred. This is a public CLI behavior decision.

### Issue 2 - Package version remains `0.1.0` while release tag/docs say `v0.1.1-hardening`

* severity: medium for package/release workflows; low for cloned-repo local use.
* reproducibility: Always reproduced.
* affected workflow: Hosted release, wheel metadata, `pip show`, dependency/version reporting.
* evidence: `pyproject.toml` has `version = "0.1.0"`; `pip show auto-research-agent` and
  `importlib.metadata.version("auto-research-agent")` both report `0.1.0`; Git tag is
  `v0.1.1-hardening`.
* recommended fix: Decide whether hardening tags are source-only milestones or package versions. If
  package-facing, bump package metadata and document the versioning policy.
* whether fixed now or deferred: Deferred. This is release policy, not a provider-free runtime bug.

### Issue 3 - Non-editable package-data assumptions are unverified

* severity: low to medium, depending on distribution plan.
* reproducibility: Static configuration finding.
* affected workflow: Installing from a wheel or outside a full repo checkout.
* evidence: `[tool.setuptools] packages = ["src"]`; editable install works because the checkout
  still contains `ui/`, `scripts/`, `prompts/`, docs, and example project files.
* recommended fix: Run a package-data review before publishing wheels. Decide whether this remains a
  cloned-repo tool or should package UI/prompts/example assets.
* whether fixed now or deferred: Deferred.

### Issue 4 - `--max-rounds 0` silently runs one round

* severity: low
* reproducibility: Reproduced in this review.
* affected workflow: CLI argument behavior.
* evidence: `.venv/bin/python -m src.main --mock --project example --max-rounds 0` printed
  "Mock mode will write normal run artifacts for 1 round(s)" and completed a one-round run.
* recommended fix: Either reject non-positive CLI round counts with an error or document the clamp.
* whether fixed now or deferred: Deferred. Safe behavior, but surprising.

### Issue 5 - Older ignored logs can still contain absolute paths

* severity: low
* reproducibility: Reproduced on this workspace's existing ignored artifacts.
* affected workflow: Sharing old generated logs/artifacts after the privacy hardening release.
* evidence: `rg` over full `projects/example/run.log` found older absolute `/Users/hanzhiyou/...`
  entries; fresh mock log entries from this review use `projects/example/...`.
* recommended fix: Keep code as-is. Add a human release-note reminder not to share pre-hardening
  ignored logs without review, or manually rotate old local logs outside Git.
* whether fixed now or deferred: Deferred. Automatic deletion would be destructive.

### Issue 6 - `docs/quickstart_zh.md` has stale future-priority wording

* severity: low
* reproducibility: Static docs finding.
* affected workflow: Human onboarding/readiness interpretation.
* evidence: the "next priorities" section still suggests adding comparison/dashboard/token-estimate
  features that are now partially or fully implemented.
* recommended fix: Update the future-priority section during the next docs sweep, ideally after the
  human release decision.
* whether fixed now or deferred: Deferred to avoid mixing documentation cleanup into this review
  report.

## Skipped Checks

* Real Ollama diagnostic: skipped because this was requested as a provider-free QA pass. Non-generating
  probes showed Ollama is installed at `/opt/homebrew/bin/ollama` and local models include
  `qwen3:8b`, `qwen3:14b`, `deepseek-r1:8b`, and `llama3.1:8b`.
* Real Gemini diagnostic: skipped because no `GEMINI_API_KEY` or `GOOGLE_API_KEY` environment
  variable was set, and the review must not require external API keys.
* `make bootstrap`: skipped because it can run a real diagnostic smoke and is not provider-free.
* `make run`, `make diagnostic`, `make continuous`, `make resume`, `make session`: skipped as real
  provider or potentially long-running workflows. Resume/diagnostic behavior was covered with
  provider-free targeted tests.
* `make ui`: skipped because it launches an interactive Streamlit server. UI import, syntax,
  version, and helper tests were run instead.
* Wheel build/install from a produced wheel: skipped to avoid broad packaging side effects during
  this release-candidate review. Static pyproject and editable install metadata were inspected.

## Remaining Risks

* Real provider behavior has not been validated in this pass. Provider-free confidence is high, but
  release acceptance still needs at least one local Ollama diagnostic and one Gemini smoke when a key
  is available.
* Package/version policy is not release-tight: source tag and package metadata do not currently
  identify the same version.
* Compare-runs single-path behavior needs a human compatibility decision before documenting or
  enforcing strict behavior.
* Old ignored runtime artifacts can preserve pre-hardening path leaks. New output is masked, but old
  local logs are not automatically rewritten.
* Internal JSON metadata still stores absolute paths intentionally for resume/analytics
  compatibility. This is acceptable for local reproducibility, but not for publishing raw artifacts.
* The example project is still a small demo; it does not prove research quality on realistic tasks.

## Recommended Next Steps

### Option A - Real-provider smoke validation

* Value: High
* Risk: Low to medium; uses local model generation and optional Gemini key if available.
* Effort: Small to medium
* Why now / why not: Provider-free checks passed. Before a hosted release or user testing, the next
  highest-value unknown is whether a real diagnostic still works end to end on this machine.
* Suggested scope: Run one local Ollama diagnostic with `qwen3:8b`; if a Gemini key is available,
  run one Gemini diagnostic. Do not change prompts, scoring, provider behavior, or benchmark logic.
* Suggested Codex prompt: Run a release-candidate real-provider smoke validation for
  `v0.1.1-hardening`: first local Ollama diagnostic with `qwen3:8b`, then Gemini diagnostic only if a
  key is already configured. Capture exact commands, outputs, generated run IDs, and any failures in
  a short report. Do not modify code or prompts.

### Option B - Compare-runs compatibility decision

* Value: Medium
* Risk: Low if treated as docs-only; medium if changing CLI behavior.
* Effort: Small
* Why now / why not: The behavior mismatch is reproducible. It should be decided before broad docs
  or hosted release notes tell users how to compare runs.
* Suggested scope: Choose either "single run compare is supported as self-baseline" or "two or more
  is required"; update CLI/tests/docs accordingly.
* Suggested Codex prompt: Resolve the `--compare-runs` arity contract for the hardening release.
  Inspect current behavior and docs, choose the smallest compatible change, update tests/docs, run
  `make check`, and avoid unrelated behavior changes.

### Option C - Package/version and wheel-data review

* Value: Medium to high if distributing beyond a cloned repo.
* Risk: Medium; packaging changes can break entrypoints or asset resolution.
* Effort: Medium
* Why now / why not: Needed before a hosted GitHub Release with install guidance or wheel artifacts.
  Not required for local editable-use release testing.
* Suggested scope: Decide version policy, inspect wheel contents, verify console script from a
  clean non-editable install, and determine whether UI/prompts/example assets should be package data.
* Suggested Codex prompt: Perform a packaging-only review for `auto-research-agent`: version policy,
  wheel contents, console script behavior from a clean non-editable install, and package-data needs
  for UI/prompts/example assets. Do not alter runtime semantics.

### Option D - Human/user acceptance testing

* Value: High
* Risk: Low
* Effort: Medium
* Why now / why not: Provider-free validation is green; the project now needs usability evidence
  rather than another feature.
* Suggested scope: Ask 1-2 humans to follow README/USER_GUIDE from a clean checkout, run mock,
  inspect UI, and report confusion points.
* Suggested Codex prompt: Prepare a short human acceptance test script for `v0.1.1-hardening`,
  focused on clean checkout, mock run, survey run, UI inspection, artifact reading, and feedback
  capture. Keep it practical and do not change code.

### Option E - Hosted GitHub Release notes

* Value: Medium
* Risk: Low if source-only; medium if publishing binaries/wheels.
* Effort: Small to medium
* Why now / why not: The tag exists remotely and changelog is ready, but package metadata and
  real-provider smoke should be settled first.
* Suggested scope: Draft release notes from `CHANGELOG.md` and this report; explicitly label it as a
  source/checkout release unless packaging is completed.
* Suggested Codex prompt: Draft hosted GitHub Release notes for `v0.1.1-hardening` from
  `CHANGELOG.md`, `PROJECT_UPDATE.md`, and `TEST_AND_NEXT_STEPS.md`. Do not publish until package
  version and real-provider smoke decisions are confirmed.

### Option F - More realistic benchmark/demo project

* Value: Medium
* Risk: Low to medium
* Effort: Medium
* Why now / why not: Useful for showing research quality, but lower priority than real-provider
  smoke and human acceptance.
* Suggested scope: Add or document a richer public-safe demo task; avoid changing benchmark logic.
* Suggested Codex prompt: Design a more realistic public-safe demo project for manual evaluation of
  `auto-research-agent`. Keep it documentation/data only, avoid prompt/scoring/provider changes, and
  include an acceptance rubric for humans.

### Option G - Provider usage capture

* Value: Medium
* Risk: Medium
* Effort: Medium to large
* Why now / why not: Valuable, but it touches provider/runtime accounting and should wait until the
  release candidate is accepted.
* Suggested scope: Research provider usage fields first; preserve estimate fallbacks and avoid
  pricing assumptions.
* Suggested Codex prompt: Research and plan provider usage capture for Ollama/Gemini without
  implementation. Identify available usage fields, fallback behavior, tests needed, and docs impact.

### Option H - Dashboard 2.0

* Value: Medium
* Risk: Medium
* Effort: Large
* Why now / why not: The current helper-level UI checks are green. More dashboard work is product
  design, not release hardening.
* Suggested scope: Human UX review first, then a scoped dashboard redesign.
* Suggested Codex prompt: Review the current Streamlit analytics dashboard with a UX/testing lens
  and propose a Dashboard 2.0 plan. Do not implement until the plan is approved.

### Option I - Multi-judge or evaluator reliability

* Value: High for research validity
* Risk: High
* Effort: Large to very large
* Why now / why not: This is methodology work and should not be bundled into a hardening release.
* Suggested scope: Design doc only: evaluator reliability, multi-judge protocols, human labels,
  calibration, and failure cases.
* Suggested Codex prompt: Write a design-only evaluator reliability proposal for
  `auto-research-agent`, covering multi-judge, human review, calibration, and benchmark validity.
  Do not change prompts, scoring, or provider behavior.

## Recommended Decision

Run real-provider validation first, then pause development for human/user acceptance testing. Do not
start Dashboard 2.0, provider usage capture, multi-judge, or packaging changes until the release
candidate has one successful real Ollama smoke and the compare-runs/package-version decisions are
made.

## Suggested Human Acceptance Checklist

* Confirm `make check` passes on a clean checkout.
* Run one provider-free `make mock ARGS="--project example --max-rounds 1"` and inspect the latest
  run directory.
* Run one provider-free `make survey ARGS="--project example"` and inspect survey outputs.
* Run one real `make diagnostic ARGS="--project example --model qwen3:8b"` on a machine with Ollama
  ready.
* Open `make ui`, verify latest metadata, analytics dashboard, run comparison, and output browser.
* Decide whether `--compare-runs` should require two paths or support one-run self-baseline output.
* Decide whether `v0.1.1-hardening` should also bump package metadata before hosted release.
* Do not share old ignored logs/artifacts until checked for absolute local paths.
