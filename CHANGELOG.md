# Changelog

## Unreleased

### Security

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

### Fixed

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
