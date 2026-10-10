# PMW Generative Mechanics v0.6 TODO1 Implementation Report

Status: `READY_FOR_OWNER_REVIEW`

All TODO1 engineering gates pass. This is an implementation freeze candidate,
not a frozen benchmark and not permission to begin formal collection.

## A. Summary

- Baseline commit: `1510b2a3a7db397b84db22ebb41d61845dd56ade`
- Feature branch: `feature/gm-v06-todo1-rich-dynamics`
- New commit: recorded after this report is committed on the feature branch
- Core changed: no
- Formal collection started: no
- Frozen-tree digest: `7e3aeb50542594cf5356963e3103d1ae52c17d7f3b1549a1eee2beeea3c6e855`
- Changed scope: 53 files, all under `next_tracks_v06/`
- Agent model disclosure: the collaboration API had no model/reasoning selector,
  so `GPT-5.6 Luna High` cannot be verified or claimed. Roles A/B/C were used;
  their later turns hit the account usage limit. An existing agent was then
  reassigned as independent role D for final read-only audit.

## B. Mathematical Semantics

For normalized state `x`:

```text
a_eff = (w_base*a_base + sum(w_i*a_i)) / (w_base + sum(w_i))
alpha_eff = clamp(alpha_base + sum(alpha_delta_i), 0, 1)
drive_eff = clamp(sum(drive_i), -drive_limit, drive_limit)
coupling_i = sum(k_ij * (x_j - x_i))
x_next = clamp(x + alpha_eff*(a_eff-x) + drive_eff + coupling_i, 0, 1)
```

`w_base > 0`, all modifier weights are non-negative, all numeric inputs are
finite, and booleans are rejected as numbers. Coupling endpoints read one
pre-phase snapshot and receive opposite deltas. Without saturation, coupling-
only transfer is conservative. Saturation is recorded as `clamp_loss` rather
than treated as equivalent dynamics.

Each integer step dispatches due Scheduler events, then executes PMW
`PREPARE -> ACCUMULATE -> COMMIT` derived events, then `world.step`, closure,
and snapshot. Scratch is reset, intrinsic/coupling deltas aggregate, and only
COMMIT writes the bounded formal value. No fixed-point iteration represents a
second physical time step.

## C. Implementation

- Six strict catalog objects: Field, Stock, Process, Relation, Discrete, Derived.
- Seven executable operators: impulse, drive/source, attractor modifier,
  dynamics modifier, process start, process modify, and relation modifier.
- Recursive unknown-field rejection, finite numeric checks, capability/scope/
  ownership gates, Derived read-only enforcement, and catalog limits.
- Deterministic joint installation allocation prevents different artifacts from
  reserving one contribution slot. Active-instance guards prevent overwrite;
  cancellation clears the slot and its pending handle through PMW laws.
- Compiler output is canonical, fully `parse_law` validated, namespaced, source
  mapped, and pure. `compile_mechanisms` performs the required batch allocation.
- Runtime activation payloads and temporal namespaces are fail-closed. Save/load
  rebuilds the same Engine bundle and continues byte-equivalently.
- A mechanism instance cannot re-enter while any of its timed operators remains
  pending. Cancellation authenticates the activation namespace and clears only
  its still-pending operators, so staggered natural expiry is safe and ownership
  cannot be mixed.
- Conserved Stock transfer uses one `min(rate, source, free_capacity)` expression
  for paired deltas. Explicit source/sink modes require privileges.
- Relation create/delete changes real PMW topology; parameter modifiers feed the
  later coupling Law. Derived values are written only by ordinary state laws.

## D. Demonstrations

All checked-in results contain the MechanismSpec, compiled Law IDs, initial and
final WorldState, activation EventResult, every StateDelta/CausalTrace, temporal
dispatches, source map, and trajectory.

- **Impulse vs Attractor**: impulse changes `0.8 -> 0.4` immediately and recovers
  to `0.692420` at step 12. A permanent cold attractor leaves step 0 at `0.8`
  and converges to `0.351535` at step 12.
- **Competing Attractors**: two weighted sources produce `0.710000` at step 1;
  the cold source expires at step 3, the hot source at step 6, and the field then
  resumes base dynamics without rollback.
- **Drive and Depletion**: boosted pump consumption takes coolant `0.8 -> 0.0`;
  the process stops at step 7 and temperature then recovers (`0.519676 ->
  0.671222` by step 12).
- **Relation Propagation**: a real `supplies_power` relation is present through
  step 2 and deleted at step 3. Battery rises `0.3 -> 0.5` while connected and
  remains `0.5` after disconnection.
- **Dynamics & Process Modification**: alpha and pump-flow slots alter only
  future evolution; coolant reaches zero at step 4, the process stops, and
  temperature follows a distinct recovery trajectory.

## E. Verification

- Core: **254/254 passed** in 25.754 s.
- Frozen Generative Mechanics: **345/345 passed** in 68.535 s.
- New TODO1: **162/162 passed** in 25.576 s.
- Production mathematical/network differential: **1000/1000 passed**, tolerance
  `1e-12`.
- Independent manual-oracle differential: **1000/1000 passed** without importing
  the production reference implementation.
- Lifecycle/expiry differential: **1000/1000 passed**, including two independent
  modifier durations, dispatch count, owner cleanup, and empty pending queue.
- Five demos rebuild byte-deterministically and match checked-in results.
- `git diff --check`: clean. Failures/skips/expected failures: **0/0/0**.

Locality with fixed participants and unrelated entities:

```text
unrelated  candidate  partial  complete  warm index builds  warm tick
1,000      23         23       10        0                  0.00612 s
10,000     23         23       10        0                  0.00663 s
100,000    23         23       10        0                  0.01429 s
```

Cold index materialization scales with total world size (`0.00641 / 0.06673 /
0.75253 s`), as expected. Warm structural work remains constant. Each first
step records one state full-scan during initial closure; lifecycle global scans
remain zero.

## F. Open Issues

- `IMPLEMENTATION_BUG`: none known after final audit.
- `CORE_CAPABILITY_GAP`: arbitrary unbounded modifier reduction and fair
  capacity-constrained multi-flow allocation are not expressible in the current
  DSL. TODO1 deliberately uses catalog-bounded slots and exclusive transfer
  paths. The DSL also cannot prove string namespace provenance internally, so
  the trusted execution harness validates activation/handle namespaces.
- `DOCUMENTED_LIMITATION`: no Law hot-install; checkpoints are supported at
  complete integer step boundaries; temporary deletion of an unspecified
  world-owned Relation is rejected because exact restoration data is absent.
  Timed artifact-created Relations are deleted safely at expiry, and permanent
  deletion of authorized world Relations is supported.
- `FUTURE_TODO2_REQUIREMENT`: goal-conditioned tasks, goal oracle, rule-blind
  baseline, model collection, and benchmark scoring were not started.
