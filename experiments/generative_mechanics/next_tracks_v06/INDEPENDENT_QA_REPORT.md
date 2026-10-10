# TODO1 Independent QA

Status: `READY_FOR_OWNER_REVIEW`.

This audit was performed independently after the role A/B/C implementation.
It does not modify PMW Core or any frozen Generative Mechanics artifact.

## Independent evidence

- A second 1,000-case randomized dynamics differential uses a manual oracle in
  the QA test and does not import `dynamics.reference`.
- The QA locality gate compares 1,000 with 100,000 unrelated entities and
  requires identical candidate rows, partial bindings, and complete bindings,
  with zero warm index builds and lifecycle global scans.
- Conservation is checked both for symmetric unsaturated coupling and for
  concurrent Stock flow at the lower boundary.
- Lifecycle attacks cover wrong-owner cancellation, orphan handles, instance
  bounds, re-entry, relation topology, and scheduled expiry.
- The complete TODO1 suite contains 162 tests. It includes the production
  1,000-case dynamics differential, a separate 1,000-case randomized lifecycle
  differential, and this audit's 1,000-case manual-oracle differential.
- Frozen compatibility was independently rerun: PMW Core passed 254 tests and
  the pre-v0.6 Generative Mechanics suite passed 345 tests.
- `git diff --check` passed. The worktree contains no tracked modification
  outside the new `next_tracks_v06/` tree.

The measured locality rows were:

| unrelated entities | candidate rows | partial bindings | complete bindings | warm index builds | lifecycle global scans |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 23 | 23 | 10 | 0 | 0 |
| 10,000 | 23 | 23 | 10 | 0 | 0 |
| 100,000 | 23 | 23 | 10 | 0 | 0 |

Timing is reported as observational evidence, not the locality proof. Warm tick
times in this run were approximately 0.0065 s, 0.0066 s, and 0.0236 s; the
structural counters above are the acceptance criterion.

## Closed findings

### QA-01: cancellation is not bound to the live activation

Cancellation now validates namespaced pending handles before execution. A wrong
activation ID fails without changing slots or the queue. After staggered natural
expiry, cancellation operates on the remaining pending-handle intersection.

### QA-02: activation instance upper bound is not enforced

`CompiledMechanism` carries `max_instances`; event construction and validation
reject an out-of-range instance before execution.

### QA-03: concurrent Stock outflows can underflow

The chosen v0.6 policy is strict writer uniqueness. Validation rejects multiple
generated writers for every source and destination Stock address and rejects a
generated flow on a Stock already written by a world Process.

### QA-04: catalog slot alias validation is incomplete

Catalog validation now proves slot kind/target agreement, runtime-object
agreement, and storage-address uniqueness.

### QA-05: Stock writer uniqueness must include runtime instances

Stock flow mechanisms are now single-instance and both transfer endpoints enter
the batch writer-conflict set.

### QA-06: created Relation IDs need an artifact namespace

Created Relation IDs now contain the artifact ID and canonical-spec hash. The
cross-artifact collision regression passes.

### QA-07: authorization fields must be enforced

Field drives accept signed bounded rates while Stock quantities remain positive.
World-owned Process privileges and capability action grants are enforced.

### QA-08: unsupported duplicate writers must fail validation

Duplicate impulse and Process lifecycle writers are rejected before compilation.

### QA-09: staggered lifecycle cancellation and partial re-entry

Cancellation now tolerates operators from the same activation that have already
expired while cancelling all remaining handles. Activation fails closed while
any timed handle for that mechanism instance remains pending, preventing mixed
activation ownership.

## Residual limitations

- Stock concurrency uses a conservative single-generated-writer policy rather
  than an aggregate flow allocator. This is a documented v0.6 limitation, not a
  silent conservation failure.
- Coupling conservation is asserted only when there is no boundary saturation
  or intrinsic source/sink. `clamp_loss` makes boundary loss auditable.
- Internal expiry event types are trusted-runtime protocol details. Supported
  callers use `activate` and `cancel_activation`, not arbitrary direct dispatch
  of internal event payloads.

No open finding blocks TODO1 owner review. This status does not freeze a v0.6
benchmark and does not authorize formal model collection.
