# Preregistered Endpoints

## Statistical Unit And Populations

The independent unit is one requested/generated mechanism at one canonical
request coordinate. For P1 the population is all requested mechanisms. For
P2-P6 and structural/dynamic secondary endpoints the population is
execution-valid mechanisms for which the frozen evaluator provides the
required construct. The 24 registered arms and six registered contexts are
repeated observations summarized within mechanism.

## Primary Endpoints

| ID | Endpoint | Mechanism-level value | Population |
|---|---|---|---|
| P1 | End-to-end executable validity | `1` iff the first content response is schema valid, compile valid, and execution valid; otherwise `0` | all requested mechanisms |
| P2 | Activation | `activated_arm_count / 24` | execution-valid mechanisms |
| P3 | Realized dependency depth | median realized depth over activated arms | execution-valid mechanisms with at least one activated arm |
| P4 | Abstract structural diversity | within-model pairwise probability that two valid mechanisms have the same frozen abstract fingerprint; lower collision means greater diversity | execution-valid, structurally available mechanisms; at least two required |
| P5 | Outcome differentiation | `outcome_differentiated_context_count / 6` | execution-valid mechanisms |
| P6 | Causal-path differentiation | `causal_path_differentiated_context_count / 6` | execution-valid mechanisms |

For a model with `n` eligible mechanisms, P4 is
`sum_{i<j} I(fingerprint_i = fingerprint_j) / choose(n, 2)`. Thus its
denominator is exactly the `n(n-1)/2` unordered pairs of distinct eligible
mechanisms from that model. Pairs are not treated as independent observations;
inference resamples/permutates whole mechanisms. P4 is reported as **collision
probability**. The label "diversity" must not
silently reverse its direction. Unique abstract topologies and unique fraction
are descriptive companions only, because unique counts depend strongly on N.

## Required Validity Chain

For every model, report `schema_valid / N_requested`, `compile_valid /
N_requested`, and `execution_valid / N_requested`. Compile and execution
validity are not conditionally renormalized in the headline chain. P1 is the
execution-valid term of this chain.

## Secondary Endpoints

The following are prespecified exploratory endpoints:

- schema validity and compile validity using `N_requested`;
- behavioral inertness among execution-valid mechanisms;
- mean and maximum realized dependency depth per mechanism;
- median, mean, and maximum necessity-backed depth per mechanism;
- median depth gap per mechanism, positive-gap indicator, and possible
  redundant-causation indicator;
- semantic-fingerprint collision probability, unique semantic count, and
  semantic unique fraction;
- abstract unique count and abstract unique fraction;
- frozen exact-match, near-copy, and recombination indicators;
- the four per-mechanism context fractions: same outcome/same path, same
  outcome/different path, different outcome/same path, and different
  outcome/different path;
- full arm-level depth distributions for description only.

Exact match, near-copy, and recombination remain secondary if all are zero.
Likewise, empty outcome/path off-diagonal quadrants remain valid observations;
neither circumstance permits a threshold, registry, world-law, environment,
or metric change.

## Missingness And Zero

- Invalid mechanisms: P2-P6 and valid-only structural/dynamic metrics are NA,
  never zero.
- Execution-valid but never activated: P2 is exactly `0`; frozen v0.5 marks
  conditional depth unavailable, so P3 and all activation-conditional depth
  summaries are NA, not zero.
- Execution-valid with no differentiated context: P5 or P6 is exactly `0`.
- Execution-valid and behaviorally inert: inertness is `1`; non-inert is `0`.
- Frozen reference diagnostic `false` is a meaningful `0`, not missingness.
- Collision probability is NA when fewer than two eligible mechanisms exist.

No secondary endpoint may be relabeled primary after results are inspected.
No endpoint may be combined into a total score.
