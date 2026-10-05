# Generative Mechanics Lab

This is the isolated Generative Mechanics research prototype built on the frozen PMW engine. It contains four loadable environments, 24 skill-independent world laws, 36 seed SkillSpecs, strict compilers for substrate and direct-control mechanics, 12 executable benchmark scenarios, clean-world evaluation, exhaustive bounded build search, paired Emergent Reach, exploit analysis, batch generation experiments, and publication-figure rendering.

See [DESIGN.md](DESIGN.md) for the frozen contracts and compiler boundary.

## Layout

```text
compiler.py             deterministic SkillSpec -> PMW laws
spec.py                 strict SkillSpec v0.1 validation
substrate.py            eight frozen public channels
substrate/world_laws.json
environments/*.json     Mine, Wetland, Industrial Yard, Fragile Bridge
skills/*.json           36 seed mechanics plus manifest
smoke.py                actual PMW execution in all environments
generation.py           versioned generator protocol and 240-sample fixtures
batch.py                resumable evaluation and single guided revision
analysis.py             cross-environment, aftermath, evaluator, kill criteria
figures.py              Figures 1-5 in PDF/SVG/300 dpi PNG
tests/                  experiment-local regression suite
```

## Commands

Run from the repository root:

```bash
PYTHONPATH=src:. python3 -m experiments.generative_mechanics validate-skills
PYTHONPATH=src:. python3 -m experiments.generative_mechanics compile-skill experiments/generative_mechanics/skills/static_grave.json
PYTHONPATH=src:. python3 -m experiments.generative_mechanics smoke
PYTHONPATH=src:. python3 -m experiments.generative_mechanics run-scenario experiments/generative_mechanics/scenarios/held_out/short_combat.json --skills static_grave
PYTHONPATH=src:. python3 -m experiments.generative_mechanics evaluate-skill static_grave --split held_out
PYTHONPATH=src:. python3 -m experiments.generative_mechanics evaluate-build static_grave kindling_arc --split held_out
PYTHONPATH=src:. python3 -m experiments.generative_mechanics search-build static_grave kindling_arc clear_sky --split calibration
PYTHONPATH=src:. python3 -m experiments.generative_mechanics evaluate-candidate static_grave kindling_arc clear_sky --split held_out
PYTHONPATH=src:. python3 -m experiments.generative_mechanics generate-fixture /tmp/gml-fixture.jsonl
PYTHONPATH=src:. python3 -m experiments.generative_mechanics generate-requests /tmp/gml-requests.jsonl --per-cell 40
PYTHONPATH=src:. python3 -m experiments.generative_mechanics ingest-responses /tmp/gml-fixture.jsonl
PYTHONPATH=src:. python3 -m experiments.generative_mechanics run-batch /tmp/gml-fixture.jsonl /tmp/gml-batch --profile full
PYTHONPATH=src:. python3 -m experiments.generative_mechanics analyze-results /tmp/gml-fixture.jsonl /tmp/gml-batch /tmp/gml-analysis.json
PYTHONPATH=src:. python3 -m experiments.generative_mechanics render-figures /tmp/gml-batch /tmp/gml-analysis.json /tmp/gml-figures
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/tests -v
```

All command output is deterministic JSON. `smoke` activates `Static Grave` unchanged in all four worlds, runs `lab.step`, drains its finite schedule, and reports fields plus downstream process/outcome state.

`generate-fixture` creates deterministic pipeline fixtures, not LLM output. Real provider responses use the same strict JSONL envelope documented in `generators/`. Figure 4 deliberately reports `unavailable` unless `analyze-results --ground-truth scores.json` receives an independent sample-to-score mapping.

The checked-in JSON assets are reproducible with:

```bash
PYTHONPATH=src:. python3 -m experiments.generative_mechanics._generate_assets
```

The compact 240-fixture batch, cross-environment table, analysis, and all figure formats are reproducible with:

```bash
PYTHONPATH=src:. python3 -m experiments.generative_mechanics.results.generate_fixture_240
```
