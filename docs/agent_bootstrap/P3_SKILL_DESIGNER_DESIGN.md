# P3 Skill Designer (DS V4 Flash) Design

Status: DRAFT by Main (2026-10-30). Becomes frozen only after the P2 Gate is
accepted. No provider call is made before that.

## Principle

The generator only proposes `pmw-skill-ir-v1` documents. Authority stays in
the accepted pipeline: `parse_skill_ir` (type, capability, budget, limits) ->
`compile_skill_ir` -> sandbox execution in a trusted reference fixture. A
candidate the pipeline rejects is never registered. The generator never sees
hidden world state and never touches WorldState or engine code.

Pipeline (contract section 23):
Context -> Generate -> Parse(JSON) -> Normalize -> Type/Capability/Budget
(parse_skill_ir) -> Compile -> Sandbox Test -> Register(candidate pool).

## Modules (NEW package `gameplay_v04/skill_designer/`)

1. `catalog.py` - deterministic, versioned mechanism catalog built from the
   accepted code, not hand prose: protocol, six state classes, seven
   Operators with their effect kinds, per-effect-kind parameter schema and
   numeric ranges, selectors, condition operators and leaves (incl. derived),
   triggers (supported and reserved/`language_gap`), lifecycle rules,
   budget arithmetic summary, limits. `catalog_hash` = sha256 of canonical
   JSON. Fails a test if a kind accepted by the parser is missing from the
   catalog (mechanical parity check), so the model sees the full language.
2. `context.py` - builds the generation context: materials and traits (from
   trusted material fixtures), derived authority (effect kinds, selectors,
   budget points), complexity tier (1..3), known world rules (public
   profile summary only), structural summary of already accepted pool
   skills (operator/effect-kind skeletons, no IDs needed), catalog. No
   hidden state. Context hash recorded.
3. `provider.py` - OpenAI-compatible client for the local Magpie gateway
   (`http://127.0.0.1:3425/v1`), model `tencent/deepseek-v4.1-flash`
   (verified in `/v1/models` on 2026-10-30). JSON-only output requested;
   bounded timeout; no credentials in code or logs. Each call appends one
   record to `evidence/p3_generator_usage.jsonl`: call id, model returned by
   the server, request/response ids, usage counters exactly as returned,
   latency, outcome. A `ReplayProvider` serves recorded responses so all
   tests run offline and deterministically.
4. `pipeline.py` - one candidate: parse JSON (strip a single code fence
   only), normalize (`origin.source="generated"`, `origin.model`,
   `origin.context_hash`, assign deterministic id/version), then
   `parse_skill_ir` with the trusted authority, `compile_skill_ir`, sandbox
   test. On failure, up to MAX_REPAIRS=2 repair calls with the structured
   GameplayContractError message; then reject. Every stage outcome is
   recorded with a closed rejection-reason code.
5. `sandbox.py` - executes a compiled candidate in the P2.2 reference
   fixture selected by the TRUSTED generation context, not candidate name,
   display tags, or an inferred union of material permissions, for PLAYER
   and NPC, against a no-skill control, and records a behavioural
   signature: sorted set of changed state paths (normalized: entity roles,
   not IDs) plus signed delta buckets. "No meaningful effect" (empty
   Skill-caused delta) is a rejection reason.
6. `metrics.py` - generation success, JSON parse success, first-pass compile
   rate, post-repair pass rate, Operator / state-class coverage, structural
   dedupe (hash of operator+effect-kind+selector+trigger skeleton),
   behavioural dedupe (signature equality), complexity distribution
   (effects, entries, condition nodes, budget use), rejection reasons, token
   usage and reference cost per accepted candidate.
7. `run_batch.py` - CLI: `--batch-id`, `--count`, `--seed`, `--profile-mix`,
   `--max-usd`. Writes `evidence/p3_batches/<batch>/` (raw responses,
   candidates, verdicts, metrics). Refuses to start if the projected cost
   would exceed `--max-usd` or the P3 stage limit in the cost ledger.

## Accounting

Generator HTTP calls do not appear in Codex rollouts. They are charged from
`p3_generator_usage.jsonl` with the same verified Flash reference prices and
the 97% cache assumption (actual counters preserved), as a separate
`Generator` family in the ledger, stage P3. A record without usage counters
is Unknown and stops further batches.

## Batches

Pilot 10 -> review prompt/catalog defects -> batches of ~60 up to 200-500
total. If the failure checks in contract P3 Gate appear (mostly impulse,
no Process/Relation, template repetition, compile-but-no-effect, frequent
non-triggering, unbounded gain/perf), fix catalog/context/authority first,
not sample size.

## Increments

- P3.1 catalog + context + replay provider + pipeline + sandbox + metrics,
  fully offline tests with recorded fixtures (no network in pytest).
- P3.2 live provider adapter + pilot batch of 10 + usage ledger integration.
- P3.3 batches to >= 200 candidates, analysis report, P3 Gate review.

## Resume Review / Next Bounded Increment (2026-11-02)

P2.2 is still pending QA sign-off. The following scope is planning only;
do not start implementation or provider generation before the P2 Gate.

First P3 increment is ONLY offline `catalog.py` + `context.py`. Provider,
pipeline, registration, live generation and accounting ingestion remain
separate subsequent increments, so they can be reviewed independently.

Catalog construction may introspect the closed accepted parsers/typed
records but must not invent runnable reserved mechanisms. Preserve a
supported/reserved distinction for all triggers, selectors and lifecycles.
Catalog metadata/hash stays outside the closed Skill IR schema unless a
separate versioned IR change is accepted. No arbitrary field paths or
world-rule dumping in the public context.

Context takes an explicit trusted fixture/profile and MaterialAuthority;
candidate display tags are never authority. For the first offline increment,
known-world rules are an explicit caller allowlist of public facts, not
serializations of a WorldState or privileged registry. Store defensive
copies/canonical JSON so mutation cannot desynchronize context/catalog hashes.
Existing-skill summaries must omit candidate identity/name and describe
structural content; equivalent structures should not receive different
summaries solely because IDs or prose differ.

Before live HTTP work, verify Magpie model catalog and response usage
semantics again; a response model label is not sufficient evidence of the
provider route. Every external call must have an idempotent usage record,
actual counters/cache fields, and a supported official reference price.
Use per-response max-output/timeout caps to bound projected spend; never
guess missing usage or log credential headers. Codex worker calls remain in
the existing rollout ledger and must not be charged again as HTTP generator
calls. A cache assumption is solely a price transform, not a counter change.
