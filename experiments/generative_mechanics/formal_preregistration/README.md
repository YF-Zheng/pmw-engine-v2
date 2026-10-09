# Formal Generative-Mechanics Preregistration

Status: `READY_FOR_OWNER_SIGNOFF`

Formal collection status: `NOT STARTED`

This directory fixes the design and analysis of the paper experiments before
any formal provider response is collected. It does not authorize collection.
Collection remains blocked until the owner resolves the model matrix, sample
size per model, and inference-budget policy, and the resulting manifest,
schedule, analysis implementation, fixture tests, hashes, commit, and
preregistration tag are frozen. The offline analysis and readiness implementation
is present and fixture-tested; the final model-specific request manifest cannot
exist until the owner gates are resolved.

## Experiments

1. **Free Invention** is the main experiment. Every selected system uses
   `gm-free-invention-v0.3`, the world-substrate interface, and
   `gm-free-evaluation-v0.5`.
2. **Interface Experiment** compares `isolated_direct_effect`,
   `matched_direct_outcome`, and `world_substrate` as representations. It is
   not a model-creativity ranking.
3. **Controlled Invention** uses frozen Controlled v0.2 to study target-band
   control after the Free experiment.

The generated mechanism is the independent inferential unit. Scenario,
context, and environment arms are repeated observations used to construct one
mechanism-level row; they never increase the generated-sample count. Results
are capability profiles. No creativity total score, composite rank, or
post-hoc primary endpoint is permitted.

## Document Map

- `RESEARCH_QUESTIONS.md`: confirmatory questions and non-directional hypotheses.
- `ENDPOINTS.md`: frozen primary and secondary endpoints.
- `DATA_DICTIONARY.md`: field units, denominators, aggregation, and NA/zero meanings.
- `STATISTICAL_ANALYSIS_PLAN.md`: estimands, uncertainty, tests, multiplicity, and sensitivities.
- `PAPER_OUTPUT_PLAN.md`: tables and figures selected before results exist.
- `INTERFACE_EXPERIMENT_PLAN.md`: Experiment 2 preregistration skeleton.
- `CONTROLLED_EXPERIMENT_PLAN.md`: Experiment 3 preregistration skeleton.
- `OWNER_DECISIONS.md`: the three unresolved collection gates.
- `FORMAL_COLLECTION_READINESS_REPORT.md`: readiness decision and remaining gates.

## Offline Commands

The formal CLI deliberately has no provider or collection command:

```text
python3 -m experiments.generative_mechanics.formal_cli generate-dry-manifest ...
python3 -m experiments.generative_mechanics.formal_cli validate-formal-lineage ...
python3 -m experiments.generative_mechanics.formal_cli analyze-formal-free-invention ...
```

Formal analysis fails closed unless frozen-manifest membership and the complete
raw-to-analysis artifact chain validate. Fixture or DEV pipeline checks require
the explicit `--non-formal-test-run` flag and emit `NON_FORMAL_TEST_RUN`.

The Luna/Terra DEV pilot is engineering and measurement evidence only. It may
exercise analysis code when output is marked `NON_FORMAL_TEST_RUN`; it cannot
enter formal estimates, choose a direction, tune a threshold, select a model,
or revise a hypothesis.

## Frozen Baseline

- Core manifest: `0cb9271e7dcfa9b1882246190f78afddfb1f153e699c7609182cbcd921cacf5d`
- Generation: `gm-free-invention-v0.3`
- Controlled generation: v0.2
- Evaluation: `gm-free-evaluation-v0.5`
- Evaluation semantic contract: `de843327762164af55c7ba342345a4861da2aab3d2082ecdd1392d4558e3b28f`
- Freeze tag: `free-evaluation-v0.5-frozen`

No problem identified here requires changing Core, generation v0.3,
Controlled v0.2, evaluator v0.5, world laws, environments, or the 36-reference
registry. A suspected contract defect must stop collection and be reported; it
must not be repaired inside the frozen experiment.
