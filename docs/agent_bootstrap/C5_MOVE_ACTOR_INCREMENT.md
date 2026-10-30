# C5.1 `move_actor` Increment Report

## Result

Implemented the frozen C5.1 bounded relocation slice in `gameplay_v04`.
`move_actor` is a closed Effect kind appended to `EFFECT_KINDS`, requires
`adjacent_area` plus `required` commitment, costs `2.0` budget points, and is
accepted only on active `on_use` Skills. Action and Skill parsing reject
duplicate moves and all disallowed co-effects.

`ActionRequest` gains only the trailing optional `target_area_id`. Strict
request parsing, runtime target checks, staged adjacency/location/link/id
validation, conditional payload insertion, and the post-run destination check
follow the frozen design. Lowering uses two event Laws with Core
`delete_relation` and `create_relation`; no Python relation mutation occurs.
The create Law binds the acting Actor and guards `$actor.id == $event.source`,
preventing duplicate lifecycle proposals.

No existing Action, Effect, or Skill canonical hash changed. Old request
payloads remain unchanged because `target_area_id` is omitted when absent.

## Verification

- `test_sandbox_move_actor.py`: **11 passed, 30 subtests passed**
- Required focused set: **77 passed, 107 subtests passed**
  - `test_sandbox_dynamics_action.py`
  - `test_p1_scenarios.py`
  - `test_gate2_actions.py`
  - `test_gate2_effects_hooks.py`
  - `test_sandbox_relation_modifier.py`
  - `test_sandbox_relation_modifier_review.py`
  - `test_sandbox_move_actor.py`
- `git diff --check`: clean

The new tests use the real formal content chain for both player and NPC with
the same parsed Skill: material authority, `make_content`,
`initialize_content_world`, `compile_content`, `build_content_session`,
`MechanismRegistryRuntime.from_compiled_content`, `change_loadout`, and
`submit_timed_primary_action`. They cover paid lifecycle acceptance,
scenario-1 continuation, paid C3 disable/expiry/parallel-link traversal,
rejection atomicity, malformed links, checkpoint rebuild, and legacy payload
and hash stability.

## Deviations

- The required `via_relation_ids` are represented as the sorted list produced
  by preparation; the design requires the values to be JSON-serializable but
  does not mandate tuple/list representation.
- No design blocker remains. Alpha travel, legal-action area enumeration, path
  solving, and topology mutation remain intentionally out of scope.
