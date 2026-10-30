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

## C5.2 Area Derived Catalog And P1 Gate Acceptance (2026-10-30)

C5.2 read-only Area Derived catalog is ACCEPTED (C5_DERIVED_CATALOG_DESIGN.md).
NEW gameplay_v04/derived.py: trusted DerivedSpec kinds weighted_sum
(clamp(bias + sum weight*Field), <=8 terms, weights/bias in [-8,8]) and
threshold (gt/gte/lt/lte -> 1.0/0.0), <=8 specs per Area, strict parse.
Values live in Area component pmw_gameplay_derived {values, spec_hash},
written once at time-zero initialization and afterwards ONLY by Core
`state`-mode Laws (neq-guarded, area id + spec_hash bound), so they follow
paid Field writes and native Ticks with no Python mutation and no second
simulator. Skills cannot write Derived; they read it through a new typed
condition leaf `derived` (subject current_area only; missing key -> False).
Gate3Content.derived_by_area trailing default: legacy compiled Laws and all
Action/Skill hashes byte-identical.

Independent QA Pauli 01a18b39-ad4a-70c1-aee5-0d6124bb5504 first REJECTED with
genuine PRODUCT_DEFECT C5.2-REV-01: actor Observation omitted Derived, so
SandboxSimulator/LegalActionGenerator rejected a live-true derived-gated
Skill. Fix owner Singer 01a18b48-9c7a-7972-a4da-38cdfaef35dc changed
observation.py (project sorted finite current-Area Derived values only when
the component exists; no spec_hash/Law IDs) and simulation.py (hydrate the
values map). Legacy Observation documents/revision tokens byte-identical.
Sandbox does not recompute Derived after simulated writes (scope note).
QA re-verified and replaced its defect-asserting method with a requirement
test: final ACCEPT (10 tests/13 subtests; obs/sim/legal/AI 43/40).
Owner Confucius 01a18b22-0852-7151-8b38-03c7d9a2d86c 11/16; fix owner 5/11;
Main focused 259/318; Main probe evidence/c5_derived_main_probe.json
(12/12 hand-computed checks, two Derived in one all-condition, player/NPC).

P1 completion conformance: owner Lovelace
01a18b3b-e9e3-7f73-a4c4-e89106ca8303 NEW test_p1_scenarios_completion.py
(4/6) proves the three previously PARTIAL scenarios through the formal chain
for PLAYER and NPC: (1) attractor change, move_actor away, three real Ticks
off-Area, return and observe continued change; (7) relation overlay blocks
move_actor atomically, expiry restores traversal; (9) Derived follows Field
changes and gates a Skill. Independent reviewer Hooke
01a18b48-d134-78d0-8ee9-908cb27e8433 (P1_SCENARIO_COMPLETION_REVIEW.md) added
counterfactual probes (no-attractor control 0.603392 vs 0.468928 while away;
no-overlay world moves; boundary 0.5 accepts, 0.499999999999 rejects), zero
product defects, zero production special cases, previous 7 PASS unaffected.

**P1 GATE ACCEPTED**: all ten contract scenarios pass through the formal
Engine (accepted 7 in P1_SCENARIO_CONFORMANCE.md + scenarios 1/7/9 in the
completion addendum), no skill-name special cases, no second world simulator.
Full frozen regression c5_derived_frozen: **985 passed, 3,550 subtests in
403.70s**, exit0, 307 Python hashes unchanged during the run; protected 100
old tests / Core 23 / Alpha 13 byte-identical vs
c5_move_main_protected_before.json (130/130).

Accounting c5_2_p1_complete subset USD8.16062993/CNY54.40202337; project
USD56.26/CNY375.04; safety 472.57/2000; P1 369.62/400; Reserve 65.29/150
(user-approved overflow booking); Unknown0. No Alpha UI/playtest or
generation claim. Next: P2 (P2_SKILL_IR_DESIGN.md) P2.1 versioned Skill IR
schema/validator/compiler lowering to the accepted runtime, then P2.2 30
reference skills. Generation provider calls stay forbidden until P2 is
accepted.
## P2.1 Versioned Skill IR Accepted (2026-10-30)

`gameplay_v04/skill_ir.py` (`pmw-skill-ir-v1`): strict closed-key IR,
multi-entry (one on_use + on_event damage_resolved passives), document-wide
shared condition and material budgets, lowering to unchanged v0.4
SkillBlueprints through `parse_skill_blueprint` (no new runtime), Operator /
state-class coverage and deterministic preview; unsupported triggers and
`lifecycle.status_duration` rejected as `language_gap`. Iterations: owner
Laplace, fixes Kierkegaard (round 2), Gibbs (round 3, compile re-parses the
canonical JSON), Halley (round 4 iterative JSON shape bound; round 5
tighten-only condition limits and |int| <= 2**53). Independent QA Ampere
rejected rounds 1-4 with distinct new defects each time (each round fixed its
target, so the section 28 stop rule was not triggered) and ACCEPTED round 5:
87 passed / 179 subtests, 0 product defects, 1 scope note (hostile container
subclasses outside the JSON threat model). Main root-cause decision: IR
condition limits are tighten-only because registry install and checkpoint
restore re-parse with default limits.

Full frozen regression p2_ir_frozen2: **1065 passed, 4103 subtests in
780.25s**, exit 0, 317 Python hashes unchanged. Protected 130/130 unchanged
(evidence/p2_ir_main_protected_after.json). First run p2_ir_frozen failed
only tests/test_agent_cost_ledger.py because the CNY3000 cap had been written
into code defaults; defaults were restored and the user-authorised limits
moved to project_run.json `budget_limits_cny` (refresh passes
`--budget-limit`); evidence preserved.

Accounting p2_1: USD 11.02583293 / CNY 73.50261264; safety 575.49/3000; P1
369.62/400; P2 76.45/350; Reserve 91.77/1150; Unknown 0. A main turn
mis-defaulted to P1 was corrected to P2 before the snapshot was written.
No Alpha UI/playtest or generation claim. Next: P2.2 reference library (40
Skills, owner Faraday done) independent QA, then the P2 Gate.