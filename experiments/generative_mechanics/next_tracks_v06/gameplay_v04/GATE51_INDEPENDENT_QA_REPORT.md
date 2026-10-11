# PMW Gameplay v0.4 Gate 5.1 Independent QA Report

Role: **D (independent adversarial QA)**  
Reviewed baseline: `326d29b4e6887ff257115dbb07e06d984deec1af` plus the shared Gate 5.1 worktree  
Branch: `feature/pmw-v04-gameplay-foundations`  
Verdict: **PASS**

Role D reviewed production changes but modified no production Python module. Its
artifacts are this report, `tests/test_gate51_independent_qa.py`, and the small
white-box correction in `tests/test_gate5_independent_qa.py` that makes an old
trusted-resolver atomicity test call the now-private primitive explicitly.

## Agent provenance

This audit ran as a separately delegated subagent. The collaboration API did
not expose a model selector or reasoning-effort selector, so no named model or
effort level is claimed.

## Defects found independently during QA

The first review build did not pass. Role D found four additional integration
defects and supplied minimal counterexamples before their production fixes:

1. **Public primary-action bypass.** Calling `resolve_action()` directly let an
   unequipped `mist_bolt` reduce the target from 40 HP to 37 HP while all six
   active slots were empty. The public resolver now performs authoritative
   equipment authorization; the raw executor is private and used only by
   trusted internal code and white-box tests.
2. **Forgeable privileged action identity.** A stronger action registered under
   a basic action ID with `builtin=True` was accepted as slot-free. The three
   slot-free actions are now bound to their shipped canonical definitions;
   arbitrary builtin metadata is not authority.
3. **Forgeable Hook mode.** The old public resolver accepted caller-provided
   `execution_kind="hook"` and `hook_context`, even when no Hook was installed.
   Those parameters are no longer public. Hook execution validates the exact
   installed Hook and effect bundle before using the private executor.
4. **Pre-Gate-5.1 checkpoint crash.** An old active status slot without the new
   `shield_layer_slot` field raised `DSLResolutionError` during `owner_turn`.
   The common Gameplay runtime attach boundary now performs an explicit,
   idempotent schema migration before Law evaluation.

All four counterexamples pass after repair.

## Independent counterexamples

### Combat transaction and time authority

- Exhausted time rejects before action, owner-turn expiry, Scheduler work, or
  ledger mutation.
- An invalid target discovered after staged `owner_turn` causes the entire
  round candidate to be discarded.
- The successful trace exposes Action, combat-round, time-spend, and world-tick
  events at their formal boundaries; one round consumes exactly one Tick.

### Harvest transaction

- A two-Tick harvest was instrumented so the first Tick completed and the
  second Tick raised. Inventory, Mana, resource abundance, degradation,
  receipts, time ledger, clock, and scheduled events remained identical to the
  pre-request `WorldState`.
- The developer regressions additionally cover zero/short/exact budget,
  condition- and luck-adjusted final duration, resource/Mana/permission
  failures, overharvest, checkpoint replay, and duplicate request receipts.

### Controller and live-action authority

- The public resolver rejects an unequipped registered skill without mutation.
- Requests cannot inject `builtin`; a non-basic action marked builtin is not
  slot-free.
- Public callers cannot self-declare Hook execution.
- Existing regressions cover stowed, other-owner, disabled, stale version/hash,
  Human/AI, and all three canonical basic actions.

### Shield ownership, Scheduler, and checkpoint

- Two independently owned temporary shields (11 and 17) were expired in both
  possible clock orders. Each expiry removed only its remaining contribution.
- Stable damage ordering, partial consumption, same-source refresh without
  restoration, ordinary ShieldEffect behavior, and source-bound expiry are
  covered by the combined Gate 5.1 suite.
- Save/load preserves shield layers and produces the same continuation.
- A simulated pre-Gate-5.1 world without the shield component or new status
  field now attaches and advances safely. Unknown historical aggregate shield
  is migrated to an unowned legacy layer and is not erased by Guard expiry.

## Final test evidence

Dedicated independent Gate 5.1 suite:

```text
PYTHONPATH=src:. python3 -m unittest \
  experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate51_independent_qa -v

Ran 10 tests in 1.319s
OK
failures: 0
errors: 0
skipped: 0
log: /tmp/gate51-independent-qa-final.log
log SHA-256: 616439a00134d5a919cd0ede011b8cb367badf91dedc2f4e97c81638eafb21fb
```

Complete Gameplay v0.4 suite after all QA-driven repairs:

```text
PYTHONPATH=src:. python3 -m unittest discover \
  -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests \
  -p 'test*.py' -v

Ran 145 tests in 76.553s
OK
failures: 0
errors: 0
skipped: 0
log: /tmp/gate51-gameplay-qa-final.log
log SHA-256: 6be51784dfa281aed4b7353da1102d52fcf5f2b2cf10ba92c96e1fc07ad87951
```

`git diff --check` also passed during the final QA review.

## Residual risks and boundaries

- Historical scalar shield values contain no source provenance. Migration
  therefore preserves them as a legacy layer; it cannot infer which old status
  originally granted them. This is conservative and prevents destructive data
  loss, but an old temporary shield may remain until consumed.
- `_resolve_action` is a Python-private trusted primitive, not a security
  sandbox against malicious code executing inside the process. Every supported
  external/controller API uses the authorized public boundary.
- Staged combat and harvest transactions follow the engine's single-writer
  session model. Concurrent mutation of one `GameplaySession` is outside the
  current runtime contract.
- `unbudgeted_fixture` remains an explicit test/demo compatibility mode and
  refuses to bypass a world that contains a formal time budget.

No remaining Gate 5.1 correctness blocker was found. Independent QA approves
the repair set for owner review.
