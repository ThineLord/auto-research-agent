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
