# DEVELOPER GUIDE

This guide is for maintaining and extending `auto-research-agent`.

## Setup

Create the local environment and install runtime plus development dependencies:

```bash
make install-dev
```

The project targets Python 3.10+ and runs fully locally against Ollama. CI does not start
Ollama or run model-backed workflows.

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
- `src/session.py` builds focused session objectives, current plans, and final session reports.
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
  title: Privacy-Aware Memory Adapter (PAMA) for Personal AI Agents
  description: Research planning for privacy-aware memory adaptation in personal AI agents.
  keywords:
    - privacy
    - memory
    - adapter
    - evaluation
    - baseline
```

The tracked `projects/pama` folder is the sample project. To work on another topic, create a new
folder under `projects/`, point `project_name` at it, and update the `topic` block plus `task.md`.

## Streamlit And Runtime Flow

The UI starts background processes through `src.runtime.start_background_process`. Process metadata
is written to `ui_run_process.json` or `ui_model_job_process.json`; stale metadata is removed when
the PID is no longer active.

Progress comes from:

- `checkpoint.json` for completed round, best score, stop reason, and resume eligibility.
- `run.log` for the current running stage.
- `STOP_REQUESTED` for safe user-initiated pause.

The model health check is intentionally fast: it checks Ollama API availability and selected-model
presence without sending a generation prompt.

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
