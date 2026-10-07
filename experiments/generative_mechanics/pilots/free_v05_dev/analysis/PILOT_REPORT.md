# Free-Invention v0.5 DEV Pilot Report

Status: `MINOR_MEASUREMENT_ISSUE`

This is a `DEV / PILOT DATASET`, not a formal or paper dataset. The results
diagnose frozen evaluator behavior only. They must not be used to rank models or
as a paper conclusion. The formal experiment remains `NOT STARTED`, and no
metric value or frozen v0.5 evaluator behavior was changed during audit.

## Collection And Provenance

- Provider path: OpenAI Codex CLI.
- Requested exact model identifiers: `gpt-5.6-luna` and `gpt-5.6-terra`, each
  with reasoning effort `high` and 15 first-attempt world-substrate requests.
- The CLI JSONL did not expose returned model identifiers or provider request
  IDs; this limitation is explicitly recorded per response. No identifier was
  invented.
- All 30 requests have unique `sample_id`, `sample_nonce`, `canonical_seed`,
  `prompt_sha256`, and `request_id` values. All 30 raw provider responses are
  preserved and hash-linked to ingestion rows.
- The provider path does not enforce seeds. Canonical seeds are identity
  coordinates only and every row records `provider_seed_enforced=false`.
- All responses are first attempts. No content failure was retried or replaced.

## Validity And Behavior

| Model identifier | Requested | Provider success | Schema valid | Compile valid | Execution valid | Activated valid mechanisms | Behaviorally inert |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gpt-5.6-luna` | 15 | 15 | 14 | 14 | 14 | 14 | 0 |
| `gpt-5.6-terra` | 15 | 15 | 13 | 13 | 13 | 13 | 0 |

The three schema failures are genuine retained first responses: one Luna output
used object wrappers for `effects` and `trigger_conditions` where arrays were
required, and two Terra outputs added the unknown strict field `write_surface`.
There were no compile or execution failures.
Every valid mechanism activated in 4-12 of 24 registered arms, giving activation
rates from 1/6 to 1/2. There are no structurally non-matching and behaviorally
inert cases because none of the 27 valid mechanisms is inert.

## Structural Measurement

Exact match, near-copy, and recombination are each 0/27. Exact non-match is
therefore saturated and must not be described as genuine novelty. Manual review
supports the near-copy negatives: all nearest-reference distances are 3-5
explicit edits, outside the frozen `<=2` boundary. Recombination negatives also
match the strict contract: partial coverage exists, but no candidate is an exact
two-reference union with independent source contributions. These three metrics
are interpretable but have no empirical discrimination in this pilot.

Across all valid profiles there are 24 distinct semantic structures and 22
distinct abstract topologies, a semantic-to-abstract ratio of 1.091. Luna has
14 semantic and 12 abstract fingerprints; Terra has 12 and 12. This is a
measurement diagnostic, not a model comparison. The topology collisions checked
by hand are expected: field identity is removed while trigger operators, write
polarity, field-sharing roles, cardinality, target scope, and temporal shape are
retained. Thus the evaluator detects some abstraction-level repetition despite
near-maximal semantic diversity.

## Dynamic Reach

Realized dependency depth does not collapse to 0-1. Across 176 activated arms it
spans 1-7 with median 3; no arm has depth 0 and only 8 have depth 1. Necessity
depth spans 1-5 with median 3. A positive dependency/necessity gap appears in
51/176 arms (29.0%): 36/80 Luna arms and 15/96 Terra arms. Manual trace review
found the reported paths consistent with dependency edges and necessity
ablations, including the large gaps attributed to possible redundant causation.

## Outcome And Path Split

Across 162 evaluated contexts, the four quadrants are:

| Outcome | Path | Contexts |
|---|---|---:|
| same | same | 118 |
| same | different | 0 |
| different | same | 0 |
| different | different | 44 |

Paired observations and normalized path signatures support every audited flag,
but this sample does not empirically separate outcome from path differentiation:
both off-diagonal quadrants are empty. This is a coverage limitation, not an
observed calculation error.

## Manual Audit

The scaffold contains 30 rows: 10 high/complex, 10 low/simple, and 10
anomalous/counterintuitive. Category overlap was preregistered and disclosed, so
these represent 23 unique valid samples. Every row was reviewed against the
parsed mechanic, complete profile, structural projections, runtime traces,
necessity evidence, and paired environment signatures.

All 30 rows were judged `yes` for overall semantic reasonableness and for
near-copy, recombination, abstract topology, dependency depth, outcome/path
split, and inertness. No metric value was modified. No systematic semantic
misclassification or new evaluator implementation failure was found.

## Bias Audit

| Metric | Saturated? | Substantially missing? | Human semantic agreement? | Anomaly found? | Blocks formal experiment? |
|---|---|---|---|---|---|
| Activation | no | no | yes | no | no |
| Inertness | yes: all non-inert | no | yes | no | no |
| Exact match | yes: all false | no | yes | no | no |
| Near-copy | yes: all false | no | yes | no | no |
| Recombination | yes: all false | no | yes | no | no |
| Semantic structure | no: 24/27 distinct | no | yes | no | no |
| Abstract topology | no: 22/27 distinct | no | yes | no | no |
| Dependency depth | no | no | yes | no | no |
| Necessity depth | no | no | yes | no | no |
| Outcome differentiation | no | no | yes | off-diagonal absent | no |
| Path differentiation | no | no | yes | off-diagonal absent | no |

Machine-readable evidence and direct answers to all 16 required questions are
in `bias_audit.json`.

## Readiness

`MINOR_MEASUREMENT_ISSUE`

No evidence justifies changing the frozen v0.5 evaluator, and no case requires a
v0.6 fix. However, the all-negative exact/near-copy/recombination results and
the empty off-diagonal outcome/path quadrants mean this DEV pilot did not test
the discriminative behavior of those dimensions on real-model outputs. A formal
run should proceed only with those limitations explicitly preregistered and with
no claim that the saturated metrics distinguish models in this pilot.
