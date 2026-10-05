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
