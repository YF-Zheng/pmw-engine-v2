# P2.1 Skill IR Third Fix

## Change

`SkillIR` now records the trusted `ConditionLimits` used during parsing as its
trailing field. `parse_skill_ir` stores that exact instance, and accepted
canonical hashes are unchanged.

`compile_skill_ir` now validates the required object types, parses
`json.loads(ir.canonical_json)` through `parse_skill_ir` with the recorded
status registry, material authority, and condition limits, then requires the
fresh canonical hash to equal the supplied canonical hash. It lowers entries,
classifies coverage, and builds the preview only from that fresh parse result.
The returned `CompiledSkillIR.ir` is also the fresh result.

The redundant `_canonical_ir` validator was removed. `parse_skill_ir` is now the
only validator, so self-consistent replacement of `canonical_json` and
`canonical_hash` cannot bypass entries, duplicate IDs, trigger count, selectors,
relation types, shared budget, origin, text bounds, or condition-node rules.
Forged derived fields such as `condition_nodes` are ignored.

## Verification

The new test covers the reviewer reproduction and the listed bypasses:
empty entries, duplicate entry IDs, two `on_use` entries, targets outside
selectors, `linked_object` without relation types, shared budget overflow,
invalid `origin.source`, over-bound text, and forged `condition_nodes`. Each
invalid canonical document is installed by setting `canonical_json` and
`canonical_hash` together with `object.__setattr__`. A valid document still
produces the same IR and v0.4 lowered hashes.

Focused result: **62 passed, 101 subtests passed**.

Per-file results:

| File | Result |
|---|---|
| `tests/test_skill_ir.py` | 14 passed, 32 subtests |
| `tests/test_skill_ir_fixes.py` | 5 passed, 16 subtests |
| `tests/test_skill_ir_review.py` | 18 passed, 43 subtests |
| `tests/test_skill_ir_fix3.py` | 8 passed, 10 subtests |
| `tests/test_p1_scenarios.py` | 10 passed |
| `tests/test_gate4_registry_checkpoint.py` | 7 passed |

Evidence: `docs/agent_bootstrap/evidence/p2_ir_fix3_owner_focused.log`.

## Hashes

SHA-256 (uppercase as reported by `Get-FileHash`):

```text
skill_ir.py
B43850A9537B0524F5CDE057CD60BFB9C91D7F01637A0870CCC9872AC2627D65

tests/test_skill_ir_fix3.py
BEF9390E0812426B90BFE15D2E1BC1E528305AA36EF16DDB4DB86BC04D3D1521
```

No existing test conflicted with the frozen decision.
