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

## Bounded Process Modification Skill Contract

The accepted `process_modify` Effect controls rate and/or remaining ticks on
exactly one already-running trusted Process belonging to the acting player/NPC.
The Process and every input/output Stock endpoint must be in current_area.
Data includes process_template_id and at least one of process_rate (finite,
positive, non-bool) or process_remaining_ticks (positive integer, non-bool).
Explicit nulls reject. Runtime template maximums, completed Tick boundary,
input-domain/availability, owner/writer checks and fixed hard deadline remain
authoritative. Paused/stopped/expired modification is denied.

This is required-commitment active on_use only, with no attribute/sensing/
evadability bypass. It costs five material capability-budget points, not a new
inventory debit. One Action may contain at most one Process control operation:
start OR modify; valid mixed operations and duplicate controls reject.

Read-only ProcessController.prepare_modify shares native controller calculation.
The Action compiler emits PROCESS_MODIFY_EVENT; existing trusted Process Laws
perform every write and expiry reschedule. Acceptance requires the exact
`pmw.v04.sandbox.process.<profile_id>.modify` match, expected component after
values and the exact scheduled expiry, not an arbitrary Law ending in .modify.
Existing staged Action plus timed submission rolls back the complete cascade
and every paid tick on failure. No second world simulator or clock is added.

Expiry at T still precedes conversion at T. Productive elapsed/remaining ticks
can diverge from wall time on saturated ticks. The pre-existing native rate-only
hard-deadline false rejection was preserved at0e4e45b and documented in
`evidence/p1_process_modify_saturation_baseline.json`. Subsequent C1 fixes that
guard using actual future expiry, preserving duration/remaining/progress and
harddeadline. C1 also fixes strict required-key accounting so rate-only and
remaining-only really parse, rather than merely being a documented contract.
Native pause/resume/progress policy
and broader Skill exposure require separate acceptance.

Public semantic footprint is `process:<template>:configuration`. Actor-safe
projection excludes both Process control Actions and private controller/Stock
authority; basic_wait still works. It is not a Process forecasting/planning gate.
Frozen acceptance evidence: `P1_PROCESS_MODIFY_INCREMENT.md` and independent
`P1_PROCESS_MODIFY_REVIEW.md`, 759 tests / 3,152 subtests.
C1 complementary evidence: `C1_RATE_EXPIRY_INCREMENT.md`, 776 tests / 3,180
subtests, all276 Python hashes unchanged. Real timed pure-rate player/NPC calls
pay one Mana and Tick, expire at3 before conversion, and do not extend lifetime.

## Remaining P1 Gates

The generic Process has bounded conversion, modification and expiry tests on
the existing clock. The 2026-10-29 typed start increment exposes one trusted
template through data-only SkillBlueprint, formal equipment and staged Action
mana/time payment for player/NPC. Process and all Stock endpoints must be local
to the acting Area. Controller Laws are trusted static checkpoint configuration,
never candidate JSON. Material capability is not one-off inventory consumption.
It is NOT exposed in Alpha inventory/UI or automatic NPC Observation/planning;
Process pause/resume/progress controls, global event/query/process budgets and seven-operator
exposure still require integration. Controller activation scans entity maps for active
writer/instance checks; reducing this privileged preflight's global work is a
future locality task, not an already-proved constant-work guarantee. A subset
passing does not close P1. Ten contract scenarios must use the formal runtime.

## C2 Positive Finite Source Contract

C2 bounded finite Stock-to-Field source is ACCEPTED: frozen full regression793 passed/3,195 subtests in388.43s, exit0, all279 Python hashes unchanged. Owner11/7, independent6 methods, Main focused53/30 and complementary8 denials pass. Reports: C2_STOCK_FIELD_DRIVE_INCREMENT.md / C2_STOCK_FIELD_DRIVE_REVIEW.md; complete metadata/log: evidence/c2_drive_frozen_full_regression_meta.json / c2_drive_frozen_full_regression.txt. Existing clock, Engine, staged Action, Observation, Alpha and all87 tracked test files at a4ad912 remain protected. Positive finite source only; no sinks/open source/universal Field units, Alpha UI, complete P1/P2 or generation claim. Local checkpoint subject: feat: add bounded stock-fed field sources. Next independent task C3_RELATION_MODIFIER_DESIGN.md, then C4_CONDITION_BUDGET_DESIGN.md and remaining P1 gates.

Each child accepts min(rate, stock*coefficient, current after-root headroom), then publishes represented Field gain and Stock debit in one Law. If either represented difference vanishes, both are no-op. Sorted profile ID ordering, one owned lifecycle and last-step deduplication are explicit. Expiry atT precedes root TickT. Candidate fields are only trusted profile ID/rate/duration; current-area/owner/material bounds and exact Law/schedule verification remain authoritative. No Drive input may overlap configured Process input/output even inactive, guarded at real compile_content. Actor-safe forecasts omit private controller/action/source authority; basic wait remains functional.

## Continuous C3 Bounded Overlay

C3 bounded existing typed Relation enable/disable overlay is ACCEPTED. Full frozen regression: **804 passed, 3,226 subtests passed in415.43s**, exit0; all282 Python hashes unchanged. Independent QA six methods, owner five methods, Main cross-focus64/48 pass. Main complementary timed parsed/equipped enable player/NPC actually match .modify.on, pay Mana1/Tick1, change opt-in downstream availability false->true, and expire to current disabled base. Independent QA formal disable/current-base/expiry/cascade/late-tick/replay remains separately attributed. Reports: C3_RELATION_MODIFIER_INCREMENT.md / C3_RELATION_MODIFIER_REVIEW.md. Metadata/log: evidence/c3_relation_frozen_full_regression_meta.json / c3_relation_frozen_full_regression.txt. All89 previously tracked test files at9f75122 remain byte-for-byte unchanged. Engine/clock/Observation/Alpha are untouched. No graph creation/deletion/retarget, generic travel/locality availability integration, Alpha UI, full P1/P2 or generation claim. Next independent target: C4_CONDITION_BUDGET_DESIGN.md, then C4_PASSIVE_DISPATCH_DESIGN.md and remaining P1. Deadline20:10 +08:00 and all accounting/stop rules remain in force.

## Continuous C4.1 Parser Budget

C4.1 bounded shared raw-condition parsing is ACCEPTED. Frozen full regression **835 passed,3,304 subtests passed in381.12s**, exit0,284 Python hashes unchanged; all91 old test files atd613cc9 remain byte-identical. Owner15/14, independent FINAL16 methods, Main89/53 pass. AST parity preserves every typed leaf branch and evaluator; Main trusted-cap depth64/nodes4096 accepts and one-over rejects. Defaults depth16/nodes64/children16 are fresh/shared per parse, root1 and every operator/leaf counts, with path-bearing GameplayContractError before over-deep/over-wide traversal. Candidate JSON cannot raise budgets; trusted callers may choose bounded caps64/4096/256. Reports:C4_CONDITION_LIMITS_INCREMENT.md/C4_CONDITION_LIMITS_REVIEW.md; full metadata/log:evidence/c4_condition_frozen_full_regression_meta.json/c4_condition_frozen_full_regression.txt. Initial17-method defect-persistence assertion moved to a non-collected actual probe before acceptance; original source/report/meta/log preserved,16 real requirement tests unchanged. No old tests/Engine/clock/Observation/Alpha change. No Status condition ingress, new typed leaves, aggregate per-Skill/per-Tick/CPU/query/active-source or full P1/P2 claim. Next actual damage-passive dispatch (C4_PASSIVE_DISPATCH_DESIGN.md), then verified active top-level false-condition gate defect (C4_ACTIVE_CONDITION_DESIGN.md). No game-generation call until full P1/P2, continue sequentially until20:10 +08:00 or real stop/account/budget/blocker.

## Continuous C4.2 Frozen Acceptance

C4.2 automatic Action-produced damage_resolved passive dispatch is ACCEPTED.
Full frozen regression869 passed,3,325 subtests in380.21s,exit0; all287 Python
hashes unchanged. All93 accepted old test files,23 Core Python files and13
Alpha Python files at718be65 retain exact blobs/SHA256. Owner13/8, independent
FINAL21/13, Main cross46/8 pass. Main real finite combat:HP50->40,shield0->7,
Mana20 unchanged,one paid Gameplay Tick,separate actual Engine Hook/root traces.
Reports:C4_PASSIVE_DISPATCH_INCREMENT.md/C4_PASSIVE_DISPATCH_REVIEW.md. Full
metadata/log:evidence/c4_passive_frozen_full_regression_meta.json and
c4_passive_frozen_full_regression.txt; Main protected_after/review_acceptance/
combat_timed evidence separately identifies Main versus independent results.
Both actual Flash workers closed before freeze. Initial independent invented
auto_hook_ prefix oracle is superseded, preserved byte-for-byte;19 other test
ASTs identical and the second changed method only corrects grammar samples,
retaining every PMW-local temp assertion. No production workaround or old-test
weakening. Trusted exact equipped Skill/Action/Hook binding, current staged
sibling state, positive real damage attribution,FIFO shared root caps/dedup,
full rollback/checkpoint continuation verified.

Only managed Action-produced damage notifications,not arbitrary World/Tick or
other advertised legacy triggers. No multi-trigger IR,global CPU/query/per-Tick
budget,full P1/P2,Alpha UI/browser playtest or game-generation claim. Cost cutoff
17:50:19 +08:00:projectCNY198.89962770,safety250.62355584/2000,
P1reserve212.97362318/400,Unknown0,complete. c4_2_cost_snapshot.json subset
USD4.31484982/CNY28.76451484 already included once;97% is pricing only. Closing
Main overhead awaits next ordinal boundary; bootstrap remains separate.
Immediately continue C4.3 active top-level condition gate after scoped local
checkpoint; latest actual stable Process gap pays2Ticks/4Mana despite false
condition (c4_active_main_latest_before.json). C4.4 Dynamics bridge architecture
is queued only,not implemented. All deadline20:10 +08:00/stop/accounting rules
remain; current chat continues without altering paused automation/global config.

## Continuous C4.3 Frozen Acceptance

C4.3 active top-level Skill condition gate is ACCEPTED. A non-null ACTIVE Skill
condition now travels into its Action (trailing default ActionDefinition field;
null/absent omitted from canonical data so legacy Action hashes are unchanged)
and is evaluated on current pre-cost staged state before quote, debit,
reservation or Engine execution. False raises GameplayContractError("action
condition is not satisfied") atomically. Passive Actions stay `always`; C4.2
Hook condition/skip semantics unchanged. Production: actions.py/skills.py only.

Evidence: owner7/2, owner cross92/27, Main cross56/106, independent FINAL8/8,
QA legacy58/2. Main finite combat rollback, canonical AST, historical Basic
hashes, loaded-code and public Alpha API replay (19 actions, clock consistent).
Real Git 576048b archive baseline reproduces the gap (QA's earlier mixed
baseline was rejected; original artifacts overwritten, so no bytewise claim).

First full frozen run FAILED honestly: 1 failed/883 passed/3,335 subtests
(c4_active_frozen_*). The sole failure was the accepted C4.1 positive fixture
whose condition all(null, not(null)) is identically false and had only passed
because conditions were ignored. Main approved one documented legacy-fixture
exception: only that assignment became all(null, not(not(null))); all other
ASTs/assertions identical (test sha256 5bc6d2...ff78 -> 956e6fa8...b560).
Replacement independent reviewer Godel 01a18a8e-510c-7931-9587-c0a11d314db2
(actual DeepSeek Flash, PMW-local temp) ACCEPTED: original false expression
rejects atomically for player and NPC (World/revision/Mana20/budget0of6/Tick0/
schedule unchanged); corrected true expression keeps Mana20->16, 2 Ticks each,
total4/2; focused22/16. C4_ACTIVE_CONDITION_FIXTURE_REVIEW.md.

Second full frozen run c4_active_fixture_frozen: **884 passed, 3,335 subtests
in414.10s**, exit0, 294 Python hashes unchanged. Protected after576048b:
94 old tests, Core23, Alpha13 byte-identical; exactly one old test changed as
reviewed (evidence/c4_active_main_protected_after.json).

Process incident: earlier Pro reviewer Franklin 01a18743-222f-7830-8432-5a83674afd70
wrote one file outside PMW via unvalidated $env:TEMP
(C:\Users\orinzheng\AppData\Local\Temp\head_condition_limits.py). User accepted
and asked to continue; file left untouched. Its review was discarded and all
later worker prompts require PMW-local TEMP/TMP/pycache per command.

Accounting: the resumed main turn 01a18a8c-d2f5-7751-86e4-3b662913c288 runs on
actual tencent/claude-opus-5.5 (rollout turn_context), not GPT-6.1-Sol. It is
priced at official Claude Opus 5.5 standard rates checked 2026-10-30
($4 input/$0.20 cache hit/$20 output per MTok; no long-context tier), recorded
as its own Claude family, never relabelled GPT. c4_3_fixture snapshot subset
USD3.26245498/CNY21.74882988; project USD36.10221855/CNY240.67182974; safety
reserve CNY303.25863582/2000; P1 reserve265.60870316/400; Unknown0, complete.

Scope remains bounded: no new evaluator/clock/Status ingress, no Alpha UI or
browser playtest, no full P1/P2, no game-generation call. Next: C4.4 typed
Dynamics Action bridge (C4_DYNAMICS_ACTION_DESIGN.md; baseline
evidence/c4_dynamics_main_before.json).
