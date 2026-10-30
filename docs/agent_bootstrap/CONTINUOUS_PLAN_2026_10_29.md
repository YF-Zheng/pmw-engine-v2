# Continuous Execution Plan - 2026-10-29

User explicitly requested a long plan followed by consecutive implementation,
not ending the chat after one accepted increment. Repository-only writes,
feature/alpha-v02-seventh-night, no remote push or global configuration change.
Start reviewed checkpoint: 0e4e45b. Main turn:
01a1862b-a31c-7351-ac83-5a77abdf3769 (verified tencent/gpt-6.1-sol).

## Execution Rules

Run one attributable target through architecture -> bounded DeepSeek worker ->
independent review -> focused/cross-module frozen tests -> budget verification
-> local checkpoint, then immediately start the next independent target.
Do not accept unreviewed patches or placeholder/reference-only mechanisms.
P1 and P2 must both pass before any game skill-generation provider request.
Existing Engine, Gameplay clock, Observation, staging, playable Alpha and every
old test remain protected. New workers have explicit disjoint file ownership.
Every actual main turn and child thread enters the per-response cost selection.
Unknown/incomplete accounting stops spending. Cache is actual in evidence and
97% only for reference-cost estimates. Bootstrap remains separate.

Stop on explicit user stop, unrecoverable blocking condition, failed accounting
or stage/MAX budget gate, or the authorized deadline 2026-10-29 20:10 +08:00.
Finish safe regression/delivery near limits. Two failed fixes require Main root
cause review; three ineffective iterations stop that direction. Automatic
heartbeat remains paused; this is continuous work in the current active turn.

## Ordered Work

| Item | Scope and measurable gate | State |
| --- | --- | --- |
| C1 | Fix rate-only Process false rejection and genuine optional-schema defect; native/formal timed player/NPC, rollback/replay; 776 tests/3,180 subtests, 276 immutable hashes | accepted a4ad912 |
| C2 | Bounded finite Stock-fed Field source on existing clock; explicit source/conservation, local authority, duration/ownership and staged Action tests | accepted:793/3,195,279 immutable hashes; local checkpoint |
| C3 | Typed Relation modification using existing topology/lifecycle Laws; endpoint/type/scope/material rejection and actual downstream behavior | accepted804/3,226,282 immutable hashes; local checkpoint |
| C4 | Bound shared condition parsing, then fix actual equipped damage-passive auto-dispatch gap; continue remaining P1 Operator/condition/lifecycle/budget gaps and ten formal player/NPC scenarios | C4.1 accepted835/3,304/284; C4.2 accepted869/3,325/287; C4.3 accepted884/3,335/294 (one reviewed legacy fixture exception); C4.4 Dynamics accepted917/3,445/296; P1 not accepted |
| C5 | Only after P1: versioned multi-trigger IR/typed selectors/conditions, one compiler/runtime and 30 data-only reference skills with adversarial/replay gates | gated by P1 |
| C6 | Only after P2: real bounded Flash generation/evaluation, then Alpha generated-skill slice and public playtest-driven iteration | gated by P1 and P2 |

This is an ordered queue, not a promise that every stage fits the remaining
day. Gate failures may select a smaller independently valuable repair rather
than pretending a full stage passed. Update the table after every checkpoint;
continue without asking for ordinary engineering choices.

C3's existing-link overlay design uses REAL Core Relation components and an
opt-in downstream World Law, not a proxy Entity or completion flag. Existing
travel/locality selectors still read topology and are not falsely declared to
honor the new effective switch. See C3_RELATION_MODIFIER_DESIGN.md.
C4 condition design/baseline: C4_CONDITION_BUDGET_DESIGN.md and
evidence/c4_condition_budget_before.json. Architecture/evidence preparation
can run while C2 workers implement, but no C3/C4 production edits begin before
the preceding source freeze, independent review, full regression and checkpoint.

Further real C4 follow-up: a normally registered/equipped damage_resolved
shield passive did not respond to a paid NPC attack (HP40->30,shield0->0,
one paidTick, only Action resolve event). Existing manual Hook helpers are
not automatic scenario6 proof. See evidence/c4_passive_dispatch_before.json
and C4_PASSIVE_DISPATCH_DESIGN.md. This is queued architecture, not a new
accepted capability, Alpha browser playtest or game-generation call.

## C1 Frozen Policy

Saturated conversion does not increment productive elapsed or decrement stored
remaining ticks, while wall-clock expiry is unchanged. Rate-only modification
must retain the scheduled future expiry and stored duration/remaining/progress,
then validate that actual expiry against the immutable hard deadline. Explicit
remaining-tick changes still use now + requested remaining and bounded total
duration. No reset, extra production lifetime, new Tick phase or second clock.
Missing/past/duplicate expiry and over-hard-deadline requests reject atomically.
Implementation ownership: processes.py and a new rate-expiry owner test only.
Independent QA owns a distinct new review test/report/evidence only. Main owns
architecture, source review, governance/accounting and frozen full regression.

### C1 Independent Finding And Scope Extension

Independent pure-rate verification exposed a second genuine production defect:
effects.py strict field equality requires both numeric keys despite the
documented rate-or-remaining contract. Original 0e4e45b reproduction in
`evidence/c1_optional_fields_before.json`: rate-only and remaining-only reject,
both accept. Previous passing combined-parameter tests did not establish the
optional-parameter claim. Do not disguise this as a fixture-only error.

Native implementation Lagrange is frozen/closed; its owner tests are supporting
coverage, not sufficient defect reproduction (some profiles retain deadline
slack, and one formal case uses explicit remaining). Russell independently
owns formal pure-rate player/NPC evidence. Linnaeus now exclusively owns
effects.py and new test_sandbox_process_optional_fields.py: correct only required
versus allowed keys for process_modify, retaining unknown/null/type/budget gates
and every other Effect schema. Actual child ID is in project_run.json. No
production scope overlap, no native-only acceptance, no generator calls.

## Next Real C4 Semantic Gap

After parser safety and actual damage passive dispatch: C4_ACTIVE_CONDITION_DESIGN.md. Main real formal parsed/equipped timed false-condition Skill still activated and spent Mana/Tick (evidence/c4_active_condition_before.json). This is queued production defect evidence, not fixed by parser safety or accepted P1. Proceed sequentially; no concurrent Actions ownership.

C4.2 accepted through independent21/13 and full869/3325,287 immutable hashes. Next C4.3 actual active-condition gate, then queued C4_DYNAMICS_ACTION_DESIGN.md if time/budget permit. Do not stop after this increment.

C4.3 accepted (884/3,335, 294 immutable hashes, one reviewed legacy fixture correction). User extended the run on 2026-10-30; continue C4.4 typed Dynamics Action bridge next, sequential ownership, no generator calls before full P1/P2.

C4.4 accepted (917/3,445, 296 immutable hashes). P1 stage reserve 302.57/400 CNY: choose remaining P1 targets by value; stop P1 spending before the stage limit and report to the user rather than overrun.

## P1 Ten-Scenario Formal Conformance (Test-Only)

Test-only audit at 1aa4aad: NEW gameplay_v04/tests/test_p1_scenarios.py
(sha256 06653f28...7ac62) drives each P1 gate through parsed SkillBlueprint ->
make_content/compile -> MechanismRegistryRuntime/change_loadout ->
submit_timed_primary_action (or managed combat) -> real advance_world_tick.
Result: 7 PASS (2,3,4,5,6,8,10), 3 PARTIAL (1 no formal actor relocation;
7 no formal supply/path consumer of relation effective_enabled; 9 no
candidate-facing Derived catalog). Owner Peirce
01a18ad2-2f1a-7632-b3af-c22186e91f05 10/10; Main rerun 10/10; independent
reviewer Banach 01a18ae6-0601-7330-aa08-673a9282fd99 confirmed all ten
classifications with causal probes (scenario 8 amount=0 stays dry; scenario
10 zero shield still pays 27 Mana), no downgrades
(P1_SCENARIO_CONFORMANCE.md / P1_SCENARIO_CONFORMANCE_REVIEW.md). Full frozen
regression p1_scenarios_frozen: **927 passed, 3,445 subtests in 406.27s**,
exit0, 298 Python hashes unchanged; no production/old-test/Core/Alpha change.
Accounting p1_scenarios subset USD3.77094469/CNY25.13862568; project
USD44.27/CNY295.14; safety 371.89/2000; **P1 reserve 334.24/400**; Unknown0.
P1 remains NOT accepted (3 PARTIAL). Next: C5_MOVE_ACTOR_DESIGN.md (formal
move_actor Effect honoring C3 link overlay), targeting scenarios 1 and 7.

## Continuous C5.1 Formal Actor Relocation (move_actor) Acceptance

C5.1 bounded `move_actor` Effect is ACCEPTED (design C5_MOVE_ACTOR_DESIGN.md).
Closed kind appended to EFFECT_KINDS: target adjacent_area only, commitment
required, raw keys exactly id/kind/target/commitment, budget cost 2, active
on_use only; at most one per Action; no damage/process_start/process_modify/
drive_source/relation_modifier co-effects (Skill and Action parse). Trailing
ActionRequest.target_area_id (default None); payload key only when present, so
legacy payloads/hashes unchanged. Staged preparation: exact adjacent target,
one located_in, destination != origin, traversal needs a joining adjacent
relation that is bare or has pmw_gameplay_link.effective_enabled True
(malformed link rejects), no id collision. Lowering: two event Laws using Core
delete_relation/create_relation; post-run exactly-one-destination check.
Production: effects.py, skills.py, actions.py, action_compiler.py only.

Owner Darwin 01a18af3-71af-75e3-9ba2-01d10ffb1a3e: 11/30; focused 77/107.
Independent Rawls 01a18b01-8653-7b81-9da2-719c1a84bb33: ACCEPT, 12/17, no
product defects; fixture corrections recorded (C5_MOVE_ACTOR_REVIEW.md).
Residual diagnostic only: a C3 profile Relation whose endpoints are marker
entities is not an Area-Area adjacency edge, so it reports "not an adjacent
Area"; an owned Area-to-Area disabled link reports "disabled" (owner test).
Main cross-module focused 281/167 (gate*, dynamics, P1 scenarios, Alpha,
storm relay). Main probe (evidence/c5_move_main_probe.json): after moving
A->B, a current_area Skill targets B; A evolves at baseline .2 while B gets
.4 on the paid Tick (hand-checked); move back/again works; NPC legal-action
enumeration does not yet list move targets (documented scope).

Full frozen regression c5_move_frozen: **950 passed, 3,492 subtests in
391.75s**, exit0, 300 Python hashes unchanged; protected 100 old tests, Core
23, Alpha 13 byte-identical vs c5_move_main_protected_before.json.
P1 scenarios 1 and 7 now have a formal relocation path and a formal
traversal consumer of relation effective_enabled; their PARTIAL status in
P1_SCENARIO_CONFORMANCE.md is not re-classified without a new conformance
review. Scenario 9 (Derived catalog) remains PARTIAL. Full P1 NOT accepted.

Accounting c5_1 subset USD3.82419318/CNY25.49360142; project CNY320.64;
safety 404.02/2000; **P1 reserve 366.37/400**, Unknown0. Another C-sized
increment (~32-37 CNY reserve) would exceed the P1 stage limit, so P1
implementation spending STOPS here pending user decision (raise P1 allocation
from Reserve, or accept current state). No Alpha UI/playtest, generation, or
full P1/P2 claim.
