# Changelog

## Unreleased

## [0.3.1] - 2026-11-26

- Launch from the requested workspace even when its path is relative. Root Make targets still execute when a project directory has the same name.
- Select a supported Python for new environments and use the selected virtual environment for both installation and startup. Setup checks pip’s effective configuration for redirected installs and prints a working recovery command for an environment missing pip.
- Show live CLI runs on Linux and macOS. A dashboard stop belongs to the selected run, including during preflight and finalization. Unrelated read-only requests can proceed concurrently.
- Reject empty project names and report damaged checkpoints before provider preflight. Recovery commands preserve the interrupted run’s workspace, project, provider, model and round limit. Interrupted offline mocks offer a fresh offline run.
- Refresh saved outputs, downloads and run comparisons when an external CLI run finishes. A delayed response cannot replace newer results. The dashboard explains blocked or missing downloads.
- Keep generated surveys out of subsequent inputs, preserve user Markdown and distinguish source paths in flat and legacy projects.
- Exclude failed scores from ranking, averages and trends. Valid zero scores and historical finite negative scores retain their meaning.
- Make concurrent lock-test reporting deterministic. Browser CI uses Ubuntu 24.04 with the pinned Playwright release. Project initialization errors and the development guide use the current example path.

[English release notes](docs/releases/0.3.1.md) · [中文更新说明](docs/releases/0.3.1.zh-CN.md)

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
