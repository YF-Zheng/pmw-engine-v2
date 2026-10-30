# P2.1 Skill IR Fourth Fix

## Change

`parse_skill_ir` now calls iterative `_validate_json_shape(raw)` before
`deepcopy(raw)`. The validator uses an explicit stack, accepts only JSON-shaped
values and tuples, and raises `GameplayContractError` with a path for:

- unsupported values or non-string dictionary keys;
- non-finite floats;
- container depth above 128;
- more than 65,536 total values;
- any string or key longer than 4,096 characters.

No other parse or compile semantics changed. A legal document retains the same
IR and lowered blueprint hashes.

## Verification

`tests/test_skill_ir_fix4.py` covers the 500-level reproduction, depth 2,000,
dict nesting above the limit, excess values, overlong strings and keys,
non-string keys, sets, arbitrary objects, NaN/infinities, tuple acceptance, and
the unchanged legal document hashes.

Focused result: **77 passed, 144 subtests passed**.

Per-file results:

| File | Result |
|---|---|
| `tests/test_skill_ir.py` | 14 passed, 32 subtests |
| `tests/test_skill_ir_fixes.py` | 5 passed, 16 subtests |
| `tests/test_skill_ir_review.py` | 23 passed, 79 subtests |
| `tests/test_skill_ir_fix3.py` | 8 passed, 10 subtests |
| `tests/test_skill_ir_fix4.py` | 10 passed, 7 subtests |
| `tests/test_p1_scenarios.py` | 10 passed |
| `tests/test_gate4_registry_checkpoint.py` | 7 passed |

Evidence: `docs/agent_bootstrap/evidence/p2_ir_fix4_owner_focused.log`.

## Hashes

SHA-256:

```text
experiments/generative_mechanics/next_tracks_v06/gameplay_v04/skill_ir.py
7D02FD59EFBE6B6AFAA2B80317CC081AA33FA4720E22C66C98079CC90471575D

experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_skill_ir_fix4.py
B2AB62DA05086BFEE18ECBCA4A0DA5FE46D1A12C456378AE2EF3DAEAA8BF2AFE
```
