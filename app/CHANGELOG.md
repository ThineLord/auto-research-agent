# Changelog

## Unreleased

- Select Python 3.10 or newer for `make venv`, `make install`, `make install-dev`, and `./start` when `python3` is older. An explicit `PYTHON=` is used while creating an environment, and `VENV=` still chooses its location. If no supported interpreter is available, setup stops before creating an environment or installing packages and prints the minimum version plus the interpreters it found. An existing incompatible `.venv` is left in place with steps to keep it or move it aside; it is not deleted or overwritten.
- After `VENV=` selects an environment, `./start` and Make run that environment's Python, including when `app/.venv` is absent. A path with spaces or quotes is passed as the path. Setup does not install into a directory that is not that virtual environment, or into one whose pip is missing, and it leaves the directory in place with steps to keep it or recreate it.
- Keep unscored placeholders out of visible best scores and chart score changes. A scoring-failure zero no longer supplies the next valid round's displayed delta, a saved best score near -1 stays a historical value, and an early invalid-judge zero stays out of means and trends. A failed round cannot outrank a successful score. All-failure archives still show an empty best score in run metadata and workspace progress, while a live valid score stays visible.
- Ignore explicit invalid-score fallbacks in run comparison and analysis. The runner's zero substitute and untouched -1 best-score placeholder no longer enter averages, score trends, or ranking, and a comparison with no valid score does not name a winner. Real zeros, finite negative legacy scores, mixed ranked and unranked runs, and failure counts stay in place.
- Keep repeated literature surveys stable by skipping this run's generated artifacts, including an explicit `--survey-output` report and the default survey paths, in flat and legacy projects. Other project Markdown remains a source. Flat projects record distinguishable workspace-relative source paths for same-named run drafts.
- Skip survey reports and related-work drafts generated at another output location, including a return to the default directory, a new report name, and consecutive switches, in flat and legacy projects. User Markdown and same-named notes stay sources, and earlier reports stay on disk. Record paths from the workspace root, so a flat project stays `<project>/...` even when that directory is named `projects`; legacy `projects/<name>/` paths stay unchanged.
- Refuse ordinary resume of an offline mock before any provider check or run-artifact change. The checkpoint can still say the run is resumable; start a new offline mock instead of continuing that history with a real model. A real provider run whose model is named `mock` or `mock-deterministic` still resumes, including when normal mode and the real provider are split across the checkpoint and run config. A truncated same-run `run_config.json` does not hide an explicit mock manifest and is not rewritten from it. Non-string mode or model name fields do not stop dashboard status from loading. Resuming that explicit mock project without `config.yaml` explains the new offline mock instead of only reporting a missing config file. An existing conflict or path block keeps its own guidance, and a mock revealed by in-lock recovery is refused again before any provider call.
- Ignore a late same-project analytics response after a newer refresh. An older success cannot replace the newer comparison, and an older or stale error cannot clear it. Idle polls still do not reread analytics.
- Refresh an already-open dashboard after an external CLI run finishes between polls, including Research Outputs and run-comparison checkboxes. Polling still skips unchanged catalogs and does not reread output files on every tick.
- Reject an empty `--create-project` name before starting a run or writing to a project.
- Generate recovery commands for the interrupted project and workspace, preserving its provider, model and round limit. An interrupted offline mock offers a new offline mock run.
- Identify corrupt and unreadable checkpoints before checking the model provider during CLI resume.
- Explain missing or recovery-blocked outputs in the dashboard. Blocked downloads no longer save empty files, and late responses from a previous project leave the selected output alone.
- Correct the default example path in project initialization errors and the development guide.
- Run the Chromium and WebKit CI jobs on Ubuntu 24.04 for compatibility with the pinned Playwright release.

## [0.3.0] - 2026-11-09

- Group application code, dependencies, tests, prompts and documentation under `app/`; add the root `start` launcher and retain root Make targets as forwarding commands.
- Create sibling research folders from the existing dashboard selector or CLI; persist selection across restarts and share project resolution across UI/CLI.
- Load legacy `projects/<name>/` in place with deterministic legacy precedence and no automatic relocation; reject unsafe names, linked paths and occupied creation targets.
- Retain the old tracked example task through real Git upgrades; only the unused public compatibility stub yields to the top-level example.
- Keep checkpoints and artifact formats unchanged, and isolate private workspace data from Git and wheel inputs.
- Document explicit upgrade/rollback boundaries; 0.2.x does not discover new sibling projects.

[English release notes](docs/releases/0.3.0.md) · [中文更新说明](docs/releases/0.3.0.zh-CN.md)

## [0.2.2] - 2026-11-09

- Reduce the repository root from 22 to 17 tracked entries: archive historical agent records, group browser tests under `tests/`, and put dependency constraints under `scripts/dependencies/`.
- Remove the redundant `requirements.txt` shim and unused `.env.example`; document `make install-dev` and the optional legacy UI environment variable.
- Add one real dashboard screenshot per language to the concise bilingual homepages, with a compact repository navigation table.
- Update CI, wheel checks, environment fingerprints and documentation for the new locations. Preserve runtime paths, research artifacts and dependency versions.

[English release notes](docs/releases/0.2.2.md) · [中文更新说明](docs/releases/0.2.2.zh-CN.md)

## [0.2.1] - 2026-11-09
- Ask Judge to emit weighted rubric points before calculating their total, with an arithmetic example; strict score validation remains unchanged.

- Mark an attempt stopped when a stop request arrives after round creation but before Draft, keeping the checkpoint resumable without inventing a completed round.

- Pin release dependencies across supported Python variants; record installed runtime versions and optional Ollama digest, preserving initial and resumed session environments.
- Add isolated real-browser regression CI for Chromium and WebKit covering editing conflicts, background refresh, run/stop/resume, outputs and preferences.

- Validate new Judge responses against complete weighted 0–100 scoring; share the rubric across normal and diagnostic runs while retaining legacy artifact readers.
- Use the configured Ollama HTTP endpoint consistently for model discovery, startup validation, and generation.

- Input saves now check field revisions under the project lock, preserve untouched memory, and show explicit conflict choices. Both dashboard editors reject stale or running-project writes.

[English release notes](docs/releases/0.2.1.md) · [中文更新说明](docs/releases/0.2.1.zh-CN.md)

## [0.2.0] - 2026-11-09

### Repository and release management

- Split the concise project homepage into English and Chinese, with separate bilingual user and agent READMEs.
- Organize detailed references, design records, historical reports, and release notes under `docs/`; preserve runtime paths and historical evidence.
- Establish Codex coordination, independent subagent review and authorized merge, without external bot delegation.
- Align package metadata at 0.2.0 and adopt matching semantic version tags, changelog entries, and GitHub Releases.
- Add local/CI version and documentation-link checks and a PR template. Ignore local browser captures and `output/`.

### Included from the previous unreleased baseline

- Local Python dashboard with persistent navigation, language and appearance preferences, system-aware theme, output browsing, and run comparisons.
- Artifact-boundary indexing, log-tail reads, shared workspace metadata, and metric analysis performance improvements.
- Recovery and provider hardening documented in the [prior changelog](docs/archive/CHANGELOG-pre-0.2.0.md), including staged partial rounds, checkpoint-last transactions, bounded legacy migration, and credential redaction.

### Compatibility

- Research behavior, prompt semantics, runtime paths, and saved-artifact schemas are unchanged by this repository organization release.
- Source checkouts provide the dashboard; the installable Python package provides the CLI and bundled starter resources.
- No private research migration, new real-provider validation, or PyPI publication is part of this release.

[English release notes](docs/releases/0.2.0.md) · [中文更新说明](docs/releases/0.2.0.zh-CN.md)

## Earlier milestones

The original `v0.1.0-stable` and `v0.1.1-hardening` tags are retained. Their package metadata remained at 0.1.0; 0.2.0 starts consistent application versioning. See the [archived changelog](docs/archive/CHANGELOG-pre-0.2.0.md) for the complete historical record. Its `Unreleased` heading describes its original snapshot, now included in the 0.2.0 baseline.
