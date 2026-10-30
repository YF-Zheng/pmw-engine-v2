# Alpha Development Plan

基线：`feature/alpha-v02-seventh-night`, commit
`1433e957d5391b880b71e92da4b5cf2ebd9751cd`。总参考预算上限 ¥2,000。

## Stage Gates

| Stage | Budget CNY | Acceptance | Status |
| --- | ---: | --- | --- |
| P0 | 100 | evidence-backed audit, module boundaries, concrete tasks | accepted: 644 baseline tests |
| P1 | 400 | all ten formal Engine mechanism scenarios | not accepted |
| P2 | 350 | versioned IR, one compiler/runtime, 30 reference skills and adversarial/replay gates | not started |
| P3 | 200 | 200-500 real DS Flash candidates and behavior-based evaluation | not started |
| P4 | 400 | playable two-area generated-skill slice, three strategy types | not started |
| P5 | 400 | playtest-driven bounded iteration | not started |
| Reserve | 150 | regression, recovery and delivery | reserved |

## Ordered Work Queue

1. P0: run baseline core/v06/Gameplay/Alpha/M0 suites and formal v06 demos;
   record Windows environment failures separately from mechanics defects.
2. P1.1 (bounded increment accepted): explicit no-recovery Field mode in the EXISTING Gameplay dynamics
   language; verify curves, expiry stacking, save/load and zero implicit
   diffusion. No new Tick or Engine rewrite.
3. P1.2 (trusted sidecar accepted; game bridge open): trusted generic Stock/Process catalog and conservative conversion
   lowering into Gameplay's world-tick event. Scale input/output together;
   reject capacity overflow, forbidden sources and competing resource writers.
4. Accepted: fix the audited Alpha stale-time/flag-only-route defects through existing
   Gameplay clock and real PMW Relation Laws; preserve current game outcomes.
5. Accepted 2026-10-29: ecology baseline-curve dispatch uses live state with
   canonical formula IDs; 719 full tests and 3,141 subtests passed. The bounded
   P1.3 slice is now accepted: typed Stock/Process start through existing staged
   Action/material authority with player/NPC, mana/time, rollback and registry
   checkpoint replay; 742 tests/3,141 subtests pass. The subsequent bounded
   rate/remaining-duration Process modification bridge is also accepted:
   759 tests/3,152 subtests, exact Law/expiry confirmation and independent QA.
   Pause/resume/progress writes are not part of this Skill language slice.
   C1 repairs the verified native rate-only hard-deadline rejection and genuine
   optional-parameter schema gap: 776/3,180, 276 immutable hashes, real timed
   player/NPC proof. Next: C2 finite Stock-fed Field drive, then bridge remaining
   catalog operators into Action/Registry;
   reuse material capabilities and topology validator, add bounded event/query
   budgets and lifecycle ownership. Run all ten scenarios including player/NPC.
6. P2: versioned multi-trigger IR, typed conditions and bounded selectors;
   schema/capability/budget checks, 30 data-only reference skills, replay tests.
7. P3: external Flash generator with bounded repairs/timeouts, authorized
   context, normalized hashes and behavioral deduplication; no hidden answers.
8. P4: Alpha crafting preview/registration/save/play loop; preserve old playable
   slice while adding verified language. API failure leaves resources untouched.
9. P5: prioritize actual normal-entry playtest failures, not extra templates.

Blind P0 public-entry playtest used 19 actions and reached forest restoration,
not a completed game. Prioritize clear rule revelations and visible pending/
completed world-change feedback; slot labels may legitimately be one-based
display for zero-based API and require clarity, not automatic renumbering.

## Iteration Discipline

Each iteration records target, acceptance, risk, file ownership, tests, review,
checkpoint, ledger and next independent task. Same bug failing two fixes returns
to GPT root-cause analysis. Three ineffective iterations stop that direction.
Never delete tests, bypass validation or modify victory flags to pass gates.
No remote pushes or global Codex/Magpie configuration changes are required.

Checkpoint verification: latest frozen full regression **776 passed, 3,180
subtests passed in 407.04s**, all 276 Python hashes unchanged (previous
checkpoint: 759/3,152). P0 accepted;
only bounded P1 increments accepted, not the
full ten-scenario gate. No generation batch or P2 reference corpus was started.

Current playable startup (PowerShell, repository root):

```powershell
$env:PYTHONPATH = 'src'
python -m examples.pmw_alpha.server --port 8020
```

This starts the EXISTING Alpha, not the future P4 generated-skill slice.

## Continuous C2 Accepted Checkpoint

C2 bounded finite Stock-to-Field source is ACCEPTED: frozen full regression793 passed/3,195 subtests in388.43s, exit0, all279 Python hashes unchanged. Owner11/7, independent6 methods, Main focused53/30 and complementary8 denials pass. Reports: C2_STOCK_FIELD_DRIVE_INCREMENT.md / C2_STOCK_FIELD_DRIVE_REVIEW.md; complete metadata/log: evidence/c2_drive_frozen_full_regression_meta.json / c2_drive_frozen_full_regression.txt. Existing clock, Engine, staged Action, Observation, Alpha and all87 tracked test files at a4ad912 remain protected. Positive finite source only; no sinks/open source/universal Field units, Alpha UI, complete P1/P2 or generation claim. Local checkpoint subject: feat: add bounded stock-fed field sources. Next independent task C3_RELATION_MODIFIER_DESIGN.md, then C4_CONDITION_BUDGET_DESIGN.md and remaining P1 gates.

C3/C4 architectures are prepared, not implemented in this checkpoint. Full P1 remains open; proceed sequentially without ordinary decision questions. Deadline20:10 +08:00 and all accounting/stop rules remain in effect.

## Continuous C3 Accepted Checkpoint

C3 bounded existing typed Relation enable/disable overlay is ACCEPTED. Full frozen regression: **804 passed, 3,226 subtests passed in415.43s**, exit0; all282 Python hashes unchanged. Independent QA six methods, owner five methods, Main cross-focus64/48 pass. Main complementary timed parsed/equipped enable player/NPC actually match .modify.on, pay Mana1/Tick1, change opt-in downstream availability false->true, and expire to current disabled base. Independent QA formal disable/current-base/expiry/cascade/late-tick/replay remains separately attributed. Reports: C3_RELATION_MODIFIER_INCREMENT.md / C3_RELATION_MODIFIER_REVIEW.md. Metadata/log: evidence/c3_relation_frozen_full_regression_meta.json / c3_relation_frozen_full_regression.txt. All89 previously tracked test files at9f75122 remain byte-for-byte unchanged. Engine/clock/Observation/Alpha are untouched. No graph creation/deletion/retarget, generic travel/locality availability integration, Alpha UI, full P1/P2 or generation claim. Next independent target: C4_CONDITION_BUDGET_DESIGN.md, then C4_PASSIVE_DISPATCH_DESIGN.md and remaining P1. Deadline20:10 +08:00 and all accounting/stop rules remain in force.

## Continuous C4.1 Accepted Checkpoint

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

## Continuous C4.4 Frozen Acceptance

C4.4 bounded typed `dynamics_modifier` Action bridge is ACCEPTED. One closed
Effect kind (current_area only, commitment required, field_id, rate_add[-1,1],
rate_multiplier[0,8], curve linear/distance_squared/none, curve_priority 0..31,
duration 1..64; strict types, no terms/targeting extras, base cost 3, active
on_use only). Trailing EffectSpec fields keep every old Effect's canonical
hash. Preparation runs on the staged session: native validate_source against
the actual Area FieldProfile, duplicate curve priority across persistent and
temporary layers, capacity, per-Action distinct slot reservation and
same-Field source-footprint conflicts all reject before cost/time/publication.
Lowering reuses the existing modify_rate slot apply/schedule/expire Laws; no
unmanaged runtime.apply_source, no new clock. Production: effects.py,
skills.py, actions.py, action_compiler.py only.

Owner Ptolemy 01a18a9f-ba78-7123-bccf-1488c2a2c2b7: 19/44; bounded 383/355 and
183/3019. Independent Hume 01a18a9f-fe77-70b0-a392-baa4e39f8914: ACCEPT,
14/14 (red run on byte-verified HEAD archive: 13 requirement failures as
expected), legacy 395 and 183 OK; ten own-fixture corrections recorded
separately; no product findings. Hume's turn was once halted by the Magpie
loop guard (same command 8x); resumed with bounded instructions. Main cross
195/176. Main two-Area hand-calculated probe (player Area .2->.8 r.2, NPC Area
.5->.9 r.1, add .3 x1.5): exact match for d=1,2,3. Main's first hand model
assumed d effective Ticks and mismatched; the real rule (scheduler-before-
Tick, d-1 effective Ticks after the paid cast Tick; duration 1 legal but
inert, same as modify_rate) was a Main expectation error, not a product fix.

Full frozen regression c4_dynamics_frozen: **917 passed, 3,445 subtests in
395.27s**, exit0, 296 Python hashes unchanged. Protected after 7c975cb: 97
old tests, Core23, Alpha13 byte-identical. QA's ~196MB duplicate HEAD archive
is byte-identical to git archive 7c975cb; kept locally, git-excluded, recorded
in evidence/c4_dynamics_review_head_manifest.json (Main deletion was refused
by tool policy, so nothing was deleted).

Accounting c4_4 subset USD4.39985098/CNY29.33116657 (main turn actual
tencent/claude-opus-5.5 priced as Claude; workers actual DeepSeek Flash).
Project USD40.50206953/CNY270.00299631; safety 340.21738405/2000; **P1
reserve 302.5674514/400**: about two more C4-sized increments fit inside P1.
Unknown0, complete. No Alpha UI/playtest, full P1/P2 or generation claim.

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