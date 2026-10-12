# Failure and Correction Log

## Integration defects found and fixed

1. **Material authority union was invalid.** The first Build A compilation
   attempted to parse each Blueprint against both Build materials. The trusted
   parser rejected this because a Blueprint's `material_ids` must exactly match
   its own authority. The final builder parses each Blueprint against its own
   material, then combines the already validated skills in one Registry.
2. **Actor IDs could not reuse the 60-skill observer.** The original observer
   is intentionally fixed to `pilot_hero`. A Build-local observer was added;
   no WorldState identity was rewritten after runtime attachment.
3. **Status Trait visibility was initially asserted at the wrong surface.** A
   granted Trait remains in the active Status slot rather than the Actor's base
   trait list. The final check reads the real `mercy_mark.granted_traits`; the
   following #052 damage independently proves its Condition consumed it.
4. **Weather snapshot comparison over-dispatched Build C.** Weather `remaining`
   changes every Tick but is not a `weather_changed` event. The discarded run
   fired four Hooks. The final runner parses the Tick CausalTrace and dispatches
   only for exact `pmw.v04.weather.changed` derived events, producing two valid
   dispatches in A→B.

## Hypotheses that did not establish playable synergy

- **Build A:** valid Status-to-Condition interaction, but 3 net damage versus 24
  from two basic attacks. Reverse order heals the enemy after a dead action.
- **Build B:** setup enables the armor and prevents 9 damage, but two Guards
  prevent 14 with no environmental setup.
- **Build D:** #053 alone crosses the smoke threshold; adding #005 mostly
  saturates the same field. In the corrected weather-absent counterexample,
  `smoke_heat_front` is removed for all arms before attachment; extra smoke then
  produces no temperature feedback and still does not justify the second skill.
- **Build E:** both rates can coexist, yet either skill alone prevents the
  tested collapse. #042 alone has the same defense; far from the threshold the
  combined higher rate reduces initially abundant biomass faster.
- **Build F:** the initial analysis omitted the simple legal Wait→Fever Key
  strategy. Natural recovery supplies enough Mana after one Tick, reaching the
  same heat outcome at 75 HP rather than the combination's 66. At 14 HP the
  combination dies, and far from the threshold it buys no relevant outcome.

These results remain in the final catalog rather than being tuned into six
nominal successes.
