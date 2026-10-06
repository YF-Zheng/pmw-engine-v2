# Free-Invention Dynamic Evaluation v0.4 Candidate

## Status and scope

This is the candidate measurement protocol for responses collected under the
frozen `gm-free-invention-v0.3` generation contract. It does not change that
prompt, response schema, or request identity. It changes no PMW Engine code and
does not extend Protocol v0.2-Controlled.

The evaluation protocol is not frozen until its registered panel, three primary
measurements, counterfactual tests, and bias audit all pass. It reports a
capability profile. There is no creativity total, weighted composite, model
ranking scalar, or post-hoc threshold for calling a model creative.

## Two distinct experiments

### A. Representation-interface experiment

Conditions are `isolated_direct_effect`, `matched_direct_outcome`, and
`world_substrate`. The estimand is the effect of the generation interface on
systemic consequences under a fixed world and evaluation procedure.

The two direct-outcome interfaces are intentionally invisible to generic world
laws. Their zero downstream depth or differentiation is a manipulation check,
not evidence that the generating model failed to invent. This experiment may
support claims about representational affordances only.

### B. Model-invention experiment

All compared models, prompting strategies, and inference budgets use exactly
the `world_substrate` SkillSpec interface and the same request allocation. The
estimand is the difference between generators under a fixed representational
surface. Only this experiment may support comparative claims about model
invention capability.

Results from A and B are never pooled into one model ranking.

## Unit, validity, and evidence

The unit is one independently issued request and its preserved provider
response. Schema validity and trusted compilation are gates, reported with
their own denominators. Invalid samples remain in validity-rate denominators and
have unavailable dynamic measurements; they are never assigned metric zero.

Every dynamic observation is paired:

1. execute the candidate in a clean registered scenario;
2. execute the same scenario without the candidate;
3. retain only candidate-attributable differences;
4. preserve canonical evidence sufficient to recompute the reported profile.

## Primary measurement 1: downstream causal depth

The object is a trace-constrained dependency graph, not elapsed time or the
number of simulation steps. The candidate activation is the root. A generic
`gm.world.*` law can enter the graph only when it is an additional executed law
relative to the paired candidate-absent run and is reachable through committed
write-to-read dependencies from the candidate or another retained world law.
For each world-to-world edge, the source must be the last effective committed
writer of an address read by the target, and ablating the source law must reduce
the target occurrence count. Candidate-to-world edges use the primary
candidate-absent arm as their intervention. The evidence records every retained
edge's excluded law and present-versus-ablated occurrence counts.

The profile reports the longest downstream world-law path, reached law IDs,
canonical nodes and edges, and scenario-level availability. Candidate-authored
skill laws are root evidence but are not counted as downstream depth. Repeated
execution of one law does not by itself create additional structural depth.
Each arm also reports `candidate_activated`. A legal candidate whose activation
conditions are not met has unavailable depth (`null`), not depth zero. Depth
zero is reserved for a committed candidate activation with no attributable
downstream world law.

## Primary measurement 2: cross-environment differentiation

Each registered context forms a matched quartet over `mine`, `wetland`,
`industrial_yard`, and `fragile_bridge`. Mechanic, public initial fields,
environment variant, program, horizons, target count, and active build are
identical within a quartet. Only the environment's hidden material/process
state and kind differ.

The confirmatory panel contains six preregistered public-field contexts:
`all_low`, `neutral`, `all_high`, `alternating_a`, `alternating_b`, and
`gradient`. The full definitions and their canonical SHA-256 digest are frozen
in `evaluation/protocol_v0.4.json`. Across the panel every one of the eight
public fields appears at low, neutral, and high levels. A single quartet remains
an audit primitive and must not be reported as the candidate's overall
cross-environment profile.

The same manifest contains a fail-closed semantic-contract digest. It binds the
four environment JSON assets, public context panel, program and horizons,
observed surfaces, environment variant, target count, active-build policy,
world-law file, substrate system laws, and the hashes of the implementation
modules that define compilation and execution. Any drift in those inputs makes
confirmatory evaluation fail instead of silently changing the estimand.

For each environment, the evaluator first computes candidate-present minus
candidate-absent outcome and downstream signatures. It then compares those
four net-effect signatures. Initial-state differences and background world-law
activity therefore cannot count as differentiation. The profile reports the
four canonical net signatures, distinct-signature count, pairwise difference
matrix, per-context distributions, and the contexts in which differentiation
occurs. Context or environment ordering must not change the result, and the
distribution is not collapsed to one score.

## Primary measurement 3: structural novelty

Structural novelty is reported at multiple resolutions against a versioned,
registered reference catalog. Identity text and exact magnitudes are removed
before structural comparison. Effect polarity (`negative`, `zero`, or
`positive`) is retained so sign changes and no-op writes cannot masquerade as
the same structure. Effect and condition order is canonicalized.

Zero-delta writes are no-op evidence, not topology. They are excluded from the
fingerprint and reference comparison. A mechanism whose every declared effect
is zero has no effective write topology: structural novelty is unavailable and
the sample is explicitly excluded from the novelty-rate denominator. In a
mixed mechanism, zero writes remain visible as no-op evidence but cannot make
an otherwise known effective topology novel.

The profile reports:

- an exact canonical topology fingerprint and whether it already exists;
- the non-dominated registered-reference frontier and source catalog categories;
- unweighted difference components for reads, writes, trigger operators,
  temporal shape, effect cardinality, and condition cardinality;
- provenance and digest of the reference catalog.

Numeric tuning, renaming, list reordering, and zero writes cannot establish
structural novelty. Difference components are not collapsed into a weighted
novelty score or described as a subjective nearest-family distance.

## Reporting

Per-generator reporting includes validity rate, duplicate-structure rate,
total arm count, activated arm count, activation rate, the distribution of
causal depths conditional on activation, the frequency and pattern of matched-quartet
differentiation, exact-reference novelty rate, source-catalog categories on the
non-dominated reference frontier, and raw structural difference components.
Uncertainty is computed over independent
requests, not over scenario executions from the same request.

The first release is descriptive and confirmatory with respect to the frozen
definitions. Human expert review, if later added, is a separate convergent-
validity study and cannot silently relabel the machine measurements as objective
creativity.

## Freeze gates

The candidate becomes frozen only after all of the following hold:

- direct-outcome isolation is verified and described as an interface result;
- candidate-absent and unrelated background activity cannot inflate metrics;
- matched-quartet invariants and environment-order invariance pass;
- renaming, numeric perturbation, and list ordering cannot create topology;
- genuine read/write or temporal topology changes are detected;
- outputs contain evidence and `available/reason`, never fabricated zeros;
- the complete experiment and PMW Core suites pass with no Core file changes.
