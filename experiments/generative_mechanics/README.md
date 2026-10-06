# Generative Mechanics Lab: Protocol v0.2-Controlled

This isolated research lab runs on the frozen PMW engine. Protocol
v0.2-Controlled fixes the controlled-invention pre-pilot contract; checked-in
deterministic fixtures validate infrastructure and are not LLM findings.

## Frozen study design

- Generation uses three controls: `isolated_direct_effect`, `world_substrate`,
  and expression-budget-matched `matched_direct_outcome`.
- Every provider request has a coordinate-derived sample ID, seed, nonce, and
  canonical prompt hash. The Controlled envelope also carries the master seed
  and sample index, and ingestion re-derives all three identity values.
  Repeated samples within a cell are distinct requests.
- Prompts disclose normalized public-channel semantics, compact generic-law
  summaries, and six scored calibration examples for the requested baseline:
  two each for Low, Mid, and High. The frozen artifact therefore contains 18
  examples across three schema-matched baselines. Evaluation environment state
  and the Oracle distribution are never disclosed.
- The eight substrate fields are bounded to `[0, 1]` by traced PMW laws and
  undergo explicit step-driven dissipation.
- `IntrinsicPower` is horizon-aware over combat-end, short, and medium
  snapshots. `ContextualMarginalPower` is a separate estimand: exact best-build
  change for a scenario backpack of 10 skills after adding one candidate, with
  active count and slot cost both capped at 6.
- Calibration, evaluation, and hidden Oracle are separate. The deterministic
  144-case Oracle defines `OracleIntrinsicPower`. Exact
  `OraclePersonalizedDelta` uses a preregistered, category/environment-stratified
  24-case subset; nested 12- and 18-case subsets are sensitivity profiles.
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
free_invention.py        frozen v0.3 request and ingestion contract
free_evaluation_v04.py   v0.4 candidate capability-profile integration
causal_depth_v04.py      paired, activation-aware, ablation-checked downstream depth
cross_environment_v04.py registered 6 x 4 matched-context panel
structural_novelty.py    versioned multi-resolution novelty evidence
free_evaluation_v05/     v0.5 split-construct evaluator and semantic lock
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

# v0.3-Free-Invention scaffold: request generation and strict ingestion
PYTHONPATH=src:. python3 -m experiments.generative_mechanics generate-free-invention-requests /tmp/gml-free-requests.jsonl --per-baseline 15
PYTHONPATH=src:. python3 -m experiments.generative_mechanics ingest-free-invention-responses responses.jsonl

# v0.5 candidate is default; v0.4 remains explicitly replayable
PYTHONPATH=src:. python3 -m experiments.generative_mechanics evaluate-free-invention responses.jsonl results/free-profiles.json
PYTHONPATH=src:. python3 -m experiments.generative_mechanics evaluate-free-invention responses.jsonl results/free-profiles-v04.json --evaluation-version v0.4

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
two-baseline fixture protocol. New controlled collection uses
`gm-generation-v0.2-controlled`. Archived `gm-generation-v0.2` responses remain
verifiable through their original shared-six-example canonical prompt; their
prompt hashes are never checked against the Controlled prompt.

Protocol v0.3-Free-Invention freezes request identity, prompt, envelope
validation, and trusted compilation. The separate v0.4 candidate now implements
three primary measurements: ablation-checked downstream causal depth, matched
cross-environment differentiation over six preregistered public-state contexts,
and multi-resolution structural novelty against a digest-bound 36-mechanic
reference catalog. It emits a capability profile and no creativity total.
Interaction surface, combinatorial potential, and self-containment remain
deferred; no genuine-model Free study has been run.

Dynamic Evaluation v0.5 leaves generation v0.3 unchanged and splits the v0.4
headlines into narrower constructs: realized dependency depth versus
necessity-backed depth; outcome differentiation versus causal-path
differentiation; and exact-match, near-copy, conservative recombination,
semantic-structure, and abstract-topology evidence. Activation and behavioral
inertness are independent. Binding identity is semantic unless an explicit
observational-equivalence class is registered. No creativity score, invention
score, total novelty score, or model ranking is produced. The default CLI is
v0.5; `--evaluation-version v0.4` preserves historical evaluation behavior.

Oracle targets are realized utility under the declared executable scoring
function and preregistered world-state distribution. They are machine-verifiable
study targets, not an objective human notion of game balance.
