# Statistical Analysis Plan

## Analysis Populations And Unit

The independent inferential unit is the generated mechanism. The formal table
contains one row per requested mechanism. Arms, contexts, environments,
retries, effects, and trace nodes are nested evidence, not independent samples.

- **Requested population:** every scheduled request, used for P1 and the full
  validity/failure chain.
- **Valid population:** execution-valid mechanisms, used conditionally for
  P2, P4, P5, P6 and valid-only secondary constructs.
- **Activated population:** execution-valid mechanisms with at least one
  activated arm, used for activation-conditional P3.

These populations are reported together to expose survivorship. Invalid rows
remain in the requested table, but their dynamic and structural values remain
NA. No complete-case result is described as end-to-end success.

## Locked Endpoints And Estimands

P1-P6 are defined in `ENDPOINTS.md`. Per model, report P1 as a requested-level
proportion; P2, P5, and P6 as the mean and distribution of mechanism-level
proportions; P3 as the distribution and median of mechanism-level median
depths; and P4 as the within-model unordered-pair abstract-fingerprint
collision probability. Lower P4 means more observed abstract diversity.

The principal hypotheses are two-sided, non-directional model effects for each
P1-P6. Alpha is 0.05. No model ordering is hypothesized.

## Descriptive Estimates And Confidence Intervals

Every model is shown independently before comparisons. Report eligible N,
missing N and reasons, point estimate, 95% CI, and the observed distribution.
Use 10,000 deterministic nonparametric bootstrap replicates, with a seed fixed
in the final preregistration registry, resampling mechanisms within model.
Percentile 2.5% and 97.5% quantiles form the CI. For P4, recompute the collision
U-statistic in each replicate. If an estimate is undefined in a replicate
(fewer than two eligible observations), omit that replicate and report the
number omitted; if fewer than 9,500 valid replicates remain, report the CI as
NA and the endpoint as underidentified for that model.

For pairwise effect-size CIs, resample complete `base_sample_index` blocks
jointly so the matched rows for all compared models remain together. Conditional
endpoint NA values remain attached to their mechanism rows. If incomplete
collection prevents a complete-block contrast, report that pairwise CI as NA in
the confirmatory output and show any unpaired estimate only as an explicitly
labeled incomplete-collection sensitivity.

Arm-level empirical distributions may be plotted descriptively, but uncertainty
and model comparisons are based on mechanism-level rows.

## Omnibus Model Tests

Use a permutation-based omnibus test for every primary endpoint, with 100,000
permutations and an exact enumeration when the admissible permutation space is
smaller. Mechanism records, including their validity/NA state and all nested
summaries, move as indivisible units.

The final matched request pool is block-interleaved by `base_sample_index`.
Permute model labels within each complete base-sample block, preserving one
record per model and the original collection coordinate. If a prespecified
model is removed in full under the replacement rule, remove that model before
forming blocks. An incomplete request block caused by an allowed terminal
collection stop is excluded from the confirmatory permutation analysis and
retained in descriptive requested counts; the complete-block analysis is then
labeled incomplete-collection sensitivity rather than a clean confirmatory
completion.

Test statistics are:

- P1, P2, P5, P6: sum across models of `n_g * (mean_g - mean_pooled)^2`.
- P3: sum across models of `n_g * (median_g - median_pooled)^2`.
- P4: sum across models of `eligible_pair_count_g *
  (collision_g - collision_pooled)^2`, where the pooled reference is computed
  over within-model eligible pairs, not cross-model pairs.

For conditional endpoints, NA remains attached to the permuted mechanism and
is omitted only from that endpoint's statistic. This preserves the frozen
missingness rather than imputing zero. P1 separately tests model differences in
the selection boundary.

The Monte Carlo p-value is `(1 + number(T_perm >= T_obs)) / (B + 1)`.
Failure to reject is not evidence of equivalence.

## Multiplicity And Pairwise Comparisons

The six P1-P6 omnibus p-values form one confirmatory family and receive Holm
family-wise correction. Pairwise comparisons for an endpoint are opened only
if that endpoint's Holm-adjusted omnibus p-value is at most 0.05. All opened
two-sided model-pair contrasts across all opened primary endpoints form one
additional Holm family. Closed endpoints have no confirmatory pairwise claims.

Prespecified secondary endpoints are exploratory. Their omnibus p-values form
one Benjamini-Hochberg family at FDR `q=0.05`; exploratory pairwise estimates
may be shown with unadjusted 95% CIs but are not significance claims. No
secondary result becomes primary because it is significant.

## Effect Sizes

- P1 and binary secondary endpoints: pairwise risk difference with bootstrap
  95% CI; risk ratio is supplemental and is NA when its denominator risk is 0.
- P2, P5, P6: pairwise difference in model mean mechanism-level proportions,
  with bootstrap 95% CI.
- P3: pairwise difference of sample medians with bootstrap 95% CI; also show
  empirical CDFs.
- P4 and semantic sensitivity: pairwise collision-probability difference with
  bootstrap 95% CI.
- Four quadrants: pairwise differences in mean mechanism-level quadrant
  fractions with bootstrap CIs.

All contrast signs are `first listed blind label minus second listed blind
label`. Report estimates regardless of p-value.

## Outcome/Path Four-Quadrant Analysis

Each of six contexts within a valid mechanism belongs to exactly one quadrant:
same/same, same/different, different/same, or different/different. Construct
four fractions per mechanism, summing to 1, then summarize across mechanisms.
Contexts are never treated as six independent generations. Empty quadrants are
reported as observed zeros and do not trigger evaluator changes.

## Prespecified Sensitivity Analyses

1. **S1, selection boundary:** interpret P2-P6 among execution-valid mechanisms
   beside P1 and the full validity chain; additionally show an end-to-end
   descriptive product `P(execution valid) * conditional mean` only for P2,
   P5, and P6. It is not a new primary endpoint or total score.
2. **S2, depth summary:** replace the per-mechanism median realized depth with
   maximum realized depth. Never flatten arms.
3. **S3, structural representation:** replace abstract-fingerprint collision
   with semantic-fingerprint collision; report both unique fractions.
4. **S4, safety refusals:** show the validity breakdown with safety refusals in
   the requested denominator (primary) and a descriptive denominator excluding
   them. The latter cannot replace P1.
5. **S5, backend drift:** if recorded provider metadata establish a backend
   version change during collection, repeat mechanism-level estimates by
   preregistered collection-time block and test a model-by-time-block
   interaction descriptively. Do not create time blocks from observed outcomes.

No additional sensitivity is confirmatory. Unexpected analyses are labeled
post-hoc exploratory.

## Failure, Retry, Stop, And Replacement Rules

Transport failures (timeout, 429, temporary unavailability) may retry the exact
same request at most three total transport attempts. Request bytes, sample
identity, model ID, and request ID must be unchanged and every attempt retained.
A first returned content response is terminal: safety refusal, empty response,
malformed JSON, schema/compile/execution invalidity, and `finish_reason=length`
receive no content retry, repair, continuation, or replacement.

Collection stops only for critical evaluator failure, prolonged provider
unavailability, permanent model withdrawal, raw-data corruption, or protocol
violation. The fixed N is never increased for significance, precision, or
failure replacement. An incident report is mandatory.

If a model is withdrawn or its fixed version becomes unavailable, stop that
model and preserve its data. The owner either removes the entire model from the
confirmatory matrix or treats a replacement as a new model collected from zero
to the full fixed N. Versions are never pooled. Requested and returned model
IDs, timestamps, and provider metadata are retained; unavailable returned IDs
are explicitly recorded as unavailable.

## Blinding, Reproducibility, And Unblinding

Integrity checks, exclusions, primary estimates/tests, and sensitivities use
sealed random labels (`Model A`, `Model B`, ...). Unblinding occurs only after
those outputs and an analysis manifest are hash-frozen. Exclusions are limited
to non-formal dataset kind, duplicate/corrupt identity, failed lineage, or a
documented protocol violation; content failures are outcomes, not exclusions.

Formal raw requests and provider responses are immutable and SHA-256
manifested. Every statistic must trace through parsed response, `SkillSpec`,
compiled mechanic, execution traces, v0.5 profile, and mechanism row to raw
hashes. DEV pilot, fixture, adversarial, and calibration rows must be rejected
by the formal pipeline. Analysis test runs on them are labeled
`NON_FORMAL_TEST_RUN`.
