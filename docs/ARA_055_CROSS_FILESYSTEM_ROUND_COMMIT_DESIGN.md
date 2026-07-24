# ARA-055 Cross-Filesystem Round Commit Design

Status: design complete; implementation packages 1-6 are complete; package 7 execution is not
approved

Date: 2026-07-23

Scope: provider-free transaction and recovery design for future iterative rounds

## Decision summary

Use one immutable, project-local write-ahead journal to make each future round commit
deterministically roll-forward across the project filesystem and a possibly different run-storage
filesystem.

The journal is prepared before a completed attempt becomes publishable. It binds one verified
attempt, one canonical round, the exact new metric, the before/after hashes of both histories, and
the bounded after-images needed for project state. Once it exists, recovery accepts each mutable
artifact only in its recorded before or after generation. Missing after-images are applied with the
existing single-file atomic writer; unknown generations fail closed.

The checkpoint advances last and is the round's visibility/commit point. Canonical output and any
earlier mutable writes are not independently proof of a committed round. Journal removal happens
only after every after-image and the advanced checkpoint verify.

Do not attempt a cross-filesystem rename, directory swap, rollback of canonical output, or
best-effort inference from mismatched histories. Those approaches either do not work across the
supported configured `runs/` storage link or would destroy/guess at evidence.

Run finalization is a second transaction phase. Its exact `run_summary.json` and finalized
`run_config.json` are applied before the final project checkpoint. This prevents a final
`can_resume=false` checkpoint from becoming authoritative while the run-local read models are
still stale.

## Authorization boundary

The owner approved this design stage only.

This document and its provider-free temporary characterization do not:

- add a journal or recovery implementation;
- change an artifact schema or existing canonical artifact;
- migrate a historical `published_uncommitted` round;
- change providers, prompts, scores, metrics, stop rules, or experiment interpretation;
- add dependencies or call a provider;
- inspect or mutate ignored runtime data.

Every implementation package near the end of this document requires separate approval.

## Confirmed current behavior

### Current write order

For a successful iterative round, `src/runner.py` currently performs these externally visible
operations in order:

1. mark the attempt `ready_to_publish`;
2. publish its output as canonical `round_NN`;
3. mark the attempt `published`;
4. parse the Judge output and build the round metric;
5. replace `best_output.md` when the round improves;
6. replace project-global `score_history.json`;
7. replace run-local `round_metrics.json`;
8. replace project-global `memory.md`;
9. replace project-global `research_state.json`;
10. replace project-global `checkpoint.json`;
11. evaluate stop conditions;
12. replace the final checkpoint;
13. replace run-local `run_summary.json`;
14. replace run-local `run_config.json`.

Each file replacement is atomic only within that file's own parent filesystem. There is no
transaction spanning the sequence.

The configured `project/runs` path may be a supported storage symlink. `make_run_root()` then
creates the run beneath the resolved configured storage, so project-global and run-local files may
have different devices and different failure behavior.

### Readers and authorities

| Artifact | Location | Current writers | Important readers/authority |
| --- | --- | --- | --- |
| `round_NN/*` | run-local | iterative runner, diagnostic | resume context; human evidence |
| attempt manifest | run-local | iterative runner | shared partial-round classifier |
| `score_history.json` | project-global | iterative runner, diagnostic | UI history; resume fallback |
| `round_metrics.json` | run-local | iterative runner, diagnostic | resume history; analytics; compare |
| `best_output.md` | project-global | iterative runner | next-round prompt; session report |
| `memory.md` | project-global | iterative runner | next-round prompts |
| `research_state.json` | project-global | iterative runner | session report |
| `checkpoint.json` | project-global | iterative runner, diagnostic | resume authority and selected run |
| `run_summary.json` | run-local | iterative runner, diagnostic | analytics, compare, UI/reporting |
| `run_config.json` | run-local | iterative runner, diagnostic | provenance, resume, reporting |

`_load_resume_histories()` correctly rejects different round sequences or overlapping fields with
different values. It has a compatibility fallback when one history is absent, but it cannot safely
repair a split generation in which the present history has advanced beyond the checkpoint.

The ARA-054 classifier correctly calls a canonical round with a verified `published` attempt
`published_uncommitted` when the checkpoint still identifies that round as pending. It blocks a
duplicate attempt, but ARA-054 intentionally has no cross-file recovery payload.

### Provider-free fault characterization

The characterization used synthetic agents and temporary directories only. It covered:

- internal and configured external run storage;
- `OSError` and `KeyboardInterrupt`;
- every current post-publication mutable-write boundary;
- a previously committed round 1 followed by a failing round 2.

For all four combinations of storage layout and fault type, failure before the second history write
produced the same state:

- canonical `round_02` exists and matches the attempt;
- the attempt state is `published`;
- `score_history.json` contains rounds `[1, 2]`;
- `round_metrics.json` contains round `[1]`;
- checkpoint bytes are unchanged and `last_completed_round=1`;
- the shared classifier and resume preview both report `published_uncommitted`;
- resume is blocked, so retry cannot create a duplicate round;
- no current automatic path can finish the commit.

The complete pre-write matrix below was identical across all four storage/fault variants:

| Injected before | Best output has round 2 | Score rounds | Metric rounds | Memory has round 2 | Research-state round | Checkpoint round | Resume result |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| `best_output.md` | no | `[1]` | `[1]` | no | 1 | 1 | blocked |
| `score_history.json` | yes | `[1]` | `[1]` | no | 1 | 1 | blocked |
| `round_metrics.json` | yes | `[1,2]` | `[1]` | no | 1 | 1 | blocked |
| `memory.md` | yes | `[1,2]` | `[1,2]` | no | 1 | 1 | blocked |
| `research_state.json` | yes | `[1,2]` | `[1,2]` | yes | 1 | 1 | blocked |
| per-round checkpoint | yes | `[1,2]` | `[1,2]` | yes | 2 | 1 | blocked |
| first operation after checkpoint | yes | `[1,2]` | `[1,2]` | yes | 2 | 2 | next round allowed |

The last row is a valid round commit, but the previous run summary remains at round 1 and the
resume-startup run config remains `status=running`. Thus the resume path can continue, while
analytics or provenance readers can observe stale finalization state.

Failures in the current final checkpoint, run-summary, and run-config sequence additionally show
why finalization needs its own journal:

- failure before the final checkpoint leaves the per-round resumable checkpoint;
- failure before run summary leaves a final non-resumable checkpoint with the old summary;
- failure before final run config leaves the new summary with a still-running run config.

## Root causes

There are three separate authority boundaries but no commit record connecting them:

1. canonical output proves four verified agent outputs;
2. both histories prove the metric generation used by resume and reports;
3. checkpoint proves which round the project advertises as complete.

The mutable project views (`best_output.md`, `memory.md`, and `research_state.json`) affect later
prompts and reports, so treating them as harmless afterthoughts also changes resumed behavior.

Reversing the two history writes does not solve the problem. It merely changes which filesystem is
ahead after interruption. A cross-filesystem atomic rename is unavailable by definition.

Rollback is not a safe general solution:

- canonical publication is deliberately no-replace and evidence-preserving;
- a process may stop after either history becomes externally visible;
- a user may edit `memory.md` between interruption and recovery;
- restoring an old project-global file can erase later human work.

## Required invariants

An implementation must preserve all of the following:

1. A canonical round remains immutable, agent-complete evidence in the existing directory format.
2. A journal exists before the attempt can transition to `ready_to_publish`.
3. A round metric is appended exactly once to each history.
4. The project checkpoint never advances before both histories and all prompt-affecting project
   views match the transaction after-generation.
5. Recovery is idempotent and makes no provider calls.
6. Recovery never assumes project and run paths share a filesystem.
7. Recovery accepts only a recorded before hash or after hash for every mutable artifact.
8. Any unknown hash, path, identity, schema, attempt, canonical tree, or journal state fails closed
   without changing another artifact.
9. A pending journal prevents a new round, another run, analytics publication, and journal
   replacement until it is recovered or explicitly inspected.
10. Existing history, checkpoint, canonical-output, summary, and config formats stay readable.
11. Historical ambiguous or journal-less `published_uncommitted` evidence is not auto-migrated.
12. A normal successful round produces the same score, metric, canonical output, prompts, and
   default user-facing artifacts as before.
13. No secret, environment snapshot, raw credential, or unbounded model text enters the journal.
14. Journal resource use is explicitly bounded.

## Selected transaction layout

Use one fixed project-local file for an in-flight round:

```text
projects/<project>/
  .round_commit_transaction.json
  checkpoint.json
  score_history.json
  best_output.md
  memory.md
  research_state.json
  runs -> <optional configured storage>
```

The fixed project location is discoverable even for round 1 before a checkpoint exists. Only one
run may own it, matching the existing project/run lock model. The record contains a validated
`run_id` and run-root identity, but recovery derives all leaf names from a fixed allowlist rather
than treating journal strings as writable paths.

Use a separate fixed project-local `.run_finalize_transaction.json` only after no round transaction
is pending. The two records must never coexist.

### Round journal schema

The schema should be strict, versioned, and additive to existing artifacts:

```json
{
  "schema_version": 1,
  "kind": "round_commit",
  "state": "prepared",
  "transaction_id": "<restricted opaque id>",
  "run_id": "<canonical run directory name>",
  "run_root": "<validated canonical run-root text>",
  "run_root_identity": {
    "configured_storage": true,
    "device": 123,
    "inode": 456,
    "stat_identity_available": true
  },
  "round": 2,
  "attempt_id": "<validated attempt id>",
  "run_config_sha256": "<64 lowercase hex>",
  "round_metric": {"round": 2},
  "artifacts": {
    "score_history": {
      "before_present": true,
      "before_sha256": "<hex>",
      "after_sha256": "<hex>"
    },
    "round_metrics": {
      "before_present": true,
      "before_sha256": "<hex>",
      "after_sha256": "<hex>"
    },
    "best_output": {
      "write": true,
      "before_present": true,
      "before_sha256": "<hex>",
      "after_sha256": "<hex>"
    },
    "memory": {
      "before_sha256": "<hex>",
      "after_sha256": "<hex>",
      "after_text": "<bounded exact text>"
    },
    "research_state": {
      "before_sha256": "<hex>",
      "after_sha256": "<hex>",
      "after_value": {}
    },
    "checkpoint": {
      "before_present": true,
      "before_sha256": "<hex>",
      "after_sha256": "<hex>",
      "after_value": {}
    }
  }
}
```

This is a design shape, not a committed public schema.

The journal stores one metric delta, not two complete history copies. At preparation time, the
runner serializes each complete after-history using the existing formatting and records its hash.
Recovery recomputes that exact after-history from the verified before-history plus the journal
metric. This keeps journal size independent of the number of completed rounds.

`best_output.md` after-content comes from the verified canonical revised output only when the metric
says the round improved. The journal needs its before/after hashes, not a second raw model-output
copy.

`memory.md` needs a bounded exact after-image because it mixes manual and auto-managed text.
`research_state.json` and checkpoint are small structured after-images. Pure builders should be
extracted from the current writer functions so preparation and application cannot disagree.

The recorded canonical run-root text is revalidated with the existing configured-storage policy;
it is not used as an unchecked write path. Device/inode values are optional defense in depth only
on platforms where the repository can obtain a meaningful stable identity. They are not a
cross-platform requirement or a promise that identity remains stable across deliberate storage
migration. If configured storage moved while a journal was pending, automatic recovery must stop
for owner-directed inspection.

## Round commit lifecycle

### Prepare

After Judge output and stage persistence succeed, but before `ready_to_publish`:

1. Hold the existing project/run lock.
2. Verify no round or finalization journal exists.
3. Verify the active attempt has all four exact staged outputs.
4. Parse the score and build the metric without externally visible round mutation.
5. Read all current transaction artifacts through trusted anchors.
6. Verify the histories correspond to the checkpoint's previous round.
7. Build the exact bounded after-generations.
8. Write the immutable journal with create-only semantics.
9. Reopen and validate the complete journal.

If preparation fails, canonical publication and all mutable round views remain unchanged. The
attempt evidence is preserved. Recovery must never create a journal by guessing timing/error metric
fields from canonical Markdown alone.

### Publish and apply

With the verified journal present:

1. transition the attempt to `ready_to_publish`;
2. use ARA-054 publication reconciliation to create/verify canonical `round_NN`;
3. transition the attempt to `published`;
4. apply `best_output.md` when required;
5. converge `score_history.json` to its after hash;
6. converge `round_metrics.json` to its after hash;
7. converge `memory.md` to its after hash;
8. converge `research_state.json` to its after hash;
9. write and verify the advanced per-round checkpoint last;
10. verify the canonical tree, attempt, every artifact after hash, and checkpoint identity again;
11. remove the journal;
12. continue to stop checks or the next round.

The order of the two histories is no longer a correctness assumption. Keeping the current order
minimizes behavioral change; the immutable journal makes either interruption recoverable.

The existing single-file replacement primitive is suitable for process interruption within one
file. The implementation must not claim all-files atomic visibility or sudden-power-loss durability.
If stronger power-loss claims are desired later, parent-directory syncing needs a separate
cross-platform design and tests.

## Recovery algorithm

Recovery runs provider-free while holding the same lock and before resume preview is treated as
actionable:

1. Read the fixed journal through the project trust boundary.
2. Enforce exact top-level keys, schema, kind, state, depth, size, scalar types, and ID grammar.
3. Validate the recorded run through configured-storage rules and cross-check run ID, directory
   identity, attempt ID, round, and run-config digest.
4. Validate the attempt and canonical handoff using ARA-054.
5. For every mutable artifact, securely read its exact bytes and classify it as:
   - `before`: hash equals the journal before hash;
   - `after`: hash equals the journal after hash;
   - `conflict`: anything else.
6. If any artifact is `conflict`, make no writes and return one path-redacted manual-recovery
   diagnostic.
7. Reconcile ready/canonical publication if needed.
8. Apply only artifacts still in `before`, reopening each and checking the after hash.
9. Write checkpoint last.
10. Re-verify the complete after-state and remove the journal.
11. Rebuild preview from the now-advanced checkpoint.

Repeated interruption at any step restarts this classification. An already-applied after-image is
never appended or transformed again.

The read-only preview may report `round_commit_recovery_required`; it should not silently mutate
artifacts. The actual resume/runner entry point performs recovery under the lock and then regenerates
the preview. A dedicated doctor/recovery command may expose the same operation with `--dry-run`.

## Run finalization transaction

Round commit and run finalization have different authorities and should not share one overloaded
payload.

After the last committed round and stop decision:

1. build the exact finalized run config, run summary, and final checkpoint in memory;
2. create and verify `.run_finalize_transaction.json` in the project directory;
3. apply and verify run-local `run_summary.json`;
4. apply and verify run-local `run_config.json`;
5. apply and verify project-global final checkpoint last;
6. remove the finalization journal.

The record uses the same fixed-artifact allowlist and before/after hash rules. It stores the three
bounded exact after-values because they include timestamps, total runtime, stop reason, and resume
eligibility that should not be recomputed differently after interruption.

While finalization is pending:

- resume and new-run entry points finish it before acting;
- compare, analytics, UI, and report readers expose `finalization_pending` instead of combining
  generations;
- an unknown hash fails closed;
- an interruption before the finalization journal exists leaves the already-committed per-round
  checkpoint as the conservative recovery authority.

Interrupted reports and stop-signal cleanup remain post-finalization derived operations. Their
failure must not invalidate a committed round or finalized run.

## Stale, malformed, and historical states

### Valid pending journal

Recover by deterministic roll-forward only.

### Journal with an unknown version, invalid JSON, excessive depth/size, unsafe leaf, wrong run,
changed run-storage identity, missing attempt, canonical conflict, or unknown artifact hash

Preserve everything and fail closed. Report fixed artifact labels and IDs, not private absolute
paths or file contents.

### Journal is present but all after hashes already match

Verify the checkpoint and canonical attempt, then remove the stale journal. This is normal cleanup
recovery, not a duplicate commit.

### `published_uncommitted` without a journal

Keep the current ARA-054 behavior: preserve and block. Existing artifacts lack a trustworthy
metric/timing payload and before-generation hashes. Automatic adoption or history synthesis would
be a migration and remains unapproved.

### Legacy histories with one side absent

Preserve the existing correlation fallback for old committed runs. Do not use that fallback to
repair a future journaled transaction; a journaled transaction must match its exact before/after
hashes.

### Manual edits during a pending transaction

An edit creates an unknown hash and blocks automatic recovery. Do not overwrite it even if it is
syntactically valid. A future explicit recovery tool may export the journal and conflict details,
but must require owner action to choose a generation.

## Security and resource constraints

- Add both journal names to the project runtime safety inventory before enabling writes.
- Use create-only journal creation; never replace an existing journal.
- Read and write through existing trusted project and run anchors.
- Treat artifact keys as a closed enum. Never join a journal-supplied arbitrary path.
- Revalidate configured external storage on every recovery.
- Reject symlinks, junctions/reparse points, hard-linked leaves, special files, identity changes,
  unsafe permissions, malformed UTF-8/JSON, and excessive nesting using existing policy.
- Use SHA-256 over exact UTF-8 bytes with domain-separated labels in the transaction digest.
- Restrict transaction/run/attempt identifiers to bounded ASCII grammars.
- Bound the serialized journal before canonical publication. The implementation proposal is a
  2 MiB ceiling, depth 128, one metric, six fixed round artifacts, and no raw agent output.
  Exceeding the cap preserves the attempt and fails before publication.
- Never include secrets, environment-variable values, provider request bodies, raw prompts, or
  unrestricted exception graphs.
- Recovery performs no network or provider call and has no retry loop beyond one idempotent pass per
  explicit invocation.
- A pending transaction consumes no unbounded sequence of journals: there is exactly one fixed
  create-only journal per project phase.
- Continue to document that the cooperative lock and descriptor-relative I/O are not a hostile
  same-UID sandbox.

## Compatibility

### Preserved

- canonical round paths, filenames, and bytes;
- history JSON list format and metric values;
- checkpoint, summary, and run-config public fields;
- score parsing, best-round selection, stop rules, prompts, providers, and call count;
- configured external `runs/` storage;
- read-only access to legacy completed runs;
- ARA-041's separate same-run-filesystem resume-startup rollback journal.

### Deliberately additive after implementation approval

- two temporary project-local journal filenames;
- a recovery-required preview/status;
- fail-before-provider behavior while a journal is pending;
- pure state builders used by preparation and application;
- report readers refusing mixed finalization generations.

### Not automatically compatible

- historical journal-less `published_uncommitted` rounds;
- ambiguous legacy canonical partials;
- a run-storage target moved during a pending transaction;
- artifacts manually edited to a third generation;
- unknown journal schemas.

These remain inspectable evidence and require a separately approved migration or owner decision.

## Options considered

| Option | Result | Decision |
| --- | --- | --- |
| Reverse the two history writes | opposite split generation remains possible | reject |
| Rename a directory containing all artifacts | paths span filesystems and existing locations | reject |
| Roll back already-written files | can erase canonical evidence or manual edits | reject |
| Infer missing history from canonical Markdown | timing/error/metric provenance is unavailable | reject |
| Put the only journal in run storage | round 1 recovery is not discoverable without trusted project authority | reject |
| Store full before/after histories | recovery is simple but journal grows with the whole run | reject |
| Store one metric delta plus exact hashes | bounded, idempotent, preserves existing artifacts | select |
| Replace artifacts with SQLite/event sourcing | broad migration and compatibility cost | defer |

## Separately identified diagnostic writer

`src/diagnostic.py` independently writes project score history before run-local metrics and then
checkpoint/summary/config. It does not use ARA-054 attempts and is not resumable as the same run, but
the same split can still leave project-global history ahead of its diagnostic run.

The shared low-level journal engine should support a fixed `diagnostic_finalize` record in a later
package, using canonical file hashes instead of an attempt identity. Do not silently fold that
runtime change into the iterative-round implementation without including its focused fault tests
and approval.

## Implementation packages requiring approval

1. **Pure builders and strict journal codec**
   - extract deterministic history, memory, research-state, checkpoint, summary, and config
     after-image builders;
   - add strict bounded schemas and fixed artifact enums;
   - no runner routing change.
2. **Round prepare and recovery engine**
   - create the journal before `ready_to_publish`;
   - reconcile ARA-054 publication and both filesystems;
   - add dry-run classification and conflict diagnostics.
3. **Runner integration**
   - route successful iterative rounds through prepare/apply/recover;
   - make checkpoint the last round-commit write;
   - preserve ordinary outputs and control flow.
4. **Preview/UI/report integration**
   - expose recovery-required and conflict states;
   - prevent mixed-generation analytics;
   - keep read-only preview non-mutating.
5. **Finalization journal**
   - apply summary/config before final checkpoint;
   - recover every finalization write boundary.
6. **Diagnostic integration**
   - only if separately approved after the iterative path is stable.
7. **Legacy migration**
   - design is complete in `docs/ARA_055_LEGACY_MIGRATION_DESIGN.md`;
   - discovery implementation, execution, and rollback remain separately approval-gated.

Each package should be a separate small commit with a clean recovery point. Runtime packages 2-6
must not start from this design-stage approval.

## Validation plan for an approved implementation

### Round transaction matrix

- internal and configured external run storage;
- `OSError` and `KeyboardInterrupt`;
- before/after journal creation;
- before/after ready transition;
- every ARA-054 publication handoff boundary;
- before/after best output, both histories, memory, research state, checkpoint, verification, and
  journal cleanup;
- repeated interruption during recovery;
- a recovery invocation repeated after success.

Every case must prove:

- exactly one canonical round;
- exactly one identical metric in each history;
- prompt-affecting state matches the committed round;
- checkpoint advances only after all prior after hashes match;
- no provider calls;
- no overwritten stopped evidence;
- no path disclosure.

### Conflict and safety matrix

- malformed/unknown/oversized/deep journal;
- symlink, hard link, junction/reparse point, special file, and changed leaf;
- wrong run ID, run root, attempt ID, config digest, or round;
- moved/removed configured storage;
- canonical missing, exact, prefix, or conflicting;
- each artifact in before, after, missing, or third-generation state;
- manual memory edit while pending;
- journal already fully applied but not removed.

### Finalization matrix

- before/after summary, config, final checkpoint, and cleanup;
- report/compare/analytics reads while pending;
- resumable and non-resumable stop reasons;
- manual interrupt status 130 and cooperative status 0;
- stale prior summary/config from a resumed run.

### Regression layers

1. strict journal codec and pure-builder unit tests;
2. ARA-054 attempt/publication tests;
3. resume-history and startup-journal tests;
4. runner, CLI, UI helper, compare, analytics, diagnostic, and storage suites;
5. `make check`;
6. isolated-wheel smoke;
7. Python 3.10 and 3.13 CI.

No real provider smoke is needed for the transaction implementation.
