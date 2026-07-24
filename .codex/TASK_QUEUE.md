# Codex Task Queue

Updated: 2026-07-23 (Asia/Hong_Kong)

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

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: a clean wheel-layout smoke can run `--help` but `--mock` cannot find `config.example.yaml`; verify and repair the install-time resource root without changing provider semantics.
- Related files: `pyproject.toml`, `src/`, `prompts/`, `ui/`, `scripts/`, packaging docs
- Acceptance criteria: exact wheel/sdist contents and clean-install smoke results are recorded; the
  documented mock workflow works from both artifacts without writing `site-packages`, importing the
  source checkout, trusting CWD prompts, or recording unrelated Git provenance; source/editable
  behavior and explicit project/config selection remain compatible.
- Validation command: focused package/CLI/mock/run-config tests, `make check`, isolated wheel/sdist
  console/module install smokes, exact archive/RECORD/resource checks, and concurrency/fault tests.
- Commit required: yes; completed at implementation commit
  `0aee55e1a48dab3d56f0475f789c2134c548ddc5`.
- Dependencies: `ARA-001`; owner approved the >30-minute implementation on 2026-07-11. The final
  code, artifacts, remote equality, and Python 3.10/3.13 push/PR checks passed. No disposition was
  granted for KI-023 ignored state, which remained untouched.

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

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: resume rebuilds `run_manifest.json` from the current session and can replace the original start time, mode, and unknown legacy fields even though `run_config.json` preserves session history; an in-runs symlink alias can also leave checkpoint `run_id` inconsistent with the canonical root identity.
- Related files: `src/runner.py`, `src/run_config.py`, resume provenance tests
- Acceptance criteria: resume retains original run identity/start provenance and unknown legacy manifest fields while adding current resume metadata; a present checkpoint `run_id` agrees with the canonical root identity or follows an explicit alias policy; consumers remain compatible.
- Validation command: focused resume/run-config tests followed by `make check`.
- Commit required: yes.
- Dependencies: `ARA-010`.

## ARA-024 - Record zero-round resume sessions in run config

- Status: `DONE`
- Priority: P3
- Risk: low
- Description: `build_initial_run_config` appends `resume_sessions` only when `start_round > 1`, so
  resuming an existing zero-round checkpoint at round 1 lacks a session-array entry even though
  lifecycle metadata correctly says `resume_existing_run`.
- Related files: `src/run_config.py`, runner/resume provenance tests
- Acceptance criteria: a zero-round resume records its session start and round 1 in
  `resume_sessions`, while a genuinely new run at round 1 still has no resume entry.
- Validation command: focused run-config/round-loop tests followed by `make check`.
- Commit required: yes.
- Dependencies: `ARA-020`.

## ARA-025 - Make committed recovery state self-resolving

- Status: `DONE`
- Priority: P2
- Risk: low
- Description: state-only closeout commits cannot embed their own final SHA, so the committed
  snapshot permanently reports the parent HEAD, pending closeout, and uncommitted files even after
  the closeout itself is pushed and CI-verified.
- Related files: `.codex/CURRENT_STATE.md`, `.codex/LAST_VALIDATION.json`,
  `.codex/RESUME_INSTRUCTIONS.md`, `.codex/DECISIONS.md`, `.codex/KNOWN_ISSUES.md`
- Acceptance criteria: committed recovery metadata resolves current HEAD from Git without claiming
  stale worktree state, retains an exact externally verified fallback commit, and instructs recovery
  to verify remote/CI state live; existing history remains readable.
- Validation command: JSON parsing, recovery-state consistency assertions, `git diff --check`, and
  `make check`.
- Commit required: yes.
- Dependencies: ARA-005 verified closeout `3fa33a7`.

## ARA-028 - Prevent stale recursive closeout recovery instructions

- Status: `DONE`
- Priority: P1
- Risk: low
- Description: the committed ARA-022 closeout still claims recovery records remain uncommitted and
  instructs the next run to create the closeout again, contradicting the live clean, pushed, and
  CI-verified state and regressing ARA-025's self-resolving recovery contract.
- Related files: `.codex/CURRENT_STATE.md`, `.codex/LAST_VALIDATION.json`, recovery-state tests and
  completion records
- Acceptance criteria: current recovery sections source worktree state from live Git, never request
  their own already-completed closeout, use one authoritative conservative external fallback, and a
  tracked regression test rejects the stale authored-state patterns.
- Validation command: `.venv/bin/python -m pytest -q tests/test_recovery_state.py`, JSON/ancestry
  assertions, `git diff --check`, and `make check`.
- Commit required: yes.
- Dependencies: ARA-025 and verified ARA-022 closeout `ca3a2e8`.

## ARA-029 - Minimize CI token permissions and bound job runtime

- Status: `DONE`
- Priority: P2
- Risk: low
- Description: the CI workflow does not explicitly restrict `GITHUB_TOKEN` to read-only contents or
  set a job timeout, so it inherits repository defaults and the platform runtime ceiling.
- Related files: `.github/workflows/ci.yml`, CI documentation
- Acceptance criteria: CI has only the permissions it needs and a documented bounded timeout while
  preserving Python 3.10/3.13 push and pull-request behavior.
- Validation command: local YAML/action validation when available, followed by all four push/PR CI
  jobs.
- Commit required: yes.
- Dependencies: owner approved ARA-029 CI configuration changes on 2026-07-12; keep dependency,
  release, wheel-smoke, and publication policy out of scope.

## ARA-030 - Add an isolated real-wheel install smoke to CI

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: CI installs only the editable checkout, while the installed-layout unit fixture
  copies `src/`; a future build-backend or package-data regression could therefore bypass CI despite
  ARA-004's one-time isolated wheel verification.
- Related files: package-resource tests, CI workflow, packaging smoke helpers
- Acceptance criteria: a temporary source-excluded wheel install verifies its import origin, exact
  bundled resources, console/module help, and one-round mock behavior without upload, sdist work,
  provider calls, or repository ignored-artifact mutation.
- Validation command: isolated wheel build/install smoke, `make check`, then Python 3.10/3.13
  push/pull-request CI.
- Commit required: yes.
- Dependencies: owner approved this greater-than-30-minute packaging/CI task on 2026-07-13;
  ARA-018, ARA-026, version, dependency, and publication policy remain out of scope.
- Resolution: implementation `4cda430` is pushed and remote-equal. The failing workflow contract,
  isolated helper, environment-safety regressions, docs, two real temporary wheel smokes, hostile
  redirect canary, final `make check`, and three reviews are green; push/PR runs
  `29232341316`/`29232344581` passed Python 3.10/3.13 with four successful wheel steps and zero
  annotations.

## ARA-031 - Fail closed on invalid existing run config during resume

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: resume treats an existing malformed, unreadable, or non-object `run_config.json` as
  missing, rebuilds it, and overwrites the original provenance before any provider work.
- Related files: `src/run_config.py`, `src/runner.py`, `tests/test_round_loop.py`, recovery records
- Acceptance criteria: missing run config retains legacy-manifest compatibility, but an existing
  invalid run config blocks resume before any automatic artifact write; original config, manifest,
  checkpoint, stop signal, and other run state remain byte-identical and no agent is invoked.
- Validation command: focused invalid-config resume regression, related run-config/resume/round-loop
  tests, `git diff --check`, and `make check`.
- Commit required: yes.
- Dependencies: ARA-010, ARA-020, ARA-022, and the clean verified baseline `cc20303`.

## ARA-032 - Ignore non-finite scores in analysis and comparison

- Status: `DONE`
- Priority: P1
- Risk: low
- Description: `nan` and `Infinity` score values from malformed/legacy artifacts can dominate run
  ranking, produce a false flat trend, and emit non-standard analysis/comparison JSON.
- Related files: `src/run_compare.py`, `src/run_analytics.py`, metric/analysis/compare tests
- Acceptance criteria: only finite numeric values participate in score selection, ranking, trend,
  and score-derived JSON output; valid negative scores and legacy numeric strings remain
  compatible, representable extreme averages stay finite, and ordinary two-decimal averages retain
  their historical result.
- Validation command: focused strict-JSON analysis/compare regressions, related metrics tests, and
  `make check` (`309 passed, 184 subtests passed`).
- Commit required: yes.
- Dependencies: complete ARA-031 without widening its resume-integrity scope.

## ARA-033 - Normalize analysis and comparison output write failures at the CLI boundary

- Status: `DONE`
- Priority: P2
- Risk: low
- Description: provider-free analysis/comparison output failures currently expose a traceback and
  absolute local path instead of a privacy-safe operational error.
- Related files: `src/cli.py`, CLI exit-code and analysis/comparison tests
- Acceptance criteria: unavailable output parents return the documented operational status without
  traceback or local path disclosure; successful output behavior remains unchanged.
- Validation command: focused subprocess CLI regressions, related CLI/analysis/comparison/storage
  tests, and `make check` (`311 passed, 188 subtests passed`).
- Commit required: yes.
- Dependencies: complete ARA-032 so shared analysis/compare tests remain isolated by root cause.

## ARA-034 - Require an explicit boolean resume eligibility flag

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: checkpoint values such as `"false"`, `"true"`, or `1` are truthy, so a malformed
  `can_resume` field can start agents and overwrite an explicitly ineligible checkpoint. A huge or
  non-finite `best_score` can also crash or contaminate the preview before the fail-safe decision.
- Related files: `src/resume.py`, resume/round-loop tests, CLI exit-code tests, recovery records
- Acceptance criteria: only JSON boolean `true` is resume-eligible; every other type fails before
  runner/agent invocation or artifact writes. Preview `best_score` accepts only finite representable
  numbers, and malformed values use the existing safe default without traceback.
- Validation command: focused preview/end-to-end/CLI regressions (`3 passed, 11 subtests passed`),
  related resume/CLI/UI tests (`137 passed, 114 subtests passed`), recovery-state consistency, then
  `make check` (`314 passed, 199 subtests passed`).
- Commit required: yes.
- Dependencies: clean, remote-equal ARA-033 checkpoint `f44687e`.

## ARA-035 - Keep legacy metric aggregates finite and strict JSON

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: non-score legacy timings, evolution values, rubric values, and token counters can
  propagate `NaN`/`Infinity`, overflow derived totals, or raise `OverflowError` during provider-free
  analysis/comparison.
- Related files: `src/metrics.py`, `src/run_compare.py`, metric/analysis/compare tests
- Acceptance criteria: malformed/non-finite legacy metric values are skipped or use documented
  unavailable defaults; finite ordinary aggregates retain their historical results; derived
  overflow never emits non-standard JSON or traceback.
- Validation command: strict-JSON numeric-boundary matrix, real CLI analysis/compare subprocess
  tests, related metrics/analysis/compare/CLI tests (`59 passed, 20 subtests passed`), broader
  runner/diagnostic/UI regression (`172 passed, 116 subtests passed`), then `make check` (`321
  passed, 201 subtests passed`).
- Commit required: yes.
- Dependencies: complete ARA-034 without combining recovery and metric semantics.

## ARA-036 - Reject unrepresentable Judge numeric fields without crashing

- Status: `DONE`
- Priority: P1
- Risk: low
- Description: a structured Judge score or rubric integer such as `10**400` raises uncaught
  `OverflowError` during float coercion instead of being classified as invalid Judge output.
- Related files: `src/judge_output.py`, Judge parser tests, runner invalid-score tests
- Acceptance criteria: unrepresentable score/rubric values are rejected like other invalid or
  non-finite values; valid JSON and legacy score parsing remain unchanged; no round/process
  traceback is introduced.
- Validation command: focused Judge parser and round-loop invalid-score regressions, related Judge/
  round-loop tests (`52 passed, 75 subtests passed`), then `make check` (`323 passed, 201 subtests
  passed`).
- Commit required: yes.
- Dependencies: keep separate from ARA-035 metric artifact aggregation.

## ARA-037 - Normalize survey manual interrupts to status 130

- Status: `DONE`
- Priority: P2
- Risk: low
- Description: a `KeyboardInterrupt` inside Literature Survey Mode releases its lock but exits as
  signal status `-2` with traceback/path disclosure instead of the documented status 130 contract.
- Related files: `src/cli.py`, CLI interrupt tests, survey tests
- Acceptance criteria: survey interruption emits the standard fixed diagnostic, exits 130 without
  traceback or absolute paths, and still releases the real run lock.
- Validation command: direct and real module subprocess interrupt regressions, survey/CLI tests
  (`36 passed, 20 subtests passed`), then `make check` (`324 passed, 201 subtests passed`).
- Commit required: yes.
- Dependencies: ARA-023 interrupt contract and ARA-033 privacy-safe CLI precedent.

## ARA-038 - Contain cloud discovery lazy-iteration and artifact-write failures

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: SDK lazy-pager iteration and discovery/profile artifact `OSError` failures escape the
  documented cloud-free error contract with traceback/path disclosure; profile cannot use its
  documented configured-seed fallback when lazy iteration fails.
- Related files: `src/cloud_free.py`, `src/cli.py`, cloud-free and CLI exit-code tests
- Acceptance criteria: lazy iteration is covered by the safe discovery error result; explicit
  discovery remains status 1, profile fallback remains status 0, and artifact-write failures use a
  fixed path-free status-1 diagnostic.
- Validation command: injected lazy-pager/write failures (`3 passed, 6 subtests passed`), cloud-free/
  CLI tests (`50 passed, 34 subtests passed`), then `make check` (`326 passed, 207 subtests passed`).
- Commit required: yes.
- Dependencies: ARA-033 output-error contract; no real provider call.

## ARA-039 - Fail before writes on unreadable prior-round resume context

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: invalid UTF-8 in an existing prior-round Judge artifact is silently converted to an
  empty drafting context, and resume continues after writing new startup metadata.
- Related files: `src/runner.py`, `src/storage.py`, resume history/context tests
- Acceptance criteria: an existing but unreadable prior-round context artifact blocks resume before
  automatic writes or agent invocation; genuinely missing legacy context follows an explicit
  compatibility policy.
- Validation command: byte-preservation four-context invalid-UTF8/read-failure matrix (`4 passed, 8
  subtests passed`), resume/round-loop/CLI tests (`80 passed, 107 subtests passed`), then `make
  check` (`328 passed, 215 subtests passed`).
- Commit required: yes.
- Dependencies: ARA-034 strict checkpoint eligibility first.

## ARA-040 - Reconcile cached cloud discovery/profile membership

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: a discovery failure can save a new fallback profile while retaining stale discovery
  data, causing the next process to recommend a model deliberately excluded by the current fallback.
- Related files: `src/cloud_free.py`, cloud artifact schemas/loaders, cloud-free CLI tests
- Acceptance criteria: stale discovery is ignored safely when its candidate membership differs from
  a non-empty profile; a later process cannot reintroduce the ignored model. This task does not claim
  generation provenance for artifacts whose membership happens to match.
- Validation command: two-process stale-cache and exact/no-profile/partial/unsafe/duplicate/legacy/
  current-policy controls, cloud-free/CLI/UI/recovery tests (`120 passed, 56 subtests passed`), then
  `make check` (`329 passed, 215 subtests passed`).
- Commit required: yes.
- Dependencies: ARA-038 error-boundary work; ARA-042 separately owns UI session cache identity.

## ARA-041 - Make resume startup metadata recoverable across multi-file failure

- Status: `DONE`
- Priority: P2
- Risk: high
- Description: a failure writing `run_manifest.json` after `run_config.json` can leave only the
  config advanced to running/resume-session state while checkpoint, manifest, and histories remain
  old, even though no agent was invoked.
- Related files: `src/runner.py`, run-config/manifest/checkpoint writers, fault-injection tests
- Acceptance criteria: every startup write-point failure leaves a documented recoverable state or
  restores the complete prior metadata generation; no file silently claims an unstarted session.
- Validation command: per-write fault-injection matrix, recovery/resume tests, then `make check`.
- Commit required: yes.
- Dependencies: owner approved the greater-than-30-minute cross-file transaction work on
  2026-07-12; do not fold in unrelated resume validation, artifact schema, or provider behavior.
- Progress: the red regression, fixed hidden-journal protocol, crash/rollback/write-point matrix,
  related `90 passed, 103 subtests passed` regression, and user/developer recovery documentation are
  committed as `2480a61`; validation state is `877562e`. Independent review and full `make check`
  are green, exact remote equality is verified, and push/PR runs `29187626378`/`29187628011`
  passed Python 3.10/3.13 with zero annotations.

## ARA-042 - Scope and refresh UI cloud-free session caches

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: Streamlit stores discovered models and profile results under global session keys, so
  switching projects or updating artifacts through an external CLI can retain stale in-memory data,
  including when model ID membership is unchanged.
- Related files: `ui/app.py`, cloud-free UI state helpers, UI/backend tests
- Acceptance criteria: cached cloud-free state is bound to the selected canonical project and
  invalidated when the underlying discovery/profile artifacts change; project switches and external
  same-ID metadata updates cannot reuse the prior session's recommendation inputs.
- Validation command: two-project switch and external-refresh UI state regressions, cloud-free/UI
  tests, then `make check`.
- Commit required: yes.
- Dependencies: complete ARA-040 membership reconciliation first; no provider call.

## ARA-043 - Respect blocking profiles when every cached candidate failed

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: `recommend_free_cloud_model` falls back to a safe seed after every candidate was
  excluded by quota, reachability, billing-safety, or token-context profile results, potentially
  selecting a model the same profile says is unusable.
- Related files: `src/cloud_free.py`, CLI/UI recommendation behavior, cloud-free tests
- Acceptance criteria: when every candidate has a blocking profile, automatic recommendation is
  unavailable rather than selecting one of those candidates; genuinely unprofiled safe candidates
  retain the documented fallback behavior.
- Validation command: auto/quality/volume blocking and recommendation/fallback property matrices,
  cloud-free/CLI/UI/recovery tests (`121 passed, 68 subtests passed`), then `make check` (`330
  passed, 227 subtests passed`).
- Commit required: yes.
- Dependencies: ARA-040 cached membership guard; no provider call.

## ARA-044 - Scope UI health results to the checked target

- Status: `DONE`
- Priority: P2
- Risk: low
- Description: Streamlit stores raw Ollama and Gemini health results under provider-global session
  keys, so changing the effective model or Ollama base URL can display a prior target's success or
  failure beside the current target.
- Related files: `ui/app.py`, UI helper tests
- Acceptance criteria: health results are displayed only when provider, normalized effective model,
  and non-secret connection scope match the check that produced them; legacy/malformed entries and
  changed targets disappear, while an unchanged target retains its result.
- Validation command: provider-free scoped-session regressions, existing health/UI/recovery tests,
  then `make check`.
- Commit required: yes.
- Dependencies: none; do not perform a real health request or persist/hash credentials.

## ARA-045 - Align Gemini credential redaction with the key actually used

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: when both built-in Gemini environment variables are populated, google-genai uses
  `GOOGLE_API_KEY` but `GeminiClient._available_api_key()` selects `GEMINI_API_KEY` for
  `known_secrets`, so a provider error can retain the actual Google key in events and exception
  causes.
- Related files: `src/llm.py`, `src/cloud_free.py`, provider redaction tests
- Acceptance criteria: client creation/key-availability/redaction resolve one consistent effective
  credential source for explicit, custom-env, Google/Gemini fallback, and both-built-in cases; no
  used key survives provider events, public exceptions, or chained causes.
- Validation command: provider-free fake-SDK credential precedence/redaction matrix, LLM/security
  regressions (`53 passed, 33 subtests passed`), two independent reviews, then `make check` (`346
  passed, 246 subtests passed`).
- Commit required: yes.
- Dependencies: completed provider-free at implementation commit `938b9a2`; no real provider request
  or credential value entered persisted test output/state.

## ARA-046 - Redact credentials from Ollama endpoint failures

- Status: `DONE`
- Priority: P1
- Risk: low
- Description: a valid Ollama base URL may contain URL userinfo or query credentials; request and
  API-fallback failures currently copy the configured endpoint and raw exception into console/run
  errors and provider events, exposing those credentials.
- Related files: `src/config.py`, `src/llm.py`, provider-free config/LLM tests, recovery state
- Acceptance criteria: Ollama request, timeout, and model-list fallback diagnostics retain a useful
  scheme/host/port endpoint label but never expose configured userinfo, query values, or private
  path text in public errors, event payloads, or exception chains; ordinary credential-free URLs
  and request behavior remain unchanged.
- Validation command: provider-free fake-request redaction regressions; related config/LLM/UI/CLI
  tests passed `138 passed, 129 subtests`; final `make check` passed `366 passed, 310 subtests`.
- Commit required: yes.
- Dependencies: completed at remote-equal implementation `3f3826b`; push/PR runs
  `29250140431`/`29250143238` passed Python 3.10/3.13 with zero annotations. No URL acceptance
  change, real Ollama call, or ignored runtime access.

## ARA-047 - Reject unrepresentable resume-history scores without traceback

- Status: `DONE`
- Priority: P1
- Risk: low
- Description: `_history_float()` directly converts numeric history values, so a valid 400-digit
  JSON integer raises `OverflowError` during resume instead of following invalid-history handling.
- Related files: `src/runner.py`, resume history tests
- Acceptance criteria: positive and negative unrepresentable history scores fail before writes or
  agent calls through the existing privacy-safe `ResumeHistoryError`/status-2 boundary; finite
  historical values remain unchanged.
- Validation command: provider-free unsafe-history and compatibility cases passed `4 passed, 20
  subtests`; related resume/runner/CLI/recovery tests passed `95 passed, 130 subtests`; final `make
  check` passed `368 passed, 316 subtests`.
- Commit required: yes.
- Dependencies: completed at remote-equal implementation `d7708b3`; push/PR runs
  `29251545910`/`29251548644` passed Python 3.10/3.13, all four wheel-smoke steps, and zero
  annotations. No provider call or ignored runtime access.

## ARA-048 - Reject conflicting primary CLI modes before any work

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: primary flags are not mutually exclusive; for example `--mock --resume` selects the
  earlier mock branch, creates a new run, and replaces the active checkpoint instead of rejecting
  an invalid command.
- Related files: `src/cli.py`, parser/entrypoint/installed-layout tests
- Acceptance criteria: conflicting execution modes exit 2 during argument handling before layout,
  config, project, or artifact access; every individual mode and compatible modifier remains
  accepted.
- Validation command: parser conflict matrix plus source/module and temporary installed-layout
  no-write subprocess regressions, then `make check`.
- Commit required: yes.
- Dependencies: none; identify modifiers separately from primary modes before changing the parser.
- Completion: all 45 primary-mode pairs in both orders now reject during parsing; individual modes,
  normal mode, and compatible modifiers pass. Focused tests pass `6 passed, 100 subtests`, related
  tests pass `122 passed, 238 subtests`, full `make check` passes `373 passed, 416 subtests`, and
  three independent reviews returned GO. Implementation `1ab338a` is pushed with exact remote/PR
  equality; push/PR runs `29253175885`/`29253180079` are successful on Python 3.10/3.13 with all
  four final wheel steps passing and zero annotations. The push run required one failed-job retry
  after a pre-checkout GitHub HTTP 503 action-download outage.

## ARA-049 - Make UI session credentials authoritative for the launched run

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: Streamlit health/discovery selects its password-box key over config, but the child
  CLI can still select an explicit config key or inherited `GOOGLE_API_KEY`, so the real run uses a
  different account/quota than the UI checked.
- Related files: `ui/app.py`, `src/runtime.py`, provider environment/credential tests
- Acceptance criteria: a nonempty session key is the actual child-run key even with competing
  config/Google/Gemini sources; when no session key is supplied, existing precedence is unchanged;
  credentials never enter argv or process metadata.
- Validation command: provider-free child-environment and fake-client precedence matrix plus UI/LLM
  regressions, then `make check`.
- Commit required: yes.
- Dependencies: preserve the ARA-045 effective-key and redaction contract.
- Completion: implementation `d75fe11` is pushed with exact local/upstream/`ls-remote`/PR-head
  equality. Focused tests pass `4 passed, 10 subtests`, related tests pass `157 passed, 127
  subtests`, and full `make check` passes `376 passed, 426 subtests`. Three independent reviews
  report GO; push/PR runs `29255525721`/`29255530241` passed Python 3.10/3.13, all four isolated
  wheel steps, and zero annotations. Draft PR body readback is exact.

## ARA-050 - Preflight installed generation resources before writing

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: an installed mock can complete successfully with a missing bundled prompt and write
  incomplete prompt provenance because deterministic agents never read the missing file.
- Related files: `src/package_resources.py`, `src/cli.py`, installed-layout tests
- Acceptance criteria: generation modes require all four readable, nonempty, valid-UTF-8 prompt
  resources before seeding or artifact writes; analysis/comparison early exits and healthy packaged
  behavior remain unchanged.
- Validation command: temporary installed-layout missing/corrupt resource matrix, package/CLI tests,
  isolated wheel smoke, then `make check`.
- Commit required: yes.
- Dependencies: preserve ARA-004/030 resource inventory and never use repository ignored runtime.
- Completion: implementation `be3bc04` is pushed with exact local/upstream/`ls-remote`/PR-head
  equality. Focused tests pass `5 passed, 23 subtests`, related tests pass `92 passed, 71 subtests`,
  and full `make check` passes `381 passed, 449 subtests`; isolated wheel smoke and three
  independent reviews are green. Push/PR runs `29257476266`/`29257478876` passed Python 3.10/3.13,
  all four wheel steps, and zero annotations.

## ARA-051 - Fail closed on duplicate conflicting cloud profiles

- Status: `DONE`
- Priority: P2
- Risk: low
- Description: duplicate profile IDs are reduced by last-record-wins dictionaries, so ordering can
  let a healthy duplicate override a blocked record and re-enable an ineligible model.
- Related files: `src/cloud_free.py`, cloud recommendation/fallback tests
- Acceptance criteria: duplicate conflicting profiles cannot recommend or select that model in any
  order; unique healthy profiles and ordinary cached candidates remain compatible.
- Validation command: both duplicate orders across cached pool, recommendation, and fallback plus
  cloud/UI regressions, then `make check`.
- Commit required: yes.
- Dependencies: preserve ARA-040/043 candidate-membership and all-blocked behavior.
- Completion: implementation `ab7d6fe` is pushed with exact local/upstream/`ls-remote`/PR-head
  equality. Focused tests pass `4 passed, 22 subtests`, related tests pass `139 passed, 127
  subtests`, and full `make check` passes `383 passed, 459 subtests`. Three independent reviews
  report GO; push/PR runs `29258640040`/`29258641820` passed Python 3.10/3.13, all four wheel steps,
  and zero annotations.

## ARA-052 - Normalize malformed Ollama health response shapes

- Status: `DONE`
- Priority: P2
- Risk: low
- Description: Streamlit Ollama health assumes a mapping response; valid JSON lists/strings raise
  `AttributeError` instead of returning a structured unhealthy result.
- Related files: `ui/app.py`, UI health tests
- Acceptance criteria: non-object response JSON produces a fixed credential-safe health failure;
  valid object responses and request targets remain unchanged.
- Validation command: provider-free response-shape matrix and UI health/recovery tests, then
  `make check`.
- Commit required: yes.
- Dependencies: preserve ARA-044 target-scoped snapshot behavior.
- Completion: implementation `2141b7d` is pushed with exact local/upstream/`ls-remote`/PR-head
  equality. Focused tests pass `3 passed, 14 subtests`, related config/UI/recovery tests pass `96
  passed, 92 subtests`, and full `make check` passes `384 passed, 465 subtests`. Three independent
  reviews report GO; push/PR runs `29259494746`/`29259495850` passed Python 3.10/3.13, all four
  wheel steps, and zero annotations.

## ARA-053 - Remove unsafe-path collisions from UI health identity

- Status: `DONE`
- Priority: P2
- Risk: low
- Description: non-allowlisted Ollama paths are represented only by segment lengths, so equal-length
  paths such as `/alpha` and `/bravo` can share an identity and display stale health evidence.
- Related files: `ui/app.py`, target-scoped UI health tests
- Acceptance criteria: distinct private paths never share health identity while no path value or
  reversible credential-derived material is stored; same target remains stable.
- Validation command: same-length private-path collision regressions plus UI/recovery tests, then
  `make check`.
- Commit required: yes.
- Dependencies: design a non-secret identity consistent with ARA-044; do not hash credentials.
- Local validation: deterministic length collisions and stale-cache reuse are fixed by a
  process-local keyed path identifier. Focused tests pass `4 passed, 14 subtests`, related tests pass
  `104 passed, 110 subtests`, and indexed full `make check` passes `392 passed, 569 subtests` with 104
  files in both safety scans; three reviews report GO.
- Completion: implementation `98dffb5` is pushed with exact local/upstream/`ls-remote`/PR-head
  equality. Push/PR runs `29262351625`/`29262353455` passed Python 3.10/3.13, all four isolated-wheel
  steps, and zero annotations.

## ARA-054 - Reconcile resumable mid-round stops with partial output directories

- Status: `DONE`
- Priority: P2
- Risk: high
- Description: interrupts or quota stops after review/revise/Judge persist a partial next-round
  directory and mark `can_resume=true`, but immediate preview correctly rejects that directory as
  uncheckpointed, making the claimed resume state unusable without manual file movement.
- Related files: `src/runner.py`, `src/resume.py`, round lifecycle/recovery tests
- Acceptance criteria: checkpoint eligibility and immediate preview agree after every stage without
  deleting or overwriting partial evidence; completed rounds remain intact.
- Validation command: per-stage interrupt/quota matrix, byte-preservation/retry tests, then
  `make check`.
- Commit required: yes after scoped design approval.
- Dependencies: requires an explicit staging/quarantine or partial-round compatibility design;
  estimated greater than 30 minutes and must not silently delete partial outputs.
- Approval: after the completed design stage, the owner said `继续` on 2026-07-23. This authorizes
  implementation package 1 only: create-only attempt storage primitives and the shared recovery
  classifier. Runtime writer switching, canonical publication, legacy migration, and ARA-055 are
  not part of this package. No existing partial evidence may be moved, deleted, or overwritten.
- Design baseline: `make check` passes `399 passed, 621 subtests` over 105 tracked files in 20.90
  seconds with zero provider calls. Provider-free stage characterization is next.
- Design result: completed in `docs/ARA_054_PARTIAL_ROUND_RECOVERY_DESIGN.md` and committed as
  `946f40f`. The eight-case post-persistence matrix confirms checkpoint/preview disagreement while
  preserving all bytes. Append-only attempt staging with whole-round retry is selected; mid-stage
  continuation and rollback are rejected.
- Design validation: indexed `make check` passes `399 passed, 621 subtests` over 106 files in 21.00
  seconds. Push/PR runs `30007167214`/`30007170465` passed Python 3.10/3.13 and isolated-wheel
  validation.
- Foundation result: `e4e784e` adds create-only anchored attempt storage, strict manifest/output
  inspection, shared recovery classification, and the initial 32-attempt cap without changing the
  runner or resume preview. Focused tests pass `9 passed, 4 subtests`; indexed `make check` passes
  `408 passed, 625 subtests` over 108 files.
- Foundation verification: exact local/upstream/`ls-remote`/PR-head equality; push/PR runs
  `30012047804`/`30012050777` passed Python 3.10/3.13 and isolated-wheel validation.
- Foundation dependency at that checkpoint: manifest transitions, runtime writer/preview
  integration, empty-canonical handling, disk-budget policy, and publication required the later
  runtime-package approval recorded below. Explicit legacy migration and ARA-055 remain separate.
- Runtime-package approval: after receiving the exact recommended next task, the owner said
  `继续` on 2026-07-23. This authorizes manifest transitions, empty-canonical handoff,
  disk-budget protection, staged runner writes, canonical publication, and shared resume-preview
  diagnostics. It does not authorize legacy migration or folding in ARA-055.
- Runtime-package baseline: exact local/upstream/`ls-remote`/PR-head equality at `816b035`; push/PR
  runs `30012529719`/`30012529172` pass. Provider-free `make check` passes `408 passed, 625
  subtests` over 108 files in 22.65 seconds.
- Runtime completion: commits `87f37d3` and `75f3d9a` add verified state transitions, bounded
  storage, atomic no-replace and retained-copy publication, staged runner writes, shared
  preview/resume eligibility, and additive checkpoint diagnostics. The four-stage manual
  interrupt/cloud-quota matrix is resumable without changing canonical completed-round bytes.
- Final validation: related tests pass `232 passed, 468 subtests`; full pytest passes `417 passed,
  633 subtests`; `make check` passes all formatting, lint, import, safety, and test gates over 108
  tracked files. Exact local/upstream/`ls-remote`/PR-head equality holds at `75f3d9a`; push/PR runs
  `30016026758`/`30016026741` passed Python 3.10/3.13 and isolated-wheel validation.

## ARA-055 - Make round history publication recoverable across two filesystems

- Status: `DEFERRED`
- Priority: P2
- Risk: high
- Description: project-global score history is written before run-local round metrics; failure of
  the second write leaves split generations that cannot be retried, and configured run storage may
  reside on another filesystem.
- Related files: `src/runner.py`, `src/storage.py`, history transaction tests
- Acceptance criteria: second-write I/O/interrupt failures recover deterministically without
  duplicate rounds or cross-filesystem atomic-rename assumptions.
- Validation command: two-write fault/crash/retry matrix with internal and external run storage,
  then `make check`.
- Commit required: yes after architecture approval.
- Dependencies: cross-file/cross-filesystem transaction design; estimated greater than 30 minutes.
- Approval: after ARA-054 closeout recommended ARA-055 design as the next high-value task, the
  owner explicitly said `批准` on 2026-07-23. This authorizes tracked-code inspection,
  provider-free temporary fault characterization, and design/recovery documentation only.
  Runtime transaction implementation, artifact migration, dependency changes, and ignored runtime
  access remain outside scope.
- Design baseline: exact local/upstream/`ls-remote`/PR-head equality at `a7eacfe`; push/PR runs
  `30016446806`/`30016453110` pass Python 3.10/3.13 and isolated-wheel validation. Provider-free
  `make check` passes `417 passed, 633 subtests` over 108 tracked files in 34.21 seconds.
- Design result: `docs/ARA_055_CROSS_FILESYSTEM_ROUND_COMMIT_DESIGN.md` records the writer/reader
  map, 40-case fault matrix, selected immutable project-local write-ahead journal, idempotent
  before/after-hash roll-forward, checkpoint-last commit point, separate finalization transaction,
  compatibility rules, security bounds, and implementation packages.
- Design verification: commit `09aeda6` is exact local/upstream/`ls-remote`/PR-head equal;
  push/PR runs `30018465335`/`30018466172` pass Python 3.10/3.13 and every isolated-wheel/check
  step. Local full validation is `417 passed, 633 subtests`; staged safety scans 109 files clean.
- Remaining approval boundary: runtime packages remain unapproved. Do not add journals, reroute
  runtime readers/writers, integrate diagnostic mode, change artifact schemas, or migrate
  historical `published_uncommitted` evidence without separate owner approval.
- Package 1 approval: after the design closeout recommended pure builders and a strict journal
  codec, the owner explicitly said `批准` on 2026-07-23. This authorizes deterministic after-image
  builders, strict bounded in-memory schema encode/decode, fixed artifact enums, and provider-free
  tests only.
- Package 1 exclusions: do not create/read a runtime journal file, register journal paths, recover
  or publish attempts, route runner/preview/UI/diagnostic code, mutate artifacts, add dependencies,
  or migrate legacy evidence. Packages 2-7 remain deferred.
- Package 1 baseline: exact local/upstream/`ls-remote`/PR-head equality at `ccdfcf4`; push/PR runs
  `30018740608`/`30018744223` pass Python 3.10/3.13 and every isolated-wheel/check step. Local
  provider-free `make check` passes `417 passed, 633 subtests` over 109 tracked files in 33.66s.
- Package 1 result: implementation commit `4cd4bf4` adds byte-compatible pure history, memory, and
  research-state extraction plus deterministic checkpoint/summary/config after-images and a strict
  bounded in-memory round-journal codec. It performs no filesystem I/O and has no runtime caller.
- Package 1 verification: focused tests pass `14 passed, 55 subtests`; related regression passes
  `111 passed, 277 subtests`; final `make check` passes `431 passed, 688 subtests`; staged safety
  scans 111 files clean. Exact local/upstream/`ls-remote`/PR-head equality holds at `4cd4bf4`;
  push/PR runs `30020697130`/`30020701903` pass Python 3.10/3.13 and every isolated-wheel/check
  step.
- Deferral boundary: package 1 is complete. Package 2 (runtime round prepare/recovery engine and
  cross-filesystem fault matrix) is the recommended next task but requires explicit owner approval.
  Packages 3-7, migration, dependencies, providers, and ignored runtime remain unapproved.
- Package 2 approval: after the package-1 closeout explicitly recommended the round
  prepare/recovery engine and cross-filesystem fault matrix, the owner said `批准下一个任务` on
  2026-07-24.
- Package 2 authorized scope: add the fixed project-local create-only round journal, trusted
  project/run identity revalidation, dry-run before/after/conflict classification, ARA-054
  publication reconciliation, idempotent roll-forward application, fixed path-redacted
  diagnostics, and provider-free internal/configured-external fault tests.
- Package 2 exclusions: do not route the iterative runner, resume preview, UI, analytics, reports,
  or diagnostic mode through the engine; do not add the finalization journal, migrate legacy
  evidence, change dependencies, call providers, inspect ignored runtime, or start packages 3-7.
- Package 2 baseline: exact local/upstream/`ls-remote`/PR-head equality at `064f5bd`; push/PR runs
  `30021141942`/`30021145878` pass Python 3.10/3.13 and every isolated-wheel/check step. Local
  provider-free `make check` passes `431 passed, 688 subtests` over 111 tracked files in 33.38s.
- Package 2 activation: commit `e899268` is exact local/upstream/`ls-remote` equal; push/PR runs
  `30024767388`/`30024770453` pass Python 3.10/3.13 and every check step.
- Package 2 local result: the dormant engine and trusted storage primitives are implemented without
  a runner caller. The internal/configured-external before/after matrix covers create, publication,
  every artifact, cleanup, `OSError`, and `KeyboardInterrupt`; focused/related validation passes
  `75 passed, 162 subtests`; full `make check` passes `449 passed, 787 subtests` plus every format,
  lint, import, and safety gate. Commit, push, PR update, and CI remain.
- Package 2 resume command: explicitly stage the ten task-owned files and run the staged safety
  scan. Packages 3-7 remain unapproved even after package 2 closes.
- Package 2 completion: implementation commit `faf1791e` is exact local/upstream/`ls-remote`/
  PR-head equal; push/PR runs `30026934582`/`30026936443` pass Python 3.10/3.13 and every workflow
  step. Draft PR 13 is updated and cleanly mergeable.
- Package 3 approval: the owner explicitly said `批准 ARA-055 package 3` on 2026-07-24.
- Package 3 authorized scope: route successful iterative rounds through `prepare_round_commit` and
  `recover_round_commit`, create the immutable journal before the ready transition, keep checkpoint
  last, and preserve ordinary outputs and control flow.
- Package 3 acceptance: runner-order regression plus internal/configured-external provider-free
  fault/retry validation proves no duplicate round and exact artifact convergence, followed by
  related regression, `make check`, staged safety, push, and Python 3.10/3.13 CI.
- Package 3 exclusions: no packages 4-7; no resume-preview, UI, analytics, report, or diagnostic
  routing; no finalization journal, legacy migration, dependency/config change, provider call, or
  ignored-runtime access.
- Package 3 baseline: exact local/upstream/`ls-remote`/PR-head equality at `9d04f46`; push/PR runs
  `30027550772`/`30027556705` pass Python 3.10/3.13 and every workflow step.
- Current work: activation checkpoint before runner edits. The next focused command is
  `.venv/bin/python -m pytest -q tests/test_round_commit_runner.py`.
- Package 3 result: implementation `54c223b` routes new and fully evidenced histories through
  prepare/recover before publication, keeps checkpoint last, accepts only safety-validated
  equivalent checkpoint roots, and preserves incomplete legacy histories without fabricated
  migration.
- Package 3 validation: focused/related `142 passed, 382 subtests`; runner layer `67 passed, 220
  subtests`; full `make check` `453 passed, 791 subtests`; staged safety 114 files clean.
- Package 3 remote verification: exact local/upstream/`ls-remote`/PR-head equality; push/PR runs
  `30030145901`/`30030150062` pass Python 3.10/3.13 and every workflow step. Draft PR 13 is updated.
- Package 4 approval: after package 3 closeout explicitly recommended the recovery-entry/read-only
  consumer package, the owner said `批准，继续` on 2026-07-24.
- Package 4 authorized scope: recover an exact valid pending round journal under the existing
  project lock before new runner/provider work; expose read-only recovery-required and conflict
  classifications to preview/UI/report/analytics consumers; reject mixed-generation reads without
  mutation or path disclosure.
- Package 4 acceptance: valid pending entry recovery is provider-free and idempotent; conflict and
  malformed journals fail before provider construction or artifact mutation; read-only consumers
  do not recover or rewrite; configured external storage and historical journal-less artifacts
  retain compatible behavior; focused/related tests, `make check`, staged safety, push, and Python
  3.10/3.13 CI pass.
- Package 4 validation command: `.venv/bin/python -m pytest -q
  tests/test_round_commit_entry.py tests/test_resume.py tests/test_ui.py
  tests/test_run_analytics.py`, followed by related runner/recovery/report tests and `make check`.
- Package 4 commit required: yes, with activation, implementation, and recovery closeout kept as
  separately understandable stable phases.
- Package 4 exclusions: no finalization journal or finalization reader behavior, diagnostic
  integration, legacy migration, dependency/config changes, provider calls, ignored-runtime
  access, or packages 5-7.
- Package 4 activation verification: `c2a7af5` is exact local/upstream/`ls-remote`/PR-head equal;
  push/PR runs `30031800668`/`30031802489` pass Python 3.10/3.13 and every workflow step.
- Package 4 local result: entry recovery runs under the existing lock before provider/client/agent
  work for every approved iterative mode; read-only preview/UI/analytics/compare/report paths
  expose or reject pending/conflicting round generations without mutation. Finalization-only and
  diagnostic behavior remain excluded.
- Package 4 local validation: focused `9 passed`; related `256 passed, 540 subtests`; recovery
  matrix `16 passed, 99 subtests`; full `make check` `462 passed, 791 subtests`; provider and
  ignored-runtime access zero.
- Package 4 completion: implementation `efcad88` is exact local/upstream/`ls-remote`/PR-head
  equal. Push/PR runs `30034539432`/`30034542276` pass Python 3.10/3.13 and every workflow step;
  draft PR 13 is open and cleanly mergeable, and comment `5062099962` records the result.
- Package-4 result: new and fully evidenced rounds have a recoverable checkpoint-last transaction;
  normal, continuous, session, resume, and mock entries recover a valid pending round under the
  existing lock before provider/client/agent work; preview/UI/analytics/comparison/report readers
  expose or reject pending/conflicting generations without mutation. Finalization remains the
  separately approval-gated package 5.
- Package 5 approval: after the ARA-061 closeout explicitly recommended finalization journaling as
  the next task, the owner said `批准` on 2026-07-24.
- Package 5 authorized scope: fixed project-local create-only finalization journal; exact bounded
  run-summary, finalized run-config, and final-checkpoint after-images; summary/config-before-
  checkpoint recovery; iterative entry recovery under the existing lock; non-mutating
  finalization-pending/conflict guards for approved readers.
- Package 5 acceptance: every summary/config/checkpoint/cleanup `OSError` and `KeyboardInterrupt`
  boundary converges idempotently in internal and configured-external run storage; unknown
  generations fail closed without writes or path disclosure; resumable/manual-interrupt and
  non-resumable/cooperative outcomes preserve artifact bytes and exit behavior; related regression,
  `make check`, staged safety, push, and Python 3.10/3.13 CI pass.
- Package 5 exclusions: no diagnostic integration, legacy migration, dependency/config schema
  changes, provider calls, ignored-runtime access, experiment changes, or packages 6-7.
- Package 5 baseline: exact local/upstream/`ls-remote`/PR-head equality at `11562f6`; push/PR runs
  `30082575170`/`30082577745` pass Python 3.10/3.13 and every workflow step.
- Package 5 next command:
  `.venv/bin/python -m pytest -q tests/test_run_finalize_recovery.py`.
- Package 5 local checkpoint: activation `a6cdd2f` is pushed; strict codec, create-only journal,
  idempotent summary/config/checkpoint recovery, lock-held entry routing, reader blockers, and
  runner/UI integration are implemented locally. Focused validation passes `7 passed, 16 subtests`;
  affected regressions pass `112 passed, 372 subtests`; final `make check` passes `473 passed, 825
  subtests`. Staged safety, commit, push, dual CI, PR update, and recovery closeout remain.
- Package 5 resume command: inspect and explicitly stage the 16 task-owned files. If interrupted,
  first rerun
  `.venv/bin/python -m pytest -q tests/test_run_finalize_recovery.py
  tests/test_round_commit_entry.py` and inspect the task-owned diff.
- Package 5 completion: implementation `5c9f0ce` is exact local/upstream/`ls-remote`/GitHub
  branch/PR-head equal. Push/PR runs `30085545590`/`30085548995` pass Python 3.10/3.13 and every
  workflow step. Full local validation passes `473 passed, 825 subtests`; staged safety scans 116
  files clean. Package 6 diagnostic recovery and package 7 migration remain separately
  approval-gated.
- Package 6 approval: after package 5 closeout recommended diagnostic integration, the owner said
  `批准，继续` on 2026-07-24 after receiving the required long-task assessment.
- Package 6 authorized scope: fixed strict bounded diagnostic-finalize journal for project score
  history, run metrics, summary, finalized config, and checkpoint; checkpoint-last recovery under
  the existing diagnostic entry lock; non-mutating reader guards; package-5 reuse for zero-round
  quota finalization; internal/configured-external provider-free fault coverage.
- Package 6 acceptance: every five-artifact write and cleanup `OSError`/`KeyboardInterrupt`
  boundary converges idempotently; unknown generations fail closed without mutation or path
  disclosure; recovery precedes provider/client work; existing successful and quota diagnostic
  artifact bytes/fields remain compatible; focused/related tests, `make check`, staged safety,
  push, and Python 3.10/3.13 CI pass.
- Package 6 exclusions: no package 7 migration, dependency/config schema/default change, provider
  call, ignored-runtime access, experiment change, or historical artifact mutation.
- Package 6 baseline: exact local/upstream/`ls-remote`/PR-head equality at `ecf9ead`; push/PR runs
  `30086126360`/`30086129319` pass Python 3.10/3.13 and every workflow step. Focused baseline
  passes `60 passed, 160 subtests`; recovery state passes `6 passed, 1 subtest`.
- Package 6 local checkpoint: activation `3d2a48b` is pushed; the fixed five-artifact diagnostic
  journal, checkpoint-last recovery, lock-held entry routing, reader blockers, and zero-round
  package-5 reuse are implemented locally. Static/focused validation passes `9 passed, 24
  subtests`; related regression passes `252 passed, 616 subtests`; full `make check` passes `481
  passed, 849 subtests` plus all static/import/safety gates. Staged safety, commit, push, CI, PR
  update, and closeout remain.
- Package 6 resume command: inspect and explicitly stage the 19 package-owned paths. If interrupted
  before commit, first rerun
  `.venv/bin/python -m pytest -q tests/test_diagnostic_finalize_recovery.py
  tests/test_diagnostic.py tests/test_round_commit_entry.py`.
- Package 6 completion: implementation `24d56ba2a39a6504672d7b42e0f3487707fcf7fc` is exact
  local/upstream/`ls-remote`/PR-head equal. Push/PR runs `30088147987`/`30088150085` pass Python
  3.10/3.13, isolated-wheel validation, every workflow step, and zero annotations. Draft PR 13 is
  open and cleanly mergeable; comment `5069196079` records the evidence. Package 7 legacy migration
  remains separately approval-gated and was not started.
- Package 7 design approval: after package 6 closeout recommended legacy-migration design, the
  owner said `批准 继续` on 2026-07-24 after receiving the long-task scope and risk assessment.
- Package 7 design scope: tracked code/history inspection and temporary synthetic fixtures only;
  classify legacy states and define evidence preservation, provenance, dry-run, explicit execution
  approval, rollback, idempotency, compatibility, and a future package plan.
- Package 7 design acceptance: publish a concrete state/decision/fault matrix that refuses
  ambiguous repair, leaves all existing artifacts byte-identical, separates read-only discovery
  from execution, and passes related provider-free tests, `make check`, staged safety, push, and
  Python 3.10/3.13 CI.
- Package 7 exclusions: no runtime implementation, migration command, artifact read/write outside
  temporary fixtures, ignored runtime, provider/experiment/config/dependency change, or automatic
  cleanup/quarantine.
- Package 7 baseline: exact local/upstream/`ls-remote`/PR-head equality at `fe514e0`; closeout
  push/PR runs `30088704158`/`30088706374` pass Python 3.10/3.13 and every workflow step.
- Package 7 next command: read the ARA-055 design, relevant Git history, compatibility tests, and
  current readers/writers before drafting the migration design.
- Package 7 design result: `docs/ARA_055_LEGACY_MIGRATION_DESIGN.md` rejects general legacy repair
  and defines 21 fixed state classes. Only an absent twin history backed by one strict, complete,
  checkpoint-correlated, uncontested history is a future exact-copy candidate. Partial/conflicting
  histories, journal-less published/canonical/finalization/diagnostic states, legacy manifest
  fallback, and unsafe/unknown evidence remain byte-identical and non-migratable.
- Package 7 design boundaries: discovery is read-only and explicitly targeted; future execution
  would require an owner-selected restricted evidence bundle, one fixed create-only roll-forward
  transaction, and exact-byte no-replace target creation. Discovery, execution, and destructive
  rollback are three independent approval gates; none is implemented or authorized here.
- Package 7 local validation: focused compatibility/recovery suites pass `51 passed, 50 subtests`;
  full `make check` passes `481 passed, 849 subtests` plus formatting, Ruff, imports, and zero-
  finding safety scans over 117 tracked files.
- Package 7 remaining: staged safety/recovery validation, design commit/push, Python 3.10/3.13
  push/PR CI, PR update, and recovery closeout. Recommended next package after closeout is 7A
  read-only classifier/report schema, requiring separate owner approval.
- Package 7 completion: design `e5f3571` is exact local/upstream/`ls-remote`/PR-head equal. Push/PR
  runs `30090592035`/`30090595366` passed Python 3.10/3.13 and every workflow step with zero
  annotations. PR comment `5069543857` records the result. Package 7A discovery implementation,
  package 7C execution, and rollback remain separately approval-gated and were not started.
- Package 7A approval: after package 7 design closeout recommended the read-only classifier/report
  package, the owner said `批准，继续` on 2026-07-24.
- Package 7A authorized scope: implement fixed L00-L20 classification and reason enums, a strict
  additive filesystem-free report builder, and explicitly targeted bounded/no-follow inspection of
  one project with trusted internal/configured-external run identity and redacted output.
- Package 7A acceptance: every design state has synthetic temporary coverage; discovery performs no
  write, stale-lock deletion, recursive project scan, provider/client construction, or execution;
  unsafe/ambiguous states fail closed without paths/raw values; focused/related tests, `make check`,
  staged safety, push, and Python 3.10/3.13 CI pass.
- Package 7A exclusions: no CLI/doctor/UI integration, `--execute`, evidence-bundle/journal/receipt
  write, missing-target creation, rollback/delete/quarantine, batch discovery, dependency/default
  change, provider/network work, ignored-runtime access, or package 7B/7C/7D.
- Package 7A baseline: `f8b770d` is exact remote-equal; push/PR runs
  `30091187286`/`30091190516` pass. Local `make check` passes `481 passed, 849 subtests`, formatting,
  Ruff, imports, and zero-finding safety scans over 118 tracked files.
- Package 7A local result: the internal API implements fixed L00-L20/reason enums, targeted
  bounded/no-follow inspection, a strict JSON report, and bounded human output without any
  integration or mutation caller. Internal/configured-external synthetic coverage includes every
  design row and both source directions.
- Package 7A local validation: focused coverage passes `17 passed, 114 subtests`; related ARA-054/
  ARA-055, runner, storage, run-config, mock, and CLI regression passes `224 passed, 642 subtests`.
  Recovery validation passes `6 passed, 1 subtest`; the isolated wheel smoke passes; final
  `make check` passes `498 passed, 963 subtests` plus every static/import/safety gate over 120
  tracked/index files with zero findings.
- Package 7A pre-commit checkpoint: all nine task-owned paths are explicitly staged; final staged
  safety scans 120 files with zero findings and cached diff checks pass. This checkpoint was
  subsequently committed and remotely verified as recorded below.
- Package 7A completion: implementation `f9b29f8fb324c1c07805128071b69aa978324a5f` is exact
  local/upstream/`ls-remote`/GitHub branch/PR-head equal. Push/PR runs
  `30098547791`/`30098553022` passed Python 3.10/3.13 and every workflow step; all four annotation
  sets are empty. PR comment `5070698572` records the result.
- Deferral boundary: ARA-055's approved work is complete through package 7A. Package 7B discovery
  integration, package 7C exact-copy execution, and any rollback remain separately approval-gated;
  no unblocked ARA-055 implementation is active.

## ARA-056 - Cover interrupts before the protected agent phase

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: an interrupt after round directory creation but before the agent-stage `try` can
  leave `status=running`, an empty round directory, and no checkpoint/summary/recovery entry.
- Related files: `src/runner.py`, interrupt lifecycle tests
- Acceptance criteria: round creation/log/memory-load interrupts either roll back pre-publication
  state or finalize the standard manual-interrupt recovery artifacts without corrupting a run.
- Validation command: pre-agent interrupt fault matrix plus manual-interrupt/resume tests and
  `make check`.
- Commit required: yes.
- Dependencies: preserve ARA-023 status 130 and ARA-041 startup transaction ordering.
- Approval: owner explicitly approved the greater-than-30-minute, medium-risk work on 2026-07-23.
- Completion: the expected pre-fix fault matrix produced `3 failed`; focused final coverage
  passes `2 passed, 3 subtests`, the CLI status/lock layer passes `3 passed`, related runner/CLI/
  session/storage/recovery coverage passes `135 passed, 339 subtests`, and indexed `make check` passes
  `399 passed, 621 subtests` with 105 tracked files and zero safety findings. Implementation
  `795665d` is pushed with exact local/upstream/`ls-remote`/PR-head equality; push/PR runs
  `30004044807`/`30004047971` passed Python 3.10/3.13, all four isolated-wheel steps, and zero
  annotations.

## ARA-057 - Reject orphan mode-specific output options before work

- Status: `DONE`
- Priority: P1
- Risk: low
- Description: `--survey-output`, `--compare-output`, or `--analyze-output` without its matching
  primary selector falls through to a normal/provider run, potentially performing paid or
  artifact-writing work instead of reporting invalid arguments.
- Related files: `src/cli.py`, parser and source/installed entrypoint tests
- Acceptance criteria: each output option requires its matching primary mode and rejects any orphan
  or mismatched-mode use during argument handling; correct mode/output pairs and output-free modes
  remain compatible.
- Validation command: parser dependency matrix plus source/module and temporary installed-layout
  no-work subprocess regressions, then `make check`.
- Commit required: yes.
- Dependencies: complete ARA-048 without folding this separate requires-relationship into its
  primary-mode mutual-exclusion fix.
- Completion: implementation `eabedff` is pushed with exact local/upstream/`ls-remote`/PR-head
  equality. Focused tests pass `4 passed, 90 subtests`, related CLI/runner/package/survey/compare/
  recovery tests pass `141 passed, 352 subtests`, and full `make check` passes `388 passed, 555
  subtests`. Three independent reviews report GO; push/PR runs `29260853734`/`29260855184` passed
  Python 3.10/3.13, all four wheel steps, and zero annotations.

## ARA-058 - Validate the nested Ollama models response shape

- Status: `DONE`
- Priority: P2
- Risk: low
- Description: an object response whose `models` value is `null` or numeric still raises
  `TypeError` while iterating instead of returning a structured unhealthy result.
- Related files: `ui/app.py`, UI health tests
- Acceptance criteria: malformed nested `models` values fail closed with fixed credential-safe
  diagnostics; omitted/list-valued `models`, valid model records, request targets, and ARA-052
  outer-shape behavior remain compatible.
- Validation command: provider-free nested response-shape matrix plus UI/recovery tests, then
  `make check`.
- Commit required: yes.
- Dependencies: preserve ARA-044, ARA-046, and ARA-052 health contracts without broad schema
  migration.
- Completion: implementation `0511a47` is pushed with exact local/upstream/`ls-remote`/PR-head
  equality. The exact list guard returns fixed `InvalidResponse` for all JSON non-list shapes before
  installed fallback. Focused tests pass `3 passed, 18 subtests`, related tests pass `101 passed,
  120 subtests`, and full `make check` passes `393 passed, 581 subtests`; three independent final
  reviews report GO. Push/PR runs `29263804804`/`29263808869` passed Python 3.10/3.13, all four
  wheel steps, and zero annotations.

## ARA-059 - Reject non-string Ollama model names

- Status: `DONE`
- Priority: P2
- Risk: low
- Description: list-valued API responses coerce null, boolean, numeric, list, or object `name`
  fields with `str(...)`, so a selected string such as `None` or `True` can be reported healthy.
- Related files: `ui/app.py`, `src/config.py`, Ollama response/parser tests
- Acceptance criteria: only nonblank string model names can enter UI health or normalized model
  inventories; valid strings, invalid list records, exact requests, and redaction remain compatible.
- Validation command: provider-free record-name type matrix across UI health and shared tags parser,
  then related tests and `make check`.
- Commit required: yes.
- Dependencies: satisfied by ARA-058 implementation `0511a47`, which kept record-field schema policy
  outside its container guard.
- Local validation: one shared scalar helper now accepts and trims only strings before inventory
  de-duplication or UI availability matching. The strengthened pre-fix matrix exited 1 with `18
  failed`; focused final tests pass `2 passed, 37 subtests`, and related UI/config/recovery tests
  pass `103 passed, 157 subtests`. Full `make check` passes `395 passed, 618 subtests` with 104
  tracked/index files and zero safety findings. Parent-level mutation probes catch both falsey
  non-list parser output and installed-name whitespace normalization even when subtest assertions
  are swallowed. Three independent reviews and the indexed full gate (`395 passed, 618 subtests`)
  are green.
- Completion: implementation `a7d00a6` is pushed with exact local/upstream/`ls-remote`/PR-head
  equality. Push/PR runs `29266119109`/`29266121277` passed Python 3.10/3.13, all four isolated-wheel
  steps, and zero annotations.

## ARA-060 - Verify unittest subtest failures fail the pytest process

- Status: `DONE`
- Priority: P2 (downgraded after direct reproduction disproved the P1 finding)
- Risk: low
- Description: ARA-059 recorded pytest 9 returning zero after 16 `SUBFAILED` reports, raising a P1
  concern across 102 `subTest` call sites in 14 files. Live direct reproduction now returns status 1;
  the historical zero belonged to an outer orchestration script that printed nested command output
  without propagating the nested exit code.
- Related files: subprocess contract sentinel, validation/recovery records, CI tests
- Acceptance criteria: an isolated subtest-only assertion failure deterministically makes the same
  local and CI pytest command nonzero while normal passing subtests retain existing reporting;
  existing tests need no bulk semantic rewrite.
- Validation command: isolated subprocess sentinel, representative subtest suites, then
  `make check` and Python 3.10/3.13 GitHub Actions.
- Commit required: yes.
- Dependencies: repository-required test-configuration safety approval received from the owner on
  2026-07-23. Prefer a no-dependency hook; any new dependency still requires separate evidence and
  must not be added merely to simplify implementation.
- Completion: isolated direct pytest probes return status 1 for one and 16 subtest-only
  failures, while passing subtests return 0. Added a no-plugin-autoload, timeout-bounded subprocess
  sentinel without changing configuration or dependencies; focused tests pass `2 passed`, and the
  existing 14-file subtest cohort passes `321 passed, 618 subtests`. Indexed `make check` passes
  `397 passed, 618 subtests` with 62 formatted files and zero safety findings. Implementation
  `0a0036f` is pushed with exact local/upstream/`ls-remote`/PR-head equality; push/PR runs
  `30002348583`/`30002350589` passed Python 3.10/3.13, all four isolated-wheel steps, and zero
  annotations.

## ARA-061 - Reject invalid numeric CLI overrides instead of silently coercing them

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: cloud pacing, retry, prompt-budget, prompt-limit, and provider-quota CLI overrides
  accept non-finite, negative, out-of-range, or mutually inconsistent values. Several are silently
  clamped, while `min_delay_seconds > max_delay_seconds` and an infinite maximum delay can reach
  runtime configuration despite the equivalent file configuration rejecting them.
- Related files: `src/cli.py`, CLI/parser and cloud scheduler tests, user-facing CLI documentation
- Acceptance criteria: all seven numeric overrides reject invalid input with argparse/startup
  status 2 before project writes or provider work; effective max delay is never below effective
  min delay; valid boundaries and the intentional zero-disable quota threshold remain compatible.
- Validation command: focused parser/override tests, provider-free CLI no-write probes, related
  cloud/config/runner tests, then `make check`.
- Commit required: yes.
- Dependencies: owner explicitly approved ARA-061 on 2026-07-24 after reviewing the 45–60 minute
  task estimate and reproduced defect.
- Pre-fix reproduction: `--min-delay-seconds 100 --max-delay-seconds 1`, `nan`/`inf` delays,
  negative retries/quota thresholds, and subminimum prompt budgets/limits were accepted.
- Scope boundary: no provider calls, ignored runtime access, config-file schema changes,
  dependency changes, scheduler policy redesign, new default values, or ARA-055 package 5 work.
- Completion: strict parsers and the effective delay check now fail invalid input with status 2
  before project/provider work. Focused tests pass `4 passed, 18 subtests`; related tests pass
  `244 passed, 554 subtests`; full `make check` passes `466 passed, 809 subtests`. Implementation
  `b1c1b6c` is remote-equal and push/PR runs `30081927773`/`30081930092` passed Python 3.10/3.13.

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

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: the output browser and analytics helpers independently trust checkpoint `run_config`/`run_summary` and summary `round_metrics_path`, so rendering a crafted checkpoint can read external JSON even though Resume itself is now blocked.
- Related files: `ui/app.py`, `src/resume_safety.py`, `tests/test_ui_helpers.py`
- Acceptance criteria: UI artifact consumers derive or validate all run-local paths against the selected canonical run root before reads; safe legacy in-run metadata remains readable and unsafe references produce partial/unavailable UI state without exposing paths.
- Validation command: focused UI metadata/dashboard/catalog tests followed by `make check`.
- Commit required: yes.
- Dependencies: `ARA-012`.

## ARA-022 - Define project-level symlink boundaries for runtime artifacts

- Status: `DONE`
- Priority: P2
- Risk: high
- Description: project-level inputs/outputs such as `runs/`, `best_output.md`, `memory.md`, logs, and provider events can still follow filesystem symlinks in normal or resume workflows; closing an active rename/symlink race requires a broader storage policy than checkpoint validation.
- Related files: `src/storage.py`, `src/runner.py`, `src/project_input.py`, runtime artifact tests
- Acceptance criteria: define the trusted-local-filesystem threat model and either reject unsafe project artifact links consistently or use descriptor-based no-follow writes without breaking canonical local workflows.
- Validation command: adversarial filesystem tests plus `make check`.
- Commit required: yes if behavior changes.
- Dependencies: owner approved the high-risk, greater-than-30-minute implementation on 2026-07-11;
  preserve the existing configured resolved `runs/` storage-link contract unless reproducible
  evidence requires a separately documented migration.
- Completion: implementation `544b26a` and Python-3.10 test portability fix `93026ca` are pushed and
  remote-equal; final local `make check` passed with 294 tests and 176 subtests. Replacement push/PR
  runs `29153023802`/`29153024964` passed Python 3.10/3.13.

## ARA-023 - Define interrupt-to-process-status propagation

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: CLI-level `KeyboardInterrupt` handlers print a manual-interrupt stop reason and then
  return status 0, while interrupts already consumed by the runner are represented only in run
  artifacts. Changing either behavior requires a single explicit process-status contract.
- Related files: `src/cli.py`, `src/runner.py`, CLI subprocess tests
- Acceptance criteria: direct CLI interrupts use a documented nonzero status (normally 130), runner
  safe-stop artifacts remain complete, and successful user-requested checkpoint stops are not
  accidentally reclassified.
- Validation command: fault-injected interrupt and safe-stop subprocess tests followed by `make check`.
- Commit required: yes if behavior changes.
- Dependencies: complete ARA-017 without widening its startup-error scope.

## ARA-013 - Make run-lock acquisition and release ownership-safe

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: the lock file is not acquired atomically and release lacks an owner token, so an old process can delete a newer owner's lock; malformed PID types can also raise unexpectedly.
- Related files: `src/runtime.py`, runtime/UI helper tests
- Acceptance criteria: atomic exclusive acquisition, robust malformed metadata handling, and owner-checked release prevent lock theft or deletion.
- Validation command: concurrency/ownership-focused runtime tests followed by `make check`.
- Commit required: yes.
- Dependencies: none after `ARA-008`.

## ARA-014 - Source benchmark stop reason from the target run

- Status: `DONE`
- Priority: P2
- Risk: medium
- Description: benchmark reporting can read the project's latest checkpoint instead of the target historical run, mislabeling stop reason.
- Related files: `src/benchmark_report.py`, `tests/test_benchmark_report.py`
- Acceptance criteria: historical reports use target-run summary/config/manifest data and only use project checkpoint when it belongs to that run.
- Validation command: historical-run mismatch regression followed by `make check`.
- Commit required: yes.
- Dependencies: higher-priority correctness work.

## ARA-015 - Enforce Gemini request timeouts at the HTTP client layer

- Status: `DONE`
- Priority: P1
- Risk: medium
- Description: configured timeout values are recorded but not passed to the Gemini transport, so one request may exceed the runner's bounded runtime expectations.
- Related files: `src/llm.py`, provider configuration, `tests/test_llm.py`
- Acceptance criteria: the configured timeout reaches the supported Gemini HTTP transport without changing model/prompt semantics; timeout errors retain safe classification.
- Validation command: mocked client-construction/request tests followed by `make check`.
- Commit required: yes.
- Dependencies: verify current Google SDK API before implementation.

## ARA-016 - Remove tracked personal paths and add a repository safety gate

- Status: `DONE`
- Priority: P1
- Risk: low
- Description: tracked reports contain a real local username in example scan text; sanitize it and prevent new tracked personal paths or obvious secrets.
- Related files: `REAL_PROVIDER_SMOKE.md`, `TEST_AND_NEXT_STEPS.md`, a small repo-safety script, `Makefile`, CI
- Acceptance criteria: tracked files contain no personal absolute paths or real secrets; local/CI `make check` runs a deterministic safety scan with focused tests or self-test fixtures.
- Validation command: tracked-file path/secret scan plus `make check`.
- Commit required: yes.
- Dependencies: avoid changing historical findings beyond redaction.

## ARA-017 - Return nonzero status for CLI startup and validation errors

- Status: `DONE`
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

## ARA-026 - Normalize public sdist ownership and generated timestamps

- Status: `DEFERRED`
- Priority: P2 for public artifact publication
- Risk: medium
- Description: two isolated `SOURCE_DATE_EPOCH=0` builds produced byte-identical wheels but
  different sdists because setuptools stamped generated directories/metadata with build time; tar
  headers also recorded the local builder account/group.
- Related files: `pyproject.toml`, future release/build workflow, source-distribution validation
- Acceptance criteria: two clean builds produce identical wheels and sdists; tar ownership is
  normalized and contains no local account; normalization occurs in the supported build path rather
  than a post-hoc archive rewrite that could invalidate metadata or signatures.
- Validation command: two isolated no-network builds, archive metadata/content comparison, isolated
  wheel/sdist install smoke, and repository/artifact safety scans.
- Commit required: yes.
- Dependencies: coordinate with ARA-018 and ARA-019 release policy; ARA-004 does not publish its
  temporary sdist.

## ARA-005 - Align stale future-priority documentation with implemented features

- Status: `DONE`
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
