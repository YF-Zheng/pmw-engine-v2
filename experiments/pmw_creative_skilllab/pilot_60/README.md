# PMW Creative SkillLab — 60-Skill Open Creation Pilot

Status: **60/60 behavior-validated; independent review PARTIAL (platform quota blocked)**

This is a creative-capability pilot built on PMW Gameplay v0.4 Gate 5.2 at
repository baseline `635537e853642ba2075ab6d97de792f2792d1ff5`. It is not a
GCCP benchmark, a model leaderboard, a balance study, or a frozen research
protocol. No PMW Core, historical Generative Mechanics asset, or Gameplay
production module is modified.

## What is here

- Six isolated Creator agents contributed 10 selected skills each. Their
  directions were combat/environment, defense/status, weather/ecology,
  exploration/resources, cross-system combinations, and free experiments.
- Every selected case includes a parsed material, authorized blueprint,
  compiled content, formal registry manifest, legal loadout, and a real Action
  or trusted Hook execution.
- Every case runs from two fresh, equal initial worlds. Baseline and treatment
  advance through the same world-time horizon. Each also has an unequipped or
  wrong-trigger counterexample that must reject without mutating WorldState.
- `evidence/` contains the complete observed state series and serialized
  `CausalTrace` for all Action, phase, and World Tick events.
- Twelve divergent ideas that the current public Effect surface cannot express
  remain in `failure_log.md` instead of being simulated by private mutation.

## Reproduce

From the repository root:

```bash
PYTHONPATH=src:. python3 -m experiments.pmw_creative_skilllab.pilot_60.runners.run_pilot
PYTHONPATH=src:. python3 -m experiments.pmw_creative_skilllab.pilot_60.runners.run_pilot --case-id skill_047
PYTHONPATH=src:. python3 -m experiments.pmw_creative_skilllab.pilot_60.runners.build_portfolio
PYTHONPATH=src:. python3 -m unittest experiments.pmw_creative_skilllab.pilot_60.tests.test_pilot_60 -v
```

The complete test reruns all 60 success cases and all 60 negative controls. On
the recorded host it ran 7 tests in 261.839 seconds. `logs/run_all_60.log` and
`logs/test_pilot_60.log` retain the published run output.

The frozen baseline regressions also pass in full: Core 254, historical
Generative Mechanics 345, v0.6 next tracks 170, and Gameplay v0.4 172, for
**941/941**. The complete output is in `logs/gate52_regression.log`.

## Evidence map

- `skills/`: one material + blueprint + scenario document per validated skill.
- `skill_catalog.jsonl`: one structured record per skill, including exact final
  differences, triggered Law IDs, paths, and negative-control result.
- `creative_portfolio.zh.md`: blind Chinese portfolio without self-ratings.
- `evidence/`: full baseline/treatment timelines and traces.
- `runners/`: shared worlds, execution pipeline, and portfolio generator.
- `tests/`: real-runtime regression and evidence integrity tests.
- `failure_log.md`: unsupported concepts, repaired prototypes, and audit gaps.
- `diversity_review.md`: structural distribution and honest homogeneity risks.
- `pilot_summary.md`: conclusions and limitations.

## Shared environments and guardrails

The runner supplies wet forest, dry basin, storm plateau, mist cavern,
depleted/lush grove, rain edge, frozen hollow, and fever marsh fixtures. The
same public Weather, Ecology, Dynamics, Status, Shield, Action, Hook, Loadout,
and time-ledger APIs used by Gameplay v0.4 drive them.

Pilot-only published guardrails reject absolute effect amounts above 100,
effect durations above 8, mana costs above 15, and observation horizons above
8. These are content-screening rules, not new Engine semantics and not a claim
of global RPG balance.

## Important limitations

- The action resolver charges its action ledger but does not itself advance
  world time; the runner advances equal explicit World Ticks on both arms.
- There is no automatic event-to-Hook dispatcher. Passive cases first execute a
  real supported source event, then call the public trusted Hook executor.
- A top-level active-skill condition does not gate Action execution in this
  Gameplay version; condition-sensitive designs put conditions on Effects.
- Most cases use one tailored success environment. This validates execution,
  not general usefulness or balance across a large world distribution.
- The requested fresh independent Reviewer was launched after integration, but
  all three reviewer/auditor calls were rejected by the platform usage limit.
  No independent-review result is claimed; that gate remains **PARTIAL**.
