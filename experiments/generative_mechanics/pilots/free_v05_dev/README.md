# Free-Invention v0.5 DEV Pilot

This directory is a strictly isolated `dev_pilot` dataset namespace. It is not
a formal/paper dataset, and formal collection or analysis code must not ingest
it. The frozen inputs are `gm-free-invention-v0.3` and
`gm-free-evaluation-v0.5` from freeze commit
`89e0c6ad24f62c68f4e326b361e0f3c5f807c756`.

The preregistered main batch contains 15 `world_substrate` requests for each of
`gpt-5.6-luna` and `gpt-5.6-terra`, both with reasoning effort `high`, through
`OpenAI Codex CLI`. The CLI path does not expose a provider-enforced seed, so
canonical seeds are identity coordinates only. No model has been called by the
infrastructure commit. Temperature, top-p, and max-output-token controls are
also recorded as `null` with an explicit CLI-unavailable reason rather than
inventing effective sampling values.

Collection records must preserve exact assistant text and the raw provider
object. Content failures are first-attempt evidence and are not retried.
Transport retries may be logged by the collector, but only one completed first
attempt is admitted per request. Repair responses belong to a separate
experiment and cannot replace a first attempt.

Layout:

- `COLLECTION.md`: exact external Codex CLI and post-collection interface.
- `requests/`: deterministic v0.3 canonical requests.
- `raw_provider_responses/`: immutable provider records after collection.
- `ingested/`: parse/schema/compile/execution status rows.
- `profiles/`: complete frozen v0.5 capability profiles.
- `analysis/`: per-model, non-ranking summaries and distributions.
- `manual_audit/`: human semantic audit scaffold; metric values are immutable.
- `manifest/`: preregistration and hash-bound artifact manifest.

Run `python3 -m experiments.generative_mechanics.pilots.free_v05_dev.pilot`
to validate the checked-in preregistration and its frozen-contract binding.
