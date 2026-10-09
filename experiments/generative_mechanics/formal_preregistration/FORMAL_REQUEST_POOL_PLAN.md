# Formal Request Pool Plan

Status: design only; final manifest generation is blocked on all owner gates.

## Frozen prompt behavior

Inspection of Free-Invention v0.3 shows that the model-visible canonical JSON
contains `sample_id`, `sample_nonce`, and `derived_seed`. Consequently, creating
model-specific v0.3 coordinates would make prompt bytes differ by model and
would weaken the matched design.

The preregistered solution does not modify v0.3:

1. Derive one v0.3 coordinate triple for each `base_sample_index` using the
   frozen `derive_identity(master_seed, "world_substrate", base_sample_index)`.
2. Reuse that same visible `sample_id`, `sample_nonce`, and `derived_seed` for
   every model in the block.
3. Render the canonical prompt once and require the identical UTF-8 bytes and
   `visible_prompt_sha256` for all models in that block.
4. Assign model-specific identities only in the transport envelope:
   `formal_sample_id`, `request_id`, requested model ID, and schedule position.
   These fields must not enter the model-visible prompt.

```text
MODEL_VISIBLE_PROMPT_MATCHING: EXACT
```

This is exact within each base-sample block. Distinct base samples intentionally
have different visible generation coordinates, as required by v0.3.

## Final manifest schema

After the model matrix, `N`, inference policy, and collection-order seed are
owner-approved and frozen, generate `formal_request_manifest.jsonl`. Each row
must contain at least:

```text
formal_experiment_id
formal_sample_id                 # globally unique, model-specific, not visible
model_id                         # requested exact model ID
base_sample_index
sample_id                        # v0.3 visible ID shared within block
nonce                            # v0.3 sample_nonce shared within block
canonical_seed                   # v0.3 derived_seed shared within block
request_id                       # globally unique transport ID, not visible
visible_prompt_sha256
full_request_sha256              # exact transport request bytes
provider_request_config          # frozen model/effort/sampling/token controls
canonical_full_request           # reconstructable canonical request payload
selected_model_matrix
samples_per_model
master_seed
generation_protocol = gm-free-invention-v0.3
evaluation_protocol = gm-free-evaluation-v0.5
dataset_kind = formal
collection_status = NOT_SENT
block_order
model_order_within_block
inference_budget_policy
```

`full_request_sha256` is the SHA-256 of the stored canonical provider request
payload and must be recomputable from `canonical_full_request`. The future
transport adapter must send those exact canonical payload bytes and retain any
provider-specific HTTP metadata separately. It may vary by model because model
IDs and inference controls differ; `visible_prompt_sha256` must not vary within
a block.

## Required validations before freeze

- every `(base_sample_index, model_id)` pair occurs exactly once;
- `formal_sample_id` and `request_id` are globally unique;
- visible coordinate triple and prompt hash are identical within each block;
- every base sample contains every selected model exactly once;
- the selected model set, fixed N, master seed, and complete `0..N-1` block set
  are embedded consistently and cannot be inferred from surviving rows;
- every full-request hash is recomputable from its stored canonical payload and
  frozen provider configuration;
- all formal identities are disjoint from DEV pilot IDs/nonces/request IDs;
- all rows have `dataset_kind=formal` and `collection_status=NOT_SENT`;
- schedule is deterministic from the frozen seed and is block-interleaved;
- no raw response exists and no provider call occurs during generation;
- manifest bytes and SHA-256 are frozen before the first formal request.

A `DRY_MANIFEST_EXAMPLE.jsonl` may exercise this schema only with unmistakable
synthetic model IDs and `dataset_kind=synthetic_mock`; it cannot be ingested as
formal data. The final manifest must not be created while an owner gate is null.
