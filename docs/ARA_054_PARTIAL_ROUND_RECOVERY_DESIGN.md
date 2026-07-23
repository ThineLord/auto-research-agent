# ARA-054 Partial-Round Recovery Design

Status: design complete; runtime recovery package approved

Date: 2026-07-23

Scope: provider-free recovery design, staging foundations, and approved runtime recovery package

## Decision summary

Use an append-only attempt staging area beneath each run and retry an interrupted round from its
first agent. A stopped attempt remains immutable evidence. It is never reused as mutable input,
deleted, overwritten, or silently promoted into a completed round.

Canonical `round_NN` directories remain the only agent-complete output format. A successful attempt
may publish its complete output directory into an absent canonical path. Existing readers, reports,
metrics, and historical artifacts continue to interpret canonical rounds exactly as they do now.
The separate history/checkpoint commit boundary remains owned by ARA-055.

Do not implement mid-agent continuation from partial files. The current files do not encode a
trustworthy stage boundary, agent error state, timing state, or prompt/config identity. In
particular, empty output and the current one-byte placeholder are not distinguishable from
legitimate empty model output.

The owner subsequently approved the runtime recovery package: manifest transitions,
empty-canonical handoff, disk-budget protection, staged runner writes, canonical publication, and
shared runner/preview classification. Legacy migration and ARA-055 remain outside that
authorization.

## Confirmed current behavior

The characterization used only `FakeAgents`, synthetic text, and temporary directories. It made no
provider calls and did not inspect ignored project data.

Current writer and reader behavior:

- `src/runner.py` creates canonical `round_NN` before the first agent.
- `_persist_round_outputs()` calls `save_round_outputs()` after draft, review, revise, and Judge.
- `save_round_outputs()` writes all four canonical files on every call. An output not produced yet
  is serialized by `write_text()` as one newline byte.
- `can_resume` is derived only from the stop reason. User stop, manual interrupt, cloud daily quota,
  and provider quota are eligible.
- `build_resume_preview()` derives the pending round as `last_completed_round + 1`.
- Any nonempty pending canonical directory blocks resume.
- Because all four filenames exist after the first persistence, preview labels even a draft-only
  attempt `complete_uncheckpointed`, not `partial`.
- `_validate_pending_resume_round_dir()` independently rejects any pending round directory with an
  entry, so bypassing preview does not make the run writable.

### Provider-free fault matrix

The probe raised either `KeyboardInterrupt` or `CloudFreeDailyQuotaExhausted` immediately after the
selected stage had been atomically persisted. The synthetic output sizes below include the trailing
newline written by the current storage helper.

| Persisted stage | Draft bytes | Review bytes | Revised bytes | Judge bytes | Checkpoint `last_successful_agent` |
| --- | ---: | ---: | ---: | ---: | --- |
| draft | 48 | 1 | 1 | 1 | `none` |
| review | 48 | 65 | 1 | 1 | `draft` |
| revise | 48 | 65 | 68 | 1 | `review` |
| judge | 48 | 65 | 68 | 329 | `judge` |

For both fault types, all eight post-persistence cases had the same recovery contract:

- `last_completed_round=0`
- `resume_metadata.next_round=1`
- checkpoint `can_resume=true`
- preview `can_resume=false`
- `next_round_status=complete_uncheckpointed`
- `blocked_reason=partial_next_round_exists`
- actual `run_resume_mode()` returned false without calling an agent
- checkpoint bytes and every pending-round file byte were unchanged by the rejected attempt

A control fault on entry to draft left an empty `round_01`, and preview correctly allowed reuse.
Faults on entry to review, revise, or Judge reproduced the same blocked state created by the
previous successfully persisted stage.

The stage-marker lag is also inconsistent: draft, review, and revise persist before updating
`last_successful_agent`, while Judge updates it before persistence. That field therefore cannot
serve as a safe migration oracle.

## Root cause

The writer uses one namespace for two incompatible meanings:

1. mutable, incomplete stage evidence; and
2. immutable, completed canonical round output.

The reader correctly treats the canonical namespace as immutable and refuses to overwrite it.
Finalization nevertheless declares the run resumable using only a stop-reason allowlist. The
checkpoint and filesystem therefore disagree.

Changing only the reader to accept the files would weaken a deliberate overwrite guard. Changing
only the checkpoint to `can_resume=false` would make the metadata truthful but would not restore
the promised recovery capability.

## Required invariants

Any implementation of this design must preserve all of the following:

1. A canonical `round_NN` is immutable, agent-complete output, never a mutable work directory.
   Whether its histories/checkpoint committed is a separate ARA-055 state.
2. A stopped attempt is immutable. Resume allocates a new attempt and never writes into the old
   attempt.
3. Completed canonical round bytes and paths retain their existing format and meaning.
4. No automatic path deletes, truncates, replaces, or overwrites stopped-attempt evidence.
5. Resume preview and the runner use the same eligibility classifier.
6. A checkpoint may say `can_resume=true` only when the runner can begin the advertised action
   without manual file movement.
7. Unknown, malformed, unsafe, or conflicting attempt state fails closed without exposing an
   absolute path or secret.
8. Partial attempts never contribute scores, best-output selection, metrics, benchmark results, or
   paper-facing conclusions.
9. Retry starts the round from draft. It does not silently reuse a prior agent result.
10. Provider, prompt, scoring, seed, and completed-round semantics remain unchanged.

## Proposed layout

The layout is additive and stays on the run root's filesystem:

```text
runs/<run_id>/
  round_01/                         # existing canonical completed round
    01_draft.md
    02_review.md
    03_revised.md
    04_judge.md
  partial_rounds/
    round_02/
      attempt_<opaque-id>/
        attempt.json
        output/
          01_draft.md               # created only after draft succeeds
          02_review.md              # created only after review succeeds
          03_revised.md             # created only after revise succeeds
          04_judge.md               # created only after Judge succeeds
```

`partial_rounds` deliberately does not match the root-level `round_*` glob used by the benchmark
report. Attempt paths are derived from a validated run root, round integer, and restricted opaque
identifier. A checkpoint must not supply an arbitrary absolute attempt path.

Each stage output is create-only and atomically written once. The current replace-capable
`write_text()` helper must not be used directly for an existing staged output. A collision or
unexpected existing entry fails closed.

## Attempt metadata

`attempt.json` is a new, attempt-local schema. This is a proposal, not an implemented schema:

```json
{
  "schema_version": 1,
  "kind": "partial_round_attempt",
  "run_id": "<canonical run directory name>",
  "round": 2,
  "attempt_id": "<restricted opaque identifier>",
  "state": "stopped",
  "completed_stages": ["draft", "review"],
  "last_successful_agent": "review",
  "stop_reason": "MANUAL_INTERRUPT",
  "created_at": "<ISO-8601>",
  "updated_at": "<ISO-8601>",
  "run_config_sha256": "<hex digest>",
  "outputs": {
    "01_draft.md": {"size": 123, "sha256": "<hex digest>"},
    "02_review.md": {"size": 456, "sha256": "<hex digest>"}
  }
}
```

Allowed states:

- `active`: the attempt may be written only by the process holding the run lock.
- `stopped`: an interrupt, quota stop, or cooperative stop preserved the attempt.
- `ready_to_publish`: all four outputs exist and match the manifest.
- `published`: the output directory was atomically published as canonical `round_NN`.
- `unverifiable`: discovery found a missing, mismatched, unsafe, or orphaned component.

The manifest contains no credentials, environment values, prompts, absolute private paths, or raw
provider exceptions. Model/config provenance remains in the existing run configuration; its digest
binds the attempt to the generation observed at creation.

Updating the manifest does not authorize changing an output file. If a process stops after creating
an output but before recording its digest, discovery preserves the orphan output, marks that
attempt unverifiable, and allocates a different attempt only after the resume classifier confirms
that a retry is safe.

## Checkpoint and preview contract

The existing checkpoint and run-config schema versions need not change. Additive resume metadata
may describe the stopped attempt:

```json
{
  "partial_round": {
    "schema_version": 1,
    "round": 2,
    "attempt_id": "<restricted opaque identifier>",
    "state": "stopped",
    "completed_stages": ["draft", "review"],
    "resume_action": "retry_round_preserve_attempt"
  }
}
```

The preview derives the attempt path from validated identifiers and cross-checks the manifest. It
must expose, at minimum:

- `next_round_status=staged_partial`
- `next_round_blocks_resume=false`
- `next_round_safety_action=retry_round_preserve_attempt`
- the count of preserved attempts
- the latest verified completed stage for diagnosis only

`can_resume=true` means a fresh attempt can be created for the same round. It does not mean the old
attempt will continue from its last stage.

The runner must call the same classifier immediately before attempt creation. Preview alone is not
a security boundary.

## Lifecycle and recovery

### New attempt

1. Validate the project, run root, run identity, canonical next-round absence, and run lock.
2. Discover and validate existing attempt directories without following links.
3. Enforce an attempt-count and disk-budget limit. Never make unbounded automatic retries.
4. Create a unique attempt directory using an anchored, exclusive operation.
5. Atomically write `attempt.json` in `active` state.
6. Run draft from the same inputs used by the current round loop.

### Stage completion

For each successful stage:

1. Atomically create its one output file with no-clobber semantics.
2. Reopen it through the trusted anchor and calculate size and SHA-256.
3. Atomically update `attempt.json`.
4. Only then advertise that stage as complete.

No placeholder file is created for a future stage.

### Interrupt, quota, or cooperative stop

1. Mark the attempt `stopped` if its current state can be verified.
2. Finalize the existing checkpoint/summary/config artifacts.
3. Set `can_resume=true` only if the shared classifier proves that another attempt can be created.
4. Preserve every attempt file.
5. Manual interrupt continues to re-raise for process status 130; quota and cooperative-stop status
   semantics remain unchanged.

If final metadata persistence itself fails, the attempt remains discoverable. A later preview may
list it, but must not infer permission to overwrite or continue it.

### Successful publication

After all four outputs and hashes verify, at the current output-publication point and without
reordering history writes:

1. Mark the attempt `ready_to_publish`.
2. Confirm canonical `round_NN` is absent.
3. Atomically rename the attempt's `output` directory to canonical `round_NN` on the same
   filesystem. Do not use replacement semantics.
4. Verify the canonical files against the manifest.
5. Mark the attempt `published` and record only the canonical relative name.

Stopped attempts are never moved. The controlled rename is limited to a fully successful,
hash-verified output directory after a separately approved implementation.

Crash reconciliation around publication is deterministic:

| Attempt output | Canonical round | Manifest state | Recovery |
| --- | --- | --- | --- |
| present | absent | `ready_to_publish` | publication not committed; verify and retry publication |
| absent | present | `ready_to_publish` | verify hashes, mark output `published`, then apply the ARA-055 boundary |
| absent | present | `published` | normal committed publication |
| present | present | any | conflict; preserve both and fail closed |
| absent | absent | any completed state | evidence missing; fail closed |

The rename is process-atomic because both paths are beneath one run root. Parent-directory fsync and
hostile same-UID replacement are not claimed; those limitations match the repository's existing
artifact-boundary threat model.

`published` proves only that the four canonical outputs match the attempt manifest. It does not
prove that histories, memory, best output, or checkpoint committed. Preview must classify that
combination as `published_uncommitted` and fail closed until ARA-055 defines its recovery.

## Existing legacy partial rounds

A canonical pending `round_NN` without a valid attempt manifest is legacy ambiguous state. It may
contain legitimate empty output, current placeholders, user-added files, or a completed output
whose history was not committed. It must not be auto-adopted or overwritten.

Initial implementation behavior:

- preview reports `next_round_status=legacy_partial`
- checkpoint-derived `can_resume` is overridden to false
- action is `explicit_migration_required`
- every byte remains in place

A future explicit migration can be designed as a journaled, same-filesystem rename into a new
attempt directory after hashing and validating the complete tree. It must require a separate owner
approval and must be recoverable across interruption. Copy-then-delete and automatic cleanup are
not acceptable substitutes.

This keeps historical artifacts readable and avoids pretending that ambiguous legacy placeholders
are resumable stage checkpoints.

## Compatibility analysis

### Preserved

- Completed canonical directories retain `round_NN` and the same four filenames and bytes.
- Existing benchmark, report, UI analytics, comparison, best-output, and history readers continue
  to consume canonical rounds and histories.
- `partial_rounds` is outside the root-level `round_*` namespace.
- Legacy checkpoints with no attempt metadata keep the existing fail-safe interpretation.
- Existing unknown run-manifest fields and schema-v1 run-config behavior remain untouched.
- A normal successful run produces no changed score, prompt, provider call order, or research
  interpretation.

### Deliberately changed after implementation approval

- Work-in-progress outputs are staged instead of being written to canonical `round_NN`.
- Future interrupted runs can retry the same round while preserving prior attempt evidence.
- Preview reports the retry action and preserved-attempt count.
- Future stage output files are created only when that stage completes; placeholder files exist only
  in historical canonical partial directories.

### Not compatible enough for automatic continuation

- Existing canonical partial directories.
- Attempt files with unknown schema versions.
- Hash, identity, path, or state conflicts.

These states remain readable evidence but are not mutable resume input.

## Security and resource constraints

- Reuse the registered run-root trust anchor and descriptor-relative path operations.
- Reject symlinks, junctions/reparse points, non-directories, non-regular outputs, multiple-link
  files, unsafe permissions, and identity changes between inspection and open.
- Restrict attempt identifiers to a fixed ASCII grammar and maximum length.
- Never trust path text from checkpoint or manifest; derive paths from validated components.
- Never use `os.replace()` or another overwrite-capable primitive for attempt creation or canonical
  publication.
- Redact displayed paths through the existing repository-relative display helper.
- Bound attempts per round. A proposed initial cap is 32; reaching it fails closed with an archive
  instruction and performs no deletion.
- Check free space before a retry and report estimated retained bytes.
- Partial attempts are excluded from artifact scoring and benchmark discovery.
- Continue to document that the cooperative run lock is not a hostile same-UID sandbox.

## Options considered

| Option | Safety | Compatibility | Recovery value | Decision |
| --- | --- | --- | --- | --- |
| Set `can_resume=false` when canonical partial exists | safe and small | high | no usable recovery | reject as sole fix |
| Delete or roll back the canonical partial | loses evidence | superficially simple | retry possible | reject |
| Continue from the last apparent stage | ambiguous placeholders and state | high implementation risk | avoids repeated calls | reject |
| Overwrite canonical files on retry | destroys evidence | breaks fail-safe guard | retry possible | reject |
| Append-only attempt staging; retry whole round | preserves evidence and canonical format | additive | deterministic retry | selected |

## ARA-055 boundary

ARA-054 owns agent-stage output isolation and agreement between resume metadata, preview, and retry
creation.

It does not make these cross-file updates atomic:

- canonical round publication
- project-global `score_history.json`
- run-local `round_metrics.json`
- `best_output.md`
- `memory.md`
- checkpoint, run summary, and run config

A hard stop after successful publication but during those updates is the ARA-055 transaction
problem. ARA-054 implementation must not reorder those artifacts or claim full round-commit
atomicity without an approved ARA-055 design. The attempt manifest can make output publication
detectable, but it cannot by itself prove that both history generations committed.

## Implementation work packages requiring approval

The foundation is implemented in `e4e784e`: item 1 and the discovery/classifier/count-cap portion
of item 2 are complete. The owner has now approved the remaining item-2 resource protection plus
items 3-5. Item 6 remains deferred, and legacy migration must not be implemented.

1. Add create-only anchored stage-output and attempt-manifest helpers with unit fault tests.
2. Add attempt discovery, validation, resource bounds, and shared eligibility classification.
3. Route partial stage persistence to attempts while preserving canonical successful output bytes.
4. Add preview/CLI/UI diagnostics and whole-round retry allocation.
5. Add successful publication reconciliation, explicitly bounded from ARA-055.
6. Add documentation and an opt-in legacy migration design; do not implement migration implicitly.

Each package should be a separate validated commit. No package should be started until the owner
approves implementation scope.

## Validation plan for an approved implementation

### Focused behavior

- 4 persisted stages × manual interrupt.
- 4 persisted stages × cloud daily quota.
- Cooperative user stop before and after every agent.
- Provider quota stop after completed error rounds.
- Empty pre-agent stop remains reusable.
- Every stopped attempt hash remains unchanged across preview and one or more retries.
- A retry allocates a distinct attempt and starts at draft.
- Successful retry publishes exactly one canonical `round_NN`.
- Canonical output bytes match the current successful-run format.

### Fault and crash windows

- interrupt before and after stage-output creation
- interrupt before and after manifest replacement
- output exists without manifest entry
- manifest entry exists with missing or mismatched output
- interrupt before and after publication rename
- destination collision before publication
- both attempt output and canonical directory present
- neither path present after a completed manifest state
- checkpoint/summary/config failure after a stopped attempt

### Safety and compatibility

- symlink, junction/reparse, hard-link, non-regular, unreadable, and unwritable cases
- external configured runs storage
- unsafe or overlong attempt identifiers
- unknown attempt schema and extra entries
- legacy one-file, four-placeholder, complete-uncheckpointed, and unexpected-entry directories
- benchmark report ignores `partial_rounds`
- analytics/comparison/UI do not count staged attempts
- legacy manifest extensions and schema-v1 run config remain byte/field compatible
- Python 3.10 and 3.13
- isolated wheel smoke
- repository safety scans
- full `make check`

All tests remain provider-free. No canonical experiment artifact is required for validation.

## Design acceptance

The design stage is complete when:

- the confirmed current matrix is recorded;
- the selected design preserves partial bytes and canonical completed-round compatibility;
- preview, runner, retry, crash, migration, security, and resource behavior are specified;
- the ARA-055 boundary is explicit;
- design/recovery documentation passes repository validation; and
- no runtime or schema behavior has changed.
