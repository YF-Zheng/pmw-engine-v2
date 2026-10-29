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
