# Changelog

## Unreleased

### Security

* CI now explicitly grants `GITHUB_TOKEN` only read access to repository contents; all unspecified
  workflow permissions remain disabled.
* Tracked reports now replace real local account names with explicit redaction wording. Local and
  CI validation scan only files reported by `git ls-files` for personal home paths, high-confidence
  provider/token shapes, and private-key headers without echoing matched values or reading ignored
  runtime artifacts.
* Provider event messages and displayed Gemini exception tracebacks now redact the exact configured
  API key, including credentials supplied through a custom environment variable, even when the
  upstream error echoes a key that does not match a known token pattern.
* Resume now accepts only canonical absolute per-run directories directly under the selected
  project's `runs/` directory. Cross-project, relative, traversal, non-directory, and escaping
  root paths fail closed before inspecting that directory. Resume-consumed run config, legacy
  manifest, summary, metrics/history, previous-round context, and all planned round directories
  also reject escaping symlinks, invalid file types, or inaccessible paths before those paths are
  read or written; the UI disables Resume for the same unsafe checkpoints.
* Latest-run UI metadata, analytics, and output browsing now derive fixed artifact names from the
  validated canonical checkpoint run root. Redundant external checkpoint/summary references and
  unsafe run or round artifact links become unavailable without being read; configured `runs/`
  storage symlinks and safe legacy in-run metadata remain supported.
* Automatic project runtime I/O now rejects linked project/task inputs, linked or hard-linked fixed
  artifact leaves, blocking special files, and linked automatic output directories before provider
  or background-process startup. POSIX reads, appends, coordination files, directory traversal and
  creation, unlink, and atomic replacement walk from a process-wide registered `projects/` or
  resolved external run-storage anchor with no-follow descriptor-relative operations and identity
  checks; worker threads share boundaries and nested run roots inherit the project anchor. Survey
  discovery uses descriptor-rooted, pruned traversal and retains lexical source paths for safe reads.
  Background log and
  process-metadata leaves are both preflighted before `Popen`, and a post-start metadata failure
  terminates the child. The configured external `runs/` storage-link contract and stale-directory
  tolerance remain. Windows performs component-level static rejection but retains a documented
  active-swap limitation; hostile same-UID replacement with another real directory is also outside
  the POSIX guarantee.
* UI project discovery and comparison skip linked project/run directories and securely reopen fixed
  run metadata leaves, closing validation/read replacement windows. Explicit CLI analysis,
  comparison, run-directory aliases, and export parents remain user-authorized paths.

### Fixed

* UI health results are now displayed only for the provider, effective model, and non-secret
  connection/credential source that was checked. Target changes and malformed or legacy snapshots
  clear stale results; endpoint/provider errors are sanitized before session storage, and a
  whitespace-only Gemini password no longer masks a valid configured key.
* Streamlit cloud-free discovery/profile session values are now scoped to the validated canonical
  project and safe content state of both artifacts. Project switches, legacy global session values,
  and external same-model-ID metadata updates reload together; unstable or unsafe snapshots fail
  empty instead of reusing stale recommendation inputs.
* Automatic cloud-free recommendation and runtime fallback now return no selection when every safe
  candidate has a profile blocked by reachability, quota, billing/safety, token-context, or unsafe-
  text results. Mixed unprofiled and healthy candidates remain eligible, Quality uses the same guard,
  and the UI distinguishes Manual mode from “no eligible automatic recommendation.”
* Cached cloud-free recommendation now distrusts discovery metadata when its current safe candidate
  membership differs from a non-empty profile artifact. CLI and UI ignore stale discovery in that
  case, retain only currently allowed configured/profiled candidates, and re-evaluate cached model
  safety under current policy without deleting or migrating existing artifacts.
* Resume now reads all four previous-round draft/review/revised/Judge context files before changing
  startup metadata. Existing unreadable or invalid-UTF-8 context blocks without agent invocation or
  artifact writes and reports only the fixed artifact name; genuinely missing legacy context remains
  compatible as empty input.
* Cloud-free model discovery now contains SDK lazy-pager iteration and model-conversion failures in
  its existing safe error result, so explicit discovery exits 1 while profile mode can retain its
  configured-seed fallback. Automatic discovery/profile artifact write failures now use a fixed,
  path-free status-1 diagnostic instead of traceback or local path disclosure.
* Literature Survey Mode manual interrupts now emit the standard `MANUAL_INTERRUPT` diagnostic and
  exit 130 without traceback or path disclosure, while preserving release of the real run lock.
  Successful surveys and artifact-I/O status 1 behavior remain unchanged.
* Structured Judge scores and rubric values that cannot be represented as floats, including numeric
  literals beyond Python's JSON integer digit limit, now follow existing invalid-output handling
  instead of raising a traceback. Valid numeric strings, clamping, legacy `SCORE:` fallback, valid
  rubric siblings, and the raw payload API remain compatible.
* Provider-free analysis and comparison now tolerate malformed, non-finite, and unrepresentably
  large legacy timing, token, evolution, rubric, and per-agent metric values without traceback or
  non-standard JSON. Unrepresentable elapsed totals and deltas become unavailable, representable
  extreme averages remain finite, raw legacy rubric averages are normalized, and ordinary finite
  aggregation plus historical token/evolution compatibility remains unchanged.
* Resume now treats only the JSON boolean `true` as an eligible checkpoint flag; strings, numbers,
  and container values fail closed before the runner or any agent stage can write artifacts. Huge,
  boolean, NaN, and infinite preview scores use the existing safe default instead of crashing or
  propagating non-finite state, while finite legacy numeric strings remain compatible.
* Analysis and comparison exports now report unavailable or unresolvable explicit output paths as
  privacy-safe operation failures (status 1) instead of emitting tracebacks and local paths;
  successful output and explicitly selected parent symlinks remain supported.
* Analysis and comparison now ignore boolean, non-finite, and unrepresentably large overall scores;
  missing scores cannot outrank valid negative scores, overflowed deltas serialize as `null`, and
  finite-extreme averages remain strict JSON without changing ordinary historical rounding.
* Clean wheel and source-distribution installs now bundle the public sample configuration, four
  canonical prompts, and default example task. Installed mock runs use the current directory as a
  writable workspace, atomically seed only a wholly missing implicit example project without overwriting
  existing input, and do not record an unrelated workspace Git commit as source provenance.
* Resuming an existing zero-round checkpoint now appends a round-1 entry to run-config
  `resume_sessions`; a genuinely new round-1 run still has no resume-session entry.
* Resuming a legacy run now preserves its original manifest provenance and unknown extension fields
  while merging current resume metadata. Existing manifests that cannot be preserved fail before
  writes, and an explicit checkpoint run ID must match the canonical run-directory identity;
  missing IDs continue to derive safely from that directory.
* Manual `Ctrl+C` now exits CLI and module entrypoints with status 130. Interrupts caught during the
  runner's protected agent-execution phase still finalize resumable checkpoint, summary/config,
  and interruption-report artifacts before propagation, while cooperative `STOP_REQUESTED` stops
  remain successful status 0 exits.
* Historical benchmark reports now take recognized stop reasons from the selected run's summary,
  config, or legacy manifest. The mutable project checkpoint is used only when its run path/ID
  proves it belongs to that target; unknown/private text renders safely instead of relabeling or
  leaking through an older report.
* Gemini now passes the configured `model.timeout_seconds` to the Google Gen AI client's HTTP
  transport in milliseconds for every supported API-key source. Transport timeouts are reported as
  a privacy-safe `timeout` provider error without adding retries or changing generation settings.
* The `--compare-runs` CLI now rejects fewer than two run directories with a clear argument error,
  matching its documented contract. The internal comparison helper still accepts one run for
  compatibility with existing UI, analytics, and legacy-metadata callers.
* Failed agent rounds and invalid Judge outputs no longer replace a trusted `best_output.md` with
  synthetic zero-score or placeholder content; their artifacts and error metrics remain available.
* Non-positive `--max-rounds` values now fail at argument parsing, and direct runner calls reject
  them before creating run artifacts, instead of silently running one round or emitting a zero-round run.
* State and artifact replacement writes now use same-directory temporary files, file flush/fsync,
  and atomic replace so a pre-commit failure preserves the previous valid checkpoint.
* Resuming an existing run now retains and appends prior round metrics and score history, preserves
  best-round and cumulative runtime metadata, restores previous-round drafting context, and fails
  closed before writes when an existing history file is malformed or unsafe to append to.
* Resume now distinguishes a genuinely missing `run_config.json` from an existing file that is
  unreadable, malformed, non-object, or excessively nested. Invalid existing config blocks before
  any automatic artifact write instead of being replaced with newly generated provenance; missing
  config retains the legacy-manifest compatibility path.
* Run acquisition now holds a cross-process OS guard for the full run lifecycle and records an
  owner token plus guard identity in `active_run.json`. Concurrent cooperating contenders cannot
  both acquire, crashed owners are recoverable without stale-file deletion races, malformed legacy
  PID metadata no longer raises, recreated guard inodes cannot displace a live recorded owner, and
  an old or fork-inherited handle cannot delete replacement/parent metadata. CLI constructor
  failures also release the guard before propagating.
* CLI configuration, project-input, provider-prerequisite, and run-lock startup refusals now exit
  with status 2 instead of printing an error and reporting success. Explicit cloud model discovery
  failure exits 1, while `--help`, successful provider-free commands, and documented profile
  fallback behavior remain status 0.
* Unreadable or non-UTF-8 configuration/task input now produces a privacy-safe startup diagnostic.
  Tolerant checkpoint and optional cloud-cache readers also treat invalid UTF-8, oversized numeric
  values, and excessively nested JSON as malformed input instead of leaking a traceback.

### Maintenance

* CI jobs now have a 15-minute timeout and use the supported Node 24 releases of
  `actions/checkout` and `actions/setup-python`, while retaining the Python 3.10/3.13 push and
  pull-request matrix.
* Added tracked `.codex/` recovery state, task queue, validation evidence, decisions, known issues,
  and resume instructions for interruption-safe autonomous maintenance.

## v0.1.1-hardening - Post-Audit Hardening Release

Date: 2026-06-25

This release tags the post-v0.1.0-stable hardening pass. It does not change prompt semantics,
provider behavior, scoring semantics, benchmark behavior, or add new features.

### Hardened

* Path privacy hardening for config/project input errors, survey artifacts, runner and diagnostic
  output, benchmark reports, UI helper displays, and Streamlit process-start failures.
* Stale artifact robustness for JSON/text readers, run metadata readers, session state, benchmark
  round artifacts, process metadata, run locks, stop signals, and best-effort log appends.
* Metadata compatibility for diagnostic resume metadata and legacy analytics/comparison artifacts.
* UI/CLI masking so displayed paths are repo-relative or masked while legacy internal metadata paths
  remain compatible with resume and artifact analysis.

### Validation

Provider-free smoke validation covered:

```bash
make mock ARGS="--project example --max-rounds 1"
.venv/bin/python -m src.main --mock --project example --max-rounds 1
.venv/bin/python -m src.main --analyze-run <mock_run_path>
.venv/bin/python -m src.main --compare-runs <mock_run_a> <mock_run_b>
.venv/bin/python -m src.main --survey --project example
```

Final validation:

```bash
git diff --check
.venv/bin/python -m src.main --help
make check
```

`make check` passed with `137 passed, 43 subtests passed`.

## Stable Milestone - Phases 9-16

Date: 2026-06-24

This milestone packages the project as a reproducible, research-ready local workflow with safer
resume handling, deterministic demo runs, local survey support, run comparison, single-run
analytics, and a compact Streamlit analytics dashboard.

### Added

* Fail-safe resume handling blocks non-empty partial next-round directories before regeneration.
* Per-round evolution metrics capture score deltas, changed lines, and draft/revised/judge
  similarity without changing prompts or scoring.
* Judge rubric summaries preserve structured subscores as descriptive trends, not benchmark scores.
* `--analyze-run` exports single-run analytics without provider calls.
* `--mock` / `make mock` runs deterministic provider-free demos that write normal run artifacts.
* Streamlit latest-run analytics dashboard shows score, rubric, similarity/evolution,
  timeout/error, agent timing, and estimated-token trends from existing artifacts.
* `--compare-runs` and the UI comparison view tolerate missing or legacy metadata.

### Stable Workflow

* `make bootstrap`: prepare a new checkout and run the first smoke path.
* `make mock`: write CI/docs-safe demo artifacts without Ollama, Gemini, network, or API keys.
* `make diagnostic`: run one real provider-backed smoke round.
* `make run`: start a bounded real research run.
* `make resume`: continue the checkpointed run only when resume metadata and next-round state are
  safe.
* `make survey`: run deterministic local Literature Survey Mode without provider calls.
* `--compare-runs`: compare two or more run directories.
* `--analyze-run`: inspect one run without provider calls.
* `make ui`: inspect inputs, progress, latest metadata, analytics, comparisons, and outputs.

### Important Distinctions

* Mock mode is for demos, docs, and CI-safe artifact inspection; it is not a real research run.
* `estimated_*_tokens` fields are conservative character-based estimates, not billing tokens.
* Rubric summaries aggregate Judge-provided subscores and do not replace benchmark scores.
* `make resume` continues an existing checkpointed run; `make run` starts a new run, even if
  previous `best_output.md` is available as context.
* Non-empty partial next-round directories block resume and require manual inspection, movement, or
  deletion.

### Validation Baseline

The milestone validation gate is:

```bash
git diff --check
.venv/bin/python -m src.main --help
make check
```

`make check` covers Ruff format, Ruff lint, import smoke checks, and the pytest suite.
