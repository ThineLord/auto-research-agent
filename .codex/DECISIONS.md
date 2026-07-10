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
