# Known Issues

Updated: 2026-07-24 (Asia/Hong_Kong)

## KI-001 - Stale invalid `.git/REBASE_HEAD`

- Status: observed; non-blocking
- Severity: P3
- Evidence: the file exists and references an unavailable object, while `rebase-merge`, `rebase-apply`, and sequencer state are absent and `git status --porcelain=v2 --branch` is clean.
- Impact: diagnostic scripts that test only for `.git/REBASE_HEAD` can falsely report an active rebase.
- Current action: leave untouched; use actual rebase directories and porcelain status to determine operation state.

## KI-002 - Compare-runs arity contract may be inconsistent

- Status: fixed, validated, committed, and pushed
- Severity: P1
- Evidence source: tracked `TEST_AND_NEXT_STEPS.md` reports that one run was accepted while CLI help and docs require two or more.
- Impact: users cannot tell whether a one-run self-baseline is supported or accidental.
- Current action: task `ARA-002` completed at remote commit `033ed01`.

## KI-003 - Non-positive max-round override may be silently coerced

- Status: fixed, validated, committed, and pushed
- Severity: P1
- Evidence source: tracked `TEST_AND_NEXT_STEPS.md` reports that `--max-rounds 0` produced a one-round mock run.
- Impact: surprising automation behavior and a possible unintended provider call when zero rounds were expected.
- Current action: task `ARA-003` completed at remote checkpoint `5c5bdc0`.

## KI-004 - Source tag and package metadata use different versions

- Status: confirmed by tracked metadata; policy decision deferred
- Severity: P2 for packaged distribution, P3 for cloned-checkout use
- Evidence: `pyproject.toml` declares `0.1.0`; tracked release documentation identifies `v0.1.1-hardening`.
- Impact: wheel metadata and source release naming may diverge.
- Current action: task `ARA-006`; do not change version without a distribution policy.

## KI-005 - Non-editable package assets are not yet verified

- Status: fixed, pushed, and CI-verified
- Severity: P2
- Evidence: the project declares only the `src` package while runtime workflows also reference repository assets and UI/scripts.
- Impact: wheel-installed behavior may differ from editable or cloned-checkout behavior.
- Current action: task `ARA-004` completed at implementation commit `0aee55e`; exact six-resource
  wheel/sdist inventories, isolated installs, and source/editable compatibility passed. UI/scripts
  remain intentionally outside the packaged CLI scope.

## KI-006 - Legacy ignored logs can predate path masking

- Status: known local-data risk; no tracked-code regression
- Severity: P3
- Evidence source: tracked release review; current ignored runtime data is intentionally not opened, rewritten, or committed during startup.
- Impact: manually shared old artifacts may disclose local paths.
- Current action: never publish ignored artifacts without a scoped privacy scan.

## KI-007 - Configured credentials can be echoed into provider events

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P0
- Impact: an arbitrary configured API key echoed by a provider response can survive pattern-only redaction and be serialized locally.
- Current action: task `ARA-008` completed at remote checkpoint `c8d6c17`.

## KI-008 - Interrupted JSON writes can destroy the last checkpoint

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P1
- Impact: an in-place write failure truncates the old valid checkpoint, after which tolerant reads can silently return empty state.
- Current action: task `ARA-009` completed at remote checkpoint `5ab7119`.

## KI-009 - Resume can discard historical metrics

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P1
- Impact: appending a resumed round can rewrite metrics and summaries with only the new round, corrupting longitudinal interpretation.
- Current action: task `ARA-010` completed at remote checkpoint `b8b629b`.

## KI-010 - Failed rounds can replace prior best output

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P1
- Impact: synthetic failure output can beat the internal sentinel score and overwrite trusted prior content.
- Current action: task `ARA-011` completed at remote checkpoint `7e9a1f5`.

## KI-011 - Resume roots are not constrained to the project runs directory

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P1
- Impact: a crafted or stale checkpoint can direct resumed artifact writes outside the selected project's run tree.
- Current action: task `ARA-012` completed at remote checkpoint `31db3f8`.

## KI-012 - Run locks are not atomic or owner-safe

- Status: fixed, pushed, and CI-verified
- Severity: P1
- Impact: concurrent acquisition can race, an old owner can remove a newer lock, and malformed PID metadata can raise.
- Current action: task `ARA-013` completed at implementation commit `55e7287` and remotely verified
  checkpoint `e93aa77`.

## KI-013 - Wheel-installed mock workflow cannot find repository assets

- Status: fixed, pushed, and CI-verified
- Severity: P1 for packaged distribution
- Impact: console help works, but mock startup cannot locate `config.example.yaml`; a source checkout works.
- Current action: task `ARA-004` completed at implementation `0aee55e`; wheel and sdist console/
  module mock smokes passed from isolated source-excluded workspaces without package writes or
  foreign Git provenance. Public publication remains blocked separately by ARA-018 and ARA-026.

## KI-014 - Tracked reports contain a personal absolute-path fragment

- Status: fixed, pushed, and CI-verified
- Severity: P1 privacy/release hygiene
- Impact: the repository embeds a real local username in historical scan examples and evidence text.
- Current action: task `ARA-016` completed at implementation commit `2b6523c` and remotely verified
  recovery checkpoint `975559d` with all Python 3.10/3.13 push and pull-request jobs passing.

## KI-015 - Some CLI startup failures exit successfully

- Status: fixed, pushed, and CI-verified
- Severity: P1 automation/release reliability
- Impact: missing config/resources can print an error while returning status 0, allowing a smoke check to pass falsely.
- Current action: task `ARA-017` completed at implementation commit `8845adf` and remotely verified
  checkpoint `a513e4d`. Wheel asset completeness was completed separately by ARA-004 at `0aee55e`.

## KI-016 - Public distribution license is absent

- Status: confirmed; owner decision required
- Severity: P1 release blocker, not a runtime defect
- Impact: public package publication has no declared license or complete project metadata.
- Current action: task `ARA-018`; do not choose a license autonomously.

## KI-017 - Gemini transport timeout is not wired to the SDK client

- Status: fixed, pushed, and CI-verified
- Severity: P1 bounded-runtime reliability
- Impact: one SDK request can exceed configured per-agent and global runtime expectations.
- Current action: task `ARA-015` completed at implementation commit `817b8a1` and remotely verified
  checkpoint `be37216`; no real provider call was required.

## KI-018 - Historical benchmark report can use another run's stop reason

- Status: fixed, pushed, and CI-verified
- Severity: P2
- Impact: a historical target run can be mislabeled from the project's latest checkpoint.
- Current action: task `ARA-014` completed at implementation commit `588e32c` and remotely verified
  recovery checkpoint `c893e63`; all Python 3.10/3.13 push and pull-request jobs passed.

## KI-019 - Resume can rewrite original run-manifest provenance

- Status: fixed, pushed, and CI-verified
- Severity: P2
- Impact: rebuilding `run_manifest.json` during resume can replace original start/mode provenance and discard unknown legacy fields, even though `run_config.json` retains resume sessions; a safe in-runs path alias can also disagree with checkpoint `run_id`.
- Current action: task `ARA-020` completed at implementation `3b98c61` and remotely verified
  checkpoint `c1e8c57` with Python 3.10/3.13 push and PR jobs passing.

## KI-020 - UI artifact viewers can follow external checkpoint references

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P1 privacy
- Impact: metadata, analytics, and output-catalog helpers can read checkpoint-supplied run config/summary paths or a summary-supplied metrics path outside the selected run.
- Current action: task `ARA-021` completed at remote checkpoint `3624385`.

## KI-021 - Static resume checks do not close active filesystem swap races

- Status: fixed within the documented ARA-022 boundary; validated, committed, pushed, and
  CI-verified
- Severity: P2 under the project's local single-user threat model
- Impact: registered POSIX automatic I/O and traversal now reject static links/hard links/special
  nodes plus ancestor/nested symlink replacements; fresh CLI/UI/background/resume/survey/stop entry
  points establish that boundary before automatic access.
- Current action: task `ARA-022` completed at implementation `544b26a` plus portability fix
  `93026ca`; push/PR runs `29153023802`/`29153024964` passed Python 3.10/3.13. Preserve the explicit
  residual boundary: trusted ancestors above the anchor, malicious same-UID replacement with a
  different real directory, post-open/new-temp hard-link races, and Windows active replacement are
  not claimed as protected.

## KI-022 - Manual interrupts can still produce process status 0

- Status: fixed, pushed, and CI-verified
- Severity: P2 automation semantics
- Impact: direct interrupts caught by the CLI and runner-consumed safe interrupts do not yet share a
  documented process-status contract, so changing only one path could make automation inconsistent.
- Current action: task `ARA-023` completed at implementation `4cae84e` and remotely verified
  checkpoint `37b3749`; cooperative `STOP_REQUESTED` remains status 0.

## KI-023 - A maintenance smoke advanced ignored example-project state

- Status: awaiting owner disposition; no cleanup attempted
- Severity: local-state integrity incident, no tracked-code/provider impact
- Impact: deterministic run `20260711_031915_776385` created one ignored run and replaced five
  ignored project-level state files plus appended `run.log` under `projects/example`.
- Current action: preserve all touched files as-is until the owner chooses to keep the transparent
  mock checkpoint or authorizes a backed-up best-effort rollback. Repository history cannot restore
  the prior ignored state byte-for-byte.

## KI-024 - Zero-round resume omits a run-config resume session entry

- Status: fixed, pushed, and CI-verified
- Severity: P3 provenance completeness
- Impact: resuming a checkpoint with `last_completed_round=0` records resume lifecycle metadata and
  current-session time but does not append `resume_sessions` because the next round is still 1.
- Current action: task `ARA-024` completed at implementation `b961070` and remotely verified
  checkpoint `a3bef4d`; all Python 3.10/3.13 push and PR jobs passed.

## KI-025 - Committed recovery snapshots permanently lag their containing closeout

- Status: fixed again with a persistent cross-file regression; verify current Git/CI state live
- Severity: P2 recovery accuracy
- Impact: each state-only closeout embeds its parent SHA and pending/dirty authoring state, so a
  later recovery can mistake an already pushed and CI-verified closeout for unfinished work.
- Current action: ARA-022's state-only closeout regressed the ARA-025 contract by retaining stale
  worktree and closeout instructions. Task `ARA-028` removed those claims, synchronized the current
  exact fallback, and added a test that checks current/task/resume/validation state together. Legacy
  exact SHA fields remain compatible; semantic `HEAD` and live Git/CI verification stay authoritative.

## KI-026 - Source-distribution metadata is not identity-neutral or reproducible

- Status: confirmed during ARA-004 artifact validation; publication deferred
- Severity: P2 release integrity/privacy
- Impact: repeated `SOURCE_DATE_EPOCH=0` builds produced different sdists because generated
  directories/metadata retained build timestamps, and tar headers recorded the local builder
  owner/group. Publishing that archive would expose local identity and prevent byte-for-byte
  reproduction.
- Current action: task `ARA-026`; do not upload the temporary ARA-004 sdist. Normalize ownership and
  generated timestamps through the supported build/release path, then verify two isolated builds.

## KI-027 - A packaging audit left one untracked pip-cache wheel entry

- Status: observed local environment residue; no cleanup authorized
- Severity: P3 local hygiene
- Impact: one cache directory under the user's pip cache contains a pre-fix wheel and origin
  metadata. It is outside the repository, is not a canonical artifact, and could confuse a future
  manual audit if mistaken for the final build.
- Current action: leave untouched unless the owner authorizes cache cleanup; future validation must
  build into fresh temporary directories and use the recorded final artifact hashes.

## KI-031 - Resume overwrites an invalid existing run config

- Status: fixed, pushed, and CI-verified
- Severity: P1 resume provenance integrity
- Impact: malformed, unreadable, non-object, or excessively nested existing `run_config.json`
  content was normalized to `{}` and replaced with current-session provenance during resume.
- Current action: task ARA-031 completed at `78b76dc`; exact push/PR runs
  `29161456466`/`29161457321` passed Python 3.10/3.13. Strict existing-config validation fails
  before writes while preserving the missing-config legacy fallback.

## KI-032 - Non-finite artifact scores contaminate analysis and comparison

- Status: fixed, pushed, and CI-verified
- Severity: P1 data/report correctness
- Impact: malformed or legacy `NaN`/`Infinity` scores can win ranking, create a false flat trend,
  and escape as non-standard JSON. Finite extremes can also overflow derived averages/deltas, while
  a numeric missing-score sentinel can outrank valid negative scores.
- Current action: task ARA-032 completed at `21fea11`; exact push/PR runs
  `29162165065`/`29162166082` passed Python 3.10/3.13. Finite conversion, score-presence ranking,
  overflow-safe derived fields, and strict-JSON/compatibility regressions are complete.

## KI-033 - Provider-free export failures leak traceback and local paths

- Status: fixed, pushed, and CI-verified
- Severity: P2 privacy/CLI reliability
- Impact: an unavailable analysis/comparison output parent or unresolved home shortcut returns the
  correct status 1 but exposes a Python traceback with temporary and repository absolute paths.
- Current action: task ARA-033 completed at `f44687e`; exact push/PR runs
  `29162704235`/`29162705572` passed Python 3.10/3.13. Explicit output resolution/write failures use
  fixed path-free diagnostics and status 1.

## KI-034 - Non-boolean resume eligibility is treated as true

- Status: fixed, pushed, and CI-verified
- Severity: P1 recovery integrity
- Impact: values such as `"false"`, `"true"`, or `1` can start agents and overwrite an explicitly
  ineligible checkpoint; huge/non-finite preview scores can crash or propagate invalid state.
- Current action: ARA-034 completed at `bdbd9d5`; exact push/PR runs
  `29163467415`/`29163468552` passed Python 3.10/3.13. Literal-true eligibility, finite preview
  conversion, and direct/CLI fail-before-write coverage are complete.

## KI-035 - Legacy non-score metrics can overflow or emit non-standard JSON

- Status: fixed, pushed, and CI-verified
- Severity: P1 report/data correctness
- Impact: malformed or extreme timings, evolution metrics, rubric values, and counters can emit
  `NaN`/`Infinity` under status 0 or raise provider-free `OverflowError` tracebacks.
- Current action: ARA-035 completed at `a99723c`; exact push/PR runs
  `29164052624`/`29164053862` passed Python 3.10/3.13. Finite coercion, overflow-safe aggregates,
  raw rubric normalization, malformed agent leaves, and strict analysis/comparison output are fixed.

## KI-036 - Unrepresentable Judge numbers raise during parsing

- Status: fixed, pushed, and CI-verified
- Severity: P1 run reliability
- Impact: structured Judge score/rubric integers outside float range raise `OverflowError` instead of
  following invalid-output handling.
- Current action: ARA-036 completed at `3d13b2f`; exact push/PR runs
  `29164348550`/`29164349968` passed Python 3.10/3.13. Float/JSON numeric limits, invalid-score
  handling, valid rubric siblings, and compatibility controls are fixed.

## KI-037 - Survey interrupt bypasses the status-130 contract

- Status: fixed, pushed, and CI-verified
- Severity: P2 automation/privacy
- Impact: survey `KeyboardInterrupt` releases the lock but exits as signal status `-2` with traceback
  and source paths instead of the documented 130 diagnostic.
- Current action: ARA-037 completed at `cd21143`; exact push/PR runs
  `29164609427`/`29164610776` passed Python 3.10/3.13. Status 130, fixed diagnostic, real-module
  behavior, and lock release are verified.

## KI-038 - Cloud-free lazy iteration and artifact writes escape error boundaries

- Status: fixed, pushed, and CI-verified
- Severity: P2 CLI/privacy
- Impact: lazy SDK iteration and discovery/profile artifact writes can leak tracebacks/paths, and
  lazy failure prevents the documented profile seed fallback.
- Current action: ARA-038 completed at `25ae39b`; exact push/PR runs
  `29165142777`/`29165143905` passed Python 3.10/3.13. Lazy discovery and all four artifact-write
  stages retain their documented status and privacy contracts.

## KI-039 - Unreadable prior-round context is silently discarded on resume

- Status: fixed, pushed, and CI-verified
- Severity: P2 reproducibility
- Impact: invalid UTF-8 in existing prior-round Judge context becomes an empty prompt context after
  startup metadata has already changed.
- Current action: ARA-039 completed at `9191a35`; exact push/PR runs
  `29165593346`/`29165594723` passed Python 3.10/3.13. Fail-before-write ordering, legacy missing
  compatibility, and path-safe failure handling are verified.

## KI-040 - Cloud fallback profile can retain stale discovery provenance

- Status: fixed, pushed, and CI-verified
- Severity: P2 selection consistency
- Impact: a new fallback profile can coexist with stale discovery data and cause a later process to
  reselect a model deliberately excluded in the current process.
- Current action: ARA-040 completed at `ba4b2c1`; exact push/PR runs
  `29166208230`/`29166209758` passed Python 3.10/3.13. CLI/UI membership reconciliation, current
  policy reclassification, and no-schema compatibility are verified.

## KI-041 - Resume startup metadata can split across generations

- Status: fixed, pushed, and CI-verified
- Severity: P2 recovery consistency
- Impact: a manifest write failure after config replacement leaves only `run_config.json` claiming
  a new running resume session although no agent ran and other state remains old.
- Resolution: the fixed config/manifest journal protocol restores pre-commit failures and surviving
  partial states before logging or agent work. Write-point, crash-state, interrupted-rollback,
  legacy, invalid-journal, unsafe-leaf, local full-gate, and Python 3.10/3.13 remote CI coverage is
  green through `877562e`.

## KI-042 - UI cloud-free session cache is not project or artifact scoped

- Status: fixed, pushed, and CI-verified
- Severity: P2 selection consistency
- Impact: switching projects or refreshing cloud artifacts outside Streamlit can leave global
  in-memory discovery/profile values active; equal model IDs can hide stale metadata from ARA-040's
  membership guard.
- Resolution: cache identity combines canonical project path/device/inode with safe SHA-256 content
  states for both artifacts. Cache misses recheck the joint identity, retry once, and fail empty if
  unstable; legacy, unreadable, unsafe, project-switch, and same-ID refresh cases cannot reuse stale
  values.

## KI-043 - All blocked profiles can still produce a fallback recommendation

- Status: fixed, pushed, and CI-verified
- Severity: P2 provider reliability
- Impact: after quota/unreachable/billing-safety/token-context profiles exclude every candidate, the
  fallback branch can select one of the same blocked safe seeds and trigger a predictably failing
  provider attempt.
- Current action: ARA-043 applies one blocking predicate to quality fast-path, normal scoring, and
  runtime fallback. All-blocked returns no recommendation/fallback; mixed unprofiled and healthy
  candidates retain existing behavior. UI distinguishes Manual from no eligible automatic result.

## KI-029 - CI token permissions and runtime are implicit

- Status: fixed, pushed, and CI-verified
- Severity: P2 CI security/reliability
- Impact: CI inherits repository-default `GITHUB_TOKEN` permissions and the platform runtime ceiling;
  old action runtimes also emit forced Node compatibility annotations on every matrix job.
- Resolution: the workflow grants only `contents: read`, forbids an untested job-level permission
  override, caps each matrix job at 15 minutes, and uses the official Node 24 action majors
  `checkout@v7` and `setup-python@v6`. Push/PR filters and Python 3.10/3.13 remain unchanged.

## KI-044 - UI health result can describe a previously selected target

- Status: fixed, pushed, and CI-verified
- Severity: P2 diagnostic correctness
- Impact: a successful or failed health check remains visible after changing the effective model or
  Ollama endpoint, so the UI can attribute stale evidence to a target that was never checked.
- Resolution: health snapshots are wrapped with normalized provider/model plus non-secret Ollama
  endpoint or actual Gemini credential-source identity. Legacy, malformed, missing-format,
  mismatched, and credential-bearing error states are removed or sanitized before display.

## KI-045 - Gemini redaction can select a different built-in key than the SDK

- Status: fixed, pushed, and CI-verified through `47c0c26`
- Severity: P1 credential disclosure
- Impact: with both `GOOGLE_API_KEY` and `GEMINI_API_KEY` set, the SDK uses the Google key while the
  wrapper records the Gemini key as the known secret. An echoed Google key can therefore survive in
  provider events and exception chaining.
- Resolution: one operation-scoped snapshot follows explicit/custom then SDK Google/Gemini
  precedence, preserves built-in delegation, and redacts every captured candidate from events,
  public/cause/context messages, client initialization, and cloud-discovery diagnostics before
  truncation. Provider-free key-source, short/overlap-value, and exception-graph regressions pass.

## KI-030 - Editable-only CI can miss wheel packaging regressions

- Status: fixed, pushed, and CI-verified
- Severity: P2 packaging reliability
- Impact: CI installs only the editable checkout, while the installed-layout unit fixture copies
  `src`; build-backend, entry-point, package-data, or RECORD regressions can bypass the gate.
- Resolution: ARA-030 adds one temporary, source-excluded real-wheel install smoke to both matrix
  jobs. Local hostile-environment wheel smoke, targeted safety/package tests, full gate, and three
  reviews are green; implementation `4cda430` plus push/PR runs
  `29232341316`/`29232344581` verify all four Python 3.10/3.13 wheel steps with zero annotations.

## KI-046 - Ollama endpoint credentials can escape through failures

- Status: fixed, pushed, and CI-verified through `3f3826b`
- Severity: P1
- Evidence: provider-free fake request and API fallback failures retained configured URL userinfo
  and query values in the public request error, chained cause, and model-list diagnostic.
- Impact: credentials embedded in a supported Ollama endpoint can be written to run logs/provider
  events or displayed by CLI diagnostics after an ordinary connection failure.
- Resolution: diagnostics now retain only an unambiguous safe endpoint label, use fixed request/API
  failure classifications, detach raw exception graphs, and discard failed command output. Actual
  request targets and accepted URL forms are unchanged; ambiguous labels fail generic.

## KI-050 - Installed mock can omit generation prompts from provenance

- Status: fixed, pushed, and CI-verified through `be3bc04`
- Severity: P2 packaging and provenance reliability
- Impact: deterministic installed mock agents do not read prompt files, so a missing or corrupt
  prompt could still produce a successful run with incomplete prompt provenance.
- Resolution: ARA-050 validates all four generation prompts before any generation-side write,
  preserves prompt-independent CLI paths and regular hardlink installation compatibility, and
  passed focused, related, isolated-wheel, full-gate, independent review, exact remote-equality,
  and Python 3.10/3.13 push/PR CI validation.

## KI-051 - Conflicting duplicate cloud profiles are ordering-sensitive

- Status: fixed, pushed, and CI-verified through `ab7d6fe`
- Severity: P2 selection consistency
- Impact: last-record-wins dictionaries can let a healthy duplicate override a blocked profile and
  re-enable that model for recommendation or fallback depending only on artifact order.
- Resolution: ARA-051 marks non-identical exact-ID duplicates conflicted and excludes only those IDs
  from cached pooling, recommendation, and fallback while retaining equivalent duplicates and
  other safe candidates. Both orders, all presets, full local gates, exact remote equality, and
  Python 3.10/3.13 push/PR CI are verified.

## KI-052 - Non-object Ollama health JSON raises instead of reporting unhealthy

- Status: fixed, pushed, and CI-verified through `2141b7d`
- Severity: P2 UI reliability
- Impact: a reachable `/api/tags` endpoint returning valid list, scalar, boolean, or null JSON can
  raise `AttributeError`, interrupting the Streamlit health action instead of returning a stable
  diagnostic.
- Resolution: ARA-052 requires a top-level mapping and otherwise returns one fixed credential-safe
  `InvalidResponse` result. Mapping compatibility, exact request targets/timeouts, endpoint
  redaction, scoped snapshots, local full gates, exact remote equality, and Python 3.10/3.13
  push/PR CI are verified.

## KI-058 - Malformed nested Ollama models values still raise

- Status: fixed, pushed, and CI-verified through `0511a47`
- Severity: P2 UI reliability
- Pre-fix evidence: provider-free responses shaped as `{"models": null}` and `{"models": 42}` both
  raised `TypeError` during iteration after ARA-052 correctly accepted the outer mapping.
- Impact: before the local fix, a reachable endpoint with a malformed nested field could interrupt
  the UI health action or be rescued into false healthy state by installed-model fallback.
- Resolution: ARA-058 requires an actual list before model iteration or installed-model fallback and
  otherwise returns the existing fixed credential-safe `InvalidResponse`. Omitted and list-valued
  `models`, valid records, exact requests, redaction, and ARA-052 behavior remain compatible; focused,
  related, full local, exact-remote, Python 3.10/3.13 push/PR, wheel, and annotation checks passed.
  No broader artifact or provider schema migration is implied.

## KI-057 - Orphan mode-specific outputs fall into unrelated work

- Status: fixed, pushed, and CI-verified through `eabedff`
- Severity: P1 CLI safety
- Impact: `--survey-output`, `--compare-output`, or `--analyze-output` without its matching selector
  is silently ignored and can enter normal/provider or another primary workflow, including artifact
  writes, instead of reporting invalid arguments.
- Resolution: ARA-057 enforces owner relationships at the post-parse boundary with fixed path-free
  status-2 diagnostics. Full order/mode/empty-value coverage, direct/module/copied-installed no-work
  controls, local gates, exact remote equality, and Python 3.10/3.13 push/PR CI are verified.

## KI-053 - Equal-length private Ollama paths share health evidence

- Status: fixed, pushed, and CI-verified through `98dffb5`
- Severity: P2 UI reliability and privacy
- Impact: non-allowlisted paths were stored only as segment lengths, so distinct equal-shape targets
  could share one provider/model identity and display stale health evidence from another endpoint.
- Resolution: normalized private paths now receive full process-local keyed opaque identifiers while
  credential values, query values, fragments, raw/reversible paths, and key material remain absent
  from session state. Collision/cache/privacy/compatibility tests, local gates, exact remote equality,
  and Python 3.10/3.13 push/PR CI are verified.

## KI-059 - Non-string Ollama model names can become false healthy matches

- Status: fixed, pushed, and CI-verified through `a7d00a6`
- Severity: P2 UI and discovery reliability
- Evidence: provider-free list responses with null, boolean, numeric, list, or object `name` values
  are converted with `str(...)`; selecting the resulting text returns `health_model_ok` for all five
  shapes. The shared tags parser performs the same coercion.
- Impact: malformed provider data can be displayed and cached as a real installed model rather than
  being ignored or rejected.
- Resolution: a shared scalar normalizer accepts only string values before either inventory
  de-duplication or UI health matching. Literal strings that resemble coerced values remain valid;
  mixed records, metadata, request/redaction, list-container, and installed-fallback behavior remain
  compatible. Exact parent-level mutation probes, focused/related/full validation, and
  three independent reviews are green. Exact remote equality plus push/PR Python 3.10/3.13 CI,
  every isolated-wheel step, and zero annotations are verified.
- Boundary: ARA-058 validates only the `models` container. Older process-local UI cache strings are
  indistinguishable from genuine names and are naturally replaced on refresh or process restart;
  text blacklists are explicitly rejected.

## KI-060 - Historical subtest zero-exit finding used the wrapper status

- Status: resolved by ARA-060 implementation `0a0036f`
- Severity: P2 test assurance and historical evidence accuracy
- Evidence: the first ARA-059 pre-fix matrix reported 16 `SUBFAILED` cases and its outer orchestration
  call returned 0. Archived command evidence shows that wrapper printed each nested command's
  `output` but never checked or propagated `exit_code`; direct pytest 9.0.3 probes with one and 16
  subtest-only failures both return 1.
- Impact: the incorrect P1 record could motivate unnecessary pytest configuration or dependency
  changes and made historical validation evidence ambiguous. Future pytest version drift still
  merits an explicit contract sentinel because 102 real call sites span 14 test files.
- Resolution: add an isolated subprocess sentinel proving subtest-only failure returns 1 and passing
  subtests return 0. Disable third-party plugin autoload, remove inherited pytest injection options,
  and bound the child process without changing the canonical pytest configuration or dependencies.
  Focused, representative-cohort, recovery, full local validation, and Python 3.10/3.13 push/PR CI
  pass; all four CI annotation sets are empty.
- Boundary: ARA-059 adds parent-level aggregate assertions only to its two new tests. A repository-wide
  correction must preserve Python 3.10/3.13, avoid masking ordinary failures, and follow the safety
  approval rule before changing test configuration or dependencies. Configuration approval is now
  satisfied, but evidence shows no configuration change is needed; adding a dependency remains
  disallowed without separate evidence.

## KI-056 - Pre-agent interrupts can leave an incoherent running round

- Status: resolved by ARA-056 implementation `795665d`
- Severity: P2 recovery reliability
- Evidence: runner inspection previously identified round-directory creation, round logging, and
  memory loading before the protected agent-phase `try`; a `KeyboardInterrupt` at those boundaries
  can bypass the standard interrupted checkpoint/summary/report finalization.
- Impact: a manual interrupt can leave `status=running`, an empty or partial round directory, and
  no coherent resume evidence even though the CLI correctly returns status 130.
- Acceptance boundary: either roll back unpublished pre-agent state or finalize the standard
  interrupt artifacts without changing schemas, successful behavior, cooperative stop semantics,
  ARA-023 status 130, or ARA-041 startup transaction ordering.
- Resolution: round creation, round-entry logging, console setup, memory loading/truncation, and the
  pre-agent cooperative-stop check now share a manual-interrupt boundary. The standard finalization
  writes coherent resumable artifacts and re-raises for CLI status 130. ARA-054 subsequently moved
  the empty pending state into an immutable stopped attempt that resume preserves before retry.
  Focused, related, full local, exact-remote, Python 3.10/3.13 push/PR, wheel, and annotation checks
  pass.

## KI-054 - Resumable mid-round stops leave an ineligible partial round

- Status: resolved by ARA-054 runtime implementation `75f3d9a`; legacy migration remains deferred
- Severity: P2 recovery consistency, high-risk compatibility surface
- Pre-fix evidence: the runner persisted partial next-round outputs after agent stages and could finalize an
  interrupt or quota stop with `can_resume=true`, while resume validation rejects a nonempty pending
  round as uncheckpointed. The exact per-stage state matrix is being re-characterized in isolated
  provider-free workspaces.
- Pre-fix impact: the persisted checkpoint could claim resumability even though immediate preview refused the
  same run, requiring unsafe manual intervention to continue.
- Resolution: new rounds use append-only staged attempts, stopped evidence is immutable, and retry
  starts from draft. Preview, runner preflight, and checkpoint eligibility share one bounded
  classifier. A complete attempt publishes with no-replace semantics or a recoverable create-only
  handoff into a preserved empty canonical directory.
- Design result: use append-only attempt staging and retry the whole round from draft. Existing
  canonical partial rounds remain fail-closed because placeholders, `last_successful_agent`, and
  file presence do not reliably identify a resumable agent boundary. ARA-055 separately owns the
  multi-artifact round-commit transaction.

## KI-055 - Published rounds can split history and finalization generations

- Status: new iterative, run-finalization, and diagnostic generations are fixed and remote-verified
  through package 6; package 7A read-only legacy classification is remote-verified, while migration
  execution remains deferred
- Severity: P2 recovery and provenance consistency, high-risk compatibility surface
- Evidence: 40 provider-free temporary cases covered ten post-publication write boundaries,
  `OSError`/`KeyboardInterrupt`, and internal/configured-external run storage. Failure before the
  run-local history write leaves canonical round 2 and a verified `published` attempt, project
  history `[1,2]`, run history `[1]`, and checkpoint round 1.
- Impact: packages 3-6 recover valid current journals and prevent transaction-sensitive readers
  from consuming pending/conflicting generations. Historical journal-less split, partial, or
  uncorrelated artifacts remain preserved and can still require owner-led forensic handling.
- Design result: `docs/ARA_055_CROSS_FILESYSTEM_ROUND_COMMIT_DESIGN.md` selects an immutable
  project-local journal with bounded deltas/after-images, exact before/after hashes, idempotent
  roll-forward across filesystems, checkpoint-last visibility, and a separate finalization
  transaction.
- Package-5 activation: the owner approved the fixed finalization journal on 2026-07-24. Scope is
  exact summary/config/final-checkpoint roll-forward plus approved entry/read-only routing only;
  diagnostic integration and legacy migration remain excluded.
- Package-5 local checkpoint: a fixed create-only journal now records strict bounded after-images
  and recovery applies summary/config before checkpoint. Focused validation passes `7 passed, 16
  subtests`; final `make check` passes `473 passed, 825 subtests`. This evidence was subsequently
  staged, committed, pushed, and remotely verified as recorded below.
- Package-5 result: implementation `5c9f0ce` transactionally applies run summary, finalized config,
  and checkpoint in that order; iterative entry recovery and reader guards cover pending/conflicting
  generations. Full `make check` passes `473 passed, 825 subtests`; push/PR CI
  `30085545590`/`30085548995` is green on Python 3.10/3.13.
- Package-6 activation: diagnostic still writes project score history before run-local metrics and
  metadata. The owner approved one fixed diagnostic-finalize transaction plus lock-held recovery
  and read-only guards on 2026-07-24; legacy migration remains excluded.
- Package-6 local result: the five diagnostic artifacts now use a strict checkpoint-last
  roll-forward transaction; every internal/external write and cleanup `OSError`/`KeyboardInterrupt`
  boundary converges in focused tests, and pending/conflicting readers fail closed. Related
  validation passes `252 passed, 616 subtests`; full `make check` passes `481 passed, 849 subtests`.
  Implementation `24d56ba` is remote-equal and push/PR CI `30088147987`/`30088150085` is green.
  Legacy journal-less split artifacts remain unchanged; package 7 migration requires separate
  approval.
- Package-7 design activation: the owner approved tracked-only design work on 2026-07-24. Runtime
  artifacts remain deliberately uninspected; the design must not infer missing before-generations
  or authorize mutation. Implementation/execution requires a later explicit approval.
- Package-7 design result: general repair is rejected. Only a safely absent twin history with one
  strict complete checkpoint-correlated source is a future exact-byte-copy candidate; all
  ambiguous, partial, journal-less published/canonical/finalization/diagnostic, unsafe, and unknown
  states are non-migratable. Read-only discovery, exact-copy execution, and destructive rollback
  remain three separate approval gates.
- Package-7A activation: the owner approved only the read-only targeted classifier/report layer on
  2026-07-24. Execution, evidence/journal writes, rollback, batch scanning, provider work, and
  ignored-runtime access remain excluded.
- Package-7A local result: fixed L00-L20 classification plus strict redacted machine/human reports
  are implemented without a caller capable of mutation. Synthetic internal/configured-external
  coverage passes `17 passed, 114 subtests`; related transaction/recovery regression passes `224
  passed, 642 subtests`; final `make check` passes `498 passed, 963 subtests` plus all static,
  import, safety, and isolated-wheel gates.
- Package-7A completion: `f9b29f8` is exact remote-equal; push/PR runs
  `30098547791`/`30098553022` passed Python 3.10/3.13 and every workflow step with zero
  annotations.
- Package-7B result: the explicit single-project preview is implemented without a writer,
  provider/config dependency, lock acquisition, recursive discovery, or execution authority.
  Focused tests pass `27 passed, 115 subtests`; related reader/transaction/UI regression passes
  `218 passed, 468 subtests`; full `make check` passes `503 passed, 970 subtests` plus every static,
  import, and safety gate, and the isolated wheel smoke passes. Implementation `3a2b62f` is exact
  remote-equal; push/PR runs `30105129908`/`30105131795` passed Python 3.10/3.13 with zero
  annotations. Package 7C execution is unapproved.
- Package-1 result: commit `4cd4bf4` adds filesystem-free exact after-image builders and a strict
  bounded journal codec with provider-free regression coverage. No runtime caller creates, reads,
  or applies the journal yet, so this issue remains open.
- Package-2 result: the fixed create-only journal, strict classification, ARA-054 publication
  reconciliation, and checkpoint-last recovery engine pass `75 passed, 162 subtests` across
  internal/configured-external before/after faults. Implementation `faf1791e` is remote-equal and
  push/PR CI is green.
- Package-3 result: implementation `54c223b` routes new and fully evidenced runner histories through
  prepare/recover with checkpoint last. Internal/configured-external `OSError`/`KeyboardInterrupt`
  retry coverage proves exact one-round histories; full `make check` passes `453 passed, 791
  subtests`, and push/PR CI `30030145901`/`30030150062` is green.
- Package-4 result: implementation `efcad88` recovers a valid pending round under the existing lock
  before provider/client/agent work and adds non-mutating preview/UI/analytics/comparison/report
  guards. Full `make check` passes `462 passed, 791 subtests`; push/PR CI
  `30034539432`/`30034542276` is green.
- Boundary: incomplete legacy histories retain their prior compatibility path because no exact
  before-generation exists. Diagnostic integration and migration remain unapproved.
  Historical journal-less `published_uncommitted` evidence and manually edited third generations
  remain preserved and fail closed.

## KI-061 - Numeric CLI overrides accept invalid or inconsistent values

- Status: fixed by ARA-061 at remote-equal implementation `b1c1b6c`
- Severity: P2 reliability, pacing, and user-intent integrity
- Evidence: the current parser accepts non-finite delay values, negative retry/quota thresholds,
  subminimum prompt budgets/limits, and `--min-delay-seconds 100 --max-delay-seconds 1`.
- Impact: several invalid inputs are silently changed after parsing, so recorded/user-requested
  intent differs from runtime behavior. Infinite or mutually inconsistent delay bounds can enter
  the scheduler configuration and violate the file-config invariant.
- Required fix: strict finite/range parsing plus an effective min/max relation check before project
  writes or provider work, with valid zero/boundary compatibility retained.
- Boundary: configuration-file schemas and defaults, scheduler policy, providers, experiments,
  dependencies, ignored runtime, and ARA-055 package 5 are not part of ARA-061.
- Resolution: strict numeric argument types reject non-finite/out-of-range values, and startup
  rejects an invalid effective delay relation after configuration merge. Provider-free entrypoint
  tests prove status 2 and no project creation; valid boundaries and zero quota threshold remain.
