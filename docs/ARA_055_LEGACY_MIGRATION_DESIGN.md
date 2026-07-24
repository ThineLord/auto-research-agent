# ARA-055 Legacy History Migration Design

Status: package 7A read-only classifier implemented and remotely verified; discovery integration
and execution are not implemented or approved

Date: 2026-07-24

Scope: provider-free design for classifying legacy history states and, in one narrowly defined
case, creating an absent twin history from exact existing bytes

## Decision summary

Do not build a general legacy repair command.

Most historical states do not contain the before-generation, metric payload, attempt identity, or
finalization timestamp needed to reconstruct an ARA-055 transaction. Preserving those states is
safer than inferring a plausible history. In particular, canonical Markdown is not a trustworthy
source for timings, errors, score metadata, prompt-affecting state, or finalization fields.

A future implementation may offer a read-only, explicitly targeted classifier. Its only future
execution-eligibility class is `exact_missing_history_twin`:

- exactly one of project `score_history.json` and selected-run `round_metrics.json` is absent;
- the present history is a bounded JSON list with strict integer rounds `1..N`;
- `N` exactly equals the selected checkpoint's `last_completed_round`;
- its best successful score and best round agree with the checkpoint;
- present run-local metadata does not contradict the checkpoint or history;
- no round, run-finalize, or diagnostic-finalize journal is present;
- no current-round canonical/attempt state is pending or ambiguous;
- the source is a safe regular single-link file and the target leaf is safely absent.

Execution, if separately approved, copies the source bytes exactly into the absent fixed target
using create-only publication. It does not rewrite the source, checkpoint, canonical output,
summary, config, memory, research state, or best output. An owner-selected restricted evidence
bundle must be durably created first, and an immutable project-local transaction record makes an
interrupted target creation idempotently roll-forward.

All other states are either already supported without migration or are non-migratable. They remain
byte-identical and receive a fixed reason code. There is no quarantine, cleanup, normalization,
history synthesis, or automatic rollback.

## Authorization boundary

The owner subsequently approved package 7A only. Package 7A adds a provider-free internal,
explicitly targeted classifier plus strict machine and human report builders. It does not expose
the classifier through CLI, doctor, UI, or automatic startup paths.

Package 7A does not:

- scan for projects/runs or inspect any unselected checkpoint, history, log, or provider artifact;
- add a discovery command, migration command, journal, receipt, or runtime path;
- copy, rewrite, move, quarantine, delete, or create a historical artifact;
- change a schema, dependency, configuration default, provider, score, prompt, metric, or result;
- authorize package 7B integration, package 7C execution, or package 7D rollback.

Approval of read-only classification must not be interpreted as approval to create a target
history. Every later package retains its separate approval boundary.

## Current compatibility behavior

### History loading

`src.runner._load_resume_histories()` currently:

- validates each present history and rejects duplicate/future rounds;
- requires paired histories to have the same round sequence and equal overlapping values;
- creates an in-memory fallback from the present history when the other history is absent;
- calls a retained history complete only when its rounds cover `1..N`, where
  `N = start_round - 1`;
- requires a complete single-side history's best score to match the checkpoint;
- permits a partial single-side history only when it does not exceed the checkpoint best and the
  remaining best-score authorities are consistent;
- does not write the absent history while loading.

A resumed legacy run uses the older direct multi-file writer unless both histories genuinely
exist and both use strict integer rounds `1..N`. A complete single-history fallback can therefore
produce one more round through the legacy writer and switch the following round to ARA-055. A
partial/non-consecutive history cannot become complete merely by appending later rounds and can
remain on the compatibility path.

That behavior is historical compatibility, not proof that missing entries can be reconstructed.
The migration design must not reinterpret tolerant loading as authority to synthesize bytes.

### Canonical and attempt classification

The ARA-054 classifier currently distinguishes:

- an absent canonical round with no attempt as `new_round`;
- an empty reserved canonical directory as `legacy_empty_canonical`;
- a nonempty canonical directory with no attempt as `legacy_partial` and
  `explicit_migration_required`;
- a verified published attempt whose checkpoint has not committed the round as
  `published_uncommitted`;
- ready, stopped, active, unverifiable, and canonical/attempt-conflict states.

`legacy_partial` names an owner-intervention boundary; it is not evidence that safe automatic
migration is possible. A journal-less `published_uncommitted` attempt verifies canonical agent
outputs, but its manifest does not contain the complete round metric, both history
before-generations, memory/research-state after-images, or checkpoint after-image needed by the
ARA-055 engine.

### Finalization and diagnostic recovery

New iterative finalization and diagnostic finalization use their own fixed create-only
transactions. A valid pending transaction is recoverable and is not legacy migration. Without
such a transaction, stale summary/config/checkpoint or diagnostic split generations lack exact
after-images and a common trusted finalization identity; they cannot be recreated from timestamps
or nearby files.

`run_manifest.json` remains a read-only fallback when `run_config.json` is absent. Its legacy
support does not make it a source for creating run configuration or history artifacts.

## Terms

| Term | Meaning |
| --- | --- |
| committed | checkpoint and all required current transaction artifacts already verify |
| compatible legacy | current readers can safely preserve/read or resume the state without writing a migration |
| eligible candidate | all exact-copy preconditions hold, but no write is authorized |
| pending current transaction | a valid ARA-055 journal exists and current recovery owns the state |
| ambiguous | two or more plausible generations or an uncorrelated authority exist |
| unsafe | path, type, link, size, encoding, JSON, identity, or bound validation fails |
| non-migratable | evidence is insufficient for a no-inference transformation |

“Non-migratable” does not mean corrupt or deletable. It means preserve the bytes and require an
owner-led forensic decision outside automatic migration.

## Legacy state decision matrix

| ID | Observed fixed state | Classification | Future handling |
| --- | --- | --- | --- |
| L00 | valid round/finalize/diagnostic journal present | `current_transaction_pending` | use existing recovery; no migration |
| L01 | paired, equal, strict `1..N` histories matching checkpoint | `already_transaction_eligible` | none |
| L02 | one history absent; present history and authorities satisfy every exact-copy rule | `exact_missing_history_twin` | dry-run eligible; execution separately approved |
| L03 | one history absent; present history is partial, sparse, non-integer, or non-consecutive | `incomplete_history_evidence` | preserve; never fill gaps |
| L04 | paired histories have different round sequences | `history_sequence_conflict` | preserve and fail closed |
| L05 | paired histories disagree on an overlapping field | `history_value_conflict` | preserve and fail closed |
| L06 | either history extends beyond checkpoint | `history_ahead_of_checkpoint` | preserve and fail closed |
| L07 | complete present history best does not match checkpoint | `history_checkpoint_conflict` | preserve and fail closed |
| L08 | partial history has absent/conflicting best authorities | `partial_history_uncorrelated` | preserve and fail closed |
| L09 | verified published attempt/canonical exists without round journal | `journal_less_published_round` | preserve and block; do not synthesize metric |
| L10 | nonempty canonical exists without attempt manifest | `canonical_without_provenance` | preserve and block |
| L11 | empty canonical reservation with no conflicting attempt | `supported_empty_canonical` | current ARA-054 path; no migration |
| L12 | ready/active/stopped attempt exists | `attempt_state_owned` | current ARA-054 behavior; no migration |
| L13 | attempt or canonical hashes/shape do not verify | `attempt_evidence_conflict` | preserve and fail closed |
| L14 | summary/config/checkpoint are stale without finalize journal | `journal_less_finalize_split` | preserve; no timestamp/status inference |
| L15 | diagnostic histories/metadata are split without diagnostic journal | `journal_less_diagnostic_split` | preserve; no diagnostic identity inference |
| L16 | only legacy `run_manifest.json` exists | `legacy_manifest_compatible` | read-only fallback; do not create config |
| L17 | unsafe path, symlink, hard link, special file, changed anchor, or unsafe permissions | `unsafe_storage_identity` | no content read or write |
| L18 | malformed, oversized, deeply nested, duplicate-key, or otherwise unsafe JSON | `unsafe_serialization` | preserve and fail closed |
| L19 | unknown/new journal or artifact version | `unknown_schema` | preserve and fail closed |
| L20 | no selected checkpoint/run identity | `run_identity_unavailable` | report only; do not guess a run |

The classifier evaluates safety and pending current transactions before compatibility or
eligibility. The first fail-closed class wins, so an unsafe leaf cannot be reported as an eligible
missing twin based on a different file.

## Exact missing-history-twin eligibility

Eligibility is deliberately narrower than the current tolerant resume loader. Every condition
below is mandatory.

### Fixed identity

1. The caller explicitly selects one trusted project. Discovery does not recursively scan all
   projects.
2. A safe project checkpoint selects one run root under the registered internal or configured
   external runs anchor.
3. The normalized run basename, checkpoint `run_id`, and any present run-config/summary ID agree.
4. `last_completed_round` is a strict integer `N >= 1`.
5. The current round `N + 1` has no pending, published, partial, or conflicting canonical/attempt
   state.

### Fixed history

1. Exactly one fixed history leaf exists and the other fixed leaf is absent.
2. The source is a regular, non-symlink, single-link file within the existing size/depth limits.
3. It decodes as a JSON list without duplicate keys or non-finite values.
4. It contains exactly `N` entries whose `round` fields are strict integers `1..N`.
5. Every entry is accepted by the current history and transaction resource constraints.
6. The source's best successful numeric score matches checkpoint `best_score` within the current
   `0.005` absolute tolerance.
7. The selected best round agrees with a valid checkpoint best-round identity when supplied.
8. Present run summary/config best, round-count, or completion fields do not contradict the source
   or checkpoint. Missing optional legacy fields are tolerated; conflicting fields are not.

### No other owner

1. No round, run-finalize, or diagnostic-finalize transaction exists.
2. No project/run lock is live. A future classifier may report `busy` without opening artifacts
   beyond the fixed lock metadata needed for that determination.
3. No journal-less published round, canonical partial, or unverifiable attempt exists at the next
   round.
4. The target remains absent after its parent and leaf identities are revalidated.

If any condition changes between classification and execution, execution reclassifies and exits
without creating the target or evidence claiming success.

## Read-only discovery contract

The package 7A discovery API is a pure, explicitly targeted operation:

- one project per invocation;
- no provider/client construction, network access, retry loop, or artifact mutation;
- cooperative lock awareness, but no stale-lock deletion;
- fixed allowlisted leaves only;
- bounded no-follow reads through registered anchors;
- no recursive canonical-output or log traversal;
- no implicit migration after a successful dry run.

Its machine result uses this strict additive schema:

```json
{
  "schema_version": 1,
  "operation": "legacy_history_migration_discovery",
  "status": "eligible_candidate",
  "classification": "exact_missing_history_twin",
  "run_id": "bounded-public-id",
  "completed_rounds": 2,
  "source_artifact": "score_history",
  "target_artifact": "round_metrics",
  "source_sha256": "64-lowercase-hex",
  "source_size": 1234,
  "reason_codes": [],
  "execution_authorized": false
}
```

For a refusal, `status` is `not_migratable`, the classification is one of the fixed table values,
and `reason_codes` contains bounded enums only. Human output uses logical artifact labels and
bounded IDs; it must not include private absolute paths, file contents, exception graphs, prompts,
provider responses, environment values, or credentials.

`classify_legacy_history_migration(project_dir)` returns the path-redacted inspection,
`build_legacy_migration_report(inspection)` returns the fixed JSON-compatible object, and
`format_legacy_migration_report(inspection)` returns bounded human text. These functions are
internal APIs in package 7A; no command or automatic caller is added.

Discovery success means only that the snapshot was classifiable. It must not describe a
non-migratable result as command failure, corruption, or safe-to-delete evidence. A future CLI can
reserve a distinct nonzero status for unsafe/unreadable input, but the exact CLI surface and exit
contract belong to the separately approved discovery package.

## Evidence and provenance bundle

Execution must require an explicit owner-selected evidence destination. There is no automatic
upload and no hidden global default.

Before creating a project transaction or target history, execution creates a new no-replace,
owner-only directory and durably writes:

- a strict manifest with tool/package version, migration ID, UTC time, classification and reason;
- logical project/run identities without private absolute paths;
- source artifact label, exact source bytes, SHA-256, byte length, and safe mode facts;
- checkpoint digest, byte length, and only the bounded normalized fields used for correlation;
- digests, byte lengths, and bounded correlation fields for any present fixed run config and run
  summary;
- an inventory proving the target was absent and all three current transaction leaves were absent;
- the proposed target label and digest, which equal the source digest;
- the exact approval/execution mode, never a credential or environment snapshot.

Only the selected source history is copied verbatim. Checkpoint/config/summary correlation evidence
uses digests and bounded validated fields, not raw copies that could unnecessarily reproduce
private paths or unknown legacy extensions. Canonical Markdown, logs, prompts, provider payloads,
memory, best output, research state, unrelated runs, and environment data are excluded. The source
history itself is treated as sensitive and is never rendered. Bundle files use restrictive
permissions, bounded sizes, no links, fixed names, and create-only publication. A partially
created bundle is not execution evidence and cannot authorize a project write.

The final receipt is written into that same bundle only after the target and its digest verify.
It records whether recovery, rather than the original process, completed publication. Evidence
retention and deletion remain an owner policy; the tool never cleans a bundle automatically.

## Future execution transaction

If execution is separately approved, use one fixed project-local
`.legacy_history_migration_transaction.json`. Adding this leaf to repository safety inventories
and reader/entry guards is part of implementation, not this design.

The strict create-only transaction contains only:

- schema/kind/state and bounded migration ID;
- selected run ID and validated run-root identity;
- source/target artifact enums;
- source and target-expectation SHA-256 plus byte length;
- checkpoint and optional correlation-metadata digests;
- evidence-bundle manifest digest;
- proof that the target was absent at preparation.

It does not contain arbitrary writable paths or unbounded artifact contents. The source is the
only target after-image and is reread through its fixed trusted anchor.

Apply order:

1. re-acquire the existing project lock;
2. reclassify all eligibility conditions;
3. verify the already-durable evidence bundle manifest;
4. create the immutable project transaction with no replacement;
5. revalidate the source digest and target absence;
6. create the target from exact source bytes with a no-replace primitive;
7. fsync and verify target bytes/digest through the trusted anchor;
8. write the final receipt into the evidence bundle;
9. remove the project transaction only if its exact generation still matches.

An interruption before step 4 leaves only an incomplete/no-op evidence destination. An interruption
after step 4 is recoverable: entry and explicit recovery detect the fixed transaction, accept only
target-absent or exact-target generations, and roll forward without a provider call. A different
target generation or changed source/checkpoint becomes a conflict and is never overwritten.

The migration does not update checkpoint, histories other than the missing twin, config, summary,
canonical output, prompts, or project views. The next normal resume may then recognize the
pre-existing strict pair and use ARA-055 for future rounds.

## Rollback policy

Automatic recovery is roll-forward only. It never deletes a created history.

A future explicit rollback, if separately designed and approved, may remove only the newly created
target when all of these still hold:

- the migration receipt and evidence bundle verify;
- the target digest equals the recorded source/target digest;
- the original source and checkpoint digests are unchanged;
- no later round, journal, attempt, finalization, or dependent project mutation exists;
- the target was recorded as absent before migration;
- the owner explicitly selects this migration ID.

Any uncertainty blocks rollback. The evidence bundle is retained. Existing source artifacts are
never rollback targets. This narrow delete-only reversal is not implemented or authorized by the
package 7 design.

## Idempotency and concurrency

- Discovery is read-only and repeatable; results describe a snapshot, not a durable authorization.
- Evidence and transaction IDs use bounded random identifiers and no-replace creation.
- A live project lock returns `busy`; discovery/execution does not steal or delete it.
- A pending migration transaction blocks new runs, resume, diagnostic, analytics publication, and
  other finalization recovery until reconciled.
- Recovery accepts only source/checkpoint generations recorded by the transaction and target
  absence or exact target bytes.
- Repeated recovery after success reports no pending transaction and the existing paired histories;
  it never creates a second target or bundle.
- Two concurrent executions cannot both create the fixed transaction or absent target.
- Unknown transaction schema or third-generation bytes preserve all files and fail closed.

## Security and privacy requirements

- Reuse the registered project and configured run-storage anchors; never trust a checkpoint string
  as a writable path.
- Reject symlinks, hard links, special files, unsafe parent identity, changed configured storage,
  malformed UTF-8/JSON, duplicate keys, non-finite values, and excessive size/depth.
- Use fixed artifact enums and fixed bundle leaf names; never join journal-supplied arbitrary
  paths.
- Revalidate source and target descriptors before and after publication.
- Redact private paths and raw values from console, JSON diagnostics, exceptions, and receipts.
- Keep bundles local, owner-only, bounded, and excluded from automatic Git staging.
- Never include credentials, environment snapshots, provider bodies, raw prompts, model outputs,
  logs, or unrelated canonical artifacts.
- Perform no provider or network call and no unbounded retry.
- Preserve the existing documented boundary that cooperative locking and descriptor-relative I/O
  are not a hostile same-UID sandbox.

## Compatibility guarantees

### Preserved

- all existing artifact bytes until separately approved execution;
- paired histories and current ARA-055 transactions;
- tolerant read-only support for partial, string-round, sparse, and older metadata;
- canonical round and attempt classifications;
- legacy run-manifest fallback;
- configured external run storage;
- prompts, scores, metrics, stop rules, provider order/calls, and experiment interpretation.

### Deliberately not normalized

- string round identifiers;
- partial or non-consecutive histories;
- missing historical rounds or fields;
- divergent paired histories;
- canonical partials and journal-less published attempts;
- stale journal-less finalization or diagnostic metadata;
- unknown/manual artifact edits.

These states may continue to use existing compatibility readers or remain blocked. Migration must
not turn tolerance into fabricated provenance.

## Options considered

| Option | Result | Decision |
| --- | --- | --- |
| synthesize metrics from canonical Judge Markdown | loses timing/error/before-generation provenance | reject |
| choose the longer of two conflicting histories | can promote an uncommitted generation | reject |
| fill missing rounds with placeholders | changes research interpretation and aggregate metrics | reject |
| normalize all legacy JSON formatting/types | rewrites evidence without functional need | reject |
| adopt journal-less `published_uncommitted` attempt | missing metric and prompt-state transaction payload | reject |
| reconstruct stale finalization from current clock/files | invents timestamps, runtime, status, or resume metadata | reject |
| copy exact complete source bytes into an absent twin | bounded and deterministic under strict correlation | select as sole candidate |
| automatically roll back or quarantine ambiguous files | destructive and can erase user/research evidence | reject |
| leave all legacy states unchanged forever | safest default; unnecessarily retains one deterministic missing-twin gap | default, with optional exact-copy candidate |

## Approval-gated packages and status

### 7A - Read-only classifier and report schema

Status: implemented and remotely verified as an internal API under the package 7A approval.

- Fixed state/reason enums and explicitly targeted inspection are implemented.
- No-follow/bounded safety validation and path-redacted human/JSON output are implemented.
- No `--execute`, journal writes, bundle writes, artifact creation, or integration caller exists.
- Synthetic tests cover every L00-L20 row in internal and configured-external storage.

### 7B - Discovery integration and reader guard design verification

Status: not implemented or approved.

- Expose the read-only result through an owner-approved doctor/preview surface.
- Prove no provider construction, lock theft, scan-all behavior, or mutation.
- Re-audit entry/readers for the future fixed migration transaction.
- Still no execution path.

### 7C - Exact missing-twin execution

Status: not implemented or approved.

- Requires a new explicit implementation approval after 7A/7B are remotely verified.
- Add restricted evidence-bundle creation, strict fixed journal codec, create-only exact-byte
  publication, lock-held recovery, and reader/entry guards.
- Support only `exact_missing_history_twin`; every other class remains report-only.
- Do not implement rollback, bulk discovery, partial repair, or canonical adoption.

### 7D - Explicit rollback, only if a real need is demonstrated

Status: not implemented or approved.

- Requires a separate destructive-operation approval and a new threat-model review.
- May remove only the exact created twin under the rollback conditions above.
- Never delete a source, ambiguous artifact, canonical output, or evidence bundle.

No package is implicitly approved by this design.

## Validation plan

### Classifier matrix

- every L00-L20 row in internal and configured-external run storage;
- source on either history side;
- strict `1..N`, missing, empty, partial, sparse, string, duplicate, future, and conflicting rounds;
- best-score tolerance boundaries and conflicting/missing authorities;
- absent, matching, and conflicting optional summary/config metadata;
- every attempt/canonical classification;
- pending/invalid/unknown round, finalization, diagnostic, and future migration journals.

### Safety matrix

- symlink, hard link, special file, unsafe permissions, changed anchor/storage identity;
- malformed UTF-8/JSON, duplicate keys, non-finite values, deep/large files;
- private paths or raw values in nested exceptions;
- live/stale/malformed locks without deletion;
- evidence destination links, collisions, partial creation, and permission failure.

### Execution/recovery matrix

- source is project history and target is run metrics, and the reverse;
- internal/configured-external storage;
- `OSError` and `KeyboardInterrupt` before/after every bundle, journal, target, receipt, and cleanup
  boundary;
- target absent, exact, or third generation;
- source/checkpoint/config/summary changed after dry run, preparation, or target creation;
- repeated recovery and concurrent execution;
- proof that all non-target project/run artifacts remain byte-identical.

### Regression layers

1. classifier/codec/evidence unit tests;
2. resume-history and ARA-054 attempt tests;
3. round, run-finalization, and diagnostic transaction suites;
4. runner, preview, analytics, compare, report, UI, storage, and CLI suites;
5. `make check`, staged repository-safety scan, and isolated-wheel smoke;
6. Python 3.10 and 3.13 push/PR CI.

No provider smoke or historical artifact execution is required to validate the implementation.
