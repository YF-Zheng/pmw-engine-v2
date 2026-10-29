# C4.4 Bounded Typed Dynamics Modifier Action Bridge

QUEUED ONLY after C4.3 acceptance. No production authorization during C4.2
source freeze. Native Gameplay DynamicsSource already supports additive rate,
rate multiplier and priority-selected curve overrides, but formal Effect/Skill
material language exposes only modify_rate amount and modify_attractor amount.
The existing public playtest shows Skills affecting an Area's recovery and
players advancing/leaving/revisiting that Area. A real typed curve intervention
should affect existing World Laws rather than add a bespoke Skill-name branch.
This increment is mechanics support, not Alpha integration or a new public
playtest. Full P1/P2 and provider generation remain gated.

## Narrow Mechanism

Add one closed Effect kind dynamics_modifier targeting an existing current_area
Field. Required explicit fields: field_id,rate_add,rate_multiplier,curve,
curve_priority,duration, plus existing id/kind/target/commitment. No amount,
attractor target, arbitrary component path, expression, dynamic curve name,
free resource, new Field or native code. Commitment required; attribute terms
and targeting checks disallowed for this slice. Active on_use only, no passive
source extension. Material must explicitly authorize this new Effect and scope.

Rate_add finite [-1,1],rate_multiplier finite [0,8],curve is one of existing
linear/distance_squared/none,curve_priority strict integer0..31,duration strict
integer1..64. These are trusted language bounds, not mutable candidate limits.
Existing native effective-rate clamps and Field domains remain authoritative;
none overrides stop recovery without changing the baseline curve/rate or
silently dropping other source configuration. Expiry restores current-base
effective behavior, not an activation-time snapshot.

Reuse existing formal staged Action preparation and owned temporary modifier
slot apply/schedule/expire Law lowering. Prepare from current formal Field,
reject missing Field/remote selectors/full capacity and duplicate active curve
priority across temporary AND persistent sources BEFORE publication/cost/Tick.
Only temporary owned slots, no rewriting Field baseline or scalar current value.
Paid Action and existing World Tick advance normally; no second clock. Source
identity derived from request/effect/owner to fit existing source grammar,
expiry handle includes exact request/effect and owned slot guards. Validate
native DynamicsSource against the actual FieldDefinition or equivalent typed
existing profile; do not treat dataclass construction as authorization.

Prevent a new dynamics_modifier sharing its Field/source-slot footprint with
another source-writing Effect in the same Action. Do not change unrelated old
Effect contracts or globally reject previously valid documents. Runtime
preparation must not reuse one free slot for two new writes. Only actual
accepted Engine deltas/schedule/causal events prove activation. Late cascade or
paid-Tick failure rolls back the whole staged session. Registry save/load
rebuild retains the same new semantic Action and Skill canonical hashes.

## Proposed Write Ownership

One DeepSeek implementation worker: effects.py,skills.py,actions.py,
action_compiler.py and NEW gameplay_v04/tests/test_sandbox_dynamics_action.py.
Material parser consumes EFFECT_KINDS already; no materials.py edit unless
Main approves a concrete blocker. No native dynamics/runtime/Engine/clock,
old tests, Observation, Alpha, global configuration or external path changes.
Independent QA: distinct NEW test_sandbox_dynamics_action_review.py,
C4_DYNAMICS_ACTION_REVIEW.md/evidence/c4_dynamics_review* only. Main owns design,
actual baseline, supplemental probes, frozen regression, counters and checkpoint.
Four production files is proposed scope, not yet an authorization to edit.

## Real Acceptance Evidence

- Same parsed Skill on normal player/NPC in two compatible Areas, using real
  registry/equipment/timed submit. Real rate/curve diagnostics and subsequent
  actual Tick evolution differ quantitatively; costs paid exactly once.
- One normally paid none-curve override freezes recovery while actor leaves
  its Area; other Area keeps evolving. Exact expiry restores CURRENT baseline.
- Existing lower and higher priority independent modifiers survive exact
  owner/handle expiry; higher winner then lower then baseline, no sticky curve.
- Add/multiply order and stable rate clamp verified against hand calculations,
  not calling the same reference evaluator to generate the expected answer.
- Invalid/null/bool/nonfinite/range/unknown field/material/remote/capacity/
  duplicate-priority/multiple-source cases reject without any publication,
  costs, time, revisions, stats, schedule or registry mutation.
- Genuine Engine cascade and late World-Tick exception rollback; deterministic
  save/load continuation and current-state changes without catalog rebuild.
- Keep every accepted old test and native Engine/Alpha byte-identical. Full
  frozen cross-module suite and independent review before local checkpoint.

Do not claim complete seven-Operator language, global CPU/query/per-Tick budgets,
unit/Discrete/Derived catalog or ten complete P1 scenarios from this slice.
Stop/close safely near20:10 +08:00; do not start an oversized final increment.
