# PMW Alpha v0.2: Before the Seventh Night

## Baseline

- Repository: `/ssd/zyf/pmw-engine-v2`
- Branch: `feature/alpha-v02-seventh-night`
- Starting commit: `7f0274b`
- Protected: `src/pmw`, historical Generative Mechanics experiments,
  preregistration, benchmarks, and the reproducible `examples/storm_relay` M0
  demo.

## Architecture

Alpha lives entirely in `examples/pmw_alpha`.  `AlphaSession` owns no second
world simulation: it constructs a PMW Gameplay WorldState, applies ordinary
PMW events/laws, advances the shared time ledger, and projects a player-safe
observation for the browser.  It reuses Gameplay actor, field, material,
registry, shield, checkpoint, and action contracts.  Alpha-specific map,
quest, enemy, ecology, and narrative facts live in explicit components and
are changed only through staged session commands or PMW Events.

## Delivery Slices

1. **P0 foundation**: audit M0, create the Alpha session/server/UI shell,
   normalize observations and command transactions, and prove restart,
   combat display, active-skill combat legality, and save/load.
2. **P1 exploration**: five Areas, observation/inspection knowledge, map
   connections, interactions, and route locks.
3. **P2 skills**: four cores x three modifiers, deterministic compilation,
   crafting, registration, equipment, and combat/exploration use.
4. **P3 world consequences**: forest ecology/root bridge and mine power/lift
   with real cross-area Tick evolution.
5. **P4 combat/growth**: three enemies, observer boss, bounded AI policies,
   level choices, and combat feedback.
6. **P5/P6 completion**: three endings, difficulty/time economy, save/load,
   browser playthroughs, QA, and packaged delivery.

## Current Decisions

- Alpha uses a fixed deterministic map and a small set of rich interactions,
  not free movement or generated quest content.
- Public observations intentionally reveal prose and only discovered values;
  raw component IDs, thresholds, Laws, and private AI state remain hidden.
- Every player command is cloned and staged before publication.  A failed
  command changes neither time nor materials nor registry state.
- A safe combat fallback always remains available, while ecology and mine
  choices alter time, routes, boss shields, and ending quality.

## Verification Cadence

Each slice adds unit and route tests, runs the M0 suite and frozen Core suite,
starts the local server, and performs an HTTP/browser smoke flow.  Playthrough
records will distinguish automated route execution from actual browser use.
