# Sandbox v1: Frozen Boundaries

日期：2026-10-29。规范来源：`DEVELOPMENT_CONTRACT.md`。
此文档冻结复用边界，不代表 P1 已验收。

## Architecture

- World truth remains `src/pmw/types.py:WorldState`. Engine, matcher, scheduler,
  revision, Observation and causal traces remain the existing `src/pmw` core.
- Catalog owns state types, units, ranges, material capabilities, process
  definitions and relation topology. Untrusted Skill IR never authors Law data
  or Python code directly.
- Reuse v06's six typed catalog objects and seven operator lowerings; extend
  their semantics rather than creating a separate world simulator.
- The production Alpha clock remains Gameplay's `pmw:v04:clock`, advanced by
  `spend_world_time` / `advance_world_tick`. Never drive both the normalized v06
  clock and the Gameplay clock in one Alpha session.
- Reuse Gameplay's material authority, registry, observation and staged action
  transactions. Skill Designer receives only authorized projections and catalog
  data, not WorldState, snapshots, raw traces or hidden completion conditions.
- API calls occur outside transactions. Parse/type/capability/budget checks and
  sandbox execution precede registration; model failures never consume material.

## Existing Tick Contract

Core `tick` counts scheduled root dispatches, NOT player World Ticks.
Gameplay `clock.next_step` / `last_completed_step` are the player tick counter.

1. Stage the complete action and time payment on an isolated Gameplay session.
2. Settle immediate action effects through existing event laws/state closure.
3. For each requested world tick, dispatch due schedules in `(time, event_id)`
   order, completing each causal cascade and state closure before the next root.
4. Validate active curve priorities; dispatch one `pmw.v04.world_tick` event.
5. Existing compiled laws calculate dynamics from the event's read state.
   Ecology transition event Laws read that SAME pre-event state, not the newly
   evolved value. Their baseline writes publish alongside the old-baseline
   dynamics; the next world tick selects the new baseline. Proposal resolution,
   subsequent state-Law closure and publication are deterministic. Clock
   completion is a Law. This clarifies existing semantics, not a phase change.
6. Gameplay processes/hooks MUST join these phases, not add another clock.
   Explicit later-phase events may be lowered through the same Engine, but any
   phase change requires a versioned contract and ordering regression tests.
7. Session-level consequences/endings run on staged state; publish only after
   the full action, event cascade and time request succeeds.

Expiry at time T happens BEFORE dynamics at T. A duration-N modifier activated
at time 0 therefore does not contribute to the dynamics event at time N.
This existing boundary is preserved rather than silently redefining durations.

The pure `dynamics/reference.py` oracles are test-only, never authoritative.
The separate historical v06 clock remains valid only for standalone v06 demos.

## Numerical Semantics

Gameplay already supports bounded linear and distance-squared recovery:

```text
linear:           x' = clamp(x + r * (target - x), min, max)
distance_squared: x' = clamp(x + r * (target - x) * abs(target - x), min, max)
```

Width = max - min > 0. Linear rate is in [0, 1]; distance-squared rate is in
[0, 1 / width]. Effective rate combines sorted additive and multiplicative
source contributions, then clamps to the chosen curve's stability limit.
Targets combine by normalized nonnegative weights; curve overrides use unique
priorities and reject ties. Expiry removes only its owned source contribution.

P1 first increment adds explicit `none` recovery (x' = clamp(x, min, max)),
which is exactly x' = x for valid in-range state, retaining independent
external impulses and world laws. Zero-rate linear remains backward compatible,
but is not a substitute for declaring a no-recovery mode. Existing default
Blueprints and both old curves remain compatible. Every pre-existing
linear/squared Law data entry matches the original HEAD lowering; only new
override variants are added (evidence/p1_old_law_comparison.json).

The 2026-10-29 ecology routing fix deliberately expands base-formula Laws:
live `baseline.curve` chooses linear, squared or none without rebuilding the
session. Canonical IDs (`base`, `base_distance_squared`, `base_none`) depend on
the formula, not construction-time profile curve, so staged and reconstructed
sessions have identical causal traces. Numerical expressions, rate limits,
source layering and expiry are unchanged. Historical byte-parity evidence
above belongs to the first increment; it is not a claim about this expanded
catalog. One Field with 2+2 source slots plus clock grows from 28/29 to 31 Laws.

## Remaining P1 Gates

The generic Process has bounded conversion, modification and expiry tests on
the existing clock. The 2026-10-29 typed start increment exposes one trusted
template through data-only SkillBlueprint, formal equipment and staged Action
mana/time payment for player/NPC. Process and all Stock endpoints must be local
to the acting Area. Controller Laws are trusted static checkpoint configuration,
never candidate JSON. Material capability is not one-off inventory consumption.
It is NOT exposed in Alpha inventory/UI or automatic NPC Observation/planning;
Process modification, global event/query/process budgets and seven-operator
exposure still require integration. Controller activation scans entity maps for active
writer/instance checks; reducing this privileged preflight's global work is a
future locality task, not an already-proved constant-work guarantee. A subset
passing does not close P1. Ten contract scenarios must use the formal runtime.
