# P2.1 Skill IR Fifth Fix

## Change

`parse_skill_ir` now rejects a `ConditionLimits` instance when any of
`max_depth`, `max_nodes`, or `max_children` exceeds the corresponding
`ConditionLimits()` default. The contract error identifies the requirement as
`tighten-only`. `compile_skill_ir` inherits this check because it reparses the
canonical document with the recorded limits.

`_validate_json_shape` now defines `MAX_JSON_SAFE_INT = 2**53` and rejects any
non-boolean integer whose absolute value exceeds that limit. The rejection runs
before numeric conversion, so `2**53 + 1` and `10**400` raise
`GameplayContractError` in `costs.mana`, effect `amount`, and condition
`value`. Plain `dict` and `list` subclasses remain accepted by the existing
container branches.

## Verification

The fix-5 tests cover all three looser-limit fields at parse and compile,
16/64/16 default boundaries, registry installation and checkpoint
save/restore of a boundary blueprint, and safe/unsafe integer handling in all
three requested numeric paths.

Focused result: **60 passed, 80 subtests passed**.

Per-file results:

| File | Result |
|---|---|
| `tests/test_skill_ir.py` | 14 passed, 32 subtests |
| `tests/test_skill_ir_fixes.py` | 5 passed, 16 subtests |
| `tests/test_skill_ir_fix3.py` | 8 passed, 10 subtests |
| `tests/test_skill_ir_fix4.py` | 10 passed, 7 subtests |
| `tests/test_skill_ir_fix5.py` | 6 passed, 15 subtests |
| `tests/test_p1_scenarios.py` | 10 passed |
| `tests/test_gate4_registry_checkpoint.py` | 7 passed |

`tests/test_skill_ir_review.py` was not run or edited, per Round-5 scope.

Evidence: `docs/agent_bootstrap/evidence/p2_ir_fix5_owner_focused.log`.

## Hashes

SHA-256:

```text
experiments/generative_mechanics/next_tracks_v06/gameplay_v04/skill_ir.py
3D807D9F6D40DD6D631688824A21D295409EC94C01C72A4194CBC191364B61BB

experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_skill_ir_fix5.py
1E34CC341C95535D6B8F2EF4E2D37C19268E4E2B5691DDA8A387610D5003C915

docs/agent_bootstrap/evidence/p2_ir_fix5_owner_focused.log
4918A52362553F03D94130326BE618C560C2CA395AA4B0B8DC8D2F295EE2C385
```
