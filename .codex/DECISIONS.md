# Maintenance Decisions

## 2026-07-10 - Use a dedicated maintenance branch

- Decision: work on `codex/sol-autonomous-hardening`, created from synchronized `master` commit `a94c4e2`.
- Reason: isolate incremental hardening work from the protected/default branch and make checkpoints easy to review or abandon.

## 2026-07-10 - Track recovery metadata in `.codex/`

- Decision: add the seven requested recovery files as repository documentation.
- Reason: `.codex/` is not ignored, no equivalent maintenance-state system exists, and these files do not affect runtime behavior.
- Boundary: never record secrets, environment values, private artifact content, or machine-specific absolute paths.

## 2026-07-10 - Preserve ignored local and experimental state

- Decision: treat ignored `config.yaml`, project runs, logs, reports, checkpoints, and research artifacts as user-owned local state.
- Reason: they may contain live configuration, experiments, or historical evidence and are outside the tracked maintenance diff.

## 2026-07-10 - Leave stale Git administrative metadata untouched

- Decision: do not delete `.git/REBASE_HEAD`.
- Reason: it is stale and invalid, but there are no active rebase/sequencer directories and normal Git status is clean. Removing it is unnecessary for maintenance and would be a deletion outside the tracked project.

## 2026-07-10 - Keep the first cycle provider-free

- Decision: use the repository's local checks and deterministic tests before any real-model workflow.
- Reason: the first objective is code/release reliability; provider calls are unnecessary to validate the initial maintenance-state and CLI contract work.

## 2026-07-10 - Prefer compatibility-preserving fixes

- Decision: when public behavior and documentation disagree, first inspect callers and tests, then prefer the smallest behavior-preserving clarification unless correctness or safety requires stricter validation.
- Reason: the project explicitly preserves historical compatibility and research artifacts.

## 2026-07-10 - Keep Git transport workarounds command-scoped

- Decision: after the normal HTTPS push hung, retry with proxy settings passed only to that single `git push` and remote-verification command.
- Reason: this restored reliable GitHub transport without changing repository or global Git configuration.

## 2026-07-10 - Redact configured credentials before persistence and exception chaining

- Decision: replace the exact resolved Gemini credential before generic token-pattern redaction and use only the sanitized message in provider events and visible exception causes.
- Reason: key-shape patterns cannot cover arbitrary or future credential formats, and Python traceback chaining otherwise re-exposes a safely wrapped provider error.
- Boundary: preserve request, retry, quota classification, public exception type, and provider semantics.

## 2026-07-10 - Atomically replace state files without changing schemas

- Decision: write replacement content to a same-directory temporary file, flush and fsync it, then use `os.replace`; clean the temp path on every pre-replace exception.
- Reason: a direct overwrite can truncate the last valid checkpoint before new content is durable, making tolerant reads silently lose the resume point.
- Boundary: append-only logs retain their existing best-effort behavior; JSON formatting, text normalization, and artifact schemas stay unchanged.

## 2026-07-10 - Canonicalize checkpoint roots against configured run storage

- Decision: resume accepts an existing absolute per-run directory only when its resolved parent is the selected project's resolved `runs/` directory; relative, nested, cross-project, container-root, traversal, and non-directory candidates fail closed.
- Reason: repository-generated checkpoints have always used absolute direct-child run roots, while trusting arbitrary checkpoint paths permits external reads and writes.
- Compatibility: a user-configured `project/runs` storage symlink remains supported because normal run creation already follows it; the checkpoint may choose only a canonical direct child of that resolved storage root.
- Boundary: static root/child checks protect resume-consumed config, legacy manifest, summary, metrics/history, previous context, and planned round paths. UI raw artifact references and active filesystem-swap resistance remain separate tasks `ARA-021` and `ARA-022`.

## 2026-07-10 - Derive UI artifacts from the selected canonical run

- Decision: when checkpoint `run_root` is present, latest-run metadata, analytics, and output
  browsing use only fixed config/summary/metrics/manifest and round-output names derived from its
  validated canonical root. Redundant checkpoint and summary path values cannot redirect reads.
- Reason: those fixed names are the repository-generated schema, while trusting stored absolute
  pointers allowed crafted or stale checkpoints to read arbitrary local JSON and text.
- Compatibility: a read-only canonical run and a configured resolved `runs/` storage symlink remain
  browseable. The project-level score-history fallback remains only for the no-`run_root` legacy
  layout.
- Boundary: project-level logs/outputs, discovered-run comparison paths, active filesystem swaps,
  and the broader local artifact symlink policy remain `ARA-022`.

## 2026-07-11 - Use a long-held owner-capability run lock

- Decision: use a persistent project-root `active_run.guard` OS advisory lock as the authority for
  the full run lifecycle. Keep `active_run.json` as atomically replaced diagnostic metadata with a
  random owner token, PID, and guard device/inode identity.
- Reason: check/write and stale-file deletion protocols allow simultaneous winners and can delete a
  replacement owner. A kernel-held guard is released on crash without a racy stale unlink.
- Compatibility: existing live PID-only locks remain blocking; dead or malformed legacy metadata
  is recovered after the guard is acquired. The returned handle remains path-like for display, but
  only the intact capability may release; a bare `Path` fails closed.
- Platform: POSIX uses `flock`; Windows uses nonblocking byte-range locking and a non-destructive
  `OpenProcess` liveness probe. Static non-regular guard/metadata paths fail closed.
- Boundary: general CLI startup error exit codes remain `ARA-017`; active non-cooperating path swaps
  outside the token/PID/guard-identity defense remain `ARA-022`.

## 2026-07-11 - Classify handled CLI startup refusals separately from operation failures

- Decision: handled argument/config/project/provider/run-lock/resume startup refusals terminate with
  status 2; an explicit operation such as failed cloud model discovery terminates with status 1;
  help, completed commands, and documented cloud-profile fallback remain status 0.
- Reason: returning `None` made both `python -m src.main` and the console script report false
  success. The split preserves existing argparse/resume status 2 and ordinary runtime status 1.
- Input boundary: config/task reads produce privacy-safe validation errors; fail-soft checkpoint and
  optional cloud-cache readers reject malformed encoding, parser depth/size, structure, and unsafe
  numeric fields before downstream use. Unknown cache fields remain forward-compatible and missing
  fields keep dataclass defaults.
- Compatibility: valid provider-free analysis, valid cached artifacts, and successful profile seed
  fallback remain unchanged. The fix does not make wheel resources self-contained.
- Boundary: direct and runner-consumed interrupt status is deferred to ARA-023; package asset/root
  behavior remains ARA-004; prompts, provider requests, scoring, and experiment artifacts are unchanged.

## 2026-07-11 - Apply Gemini timeout at the Client HTTP boundary

- Decision: pass the validated `timeout_seconds` to every Gemini `genai.Client` credential path as
  Client-level `http_options.timeout` after converting seconds to milliseconds.
- Reason: the configuration and logs already promised a bounded request timeout, but generation
  config did not enforce one at the transport layer; the installed public SDK contract confirms
  Client-level HTTP options are the supported boundary.
- Error policy: classify concrete timeout types, explicit `timed out` messages, and HTTP 408/504 as
  `timeout`; do not treat arbitrary option text or timeout-like class-name substrings as transport
  failures.
- Compatibility: preserve model, prompts, generation configuration, credential selection, and the
  existing retry decision. Real provider calls and dependency constraints remain outside this fix.

## 2026-07-11 - Scan tracked worktree and index without following filesystem links

- Decision: validate both the tracked worktree and every stage-0 index blob with byte-oriented,
  high-confidence path/key rules; enumerate only `git ls-files` entries and never echo matched text.
- Reason: four tracked report fragments contained a real local account name, while an index-only or
  UTF-8/text-only check could miss unstaged, binary, NUL, or partially staged content.
- Filesystem boundary: worktree reads walk parent directories through descriptor-relative
  `O_NOFOLLOW`, inspect the final node without following it, and scan a tracked symlink's link text.
  If the platform lacks those primitives, the worktree scan fails closed; `--staged` remains usable.
- Compatibility: ignored runtime artifacts, provider behavior, prompts, metrics, experiment values,
  and historical conclusions remain unchanged. Reports describe the account as redacted rather than
  pretending a placeholder was the original evidence.

## 2026-07-11 - Walk automatic artifact paths from a registered trust anchor

- Decision: reject linked project/task inputs, linked or hard-linked fixed artifact leaves,
  blocking special files, and linked automatic output directories. On POSIX, register each project
  process-wide against its real `projects/` directory, rebase nested run boundaries to that anchor,
  and give only external run storage its own resolved physical root; walk every component from the
  selected anchor with descriptor-relative no-follow opens before leaf reads/appends/replacements/
  unlinks, child-directory creation, or automatic source traversal.
- Reason: path-based existence checks followed by reads, appends, or replacement followed static
  links and allowed a parent rename/link swap to redirect automatic I/O outside the project.
- Compatibility: preserve a configured `project/runs` storage link by resolving it once to a real
  storage directory; preserve stale real-directory tolerance and explicit analyze/compare/export
  paths. Fixed automatic hard links are rejected because writes would mutate every name for the
  inode. Survey source helpers now return lexical `abspath` spelling rather than canonicalizing
  through mutable project components; persisted content, ordering, and displayed repo-relative paths
  remain unchanged.
- Threat boundary: ancestors above a registered anchor remain trusted local infrastructure. Static
  links and hard links are rejected, but a malicious same-UID actor replacing a real-directory entry
  with another real directory, racing a hard link onto an already-open inode, or targeting a new
  temporary inode is outside the guarantee. Windows receives component-level static rejection but
  cannot claim equivalent active-swap resistance with the standard path-based fallback; unsupported
  POSIX automatic boundaries fail closed.

## 2026-07-11 - Bind benchmark stop reason to fixed target-run metadata

- Decision: resolve report stop reason from the selected run's fixed `run_summary.json`,
  `run_config.json`, then legacy `run_manifest.json`; use the mutable project checkpoint only when
  its normalized root and any supplied run ID positively match the target.
- Reason: project checkpoint represents the latest run and can silently relabel a historical report.
  Run-local final metadata is the authoritative target-specific evidence.
- Safety boundary: read only regular non-symlink metadata leaves with descriptor identity checks,
  and render only official `STOP_*` constant values. Unknown, private, injected, malformed, or
  unrelated values become `unknown` rather than being copied into Markdown.
- Compatibility: all current stop constants, absolute/repository/project/runs-relative checkpoint
  paths, ID-only legacy checkpoints, and legacy manifest fallback remain covered. Active parent/path
  replacement remains the separately tracked ARA-022 threat boundary.

## 2026-07-11 - Distinguish manual interrupts from cooperative checkpoint stops

- Decision: every manual `KeyboardInterrupt` reaching a supported CLI boundary exits with status
  130. When the runner catches an interrupt during its protected agent-execution phase, it first
  finalizes checkpoint, summary/config, and interrupted-report artifacts, then re-propagates it.
- Reason: returning success for `Ctrl+C` makes automation unable to distinguish an interrupted run,
  while propagating before finalization would discard the existing safe-resume guarantee.
- Cooperative boundary: `STOP_REQUESTED` remains a successful status 0 stop with
  `USER_STOP_REQUESTED`; shared `can_resume` and interrupted-report fields do not determine status.
- Lock boundary: survey, mock, and provider acquisition/error evaluation are inside their lifecycle
  `try/finally` blocks. A second interrupt during finalization or an interrupt outside the runner's
  protected agent phase does not promise complete run artifacts.
- Compatibility: statuses 0/1/2, artifact schemas, provider/prompt/scoring behavior, and historical
  experiment interpretation remain unchanged.

## 2026-07-11 - Preserve raw manifest provenance and canonicalize resume identity

- Decision: the resolved run-directory basename is the single resume identity. A nonempty
  checkpoint or existing-manifest `run_id` must match it; missing IDs are derived canonically.
- Manifest policy: parse and snapshot an existing raw manifest before the first resume write,
  preserve creation-time and unknown fields, canonicalize only ID/root/config pointers, and merge
  existing then current resume metadata. Unpreservable manifests fail closed without replacement.
- Sparse policy: an existing sparse manifest remains sparse. A missing manifest may use fields
  already persisted in run config; only a genuinely new run uses current creation-session defaults.
- Reason: rebuilding from normalized/current inputs erased historical provenance, while filling
  absent legacy fields from a resume session fabricated provenance that never existed.
- Compatibility: configured `runs/` storage links and leaf aliases remain usable with canonical ID;
  current session mode/model/time stay in run config, and consumer fallback remains unchanged.

## 2026-07-11 - Resolve committed recovery HEAD semantically

- Decision: make `current_head.ref: HEAD` plus the fixed argv
  `git rev-parse --verify HEAD` authoritative for the commit containing a tracked recovery snapshot.
  Keep the schema-v1 `head_commit` and `last_known_stable_commit` fields as deprecated exact SHA
  fallbacks, and add explicit field semantics plus the most recent external verification evidence.
- Reason: a commit cannot embed its own final SHA because changing the tracked file changes that SHA.
  State-only closeout commits therefore permanently claimed their parent HEAD, pending work, and a
  dirty worktree even after they were pushed and CI-verified.
- Recovery boundary: committed metadata does not claim future live worktree, upstream, or CI state.
  Recovery must resolve Git state live and fall back to the last exact externally verified commit
  when current remote evidence is absent.
- Compatibility: no runtime code consumes these files; additive schema-v1 fields preserve unknown
  external readers that still require the legacy 40-hex values.

## 2026-07-11 - Separate installed resources, writable workspace, and Git provenance

- Decision: source/editable layouts continue using the repository root for resources and workspace;
  non-editable installs use an exact six-file `src._bundled` read-only resource allowlist and the
  invocation CWD as their writable workspace. Git provenance has a separate explicit root and is
  disabled for installed layouts rather than inheriting an unrelated CWD repository.
- Mock seed policy: only an installed, implicit default `example` mock may copy the bundled sample
  task into an absent workspace project. Explicit, partial, custom, and non-mock selections are
  never seeded or overwritten. Installed prompts always come from the bundled canonical copies;
  local config/task precedence remains unchanged.
- Publication policy: stage a complete hidden sibling, flush/fsync its file, then publish with an
  operating-system no-replace primitive (`renamex_np` on Darwin, `renameat2` on Linux, `os.rename`
  on Windows). Missing/unknown primitives fail closed; interrupts clean only owned staging paths.
- Reason: wheel/sdist mock startup lacked repository-only resources, while using `site-packages` as
  a writable root or trusting CWD prompts/Git state would create mutation and provenance hazards.
- Compatibility boundary: UI/scripts distribution, dependencies, version, license, provider,
  prompts' canonical bytes, scoring, schemas, experiment results, historical artifacts, and KI-023
  ignored state are unchanged.
- Release boundary: the validated temporary sdist is not publishable because its tar metadata
  contains local owner/group identity and nondeterministic generated timestamps. ARA-026 owns that
  follow-up; ARA-018 still requires the owner's license decision.

## 2026-07-12 - Treat recovery metadata as a cross-file tested contract

- Decision: keep committed worktree state live-resolved, allow at most one `IN_PROGRESS` task, and
  require `CURRENT_STATE.md`, `TASK_QUEUE.md`, `RESUME_INSTRUCTIONS.md`, and
  `LAST_VALIDATION.json` to agree on the active task and conservative external fallback.
- Recursive-closeout rule: a remaining-work bullet that asks for commit, push, checkpoint, or
  closeout work must name exactly the current `IN_PROGRESS` task. Once no task is active, committed
  recovery state cannot retain task-owned finalization instructions.
- Reason: the ARA-022 closeout repeated the stale authored-state pattern that ARA-025 had corrected;
  one-time assertions did not prevent a later manual closeout from reintroducing it.
- Compatibility: semantic `HEAD`, schema-v1 exact fallback fields, historical evidence, ignored
  runtime state, provider behavior, artifacts, experiments, and release policy remain unchanged.

## 2026-07-12 - Preserve invalid existing run config instead of rebuilding it

- Decision: keep the general run-config reader tolerant, but let the resume runner request strict
  handling for an existing `run_config.json`. Missing and existing are distinguished by an identity
  sentinel; malformed, unreadable, non-object, `null`, and excessively nested existing content
  raises the existing `ResumeHistoryError` boundary before automatic writes.
- Reason: mapping invalid existing content to `{}` made resume treat corruption as absence and
  replace provenance with current-session values, creating silent data loss.
- Compatibility: a genuinely missing config still falls back to `run_manifest.json`; ordinary UI,
  analytics, comparison, and other tolerant readers retain their existing behavior. An empty JSON
  object remains an object under this task; field-level schema migration is out of scope.
- Failure boundary: errors contain only the fixed artifact name and category. Config, manifest,
  checkpoint, stop signal, histories, and run outputs remain byte-identical or absent, and no agent
  is invoked.

## 2026-07-12 - Treat only finite values as scores without changing ordinary averages

- Decision: reject boolean, non-finite, and unrepresentable values at analysis/comparison score
  conversion boundaries. Missing scores rank below every finite score, including negative values.
- Derived arithmetic: an unrepresentable delta becomes `null`; trend direction still comes from
  the finite endpoints. Preserve the existing `sum(scores) / count` operation whenever its total is
  finite, and use max-absolute scaling with `math.fsum` only when that total overflows.
- Reason: input-only finite checks still allowed finite extremes to create `Infinity`, while always
  using a numerically different mean changed ordinary paper/report-facing rounded values by 0.01.
- Compatibility: finite legacy numeric strings, ordinary rounded averages, run ordering among
  scored records, prompts, providers, experiment artifacts, and historical reports are unchanged.
  Arbitrary non-score metadata sanitation remains outside ARA-032.

## 2026-07-12 - Normalize explicit provider-free export failures as operation errors

- Decision: analysis/comparison output argument expansion, parent resolution, and JSON writes map
  `OSError`/path-resolution `RuntimeError` to a fixed privacy-safe diagnostic and exit status 1.
- Reason: these commands have already entered their requested provider-free operation, so the
  documented operation-failure status applies; exposing raw exceptions leaked local paths without
  adding actionable recovery information.
- Boundary: do not catch analysis/comparison computation or terminal-rendering failures, and do not
  suppress errors in the storage layer. Successful exports and explicitly authorized output-parent
  symlinks retain their existing behavior.

## 2026-07-12 - Require an identity-true resume eligibility flag

- Decision: treat a checkpoint as resume-eligible only when `can_resume is True`; do not coerce
  strings, integers, arrays, objects, or other values by truthiness. Convert preview `best_score`
  only when it is non-boolean, representable as a float, and finite; otherwise use the established
  `-1.0` default.
- Reason: tolerant truthiness turned malformed values such as `"false"` into authorization to run
  agents and replace checkpoint state, while unbounded float conversion could crash or propagate
  Infinity/NaN before the recovery decision.
- Failure boundary: invalid eligibility returns the existing `not_resume_eligible` preview and CLI
  status 2 before the iterative runner or any agent stage. Project artifacts remain byte-identical,
  and the acquired CLI run lock is released by its existing lifecycle boundary.
- Compatibility: literal JSON `true`, finite numeric values and strings, checkpoint schema, run
  execution, providers, prompts, score semantics, experiment artifacts, and historical conclusions
  remain unchanged. Client/agent container construction order is a separate existing CLI behavior;
  no provider call or agent stage occurs for an ineligible checkpoint.

## 2026-07-12 - Keep legacy metric aggregation finite without changing ordinary arithmetic

- Decision: coerce required additive legacy floats to the established zero default when malformed,
  non-finite, or unrepresentable; optional floats become unavailable. An elapsed sum that cannot be
  represented becomes `None` at each cross-agent, cross-round, and per-agent accumulation level.
- Derived arithmetic: preserve the existing `sum(values) / count` and rounding path whenever the
  total is finite. Only an overflowed evolution/rubric total uses max-absolute scaling with
  `math.fsum`; an unrepresentable delta becomes `None`.
- Legacy boundary: normalize raw summary rubric averages through the same finite conversion and
  treat non-Mapping agent metric leaves as empty records. Preserve timing numeric strings, token
  float truncation and arbitrary-precision integers, finite rubric numeric strings/unknown keys,
  and the existing rule that evolution numeric strings are ignored. Do not add positivity or
  similarity-range clamps under this task.
- Reason: tolerant conversions and ordinary float addition allowed malformed artifacts to crash
  provider-free commands or emit NaN/Infinity under status 0, while changing the ordinary arithmetic
  path would silently alter historical report values.
- Scope: analysis/comparison API, JSON writer, and CLI paths are covered without changing global JSON
  serialization, providers, prompts, scoring, generated artifacts, experiments, or research claims.

## 2026-07-12 - Treat unrepresentable Judge numbers as invalid output

- Decision: contain numeric conversion `TypeError`/`ValueError`/`OverflowError` at the shared Judge
  score/rubric coercion boundary. Treat a plain JSON-decoder `ValueError`, including Python 3.11+
  integer digit-limit failures, the same as malformed structured JSON at both parse entrypoints.
- Reason: a provider-returned large numeric literal could escape the parser after round artifacts
  were saved, producing a traceback instead of the existing invalid-score stop and compatibility
  fallbacks.
- Compatibility: boolean/non-finite values remain invalid, finite numeric strings remain accepted,
  out-of-range finite values remain clamped to 0..100, invalid structured scores may still fall back
  to a legacy `SCORE:` line, and invalid rubric fields are omitted independently. The raw payload API
  remains raw for successfully parsed JSON.
- Scope: no schema, prompt, provider, score threshold, runner control, artifact interpretation,
  experiment result, or historical conclusion changes.

## 2026-07-12 - Normalize survey interrupts inside the lock lifecycle

- Decision: catch `KeyboardInterrupt` in the Literature Survey Mode `try/finally`, print a fixed
  `MANUAL_INTERRUPT` diagnostic, and raise the shared interrupted status 130. Leave lock release in
  the existing `finally` so real and mocked ownership paths retain one cleanup mechanism.
- Reason: uncaught survey interrupts returned signal status `-2` with a traceback and source paths,
  unlike mock/provider runner paths and the documented automation contract.
- Compatibility: normal survey completion remains status 0, survey artifact `OSError` remains the
  existing path-safe status 1, and no survey inputs, outputs, discovery logic, locks, configuration,
  provider behavior, or artifacts change.

## 2026-07-12 - Contain cloud discovery consumption and automatic artifact writes

- Decision: keep initial client construction and model-list invocation compatibility unchanged, but
  consume the returned iterator and convert its model records inside a classified public-error
  boundary. Fall back to a legacy `.models` collection only when obtaining the outer iterator fails;
  never reinterpret an iteration-time `TypeError` as legacy success.
- Artifact boundary: map `OSError` from each automatic discovery/profile save stage to the shared
  operation-failure status 1 and a fixed diagnostic without path or exception chaining. Do not catch
  provider/profile computation errors as artifact failures.
- Compatibility: explicit discovery errors remain status 1; profile discovery errors still use
  configured candidate seeds and can finish with status 0. Discovery/profile schemas, selection,
  pricing policy, provider calls, model metadata, and existing artifacts remain unchanged.
- Scope: the possibility of retaining stale discovery beside a new fallback profile is a separate
  provenance-cohort problem queued as ARA-040, not silently changed under ARA-038.

## 2026-07-12 - Preload prior-round resume context before startup writes

- Decision: after canonical path and artifact checks, read the previous round's fixed draft, review,
  revised, and Judge files exactly once before building or writing new startup metadata. Reuse those
  in-memory values in the round loop.
- Missing compatibility: a missing leaf or entirely missing legacy previous-round directory remains
  an empty context. Existing content that cannot be opened or decoded as UTF-8 raises a basename-only
  `ResumeHistoryError` with exception chaining suppressed.
- Reason: the tolerant storage helper erased the distinction between missing and unreadable data and
  was called only after run config/log/manifest writes, so corrupted research context could silently
  change the next prompt while new metadata claimed a resumed session.
- Scope: no context schema, prompt composition, provider, scoring, history reconciliation, round
  output, valid-context whitespace behavior, or historical artifact interpretation changes.

## 2026-07-12 - Reconcile cached cloud artifacts by candidate membership

- Decision: for automatic CLI/UI recommendation, reclassify cached discovery under current policy
  and trust its metadata only when a non-empty profile has exactly the same unique, canonical safe
  model IDs. On mismatch, ignore discovery and intersect current configured candidates with safe
  profile IDs.
- Compatibility: an absent or empty profile retains the existing discovery-only behavior; a complete
  exact cohort retains discovery metadata and recommendation scoring. Explicit discovery and profile
  commands continue using their same-process in-memory candidate pool.
- Reason: a discovery-error profile save did not replace an older discovery file, so a later process
  could score a deliberately unprofiled stale model as an attractive safe/high-TPM candidate.
- Boundary: this is membership reconciliation, not proof that equal-ID artifacts share a generation.
  No schema, timestamp, artifact file, migration, deletion, provider, or preset changes are made;
  project/external-refresh UI session identity remains queued separately as ARA-042.

## 2026-07-12 - Treat an all-blocked cloud profile set as no recommendation

- Decision: define one blocking predicate for unsafe-text, unreachable, daily-quota, billing/safety,
  and token-context profiles. Apply it to Quality's preferred-model shortcut, ordinary scoring, and
  runtime fallback eligibility.
- Reason: every non-blocked safe candidate always enters the scored list, so an empty scored list
  means all candidates were explicitly blocked; selecting a seed in that branch contradicted the
  same profile evidence and could trigger a predictably failing provider attempt.
- Compatibility: missing-profile candidates remain eligible, healthy profiles keep their scoring,
  non-daily rate limiting retains its lower-score behavior, Manual remains manual, and mixed pools
  may still choose an eligible unprofiled candidate. UI preserves picker/manual selection when no
  automatic result exists and reports that state accurately.
- Scope: no provider retry, scheduler, artifact schema/file, configuration, preset, prompt, score,
  experiment result, or historical conclusion changes.

## 2026-07-12 - Bound CI authority and runtime

- Decision: set workflow-level `permissions` to only `contents: read` and cap each matrix job at 15
  minutes. The workflow only checks out and tests the repository, so no write permission is needed;
  the timeout leaves substantial headroom over the observed minute-scale jobs.
- Runtime maintenance: replace the deprecated Node 20 action majors with `actions/checkout@v7` and
  `actions/setup-python@v6`. Their official current releases (`v7.0.0` and `v6.3.0`) both declare
  `node24`; the hosted `ubuntu-latest` runner satisfies the documented minimum runner version.
- Compatibility: preserve push and pull-request branch filters, Python 3.10/3.13 matrix, pip cache,
  install command, and every validation step. Continue the repository's existing floating-major
  convention; immutable action pinning remains separately owned by ARA-019.
- Scope: no dependency, packaging, wheel-smoke, publication, release, provider, artifact, experiment,
  or application runtime policy changes are included.

## 2026-07-12 - Content-scope UI cloud session state

- Decision: bind discovery and profile session lists to one identity containing the validated
  canonical project path, project device/inode, and SHA-256 content state of both fixed artifacts.
  Use distinct missing, unreadable, and unsafe/error sentinels; never store artifact content in the
  identity.
- Consistency boundary: clear legacy/old state before a miss, load both lists, re-fingerprint the
  joint identity, retry once on change, and fail empty without caching if it changes again. Commit
  the two lists before the identity; UI-owned saves invalidate identity before updating one list.
- Reason: global list keys survive project changes, while ID-membership reconciliation cannot see
  external metadata changes when model IDs stay equal. Content state also prevents inode/size/mtime
  preservation from hiding an update.
- Compatibility: valid stable artifacts retain session reuse; malformed or missing artifacts still
  yield empty lists and recover when replaced. No artifact schema/file, provider call, configuration,
  model-selection rule, experiment result, ignored runtime, or historical interpretation changes.
- Residual boundary: a mutation after the final fingerprint can affect at most one render. Atomic
  cross-file discovery/profile generations require a transaction or provenance schema and remain
  outside this no-schema UI cache fix.

## 2026-07-12 - Bind UI health snapshots without retaining credentials

- Decision: wrap each cached health result with normalized provider/model plus a non-secret
  connection identity. Ollama stores normalized origin, an allowlisted safe-path label or redacted
  path shape, and only userinfo/query presence. Gemini stores only session/config/environment source
  labels, following actual custom-env then SDK Google/Gemini precedence.
- Validation boundary: accept only known health message keys with their required format arguments,
  string messages, boolean `ok`, and mapping arguments. Evict raw legacy, malformed, unknown,
  missing-argument, or mismatched entries before localization.
- Privacy boundary: never persist or hash credential values. Sanitize endpoint display and provider
  error details before session storage; arbitrary URL paths, userinfo, query values, and exception
  text are excluded. Same-source external credential rotation can remain indistinguishable under
  this constraint and requires a fresh health check.
- Compatibility: same-target success/failure snapshots remain visible. Widget changes, effective
  model/endpoint/source changes, and Ollama model refresh invalidate stale state. Provider calls,
  configuration files, artifacts, experiment behavior, and research conclusions are unchanged.
- Follow-up: ARA-045 separately owns the P1 provider-event/chained-cause leak caused by
  `GeminiClient._available_api_key()` disagreeing with SDK built-in environment precedence.

## 2026-07-12 - Snapshot Gemini credentials using the SDK's actual precedence

- Decision: resolve explicit configuration, custom environment, then the SDK-managed
  `GOOGLE_API_KEY` and `GEMINI_API_KEY` sources once per operation. Continue passing explicit and
  custom keys directly while delegating built-in sources to google-genai; capture every populated
  candidate for defense-in-depth redaction.
- Reason: google-genai gives Google precedence when both built-ins exist, while the wrapper formerly
  selected Gemini for redaction. The mismatch exposed the key actually used when an upstream error
  echoed it.
- Exception boundary: construct sanitized failures inside provider handlers, but raise them only
  after leaving the handler so Python cannot retain the raw provider exception through
  `__context__`. Apply the same exact-secret redaction before cloud-discovery diagnostics are
  truncated.
- Compatibility: preserve SDK built-in credential delegation, raw environment truthiness, timeout,
  request/event classification, retry behavior, and public error types. Validation is provider-free.

## 2026-07-12 - Recover resume startup metadata as one generation

- Decision: for an existing-run resume only, atomically prepare a fixed hidden journal containing
  the exact prior `run_config.json`/`run_manifest.json` text plus before/after SHA-256 values, replace
  both canonical files, and use journal unlink as the commit point before logging `run_start`.
- Recovery: ordinary exceptions, `KeyboardInterrupt`, interrupted rollback, and a surviving journal
  restore the exact prior generation idempotently. A missing journal after an unlink-side exception
  is recovered from the in-memory transaction. Unknown hashes, changed journals, malformed content,
  and unsafe leaves fail closed without overwriting external changes.
- Commit semantics: journal unlink marks the resume session started. A hard termination after unlink
  but before `run_start` logging can retain a complete zero-work session; the next resume preserves
  it as a started attempt rather than rolling back one canonical file. Detected external changes fail
  closed, but the cooperative project lock is not a hostile same-UID sandbox across hash/restore.
- Compatibility: preserve schema-v1 config behavior, schema-less/sparse legacy manifests, unknown
  manifest fields, missing legacy artifacts, run IDs, histories, checkpoints, and provider-free
  fail-before-agent behavior. New-run writes remain ordinary single-file atomic replacements.
- Boundary: this is a two-file startup recovery protocol, not a schema migration, cross-round
  transaction, or sudden-power-loss guarantee; parent directories are not fsynced.

## 2026-07-13 - Gate CI on one source-excluded wheel install

- Decision: add one standard-library helper to the existing Python 3.10/3.13 matrix after editable
  dependency installation. It copies only explicit tracked packaging inputs into an external
  temporary source snapshot, builds exactly one wheel, and installs it into a fresh venv.
- Contract: require the real import and console entry point to come from that venv; require the exact
  six bundled resources, canonical bytes, and RECORD hashes/sizes; run console/module help and one
  deterministic mock round; reject source/foreign-Git provenance and package-tree mutation.
- Isolation: ignore pip/user-site/Git redirect variables, disable pip cache reuse, isolate Git
  config/hooks/signing, reject checkout-local temporary roots, strip provider credentials from the
  runtime environment, blackhole upper/lower proxy variables, suppress raw child output, and share
  a 600-second helper deadline beneath the 15-minute job limit.
- Compatibility: preserve workflow triggers, read-only permissions, action versions, matrix,
  editable development install, application/provider behavior, prompts, scores, artifacts, and
  historical results. Do not build an sdist, upload an artifact, or change version, dependency,
  license, release, or publication policy.
- Boundary: the checkout and same-UID tracked-source reads remain trusted; the runtime proxy guard is
  not a syscall-level network sandbox. The deterministic mock path and artifact/provider assertions
  support provider-free behavior without claiming arbitrary code cannot open a socket.

## 2026-07-13 - Separate Ollama request targets from diagnostic endpoint labels

- Decision: keep configured endpoint acceptance and the exact `/api/chat`/`/api/tags` request target
  construction unchanged, but render only an unambiguous scheme/host/port diagnostic origin. Convert
  IDNs to ASCII; ambiguous authority delimiters, encoded/scoped hosts, and invalid ports use a fixed
  generic label rather than guessing.
- Error boundary: never persist provider-controlled requests/urllib exception text or failed
  `ollama list` stdout/stderr. Classify only safe timeout, HTTP status, invalid-JSON, command status,
  and generic request failures, and construct the public/safe cause after leaving raw exception
  handlers so Python cannot retain secret-bearing context.
- Reason: exact string replacement does not cover normalized or relative URLs, urllib `InvalidURL`,
  decode failures, backslash authorities, or command fallback output; fixed classification closes
  the whole diagnostic surface without altering provider calls.
- Compatibility: preserve outer `RuntimeError`, normal public wording for plain origins, event
  schema/error types, helper return shapes, actual request URL/timeout, config acceptance, and
  healthy parsing. The linked cause is intentionally a sanitized `RuntimeError` rather than the raw
  requests exception because exposing its type object also retained attacker/provider text.

## 2026-07-13 - Preflight only prompt-consuming generation modes

- Decision: validate the four fixed generation prompts after analysis/comparison early returns but
  before config, seeding, provider startup, locks, or artifact writes. Normal, mock, continuous,
  diagnostic, session, and resume are gated; survey and cloud discovery/profile remain independent.
- Resource boundary: require an anchored no-follow regular file, stable opened identity, valid
  UTF-8, and nonblank content. Package prompts explicitly allow regular hardlinks so cache- or
  hardlink-based installations remain valid; the storage reader keeps single-link enforcement for
  every existing automatic-artifact caller by default.
- Compatibility: do not change prompt bytes, package inventory, generation semantics, provider
  setup, installed workspace selection, or provider-free analysis/comparison behavior.
- Residual boundary: the validator and later prompt/provenance consumers do not share an immutable
  byte snapshot, so hostile same-UID replacement after preflight remains outside this minimal fix.
  Source-layout marker fallback when canonical prompts are missing also remains a separate concern.

## 2026-07-13 - Treat non-identical duplicate cloud profiles as conflicted

- Decision: build one internal exact-ID profile index and a set of IDs whose parsed
  `CloudModelProfile` values differ. Cached candidate reconciliation, automatic recommendation, and
  runtime fallback explicitly exclude those IDs in every record order.
- Compatibility: value-equivalent duplicate dataclass records remain accepted, including the
  existing ARA-040 configured-source fallback. Unique healthy profiles, safe unprofiled
  alternatives, ARA-040 cohort reconciliation, ARA-043 all-blocked behavior, raw artifact/session
  lists, and exact legacy model-ID matching remain unchanged.
- Reason: dropping a conflict only from the profile mapping would reinterpret it as an unprofiled
  candidate and re-enable it. Explicit exclusion removes only the conflicted ID while retaining
  other eligible candidates.
- Boundary: CLI/UI retain their existing configured or manually selected model when automatic
  recommendation returns none; changing that product behavior is outside the three ARA-051
  selection surfaces. UI recent-429 display still reads the first matching profile diagnostically.

## 2026-07-13 - Fail closed on non-mapping Ollama health JSON

- Decision: after successful `/api/tags` JSON decoding, require only that the top-level payload is
  a `Mapping`. Non-mapping values return the existing `health_api_unhealthy` contract with
  `api_ok=false`, `model_ok=false`, and fixed error token `InvalidResponse`.
- Security: render only `ollama_health_display_endpoint(base_url)` and never include payload values,
  raw endpoint paths, userinfo, query values, or response-derived type text in the result.
- Compatibility: valid mappings, including an empty object, keep their existing reachable-API and
  model-presence behavior; request URL, timeout, i18n keys, cache schema, and scoped identity are
  unchanged.
- Boundary: nested `models` schema validation is not inferred from the outer-shape fix. Confirmed
  null/numeric inner values are tracked as ARA-058 rather than broadening ARA-052.

## 2026-07-13 - Validate mode-specific output ownership after parsing

- Decision: retain the three output flags as ordinary optional arguments, then enforce their owner
  relationships immediately after parsing with `parser.error()`. Do not use order-sensitive custom
  actions or place valid mode/output pairs in an exclusion group.
- Contract: `--survey-output` requires truthy `--survey`, `--compare-output` requires truthy
  `--compare-runs`, and `--analyze-output` requires truthy `--analyze-run`. Output presence is
  tested with `is not None`, so an explicitly empty orphan remains invalid.
- Ordering: preserve the existing compare minimum-count check before output ownership, while
  argparse primary-mode conflicts remain earlier still. Hidden UI credential validation remains
  later. All failures precede logging and runtime setup.
- Compatibility: correct pairs in either argument order, empty values owned by a valid mode,
  output-free modes, `--help`, and output-free blank analyze parsing retain prior behavior. An empty
  analyze selector with an output is rejected because main's actual truthy dispatch would otherwise
  enter normal/provider work.
- Privacy: dependency errors interpolate only fixed option names and never the user-provided output
  value.

## 2026-07-13 - Pseudonymize private Ollama health paths within one process

- Decision: retain explicit identities for the existing allowlisted path segments, but represent
  every other normalized path with a full HMAC-SHA256 identifier keyed by 32 random process-local
  bytes. The random key lives only in a normally imported helper module so ordinary Streamlit
  reruns reuse it without placing it in session state, configuration, logs, or files.
- Privacy boundary: authenticate only `parsed.path.rstrip("/") or "/"`. Userinfo, passwords, query
  values, and fragments never enter the HMAC or key; existing userinfo/query presence markers and
  fragment omission remain unchanged. A persistent, hardcoded, or unkeyed digest is rejected
  because low-entropy private paths would remain enumerable or correlatable across processes.
- Compatibility: scheme, lowercased host, default-port normalization, safe path identities, and
  same-target cache reuse remain unchanged. A different private path now invalidates prior health
  evidence; process restart or helper reload rotates the key and safely invalidates old evidence.
- Assurance boundary: a fixed digest cannot be mathematically injective over arbitrary-length
  paths. The full 256-bit keyed identifier removes the deterministic length collisions with
  negligible cryptographic collision risk while satisfying the no-raw/no-reversible-state rule.

## 2026-07-13 - Require a list-valued nested Ollama models field

- Decision: after decoding `/api/tags`, bind `models` to the existing empty-list default only when
  the field is absent, then require an actual `list`. Null, boolean, numeric, string, and mapping
  containers return the same fixed ARA-052 `InvalidResponse` result before installed-model fallback.
- Security: never render the nested value, its type, or provider-controlled detail. Continue using
  only the ARA-046 redacted endpoint plus the fixed error token with `api_ok=false` and
  `model_ok=false`.
- Compatibility: preserve outer non-mapping behavior, omitted/empty/list-valued fields, mixed lists
  that ignore non-dict records, model-name trimming, installed-model union, exact request target,
  timeout, message keys, and target-scoped health storage.
- Boundary: record-field typing is not changed. Confirmed non-string `name` coercion is tracked as
  ARA-059 rather than broadening this container-only guard or the shared parser contract.

## 2026-07-14 - Require string-valued Ollama model names

- Decision: normalize one raw model-name value through a shared scalar helper that trims only
  `str` instances and returns empty for every other type. Both the shared inventory normalizer and
  UI health extraction use that helper before de-duplication or availability matching.
- Security: provider-controlled null, boolean, numeric, list, and object values are ignored rather
  than converted to Python display text that can enter caches, selectors, diagnostics, or command
  arguments. Invalid records do not poison valid siblings or reveal object content.
- Compatibility: nonblank string values remain valid even when their text is `None`, `True`, a
  number, list, or object representation. Existing trimming, case-sensitive first-valid de-duplication,
  sorting, metadata coercion, exact request/timeout, endpoint redaction, list-container handling,
  and valid installed-model fallback remain unchanged.
- Boundary: the helper does not validate model-name syntax, length, control characters, Gemini or
  artifact names, or legacy UI session strings that are indistinguishable from genuine names. A
  refresh or process restart naturally replaces an older process-local inventory.

## 2026-07-23 - Approve ARA-060 test-gate hardening

- Approval: the owner explicitly approved ARA-060 on 2026-07-23, satisfying the repository safety
  gate for a scoped pytest/test-configuration change.
- Decision order: reproduce the reported subtest-only zero-exit defect in an isolated subprocess,
  prefer a standard-library/no-new-dependency hook, and add both failing and passing sentinel
  coverage before changing the canonical test gate.
- Compatibility: preserve ordinary pytest/unittest failures, successful subtest reporting,
  Python 3.10/3.13 CI, existing test semantics, and the current `make check` entrypoint. Do not bulk
  rewrite the 102 call sites merely to compensate for infrastructure behavior.
- Boundary: this approval does not authorize production behavior changes, provider calls, ignored
  runtime access, dependency additions without new evidence, or changes to experiment artifacts.
- Finding: direct pytest 9.0.3 execution returns status 1 for both one and 16 subtest-only failures.
  The historical zero was the successful status of an outer parallel orchestration script that
  rendered nested stdout but did not inspect or propagate nested `exit_code` values.
- Resolution: do not change pytest configuration or add a dependency. Add an isolated subprocess
  contract test with third-party plugin autoload disabled, inherited pytest injection options
  removed, and a fixed timeout; retain ARA-059's parent aggregates as local defense in depth.

## 2026-07-23 - Approve ARA-056 pre-agent interrupt hardening

- Approval: the owner explicitly approved ARA-056 after receiving the greater-than-30-minute,
  medium-risk assessment and checkpoint plan.
- Decision order: reproduce interrupts at each pre-agent boundary before changing lifecycle code,
  then prefer one shared finalization/rollback path over per-call ad hoc handlers.
- Compatibility: preserve ARA-023 manual-interrupt status 130, cooperative status-0 stops, ARA-041
  config/manifest startup transaction ordering, existing artifact schemas, successful rounds,
  ordinary exception behavior, and legacy resume interpretation.
- Boundary: do not redesign cross-file transactions, absorb ARA-054/055, change provider/prompt/
  scoring behavior, access ignored runtime, add dependencies, or rewrite stable runner structure
  without fault-matrix evidence.
- Finding: fault injection immediately after round-directory creation, round-entry logging, and
  memory loading reproduced three missing-checkpoint failures. In every case startup metadata
  already existed, so rolling back only the empty round would still leave a misleading running run.
- Resolution: extend only the existing manual-interrupt boundary over pre-agent round setup and
  route both boundaries through one marker. Standard finalization records zero completed rounds and
  a reusable next round, then re-raises `KeyboardInterrupt`; ordinary exceptions remain outside this
  catch and keep their prior behavior.

## 2026-07-23 - Approve ARA-054 design stage only

- Approval: the owner explicitly approved the ARA-054 design stage on 2026-07-23.
- Authorization: inspect tracked code and tests, run provider-free characterization in temporary
  workspaces, and update recovery/design documentation. Runtime implementation, schema changes, and
  artifact migration require separate approval.
- Evidence boundary: preserve every partial-output byte. Do not move, delete, truncate, replace, or
  overwrite partial evidence during characterization or as an implicit recovery mechanism.
- Design order: establish the per-stage interrupt/quota state matrix first; map all writers,
  readers, identity checks, and transaction boundaries second; then compare staging/quarantine,
  partial-round compatibility, and rollback approaches.
- Acceptance boundary: the selected design must specify deterministic discovery, ownership,
  retry, compatibility, crash recovery, and migration behavior, and must keep ARA-055's
  cross-filesystem history transaction problem explicit rather than silently absorbing it.
- Result: select append-only attempt staging beneath the run root and retry an interrupted round
  from draft. Stopped attempts are immutable; successful canonical output retains the existing four
  filenames and bytes.
- Rejected alternatives: do not delete/rollback evidence, overwrite canonical partial files, or
  continue from an apparent last stage. Current placeholders and marker ordering cannot prove a
  safe continuation boundary.
- Legacy boundary: ambiguous canonical partial directories remain fail-closed. A journaled,
  explicit migration may be designed later but is not authorized or implemented.

## 2026-07-23 - Approve ARA-054 implementation package 1

- Approval: after receiving the recommended next task, the owner said `继续`.
- Authorized scope: create-only attempt storage primitives plus a deterministic shared recovery
  classifier and provider-free tests.
- Excluded scope: do not switch the runner's canonical write path, publish staged output, migrate
  legacy artifacts, or absorb ARA-055.
- Evidence boundary: this package may create new test artifacts and new append-only attempt paths;
  it must not move, delete, truncate, replace, or overwrite existing canonical or partial evidence.
- Completion boundary: package 1 may complete independently while KI-054 remains open. Runtime
  recovery behavior must not be claimed fixed until a later approved package is implemented and
  the full interrupt/quota matrix passes.

## 2026-07-23 - Approve ARA-054 runtime recovery package

- Approval: after receiving the recommended next task, the owner said `继续`.
- Authorized scope: manifest transitions, empty-canonical handoff, bounded disk-space protection,
  staged runner writes, canonical publication, shared runner/preview classification, and
  provider-free interrupt/quota regression coverage.
- Excluded scope: do not migrate legacy canonical partials, alter experiment semantics, or absorb
  the ARA-055 histories/checkpoint transaction.
- Compatibility boundary: completed canonical rounds must keep the same four filenames and bytes;
  existing ambiguous partials remain fail-closed and immutable.
- Interruption boundary: every independently safe phase must be committed and pushed. If
  publication cannot be separated safely from ARA-055, stop at the last verified staging
  checkpoint rather than weakening recovery guarantees.

## 2026-07-23 - Complete ARA-054 runtime recovery

- Resolution: use append-only attempts for every new runner round, persist only the current stage,
  and publish a verified four-stage tree before scoring or history mutation.
- Publication: an absent canonical directory uses a platform no-replace atomic rename. A preserved
  historical empty canonical directory uses create-only files in stage order, retains the attempt
  output, and reconciles only an exact verified prefix after interruption.
- Eligibility: preview, runner preflight, and final checkpoint use the same classifier and bounded
  attempt/disk policy. Stopped attempts are immutable; retry always starts from draft.
- Compatibility: existing completed canonical bytes, provider order, prompts, scores, metrics, and
  experiment interpretation are unchanged. Nonempty legacy canonical partials remain fail-closed.
- Boundary: `published_uncommitted` still belongs to ARA-055; no legacy migration or cross-file
  transaction was added.

## 2026-07-23 - Approve ARA-055 design stage only

- Approval: after ARA-054 closeout recommended ARA-055 design as the next task, the owner said
  `批准`.
- Authorized scope: inspect tracked code and history, characterize failures only in temporary
  provider-free workspaces, and write the transaction/recovery design plus durable state.
- Required analysis: cover canonical publication, both history locations, checkpoint/summary/config,
  memory/research-state side effects, configured external run storage, interruption at every write
  boundary, idempotency, stale journal handling, and legacy compatibility.
- Excluded scope: no runtime transaction implementation, automatic artifact migration, dependency
  changes, provider calls, ignored runtime access, or mutation of canonical/experimental data.
- Acceptance boundary: the design must not claim cross-filesystem atomic rename and must specify a
  deterministic fail-closed recovery path with bounded journal state and no duplicate rounds.

## 2026-07-23 - Select an immutable roll-forward journal for ARA-055

- Evidence: 40 provider-free temporary cases covered ten post-publication write boundaries,
  `OSError`/`KeyboardInterrupt`, and internal/configured-external run storage. All four variants at
  each boundary produced the same generation state.
- Confirmed failure: before the second history write, canonical round 2 and its `published`
  attempt exist, project history is `[1,2]`, run history is `[1]`, and checkpoint remains at 1.
  Preview correctly blocks a duplicate as `published_uncommitted`, but no current recovery payload
  can finish the commit.
- Decision: prepare one immutable project-local journal before an attempt becomes publishable;
  accept each fixed artifact only at its recorded before or after hash; roll forward missing
  after-images; advance checkpoint last; remove the journal only after complete verification.
- Finalization decision: use a separate project-local transaction for exact run summary, finalized
  run config, and final checkpoint, applying the final checkpoint last.
- Rejected: reversing history order, cross-filesystem directory rename, canonical rollback,
  history inference from Markdown, an undiscoverable run-only journal, full-history journal copies,
  and a broad database/event-store migration.
- Compatibility: canonical and public artifact formats remain unchanged. Journal-less historical
  `published_uncommitted`, manually edited third generations, moved pending storage, and unknown
  schemas stay preserved and fail closed.
- Authorization: this is a design decision only. All runtime packages in
  `docs/ARA_055_CROSS_FILESYSTEM_ROUND_COMMIT_DESIGN.md` require separate approval.

## 2026-07-23 - Approve ARA-055 implementation package 1 only

- Approval: after the ARA-055 design closeout recommended package 1, the owner said `批准`.
- Authorized scope: extract deterministic history, memory, research-state, checkpoint, summary,
  and config after-image builders; add one strict bounded in-memory round-journal codec with fixed
  artifact enums; add provider-free unit tests.
- Compatibility requirement: public artifact serialization and current runtime behavior remain
  unchanged. Existing writer functions may delegate to pure builders only when byte-for-byte
  regressions prove equivalence.
- Excluded scope: no runtime journal I/O, journal path registration, transaction prepare/recovery,
  runner/preview/UI/report/diagnostic routing, dependencies, provider calls, ignored runtime,
  artifact migration, or packages 2-7.
- Checkpoint requirement: commit and push the activation state before implementation, then keep the
  implementation and final recovery closeout as separately validated commits.

## 2026-07-23 - Keep ARA-055 package 1 filesystem-free and byte-compatible

- Decision: package 1 exposes immutable metadata plus exact serialized after-images but performs no
  journal or artifact I/O. Existing storage writers delegate only to pure builders whose bytes are
  regression-tested against the prior implementation.
- Schema decision: use closed round-artifact names and exact envelope/record keys, including
  configured-storage and optional stable stat identity. Reject unknown or ambiguous input rather
  than normalizing it.
- Bound decision: reject journals larger than 2 MiB, JSON deeper than 128 levels, duplicate keys,
  non-finite values, invalid UTF-8, unsafe identifiers, and mismatched embedded content digests.
- Serialization decision: impose fixed ordering on the journal envelope and artifact records while
  preserving embedded after-value insertion order because the existing artifact byte hash depends
  on that order.
- Deferral: runtime create-only journal storage, trusted path revalidation, prepare/apply/recovery,
  fault injection, and runner integration remain package 2 or later and require separate approval.

## 2026-07-24 - Approve ARA-055 implementation package 2 only

- Approval: after the package-1 closeout recommended package 2, the owner said
  `批准下一个任务`.
- Authorized scope: implement the fixed create-only round journal and provider-free
  prepare/classify/apply/recover engine; revalidate trusted project/run identity and ARA-054
  attempt/publication evidence; add dry-run conflict diagnostics and the internal/configured
  external storage fault matrix.
- Compatibility requirement: preserve canonical output and public artifact bytes, keep recovery
  idempotent and provider-free, accept only exact before/after generations, write checkpoint last,
  and fail closed without path/content disclosure on any unknown generation or identity.
- Excluded scope: no runner, resume-preview, UI, analytics, report, or diagnostic routing; no
  finalization journal, legacy migration, dependency/config change, provider call, ignored runtime
  access, or packages 3-7.
- Checkpoint requirement: push this activation state before adding engine code, then keep
  implementation and recovery closeout in separately validated commits.

## 2026-07-24 - Keep ARA-055 package 2 dormant, create-only, and roll-forward only

- Journal decision: register exactly the two fixed phase-journal names, create the round journal
  exclusively before publication, reopen and compare its exact bytes, and remove it only when the
  same single-link leaf still matches.
- Recovery decision: revalidate the selected project, configured run storage, stable run identity,
  run config, ARA-054 attempt, canonical publication, immutable journal, and each artifact
  generation. Accept exact before or after hashes only; never infer or roll back a generation.
- Ordering decision: reconcile publication first; apply best output, project history, run history,
  memory, research state, then checkpoint last; verify the complete after generation before
  conditional cleanup.
- Compatibility decision: a new run's round one replaces old project history while an unchanged
  non-improving best output remains absent or byte-identical. Public artifact formats and ARA-054
  canonical bytes stay unchanged.
- Safety decision: bounded reads and conditional cleanup reject symlink/hard-link/special leaves;
  fixed diagnostic codes suppress path-bearing formatted exception causes. The cooperative lock
  remains outside this package, and hostile same-UID replacement remains outside the documented
  guarantee.
- Deferral: this module has no runtime caller. Runner/resume-preview/UI/report/diagnostic routing,
  finalization, migration, dependencies, providers, ignored runtime, and packages 3-7 remain
  unapproved.

## 2026-07-24 - Complete ARA-055 implementation package 2

- Result: implementation `faf1791e` adds only the dormant round prepare/classify/recover engine,
  trusted storage primitives, and provider-free fault coverage.
- Verification: focused/related coverage passes `75 passed, 162 subtests`; full `make check` passes
  `449 passed, 787 subtests`; staged safety scans 113 files clean. Push/PR runs
  `30026934582`/`30026936443` pass Python 3.10/3.13 and every workflow step.
- GitHub: exact local/upstream/`ls-remote`/PR-head equality holds at the implementation commit;
  draft PR 13 is open, cleanly mergeable, and updated.
- Boundary: package 2 is complete but KI-055 is not resolved in the current live runner. Package 3
  remains a separate high-risk routing change requiring owner approval; no package-3 code was
  started.

## 2026-07-24 - Approve ARA-055 implementation package 3 only

- Approval: the owner explicitly said `批准 ARA-055 package 3`.
- Authorized scope: route successful iterative rounds through the already verified
  `prepare_round_commit` and `recover_round_commit` engine, with journal preparation before the
  ready transition and checkpoint as the last transaction artifact.
- Compatibility requirement: preserve public artifact bytes, canonical round output, metric
  semantics, best-output behavior, prompts, logs, stop conditions, and ordinary control flow.
- Validation requirement: add provider-free runner integration, internal/configured-external
  storage, interruption, and retry coverage before the implementation is treated as stable.
- Excluded scope: packages 4-7; recovery at runner entry; resume-preview, UI, analytics, reports, or
  diagnostic routing; finalization journaling; legacy migration; dependency/config changes;
  provider calls; ignored runtime data.
- Checkpoint requirement: commit and push this activation state before editing the runner, then keep
  implementation and recovery closeout in separately validated commits.

## 2026-07-24 - Complete ARA-055 implementation package 3

- Result: implementation `54c223b` routes new and fully evidenced iterative histories through the
  package-2 prepare/recover engine, with journal creation before ready and checkpoint applied last.
- Compatibility decision: incomplete or one-sided legacy histories retain the pre-transaction
  writer because their missing before-generation cannot be reconstructed without an unapproved
  migration. A complete integer-round pair switches the following round to the transaction path.
- Path decision: checkpoint roots may use a safety-validated equivalent spelling of the same
  configured run root; arbitrary, cross-project, moved, or unsafe roots remain rejected.
- Verification: focused/related `142 passed, 382 subtests`; runner `67 passed, 220 subtests`; full
  `make check` `453 passed, 791 subtests`; staged safety 114 files clean; push/PR CI
  `30030145901`/`30030150062` passed Python 3.10/3.13 and every workflow step.
- Boundary: package 3 does not recover a pending journal at runner entry and does not route
  preview/UI/report/diagnostic readers, finalization, or migration. Package 4 requires separate
  approval.

## 2026-07-24 - Approve ARA-055 implementation package 4 only

- Approval: after package 3 closeout recommended package 4, the owner said `批准，继续`.
- Authorized scope: under the existing project lock, classify and recover an exact valid pending
  round journal before new runner/provider work; expose non-mutating recovery-required and conflict
  states to preview/UI/report/analytics consumers; reject mixed-generation reads.
- Compatibility requirement: completed and historical journal-less artifacts retain their current
  interpretation, configured external storage remains supported, public schemas stay additive or
  unchanged, and read-only consumers never perform recovery.
- Failure policy: unknown, malformed, moved, or conflicting journal state fails closed with
  path-safe diagnostics and preserves all evidence. Recovery is provider-free and idempotent.
- Excluded scope: no finalization journal or finalization reader behavior, diagnostic integration,
  legacy migration, dependency/config changes, provider calls, ignored-runtime access, or packages
  5-7.
- Checkpoint requirement: push this activation state before implementation, then keep package 4
  implementation and recovery closeout as separately validated stable phases.

## 2026-07-24 - Keep ARA-055 package 4 round-specific and read-only outside the lock

- Entry decision: normal, continuous, session, resume, and mock recover an exact valid round
  journal only after acquiring the existing project lock and before provider preflight, client
  construction, or agent work. Diagnostic remains unchanged for its separately approved package.
- Reader decision: preview and UI classification never call recovery. Analytics, comparison,
  benchmark reports, UI metadata/history/analytics/comparison, and transaction-sensitive output
  browsing refuse a project while its round journal is pending or conflicting.
- Compatibility decision: first test only the fixed round-journal leaf. An absent round journal
  preserves existing handling of unrelated metadata, including legacy unsafe leaves; a
  finalization-only journal remains outside this package.
- Failure decision: unknown or edited generations produce fixed recovery-conflict diagnostics,
  disclose no filesystem path, preserve all bytes, and prevent provider/client/agent work.
- Validation: focused `9 passed`; related `256 passed, 540 subtests`; cross-filesystem recovery
  `16 passed, 99 subtests`; full `make check` `462 passed, 791 subtests`.

## 2026-07-24 - Complete ARA-055 implementation package 4

- Completion: implementation `efcad88f1214060835d65b9e8f41c3fe78bc84aa` is exact local,
  upstream, `ls-remote`, and PR-head equal. Push/PR runs `30034539432`/`30034542276` passed
  Python 3.10/3.13 and every workflow step.
- Review record: draft PR 13 remains open and cleanly mergeable; comment `5062099962` records the
  implementation, local validation, remote CI, and exclusions.
- Outcome: valid pending round commits recover under the existing project lock before provider,
  client, or agent work. Read-only preview/UI/analytics/comparison/report consumers never mutate
  recovery state and fail closed on pending or conflicting generations where required.
- Boundary: finalization journaling is package 5 and remains separately approval-gated. Diagnostic
  recovery, legacy migration, dependencies/configuration, providers, ignored runtime, and packages
  6-7 remain outside this completion.

## 2026-07-24 - Approve ARA-061 strict numeric CLI validation

- Approval: after a bounded provider-free audit reproduced the defect and reported a 45–60 minute
  estimate, the owner said `批准ARA061`.
- Root cause: individual numeric CLI overrides use permissive built-in parsers and later clamp
  several values instead of applying the finite/range invariants already enforced for equivalent
  file configuration. Effective minimum and maximum delay overrides are never compared.
- Authorized scope: validate the seven existing numeric overrides, enforce the resolved min/max
  delay relation, retain valid boundaries including quota threshold zero, and add parser,
  no-write/startup, and scheduler/config compatibility tests.
- Failure policy: invalid user input exits with fixed argparse/startup status 2 before project
  writes, provider preflight, client construction, or agent work. Do not silently reinterpret it.
- Excluded scope: no configuration-file schema/default change, scheduler policy redesign,
  dependency, provider, experiment, ignored-runtime, or ARA-055 package-5 change.

## 2026-07-24 - Complete ARA-061 at the CLI startup boundary

- Implementation: `b1c1b6c96aaa46b03ef1e25c30aebc771893e4d9` replaces permissive numeric
  parsers and downstream clamps with finite/range-aware argument types, then validates the
  effective min/max relation after configuration merge.
- Compatibility: documented boundaries remain accepted, including `--max-rounds 1`,
  `--max-provider-quota-failures 0`, 86400 seconds maximum delay, retry count 20, and 1000-character
  prompt minima. Defaults, configuration schema, scheduler policy, providers, and experiments are
  unchanged.
- Verification: focused `4 passed, 18 subtests`; related `244 passed, 554 subtests`; full
  `make check` `466 passed, 809 subtests`; staged safety 115 files with zero findings.
- Remote evidence: exact local/upstream/`ls-remote`/PR-head equality; push/PR CI
  `30081927773`/`30081930092` passed Python 3.10/3.13 and every workflow step. PR comment
  `5068253242` records the result.
- Next boundary: ARA-055 package 5 remains separately approval-gated; this completion does not
  authorize finalization journaling or other queued policy work.

## 2026-07-24 - Approve ARA-055 implementation package 5 only

- Approval: after ARA-061 closeout explicitly recommended package 5, the owner said `批准`.
- Authorized scope: add one fixed create-only finalization journal; capture exact bounded
  `run_summary.json`, finalized `run_config.json`, and final `checkpoint.json` after-images; apply
  summary and config before the checkpoint; recover valid pending state under the iterative entry
  lock; block approved read-only consumers without mutation while generations are mixed.
- Compatibility requirement: preserve public artifact schemas/bytes, stop decisions, timestamps,
  resume eligibility, configured external storage, manual-interrupt status 130, cooperative status
  0, and package 3/4 round-transaction ordering.
- Failure policy: unknown/malformed/unsafe journals or third-generation artifacts remain preserved
  and fail closed with path-redacted diagnostics. Recovery is provider-free and idempotent.
- Excluded scope: diagnostic integration, legacy migration, dependency/configuration changes,
  provider calls, ignored runtime, experiment changes, and packages 6-7.
- Checkpoint requirement: commit and push this activation record before production or test changes,
  then keep implementation and recovery closeout separately verifiable.

## 2026-07-24 - Implement finalization as an exact roll-forward transaction

- Transaction boundary: the runner builds the existing final summary, finalized configuration, and
  final checkpoint values in memory, persists one fixed create-only project journal, then applies
  summary, configuration, and checkpoint in that order.
- Recovery contract: each artifact must match either its recorded before or after digest; any third
  generation is preserved as a read-only conflict. Every write is verified and journal cleanup is
  conditional on the exact reopened transaction bytes.
- Compatibility decision: summary and checkpoint resume metadata remain exactly equal. Finalized
  config may retain established session metadata, so cross-artifact validation compares the four
  recovery-core fields rather than discarding or rejecting compatible extra fields.
- Routing: iterative entry recovers valid pending finalization under the existing project lock.
  Preview, UI, analytics, compare, report, and artifact readers expose or reject pending/conflicting
  state without mutation. Diagnostic integration and legacy migration remain separate packages.

## 2026-07-24 - Complete ARA-055 package 5

- Implementation: `5c9f0ced8d45d3aafd406f3e4a84beb46d8d8d5c`.
- Verification: focused `7 passed, 16 subtests`; affected regression `112 passed, 372 subtests`;
  final `make check` `473 passed, 825 subtests`; staged safety 116 files with zero findings.
- Remote evidence: exact local/upstream/`ls-remote`/GitHub branch/PR-head equality; push/PR CI
  `30085545590`/`30085548995` passed Python 3.10/3.13 and every workflow step.
- Boundary: package 6 diagnostic recovery and package 7 legacy migration remain separately
  approval-gated. This completion does not authorize either package.

## 2026-07-24 - Approve ARA-055 package 6 diagnostic integration

- Approval: after package 5 completion recommended package 6 with a 60–100 minute estimate, the
  owner said `批准，继续`.
- Transaction boundary: use a separate fixed diagnostic-finalize journal because diagnostic has no
  ARA-054 attempt identity and independently writes project score history plus run-local metrics.
  A successful diagnostic transaction covers both histories, summary, finalized config, and
  checkpoint with checkpoint last. Zero-round quota metadata may reuse package 5 finalization.
- Entry/read policy: recover valid pending diagnostic state under the existing project lock before
  provider/client construction; readers remain non-mutating and fail closed on mixed or unknown
  generations.
- Excluded scope: no legacy migration, dependency/configuration change, provider call, ignored
  runtime, experiment change, historical artifact mutation, or package 7.

## 2026-07-24 - Keep diagnostic finalization fixed, checkpoint-last, and provider-free

- Use one project-local diagnostic journal because diagnostic has no ARA-054 attempt identity.
  Store exact after-values and hashes for its two one-round histories plus summary, config, and
  checkpoint; apply checkpoint last.
- Require both histories to contain the same single round and cross-check run identity, completion
  state, stop/resume metadata, score, and one common finalization timestamp before journal creation
  or recovery.
- Reuse package 5 only for a quota stop before a diagnostic round completes. Do not broaden package
  5 semantics or infer a diagnostic attempt/migration identity.
- Recover only under the existing entry lock before provider/client work. Preview and readers stay
  non-mutating and fail closed on unknown generations.

## 2026-07-24 - Complete ARA-055 package 6 without starting legacy migration

- Implementation `24d56ba` and push/PR CI `30088147987`/`30088150085` are green on Python
  3.10/3.13, every isolated-wheel/check step, and zero annotations.
- Package 6 closes the approved diagnostic split-generation defect. Package 7 remains an explicit
  legacy-migration design/owner decision and is not implied by this completion.

## 2026-07-24 - Approve ARA-055 package 7 design stage only

- Approval: after package 6 closeout recommended a separately gated legacy-migration design, the
  owner said `批准 继续`.
- Authorized scope: inspect tracked code, history, tests, and temporary synthetic fixtures; define
  a read-only legacy classifier, evidence/provenance bundle, dry-run contract, rollback and
  idempotency rules, explicit execution approval boundary, and future implementation packages.
- Safety boundary: existing ignored/canonical artifacts remain unread and byte-identical.
  Ambiguous states must be classified as non-migratable rather than repaired by inference.
- Excluded scope: no migration implementation/command, schema/default/dependency/provider/
  experiment change, ignored-runtime inspection, artifact move/delete/rewrite, or package execution.

## 2026-07-24 - Restrict legacy migration to one exact missing-twin candidate

- Decision: do not build a general repair command. Preserve partial, divergent, journal-less
  published/canonical/finalization/diagnostic, unsafe, unknown, and uncorrelated states without
  inference, normalization, cleanup, or quarantine.
- Sole candidate: when exactly one fixed history is absent, the present history must be a bounded
  strict-integer `1..N` list exactly matching the selected checkpoint and all present run
  authorities, with no pending journal, current-round ambiguity, unsafe storage, or live owner.
- Future execution shape: create a restricted owner-selected evidence bundle first, then use a
  fixed project-local create-only roll-forward transaction to copy exact source bytes into the
  absent fixed target with no replacement. Do not update any other artifact.
- Approval boundary: package 7A read-only classification, package 7C exact-copy execution, and any
  later destructive rollback are separately approval-gated. This design authorizes none of them.

## 2026-07-24 - Approve ARA-055 package 7A read-only classification

- Approval: after package 7 design closeout recommended package 7A, the owner said `批准，继续`.
- Authorized scope: fixed L00-L20 classification/reason enums, one strict additive report schema,
  and explicitly targeted bounded/no-follow inspection of one selected project using trusted
  internal/configured-external run identity.
- Mutation boundary: discovery is pure and provider-free. It must not write, create, replace,
  delete, quarantine, recover, steal a lock, scan all projects, or implicitly execute migration.
- Excluded scope: CLI/doctor/UI routing, evidence bundle, transaction/receipt, missing-twin
  creation, rollback, dependencies/defaults/providers/experiments, ignored runtime, and packages
  7B-7D.

## 2026-07-24 - Keep package 7A internal, total, and execution-inert

- The classifier accepts exactly one owner-selected project path and reads only fixed allowlisted
  project/run leaves through existing registered-anchor and bounded no-follow primitives.
- A valid live lock returns an orthogonal `busy` result; stale locks remain untouched; malformed
  locks and unsafe/unknown evidence fail closed without exposing path or raw-value diagnostics.
- Only `exact_missing_history_twin` can report `eligible_candidate`. The strict report always sets
  `execution_authorized` to false and has no function capable of creating the missing target.
- Current ARA-054/ARA-055 journals and attempt/canonical states retain their existing owners.
  Package 7A maps their read-only classifiers rather than reconstructing or recovering evidence.
- Human and machine reports contain fixed enums, logical artifact labels, bounded public run IDs,
  source digest/size where applicable, and no private path, content, exception graph, provider
  value, or environment value.

## 2026-07-24 - Approve ARA-055 package 7B read-only integration

- Approval: after package 7A closeout recommended package 7B, the owner said `批准，继续` and
  confirmed the 60–90 minute long-task assessment with `确认，启动`.
- Authorized scope: expose the existing explicitly targeted classifier through one read-only
  doctor/preview surface and verify legacy-sensitive readers fail closed on unsafe transaction
  state without mutation or path disclosure.
- Safety boundary: preserve explicit single-project selection, fixed allowlisted reads,
  internal/configured-external storage, live-lock busy classification, stale/malformed lock
  preservation, and byte-compatible journal-less readers.
- Excluded scope: package 7C execution, target/evidence/journal/receipt creation, recursive project
  discovery, lock recovery/removal, rollback/delete/quarantine, dependency/default/config schema
  or provider/experiment changes, ignored runtime access, and historical artifact mutation.

## 2026-07-25 - Approve ARA-055 package 7C exact missing-twin execution

- Approval: after package 7B closeout recommended package 7C, the owner said `批准` and confirmed
  the 60–100 minute long-task assessment with `确认启动`.
- Authorized scope: the sole `exact_missing_history_twin` class; an explicit owner-selected
  restrictive evidence bundle; one fixed project-local immutable transaction; exact-byte
  no-replace target publication; lock-held roll-forward recovery; and shared reader/entry guards.
- Evidence boundary: only the selected source history is copied verbatim; other authorities are
  represented by bounded validated fields and digests. No hidden default destination or upload.
- Excluded scope: package 7D rollback/delete/quarantine, batch discovery, partial/sparse/string-
  round repair, canonical adoption, source rewrite, inferred generations, real ignored-runtime
  execution, dependency/default/provider/experiment changes, and general migration.
