# Alpha Playtest Report

## Scope and status

Bounded blind sidecar playtest completed on 2026-10-28. This is evidence for
the next UX/integration work queue, not a complete-game claim or P4 acceptance.
It covers one short public-API run, not browser UX, a full win/loss cycle, or
mechanically different complete runs.

The run imported `AlphaSession` once in one persistent Python interpreter with
`PYTHONPATH=src`. It used only `new_game()`, `public_state()`, and
`perform(action, target=..., slot=...)`, selecting actions from advertised
controls and visible feedback. No game source, content, tests, hints, hidden
WorldState, `.state`, or private methods were read. No source files were
modified. The Alpha authority worker may have edited concurrently; source
revision was not captured, so timing-specific results should be rechecked
against the authority revision.

## Result

| Item | Public observation |
| --- | --- |
| Player actions | 19 of 20 maximum |
| Outcome | `playing` |
| Remaining time | 44 of 72 |
| Final area | `frost_forest` (霜痕森林) |
| Player state | HP 36/36, mana 7/10, shield 0 |
| Changed-world action | `restore_forest`; consumed 2 孢芽 and changed public biomass target/behavior |
| Runtime/API error | None; constructor and public API worked |
| Clock consistency | Failed: `remaining_time` decreased after every action, while public `time` and every recent-event `tick` stayed at 0 |

The run established comprehension of travel, inspection, collection, craft,
equip, cast, and a persistent-world restoration action. The visible humidity
changed from 0.42 to 0.686 after casting 潮息瞬发纹, and biomass in 霜痕森林
rose from 0.420 at the forest-heart inspection to 0.475 immediately after
`restore_forest`, then to 0.561 on return. The root bridge did not visibly
grow or unlock within the remaining observation window.

Full allowlisted public observations and controls are in
`evidence/p0_blind_playtest.json`.

## Comprehension findings

- The start objective, camp interactions, travel costs, and first route were
  understandable. Inspecting the insight dais made all recipe costs/effects
  visible and unlocked the three tide recipes; the player could then make,
  equip, and cast one without guessing an API shape.
- Resource feedback was clear: collecting reduced visible abundance and
  granted one unit. The forest-heart control explicitly exposed the 2-spore,
  2-tick restoration cost, and the post-restoration feedback told the player
  to leave, advance the world, and return.
- Inspect feedback is inconsistent. 水文碑 disclosed an actionable qualitative
  rule, but 补给火, 隐蔽菌圃, 潮雾潜伏兽, 根桥遗迹, and other generic
  inspections only said that an observable feature was recorded. Those
  controls advertised a reusable rule clue while revealing no rule.
- The public clock is stale and self-contradictory. `remaining_time` fell
  normally, but `time` stayed 0 and the event log repeatedly said
  “世界推进至第 0 刻。” This makes the requested “advance several ticks”
  instruction impossible to verify and misstates world progress.
- Equip feedback says “槽位 1” after the advertised control used `slot: 0`.
  The zero-based API value and one-based human-facing slot label need an
  explicit convention.
- After the dais inspection, the control list exposed craft actions for all 12
  recipes even when public state marked them `craftable: false` and listed
  missing materials. This is survivable because missing materials are visible,
  but unavailable controls should be visually disabled or separated.
- The forest restoration produced an immediate biomass change, but the root
  bridge remained described as “尚未发现明确规律” after leaving, advancing,
  returning, and inspecting. There is no visible due-tick, threshold, pending
  status, or completed-state acknowledgement.
- Recipe diversity observed here is limited to the existing 12 recipes (four
  resource families × instant/sustain/echo). Only the tide family was
  affordable in this bounded run; no new recipe diversity was inferred.

## Work-queue recommendations

1. Fix world-clock semantics first: make absolute time, remaining time, and
   event ticks advance consistently and show the actual tick that elapsed.
2. Make every “reusable rule clue” inspection return a specific rule or state
   that no rule is currently known. Do not reuse generic recorded-feature text
   while advertising rule discovery.
3. Add pending/completed/deadline feedback for delayed world changes such as
   the root bridge, including the next expected observation tick.
4. Normalize equip slot numbering between controls/API and player-facing text.
5. Disable or clearly separate non-craftable recipe controls, while preserving
   visibility of missing materials.
6. Re-run this exact public path after clock fixes and verify that restoration
   can be observed reaching a stable world-state outcome. This remains required
   before claiming completion or P4 acceptance.

## 2026-10-29 Process Modification Boundary

This increment adds typed running-Process rate/remaining-duration control to
formal Gameplay Skills, not to the Alpha UI/inventory. Independent player/NPC
paid Action tests and the complete Alpha/M0 regression pass (759 total tests /
3,152 subtests across all modules). They are mechanics/regression evidence,
not a new public browser playtest or proof of the recommendations above.
No new recipe diversity, completed game or P4 acceptance is claimed.

## Continuous C1 Boundary

C1 repairs native expiry and actual optional Process controls. New formal
player/NPC timed probes and complete regression776/3,180 pass; this is still
mechanics evidence, not a new public Alpha playtest. C2 finite Stock-fed Field
source is selected to support sustained environmental investment identified by
the existing playtest. Pending/completed UI feedback and full public-path rerun
remain open; no generated skills or P4 acceptance are inferred.

## Continuous C2 Mechanics Boundary

C2 bounded finite Stock-to-Field source is ACCEPTED: frozen full regression793 passed/3,195 subtests in388.43s, exit0, all279 Python hashes unchanged. Owner11/7, independent6 methods, Main focused53/30 and complementary8 denials pass. Reports: C2_STOCK_FIELD_DRIVE_INCREMENT.md / C2_STOCK_FIELD_DRIVE_REVIEW.md; complete metadata/log: evidence/c2_drive_frozen_full_regression_meta.json / c2_drive_frozen_full_regression.txt. Existing clock, Engine, staged Action, Observation, Alpha and all87 tracked test files at a4ad912 remain protected. Positive finite source only; no sinks/open source/universal Field units, Alpha UI, complete P1/P2 or generation claim. Local checkpoint subject: feat: add bounded stock-fed field sources. Next independent task C3_RELATION_MODIFIER_DESIGN.md, then C4_CONDITION_BUDGET_DESIGN.md and remaining P1 gates.

This is quantitative formal Gameplay engine evidence, not a new browser/public Alpha playtest. Sustained environmental investment now has a bounded finite-source mechanism. Existing public pending/completed feedback, locked crafting UX, recipe diversity and full playable-path recommendations remain unverified; no P4 or completed-game claim follows.

## Continuous C3 Mechanics Boundary

C3 bounded existing typed Relation enable/disable overlay is ACCEPTED. Full frozen regression: **804 passed, 3,226 subtests passed in415.43s**, exit0; all282 Python hashes unchanged. Independent QA six methods, owner five methods, Main cross-focus64/48 pass. Main complementary timed parsed/equipped enable player/NPC actually match .modify.on, pay Mana1/Tick1, change opt-in downstream availability false->true, and expire to current disabled base. Independent QA formal disable/current-base/expiry/cascade/late-tick/replay remains separately attributed. Reports: C3_RELATION_MODIFIER_INCREMENT.md / C3_RELATION_MODIFIER_REVIEW.md. Metadata/log: evidence/c3_relation_frozen_full_regression_meta.json / c3_relation_frozen_full_regression.txt. All89 previously tracked test files at9f75122 remain byte-for-byte unchanged. Engine/clock/Observation/Alpha are untouched. No graph creation/deletion/retarget, generic travel/locality availability integration, Alpha UI, full P1/P2 or generation claim. Next independent target: C4_CONDITION_BUDGET_DESIGN.md, then C4_PASSIVE_DISPATCH_DESIGN.md and remaining P1. Deadline20:10 +08:00 and all accounting/stop rules remain in force.

Real Engine Gameplay evidence, not a new browser playtest. Public feedback/control/discovery recommendations and P4 remain open.

## Continuous C4.1 Mechanics Boundary

C4.1 bounded shared raw-condition parsing is ACCEPTED. Frozen full regression **835 passed,3,304 subtests passed in381.12s**, exit0,284 Python hashes unchanged; all91 old test files atd613cc9 remain byte-identical. Owner15/14, independent FINAL16 methods, Main89/53 pass. AST parity preserves every typed leaf branch and evaluator; Main trusted-cap depth64/nodes4096 accepts and one-over rejects. Defaults depth16/nodes64/children16 are fresh/shared per parse, root1 and every operator/leaf counts, with path-bearing GameplayContractError before over-deep/over-wide traversal. Candidate JSON cannot raise budgets; trusted callers may choose bounded caps64/4096/256. Reports:C4_CONDITION_LIMITS_INCREMENT.md/C4_CONDITION_LIMITS_REVIEW.md; full metadata/log:evidence/c4_condition_frozen_full_regression_meta.json/c4_condition_frozen_full_regression.txt. Initial17-method defect-persistence assertion moved to a non-collected actual probe before acceptance; original source/report/meta/log preserved,16 real requirement tests unchanged. No old tests/Engine/clock/Observation/Alpha change. No Status condition ingress, new typed leaves, aggregate per-Skill/per-Tick/CPU/query/active-source or full P1/P2 claim. Next actual damage-passive dispatch (C4_PASSIVE_DISPATCH_DESIGN.md), then verified active top-level false-condition gate defect (C4_ACTIVE_CONDITION_DESIGN.md). No game-generation call until full P1/P2, continue sequentially until20:10 +08:00 or real stop/account/budget/blocker.
