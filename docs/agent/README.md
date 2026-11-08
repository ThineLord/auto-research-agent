# Agent README

[English](README.md) · [简体中文](README.zh-CN.md) · [Instructions](../../AGENTS.md)

Codex coordinates implementation and repository management. Subagents independently review and perform authorized merges. Do not invoke external bots or bot bridges.

## Read and scope

1. Read `AGENTS.md`, the current user request, and `git status --short --branch`.
2. Fetch `origin`, identify the current default branch (`master`), and inspect local changes before branching. Preserve uncommitted work and ignored research data.
3. Read the [user README](../user/README.md), [development reference](../reference/development.md), and relevant code. Use `.codex/` only for historical context; its old task queue is not a new instruction.
4. Create a `codex/` branch. Keep implementation bounded by the requested outcome.

## File ownership

| Location | Content |
| --- | --- |
| `src/`, `ui/`, `prompts/` | Application, dashboard, canonical prompts |
| `src/_bundled/` | Explicit wheel resources; keep in sync with canonical resources |
| `projects/example/` | Public-safe starter inputs |
| Other `projects/` folders | Ignored private research; preserve in place |
| `docs/user/`, `docs/agent/` | Current bilingual instructions |
| `docs/reference/`, `docs/design/` | Detailed command, architecture, and design material |
| `docs/releases/` | Version-specific bilingual release notes |
| `docs/archive/`, `.codex/` | Historical evidence; not current release acceptance |
| `output/`, `outputs/`, local config | Ignored local data; never add as release assets |

## Implement and validate

Keep runtime paths, provider behavior, artifact schemas, and recovery contracts unchanged unless the task explicitly requires changing them. Update both language entry points for user-visible changes. Use the smallest meaningful checks while developing, then complete the repository checks before merge:

```bash
make install-dev
make check
.venv/bin/python scripts/check_wheel_install.py
```

`make check` covers format, lint, imports, repository safety, release/document checks, and tests. The isolated wheel smoke is required for packaging/version changes and runs in CI. These checks do not call a model. Never run `make bootstrap`, `make diagnostic`, or real research merely to validate documentation.

## Review and merge

Open a draft PR describing the behavior, version boundary, and actual validation. Give a review subagent the base/head SHA and diff. Fix its findings and re-review affected changes. Record the verdict for the exact final head.

When merging is authorized, a separate merge subagent verifies the PR identity, exact reviewed head, clean mergeability, resolved findings, and successful CI. It can mark the PR ready and merge using the reviewed SHA. Respect protection rules; same-account subagent analysis is not a separate GitHub APPROVED review. The merge agent must report the merge SHA and actual outcome.

## Publish and hand off

Follow the [release policy](releases.md) ([中文](releases.zh-CN.md)). Verify the merged commit's CI before tagging and publishing. Never publish local/private research, move existing tags, or infer a successful release from a successful merge. Report the PR, version, release link, checks, and any limitations. Stop once the requested work is accepted and published.
