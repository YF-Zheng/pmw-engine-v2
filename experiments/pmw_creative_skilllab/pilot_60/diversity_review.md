# Diversity Review

## Distribution

| Measure | Observed |
|---|---:|
| Validated skills | 60 |
| Creator contribution | A–F: 10 each |
| Active / passive | 54 / 6 |
| Distinct kind + trigger + Effect-kind signatures | 39 |
| Cases with effect-level conditions | 18 |
| Cases with Status definitions | 16 |
| Final weather-state divergence | 10 |
| Final ecology-state divergence | 2 |
| Material tiers | 2 common, 18 fine, 32 rare, 8 epic |
| World-Tick horizon | 2–6 ticks; 3–4 ticks for 38 cases |

Effect coverage across all Blueprints is: 40 `modify_field`, 16
`apply_status`, 14 `damage`, 12 `modify_attractor`, 10 `heal`, 8 `shield`, 8
`modify_rate`, 5 `add_resource`, and 3 `grant_trait`.

## Repetition analysis

No two final Blueprints have the same ID, material, complete effect document,
scenario, and evidence. A coarse signature that ignores fields, conditions,
amounts, targets, and intended use does produce repeated families:

- four `heal + modify_field` skills (`skill_034`, `044`, `054`, `057`);
- four single-attractor skills (`skill_021`, `024`, `025`, `029`);
- three `damage + modify_field` skills (`skill_001`, `053`, `060`);
- three single-field modifiers (`skill_023`, `026`, `030`);
- three double-field modifiers (`skill_028`, `031`, `033`);
- three single-rate modifiers (`skill_022`, `027`, `037`).

These groups are not exact numeric reskins: for example, the four healing
skills respectively exchange inventory/time, wetness/salinity, ecology stock,
and an extreme-cold window. Still, the distribution is visibly field-heavy and
the passive share is only 10%. The current closed Effect vocabulary, not just
Creator preference, is a real source of convergence.

## Cross-system coverage

Strong examples include:

- `skill_002`: biomass consumption plus smoke can enter the shared smoke/heat
  weather loop rather than ending at direct damage.
- `skill_027`: changing biomass recovery alters the ecology collapse counter
  and yields a different final ecology regime.
- `skill_030`: a seemingly restorative phenology reset pushes the ecology from
  balanced to stressed in its tested trajectory.
- `skill_047`: smoke, a temporary biomass-rate penalty, mana debt, weather, and
  ecology all remain visible across four Ticks.
- `skill_049` and `skill_050`: real weather/damage source events precede trusted
  passive Hook execution; unrelated triggers reject atomically.
- `skill_053`: one point of direct damage is secondary to smoke-driven heat and
  ecological consequences.
- `skill_060`: deliberate self-damage pushes a public field across weather
  thresholds that affect both sides.

## Review status

Lead-side structural review found no unbounded numeric exploit, duplicate Skill
ID, unauthorized selector/effect, missing negative control, or unequal final
simulation time. All 60 integrated cases passed the real-runtime suite.

The required independent Reviewer was invoked only after the portfolio was
stable, but the sub-agent service rejected the Reviewer and two auxiliary audit
calls due to quota. Consequently this document is a reproducible Lead audit,
not an independent opinion. Independent authenticity and creativity review is
the only unfinished acceptance item and is marked **PARTIAL**.
