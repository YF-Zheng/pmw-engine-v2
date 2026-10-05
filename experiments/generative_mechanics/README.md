# Generative Mechanics Lab: paper protocol v0.2

This isolated research lab runs on the frozen PMW engine. Protocol v0.2 fixes
the pre-pilot experimental contract; checked-in deterministic fixtures validate
infrastructure and are not LLM findings.

## Frozen study design

- Generation uses three controls: `isolated_direct_effect`, `world_substrate`,
  and expression-budget-matched `matched_direct_outcome`.
- Every provider request has a coordinate-derived sample ID, seed, nonce, and
  canonical prompt hash. Repeated samples within a cell are distinct requests.
- Prompts disclose normalized public-channel semantics, compact generic-law
  summaries, and six scored calibration examples. Evaluation environment state
  and the Oracle distribution are never disclosed.
- The eight substrate fields are bounded to `[0, 1]` by traced PMW laws and
  undergo explicit step-driven dissipation.
- `IntrinsicPower` is horizon-aware over combat-end, short, and medium
  snapshots. `ContextualMarginalPower` is a separate estimand: exact best-build
  change for a scenario backpack of 10 skills after adding one candidate, with
  active count and slot cost both capped at 6.
- Calibration, evaluation, and hidden Oracle are separate. The deterministic
  144-case Oracle defines `OracleIntrinsicPower` and
  `OraclePersonalizedDelta` targets.
- Cross-environment results are reported by baseline. Structural diversity and
  parametric diversity are reported separately.
- Parameter rescaling in `batch.py` is a deterministic controller baseline. It
  is not described as LLM self-revision.

The cheap CI/batch profile defers contextual search and records it as
unavailable, never as zero. Use `--contextual exact` for a real pilot or final
evaluation. Exact Oracle personalized search is intentionally expensive.

## Layout

```text
generation.py           v0.1 replay plus v0.2 request/envelope contracts
baseline_v02.py         expression-matched direct-outcome control
power_v02.py            authoritative scale and the two power estimands
scenario.py             calibration/evaluation/oracle scenario contract
oracle.py               deterministic hidden-suite reconstruction and targets
substrate.py            eight bounded public channels and system laws
batch.py                fault-isolated evaluation and deterministic controller
analysis.py             stratified statistics and two-task estimator analysis
diversity.py            structural and parametric fingerprints
generators/archive.py   byte-reproducible ZIP builder
```

## Commands

Run from the repository root:

```bash
PYTHONPATH=src:. python3 -m experiments.generative_mechanics validate-skills
PYTHONPATH=src:. python3 -m experiments.generative_mechanics smoke
PYTHONPATH=src:. python3 -m experiments.generative_mechanics run-scenario experiments/generative_mechanics/scenarios/evaluation/short_combat.json --skills static_grave
PYTHONPATH=src:. python3 -m experiments.generative_mechanics evaluate-skill static_grave --split evaluation
PYTHONPATH=src:. python3 -m experiments.generative_mechanics evaluate-candidate clear_sky static_grave kindling_arc --split evaluation

# v0.2 is the default: 3 baselines x 3 bands x 15 = 135 pilot requests
PYTHONPATH=src:. python3 -m experiments.generative_mechanics generate-requests /tmp/gml-pilot-requests.jsonl --per-cell 15

# CI defers exact contextual search; real/final runs must request it explicitly
PYTHONPATH=src:. python3 -m experiments.generative_mechanics run-batch responses.jsonl results/pilot --profile full --contextual exact
PYTHONPATH=src:. python3 -m experiments.generative_mechanics analyze-results responses.jsonl results/pilot results/pilot-analysis.json --ground-truth oracle-targets.json
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/tests -v
```

The ground-truth file has two independent tables:

```json
{
  "IntrinsicPower": {"sample-id": 42.0},
  "ContextualMarginalPower": {"sample-id": 7.5}
}
```

The analysis never computes an error between an intrinsic estimator and a
contextual Oracle target. The old `sample_id -> scalar` format remains readable
only as an intrinsic-only replay format.

`generate-requests --protocol v0.1` exists solely to reproduce the historical
two-baseline fixture protocol. New model collection must use the default v0.2.
