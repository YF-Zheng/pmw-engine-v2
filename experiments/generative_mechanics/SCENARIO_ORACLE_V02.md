# Scenario and Oracle Protocol v0.2

## Splits

- `calibration`: public prompt examples and score calibration only.
- `evaluation`: the standard six-scenario executable estimator suite.
- `oracle`: hidden fixed-distribution ground truth; never prompt material and
  never used for evaluator tuning.

`held_out` was the v0.1 name for `evaluation`. APIs accept it as an explicit
alias and legacy scenario documents are canonicalized from
`held_out_<name>` to `evaluation_<name>`. There is no duplicate
`scenarios/held_out` directory, preventing the two names from drifting.
`load_scenario()` redirects a missing legacy `held_out/<name>.json` path to
the canonical `evaluation/<name>.json` asset.
Generator code must obtain scenario assets through
`scenario.public_calibration_paths()`, which returns calibration paths only.

## Scenario contract

Every scenario has exactly three ordered horizons: `combat_end`, `short`, and
`medium`. `horizon_weights` has exactly those keys, finite values in `[0,1]`,
and sum `1.0`. Capability weights remain a separate five-dimensional vector.
The backpack has exactly ten unique known skills and the active build exactly
six, respecting the six-slot cap.

`environment_variant` is one of the named public variants in `substrate.py`.
`initial_fields` is a sparse override restricted to the eight public channels
and normalized values. Material, process, outcome, actor resources, and any
hidden component cannot be introduced through this interface.

## Normalized substrate

The original 24 `gm.world.*` laws remain generic and skill-independent.
Two experiment-system laws are loaded separately:

1. `gm.substrate.01.normalized_bounds` is a PMW state law. If any public field
   leaves `[0,1]`, one closure transaction sets all eight channels to their
   clamped values. The correction is represented in the causal trace.
2. `gm.substrate.02.dissipation` handles explicit `lab.dissipate` events.
   Runner step commands execute `lab.step` and then one `lab.dissipate`, so
   interaction and relaxation cannot conflict on one PMW transaction.

No Python code mutates attached runtime state. The runner rejects invalid
pre-attach setup and checks the normalized invariant after every externally
observable root or scheduler dispatch.

## Oracle reconstruction

`oracle/manifest.json` freezes protocol, seed, and case count. `oracle.py`
rebuilds 144 canonical micro-scenarios spanning all categories, environments,
variants, channels, program shapes, ten-skill backpacks, legal six-skill
builds, and aftermath horizons. Expanded cases and traces are not committed.
