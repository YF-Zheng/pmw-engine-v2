# P2 Versioned Skill IR, Validator And Compiler (Design)

Architecture by Main. Drafted while C5.2 QA and the P1 completion conformance
were running. P2 implementation does NOT start until P1 is accepted
(contract gate order P1 -> P2). No generation provider calls before P2 is
accepted.

## Principle: One Compiler, Lowering To The Accepted Runtime

The contract (DEVELOPMENT_CONTRACT.md chapters 4-5, P2 section) asks for a
versioned Skill IR with Schema, Conditions, Triggers, Selectors, Lifecycle,
Compiler and Validator, plus at least 30 reference Skills that use one
Compiler and Runtime. The accepted v0.4 runtime already executes
`SkillBlueprint` through staged Action transactions, the single Gameplay
clock, Core Laws and the automatic `damage_resolved` passive dispatch. P2
therefore adds a strictly versioned IR layer (`protocol: "pmw-skill-ir-v1"`)
whose compiler is a pure function lowering one IR document into one or more
existing parsed `SkillBlueprint` values plus a trusted metadata record. It
does NOT add a second runtime, evaluator, clock or Law family. Every IR
capability must map to an accepted runtime path, or the validator rejects it
with an explicit `language_gap` reason (contract section 10: record gaps,
never add skill-specific special cases).

## IR Document (strict, closed keys)

```
{
  "protocol": "pmw-skill-ir-v1",
  "identity": {"id", "version", "name", "description"},
  "origin": {"source": "reference"|"generated"|"authored",
             "model": str|null, "context_hash": hex64|null,
             "material_ids": [..]},
  "capability": {"traits": [..]}            # informational; authority comes
                                             # only from trusted materials
  "targeting": {"selectors": [...], "relation_types": [...]},
  "costs": {"mana": n, "duration": ticks},
  "entries": [ { "id", "trigger": {"kind": "on_use"} |
                 {"kind": "on_event", "event": "damage_resolved"},
                 "condition": <condition|null>,
                 "effects": [<v0.4 effect>...],
                 "max_firings_per_root": 1..8 } ],
  "lifecycle": {"status_duration": null|{"unit","amount"}},
  "limits": {"budget": n},
  "display": {"summary": str<=240, "tags": [..<=8]}
}
```

- `entries` 1..4. At most one `on_use` entry. Each `on_event` entry lowers to
  a `passive_blueprint` with the neutral 1/0 cost; the `on_use` entry lowers
  to a `skill_blueprint` carrying `costs`. Lowered IDs are
  `<identity.id>__<entry.id>`, `version` = identity.version; uniqueness is
  enforced.
- `budget` is shared: the sum of all lowered entries' budget usage (existing
  `_effect_cost` arithmetic, passive +0.5) must fit `limits.budget` and the
  trusted material authority. This closes the multi-entry budget bypass.
- Triggers not executed by the accepted runtime (`on_tick`, `on_expire`,
  other `on_event` events, transition events) are rejected with
  `language_gap:<trigger>`; they are listed in the IR catalog as reserved so
  P3 context can expose them honestly as unavailable.
- Conditions reuse `parse_condition` with the C4.1 shared budget across the
  whole document (one counter per IR document, not per entry).
- Effects reuse `parse_effect` unchanged; selectors reuse the closed selector
  set. No new effect kinds are introduced by P2.1.
- Canonical IR hash: sha256 of sorted-key compact JSON; lowered blueprint
  hashes are unchanged v0.4 hashes, and the metadata record links IR hash ->
  lowered (id, version, hash) tuples.
- Display: compiler generates a deterministic preview (operators, selectors,
  costs, trigger list) from parsed specs; candidate `summary` is
  display-only and never parsed for semantics.

## Operator And State Catalog (validator-side classification)

Seven contract Operators map onto existing closed Effect kinds:

| Operator | Effect kinds |
|---|---|
| impulse | damage, heal, shield, add_resource, modify_field, apply_status, grant_trait |
| drive/source | drive_source |
| attractor_modifier | modify_attractor |
| dynamics_modifier | modify_rate, dynamics_modifier |
| process_start | process_start |
| process_modify | process_modify |
| relation_modifier | relation_modifier (overlay), move_actor (located_in lifecycle) |

Six state classes: Field (modify_field/attractor/rate/dynamics_modifier),
Stock (add_resource, Process/Drive Stock consumption), Process
(process_start/modify), Relation (relation_modifier, move_actor), Discrete
(apply_status/grant_trait, ecology regime transitions read by conditions),
Derived (read-only `derived` condition leaf; never written by Skills).
The compiler emits `operators` and `state_classes` coverage per Skill so the
30-skill library can prove coverage mechanically.

## Increments

- **P2.1 IR schema/validator/compiler** — NEW `gameplay_v04/skill_ir.py`
  (pure parse/validate/lower/preview/hash), NEW owner test, independent QA.
  No production edits outside the new module unless Main approves a blocker.
- **P2.2 Reference library** — NEW `gameplay_v04/reference_skills/` (30+ IR
  JSON documents + trusted world/material fixtures) and NEW conformance test
  covering the contract Gate matrix for each skill: positive execution,
  illegal permission (material authority / selector), budget overflow,
  lifecycle (duration/expiry/firing limits), cross-region (adjacent_area /
  move_actor / off-area evolution), checkpoint save/load, deterministic
  replay (two independent runs -> identical canonical world digests).
- **P2.3** remaining trigger gaps only if a real runtime path exists; else
  recorded as language gaps for P3.

P2 Gate (contract): 30 reference skills through the same compiler/runtime
with all seven test categories, no hand special-casing.

## P2.2 Reference Library Frozen Plan (Main, 2026-10-30)

Location: NEW package `gameplay_v04/reference_skills/` containing
`library.json` (a list of >= 30 IR documents, `origin.source = "reference"`)
and `fixtures.py` (trusted world/material/controller builders keyed by a
small closed set of fixture profiles: `field`, `stock`, `process`,
`relation`, `combat`, `travel`, `derived`). Fixture code may only build
time-zero worlds and trusted profiles; it must never branch on a Skill ID
(static scan enforced). Each IR document declares its fixture profile in
`display.tags` as `fixture:<profile>` (display-only, used by tests to pick
the world, never by the compiler/runtime).

Required coverage (each row at least the listed count; one Skill may count
toward several rows):

| Category (contract) | Min |
|---|---|
| instant Field change (modify_field) | 3 |
| long-term attractor investment (modify_attractor) | 2 |
| recovery-rate change (modify_rate / dynamics_modifier) | 3 |
| resource consume/produce (add_resource, Process Stock, drive_source) | 3 |
| Process start and modify | 3 |
| Relation change (relation_modifier, move_actor) | 3 |
| event-driven passive (on_event damage_resolved) | 3 |
| condition combination (all/any/not with >= 2 typed leaves incl. derived) | 4 |
| multi-effect synergy (>= 2 effects, distinct Operators) | 4 |
| different legal scopes (self, target_actor, current_area, adjacent_area, linked_object) | each selector >= 1 |

Mechanical coverage proven by `compile_skill_ir` outputs over the library:
all seven Operators and all six state classes appear.

Conformance test (`tests/test_p2_reference_library.py`, NEW) per Skill:
1. positive execution through the formal chain for PLAYER and NPC (exact
   Mana/Tick and at least one asserted world delta that is caused by the
   Skill: compare against a no-skill control run where the delta is not
   obvious);
2. illegal permission: same document with a material authority missing one
   used effect kind or selector -> GameplayContractError at parse;
3. budget overflow: `limits.budget` lowered below usage -> rejected;
4. lifecycle: duration/expiry or firing limit observed through real Ticks
   for every Skill with a duration/expiry or passive firing cap, otherwise
   an explicit N/A reason recorded per Skill;
5. cross-region: at least 6 Skills exercise adjacent_area/move_actor/off-Area
   evolution (row recorded in a matrix);
6. checkpoint: save/load mid-effect and continue identically to an
   uninterrupted run;
7. deterministic replay: two independent builds and runs produce identical
   canonical world digests.
A generated coverage matrix JSON goes to evidence. No skill-specific branch
in production or fixtures; any semantic the language cannot express is
recorded as a language gap, not special-cased.

## P2.1 fix decisions

- `lifecycle.status_duration` remains part of the closed lifecycle object, and
  `null` remains valid. Because no accepted runtime consumes
  `SkillBlueprint.duration`, every non-null value is rejected with
  `language_gap:lifecycle.status_duration`. Per-Effect durations remain the
  supported lifecycle path.
- Malformed untrusted input stays behind the `GameplayContractError` boundary.
  Scalar and mapping types are checked before set/dict membership tests.
  Delegated lowering calls that could leak `TypeError`, `KeyError`, or
  `AttributeError` convert only those errors to `GameplayContractError`.
- The canonical JSON recorded at parse time is authoritative for compilation.
  Compilation verifies its SHA-256 against `canonical_hash`, reloads fresh data,
  and does not lower reachable mutable fixture data. This keeps the IR hash,
  lowered blueprint hashes, and semantics linked without changing existing
  canonical hashes for accepted inputs.
- P3 ingress length bounds are enforced now: `identity.name` <= 80 characters,
  `identity.description` <= 600, and `origin.model` is null or <= 128.

## Main Root-Cause Review After Second Fix Round (2026-10-30)

Two fix rounds have now been reviewed: the original P2.1, then the
three-defect fix. Independent QA (Ampere 01a18b82-324d-7953-8978-3d2f226d9357)
found that compile_skill_ir verifies only that canonical_json matches
canonical_hash. A caller who replaces both fields together (for example with
object.__setattr__ on the frozen dataclass) can compile documents that
parse_skill_ir rejects, and can supply a forged condition_nodes value.

Root cause: the fixes treated `SkillIR` as a trusted capability, but it is a
plain value object whose fields can be replaced together. Integrity checks
inside one value object cannot prove that it was validated. Each fix patched
a symptom, such as mutable nested dicts or a hash mismatch, instead of
removing the trust assumption.

Decision: make compile a pure function of validated input.
- `SkillIR` additionally records the trusted `condition_limits` used at parse
  time.
- `compile_skill_ir(ir)` re-runs the FULL `parse_skill_ir` over
  `json.loads(ir.canonical_json)`, using `ir.statuses`, `ir.authority` and
  `ir.condition_limits`. It lowers ONLY from that freshly parsed result. It
  then requires that the fresh `canonical_hash` equals `ir.canonical_hash`.
  Every parse-time rule (entries, selectors, budgets, condition nodes, text
  bounds, language gaps) is therefore re-applied, and derived fields such as
  `condition_nodes` are never trusted from the object.
- The separate `_canonical_ir` re-validator is removed so there is one
  validator and no drift.

Threat model (stated explicitly): untrusted data enters only as JSON. Code
running in the same process that forges `authority`, `statuses` or
`condition_limits` themselves is trusted code. The material authority is the
trusted root, as in v0.4 `SkillBlueprint`, and is out of scope. If this
third fix round fails review, the three-ineffective-iteration rule applies
and this direction stops.
## Main Decision After Round-3 QA (2026-10-30)

Round-3 QA (Ampere) verified that the forged canonical payload and forged
derived-field defects are fixed (an effective improvement), and reported one
NEW, distinct PRODUCT_DEFECT: `parse_skill_ir` calls `deepcopy(raw)` before any
shape validation, so deeply nested JSON escapes as `RecursionError`.

This is not the same defect failing twice and not an ineffective iteration,
so the contract stop rule (section 28) is not triggered. Root cause: missing
pre-validation input bound. Frozen fix (round 4, narrow):

- Add an ITERATIVE (non-recursive) `_validate_json_shape(raw)` that runs
  before `deepcopy`: only dict (str keys) / list / str / int / float / bool /
  None; non-finite floats rejected; max container depth 128 (above the
  trusted condition cap 64 plus document nesting); max total JSON values
  65536; max string length 4096. Any violation -> GameplayContractError.
- `parse_skill_ir` calls it first; `compile_skill_ir` already wraps
  json.loads RecursionError.
- No other semantic change; all prior tests must pass unchanged.

## Main Decision After Round-4 QA (2026-10-30)

Round 4 fixed the recursion leak (verified). QA reported two NEW, distinct
defects; each round has fixed its target, so section 28 stop is not
triggered, but Main re-analysed the root cause instead of patching blindly.

1. Trusted condition caps vs lowering. Root cause is a contract mismatch,
   not a lowering bug: every accepted runtime re-entry point
   (`SkillRegistry.install`, `checkpoint` restore, `parse_skill_blueprint`)
   parses each blueprint condition with the runtime DEFAULT
   `ConditionLimits()` (16/64/16). Propagating looser caps only into IR
   lowering would create blueprints that the registry/checkpoint cannot
   re-parse, i.e. un-restorable Skills. Decision: the IR condition budget is
   TIGHTEN-ONLY relative to the runtime default. `parse_skill_ir` rejects
   (GameplayContractError, before any parsing) a `condition_limits` with any
   field above `ConditionLimits()` defaults. Raising the runtime default is a
   separate, future runtime-wide change (registry + checkpoint + IR together),
   not a P2.1 item. The round-4 review requirement "legal under trusted caps
   64/4096/256 must parse" is superseded by this decision; the replacement
   requirement is "looser-than-default limits are rejected fail-closed, and
   any limits <= default parse exactly as the runtime would".
2. Oversized integers. Root cause: shape validation accepts unbounded Python
   ints that later hit float conversion. Decision: `_validate_json_shape`
   rejects non-bool ints with `abs(value) > 2**53` (JSON safe integer range)
   with GameplayContractError.
3. Hostile container subclasses: scope note accepted; the input contract is
   plain JSON from `json.loads`. Plain dict/list subclasses stay accepted
   (existing independent requirement `test_plain_json_subclasses_and_scalar_edges`);
   no change.

Test governance: QA's round-4 test
`test_documents_at_trusted_condition_caps_parse_and_compile` encodes the
superseded requirement. It is NOT weakened by the fix owner; the independent
QA owner rewrites it to the replacement requirement (looser limits rejected
fail-closed at parse; limits equal to defaults reach exactly the default
16/64/16 boundary through parse, compile, registry install and checkpoint
restore), and the rationale is recorded in P2_SKILL_IR_REVIEW.md.
