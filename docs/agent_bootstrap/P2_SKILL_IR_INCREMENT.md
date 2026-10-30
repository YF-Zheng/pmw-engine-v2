# P2.1 Skill IR Increment

## Scope

P2.1 adds a strict, versioned Skill IR layer over the accepted v0.4 runtime:

- `gameplay_v04/skill_ir.py`: protocol `pmw-skill-ir-v1`, document-wide
  validation, lowering through the existing `parse_skill_blueprint`, canonical
  hashes, metadata, Operator/state-class coverage, and deterministic preview.
- `gameplay_v04/tests/test_skill_ir.py`: owner tests for schema, trigger gaps,
  shared budgets, authority, hash parity, classification, determinism, and a
  formal Player/NPC runtime chain.

The compiler is a pure lowering layer. It does not add an Engine, evaluator,
clock, transaction path, Law family, or second SkillBlueprint parser.

## Implemented Contract

- Closed top-level and nested keys are required exactly as specified by
  `P2_SKILL_IR_DESIGN.md`.
- IDs, positive integers, finite numeric values, booleans-as-numbers, context
  hashes, summary length, tag count, entry count/uniqueness, the single
  `on_use` entry, and the lowered 64-character ID grammar are validated
  before lowering.
- `{"kind":"on_use"}` lowers to `skill_blueprint`; a
  `{"kind":"on_event","event":"damage_resolved"}` entry lowers to
  `passive_blueprint` with neutral cost `{"duration":1,"mana":0}`.
- Reserved trigger kinds (`on_tick`, `on_expire`, `transition`, conditional
  transition names) and reserved hook events reject with a
  `language_gap:`-prefixed message. Unknown trigger junk uses an ordinary
  schema error.
- Condition nodes are counted across every entry condition and every effect
  condition in the document. `null` contributes one node, matching the
  existing `parse_condition` traversal. The sum must fit the trusted
  `ConditionLimits.max_nodes`.
- Material usage is the sum of all lowered entries' existing
  `SkillBlueprint.budget_used` values, including the existing passive `+0.5`.
  It must fit both `limits.budget` and `authority.budget_points`.
- The IR hash is SHA256 over sorted-key, compact JSON with `allow_nan=False`.
  Key order does not affect the IR hash, lowered canonical hashes, metadata,
  Operator/state-class sets, or preview.
- `metadata_by_ir_hash[ir.canonical_hash]` maps to immutable
  `(lowered_id, version, lowered_canonical_hash)` records.
- Preview content is generated from parsed blueprints/specs. `summary` is not
  parsed or injected into it.

## Boundaries

- The accepted `skills.py` restricts Process/Drive/Relation control effects
  and other runtime-sensitive effects to primary `on_use` entries. P2.1
  deliberately inherits those restrictions by calling the existing parser
  rather than bypassing or duplicating them. An `on_event` entry using such an
  effect is rejected by the accepted runtime contract.
- P2.1 does not implement the 30-skill reference library, Gate categories for
  that library, or a full P2 Gate claim. Those remain P2.2 work.
- No generation provider is called.

## Verification

The owner suite covers the requested rejection matrix, every named
language-gap trigger/event family, exact condition and material budget
boundaries, multi-entry bypass, authority by effect kind/selector, v0.4 hash
parity, Operator/state-class classification, key-order determinism, and a
two-entry `on_use` plus `damage_resolved` passive through
`make_content -> initialize_content_world -> compile_content ->
build_content_session -> MechanismRegistryRuntime.from_compiled_content ->
change_loadout -> submit_timed_primary_action/run_combat_round`.

Focused final evidence: `docs/agent_bootstrap/evidence/p2_ir_owner_focused.log`.

## Fixture Errors Fixed During Owner Test Construction

These were fixture-authoring mistakes, not product findings:

- `grant_trait` fixture omitted its required positive `duration`.
- The initial operator/state catalog fixture placed Process control on a
  passive entry; the accepted runtime permits Process control only on the
  active entry, so the fixture now exercises the classification through the
  single `on_use` entry.
- The end-to-end combat HP expectation ignored shield absorption and passive
  trigger ordering; corrected to the actual deterministic 45 HP / 3 shield.
- The combat time assertion used the wrong public field name; corrected to
  `time_spend_result.duration`.
- A condition-parity assertion included an extra synthetic root by mistake;
  it now compares the IR document's per-condition root accounting explicitly.

## Product Findings

- `Derived` classification must inspect both entry conditions and parsed
  effect conditions. The compiler's state-class classifier does so.
- The existing runtime's accepted passive-effect restrictions are the
  authoritative language boundary for P2.1; the IR validator does not attempt
  to widen them.
