# Version and release policy

[English](releases.md) · [简体中文](releases.zh-CN.md)

`pyproject.toml` is the application version source. Starting with **0.2.0**, every published update uses the same `MAJOR.MINOR.PATCH` in package metadata, both home READMEs, `CHANGELOG.md`, bilingual release notes, a `vMAJOR.MINOR.PATCH` Git tag, and a GitHub Release. A merged development commit is not automatically a published release.

## Choose a version

- **Patch:** compatible bug fixes, documentation corrections, or maintenance releases.
- **Minor:** compatible additions or a substantial new release baseline, such as 0.2.0's dashboard and repository organization.
- **Major:** incompatible changes once 1.0 is established. While below 1.0, document incompatible changes prominently in a new minor release and supply migration instructions.

Never reuse or move a published tag. Preserve `v0.1.0-stable` and `v0.1.1-hardening` as historical milestone identifiers; the old package version stayed at 0.1.0. Version 0.2.0 establishes consistent naming without rewriting that history. Artifact schemas and checkpoints have their own compatibility contracts; an application version bump does not authorize a data migration.

## Prepare a release PR

1. Branch from current `origin/master` and inspect unreleased changes and existing tags/releases.
2. Update `pyproject.toml`, both root READMEs, relevant bilingual guides, `CHANGELOG.md`, and `docs/releases/<version>.md` plus `<version>.zh-CN.md`. Keep an `Unreleased` section for later work.
3. Describe what changed, upgrade steps, unchanged or changed data contracts, verification, and unresolved limits. Never invent provider validation.
4. Run `make check` and the isolated wheel smoke. `make release-check` validates the local version markers, bilingual release-note files, changelog entry, and relative Markdown file links outside historical archives. It does not verify remote tags, CI, or GitHub approvals.
5. Open a draft PR. Complete independent subagent review and successful CI for the final head, then have the authorized merge subagent merge that exact head.

## Publish the merged version

After the merged commit's CI succeeds, fetch `origin`, verify the intended commit is on `master`, and ensure the version's tag/release does not already exist. Read the actual repository version; the placeholders below must be replaced with the reviewed version and merge SHA.

```bash
git tag -a v<VERSION> <MERGE_SHA> -m "Auto Research Agent <VERSION>"
git push origin refs/tags/v<VERSION>
gh release create v<VERSION> --verify-tag --title "Auto Research Agent <VERSION>" --notes-file <RELEASE_BODY_FILE> --latest
```

Run `python scripts/check_release.py --tag v<VERSION>` on that commit before publishing. Prepare the release body from the committed bilingual notes, using absolute GitHub links because relative file links in a Release body do not resolve like repository links. State validation results with the tested SHA. GitHub's source archives are sufficient for a source release; do not attach a directory archive containing ignored local files. PyPI publication is a separate action and is not part of this workflow.

Read back the published release, tag target, and version. If publication fails after tag creation, inspect the existing tag before retrying; never force-update it. Correct a published defect in a new patch release. Keep all unrelated branches and local research intact.
