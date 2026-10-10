# Gate 2 Implementation Report

Status: `DONE` after integration-owner review.

This report covers G2.01-G2.10 on top of Gate 1 commit `1f1ae81`.  It does not
freeze gameplay balance, start TODO2, or modify PMW Core or Gate 0/1 sources.

## Implemented contracts

- `ActionRequest` contains only controller intent.  It cannot inject a cost,
  Effect, PMW path, or Law.  A hash-pinned `ActionRegistry` supplies trusted
  definitions and recursively rejects unknown fields.
- `ActionCost` has positive base duration, Mana cost, and explicit conditional
  modifiers.  Final duration is at least one.  Cost and required Effects are
  preflighted before one PMW root Event; a failed preflight makes no formal
  write and a PMW scheduler conflict is rejected before publication.
- Effect templates cover damage, heal, shield, resource change, Status, Field
  impulse, temporary attractor target, temporary recovery rate, and temporary
  Trait grant.  Temporary Dynamics effects reserve owner-tagged Gate 1 slots
  and use PMW Scheduler handles for exact expiry.
- Attribute `scaling`, `threshold`, `check`, and `modifier` terms must name one
  of Power, Control, Resilience, or Agility.  Target sensing and evasion are
  opt-in fields; an evadable Effect requires an explicit check.  There is no
  ambient hit, evasion, defense, or initiative formula.
- Status instances use eight bounded, static actor slots.  Reject, refresh,
  replace, and bounded additive stacking are deterministic.  World Tick,
  Combat Round, and Owner Turn expiry use formal phase Events.  Periodic
  resource Effects execute on the final boundary before expiry.  Cancellation
  checks the exact instance and owner.
- Hook schemas expose all six required trigger names, typed conditions,
  installed Effect bundles, per-root budget, source deduplication, depth cap,
  and an authoritative PMW cooldown write.  Hook Effects execute through the
  same PMW action Laws without consuming a main action or Mana.
- Attack, Guard, and Wait are ordinary immutable built-in definitions and do
  not occupy the six active slots.  Attack explicitly scales Power.  Guard
  explicitly scales Resilience, refreshes instead of stacking, and expires at
  the start of the owner's next turn.  Wait grants explicit Mana value.
- `HumanController` and `AIController` return the same `ActionRequest` type.
  Combat commits actions sequentially, revalidates against the latest state,
  skips defeated Actors, and advances one World Tick after one complete round,
  independently of participant count.
- `explain_action()` exposes Effect outcomes and PMW's semantic causal trace.

All authoritative HP, Mana, shield, Status, cooldown, Field, Dynamics slot,
expiry, and action ledger changes are PMW Law effects.  Python performs strict
validation and computes an immutable ordered plan, but does not mutate the
formal state.  PMW prepares the complete proposal and Scheduler set before
publishing it.

## Verification

Environment: Python 3, repository root, `PYTHONPATH=src:.`.

```text
python3 -m unittest discover \
  -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests \
  -p 'test_gate2_*.py' -v

34 tests, all passed in 0.719 seconds (0.82 seconds process elapsed)
```

```text
python3 -m unittest discover \
  -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests -v

55 Gate 1 + Gate 2 tests, all passed in 3.185 seconds (3.29 seconds process elapsed)
```

The tests include failed-cost and failed-required-Effect atomicity, duplicate
Scheduler handle rollback, all nine Effect templates, all four attribute term
types, three duration clocks, Status stacking/cancellation, Hook cycle and
cooldown limits, controller parity, sequential shield/damage visibility,
Mana/Dynamics mirror synchronization, and participant-count-invariant ticks.

The deterministic executable demo is:

```text
python3 -m experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat
```

It executes two rounds.  Round 1 is Guard then Attack; round 2 is Attack then
Wait.  The clock ends at World Tick 2, the hero at HP 45, and the enemy at HP
39 / Mana 15.  Two independent process runs were byte-identical.  The emitted
canonical line has SHA-256
`23c8df0cbcf7b61aa521f8a46776a04511207403019c17847ce3553d1ece4c8b`.

`python3 -m compileall -q .../gameplay_v04` and `git diff --check` also pass.

## Deliberate fail-closed boundaries

- One action may not contain two Effects that write the same scoped resource,
  nor two Status writes to the same scoped Actor.  This avoids pretending PMW
  snapshot proposals have imperative order.  A later domain compiler may
  normalize such authoring into one final write.
- A Gate 2 Effect must resolve to exactly one target.  Multi-target fan-out
  awaits an explicit budget and aggregation contract.
- Status periodic behavior currently supports a bounded resource delta plus
  Trait grants.  Arbitrary recursive periodic Effect bundles are rejected.
- Hook dispatch is explicit: combat, weather, harvest, and Status domain code
  calls the typed dispatcher at its named phase.  Gate 2 does not infer hooks
  from names or install a hidden global callback bus.
- Temporary attractor modification sets an absolute target; temporary recovery
  modification is additive.  Final balance magnitudes remain demo fixtures.

These boundaries return validation errors and never fall back to direct Python
WorldState writes.

## Integration-owner review

The owner independently reran the combined suite and reviewed the PMW lowering.
One audit-only defect was found: `payload.writes` recorded base Mana cost rather
than the final cost after modifiers, although the formal PMW write itself was
already correct. The owner changed the audit value to the post-quote shadow and
added a regression that distinguishes the two values. No authoritative state
path was affected by this correction.

After that correction, the owner run passed `55/55` in `3.231 s`, with no
failures, skips, or expected failures. Raw log:
`/tmp/pmw_gate2_owner_tests.log`, SHA-256
`11a9679b6a807ba560b31b486d54c07c52f7a04713983621ede0edeb0ab81107`.

The legacy v0.6 suite also passed `170/170` in `25.463 s`. Raw log:
`/tmp/pmw_gate2_v06_regression.log`, SHA-256
`0faad9c94329542186b125c4f6326a2574c3300ec49133a63b1ea7f7284c9572`.
