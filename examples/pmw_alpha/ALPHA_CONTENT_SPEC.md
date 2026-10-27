# Before the Seventh Night: Content Specification

## Map

`mist_camp` connects to `moss_shallows` and `thunder_mine`.  Shallows connects
to `frost_forest`; Mine and Forest can independently unlock routes to
`ash_observatory`.  The Mine lift, once safely built, is permanent.  The
Forest root bridge appears only after a real biomass recovery window.

## Areas and Discoveries

| Area | Interactions | Rule discovered | Consequence |
| --- | --- | --- | --- |
| Mist Camp | insight dais, supply fire, survey map | preparation and rest | crafting, level choice, map notes |
| Moss Shallows | hydrology stele, moss bed, hidden fungal grove, mist beast | humidity produces fog | fog hides resources and changes beast combat |
| Thunder Mine | crystal vein, generator, sentinel, lift | charge sustains machinery | lift route; powered Boss shield risk |
| Frost Forest | spore bed, forest heart, root bridge, mycelial mass | biomass recovery is delayed | ecological route to Observatory |
| Ash Observatory | control console, stabilizer, observer | power and ecology change the finale | fight, seal, or fail |

## Craft Cores and Modifiers

Each core with each modifier is a legal deterministic recipe (12 total).

| Core | Instant glyph | Sustaining glyph | Echo glyph |
| --- | --- | --- | --- |
| Tide | humidity +0.30 / fog | humidity target +0.20 for 4 ticks | on fog: 3 shield |
| Thunder | charge +0.35 / discharge | charge target +0.25 for 4 ticks | on storm: damage conductive enemy 4 |
| Spore | biomass +0.25 | biomass target +0.20 for 5 ticks | on ecology recovery: heal 3 |
| Ash | temperature +0.30 / smoke | temperature target +0.20 for 4 ticks | on clear: scorch enemy 3 |

All recipes cost one Core material, one glyph material, 3 Mana to cast (Echo
is passive), and two World Ticks to craft.  Core materials also have world
uses: thunder crystal powers the lift, spore bud restores the forest, and ash
cinder can reinforce a build or stabilize the Observatory.

## Enemies and Endings

- **Mist Stalker** gains pressure in fog; Tide or non-visual skills counter it.
- **Conductive Sentinel** accumulates charge and releases it; Thunder control
  or Guard counters it.
- **Mycelial Mass** benefits from local biomass; ecological intervention or
  Ash changes its plan.
- **Ash Observer** gains periodic shield from an active Mine power relation.
  It changes behavior when low HP or the shield is absent.

Stable Seal requires a disabled/managed power risk, restored forest, and the
stabilizer interaction.  Forced Cut requires defeating the Observer and
closing the core but leaves a world scar.  Seventh Night occurs on death or
time exhaustion.
