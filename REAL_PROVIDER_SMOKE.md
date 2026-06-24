# Real-Provider Smoke Validation

Date: 2026-06-25
Branch: master
Current HEAD before report: a63a39aa4ffaf3d47bb8da83d2145844d0922609
Release target: v0.1.1-hardening

## Executive Summary

Real-provider smoke validation partially passed.

The local Ollama provider path works when the provider is explicitly selected: one diagnostic round
completed with `qwen3:8b`, wrote the expected artifacts, and `--analyze-run` read them successfully.
The generated diagnostic console/log display paths were repo-relative.

The exact requested command, `make diagnostic ARGS="--project example --model qwen3:8b"`, did not
run Ollama in this local environment because the current local config resolves to Gemini. The CLI
kept the configured provider and stopped on missing Gemini credentials. This is a command-accuracy
finding: for provider-independent smoke instructions, the local Ollama command should include
`--provider ollama`.

Gemini smoke was skipped because neither `GEMINI_API_KEY` nor `GOOGLE_API_KEY` was configured.

## Initial State

* Command: `git status`
* Result: clean and synced.
* Evidence: `On branch master`; `Your branch is up to date with 'origin/master'.`; `nothing to
  commit, working tree clean`.

* Command: `ollama list`
* Result: Ollama available with the target model installed.
* Evidence: installed models included `qwen3:8b`, `qwen3:14b`, `deepseek-r1:8b`, and `llama3.1:8b`.

* Command: env key probe for Gemini
* Result: no Gemini key available.
* Evidence: `GEMINI_API_KEY_SET=False`; `GOOGLE_API_KEY_SET=False`.

## Ollama Diagnostic Result

### Requested Command Probe

* Command: `make diagnostic ARGS="--project example --model qwen3:8b"`
* Completed: No provider-backed diagnostic was run.
* Result: failed before model execution because the configured provider was Gemini and no Gemini key
  was present.
* Evidence: output ended with `Gemini API key is missing. Set the configured environment variable,
  GEMINI_API_KEY, or GOOGLE_API_KEY, then retry.`
* Notes: `--model qwen3:8b` overrides the model name but does not switch provider. In environments
  whose local config provider is not Ollama, release smoke docs should use an explicit provider
  override.

### Explicit Ollama Provider Probe

* Command: `make diagnostic ARGS="--project example --provider ollama --model qwen3:8b"`
* Completed: Yes.
* Run id: `20260625_015930_676608`
* Run root: `projects/example/runs/20260625_015930_676608`
* Provider/model: `ollama` / `qwen3:8b`
* Stop reason: `MAX_ROUNDS`
* Best score: `96.0`
* Completed rounds: `1`
* Round timing:
  * Draft: `43.54s`
  * Review: `34.34s`
  * Revise: `56.00s`
  * Judge: `31.38s`
* Result evidence: diagnostic output reported `Diagnostic file check passed (all round files saved)`,
  `Score: 96.00`, `Errors: draft=False review=False revise=False judge=False`, and `Diagnostic mode
  complete (terminated after round 1).`

## Artifact Checks

Checked run root `projects/example/runs/20260625_015930_676608`.

* `run_config.json`: exists
* `run_summary.json`: exists
* `round_metrics.json`: exists
* `projects/example/checkpoint.json`: exists
* `projects/example/score_history.json`: exists
* `round_metrics.json` entries: `1`

Parsed artifact summary:

* `run_id`: `20260625_015930_676608`
* `summary_stop_reason`: `MAX_ROUNDS`
* `config_stop_reason`: `MAX_ROUNDS`
* `checkpoint_stop_reason`: `MAX_ROUNDS`
* `best_score`: `96.0`
* `completed_rounds`: `1`
* `provider`: `ollama`
* `model`: `qwen3:8b`

Generated artifacts are ignored by Git:

* `projects/example/runs/20260625_015930_676608` ignored by `projects/*/runs/`
* `projects/example/checkpoint.json` ignored by `projects/*/checkpoint.json`
* `projects/example/score_history.json` ignored by `projects/*/score_history.json`
* `projects/example/run.log` ignored by `projects/*/run.log`

## Path Privacy / Display Check

Fresh diagnostic console output displayed repo-relative paths:

* `task=projects/example/task.md`
* `project_dir=projects/example`
* `task_path=projects/example/task.md`
* `Saved diagnostic round outputs: projects/example/runs/20260625_015930_676608/round_01`
* `Run root: projects/example/runs/20260625_015930_676608`

Fresh `projects/example/run.log` diagnostic lines also used repo-relative project paths:

* `project_dir=projects/example`
* `task_path=projects/example/task.md`

No local absolute path hits were found in the fresh diagnostic `round_01` files or
`round_metrics.json` when scanning for `/Users/hanzhiyou`, `/private/var`, and `/tmp`.

Known caveat: the long-lived ignored `projects/example/run.log` still contains older pre-hardening
absolute paths from historical local runs. The fresh diagnostic lines produced in this smoke are
repo-relative.

## Analyze-Run Result Summary

* Command: `.venv/bin/python -m src.main --analyze-run projects/example/runs/20260625_015930_676608`
* Completed: Yes.
* Result: `metadata_status: ok`
* Metadata sources: `run_summary`, `run_config`, `round_metrics`
* Provider/model: `ollama` / `qwen3:8b`
* Completed rounds: `1`
* Best score: `96.0`
* Average score: `96.0`
* Trend: `single_round`
* Stop reason: `MAX_ROUNDS`
* Timeout count: `0`
* Error count: `0`
* Total agent elapsed seconds: `165.258`
* Estimated input/output/total tokens: `3037` / `894` / `3931`
* Rubric round count: `1`
* Rubric averages:
  * `novelty_and_research_value`: `24.0`
  * `technical_clarity_and_correctness`: `24.0`
  * `feasibility_and_implementation_realism`: `19.0`
  * `evaluation_design_quality`: `19.0`
  * `tomorrow_actionability`: `20.0`
* Artifact paths in analysis output were repo-relative.

## Gemini Diagnostic Result

* Command planned: `make diagnostic ARGS="--project example --provider gemini --model gemini-3.5-flash"`
* Result: skipped.
* Reason: no existing Gemini credentials were configured in the environment.
* Evidence: `GEMINI_API_KEY_SET=False`; `GOOGLE_API_KEY_SET=False`.

## Issues Found

### Issue 1 - Ollama smoke command should explicitly set provider

* Severity: medium for release instructions; low for runtime behavior.
* Reproducibility: reproduced in this environment.
* Affected workflow: release smoke validation and docs/runbook command accuracy.
* Evidence: `make diagnostic ARGS="--project example --model qwen3:8b"` stopped on missing Gemini
  credentials because the configured provider was Gemini.
* Recommended fix: update future smoke instructions to use
  `make diagnostic ARGS="--project example --provider ollama --model qwen3:8b"` when the intent is
  specifically local Ollama validation.
* Fixed now: no. This report documents the finding; no code/docs outside this report were changed.

### Issue 2 - Gemini provider remains unvalidated in this pass

* Severity: medium for release confidence.
* Reproducibility: environment-dependent.
* Affected workflow: Gemini release acceptance.
* Evidence: no `GEMINI_API_KEY` or `GOOGLE_API_KEY` environment variable was set.
* Recommended fix: run one explicit Gemini diagnostic on a machine/session with credentials already
  configured.
* Fixed now: no; skipped by scope.

## Recommendation

Treat local Ollama real-provider smoke as passed for `qwen3:8b` when using an explicit provider
override. Before calling the release fully provider-validated, run the same one-round diagnostic for
Gemini in a credentialed environment.

For future release instructions, prefer explicit provider commands:

```bash
make diagnostic ARGS="--project example --provider ollama --model qwen3:8b"
make diagnostic ARGS="--project example --provider gemini --model gemini-3.5-flash"
```
