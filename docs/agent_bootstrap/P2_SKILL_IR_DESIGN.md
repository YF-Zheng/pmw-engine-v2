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
