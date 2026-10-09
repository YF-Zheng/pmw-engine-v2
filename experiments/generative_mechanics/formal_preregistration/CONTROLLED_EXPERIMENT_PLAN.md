# Experiment 3 - Controlled Invention Plan

Status: `PLANNED_AFTER_FREE`; no collection is authorized. This experiment
uses frozen Controlled generation v0.2 and starts only after the Free formal
experiment is prepared and run under its own freeze.

## Questions

1. What fraction of executable mechanisms land in their assigned Low, Mid, or
   High realized-power band?
2. How well do realized values calibrate to ordered targets across bands?
3. Does the frozen guided-revision procedure improve target-band attainment?

The task measures control over realized power, not Free-Invention structural
diversity and not a global creativity score.

## Design Skeleton

Use matched canonical blocks across target bands and selected model
configurations. Randomize and interleave model and band order. Preserve initial
generation and guided revision as linked stages. The independent unit for band
attainment is the initial requested mechanism coordinate; a revision is a
paired observation belonging to that coordinate, not a second independent
sample.

Primary candidate estimands are target-band hit rate by assigned band,
absolute calibrated distance from the target band/target point, and paired
change in hit status or calibrated distance after the single frozen revision
opportunity. Report the complete schema/compile/execution chain on all requests.
Invalid outputs have realized-power metrics NA and remain failures in the
requested denominator.

The final protocol must define exact Low/Mid/High boundaries, boundary
inclusivity, power functional, revision information exposed to the model,
number of revisions, and handling of an invalid initial or revised response.
These values may not be inferred from formal outcomes.

## Analysis Skeleton

Report model-by-band estimates and mechanism-block bootstrap CIs. Use
block-respecting permutation or an explicitly frozen ordinal/hierarchical model
for the band effect, and paired randomization tests for revision improvement.
Predeclare omnibus and pairwise multiplicity before collection. Do not pool
bands into a score unless a scientifically interpretable estimand is separately
preregistered; no such score is authorized now.

Formal safeguards mirror Experiment 1: blind labels until analyses are frozen,
immutable and hash-linked raw artifacts, transport-only retries, no content
repair/retry, fixed N, documented stopping, no pooled model replacements, and
physical rejection of pilot/fixture/adversarial/calibration data.

## Required Pre-Collection Decisions

- model matrix, N per model per band, and inference-budget policy;
- exact power-band and revision contracts from frozen v0.2;
- collection seed, manifest, cost plan, and rate-limit schedule;
- finalized endpoints, tests, multiplicity, fixtures, lineage checks, and tag.
