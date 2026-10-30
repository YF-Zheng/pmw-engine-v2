# P1 Ten-Scenario Formal-Runtime Conformance

## Scope And Method

This audit covers the ten P1 gates in
`SANDBOX_CAPABILITY_AUDIT.md#ten-p1-scenario-gates-at-audit-baseline`,
interpreted against the accepted C1-C4.4 increments. It is test-only work at
HEAD `1aa4aad`.

Every collected scenario uses the same formal chain:

1. A data-only SkillBlueprint document is parsed with material authority.
2. The parsed Skill enters `make_content` / `compile_content`.
3. `MechanismRegistryRuntime` and normal `change_loadout` equip it.
4. The request enters `submit_timed_primary_action`, or managed combat for the
   passive case.
5. Paid duration executes real `advance_world_tick` calls; state, Stock, Mana,
   scheduled expiry, and time-budget values are read after publication.

The initial world is fixture setup. No scenario injects a Law, calls a private
Action helper to bypass payment, or mutates live state after time zero.
Scenarios involving an actor execute the same parsed Skill for both PLAYER and
NPC. Scenario 7 uses two independent time-zero worlds because the trusted
Relation profile binds its owner; both worlds use the same parsed Skill object
and the same profile ID.

## Status Table

| # | Scenario | Status | Collected evidence test | Boundary / gap detail |
|---|---|---|---|---|
| 1 | Off-Area persistent change | PARTIAL | `test_scenario01_persistent_area_change_partial_without_formal_relocation` | PASS part: paid Skill creates an owned Area Dynamics source; after the actor remains in place, three real ticks evolve `0.44 -> 0.584 -> 0.6704 -> 0.72224` while its expiry remains scheduled. GAP part: no data-only paid actor-relocation Effect exists, so a formal "actor leaves, Area keeps evolving" action sequence cannot be expressed. |
| 2 | Target vs rate separation | PASS | `test_scenario02_target_and_rate_are_separate_sources` | Two effect slots have different source IDs; target and rate combine independently to effective target `0.6` and rate `0.3`. The paid tick gives `0.32`; a later explicit tick gives `0.404` without consuming time budget. |
| 3 | Multiple modifiers expire independently | PASS | `test_scenario03_multiple_dynamics_modifiers_expire_independently` | Humidity and temperature modifiers start together with durations 2 and 4. At the expiry boundary humidity returns from rate `0.4` to `0.2` while temperature remains `0.3`; two more ticks restore `0.1`. Scheduled expiries are empty and the paid Action costs one Tick. |
| 4 | Process consumes one Stock producing another | PASS | `test_scenario04_process_converts_input_stock_to_output_stock` | For each controller, a parsed `process_start` costs 1 Tick and 4 Mana. Actual Stocks move ore `8 -> 7 -> 6` and ingot `0 -> 1 -> 2`; the second transition is a real explicit tick. |
| 5 | Process rate and duration modification | PASS | `test_scenario05_process_rate_and_remaining_duration_modification` | Parsed `process_modify` changes rate to `2.0`, remaining to `2`, duration to `4`, and elapsed to `2`, with Stocks at ore `5` / ingot `3`. Two paid actions each cost 1 Tick and 4 Mana. |
| 6 | Passive event trigger with recursion prevention | PASS | `test_scenario06_damage_passive_fires_once_and_recursion_stops` | Managed combat fires the same parsed passive for PLAYER and NPC at depths 1 and 2, reducing HP to `36` and `46`. The next record is skipped at depth 3 with `duplicate owner+hook source in this root`; no recursive firing occurs and only one Tick is spent. |
| 7 | Relation change alters supply/path | PARTIAL | `test_scenario07_relation_overlay_partial_without_supply_path_consumer` | PASS part: the parsed Action disables the existing typed Relation overlay, pays 1 Tick and 1 Mana, sets effective availability false, schedules expiry at `3.0`, and restores true base availability after three real ticks. GAP part: no formal generated supply/path consumer reads that overlay to change movement, reachability, or Stock. |
| 8 | Discrete state transitioned by a Law | PASS | `test_scenario08_ecology_discrete_transition_triggered_by_field_law` | Paid `+0.5` Field action reaches humidity `0.58`; the same paid Tick's trace contains one `ECOLOGY_CHANGED_EVENT` for `dry -> wet` / transition `rain`. Ecology state and baseline target `0.9` commit, with value `0.644` on the next explicit tick. |
| 9 | Derived value reacting to dependency change | PARTIAL | `test_scenario09_field_diagnostics_are_partial_derived_bridge` | PASS part: a paid Dynamics change updates live Field diagnostics (`effective_rate 0.2 -> 0.1`), the paid value becomes `0.26`, and expiry after the next tick restores rate `0.2`. GAP part: there is no candidate-facing, read-only unified Derived catalog/value bridge. |
| 10 | Player/NPC same execution | PASS | `test_scenario10_same_parsed_skill_executes_for_player_and_npc` | Both controllers equip and execute the exact same parsed Skill/action hashes, each pays 1 Tick and 3 Mana, and each ends with Mana `27` / shield `7`; the clock reports two spent Ticks. |

## PASS And PARTIAL Boundaries

- **Scenarios 2-6, 8, and 10: PASS.** The stated scenario is exercised through
  parsed trusted content, compiled Laws, normal equipment, staged Action
  payment, and real world Ticks, with assertions on resulting World values.
- **Scenario 1: PARTIAL.** Persistent Area evolution is formal and paid. The
  missing sub-requirement is the action that moves the actor away; the test
  does not claim an off-Area departure occurred.
- **Scenario 7: PARTIAL.** The Relation availability overlay is formal and
  paid. The missing sub-requirement is a generated consumer that interprets
  availability as supply/path semantics. The test does not claim Stock or
  route behavior changed.
- **Scenario 9: PARTIAL.** Live Field diagnostics react to dependency changes.
  The missing sub-requirement is the general read-only Derived catalog bridge;
  the test does not claim that a candidate can query such a catalog.

## Non-Collected GAP Probes

These probes are not part of the collected test module and no test asserts that
the gaps persist. They were run as separate commands; the exact transcript is
in `evidence/p1_scenarios_gap_probes.log`.

| Missing language | Probe result | Intended location |
|---|---|---|
| Paid actor relocation | `move_actor: GameplayContractError: $.effect.kind is invalid` | `effects.py` parsing, `action_compiler.py` lowering, `actions.py` atomic write, `relations.py` location validation |
| Relation supply/path semantics | `relation_supply_multiplier: GameplayContractError: $.effect has missing or unknown fields` | `relations.py` trusted profile/consumer semantics, plus compiler and bounded consumer Laws |
| Unified Derived value | `derived_value: GameplayContractError: $.effect.kind is invalid` | `effects.py` / compiler bridge and a read-only Derived catalog module |

## Verification

- Focused command: `python -m unittest -v experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_p1_scenarios`
- Result: **10 tests run, 10 passed, 0 skipped, 0 failures, 0 errors**
- Evidence log: `evidence/p1_scenarios_owner.log`
- Test file SHA256:
  `06653F28E28A3B2FD8B1271B5A805346B5633B69D4552B394327C94BD1D7AC62`

## Highest-Value Next Scopes

1. **Typed Relation supply/path consumer.** In `relations.py`, extend the
   trusted relation profile with one bounded consumption/path edge and a
   multiplier or availability consumer; lower it through
   `action_compiler.py` and have bounded Laws update one configured Area
   availability or Stock value. Keep graph create/delete/retarget out of scope.
2. **Paid data-only actor relocation.** Add one `move_actor` Effect in
   `effects.py`, compiler lowering in `action_compiler.py`, and atomic
   Action writes in `actions.py`, validated by `relations.py` for exactly one
   current `located_in` edge and one authorized adjacent destination. Do not
   expose a generic topology editor.
