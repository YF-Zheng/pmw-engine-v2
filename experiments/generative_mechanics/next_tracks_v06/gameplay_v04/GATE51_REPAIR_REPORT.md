# PMW Gameplay v0.4 Gate 5.1 Repair Report

Status: **READY_FOR_OWNER_REVIEW**

Baseline: `326d29b4e6887ff257115dbb07e06d984deec1af`  
Branch: `feature/pmw-v04-gameplay-foundations`
Implementation commit: `23bce15b5055ef97b3e4179d3958f03d34b5df51`

Gate 5.1 repairs the final gameplay integration defects. It does not modify PMW
Core, start TODO2 collection, freeze a benchmark, or begin TODO3 production.

## Failure reproduction

All four owner-review defects were reproduced before repair.

| Defect | Reproduction evidence | SHA-256 |
|---|---|---|
| P1-01/P1-03 combat time and action authority | `/tmp/pmw_gate51_combat_red.log` | `f1e8910979c2e1149d3ada8062f3c0d18b2b4a629bdd015e220bccbed6eb1255` |
| P1-02 harvest/time split commit | `/tmp/pmw_gate51_harvest_red.log` | `c6980adde9e4588c52d40a084ba75f00ac17399e1d82162a041187decb559bcc` |
| P2-04 Guard clearing another shield | `/tmp/pmw_gate51_p204_red.log` | `715697ca7ce6455eeb2d31fc0f810e3f95371a5f80042b75a3474887e823b84b` |

Independent QA then found three additional action-authority bypasses and one
legacy checkpoint failure. The public-resolver and checkpoint red logs have
SHA-256 `041139add04fb465853e4ad170fda2f670b1a9b6e6858c9ce30663bd8bd41199`
and `76dc42c6a572bac117ac3645521f9fb5a92d1c91bf32b39f120f8fb2d4f82745`.

## P1-01: combat time transaction

`run_combat_round()` now defaults to the formal finite-time policy. It
preflights exactly one `combat` Tick before `owner_turn`, action, expiry, or
Scheduler work. The whole round executes against a staged WorldState on the
same Engine/Law set. Only a fully successful sequence is published:

```text
owner_turn(s) -> ordered actions -> combat_round -> time.spend(1) -> world_tick
```

Actor count cannot multiply the charge. Any late action or Tick failure drops
the staged runtime, preserving state, queue, ledger, and runtime bookkeeping.
Old isolated fixtures must explicitly request `time_policy="unbudgeted_fixture"`;
that mode refuses a world containing a formal time budget.

## P1-02: atomic harvest

`resolve_harvest()` is now the sole authoritative harvest behavior. On a staged
WorldState it validates the request, computes the final condition/luck-adjusted
duration, applies Mana/resource/inventory/ecology changes, emits the formal
harvest event, charges time, and advances every required Tick/Scheduler step.
The live session is replaced only after all steps succeed.

Each successful request atomically creates a formal receipt relation keyed by
`request_id`. Replays are rejected both immediately and after checkpoint
restore. `HarvestOutcome.time_result` exposes the already-completed time charge;
callers no longer perform a second `spend_world_time()`. The existing absolute
`1e-12` overharvest boundary remains unchanged.

## P1-03: action authority

The public `resolve_action()` and `submit_primary_action()` both enforce the
same primary-action authorization used by combat and AI live revalidation.
Non-basic skills require an exact six-slot equipped reference containing the
current ID, version, canonical hash, kind, and enabled formal registry entry.
Stowed, other-owner, disabled, revoked, or stale references fail before
`owner_turn` or any action effect.

Only the shipped canonical Attack, Guard, and Wait definitions are slot-free.
The `builtin` field is not an authority token. Public callers also cannot select
Hook execution mode; installed Hook identity and its exact effect bundle are
validated before the private trusted executor is used.

## P2-04: source-owned shields

Actors now carry a bounded eight-slot `pmw_gameplay_shields` component while
`pmw_gameplay_actor.shield` remains the public aggregate. A layer records its
source, owner, grant, remaining value, stable sequence, and optional owning
status instance.

- Different sources and casters coexist additively.
- Damage consumes layers by `(sequence, slot)`.
- Same-source refresh never stacks or restores consumed capacity.
- Status expiry/cancel removes only that layer's remaining contribution.
- A persistent ShieldEffect has no status owner and remains until consumed.
- Checkpoints preserve the complete layer state and continuation.

The common Gameplay runtime attach boundary performs an idempotent legacy
migration. An old scalar shield becomes an unowned legacy layer and old status
slots receive `shield_layer_slot=None`; historical Guard cannot claim or erase
unknown shield provenance.

## Integrated scenario

`tests/test_gate51_integration.py` uses only production entry points:

```text
3-Tick world -> exact skill equip -> two combat rounds -> Guard expiry
-> lucky harvest -> zero remaining time -> rejected round -> registry checkpoint
```

The rejected round is byte-semantically state neutral, and restored time,
shield/status state, receipts, Scheduler, and WorldState match the source.

## Final verification

| Suite | Result | Wall time | Log SHA-256 |
|---|---:|---:|---|
| PMW Core | 254/254 | 26.26 s | `b43f49ec491f1a97748671fe81d2e26a339b3795f2f717f1ee36011750d5b052` |
| Old Generative Mechanics | 345/345 | 68.59 s | `9c1231b4cc97f74f16b40d47facb9e4647b6cae4f6e369c3e3bb00b097e52968` |
| v0.6 | 170/170 | 25.86 s | `b7ba60a7cc7c51d8271524039e3c905358001b3d59628b5ed68594d7dfbb44b8` |
| Gameplay v0.4 | 145/145 | 76.57 s | `41dca1121f72231593c2dbc70362494522ce6c3bfdd5385b7b069da6ca55cb07` |

Total: **914/914**, with zero failures, errors, skips, or expected failures.

Two fresh Gate 5 Demo processes produced byte-identical canonical output,
SHA-256 `db9b7877b19c4d664bbf0df4baa8bf7d9182b36d0b36c355705d0b5b868b575b`.
`git diff --check` passes. The 381-entry protected manifest remains
`a20fd763cad342ac357a08d94ee96ca42075f215efcbff93c4017b65a8ddd669`.

## Residual boundaries

- Historical scalar shields have no recoverable provenance and are therefore
  preserved conservatively as a legacy layer until consumed.
- The private raw action executor is an internal Python boundary, not a sandbox
  against malicious code already executing in-process.
- Gameplay transactions follow the existing single-writer session contract.
- The explicit unbudgeted mode exists only for old test/demo fixtures.

No remaining Gate 5.1 correctness blocker is known.
