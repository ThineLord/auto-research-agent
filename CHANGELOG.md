# Changelog

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
