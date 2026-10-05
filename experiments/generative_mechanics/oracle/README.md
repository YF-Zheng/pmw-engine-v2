# Hidden Oracle Suite v0.2

`manifest.json` and `oracle.py` deterministically rebuild 144 micro-scenarios.
The checked-in asset is intentionally compact: execution traces and expanded
scenario JSON are outputs, not source artifacts.

The suite is an evaluation target, not prompt context. Generator prompts may
read only `scenarios/calibration/**`; standard evaluator selection may read
`scenarios/evaluation/**`. Neither may import this module or inspect Oracle
initial fields, environment variants, programs, backpacks, or horizons.

Each case contains a ten-skill backpack and a legal six-skill active build.
The fixed distribution covers all six scenario categories, four environments,
six public variants, sparse combinations of all eight normalized channels,
multiple programs, and distinct combat/short/medium aftermath horizons.

## Two registered targets

- `OracleIntrinsicPower` executes the complete 144-case suite.
- `OraclePersonalizedDelta` defaults to the 24-case exact-search subset. The
  subset is selected from the full suite, never generated independently, with
  one context per category/environment stratum. Registered 12- and 18-case
  profiles exist for sensitivity analysis; 24 is the formal default. The
  profiles are strictly nested (`12` is a subset of `18`, which is a subset of
  `24`), isolating the effect of adding contexts from the effect of resampling.

`contextual_subset` in `manifest.json` freezes the selector, seed, sizes, and
the digest of every profile. `contextual_subset_audit()` exposes a compact
coverage record without storing traces. A digest mismatch is a protocol error,
not an invitation to silently update expected output.

The term Oracle means executable ground truth *under the declared PMW utility
functional*. It does not mean objective or human-universal power. Results are
conditional on the scenario distribution, horizon/capability weights, and
legal-build constraints encoded here.
