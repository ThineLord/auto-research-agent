## Change

Describe the problem and resulting behavior. Link the relevant version notes for a release PR.

## Validation

Record checks actually run and material limitations. Do not infer real-provider validation from mock tests.

## Review and version

- [ ] English and Chinese user/agent documentation updated where relevant
- [ ] `make check` passed; isolated wheel smoke passed for packaging/version changes
- [ ] Independent subagent review completed for the final head; findings resolved
- [ ] Release version, changelog, and bilingual notes aligned if publishing an update

The authorized merge subagent verifies the exact reviewed head and CI before merging. Published releases follow `docs/agent/releases.md`.
