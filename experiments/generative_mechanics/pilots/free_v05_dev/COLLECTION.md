# Collection Interface

Importing or validating this package makes no provider call. The explicit
collector iterates `requests/canonical_requests.jsonl` exactly once and invokes
the installed Codex CLI with the row's `prompt`, `exact_model_identifier`, and
`reasoning_effort`. Its non-interactive invocation shape is:

```bash
codex exec --ephemeral --ignore-rules --sandbox read-only \
  --model "$EXACT_MODEL_IDENTIFIER" \
  --config 'model_reasoning_effort="high"' \
  --json --output-last-message "$RESPONSE_TEXT_FILE" - < "$PROMPT_FILE"
```

The provider command intentionally does not use `--output-schema`. The frozen
v0.3 prompt is the only response constraint presented to the model, so invalid
JSON and schema-invalid first responses remain observable pilot evidence.

The collector must capture the complete JSONL stdout/stderr/exit metadata as
`raw_provider_response`, and the byte-exact last message as `response_text`.
It then writes one object per completed request to the model-specific
`raw_provider_responses/{luna,terra}/first_attempts.jsonl` with fields enforced by
`pilot._check_raw_record`. In particular, `attempt` is `1`, `repair` is false,
and null `provider_request_id` or `returned_model_identifier` values have a
non-empty corresponding unavailable-reason field.

There is intentionally no transparent retry loop. Transport retries, if needed,
must remain visible in raw transport metadata and must not create a second
completed response. Content failures are never retried in the main pilot.

Run the two frozen model batches explicitly:

```bash
PYTHONPATH=src python3 -m experiments.generative_mechanics.pilots.free_v05_dev.provider_codex collect --model gpt-5.6-luna
PYTHONPATH=src python3 -m experiments.generative_mechanics.pilots.free_v05_dev.provider_codex collect --model gpt-5.6-terra
```

Then run local-only stages:

```bash
PYTHONPATH=src python3 -m experiments.generative_mechanics.pilots.free_v05_dev.provider_codex ingest --model gpt-5.6-luna
PYTHONPATH=src python3 -m experiments.generative_mechanics.pilots.free_v05_dev.provider_codex ingest --model gpt-5.6-terra
PYTHONPATH=src python3 -m experiments.generative_mechanics.pilots.free_v05_dev.provider_codex evaluate --model gpt-5.6-luna
PYTHONPATH=src python3 -m experiments.generative_mechanics.pilots.free_v05_dev.provider_codex evaluate --model gpt-5.6-terra
PYTHONPATH=src python3 -m experiments.generative_mechanics.pilots.free_v05_dev.provider_codex analyze
PYTHONPATH=src python3 -m experiments.generative_mechanics.pilots.free_v05_dev.provider_codex finalize
```

`finalize` is fail-closed. It writes the final recursive hash manifest only
after all 30 provenance records, 30 ingested rows, every compile-valid profile,
completed manual audit, final report/bias table, and analysis artifacts pass
their cross-artifact checks.
