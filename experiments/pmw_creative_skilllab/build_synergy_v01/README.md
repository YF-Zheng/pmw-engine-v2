# PMW Build Synergy Pilot v0.1

This pilot tests six preregistered combinations drawn unchanged from the
Creative SkillLab 60-skill portfolio at commit
`f1e17bf8e58e48c6e13fd906ece8ac58b17a871d`. It creates no new skills and
modifies no PMW Core, Gameplay, or historical Generative Mechanics semantics.

## Scope and method

Each Build runs six comparison arms in fresh deterministic worlds:

```text
No Skill / A Only / B Only / A -> B / B -> A / Matched Alternative
```

Every arm uses the same initial Actor, Area, Weather, Ecology, random seed,
enemy policy, four combat-round opportunities, and final observation horizon.
The player and enemy execute through `run_combat_round`; therefore each round
advances exactly one formal World Tick and charges the TimeLedger once. Failed
actions reject atomically and are replaced by a wait for that already-budgeted
opportunity. No prerequisite Trait or field outcome is injected after the
detached time-zero world is created.

The shared builder parses each material against its own authority, compiles all
Build skills into one content Registry, and equips only the skills assigned to
the current arm. All timelines and traces come from the real Gameplay session.

## Run

From the repository root:

```bash
PYTHONPATH=src:. python3 -m experiments.pmw_creative_skilllab.build_synergy_v01.runners.run_builds
PYTHONPATH=src:. python3 -m experiments.pmw_creative_skilllab.build_synergy_v01.runners.run_builds --build-id build_c
PYTHONPATH=src:. python3 -m experiments.pmw_creative_skilllab.build_synergy_v01.runners.build_reports
PYTHONPATH=src:. python3 -m unittest experiments.pmw_creative_skilllab.build_synergy_v01.tests.test_build_synergy -v
```

The recorded Build suite covers 6 Builds, 11 scenario variants, 66 arms, and
264 formal combat rounds. Its final 10-test suite ran in 113.846 seconds.

## Results at a glance

|Build|Functional|Mechanical interaction|Strategic value|Classification|
|---|---|---|---|---|
|A: Mercy + Execution|yes|yes|no|`MECHANICALLY_INTERESTING`|
|B: Rain setup + Paper Armor|yes|yes|no|`MECHANICALLY_INTERESTING`|
|C: Storm + Relay|yes|yes|yes, tested task|`PLAYABLE_BUILD`|
|D: Smoke stacking|yes|no, redundant|no|`EXECUTABLE_ONLY`|
|E: Ecology rates + Root defense|yes|no, diminishing additive|no|`EXECUTABLE_ONLY`|
|F: Mana debt + Fever Key|yes|yes|no, dominated by waiting|`MECHANICALLY_INTERESTING`|

Build C is explicitly limited by `manual_trusted_hook_dispatch`. The runner
calls the public Hook executor only when the preceding World Tick's CausalTrace
contains a real `pmw.v04.weather.changed` derived event, and records that event
as the Hook lineage root. This is not a claim of production automatic routing.

Independent counterexample review rejected the first Build F judgment: waiting
one round for natural Mana recovery and then using Fever Key reaches the same
temperature and weather while retaining 9 more HP. The corrected arm and
classification are preserved in the evidence rather than tuned away.

## Files

- `build_specs/`: initial conditions, objective, arms, actions, and variants.
- `runners/`: multi-skill world construction, real execution, and reporting.
- `evidence/`: compact JSON with complete timelines and CausalTrace values.
- `replays/`: human-readable Battle/World replay for every arm and Tick.
- `build_catalog.jsonl`: structured judgments and metrics.
- `build_portfolio.zh.md`: concise human/Judge presentation.
- `tests/`: real-runtime comparison and counterexample tests.
- `failure_log.md`: rejected assumptions and corrected runner defects.
- `independent_review.md`: independent counterexample audit and correction trail.
- `build_synergy_report.md`: full findings and limitations.

## Recorded regressions

- Build Synergy suite: 10/10 passed in 113.846 seconds (including fresh-run
  evidence and classification freeze checks).
- Original Creative SkillLab 60-Skill Pilot: 7/7 passed in 262.396 seconds.
- Frozen Core, GM, Scheduler, and Gameplay groups: 254 + 345 + 170 + 172 =
  941/941 passed in 25.747, 68.401, 25.458, and 77.913 seconds.
- Independent corrected-suite replay: 8/8 passed in 114.455 seconds.

The raw command output is retained under `logs/`. Only this Pilot directory was
added; frozen production and historical experiment files were not modified.

These are pilot results, not a balance standard or a claim that one qualified
example establishes broad RPG quality.
