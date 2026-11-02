# Alpha QA Report

2026-10-28 P0 baseline: **644 existing tests passed**, no baseline failures.

| Suite | Tests | Seconds | Evidence |
| --- | ---: | ---: | --- |
| Core | 254 | 32.75 | evidence/p0_core_qa_pytest.txt |
| v06 formal mechanism catalog/compiler | 170 | 32.13 | evidence/p0_next_tracks_v06_qa_pytest.txt |
| Gameplay | 172 | 96.91 | evidence/p0_gameplay_v04_qa_pytest.txt |
| Alpha + Storm Relay M0 | 48 | 129.59 | evidence/p0_alpha_storm_relay_qa_pytest.txt |

All tests ran in the local Python 3.12 runtime with `PYTHONPATH=src` and no
network installation. Five Engine-backed demos were separately regenerated to
evidence/p0_mechanisms; history outputs were not replaced. Detailed discovery,
commands and independent QA conclusions are in P0_BASELINE_QA.md.

New Sandbox v1 / P1 / P2 / generator / browser UX gates are NOT passed by these
baseline tests. Regression results for each new increment are appended after
implementation and independent review, rather than retroactively relabeling
baseline capabilities as complete.

## First P1 Integration Run

First combined run: **2 failed, 691 passed, 3,045 subtests**, 317.75s.
Failures were independently added assertions, NOT suppressed baseline tests:
formal no-recovery Law skipped the domain clamp, and ecology accepted a
nonzero-rate `none` baseline. Evidence is `evidence/p1_initial_regression.txt`.
Both are sent back for narrow repairs; acceptance requires a fresh clean run.
The first run overlapped final QA test-authoring; the final run is taken only
after implementation and independent test scopes have stopped changing.

An independent probe also found an older limitation: ecology base-curve
transitions change stored baseline data without regenerating the compiled base
variant. It predates this increment, is tracked for P1, and cannot be hidden by
claiming all dynamics semantics are restored.

## Final Frozen Regression

All implementation and independent QA workers were closed before this run;
the source/test scopes did not change during execution.

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -ra -p no:cacheprovider `
  tests `
  experiments/generative_mechanics/next_tracks_v06/tests `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests `
  examples/pmw_alpha/tests examples/storm_relay/tests
```

**701 passed, 3,130 subtests passed in 342.67s (0:05:42)**. Exit code 0.
Evidence: `evidence/p1_frozen_final_regression.txt`.

The intervening `evidence/p1_combined_regression.txt` run recorded **6 failed,
695 passed, 3,130 subtests passed in 358.13s** against intermediate Process
source while its worker was still repairing `valid_duration` and capacity
branches. This is retained as failed-run history, not relabeled as a passing
result. The final frozen rerun above is the current cross-module result.

Bounded accepted changes: no-recovery curve/policy/domain clamp, trusted
Stock-conversion Process on the existing clock, Alpha authoritative completed
time and real topology, and fail-closed deduplicated reference-cost tooling.
Independent review: `P1_INDEPENDENT_REVIEW.md`; its QA-owned results remain
separate from this Main-owned full regression.

Full P1 remains open: all ten integrated scenarios, generic seven-Operator
Action/material/Registry access, global budgets/locality, and ecology base-curve
transition semantics. No P2/P3/P4/P5 acceptance or new generation-provider
calls follow from a green regression. Alpha save v0.3 deliberately rejects old
v0.2 saves; compatibility migration remains an explicit future decision.

## 2026-10-29 Ecology Curve Increment

Independent QA: 9 tests and 5 subtests passed against frozen source hash
`d057121d008fa5a1d4057fbf838fe4018a8d0386a72c7348664bb0ebe7d67dcb`.
Owner tests: 9 tests and 6 subtests passed after correcting its contradictory
two-Area draft assertion. Existing independent limitation test was strengthened
to require the new curve from the next tick; its genuine pre-fix failure is
retained in `evidence/p1_ecology_main_before.txt`.

Main's complete frozen regression (same command as previous section):
**719 passed, 3,141 subtests passed in 373.46s (0:06:13)**, exit code 0.
All 269 recorded Python source/test hashes were unchanged during execution.
Output: `evidence/p1_ecology_frozen_full_regression.txt`; hashes/timestamps:
`evidence/p1_ecology_full_regression_meta.json`.

This accepts the bounded live-baseline curve fix and canonical causal Law IDs.
Actual before/after ticks, quantitative two-Area behavior, source layering,
expiry and full-trace/stage/rebuild/load consistency are covered. Intermediate
QA draft/source-overlap evidence is preserved, not mislabeled as frozen
baseline evidence. Full P1 remains open; next is the typed Process Action and
material/Registry bridge, followed by all ten scenarios and resource budgets.
No new game generator calls, UI victory shortcuts or Engine/tick fork.

## 2026-10-29 Typed Process Action Increment

Owner test recovery retained the original all-zero file and successful patch
call IDs. Recovered run: 17 passed / 1 failed due to the fixture equipping NPC
while only unloading player before disable. Normal NPC unload repaired the
test; no registry guard or assertion was weakened. Owner run: 18 passed.
Resumed focused Process/time run: 31 passed / 5 subtests; existing Gameplay
cross-run: 230 passed / 125 subtests. All intermediate evidence is retained.

Independent QA's initial five passing tests were not accepted as formal-entry
evidence: its compound fixture directly rewrote equip/registry references.
Revised compound skill is parsed from raw Blueprint under seven-point material
authority and normally registered/equipped. Final independent run: 5 passed
in 1.58s. Real post-activation emitted-event exception, late tick rollback of
state/scheduler/revisions/stats, changed compiled-profile checkpoint rejection
and basic-action Observation simulation are covered. Cost-modifier testing is
explicitly trusted action-level; current Blueprint JSON cannot author it.
Independent source/report: `P1_PROCESS_ACTION_REVIEW.md`.

Main's complete frozen regression used the same Core/v06/Gameplay/Alpha/M0
command as the previous sections, with TEMP/TMP inside the PMW repository:
**742 passed, 3,141 subtests passed in 343.03s (0:05:43)**, exit code 0.
All **271 Python source/test hashes** were unchanged during the run; no old
tests were removed. Evidence: `evidence/p1_process_action_frozen_full_regression.txt`;
command/timestamps/hashes: `evidence/p1_process_action_full_regression_meta.json`.

Accept only the bounded trusted-template Process start and staged action/time
bridge. No Alpha UI/inventory/Process planner, reagent-debit, dynamic template,
full P1/P2 or generation-provider acceptance follows from this regression.
Next independent target: typed Process modification through the same material,
local owner, registry and transaction boundaries.

## 2026-10-29 Bounded Process Modification Increment

Owner tests: 11 passed in 2.40s; existing native controller tests: 11 passed
in 0.40s; existing start Action tests: 18 passed in 2.95s. Independent owner
rerun: 11 passed in 2.30s. Main focused cross-regression: 42 passed / 80 subtests
in 7.45s (`evidence/p1_process_modify_main_focused.txt`). Owner setup partly uses
privileged native start; this alone does not establish the formal Skill bridge.

Independent frozen final QA: **6 passed, 11 subtests passed in 1.92s**.
The cold trusted initial catalog holds normally parsed start/modify Skills,
equipped with change_loadout, used through formal Actions and real paid ticks.
Player/NPC quantitative conversion, bounded shorten/extend, exact expiry,
locality/owner/ambiguity, real emitted-event and late-tick rollback, unrelated
.modify Law spoof denial, checkpoint continuation and actor-safe projection
are covered. No loadout/manifest hash rewriting authorizes positive acceptance.
Source/report: `P1_PROCESS_MODIFY_REVIEW.md`; exact output:
`evidence/p1_process_modify_review_final.txt`.

Earlier red QA drafts remain in `p1_process_modify_review_focused.txt` and
`p1_process_modify_review_debug.txt`: illegal hot registry fixture/version
operations, malformed mixed-effect shape, ambiguous normal start, incorrect
1:1 Stock conservation oracle and fixture property/local-variable errors.
The final suite uses the actual 2 ore -> 1 ingot rule and cold setup; production
guards and all old test assertions remain intact. These red drafts are not
relabeled as passing production acceptance. Main caught and required repair of
the initial suffix-only modification Law check before final QA/source freeze.

Both workers were closed before Main's complete frozen regression, with
TEMP=TMP=TMPDIR inside PMW and bytecode/pytest cache disabled. Same full
Core/v06/Gameplay/Alpha/M0 command as earlier sections:
**759 passed, 3,152 subtests passed in 332.41s (0:05:32)**, exit code 0.
All **273 Python source/test hashes** unchanged, no added Python paths during
execution. Exact log: `evidence/p1_process_modify_frozen_full_regression.txt`;
command/timestamps/before-after hashes:
`evidence/p1_process_modify_full_regression_meta.json`.

Original pytest log bytes are preserved, including Windows CRLF and traceback
indentation-only lines. They naturally trigger Git whitespace warnings, not
test/source failures. Staged whitespace checking covers code, tests, reports
and JSON; raw logs are separately hash-verified and warnings retained in the
precommit verification metadata rather than sanitizing failed-run evidence.

Accept only typed running Process rate/remaining-duration modification. Real
prior-checkpoint saturated-tick native rate-only false rejection remains open;
do not change deadline/progress policy silently. No pause/resume/progress-write
Skill, Alpha UI, full P1/P2 or generation acceptance follows. No new public
browser playtest was performed in this engine increment.

## Continuous C1 Expiry And Optional Controls

Independent QA found a genuine production defect that prior both-parameter
tests missed: strict Effect schema required both optional numeric keys.
Original native and schema counterexamples are in c1_rate_expiry_before.json
and c1_optional_fields_before.json. Native repair and separate schema repair
have disjoint ownership; all three workers closed before final full regression.

Independent frozen combined run of three new suites:17 passed/28 subtests in
3.45s; four methods are QA-owned. Genuine pure-rate raw Effect omits remaining,
parses None, uses cold catalog/normal player+NPC equipment and paid start. Pure
Primary resolution pays Mana; manual world tick verifies expiry but does not
pay modifier time budget. Main separately verified submit_timed_primary_action
for player/NPC: clock2->3, budget spent2->3/remaining10->9, Mana1, no full-Stock
conversion, exact expiry3. Evidence: c1_rate_expiry_main_timed.json.

Earlier red logs preserve fixture/property errors, parser-defect evidence and
Windows default-sandbox launcher1385 failures. Escalated repository-only
execution works; this was not a permanently unavailable host. No tests were
weakened or deleted to conceal those failures. Owner profiles with deadline
slack and explicit remaining are supporting tests, not original defect proof.

Full frozen regression: **776 passed, 3,180 subtests passed in407.04s**; exit0,
all276 Python before/after hashes match, old tests unchanged. Logs/metadata:
c1_rate_expiry_frozen_full_regression.txt / _full_regression_meta.json.
Independent review: P1_PROCESS_RATE_EXPIRY_REVIEW.md; Main clarified its timing
prose without modifying frozen test source. Full P1 remains open. Proceed to
C2 finite Stock-fed Field source; no generator calls or Alpha UI claims.

## Continuous C2 Frozen Acceptance

C2 bounded finite Stock-to-Field source is ACCEPTED: frozen full regression793 passed/3,195 subtests in388.43s, exit0, all279 Python hashes unchanged. Owner11/7, independent6 methods, Main focused53/30 and complementary8 denials pass. Reports: C2_STOCK_FIELD_DRIVE_INCREMENT.md / C2_STOCK_FIELD_DRIVE_REVIEW.md; complete metadata/log: evidence/c2_drive_frozen_full_regression_meta.json / c2_drive_frozen_full_regression.txt. Existing clock, Engine, staged Action, Observation, Alpha and all87 tracked test files at a4ad912 remain protected. Positive finite source only; no sinks/open source/universal Field units, Alpha UI, complete P1/P2 or generation claim. Local checkpoint subject: feat: add bounded stock-fed field sources. Next independent task C3_RELATION_MODIFIER_DESIGN.md, then C4_CONDITION_BUDGET_DESIGN.md and remaining P1 gates.

Intermediate QA fixture/import failures and Main nonexistent-path exit4 are retained, not called product regressions. Main two-failed-fix root review corrected the cascade fixture: an isolated copied session plus real installed action Laws and equipped timed Skill causes the actual Drive child to raise, then complete staged state/revisions/stats/closure/schedule remain unchanged. Independent Skills are equivalent actor-bound separate IDs, not one same-ID profile routed to both owners. Nonfinite rate coverage is complemented by c2_drive_main_denials.json; do not expand report prose into unexecuted tests. QA report/test hashes are preserved. No Python edits occurred during final full regression.

## Continuous C3 Frozen Acceptance

C3 bounded existing typed Relation enable/disable overlay is ACCEPTED. Full frozen regression: **804 passed, 3,226 subtests passed in415.43s**, exit0; all282 Python hashes unchanged. Independent QA six methods, owner five methods, Main cross-focus64/48 pass. Main complementary timed parsed/equipped enable player/NPC actually match .modify.on, pay Mana1/Tick1, change opt-in downstream availability false->true, and expire to current disabled base. Independent QA formal disable/current-base/expiry/cascade/late-tick/replay remains separately attributed. Reports: C3_RELATION_MODIFIER_INCREMENT.md / C3_RELATION_MODIFIER_REVIEW.md. Metadata/log: evidence/c3_relation_frozen_full_regression_meta.json / c3_relation_frozen_full_regression.txt. All89 previously tracked test files at9f75122 remain byte-for-byte unchanged. Engine/clock/Observation/Alpha are untouched. No graph creation/deletion/retarget, generic travel/locality availability integration, Alpha UI, full P1/P2 or generation claim. Next independent target: C4_CONDITION_BUDGET_DESIGN.md, then C4_PASSIVE_DISPATCH_DESIGN.md and remaining P1. Deadline20:10 +08:00 and all accounting/stop rules remain in force.

## Continuous C4.1 Frozen Acceptance

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


## P2 Reference-Library Gate Accepted (2026-11-02)

**P2 GATE ACCEPTED for the supported pmw-skill-ir-v1 runtime subset.**
Forty reference Skills use the same parser/compiler and actual Gameplay
runtime, covering seven Operators, six state classes, five selectors and
all seven required test categories. Per-Skill matrix: positive 40/40 (both
PLAYER/NPC plus control); permission rejection 40; budget rejection 40;
lifecycle 24 pass / 16 reasoned N/A; cross-region 6 pass / 34 N/A;
checkpoint 40; deterministic replay 40. No Skill-specific runtime code or
Alpha source change was added.

Independent QA completed by Rawls (DeepSeek Flash,
01a19a0a-db54-7e22-a0cc-861e905591cc), recovering Mill's interrupted review:
ACCEPT, product defects 0, historical test gap 1 (a tautological cap-owner
assertion) closed by a new exact dual-owner probe, scope notes 3. See
P2_REFERENCE_LIBRARY_REVIEW.md. New evidence proves strict before/at expiry,
real restored versus independently continued second attacks with distinct
request IDs, two counter owners firing once with bounded duplicate skips,
and no extra paid Tick. Main removed an unused imported TestCase so original
QA methods are not collected twice; all assertions preserved, new class
3 passed in 15.11s. Recovery failures are test-fixture errors, not product
fixes; original rollout output strings preserved.

Frozen full regression p2_lib_frozen_20261102: **1076 passed / 4257 subtests
in 1212.41s**, exit 0, 319 Python source hashes unchanged; 130 protected files
unchanged; library JSON and prior production/test sources unchanged.
Main acceptance: evidence/p2_lib_main_acceptance.json.

Limits remain explicit: reserved on_tick/on_expire/edge/other-event triggers
and non-null lifecycle.status_duration fail as language_gap; linked_object
requires one endpoint; no general effect-dependency graph; no staggered
two-timed-effect library row; passive caps in this library are only 1.
Gate acceptance is NOT a claim that every aspirational trigger/query or
all cap values are supported. Nor is it an Alpha playability milestone.

Accounting p2_2 snapshot cutoff 2026-11-02T02:59:18.189Z: task subset USD 4.84947528 / CNY 32.32854201
(already included once in the cumulative ledger). Project CNY 480.87;
safety-reserved CNY 605.92 / 3000; P2 106.88 / 350; Unknown 0, malformed 0.
The two November resumed main turns and actual old/new child IDs are included;
no polling-related costs were erased. Bootstrap remains separate.
Next independent target: P3.1A OFFLINE full mechanism Catalog + public Context,
then review; no live generation until a separately accepted provider/accounting
path is ready. Follow P3_SKILL_DESIGNER_DESIGN.md.
