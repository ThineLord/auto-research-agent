# Codex Task Queue

Updated: 2026-07-10 (Asia/Shanghai)

Allowed states: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `DEFERRED`.

## ARA-001 - Establish and record the current validation baseline

- Status: `DONE`
- Priority: P1
- Risk: low
- Description: run the repository's documented provider-free validation gate on the dedicated maintenance branch and record exact results.
- Related files: `Makefile`, `pyproject.toml`, `.github/workflows/ci.yml`, `.codex/LAST_VALIDATION.json`
- Acceptance criteria: formatting, lint, import smoke, and tests have current results; failures are classified as pre-existing or introduced.
- Validation command: `make check`
- Commit required: yes, together with the initial recovery-state checkpoint after validation.
- Dependencies: none.

## ARA-002 - Resolve the compare-runs arity contract mismatch

- Status: `DONE`
- Priority: P1
- Risk: low
- Description: reproduce whether `--compare-runs` accepts one path while the public contract requires two or more, then make the smallest backward-compatible correction.
- Related files: `src/cli.py`, `src/run_compare.py`, `tests/test_run_compare.py`, CLI documentation
- Acceptance criteria: CLI behavior, help text, tests, and documentation agree; two-run comparison and legacy metadata remain unchanged.
- Validation command: `.venv/bin/python -m pytest tests/test_run_compare.py -q`
- Commit required: yes.
- Dependencies: `ARA-001`.

## ARA-003 - Make non-positive max-round overrides explicit

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: reject non-positive CLI overrides before provider setup and add a runner fail-fast guard before artifact creation; current silent coercion can unexpectedly trigger a provider call.
- Related files: `src/cli.py`, `src/config.py`, `src/mock_run.py`, relevant CLI/config tests
- Acceptance criteria: `0` and negative CLI values exit 2 before project/provider work; direct runner calls fail before creating artifacts or invoking agents; positive/default behavior is unchanged.
- Validation command: targeted CLI/mock/runner tests followed by `make check`.
- Commit required: yes if behavior changes.
- Dependencies: `ARA-001`.

## ARA-004 - Verify source distribution and wheel behavior from a clean install

- Status: `TODO`
- Priority: P1
- Risk: medium
- Description: a clean wheel-layout smoke can run `--help` but `--mock` cannot find `config.example.yaml`; verify and repair the install-time resource root without changing provider semantics.
- Related files: `pyproject.toml`, `src/`, `prompts/`, `ui/`, `scripts/`, packaging docs
- Acceptance criteria: exact wheel/sdist contents and clean-install smoke results are recorded; any missing assets have a reproducible test before a fix.
- Validation command: isolated build/install smoke commands selected after checking available build tooling.
- Commit required: only if a verified packaging defect is fixed.
- Dependencies: `ARA-001`.

## ARA-008 - Redact the configured provider credential from provider events

- Status: `DONE`
- Priority: P0
- Risk: high
- Description: provider error/event redaction currently relies on token-shaped patterns and can persist an arbitrary configured API key if a remote response echoes it.
- Related files: `src/llm.py`, `tests/test_llm.py`, provider event artifacts
- Acceptance criteria: the exact configured credential and common token patterns are absent from exceptions, events, logs, and serialized metadata; non-secret diagnostics remain useful.
- Validation command: focused LLM redaction tests, repository secret scan, then `make check`.
- Commit required: yes.
- Dependencies: publish the current validated checkpoint first.

## ARA-009 - Make checkpoint and JSON state writes atomic

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: state JSON currently uses in-place writes, so an interruption can truncate the previous valid checkpoint and make recovery silently fall back to empty data.
- Related files: `src/storage.py`, checkpoint/run state writers, `tests/test_storage.py`
- Acceptance criteria: same-directory temporary write, flush/fsync, and atomic replace preserve the previous file on a pre-replace failure; normal permissions and schema remain compatible.
- Validation command: fault-injection storage tests, resume tests, then `make check`.
- Commit required: yes.
- Dependencies: `ARA-008` unless security work is blocked.

## ARA-010 - Preserve prior round history when resuming a run

- Status: `DONE`
- Priority: P1
- Risk: high
- Description: resume initializes empty histories and can rewrite `round_metrics.json` and summaries with only newly resumed rounds.
- Related files: `src/runner.py`, `src/resume.py`, `src/run_config.py`, `tests/test_round_loop.py`
- Acceptance criteria: resumed runs retain existing metrics/history and append only new completed rounds; best-round and summary aggregates remain correct.
- Validation command: focused resume regression with existing rounds, analytics/compare tests, then `make check`.
- Commit required: yes.
- Dependencies: atomic state writing preferred first.

## ARA-020 - Preserve legacy run-manifest provenance across resume

- Status: `TODO`
- Priority: P2
- Risk: medium
- Description: resume rebuilds `run_manifest.json` from the current session and can replace the original start time, mode, and unknown legacy fields even though `run_config.json` preserves session history; an in-runs symlink alias can also leave checkpoint `run_id` inconsistent with the canonical root identity.
- Related files: `src/runner.py`, `src/run_config.py`, resume provenance tests
- Acceptance criteria: resume retains original run identity/start provenance and unknown legacy manifest fields while adding current resume metadata; a present checkpoint `run_id` agrees with the canonical root identity or follows an explicit alias policy; consumers remain compatible.
- Validation command: focused resume/run-config tests followed by `make check`.
- Commit required: yes.
- Dependencies: `ARA-010`.

## ARA-011 - Prevent failed rounds from replacing a trusted best output

- Status: `DONE`
- Priority: P1
- Risk: high
- Description: a failed research round can produce a synthetic zero score that beats the internal `-1` sentinel and overwrite a valid prior best output with skipped/error text.
- Related files: `src/runner.py`, score/best-output tests
- Acceptance criteria: only successful scored rounds may update best output; prior trusted best content is preserved across provider-stage failures.
- Validation command: focused provider failure and best-output tests followed by `make check`.
- Commit required: yes.
- Dependencies: none after `ARA-008`.

## ARA-012 - Constrain checkpoint run roots to the selected project

- Status: `DONE`
- Priority: P1
- Risk: high
- Description: resume preview can accept an existing checkpoint `run_root` outside `projects/<project>/runs`, allowing cross-project or arbitrary-directory artifact writes.
- Related files: `src/resume_safety.py`, `src/resume.py`, `src/runner.py`, `ui/app.py`, resume/UI tests and docs
- Acceptance criteria: the resolved root is an existing absolute per-run directory directly under the selected project's resolved `runs/` directory; equality, nested/relative/cross-project/traversal paths, files, and escaping root/round/resume-state symlinks fail before unsafe inspection or writes with a privacy-safe reason. Repository-generated legacy absolute roots remain usable, all planned resume rounds receive runner preflight/rechecks, and the UI disables Resume on the same blockers.
- Validation command: focused resume/UI path-containment and consumer tests followed by `make check`.
- Commit required: yes.
- Dependencies: none after `ARA-008`.

## ARA-021 - Constrain UI checkpoint artifact reads to the selected run

- Status: `TODO`
- Priority: P1
- Risk: medium
- Description: the output browser and analytics helpers independently trust checkpoint `run_config`/`run_summary` and summary `round_metrics_path`, so rendering a crafted checkpoint can read external JSON even though Resume itself is now blocked.
- Related files: `ui/app.py`, `src/resume_safety.py`, `tests/test_ui_helpers.py`
- Acceptance criteria: UI artifact consumers derive or validate all run-local paths against the selected canonical run root before reads; safe legacy in-run metadata remains readable and unsafe references produce partial/unavailable UI state without exposing paths.
- Validation command: focused UI metadata/dashboard/catalog tests followed by `make check`.
- Commit required: yes.
- Dependencies: `ARA-012`.

## ARA-022 - Define project-level symlink boundaries for runtime artifacts

- Status: `TODO`
- Priority: P2
- Risk: high
- Description: project-level inputs/outputs such as `runs/`, `best_output.md`, `memory.md`, logs, and provider events can still follow filesystem symlinks in normal or resume workflows; closing an active rename/symlink race requires a broader storage policy than checkpoint validation.
- Related files: `src/storage.py`, `src/runner.py`, `src/project_input.py`, runtime artifact tests
- Acceptance criteria: define the trusted-local-filesystem threat model and either reject unsafe project artifact links consistently or use descriptor-based no-follow writes without breaking canonical local workflows.
- Validation command: adversarial filesystem tests plus `make check`.
- Commit required: yes if behavior changes.
- Dependencies: owner input only if external artifact storage is intended; otherwise higher-priority P1 work.

## ARA-013 - Make run-lock acquisition and release ownership-safe

- Status: `TODO`
- Priority: P1
- Risk: medium
- Description: the lock file is not acquired atomically and release lacks an owner token, so an old process can delete a newer owner's lock; malformed PID types can also raise unexpectedly.
- Related files: `src/runtime.py`, runtime/UI helper tests
- Acceptance criteria: atomic exclusive acquisition, robust malformed metadata handling, and owner-checked release prevent lock theft or deletion.
- Validation command: concurrency/ownership-focused runtime tests followed by `make check`.
- Commit required: yes.
- Dependencies: none after `ARA-008`.

## ARA-014 - Source benchmark stop reason from the target run

- Status: `TODO`
- Priority: P2
- Risk: medium
- Description: benchmark reporting can read the project's latest checkpoint instead of the target historical run, mislabeling stop reason.
- Related files: `src/benchmark_report.py`, `tests/test_benchmark_report.py`
- Acceptance criteria: historical reports use target-run summary/config/manifest data and only use project checkpoint when it belongs to that run.
- Validation command: historical-run mismatch regression followed by `make check`.
- Commit required: yes.
- Dependencies: higher-priority correctness work.

## ARA-015 - Enforce Gemini request timeouts at the HTTP client layer

- Status: `TODO`
- Priority: P1
- Risk: medium
- Description: configured timeout values are recorded but not passed to the Gemini transport, so one request may exceed the runner's bounded runtime expectations.
- Related files: `src/llm.py`, provider configuration, `tests/test_llm.py`
- Acceptance criteria: the configured timeout reaches the supported Gemini HTTP transport without changing model/prompt semantics; timeout errors retain safe classification.
- Validation command: mocked client-construction/request tests followed by `make check`.
- Commit required: yes.
- Dependencies: verify current Google SDK API before implementation.

## ARA-016 - Remove tracked personal paths and add a repository safety gate

- Status: `TODO`
- Priority: P1
- Risk: low
- Description: tracked reports contain a real local username in example scan text; sanitize it and prevent new tracked personal paths or obvious secrets.
- Related files: `REAL_PROVIDER_SMOKE.md`, `TEST_AND_NEXT_STEPS.md`, a small repo-safety script, `Makefile`, CI
- Acceptance criteria: tracked files contain no personal absolute paths or real secrets; local/CI `make check` runs a deterministic safety scan with focused tests or self-test fixtures.
- Validation command: tracked-file path/secret scan plus `make check`.
- Commit required: yes.
- Dependencies: avoid changing historical findings beyond redaction.

## ARA-017 - Return nonzero status for CLI startup and validation errors

- Status: `TODO`
- Priority: P1
- Risk: medium
- Description: several config/project/provider startup failures print an error and return normally, so automation and clean-install smoke tests can report false success.
- Related files: `src/cli.py`, `src/main.py`, console entrypoint tests
- Acceptance criteria: user/config/startup failures return a documented nonzero status; `--help` and successful provider-free modes remain zero; library helpers keep clear behavior.
- Validation command: subprocess CLI error/success tests followed by `make check`.
- Commit required: yes.
- Dependencies: define narrow error categories to avoid changing successful workflows.

## ARA-018 - Choose a public distribution license and package metadata policy

- Status: `BLOCKED`
- Priority: P1 for public package release
- Risk: high product/legal decision
- Description: the repository has no `LICENSE` and package metadata lacks license/project identity fields; Codex must not choose a license for the owner.
- Related files: future `LICENSE`, `pyproject.toml`, release documentation
- Acceptance criteria: owner selects the license and distribution intent; metadata and release guidance then match that decision.
- Validation command: package metadata inspection and license-file presence check.
- Commit required: yes after owner decision.
- Dependencies: explicit project-owner license decision.

## ARA-019 - Add reproducible packaging and CI hardening after policy decisions

- Status: `DEFERRED`
- Priority: P2
- Risk: medium
- Description: editable-only CI masks package assets; dependencies are unconstrained, workflow permissions/timeouts are implicit, and third-party actions are tag-pinned rather than commit-pinned.
- Related files: `.github/workflows/ci.yml`, `pyproject.toml`, constraints/lock policy
- Acceptance criteria: isolated artifact install smoke, least-privilege Actions permissions, bounded job time, and evidence-based dependency floors or constraints.
- Validation command: local equivalent plus GitHub Actions on the maintenance PR.
- Commit required: yes.
- Dependencies: `ARA-004`, `ARA-006`, and `ARA-018` policy outcomes.

## ARA-005 - Align stale future-priority documentation with implemented features

- Status: `TODO`
- Priority: P3
- Risk: low
- Description: remove or revise statements that still describe implemented comparison, analytics, or dashboard work as future work.
- Related files: `docs/quickstart_zh.md`, related release documentation
- Acceptance criteria: roadmap wording matches current behavior and does not overstate research readiness.
- Validation command: documentation search, `git diff --check`, and `make check`.
- Commit required: yes, grouped only with closely related documentation corrections.
- Dependencies: higher-priority reproducible issues.

## ARA-006 - Decide package version policy for hardening tags

- Status: `DEFERRED`
- Priority: P2
- Risk: medium
- Description: package metadata is `0.1.0` while the source tag is `v0.1.1-hardening`; changing this requires an explicit distribution/versioning policy.
- Related files: `pyproject.toml`, `CHANGELOG.md`, release workflow
- Acceptance criteria: owner-approved policy states whether source milestone tags map to PEP 440 package versions.
- Validation command: metadata inspection plus isolated wheel install.
- Commit required: yes after policy is decided.
- Dependencies: project owner release-policy decision.

## ARA-007 - Audit ignored legacy logs before any publication workflow

- Status: `DEFERRED`
- Priority: P3
- Risk: low locally, privacy-sensitive if shared
- Description: old ignored runtime logs may predate path masking; do not rewrite or delete them automatically.
- Related files: ignored `projects/*/run.log` and runtime artifacts
- Acceptance criteria: any future publication flow scans selected artifacts and excludes local paths or secrets.
- Validation command: scoped path/secret scan of explicitly selected publication artifacts.
- Commit required: no for local ignored artifacts.
- Dependencies: an explicit artifact-publication request.
