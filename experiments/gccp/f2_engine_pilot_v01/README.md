# GCCP F2 Engine-First Pilot v0.1

This experiment connects the four-world F2 decision problem to the real PMW
Gameplay runtime. PMW Laws own every physical M/S transition, probe intervention,
repair effect, material receipt, and world-time tick. The exact solver receives
only allowlisted public observations and reconstructs a fresh runtime for every
hidden-world branch.

The referenced `gccp_f2/f2_minimal.py` and README were not present in the
repository, Git history, or supplied attachments. `reference_model.py` is an
independent reconstruction from the task's stated priors and three Q-value
anchors; it is not presented as a run of unavailable source code.

## Run

From the repository root:

```bash
PYTHONPATH=src:. python3 -m experiments.gccp.f2_engine_pilot_v01.run_pilot
PYTHONPATH=src:. python3 -m unittest -v \
  experiments.gccp.f2_engine_pilot_v01.tests.test_f2_engine
```

The evidence generator writes:

- `evidence/engine_physics.json`: WorldState before/after, EventResult, and
  CausalTrace for no intervention, probes, and four-Tick repairs.
- `evidence/observation_boundary.json`: four initial observations and
  calibration histories.
- `evidence/solver_results.json`: complete exact policy trees and Q values.
- `evidence/pilot_result.json`: combined reproducible result.

## Public API usage

The scenario uses `build_gameplay_world`, detached content initialization,
`compile_content`, `build_content_session`, `MechanismRegistryRuntime`,
`parse_skill_blueprint`, `material_authority`, `change_loadout`,
`resolve_action`, and `spend_world_time`. Experiment-only PMW Laws are appended
to the trusted compiled content before runtime attachment. No frozen Core,
Gameplay, historical GM, SkillLab, or Build Synergy file is modified.

W and R are public Area Dynamics Fields. H, X, and M remain in a private
component; S is projected explicitly by the F2 observation allowlist. Raw
WorldState, checkpoints, EventResult, CausalTrace, law matches, and Registry
internals remain trusted evidence and never enter solver observations.

## Frozen inferred semantics

- Every calibrate, forge, and probe action spends exactly one preparation Tick.
- At most three preparation Ticks are allowed; repair may be selected at any
  information state.
- Probe success/failure reveals interface compatibility after the one-shot
  investment, but never directly reveals H or M.
- A repair is successful when stability after four real World Ticks is at least
  its pre-repair value.
- Equivalent-mode utility is binary terminal success minus `cf` and `ci` when
  those actions are actually taken. Native mode uses materials/time as hard
  constraints and does not compare its Q values to normalized-cost Q values.

See `F2_ENGINE_REPORT.md` for results, limitations, and the cycle record.

## Recorded verification

- F2 Engine Pilot: 13/13 passed in 97.916 seconds.
- Core: 254/254 passed in 25.655 seconds.
- Historical GM: 345/345 passed in 68.512 seconds.
- v0.6: 170/170 passed in 25.632 seconds.
- Gameplay v0.4: 172/172 passed in 78.646 seconds.
- Creative SkillLab 60-Skill Pilot: 7/7 passed in 264.579 seconds.
- Build Synergy Pilot: 10/10 passed in 116.274 seconds.
- Total current regression: 971/971 passed.
- Independent F2 review: 13/13 passed in 98.354 seconds.

Raw output is retained in `logs/`; `INDEPENDENT_REVIEW.md` records the separate
audit and its residual limitations.
