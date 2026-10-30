# P1 Scenario Completion Increment

## Scope

This increment closes the three PARTIAL classifications in
`P1_SCENARIO_CONFORMANCE.md` with one new test module. It changes no production
code, Engine/Core source, Alpha source, existing test, ledger, or project-run
file.

The proof chain for every scenario is:

`parse_skill_blueprint` -> `make_content` -> `initialize_content_world` ->
`compile_content` -> `build_content_session` ->
`MechanismRegistryRuntime.from_compiled_content` -> `change_loadout` ->
`submit_timed_primary_action` / `advance_world_tick`.

The same parsed Skill objects are installed for both PLAYER and NPC. Scenario 1
and 7 use the C5.1 move-actor fixture IDs and its two-Area world; Scenario 9
uses the P1 fixture IDs and its Area. Each controller receives an independent
time-zero runtime, so clock, Mana, schedule, and state accounting do not leak
between the two executions. C5.2 Derived specs are trusted fixture input only.

## Scenario 1 - Leaves, Keeps Evolving, Returns

**Status: PASS.**

The attractor Skill changes humidity target from 0.8 to 0.6:

`(0.8 * 1 + 0.4 * 1) / (1 + 1) = 0.6`.

The paid attractor Tick evolves `0.2 -> 0.28`. A separate parsed `move_actor`
Skill then moves the actor from A to B; its paid Tick runs after commit and
evolves A to `0.344`. Three real free Ticks while the actor remains in B give
`0.3952 -> 0.43616 -> 0.468928`. The actor returns through the same parsed
`move_actor` Skill; the returning paid Tick gives
`0.468928 + 0.2 * (0.6 - 0.468928) = 0.4951424`.

Assertions cover exact origin values, exactly one `located_in` edge at each
stage, A -> B -> A movement, Mana `20 -> 15 -> 11 -> 7`, and finite time
`spent_ticks 1 -> 2 -> 3`.

## Scenario 7 - Relation Change Blocks a Later Rule

**Status: PASS.**

A parsed `relation_modifier` disables the only A-B `pmw_gameplay_link`
(`effective_enabled is False`) for three Ticks. A subsequent parsed
`move_actor` request is rejected with `move_actor path is disabled`. A full
runtime snapshot (state, revision, object revision, stats, state-closure flag,
schedule, runtime identity), Mana, and spent Ticks are asserted byte-equal
after rejection.

The overlay expires across two real Ticks after its paid Tick (`expires_at=3`,
clock already at 1), restores `effective_enabled is True`, and the same move
request succeeds. Both controllers end in B with Mana 15 and two spent Ticks.

## Scenario 9 - Derived Values and a Derived Gate

**Status: PASS.**

The trusted Area catalog has:

- `comfort = clamp(2 * humidity, 0, 2)`
- `humid = 1 when humidity >= 0.5 else 0`

Initial values are `0.4` and `0.0`. The parsed top-level `derived` condition is
false, so the gate Skill is rejected atomically with no Mana/time/state
change. A separate parsed paid `modify_field` raises humidity to `0.5`; the
same Engine publication changes comfort `0.4 -> 1.0` and humid `0.0 -> 1.0`.
The trace contains the expected Derived state-Law IDs and persisted old/new
values.

The paid Tick reaches humidity `0.56`, comfort `1.12`. Two free Ticks reach
`0.608` / `1.216` and `0.6464` / `1.2928`. The original parsed gate Skill is
then accepted, pays four Mana and one Tick, and grants shield 1 for both
controllers.

## Anti-Special-Case Scan

The module statically scans production `gameplay_v04/*.py` for every new Skill
ID and the new test module name and requires zero hits. Production behavior is
therefore selected by parsed content and compiled Laws, not by test or Skill
names.

## Fixture Corrections and Product Findings

A fixture issue was found and fixed in the test only: `test_p1_scenarios.py`
and `test_sandbox_move_actor.py` intentionally define different actors under
the same `PLAYER`/`NPC` Python constant names. The new tests now pair each world
with its own move-actor or P1 actor IDs and equip each runtime explicitly.

No product defect was found in the exercised C5.1/C5.2 paths. The existing
move-actor and Derived acceptance suites also pass in the final focused run.

## Verification

Focused command:

`python -m pytest -p no:cacheprovider -q` on
`test_p1_scenarios_completion.py`, `test_p1_scenarios.py`,
`test_sandbox_move_actor.py`, and `test_sandbox_derived_catalog.py`.

Result: **36 passed (4 new, 10 P1, 11 move-actor, 11 Derived), 52 subtests
passed**.

Per-scenario outcome:

- Scenario 1: PASS for PLAYER and NPC.
- Scenario 7: PASS for PLAYER and NPC.
- Scenario 9: PASS for PLAYER and NPC.
- Anti-special-case production scan: PASS.

Evidence: `evidence/p1_completion_owner_focused.log`.
Collection manifest: `evidence/p1_completion_owner_collect.log` (36 tests).

New test file SHA256:
`C6AA34E3DA7CA09454EFC6F598F9B3A2625C693B4BB1D227041ED807DA7455A3`.
