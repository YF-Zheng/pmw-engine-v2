# GCCP F2 Engine-First Pilot v0.1 Report

## Status

**PASS for the stated minimal F2 experiment**, with explicit adapter boundaries.
The physical world, capability authorization, one-shot resource receipts, time,
and four-Tick terminal evolution execute through PMW; the final stability
predicate is an explicitly frozen experiment adapter. The original reference program was
unavailable, so equivalence means agreement with the independently reconstructed
mathematical semantics implied by the task's three published anchors.

## Cycle record

### Cycle 0 - Baseline

**Question:** Is the reference prototype available, and can F2 use frozen APIs?

**Engine execution:** Repository, all Git refs, attachment directory, Gameplay
handoff, and public API sources were inspected.

**Result:** No `gccp_f2/f2_minimal.py` or reference README exists. Gameplay can
host F2 through compiled experiment Laws without modifying Core.

**Mismatch:** The original implementation cannot be reproduced verbatim.

**Next action:** Reconstruct only the semantics forced by the published priors
and Q values, while preserving the missing-source caveat.

### Cycle 1 - Physical causality

**Question:** Can PMW express the exact M/S recurrence?

**Engine execution:** Real `pmw.v04.world_tick` events evaluated mutually
exclusive H Laws. `S_next` inlines the same `M_next` expression because all
effects in one event read the same snapshot.

**Result:** No intervention gives S 100 -> 98 for both roots. A compatible probe
on the true root gives +2; an unrelated intervention gives -2. W/R recover to
their baselines while M/S history remains. Correct four-Tick repair reaches
116.5; wrong repair reaches 92. Full traces are in `engine_physics.json`.

**Mismatch:** None.

**Next action:** Add a public allowlist and one-shot capability lifecycle.

### Cycle 2 - Observation boundary

**Question:** Do H and X leak before evidence is acquired?

**Engine execution:** `ActorObservationBuilder` provides public Gameplay state;
an F2 allowlist adds S and capability receipts but excludes the private component
and all trusted traces.

**Result:** All four initial worlds have byte-identical public observations and
legal actions. Calibration observations differ by X but remain identical across
H, so the H posterior stays 0.65/0.35.

**Mismatch:** Gameplay's generic observation intentionally publishes every Area
Dynamics Field, so H/X/M cannot be stored there. They remain private component
state and are never included in the generic revision token given to the solver.

**Next action:** Implement material-backed dynamic probe registration.

### Cycle 3 - Capability investment

**Question:** Is probe creation materially irreversible and time-bearing?

**Engine execution:** A forge PMW Event consumes the only diagnostic blank and
records the chosen probe. `MechanismRegistryRuntime.install_blueprint` registers
the material-authorized skill; `change_loadout` equips its exact hash/version;
one formal exploration Tick follows. Probe use commits a one-shot receipt and
always spends a Tick, including interface failure.

**Result:** A second forge or probe is rejected without changing WorldState,
Registry manifest, or time. Repair consumes a separate kit.

**Mismatch:** Gameplay has no single public transaction spanning inventory
Event + Registry rebuild + Loadout + time. The experiment prevalidates this
deterministic sequence, but crash-atomicity across those APIs remains adapter
logic rather than one Engine transaction.

**Next action:** Solve by fresh reconstruction rather than live rollback.

### Cycle 4 - Exact belief planning

**Question:** Do Engine transitions reproduce the three reference optima?

**Engine execution:** Every belief successor reconstructs a fresh hidden world,
replays its public action history, executes the candidate action, groups equal
public observations, and performs exact Bayes updates.

**Result:**

| cf | ci | Engine optimum | Value |
|---:|---:|---|---:|
|0.10|0.03|`calibrate`|0.870|
|0.10|0.23|`forge_water` / `forge_resonance`|0.725|
|0.40|0.03|`repair_water`|0.650|

All three match the reconstructed reference optima. At the third point,
adaptive `Q(calibrate)=0.620`, not the fixed-path 0.570: after calibration the
solver may rationally abandon expensive forging and repair Water. This is the
required replanning behavior, not a mismatch in the root optimum.

### Cycle 5 - Counterfactuals

Changing H changes the consequence of the same compatible probe. Initial
observations remain identical. Public costs flip the optimal initial action at
the three specified points. With probe diagnostic observations withheld, the
optimum is `repair_water=0.650`; `calibrate=0.620` and direct forge=0.550, so the
long-term information value disappears.

In this pilot's native feasibility economy, normalized `cf/ci` penalties are absent. The unique
blank, one-shot probe, three preparation Ticks, and repair kit are hard
constraints. `calibrate` is optimal for this defined objective with value 1.0; direct forge is
0.825. Thus the reference cost flip does not survive the different economy.

## Required answers

1. **Real PMW transitions:** W/R interventions, dynamics recovery, M/S physics,
   material and repair receipts, Action effects, four-Tick terminal evolution,
   Scheduler advancement, and TimeLedger charging.
2. **Adapter logic:** public observation projection; composite orchestration of
   forge/Registry/Loadout/time; exact belief enumeration; the explicitly frozen
   terminal stability predicate and equivalent-mode normalized utility.
3. **Reference equivalence:** all three published root optima and values match
   the independently reconstructed model. Original source equivalence cannot be
   claimed because its files were unavailable.
4. **Observation leakage:** none before evidence. Four initial public documents
   are identical. Calibration reveals only X. Probe success/failure reveals
   interface compatibility after the irreversible investment; raw trace and
   failure internals are not public.
5. **Irreversibility:** the only blank changes 1 -> 0 through a PMW Law, one
   exact probe Blueprint is installed and equipped, and the receipt blocks both
   rebuilding and reuse.
6. **Cost flip:** yes in equivalent mode at the three specified public costs.
7. **Native economy:** yes, it changes the conclusion: without normalized
   utility penalties, calibration dominates in this pilot while resources/time
   remain feasibility constraints. Exploration damage is not separately priced
   beyond the binary terminal predicate, so this is not a general time-cost result.
8. **Shortcuts:** direct public access to Registry, Loadout, checkpoints,
   traces, basic actions, and arbitrary field writes is excluded. Reforge,
   reprobe, skipped Tick, and duplicate repair tests reject without mutation.
9. **Engine expression gap:** no gap for F2 physics. The only missing primitive
   is a cross-Registry/inventory/action/time composite transaction.
10. **Next question:** test whether noisy or delayed public responses preserve
    capability investment value without exposing interface compatibility as a
    discrete result. This is a future F2 extension, not F3/L1 work.

## Scope limit

This result establishes one four-world, exact-enumeration decision problem. It
does not establish autonomous goal discovery, general GCCP superiority, an LLM
deficit, or a benchmark claim.

## Residual engineering boundaries

- `F2Transition` is a trusted evidence object and contains raw EventResult and
  CausalTrace. The solver deliberately consumes only `_prep_observation`, but a
  future external Agent integration should use a separate public return type so
  a caller cannot accidentally receive H-bearing law IDs.
- Forge prevalidates and tests normal rejection atomicity, but inventory Event,
  Registry install, Loadout change, and time spend are not one crash-atomic
  transaction across APIs. A process interruption can leave a partial commit.
- Native time is modeled as a three-preparation-Tick feasibility horizon. It is
  not assigned an additional scalar utility penalty, and no broader economy
  conclusion is claimed.
