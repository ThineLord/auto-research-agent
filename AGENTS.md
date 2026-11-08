# Agent instructions

Read the [agent README](app/docs/agent/README.md) ([简体中文](app/docs/agent/README.zh-CN.md)) before making changes. The human entry points are [README.md](README.md) and [README.zh-CN.md](README.zh-CN.md).

## Coordination

- Codex organizes and manages repository work. Do not invoke external bots or bot bridges.
- Use subagents for independent review and, when the user has authorized merging, for the merge. The implementation agent addresses findings before the merge agent checks the exact PR head and CI.
- A subagent's review is independent analysis, not a GitHub approval by another account. Respect branch protections; never bypass a required approval.
- Infer the intended outcome, make reversible choices, and finish implementation plus proportionate validation. Ask only for material missing information or actions beyond existing authorization.

## Files and evidence

- Application internals belong under `app/`. Preserve workspace configuration, sibling research folders and legacy `projects/` data in place. Inspect an existing project before changing it; never overwrite a task, config, output, checkpoint, or private project to tidy the repository.
- Keep credentials, local configuration, generated outputs, incidental browser captures, and private research out of commits and release assets. Curated public-demo screenshots belong in `app/docs/assets/`; inspect them for private data before staging. Stage explicit paths and inspect the diff.
- Current instructions live here and in `app/docs/agent/`. `app/docs/archive/` (including `codex/`) preserve historical evidence; they do not authorize reopening old tasks, running providers, or merging changes. Keep the tested `app/docs/archive/codex/` record structure intact.
- Do not claim real-provider validation from mock tests or scientific validity from model scores. Ordinary repository checks must not call a model.

## Changes and releases

- Work on `codex/` branches from the current `origin/master`; use a draft PR for review.
- Keep English and Chinese READMEs separate and aligned. Keep the homepage short; put detail under `app/docs/`.
- Follow the [release policy](app/docs/agent/releases.md). `app/pyproject.toml` is the application version source. Every published update gets a new version, changelog entry, bilingual release notes, matching tag, and GitHub Release. Never move a published tag.
- Run `make check`; run `app/scripts/check_wheel_install.py` for packaging/version changes. Before an authorized merge, require independent review and successful CI for the exact head. Release only a reviewed commit on `master` after its CI succeeds.
- Do not weaken tests, privacy checks, branch rules, or permissions to finish a release. Report genuine blockers and unresolved limits.
