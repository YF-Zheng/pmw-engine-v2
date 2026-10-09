# Formal Collection Readiness Report

Decision: `READY_FOR_OWNER_SIGNOFF`

This means the preregistration package is ready for the three owner decisions.
It does **not** mean collection is authorized or started.

| Question | Answer |
|---|---|
| Any formal model request sent? | **NO.** Formal collection remains `NOT STARTED`. |
| Research questions locked? | **YES.** RQ1-RQ7 are non-directional capability-profile questions; Interface and Controlled are separate experiments. |
| Primary/secondary endpoints locked? | **YES.** P1-P6 are primary; reference-relative and other listed diagnostics are secondary/exploratory. |
| Independent unit? | **Generated mechanism/request coordinate.** |
| Arm-level pseudoreplication removed? | **YES.** Arms and contexts are summarized within mechanism and never count toward generated N. |
| Invalid-output policy? | All requested rows remain in the validity denominator; dynamic and structural metrics are NA, not zero. |
| Retry distinction? | Up to three exact transport attempts; no retry, repair, or continuation after returned content. |
| Pilot/formal isolation? | Formal analysis requires `dataset_kind=formal`; other kinds are test-only and marked `NON_FORMAL_TEST_RUN`. Machine enforcement is part of the readiness suite. |
| Collection order? | Preregistered block-interleaved schedule from a seed frozen before any call. |
| Analysis fixed before formal data? | **YES.** The executable pipeline implements P1-P6, 10,000-replicate mechanism/bootstrap CIs, 100,000 within-block permutations, omnibus Holm gating, opened-pairwise Holm, secondary BH, effect sizes, S1-S5, and prespecified outputs. A checked-in fixture run is marked `NON_FORMAL_TEST_RUN`. |
| Blind analysis? | Blind labels are required through integrity, exclusions, primary analysis, and sensitivities; mapping opens only after output hashes freeze. |
| Multiplicity policy? | Holm across six primary omnibus tests; gated pairwise primary contrasts use a second Holm family; secondary omnibus tests use BH-FDR at q=0.05. |
| Sample-size options? | 100, 150, or 200 per model; exact precision, rare-event coverage, and cost are supplied by the companion sample/cost plans. |
| Model matrices? | 4-model budget, 5-model balanced, or 6-model extended; exact candidates are supplied by the companion matrix files. |
| Inference policy? | Owner chooses deployed system-level configuration or approximate matched inference budget; neither is silently defaulted. |
| Frozen-contract break required? | **NO.** No evidence requires changing Core, generation v0.3, Controlled v0.2, evaluator v0.5, world laws, environments, or reference mechanics. |

## Locked Statistical Choices

- mechanism-level nonparametric bootstrap, 10,000 replicates, percentile 95% CIs;
- within-base-sample model-label permutation omnibus tests, 100,000 replicates;
- risk differences for binary outcomes, differences in mechanism-level means
  for rates, median differences for depth, and collision-probability differences
  for structure;
- explicit four-quadrant mechanism summaries;
- five and only five prespecified sensitivity families S1-S5;
- no total score, no overall creativity rank, and no post-hoc promotion.

## Open Owner Gates

1. **Gate A:** select the 4-, 5-, or 6-model matrix and resolve exact IDs.
2. **Gate B:** select 100, 150, or 200 mechanisms per model.
3. **Gate C:** select system-level or matched inference-budget policy.

Until all gates close, final request coordinates and collection seeds remain
unfrozen and the collection guard must refuse execution.

## Stop And Replacement Readiness

The preregistration fixes N and permits stopping only for critical evaluator
failure, prolonged provider unavailability, permanent model withdrawal,
raw-data corruption, or protocol violation, with an incident report. A retired
model is either removed as a whole by owner decision or replaced by a newly
identified model collected from zero to the full N. Versions are never merged.

## Final Pre-Collection Freeze

After owner signoff, populate the registry, generate and hash the unsent request
manifest and deterministic schedule, verify model-visible prompt matching, run
all Core/Generative Mechanics/formal isolation/fixture tests and JSON/JSONL
validation, confirm protected paths unchanged, commit, and tag. Only then may
the owner separately authorize collection.

Final state for this round: `READY_FOR_OWNER_SIGNOFF`

## Readiness Evidence

- PMW Core: 254 tests passed.
- Generative Mechanics, including formal infrastructure: 345 tests passed.
- Focused formal/statistical suite: 28 tests passed (included in the counts above).
- Dry manifest: `dataset_kind=synthetic_mock`, `sendable=false`.
- Formal request manifest: absent by design; all owner gates remain unresolved.
- Formal provider requests sent: 0.
- Fixture outputs: `readiness/fixture_analysis/`, all marked `NON_FORMAL_TEST_RUN`.
- Artifact hashes: `readiness/ARTIFACT_MANIFEST.json`.
