# Collection Protocol

Status: preregistration candidate; formal collection remains `NOT_STARTED`.

## Preconditions

Collection is forbidden until the owner has selected the model matrix, equal
sample count per model, inference-budget policy, and collection-order seed; the
final request manifest and schedule have been hashed; readiness checks pass; and
the preregistration commit is tagged. No transport-only preflight is authorized
by this document.

## Block-interleaved schedule

For each `base_sample_index`, deterministically shuffle the complete selected
model list using the frozen `collection_order_seed` plus the block index. Execute
all rows of a block in the recorded order before advancing to the next block.
This prevents running one complete model batch before another and reduces
confounding by time, backend updates, and provider drift. The full schedule and
its hash must exist before the first request; runtime results cannot alter it.

All models in a block receive byte-identical model-visible v0.3 prompts. Visible
`sample_id`, `sample_nonce`, and `derived_seed` are block-shared; only invisible
outer `formal_sample_id`, `request_id`, model ID, transport configuration, and
schedule metadata are model-specific.

## Attempts and first-response rule

The maximum is three transport attempts total for one exact request. A transport
retry is permitted only after a failure before a usable provider content response,
such as timeout, HTTP 429, or temporary provider unavailability. Every attempt
must retain identical request bytes, `formal_sample_id`, and `request_id`; record
attempt number, timestamps, error/response, provider metadata, and hashes.

There is no content retry. The first returned content is the formal result for
malformed JSON, empty response, safety refusal, illegal fields, schema failure,
compile failure, execution failure, or `finish_reason=length`. Do not repair,
continue, regenerate, or replace it. Classification is exactly one of:

```text
transport_failure
provider_failure
safety_refusal
empty_response
malformed_json
schema_invalid
compile_invalid
execution_invalid
valid
```

An exhausted transport failure remains a requested mechanism in the end-to-end
denominator. Invalid mechanisms receive `NA` for unavailable structural/dynamic
metrics; they are never silently dropped or assigned novelty/depth zero.

## Immutable raw evidence

Write exact request bytes and every provider attempt append-only under
`raw_requests/` and `raw_provider_responses/`. Never overwrite a raw artifact.
Register each path, byte length, SHA-256, identity, and timestamp in
`RAW_DATA_MANIFEST.json`. Derived parsed, compiled, evaluated, and aggregated
layers must link to parent hashes and may not alter raw files.

Store requested model ID, returned model ID when exposed, provider request/session
IDs when exposed, collection time, finish reason, usage, and provider metadata.
If not exposed, write `unavailable` plus the reason; never infer or fabricate it.

## Alias drift and replacement

Use a version-fixed model ID where available. If only a dynamic alias exists,
record that limitation and inspect returned identity metadata without changing
the predeclared handling. Suspected alias drift triggers an incident report and
a pause for the affected model; it does not authorize rewriting prior identity.

If a model is withdrawn or permanently unavailable:

1. stop its collection and preserve all collected data;
2. record exact date/time, attempt evidence, and incident report;
3. require the owner to either remove that entire model from the confirmatory
   matrix or treat a replacement as a new model collected from zero to full N;
4. never pool old and replacement versions and never silently follow a newer alias.

## Stopping rule

The chosen fixed N per model cannot be increased based on observed outcomes,
validity, significance, or precision. Permitted pauses/stops are limited to
critical evaluator failure, prolonged provider unavailability, permanent model
withdrawal, raw-data corruption, or protocol violation, each with an incident
report. A stop does not redefine N or permit outcome-dependent supplementation.

## Formal isolation

Only rows with `dataset_kind=formal`, identities in the frozen formal manifest,
and valid raw-hash lineage may enter formal analysis. DEV pilot, fixture,
adversarial, calibration, synthetic, and repaired data must be rejected. The
analysis unit is the generated mechanism; registered arms are repeated measures.
