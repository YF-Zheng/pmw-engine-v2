# Owner Decisions

Status: `OWNER_DECISION_REQUIRED`

No formal request may be sent until all three gates are selected, recorded in
the registry, used to generate the final manifest and schedule, and frozen by
commit and tag.

## Gate A - Model Matrix

Choose exactly one preregistered candidate:

- `4-model budget`
- `5-model balanced`
- `6-model extended`

The chosen set must retain at least two frontier/high-capability systems, at
least one medium-capability system, and at least one smaller or open-weight
system, while avoiding near-duplicate family coverage. Exact IDs and all
`UNVERIFIED` availability, identity, pricing, and rate-limit fields must be
resolved before freeze. Dynamic aliases require explicit limitation text.

Decision: `OWNER_DECISION_REQUIRED`

## Gate B - Samples Per Model

Choose one balanced N for every selected model:

- `100 per model`
- `150 per model` (balanced candidate, not an automatic choice)
- `200 per model`

N is selected from precision, low-frequency-event coverage, budget, runtime,
and storage estimates, not Luna/Terra pilot effect sizes. N cannot be increased
after looking at significance or failure rates.

Decision: `OWNER_DECISION_REQUIRED`

## Gate C - Inference-Budget Policy

Choose one:

- `system-level configuration`: each deployed system uses its standard or
  recommended high-quality configuration. This has strong ecological validity
  but configuration and model identity are jointly compared.
- `matched inference budget`: token/reasoning budgets are matched as closely as
  provider controls permit. This improves budget comparability but may be
  artificial, may not equate latent compute, and may disadvantage systems whose
  controls differ.

Decision: `OWNER_DECISION_REQUIRED`

## After All Three Decisions

1. Populate exact model/configuration fields and final N in the registry.
2. Fix collection-order and bootstrap/permutation seeds.
3. Generate the final unsent request manifest and block-interleaved schedule.
4. Verify visible-prompt matching and request hashes.
5. Run the full test, isolation, lineage, and JSON/JSONL validation suite.
6. Hash preregistration artifacts, commit, and tag
   `free-invention-formal-prereg-v1` (or owner-approved equivalent).
7. Only after the tag may an owner separately authorize a transition from
   `formal_collection_started=false`.

Silence, timeout, or a default does not resolve a gate.
