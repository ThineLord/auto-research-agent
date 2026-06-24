# DEVELOPER GUIDE

This guide is for maintaining and extending `auto-research-agent`.

## Setup

Create the local environment and install runtime plus development dependencies:

```bash
make install-dev
```

The project targets Python 3.10+. Model-backed research workflows can run against local Ollama or
cloud Gemini, while Literature Survey Mode is deterministic and local-only. CI does not start
Ollama, call Gemini, or run model-backed workflows.

Useful local commands:

```bash
make format
make lint
make import-check
make test
make check
```

Use `make check` before committing. It matches the CI sequence: Ruff format check, Ruff lint,
import smoke check, and `pytest -q`.

## Architecture

The command-line entry point is `src.cli:main`, exposed as both `python -m src.main` and the
`auto-research-agent` console script.

Core modules:

- `src/config.py` validates `config.yaml`, including model, runtime, project, and topic settings.
- `src/agents.py` wraps the Draft, Review, Revise, and Judge prompts and injects topic context.
- `src/runner.py` coordinates iterative rounds, checkpoints, scoring, safe stop, and resume data.
- `src/run_config.py` builds run-level reproducibility metadata, hashes prompt files, records Git
  commit state when available, and reads legacy `run_manifest.json` metadata for old runs.
- `src/run_compare.py` merges `run_summary.json`, `run_config.json` or legacy manifests, and
  `round_metrics.json` to compare two or more run roots.
- `src/metrics.py` centralizes per-agent timing, character counts, and conservative token estimates
  so runner, diagnostic mode, and comparison fallbacks use the same schema.
- `src/session.py` builds focused session objectives, current plans, and final session reports.
- `src/literature_survey.py` implements local Literature Survey Mode: source collection, paper
  metadata parsing, deduplication, theme/gap extraction, survey report rendering, and related-work
  generation.
- `src/storage.py` owns project file IO, memory summaries, score history, and research state.
- `src/runtime.py` owns process metadata, run locks, test execution, and UI background process helpers.
- `ui/app.py` is the Streamlit UI for editing inputs, running workflows, checking model health,
  watching progress, and browsing outputs.

Generated project artifacts live under `projects/<project_name>/` and are ignored by git when they
are runtime outputs.

## Configuration And Topic Context

`config.yaml` is validated before CLI or UI workflows start. Unknown keys and invalid values fail
fast with field-specific messages.

The `topic` block makes the reusable prompts project-agnostic:

```yaml
topic:
  title: Example Research Planning Task
  description: A public-safe starter project for learning the local research workflow.
  keywords:
    - research
    - planning
    - methods
    - evaluation
    - risks
```

`drafting_mode` is also validated at startup. Supported values are:

- `best_guided`: backward-compatible default; Draft sees current best output and previous Judge
  feedback.
- `fresh_from_task_with_review`: Draft starts from the original task each round and may use previous
  Review/Judge feedback.
- `continue_from_previous_draft`: Draft continues from the previous draft/revised output and may use
  feedback.

The selected mode is written into `checkpoint.json`, `score_history.json`, and
`runs/<run_id>/run_config.json`.

The tracked `projects/example` folder is the sample project. To work on another topic, create a new
folder under `projects/`, point `project_name` at it, and update the `topic` block plus `task.md`.
The UI uses the configured `project_name` as its initial selection when that folder exists, and
falls back to the public-safe example only when the configured project is unavailable.

## Streamlit And Runtime Flow

The UI starts background processes through `src.runtime.start_background_process`. Process metadata
is written to `ui_run_process.json` or `ui_model_job_process.json`; stale metadata is removed when
the PID is no longer active.

Progress comes from:

- `checkpoint.json` for completed round, best score, stop reason, and resume eligibility.
- `runs/<run_id>/run_config.json` for reproducibility metadata: provider/model settings, runtime
  limits, topic snapshot, prompt hashes, Git commit, start/end timestamps, stop reason, and resume
  eligibility.
- `runs/<run_id>/round_metrics.json` for per-round agent timings, error flags, scores, rubric
  subscores when Judge returns structured JSON, and per-agent `agent_io_metrics`.
- `runs/<run_id>/run_summary.json` for run-level counts, best score, stop reason, total elapsed
  seconds, total agent elapsed seconds, aggregate estimated tokens, and paths to metrics/config
  artifacts.

Token fields are deliberately named `estimated_*_tokens` and use
`visible_context_chars_div_4_ceil`. They are cost-ready accounting foundations, not provider billing
truth, and the project does not hardcode vendor prices.
- `resume_metadata` appears in checkpoint, run config, and run summary. It distinguishes
  `start_new_run` from `resume_existing_run`, records checkpoint resume round, whether previous
  best output is only context for a new run, whether completed round files are preserved, and the
  next-round directory status/safety action.
- `run.log` for the current running stage.
- `STOP_REQUESTED` for safe user-initiated pause.

The Streamlit UI renders a compact latest-run metadata table from `run_config.json` and
`run_summary.json`, keeps artifact paths repo-relative or masked, and gives artifact-specific
messages when `run_config.json`, `run_summary.json`, or `round_metrics.json` has not been written.
It also exposes a multi-run comparison table using the same `src.run_compare` helper as
`--compare-runs`; missing or legacy metadata should produce partial rows instead of UI failures.
Newer runs add aggregate agent elapsed seconds and estimated token totals to that comparison output.
The Resume control uses checkpoint metadata to preview run id/root, last completed round, next
round, stop reason, resume eligibility, completed-round preservation, and next-round directory
status before launching `--resume`. A non-empty next-round directory is treated as partial or
uncheckpointed output and blocks resume with `fail_safe_require_user_action`; the app does not
move or delete that directory automatically.

The model health check is intentionally fast: it checks Ollama API availability and selected-model
presence without sending a generation prompt.

## Literature Survey Mode

`make survey` dispatches through `src.cli` before provider validation. This is intentional: survey
mode is deterministic and local, so it should run even when Ollama is stopped or Gemini credentials
are unavailable. Configuration lives under `literature_survey:` in `config.yaml`.

Generated survey artifacts live under `projects/<project>/survey/` by default and are ignored by
git. Keep example or golden outputs under `docs/examples/` instead of committing local project
survey output.

Survey metadata artifacts are expected to stay deterministic and schema-additive: parsers normalize
DOI/arXiv aliases for deduplication, and both `paper_metadata.json` and `survey_manifest.json`
include metadata-quality counts plus representative theme groups.

## Contribution Flow

1. Start from a clean understanding of `git status`.
2. Keep edits scoped to the requested behavior.
3. Add focused tests for changed helpers and public behavior.
4. Run `make check` and fix failures before committing.
5. Stage only intended files.
6. Commit with a short imperative message.
7. Push the branch and open a PR when requested.

Avoid committing runtime outputs such as `runs/`, `best_output.md`, `checkpoint.json`, logs, or
local environment files.
