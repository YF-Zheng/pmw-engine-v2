# P3.1B Offline Replay + Candidate Compile Increment

Status: implemented and owner-tested on 2026-11-02 from checkpoint `6592694`
on branch `feature/alpha-v02-seventh-night`. This increment is offline only.
It makes no live provider/API call, performs no generation, registers no
Skill, runs no Sandbox, mutates no WorldState, and makes no P3 Gate claim.

## Scope

New files:

- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/skill_designer/replay.py`
- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/skill_designer/pipeline.py`
- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_skill_designer_offline_pipeline.py`

No existing source, package initializer, existing test, fixture, registry,
manifest, or ledger file was changed by this increment.

## Frozen Public API

```python
ReplayRequest(attempt: int, feedback: str, context_hash: str)
ReplayReply(text: str, origin_source: str = "authored", origin_model=None)
ReplayCall(attempt: int, feedback: str, context_hash: str,
           reply_text: str | None, reply_hash: str | None)
ReplayProvider(replies: Sequence[ReplayReply])
ReplayProvider.reply(request: ReplayRequest) -> ReplayReply
ReplayProvider.calls -> tuple[ReplayCall, ...]

AttemptRecord(attempt: int, stage: str, reason: str, context_hash: str,
              accepted: bool, reply_hash: str | None)
DecodedCandidate(document: dict, canonical_json: str, reply_hash: str)
PipelineResult(canonical_json: str, parsed: SkillIR | None,
               compiled: CompiledSkillIR | None)
PipelineResult.to_dict() -> dict

decode_candidate(text: str) -> DecodedCandidate
normalize_candidate(document, *, context, authority, candidate_id) -> dict
run_offline_pipeline(
    *,
    materials: Sequence[MaterialDefinition],
    statuses: Mapping[str, Any],
    profile: str,
    complexity: int,
    public_known_rules: Sequence[str],
    acquired_capabilities: Sequence[str],
    existing_skills: Sequence[ExistingSkillInput],
    candidate_id: str,
    replay: ReplayProvider,
    max_repairs: int = 0,
) -> PipelineResult
```

The public pipeline inputs are trusted material dataclasses and the same
allowlisted Context inputs as P3.1A. It does not accept serialized Context or
an arbitrary authority JSON object. `GenerationContext` is built internally.
The pipeline defensively revalidates public materials with `parse_material`,
derives the material set with `material_authority`, and requires the Context's
full authority tuple (IDs, effect kinds, selectors, and budget) to match that
rederived value before delegating to the accepted IR parser/compiler. Any
mismatch fails closed before replay is called; the Context's displayed
authority never replaces the trusted-trait-derived authority.

Replay replies are immutable caller-provided fixture text, limited to 65,536
UTF-8 bytes. There is no transport, generator, subprocess, network, registry,
Sandbox, or WorldState surface. Fixture replies normalize only to
`origin.source = "authored"` and `origin.model = None`; replay provenance is
recorded outside the Skill IR. Calls are not model usage, token counts, cost,
or generated-skill evidence.

## Candidate Boundary

`decode_candidate` accepts exactly one JSON object. A single complete
```json fenced block is accepted; prose before/after it, an incomplete fence,
multiple fences, a non-object root, duplicate object keys, NaN/Infinity,
invalid Unicode, excessive bytes, excessive depth, and excessive JSON shape
fail closed as typed candidate rejections.

`normalize_candidate` changes only:

- `identity.id` to the server-owned candidate ID;
- `identity.version` to `1`;
- `origin.source` to `authored`;
- `origin.model` to `None`;
- `origin.context_hash` to the internally built Context hash.

Unknown root fields and nested candidate fields are preserved so the strict IR
parser rejects them rather than having this layer silently discard them. All
Effects, costs, conditions, targeting, entries, lifecycle, display, and
limits stay candidate-controlled and are validated by `parse_skill_ir`.
Submitted `origin.material_ids` must exactly match the trusted selected IDs;
forged claims fail instead of being silently repaired.

Every attempt has a bounded `stage` and `reason`. Candidate validation errors
receive structured feedback and can consume `max_repairs` (strict integer
0..2, not bool), for at most three total calls. Provider exhaustion and
provider contract failures terminate immediately with preserved call causes.

## Result Semantics

A successful result is exactly:

```text
status = compiled_unregistered
accepted = false
sandbox = not_run
register = not_available
usable_pool = false
generated_skills = 0
live_requests = 0
actual_usage = null
actual_cost = null
model = null
```

It is compiler evidence only. It cannot be registered by this module and is
not admitted to a usable pool. Failure results preserve attempts, calls, and
failure stage/reason while leaving `ir`, `ir_hash`, `blueprint_hash`, `parsed`,
and `compiled` empty.

All result/readback JSON is fresh canonical JSON. `result_hash` covers the
result without itself and is stable for identical replay/context sequences.
Same replay inputs produce the same compiler IR hash, blueprint hash, call
records, and result hash.

## Verification

Focused owner suite:

```text
49 passed in 7.27s
```

Requested combined regression:

```text
166 passed, 32 subtests passed in 23.22s
```

The combined run covered the Catalog/Context owner and review suites, Skill IR
owner suite, the new offline pipeline suite, and the Gate4 registry checkpoint.

Library integration probe recursively fed all 40 current reference documents
through the new public pipeline twice. All 40 reached
`compiled_unregistered`; all paired result hashes, IR hashes, blueprint hashes,
and attempt records matched. The library contains field, stock, process,
relation, travel, combat, and derived examples; the four explicitly required
families are covered in the focused suite.

## Deliberate Limitations

- No live model/provider, HTTP, batch, generation call, or usage ledger entry.
- No Skill registration, usable-pool admission, Sandbox run, or WorldState
  mutation.
- No behavioral, runtime, balance, or generation-diversity verdict.
- Replay is deterministic fixture transport, not model-output evidence.
- IR bounds and compile authority remain owned by the accepted
  `parse_skill_ir` and `compile_skill_ir`; this module delegates to them.
- Candidate identity normalization is server-owned and intentionally narrow;
  any future live-generated provenance path requires separate review.

## Evidence

Raw logs and the 40-case hash manifest are under
`docs/agent_bootstrap/evidence/p3_offline_owner*`.

Failed iterations are preserved as unique logs rather than overwritten.

## P3.1B Offline Replay / Compile Accepted (2026-11-02)

Finite immutable ReplayProvider and strict bounded JSON decode/normalize/type/
capability/budget/compile now delegate to the accepted IR compiler. Material
authority is rederived from trusted traits, compared in full with Context and
never replaced by display JSON. Repairs are limited to two; exhaustion stops.
Only server-owned identity/provenance is normalized; unknown candidate fields
remain for rejection. Output is compiled_unregistered, accepted=false,
Sandbox not_run and Register not_available. No live generation request.

Independent QA final ACCEPT: **234 passed /32 subtests** (49 owner,59 QA,
16 Unicode regressions,96 Catalog/Context,14 IR). One real defect fixed:
escaped lone surrogates bypassed the raw-wire check; decoded values AND keys
now require valid UTF-8. All five original failing expectations and red logs
are preserved; valid pairs/emoji/Chinese still pass. Main same-process old
cross-module regression: **237 passed /22 subtests /27.46s**. Previous P2
319 frozen Python files,5 accepted P3.1A files and130 protected files remain
unchanged. This is NOT a fresh full-project run or P3 Gate acceptance.

Evidence: P3_OFFLINE_PIPELINE_REVIEW.md, P3_OFFLINE_PIPELINE_INCREMENT.md,
P3_OFFLINE_PIPELINE_UNICODE_FIX.md, evidence/p3_offline_main_acceptance.json.
Accounting p3_1b cutoff 2026-11-02T04:06:44.566Z: subset CNY15.41330278
(already included once), cumulative CNY509.98733256; safety CNY642.60974341
/3000, Unknown0. Actual caches preserved; replay fixture calls have no model
usage entries. Worker calls are charged by their actual rollout IDs. Bootstrap
separate; closing overhead awaits the next ordinal snapshot.

Next: a separately bounded real Engine Sandbox with trusted fixture selection,
PLAYER/NPC/control execution, actual causal receipts and behavior signatures.
No usable-pool admission, provider batch or Alpha UI/playtest claim yet.

