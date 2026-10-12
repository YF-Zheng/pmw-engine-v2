# Pilot Summary

## Result

Sixty of sixty selected skills passed material parsing, Blueprint parsing,
content compilation, registry construction, legal loadout, a real Action or
trusted Hook success path, equal-time baseline comparison, and an atomic
negative control. Twelve additional concepts are explicitly unsupported. The
published suite has 7 tests and reran in 261.839 seconds.

All four frozen baseline suites also pass: 254 + 345 + 170 + 172 = **941/941**.

This supports a limited but useful conclusion: the current PMW Gameplay surface
can express substantially more than direct damage/healing cards. It supports
conditional resource exchanges, temporary attractor/rate changes, weather and
ecology threshold crossings, status-owned temporal effects, public-world costs,
and event-sourced passive reactions. It does not establish commercial balance,
large-world robustness, or comparative model creativity.

## Answers to the pilot questions

1. **How many actually ran?** 60 behavior-validated, 0 compile-only entries in
   the final catalog, 12 unsupported concepts outside the catalog.
2. **Most promising mechanisms:** temporary Dynamics modifiers, public fields
   consumed by shared Weather/Ecology Laws, Status lifecycles, and Hook-based
   conversion of real source events into bounded follow-up effects.
3. **Unexpected consequences:** `skill_027` prevents an ecology-collapse path;
   `skill_030` ends stressed despite restorative framing; smoke-focused
   `skill_047` crosses both ecology and weather processes; the deliberately weak
   `skill_053` derives most of its impact from shared heat/smoke Laws.
4. **Hard to express:** position/relation changes, two-area transfers, material
   conversion, event-payload-dependent amounts, historical-state reads,
   arbitrary future actions, and live Weather/Ecology graph editing.
5. **Template pressure:** yes. There are 39 coarse structural signatures for 60
   skills, `modify_field` dominates, and only 6 skills are passive. The
   strategies differ, but the closed Effect vocabulary imposes convergence.
6. **Build potential:** environmental primers plus conditional consumers,
   status markers plus follow-up attacks, smoke plus heat/ecology manipulation,
   and resonance/field setup plus passive recovery are credible small build
   kernels. This pilot validates components separately; it does not claim every
   named pairing has a dedicated joint experiment.
7. **Engine limits vs design limits:** missing relational, historical, delayed,
   and inventory-transform Effects are Engine-surface limits. The active-heavy
   mix, rare-material concentration, and frequent 3–4 Tick fixtures are Creator
   and pilot-design limitations.

## Evidence quality

Every evidence file contains both complete timelines, all formal event results,
full serialized CausalTrace values, the compiled skill hash, legal-stage status,
changed-step indices, and the negative-control message. `skill_catalog.jsonl`
provides a compact cross-reference; `creative_portfolio.zh.md` is the blind
reading layer.

## Remaining risk

Independent review is not complete. The fresh Reviewer and two audit agents
were invoked, but the platform rejected them at startup due to its usage limit.
The pilot is therefore complete as an implementation and evidence bundle but
**PARTIAL as a multi-party review process**. A future reviewer should rerun a
stratified sample, inspect claims against traces, and challenge the repeated
signature families before any downstream LLM-as-a-Judge exercise.
