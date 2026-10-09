# Formal Analysis Data Dictionary

## Row Grain

The analysis table has exactly one row per requested mechanism.
`formal_sample_id` and `request_id` are globally unique and identify that row.
The model-visible generation `sample_id`, `nonce`, and `canonical_seed` are
intentionally shared by all models within one matched `base_sample_index`
block; their coordinate tuple is unique across base blocks. Formal mechanism
identities, request identities, and visible generation-coordinate namespaces
must each be disjoint from pilot, fixture, adversarial, and calibration
namespaces. Arm- and context-level child records retain foreign keys to the
formal row but are not generated-sample rows.

`NA` means the construct is unavailable or outside its declared population.
It never means observed zero. JSON encodes NA as `null`; tabular exports use an
empty/NA value plus the applicable availability/reason field, never numeric 0.

## Identity, Provenance, And Status

| Field | Type | Unit/denominator | NA meaning | Zero meaning | Role/aggregation |
|---|---|---|---|---|---|
| `dataset_kind` | enum | row | forbidden | n/a | must equal `formal` |
| `formal_experiment_id` | string | experiment | forbidden | n/a | lineage key |
| `model_blind_label` | string | model | forbidden in analysis row | n/a | primary analysis grouping |
| `model_id` | string | model | unavailable only in blinded derivative | n/a | sealed/raw provenance, not used before unblinding |
| `base_sample_index` | integer | matched block | forbidden | index may start at 0 only if manifest schema says so | schedule/block key |
| `formal_sample_id` | string | requested mechanism/model/block row | forbidden | n/a | globally unique independent-unit key |
| `sample_id` | string | model-visible base generation coordinate | forbidden | n/a | shared within block; tuple with nonce/seed unique across blocks |
| `nonce` | string | model-visible base generation coordinate | forbidden | n/a | shared within block; not a globally unique row key |
| `canonical_seed` | integer/string | model-visible base generation coordinate | forbidden | valid coordinate | shared within block; identity only, not evidence provider enforced seed |
| `request_id` | string | request | forbidden | n/a | retry-stable key |
| `visible_prompt_sha256` | SHA-256 | request bytes | forbidden | n/a | lineage |
| `full_request_sha256` | SHA-256 | request bytes | forbidden | n/a | retry identity |
| `raw_response_sha256` | SHA-256 | first content response | NA only if no response artifact exists, with failure reason | n/a | immutable lineage |
| `failure_class` | enum | requested mechanism | NA iff valid | n/a | one of transport/provider/safety/empty/malformed/schema/compile/execution failure |
| `evaluation_status` | enum | requested mechanism | forbidden | n/a | success or classified failure |

Allowed terminal classes are `transport_failure`, `provider_failure`,
`safety_refusal`, `empty_response`, `malformed_json`, `schema_invalid`,
`compile_invalid`, `execution_invalid`, and `valid`. Max-token truncation is a
content-returned failure and is classified at the first failed content stage;
it is never continued or repaired.

## Validity And Runtime

| Field | Type | Unit/denominator | NA meaning | Zero meaning | Role/aggregation |
|---|---|---|---|---|---|
| `schema_valid` | boolean | all requested | forbidden | schema failed/not reached | secondary rate; denominator `N_requested` |
| `compile_valid` | boolean | all requested | forbidden | compile failed/not reached | secondary rate; denominator `N_requested` |
| `execution_valid` | boolean | all requested | forbidden | execution failed/not reached | P1; denominator `N_requested` |
| `registered_arm_count` | integer | valid mechanism | invalid/not evaluated | no registered arms, protocol error | expected 24; not sample N |
| `activated_arm_count` | integer | valid mechanism | invalid/not evaluated | no arm activated | P2 numerator |
| `activation_rate` | proportion | valid mechanism/24 arms | invalid/not evaluated | observed no activation | P2; compare mechanism-level values |
| `behaviorally_inert` | boolean | valid mechanism | invalid/not evaluated | observed non-inert | secondary mechanism rate |
| `no_committed_observed_state_difference` | boolean | valid mechanism | invalid/not evaluated | a paired state difference exists | descriptive component |
| `no_candidate_induced_world_law_activity` | boolean | valid mechanism | invalid/not evaluated | world-law path activity exists | descriptive world participation |

## Dynamic Reach

All depth values are conditional on activation under frozen v0.5. An
unactivated arm has null depths. A valid mechanism with zero activated arms has
an empty distribution and null mechanism summaries.

| Field | Type | Unit/denominator | NA meaning | Zero meaning | Role/aggregation |
|---|---|---|---|---|---|
| `arm_realized_dependency_depth` | integer | activated arm | arm did not activate/unavailable | activated with no downstream dependency edge | child trace only |
| `arm_necessity_backed_depth` | integer | activated arm | arm did not activate/unavailable | no necessity-backed downstream edge | child trace only |
| `arm_depth_gap` | integer | activated arm | arm did not activate/unavailable | realized and necessity depths equal | child trace only |
| `median_realized_depth` | number | valid mechanism's activated arms | no activated arms | median observed depth is 0 | P3 |
| `mean_realized_depth` | number | valid mechanism's activated arms | no activated arms | observed mean is 0 | secondary |
| `max_realized_depth` | integer | valid mechanism's activated arms | no activated arms | observed maximum is 0 | S2/secondary |
| `median_necessity_depth` | number | valid mechanism's activated arms | no activated arms | observed median is 0 | secondary |
| `median_depth_gap` | number | valid mechanism's activated arms | no activated arms | no median gap | secondary |
| `positive_depth_gap` | boolean | valid mechanism with activation | no activated arms | no activated arm has positive gap | secondary |

## Structure

| Field | Type | Unit/denominator | NA meaning | Zero meaning | Role/aggregation |
|---|---|---|---|---|---|
| `semantic_fingerprint` | SHA-256/string | valid mechanism | structure unavailable | n/a | secondary collision/unique summaries |
| `abstract_fingerprint` | SHA-256/string | valid mechanism | structure unavailable | n/a | P4 collision/unique summaries |
| `abstract_collision_probability` | proportion | matching pairs / `choose(n_eligible, 2)` unordered distinct-mechanism pairs within model | fewer than 2 eligible mechanisms | no pair collides | P4 model-level U-statistic; pairs are not independent units |
| `semantic_collision_probability` | proportion | matching pairs / `choose(n_eligible, 2)` unordered distinct-mechanism pairs within model | fewer than 2 eligible mechanisms | no pair collides | S3/secondary; pairs are not independent units |
| `exact_match` | boolean | valid structurally available mechanism | unavailable | frozen registry found no exact match | secondary diagnostic |
| `near_copy` | boolean | same | unavailable | not within frozen near-copy definition | secondary diagnostic |
| `recombination` | boolean | same | unavailable | frozen conservative detector did not detect recombination | secondary diagnostic |

A false reference diagnostic makes no claim of genuine novelty or absence of
recombination beyond the frozen detector.

## Environmental Behavior

| Field | Type | Unit/denominator | NA meaning | Zero meaning | Role/aggregation |
|---|---|---|---|---|---|
| `evaluated_context_count` | integer | valid mechanism | invalid/not evaluated | protocol error | expected 6 |
| `outcome_differentiated_context_count` | integer | valid mechanism | invalid/not evaluated | no context differs | P5 numerator |
| `fraction_outcome_diff` | proportion | valid mechanism/6 contexts | invalid/not evaluated | no outcome differentiation | P5 |
| `path_differentiated_context_count` | integer | valid mechanism | invalid/not evaluated | no context differs | P6 numerator |
| `fraction_path_diff` | proportion | valid mechanism/6 contexts | invalid/not evaluated | no path differentiation | P6 |
| `quadrant_*_context_count` | integer | valid mechanism | invalid/not evaluated | no context in quadrant | secondary; four counts sum to 6 |
| `fraction_quadrant_*` | proportion | valid mechanism/6 contexts | invalid/not evaluated | no context in quadrant | secondary mechanism summary |

Quadrants are `same_outcome_same_path`, `same_outcome_different_path`,
`different_outcome_same_path`, and `different_outcome_different_path`.

## Aggregation Invariants

Counts of arms or contexts may appear only as within-mechanism numerators and
denominators or as descriptive trace totals. Model-level N is the number of
requested mechanisms for validity and the number of eligible mechanisms for
conditional endpoints. No analysis may replace missing dynamic or structural
values with zero, and no paper statistic may lose its lineage back to request
and raw-response hashes.
