# PMW Gameplay v0.4 Gate 5.2 Final Repair Report

Status: **READY_FOR_FINAL_OWNER_SIGNOFF**

Baseline: `645d82dd926c51094fac8089af1e090c0a5ca32c`  
Branch: `feature/pmw-v04-gameplay-foundations`  
Implementation commit: `75ebe9eaaff3e7cd2349bfd33fde58fbb2c0713d`

Gate 5.2 closes the two remaining TODO1 correctness gaps and completes the
engineering evidence needed for owner signoff. It does not declare TODO1
accepted or closed, change PMW Core, start TODO2 collection, freeze a benchmark,
or begin TODO3 production.

## RED evidence

Both owner-review defects were reproduced before repair.

| Defect | Observed failure | Evidence SHA-256 |
|---|---|---|
| P2-01 cross-source Status/Shield | 11 + 17 shield became 11 after all Status instances expired | `b66eae996202b7342e47825f02d8768c533c462afea08631e46c21f4f91683ca` |
| P2-02 multi-Tick time spend | failure after Tick 2 left `sim_time=2` and a partially charged ledger | `6c28283b31bec66ccf4ed30e08564be2d4e71da153cb9b936bb5cfbf99dca12b` |

Independent QA then found two acceptance gaps before final verification:

- temporary shield ownership validation did not compare caster owner or
  action-to-effect source lineage;
- harvest cost conditions used a raw Actor view and therefore could not see a
  legal active Status when computing final duration.

The Status-duration RED log is `/tmp/pmw_gate52_status_cost_red.log`, SHA-256
`8b60c58e03b075b25824ccd5d6c294b8b39ea537a8ac7faefff44f76d929dcd7`.
Both independent findings are fixed and locked by the final QA suite.

## P2-01: Status and shield lifecycle

Status identity for `refresh` and `add_stacks` now includes canonical spec
hash, action source, and caster owner. Different sources using the same
StatusSpec can coexist. `reject` and `replace` retain their explicit
cross-source semantics; replacement releases exactly the old instance's owned
shield layer before the new instance is bound.

Temporary shield ownership is bidirectional and fail-closed:

- a live Status points to exactly one active layer;
- that layer points back to the same Status instance;
- layer and Status caster owners agree;
- the layer `action_id:effect_id` source belongs to the Status action source.

Expiry uses mergeable deltas so simultaneous independent expiries cannot
overwrite each other. Cancellation, damage, refresh, and replacement only
remove the remaining capacity owned by the affected instance. Persistent and
legacy-unowned shields remain outside Status lifecycle control.

The shared attach migration removes invalid pre-5.2 temporary orphans,
preserves valid persistent/legacy layers, clears stale Status pointers, and is
idempotent. Live malformed ownership is rejected before Action commit.

## P2-02: atomic time transactions

`stage_gameplay_session()` now clones the complete managed runtime boundary:
WorldState and Scheduler queue, runtime statistics, revisions, and closure
state. `spend_world_time()` preflights the entire duration, runs every Tick and
Scheduler dispatch on the staged session, and publishes the candidate runtime
only after complete success.

Combat and harvest reuse the same staging and publication helpers. This keeps
their existing whole-operation transactions while preventing nested duplicate
charges. A failure at any Tick or Scheduler callback leaves the live state,
queue, ledger, runtime bookkeeping, identity, and visible trace surface
unchanged.

Harvest now constructs cost-condition context with the common status-aware
Actor view. A legal `has_status(self, basic_guarding)` modifier survives a
checkpoint round trip and changes a two-Tick harvest to exactly three formal
Ticks in its result, clock, and ledger.

## Integration and QA

The production-entry integration test executes:

```text
limited world -> exploration -> harvest -> skill equip -> multi-source shield
-> combat -> status expiry -> rest -> checkpoint -> restore -> budget exhaust
```

The developer Gate 5.2 suite passed 22/22. Independent Role D added five new
counterexamples and then passed 5/5; the combined Gate 5.2 suite passed 27/27.
Role D modified no production module, found no remaining P1/P2 blocker, and
records its unverified model provenance in `GATE52_INDEPENDENT_QA_REPORT.md`.

## Final verification

| Suite | Result | Wall time | Log SHA-256 |
|---|---:|---:|---|
| PMW Core | 254/254 | 26.207 s | `e5e2f75bb3bb7758662aeb0eb087283a703e090d045336b498e4082a35beca77` |
| Old Generative Mechanics | 345/345 | 68.326 s | `1d21efdced5f038cd78f70329273ed5ab4bfe8d3f87692ff6f7ab91e8b388f50` |
| v0.6 | 170/170 | 25.732 s | `0e3d80023609713b13ff2fdb9c9c9403934126ee5e627e184fd51f8c44d021ba` |
| Gameplay v0.4 | 172/172 | 78.165 s | `7711da3840787d3e835a6066f8b3d53a20b1bc57599ab310552c63407937f94b` |

Total: **941/941**, with zero failures, errors, skips, or expected failures.

Two fresh Gate 5 Demo processes produced byte-identical canonical output,
SHA-256 `89c9e21b676c2079967634339954ebf698a04397bf8b385198032a212a7b74b9`.
Checkpoint continuation is covered by developer, integration, and independent
QA tests. `git diff --check` passes. The protected 381-entry manifest remains
`a20fd763cad342ac357a08d94ee96ca42075f215efcbff93c4017b65a8ddd669`.

## Residual boundaries

- Gameplay sessions are single-writer; concurrent optimistic merging is not
  implemented.
- Successful publication replaces `session.runtime`; callers must retain the
  GameplaySession instead of a stale external runtime/state reference.
- Runtime-external irreversible effects must occur after commit.
- Historical corrupt temporary ownership cannot be reconstructed; migration
  removes it while preserving valid persistent and legacy-unowned capacity.
- A registry permits one canonical Status definition per `spec_id`; divergent
  same-ID definitions fail closed.

No remaining Gate 5.2 P1/P2 correctness blocker is known. Final acceptance and
TODO1 closure remain an owner decision.
