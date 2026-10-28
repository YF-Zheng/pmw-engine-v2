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
