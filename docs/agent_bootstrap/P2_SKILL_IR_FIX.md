# P2.1 Skill IR Fix Record

## Scope

This fix addresses the three independent review defects in
`P2_SKILL_IR_REVIEW.md` without changing accepted semantics.

## Decisions Applied

1. `lifecycle.status_duration` remains a closed lifecycle key. `null` is
   accepted; every non-null value raises a `GameplayContractError` beginning
   with `language_gap:lifecycle.status_duration`. Runtime-supported durations
   remain on individual Effects.
2. Malformed untrusted inputs stay inside the contract exception boundary.
   Membership checks are type-guarded, and delegated blueprint parsing/lowering
   converts only `TypeError`, `KeyError`, and `AttributeError` to
   `GameplayContractError`.
3. `canonical_json` is the authoritative parse-time semantic record.
   `compile_skill_ir` verifies its SHA-256 against `canonical_hash`, reloads a
   fresh document, and lowers from that document rather than reachable mutable
   fixtures. Existing accepted IR and v0.4 blueprint hashes remain unchanged.

Length bounds from the P3 ingress guard are also enforced: 80 characters for
`identity.name`, 600 for `identity.description`, and 128 for
`origin.model`.

## Files

- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/skill_ir.py`
- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_skill_ir_fixes.py`
- `docs/agent_bootstrap/P2_SKILL_IR_DESIGN.md` (append-only decision section)

## Verification

Focused evidence is recorded in
`docs/agent_bootstrap/evidence/p2_ir_fix_owner_focused.log`. The required
suites are:

- `tests/test_skill_ir.py`
- `tests/test_skill_ir_review.py`
- `tests/test_skill_ir_fixes.py`
- `tests/test_p1_scenarios.py`
- `tests/test_gate4_registry_checkpoint.py`

The accepted owner test has no assertion that conflicts with the frozen
`status_duration` rejection decision.
