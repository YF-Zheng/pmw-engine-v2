# Protocol v0.3: Free Invention

`gm-free-invention-v0.3` is an independent generation track. It asks a model
to invent one executable mechanic without disclosing a desired score, scored
demonstrations, or an iterative revision policy. Protocol v0.2 remains frozen
and replayable; v0.3 does not replace or reinterpret its samples.

## Experimental conditions

The track retains three conditions so that representational affordances can be
compared without imposing an outcome target:

1. `isolated_direct_effect`: one validated direct outcome.
2. `matched_direct_outcome`: a direct-outcome representation with multi-effect,
   trigger, duration/periodic, cost, charge, and slot affordances.
3. `world_substrate`: writes the eight normalized public world channels which
   generic world laws may consume.

Every condition receives the same public channel semantics and the same generic
law summary. Environment instances, evaluation scenarios, oracle cases, and
private entity state are never placed in a prompt.

## Collection and provenance

Each request has a unique deterministic `sample_id`, derived seed,
`sample_nonce`, and canonical prompt SHA-256. The response envelope carries
strict `request_coordinates` containing `master_seed` and `sample_index`;
ingestion re-derives and individually checks the ID, seed, and nonce. A response envelope contains
exactly the fields declared in `generators/protocol_v0.3.json`; its `response`
contains only `mechanic`. The prompt digest is reconstructed during ingestion,
and duplicate identities are rejected across a JSONL batch.

Generated data cannot contain PMW laws. Mechanics pass the existing strict
`SkillSpec`, `DirectEffectSpec`, or `MatchedDirectOutcomeSpec` validator and the
existing trusted compiler before execution.

## Evaluation contract

The protocol document declares evaluation after generation along these
dimensions, but none of their names or definitions is included in the model
prompt:

- structural novelty
- interaction surface
- causal depth
- cross-environment differentiation
- downstream consequences
- combinatorial potential
- self-containment

The current implementation is a generation plus static-evaluation scaffold,
not a complete Free-Invention benchmark. It computes structural novelty against
the compatible checked-in seed catalog. The other six dimensions require
scenarios, paired traces, or exact build search and remain unimplemented;
they are marked `available=false` with a reason. Missing evidence is never
encoded as a zero score, and no complete benchmark claim should be made until
all six dynamic evaluators and their tests exist.

## CLI

```bash
PYTHONPATH=src:. python3 -m experiments.generative_mechanics \
  generate-free-invention-requests requests.jsonl --seed 2603 --per-baseline 40

PYTHONPATH=src:. python3 -m experiments.generative_mechanics \
  ingest-free-invention-responses responses.jsonl
```

The first command emits 120 balanced requests. Provider execution remains
external and raw responses should be archived before ingestion.
