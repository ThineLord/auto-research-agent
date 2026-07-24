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
make repo-safety
make test
make check
python scripts/check_wheel_install.py
```

Use `make check` before committing. It covers the core CI sequence: Ruff format check, Ruff lint,
import smoke check, a tracked-file personal-path/high-confidence-secret scan, and `pytest -q`.
CI additionally runs `python scripts/check_wheel_install.py` in both supported Python jobs. That
bounded network-install smoke copies only explicit tracked packaging inputs into a temporary source
snapshot, builds one wheel, installs it with runtime dependencies into a fresh virtual environment,
and checks its import origin, exact bundled resources and RECORD metadata, console/module help, and
one provider-free mock round. Run it locally after packaging changes; it never builds an sdist,
uploads an artifact, or writes generated project state into the checkout.
The safety scan reads the tracked worktree and complete stage-0 index, never follows tracked
symlinks or enumerates ignored runtime artifacts, and reports only relative file names, line
numbers, and finding categories instead of echoing matched values.
The worktree scan requires descriptor-relative no-follow filesystem support and fails closed when
that support is unavailable; `--staged` remains available for inspecting the complete index.

## Stable Milestone Workflow

The release-facing workflow is intentionally small:

1. `make bootstrap`
2. `make mock`
3. `make diagnostic`
4. `make run`
5. `make resume`
6. `make survey`
7. `python -m src.main --compare-runs ...`
8. `python -m src.main --analyze-run ...`
9. `make ui`

Keep release documentation aligned with `README.md`, `CHANGELOG.md`, `docs/USER_GUIDE.md`,
`docs/quickstart_zh.md`, and `docs/runbook_zh.md`. Release packaging should not change provider
behavior, prompt semantics, scoring semantics, benchmark behavior, or artifact schemas.

## Architecture

The command-line entry point is `src.cli:main`, exposed as both `python -m src.main` and the
`auto-research-agent` console script.

CLI exit-status contract:

- `0`: the requested command completed, `--help` was shown, or a documented soft fallback (such as
  cloud-profile discovery falling back to configured seeds) completed its remaining work. A
  cooperative `STOP_REQUESTED` checkpoint stop is also successful and remains status 0.
- `1`: an explicit operation failed after startup, such as `--cloud-free-discover` being unable to
  discover models, or an unexpected runtime exception propagated to the process boundary.
- `2`: arguments, configuration, project input, provider prerequisites, run-lock acquisition, or
  resume safety checks rejected startup. These failures print a user-facing diagnostic before exit.
- `130`: the process received `Ctrl+C`. If the iterative runner catches the interrupt during its
  protected agent-execution phase, it finalizes the resumable checkpoint, run summary/config, and
  interrupted report before propagating the interrupt. Interrupts outside that protected phase do
  not promise the same artifact completeness.

Source checkouts and editable installs keep the checkout root as both resource root and writable
workspace. Non-editable wheel/source-distribution installs instead read an explicit package-data
allowlist (`config.example.yaml`, four canonical prompts, and the example task) while using the
current directory as the writable workspace. Only an installed, implicit default `--mock` run may
atomically seed a wholly missing `projects/example/task.md`; existing or explicitly selected
projects are never overwritten. Installed runs leave source Git provenance empty rather than
recording an unrelated workspace repository.

Core modules:

- `src/config.py` validates `config.yaml`, including model, runtime, project, and topic settings.
- `src/agents.py` wraps the Draft, Review, Revise, and Judge prompts and injects topic context.
- `src/runner.py` coordinates iterative rounds, checkpoints, scoring, safe stop, and resume data.
- `src/run_config.py` builds run-level reproducibility metadata, hashes prompt files, records Git
  commit state when available, and reads legacy `run_manifest.json` metadata for old runs.
- `src/run_compare.py` merges `run_summary.json`, `run_config.json` or legacy manifests, and
  `round_metrics.json` to compare two or more run roots.
- `src/run_analytics.py` builds a provider-free single-run analytics export from the same metadata
  foundations for diagnostics, docs, and CI-safe artifact inspection.
- `src/mock_run.py` provides deterministic fake Draft/Review/Revise/Judge agents for `--mock`
  demo runs. It reuses the normal runner and writes normal artifacts without creating a provider
  client.
- `src/metrics.py` centralizes per-agent timing, character counts, conservative token estimates,
  and per-round text evolution metrics so runner, diagnostic mode, UI tables, and comparison
  fallbacks use the same additive schema.
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

### Automatic artifact filesystem boundary

Normal CLI, runner, session, diagnostic, survey, provider-event, runtime-lock, and UI workflows
treat repository code/configuration and the local workspace/storage ancestors as trusted, but do
not trust the automatic artifact nodes inside a selected project or run. A selected `projects/`
directory, project directory, or `task.md` may not be a symbolic link. Fixed project artifact
leaves must be missing or single-link regular files; symbolic links, hard-linked files, FIFOs,
sockets, and devices fail before provider or background-process startup. Historical stale real
directories at a file-shaped artifact name remain tolerated where existing callers already handle
them. Automatic output directories must be real directories.

`project/runs` is the one intentional link exception. An existing configured storage link is
resolved once to a real directory, and new or resumed runs use canonical direct children of that
resolved location. Per-run directories discovered by the UI must themselves be real directory
entries, and their fixed metadata leaves must pass the same non-following checks. Explicit
`--analyze-run`, `--compare-runs`, and explicit export paths are user-authorized inputs and are not
silently re-scoped to the selected project.

On POSIX systems, each selected project is registered process-wide against its real `projects/`
directory, so background threads and UI reruns share the same boundary. Nested run roots inherit
that project anchor; only a configured run store outside the project receives its own resolved
physical storage anchor. Storage helpers open the trusted anchor with `O_DIRECTORY|O_NOFOLLOW`,
walk every untrusted component to the immediate parent with descriptor-relative no-follow opens,
then perform leaf `stat`, read,
append, coordination-file creation, directory creation, unlink, temporary-file creation, and
replacement relative to the final descriptor. Opened leaves are regular single-link files whose
device/inode identity is rechecked; nonblocking opens prevent FIFOs from hanging a read or append.
Atomic replacement remains same-directory and fsyncs the temporary file before replacement.
Unknown POSIX platforms without the required descriptor primitives fail closed for registered
automatic boundaries. Survey source discovery uses the same descriptor-rooted traversal, prunes
unconfigured top-level trees, and intentionally retains lexical path spelling for subsequent safe
reads instead of canonicalizing a candidate through mutable project components.

This is not a hostile multi-user filesystem sandbox. Ancestors above the registered anchor are
trusted local infrastructure. A malicious same-UID actor that replaces an untrusted real-directory
entry with a different real directory, races a new hard link onto an already opened file, or targets
an unpredictable temporary inode is outside the guarantee; static links, hard links, and special
nodes are still rejected. Windows performs component-level static link/junction and node checks,
but standard path-based fallback cannot promise resistance to active replacement between validation
and I/O.

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

Run exclusivity uses a long-held OS advisory guard at project-root `active_run.guard`; the ignored guard
file is persistent, while `active_run.json` remains transient diagnostic metadata. The metadata
includes a per-acquisition owner token plus guard device/inode identity. The guard is held from
successful acquisition through all client/agent initialization and run dispatch, and release
removes metadata only when its token, PID, and guard identity still match the handle. A process
crash releases the kernel guard automatically, so the next process can replace stale metadata
without a check/delete race. If the guard path is accidentally recreated while an owner remains
live, the stored PID/identity prevents the new inode from taking over. Existing live legacy
PID-only locks remain blocking; malformed or dead legacy metadata is recovered under the guard.

Progress comes from:

- `checkpoint.json` for completed round, best score, stop reason, and resume eligibility.
- `runs/<run_id>/run_config.json` for reproducibility metadata: provider/model settings, runtime
  limits, topic snapshot, prompt hashes, Git commit, start/end timestamps, stop reason, and resume
  eligibility.
- Existing-run startup treats `run_config.json` and `run_manifest.json` as one recoverable metadata
  generation. It first atomically writes `.resume_startup_transaction.json` with exact prior text
  and before/after SHA-256 values, replaces both canonical files, and commits by unlinking the
  journal before `run_start` is logged or an agent can run. A surviving valid journal is rolled back
  idempotently on the next attempt that reaches the resume runner; CLI provider/client construction
  still precedes that boundary. Malformed journals, unexpected hashes, unsafe leaves, and externally
  changed metadata detected during validation fail closed. Journal unlink defines the resume-session
  start: a hard termination after that commit but before `run_start` logging may retain a complete
  zero-work session, which a later resume preserves as a started attempt rather than a split
  generation. This boundary deliberately excludes checkpoint,
  histories, summaries, and per-round writes, which have not changed at startup. Atomic leaf writes
  are fsynced, but parent-directory entries are not, so this is process/error recovery rather than a
  claim of sudden-power-loss durability.
- `runs/<run_id>/round_metrics.json` for per-round agent timings, error flags, scores, rubric
  subscores when Judge returns structured JSON, per-agent `agent_io_metrics`, and
  `evolution_metrics` for draft/revised/judge text similarity and adjacent score deltas.
- `runs/<run_id>/run_summary.json` for run-level counts, best score, stop reason, total elapsed
  seconds, total agent elapsed seconds, aggregate estimated tokens, and paths to metrics/config
  artifacts.

Offline benchmark reports resolve a recognized `STOP_*` reason from the selected run's summary,
config, then legacy manifest. They use the mutable project checkpoint only when its run path and any
supplied run ID match that target; unsafe/unknown values or unrelated state render as `unknown`.

Token fields are deliberately named `estimated_*_tokens` and use
`visible_context_chars_div_4_ceil`. They are cost-ready accounting foundations, not provider billing
truth, and the project does not hardcode vendor prices.
Evolution fields are deliberately descriptive rather than scoring fields. They are computed after
agent outputs exist, use only stored text artifacts, and must not change prompts, provider calls,
Judge parsing, stop conditions, or benchmark semantics.
Rubric trend fields follow the same rule: they aggregate already-parsed `judge_rubric` dictionaries
into averages, latest values, best values, and first-to-latest deltas. They must stay
schema-additive and must not reinterpret or rescale the Judge's top-level score.
- `resume_metadata` appears in checkpoint, run config, and run summary. It distinguishes
  `start_new_run` from `resume_existing_run`, records checkpoint resume round, whether previous
  best output is only context for a new run, whether completed round files are preserved, and the
  next-round directory status/safety action. Resumed runs also record retained-history status and
  source fields. Existing histories remain opaque append-only records; unsafe arrays fail closed
  before run config, manifest, checkpoint, round, or summary writes.
- `resume_sessions` uses lifecycle metadata as well as the round number, so resuming a zero-round
  checkpoint records a round-1 session while a genuinely new round-1 run keeps an empty list.
- Resume treats the canonical run-directory basename as the run identity. A present checkpoint
  `run_id` must match it; a missing ID is derived from it. Existing legacy manifests are parsed
  before the first write, retain creation-time and unknown fields, and merge current resume metadata.
  Unreadable, malformed, overly nested, identity-conflicting, or unmergeable manifests fail closed
  instead of being replaced.
- `src/resume_safety.py` defines the shared resume path boundary used by CLI preview, the runner,
  and the UI. A resumable root is an existing absolute per-run directory directly under the
  selected project's resolved `runs/` directory. Root containment is checked before directory
  listing or run config/manifest/summary/metrics/history reads. The runner preflights all planned
  round directories and rechecks the current round plus those resume-consumed paths before writes.
- `run.log` for the current running stage.
- `STOP_REQUESTED` for safe user-initiated pause.

The Streamlit UI renders a compact latest-run metadata table from `run_config.json` and
`run_summary.json`, keeps artifact paths repo-relative or masked, and gives artifact-specific
messages when `run_config.json`, `run_summary.json`, or `round_metrics.json` has not been written.
When a checkpoint selects a run, these UI consumers validate and canonicalize its per-run root,
derive those fixed filenames, and validate each leaf before reading it. Checkpoint `run_config` /
`run_summary` values and summary `round_metrics_path` remain provenance only; they cannot redirect
UI reads. Unsafe roots, non-regular files, and escaping run/round links produce partial or
unavailable views without exposing their target paths. The automatic project-level boundary above
also applies to project score history, inputs, logs, and UI process metadata. Project-level
`score_history.json` is used only by the
no-`run_root` legacy layout; a selected canonical run uses its own `round_metrics.json` instead.
The `Run analytics dashboard` uses existing `run_summary.json`, `round_metrics.json`, and
`score_history.json` only. It displays compact score, rubric, similarity/evolution, timeout/error,
agent timing, and estimated-token views, and should keep missing/legacy fields as empty partial
states rather than failures.
It also exposes a multi-run comparison table using the same `src.run_compare` helper as
`--compare-runs`; missing or legacy metadata should produce partial rows instead of UI failures.
Newer runs add aggregate agent elapsed seconds, estimated token totals, average revised similarity,
low-change round counts, rubric round counts, and compact rubric averages to that comparison output.
The CLI `--analyze-run` path uses `src.run_analytics` to summarize one run into score trend,
robustness, cost-ready, interpretability, rubric, and artifact sections without loading config or
calling providers.
The CLI `--legacy-migration-preview PROJECT` path dispatches even earlier: it selects exactly
`projects/<PROJECT>`, calls the bounded no-follow classifier, and prints the fixed path-redacted
human report without generation-resource validation, configuration, provider/client construction,
project-input loading, lock acquisition, recursive discovery, or writes. Every classification is
a discovery result; `execution_authorized` remains false.
The CLI `--mock` path dispatches after project input resolution and before provider validation. It
must remain deterministic, provider-free, and schema-additive: no Ollama discovery, Gemini key
checks, network calls, prompt changes, or scoring-semantic changes. The synthetic Judge score exists
only to exercise normal artifact writing for CI/docs smoke runs.
The Resume control uses checkpoint metadata to preview run id/root, last completed round, next
round, stop reason, resume eligibility, completed-round preservation, and next-round directory
status before launching `--resume`. A non-empty next-round directory is treated as partial or
uncheckpointed output and blocks resume with `fail_safe_require_user_action`; the app does not
move or delete that directory automatically. Unsafe or invalid root/round/artifact paths use the
same backend preview and disable the Resume control.

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
