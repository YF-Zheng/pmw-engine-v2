# PMW Gameplay v0.4 Gate 5.2 Independent QA Report

Role: **D (independent adversarial QA)**  
Reviewed baseline: `645d82dd926c51094fac8089af1e090c0a5ca32c` plus the shared Gate 5.2 worktree  
Branch: `feature/pmw-v04-gameplay-foundations`  
Verdict: **PASS - READY_FOR_FINAL_OWNER_SIGNOFF**

Role D reviewed production changes but modified no production Python module. Its
only implementation artifacts are this report and
`tests/test_gate52_independent_qa.py`.

## Agent provenance

This audit ran as a separately delegated subagent. The collaboration API did
not expose a model selector or reasoning-effort selector. Model identity and
reasoning effort are therefore **unverified**; no Luna, Terra, or other named
model configuration is claimed.

## Defects found independently during QA

The first review build exposed two additional acceptance gaps. Both were
reported with minimal counterexamples before production repair:

1. **Incomplete temporary-shield ownership validation.** A live temporary
   layer whose `owner_id` had been changed from `actor_0` to another actor still
   passed `validate_status_shield_ownership()`. The validator and migration now
   require caster equality and an `action_id:effect_id` layer source belonging
   to the owning Status source. Runtime corruption fails closed before Action
   commit; historical corrupt temporary layers are discarded without touching
   persistent layers.
2. **Status-blind harvest duration modifiers.** A real `basic_guard` created an
   active `basic_guarding` Status, but a legal `has_status` harvest cost
   modifier did not apply because harvest constructed its condition context
   from the raw Actor component. Harvest now uses the common status-aware Actor
   view. The reproduced two-Tick harvest becomes three Ticks, and the formal
   ledger, Tick results, and `sim_time` all consume exactly three.

The final independent suite locks both repairs. No further P1 or P2 defect was
found after repair.

## Independent counterexamples

### Status and shield ownership

- Both caster-owner mismatch and action-source-lineage mismatch are rejected by
  the ownership validator and by the Action precommit boundary with no state
  mutation.
- Migration removes a corrupt temporary layer, clears its Status pointer, and
  preserves an unrelated 23-point persistent layer exactly.
- After two different sources grant 11 and 17 points, damage consumes the
  deterministic oldest layer first. Refreshing both sources moves lifecycle
  ownership but does not restore consumed capacity; the total remains 24.
- The combined Gate 5.2 suite also covers both application/expiry orders,
  staggered lifetimes, cancel versus natural expiry, `refresh`, `reject`, and
  `replace`, persistent/temporary mixing, checkpoint continuation, legacy
  scalar migration, and orphan migration.

### Time transaction boundary

- Controlled exceptions injected after Tick 1, 2, and 3 of a three-Tick spend
  preserve the exact pre-call `WorldState`, runtime statistics, revisions,
  closure flag, and live runtime identity.
- A real active Status changes harvest duration from two to three. The returned
  duration and Tick tuple, world clock, and budget ledger all agree on three.
- The combined suite verifies insufficient-budget preflight, Scheduler-stage
  failure rollback including its pending queue, checkpoint continuation,
  identical move/rest/offline accounting, and no duplicate charge through
  combat or harvest nesting.

### Integrated production path

`test_gate52_integration.py` completes the required authoritative path:

```text
limited world -> exploration -> harvest -> skill equip -> multi-source shield
-> combat -> status expiry -> rest -> checkpoint -> restore -> budget exhaust
```

It uses production Gameplay entry points and validates ownership before and
after checkpoint continuation. The test passed in both the focused Gate 5.2
run and the complete Gameplay run.

## Final test evidence

Dedicated independent adversarial tests:

```text
PYTHONPATH=src:. python3 -m unittest \
  experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate52_independent_qa -v

Ran 5 tests in 0.874s
OK
failures: 0
errors: 0
skipped: 0
log: /tmp/pmw_gate52_independent_qa_targeted.log
log SHA-256: 698613520a0b0609bd2eb2577584613cf11f4cd34fffeba0abea9cd25fdc833f
```

All Gate 5.2 repair, integration, and independent QA tests:

```text
PYTHONPATH=src:. python3 -m unittest discover \
  -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests \
  -p 'test_gate52*.py' -v

Ran 27 tests in 4.849s
OK
failures: 0
errors: 0
skipped: 0
log: /tmp/pmw_gate52_independent_qa_all_gate52.log
log SHA-256: 2f535730f1dea7cf6db479b35e0743c91fb5e727490a0bec0c36d072970294c7
```

Complete Gameplay v0.4 suite:

```text
PYTHONPATH=src:. python3 -m unittest discover \
  -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests \
  -p 'test_*.py' -v

Ran 172 tests in 79.231s
OK
failures: 0
errors: 0
skipped: 0
log: /tmp/pmw_gate52_independent_qa_gameplay.log
log SHA-256: 29d3af3fabbfa561b6ebf2c2d51199d8f4401d76f3e9418783ad9f3fa5c72edf
```

## Residual risks and boundaries

- Gameplay transactions retain the Engine's single-writer session contract.
  Concurrent mutation of one `GameplaySession` is not supported.
- Successful staged publication replaces `session.runtime`; code must retain
  the `GameplaySession`, not a stale external reference to its prior runtime or
  state object. Failed publication leaves both references unchanged.
- External irreversible effects such as network or filesystem writes are not
  transactionally rolled back and must not run inside a precommit Gameplay
  transaction.
- A registry admits one canonical Status definition per `spec_id`; divergent
  same-ID definitions are rejected rather than concurrently aliased. Runtime
  status identity additionally includes canonical hash and source ownership.
- Corrupt historical temporary-layer provenance cannot be reconstructed.
  Migration conservatively drops that temporary layer while preserving valid
  persistent and legacy-unowned shields.

These are explicit architecture boundaries rather than open Gate 5.2 defects.
Independent QA found no remaining P1/P2 blocker and recommends
`READY_FOR_FINAL_OWNER_SIGNOFF`. It does not declare TODO1 owner acceptance or
closure.
