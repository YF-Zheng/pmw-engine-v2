# P1 Completion Conformance Independent Review

## Verdict

All ten P1 scenarios now **PASS** against the contract text. The prior three
PARTIAL classifications (scenarios 1, 7, and 9) are closed by formal,
candidate-facing mechanics:

- C5.1 bounded `move_actor` supplies paid relocation through Core lifecycle
  Laws.
- The trusted `pmw_gameplay_link` overlay is consulted by traversal, so a
  disabled path blocks movement and expiry restores it.
- C5.2 supplies a read-only Area Derived catalog written by Core state Laws,
  readable by typed conditions and followed over real Ticks.

| # | Status | Independent verdict | Closure basis |
|---|---|---|---|
| 1 | PASS | **PASS** | Attractor Skill, paid A->B move, three free Ticks in B, paid return; origin Field continues toward the modified target and a no-attractor control differs causally. |
| 2 | PASS | **PASS** | Previously accepted; target/rate remain distinct and causal. |
| 3 | PASS | **PASS** | Previously accepted; independent expiries remain intact. |
| 4 | PASS | **PASS** | Previously accepted; Process Stock conversion remains intact. |
| 5 | PASS | **PASS** | Previously accepted; Process rate/duration modification remains intact. |
| 6 | PASS | **PASS** | Previously accepted; passive recursion bound remains intact. |
| 7 | PASS | **PASS** | Paid Relation overlay disables the only A-B link; move rejects only in the overlay world, atomically; two free Ticks restore the path and the same request then succeeds. |
| 8 | PASS | **PASS** | Previously accepted; Law-driven Discrete transition remains intact. |
| 9 | PASS | **PASS** | Area Derived values follow Field changes through Engine state Laws; threshold opens at `>= 0.5`, closes below it, and gates a parsed Skill for both controllers. |
| 10 | PASS | **PASS** | Previously accepted; identical parsed execution for PLAYER and NPC remains intact. |

No PRODUCT_DEFECT was found in the reviewed completion paths. No FIXTURE_ERROR
remains in the owner completion module.

## Formal-Chain Audit

The owner completion module uses the required chain:

`parse_skill_blueprint` -> `make_content` ->
`initialize_content_world` -> `compile_content` ->
`build_content_session` -> `MechanismRegistryRuntime.from_compiled_content` ->
`change_loadout` -> `submit_timed_primary_action` -> `advance_world_tick`.

Worlds, Fields, Actors, Relations, trusted Relation profiles, and trusted
Derived specs are fixture setup at time zero. The production paths then use
paid Actions and real Ticks. The completion module does not call
`apply_source`, `remove_source`, a private Action resolver, `run_event`, or a
Law/Event injector after initialization.

Static search found no assignment through
`runtime.session.state...`, `components[...] =`, or `relations[...] =` in that
module. Its only state-changing calls are paid Action submission and real
World Tick advancement.

The owner module pairs move-actor fixture IDs with the move-actor world and P1
fixture IDs with the P1 world. This avoids the prior cross-fixture actor-name
collision and is not a product special case.

## Causal Numbers

### Scenario 1

Initial Field: value `0.2`, target `0.8`, rate `0.2`. The parsed attractor
Skill adds target `0.4` with weight `1` and duration `10`, so:

`effective_target = (0.8 * 1 + 0.4 * 1) / (1 + 1) = 0.6`.

Paid attractor Tick: `0.2 + 0.2 * (0.6 - 0.2) = 0.28`.

Paid leave Action commits A->B, then its Tick evolves A:
`0.28 + 0.2 * (0.6 - 0.28) = 0.344`.

Three free Ticks while the actor is in B:

1. `0.344 + 0.2 * (0.6 - 0.344) = 0.3952`
2. `0.3952 + 0.2 * (0.6 - 0.3952) = 0.43616`
3. `0.43616 + 0.2 * (0.6 - 0.43616) = 0.468928`

Paid return commits B->A, then its Tick gives:
`0.468928 + 0.2 * (0.6 - 0.468928) = 0.4951424`.

Mana is `20 -> 15 -> 11 -> 7`; spent finite Ticks are `1 -> 2 -> 3`.
There is exactly one `located_in` Relation throughout each A/B/A stage.

Independent counterfactual: the same material, move Skill, world, Action
sequence, and paid `basic_wait` first Tick without the attractor Skill leave
the target at baseline `0.8`. Its origin values after leave plus three free
Ticks are `0.416, 0.4928, 0.55424, 0.603392`, versus the attractor path's
`0.344, 0.3952, 0.43616, 0.468928`. The final counterfactual gap is
`0.134464`, proving the attractor Skill, not merely relocation or Tick
advancement, causes the persistent difference. Both PLAYER and NPC pass.

### Scenario 7

The trusted profile binds the only A-B adjacent link. The parsed
`relation_modifier` disables it for three Ticks at time zero:

`expires_at = 0 + 3 = 3`.

Its paid Tick moves the clock to `1`, so two free Ticks reach time `3` and
expire the overlay. The same parsed `move_actor` request then succeeds.

Mana is `20 -> 19` on disable and `19 -> 15` on the eventual move; spent Ticks
are `1 -> 2`. The rejection does not deduct Mana or Tick budget.

Independent controls:

- **No overlay:** the same parsed move with no disable Skill succeeds A->B,
  spends one Tick, and reduces Mana `20 -> 16`.
- **Overlay:** the disabled-only-link world rejects with
  `move_actor path is disabled`.
- **Atomicity:** the rejection snapshot is byte-equal for full WorldState,
  runtime revision/object revision/stats/closure flag, scheduled events, and
  runtime identity. The review additionally compares manifest entries,
  blueprint hashes, and all Action hashes before and after rejection; they are
  unchanged.

Both PLAYER and NPC produce the same disabled-only-link rejection and
post-expiry success.

### Scenario 9

Trusted Area specs:

- `comfort = clamp(2 * humidity, 0, 2)`
- `humid = 1.0 iff humidity >= 0.5, else 0.0`

Initial `humidity = 0.2`: `comfort = 0.4`, `humid = 0.0`. The parsed gate
Skill is rejected atomically before any payment.

The parsed paid `modify_field` writes `0.2 + 0.3 = 0.5`. The Engine trace
records that exact Field delta and the resulting Derived deltas
`comfort 0.4 -> 1.0` and `humid 0.0 -> 1.0`. The paid Tick then evolves:

`0.5 + 0.2 * (0.8 - 0.5) = 0.56`,

so the published `comfort = 2 * 0.56 = 1.12`. Two further free Ticks produce
`0.608 -> comfort 1.216` and `0.6464 -> comfort 1.2928`. The gate then pays
one Tick and four Mana and grants shield `1.0`. Both PLAYER and NPC pass.

Additional boundary probes:

- Direct Field `0.5`: `humid = 1.0`, gate accepted, one Tick and four Mana
  spent.
- Direct Field `0.499999999999`: `humid = 0.0`, gate rejected atomically.
- Downward crossing from `humidity 0.6` to a still-accepted boundary `0.5`,
  then to `0.4`: trace records `humid 1.0 -> 0.0`; the gate subsequently
  rejects with no state, Mana, or Tick change.

These results confirm the threshold is not one-way and the gate reads the
trusted Derived value at the exact `>=` boundary. Both PLAYER and NPC pass.

## Production Special-Case Scan

Search of production `gameplay_v04/*.py` found **zero** hits for all owner and
review Skill IDs, request IDs, and test module names. Production dispatch is
selected by parsed effect kinds, selectors, hashes, capabilities, and compiled
Laws.

The remaining `skill_id`/`action_id` comparisons found in production are
generic registry, loadout, lineage, or hook identity checks. They do not
compare against the scenario IDs. The built-in `basic_attack`, `basic_guard`,
and `basic_wait` names are part of the installed Basic Action registry, not
P1 scenario special cases.

No second world simulator is used for the collected scenarios. The formal
completion tests use `MechanismRegistryRuntime` and the Engine; the newer
projection-only sandbox is a separate candidate forecast path and is not
substituted for authoritative execution.

## Findings

1. **PRODUCT_DEFECT: none.**
2. **FIXTURE_ERROR: none remaining** in the owner completion module. Prior
   actor/world pairing was corrected in the fixture, not by production
   special-casing.
3. **SCOPE_NOTE: `move_actor` and candidate forecast support are bounded.**
   C5.1 does not provide a generic path solver, legal-action target
   enumeration, teleport, or Alpha travel integration. C5.2 exposes two
   strict Derived kinds and current-Area reads. These are documented limits,
   not omissions against the P1 scenario text.
4. **SCOPE_NOTE: Observation projection is concurrent work.** The revalidation
   fix owner is editing `observation.py` and `simulation.py`. The collected
   P1 scenarios do not depend on that projection for authoritative outcomes.

## Previously PASS Scenarios

- **Scenario 2:** PASS unaffected; distinct target and rate sources still
  produce `effective_target=0.6`, `effective_rate=0.3`, values `0.32/0.404`.
- **Scenario 3:** PASS unaffected; humidity and temperature still expire
  independently at the asserted Tick boundaries.
- **Scenario 4:** PASS unaffected; Process still converts ore `8->7->6` and
  ingot `0->1->2` through real Ticks.
- **Scenario 5:** PASS unaffected; Process modification still yields rate
  `2.0`, remaining `2`, duration `4`, and ore/ingot `5/3`.
- **Scenario 6:** PASS unaffected; the passive still fires once per root for
  PLAYER and NPC and stops recursion with the duplicate-root skip.
- **Scenario 8:** PASS unaffected; the paid Field change still triggers the
  Law-driven dry->wet transition and the expected values.
- **Scenario 10:** PASS unaffected; the same parsed Skill still pays and
  executes identically for PLAYER and NPC.

## Verification

Focused command:

`python -m pytest -p no:cacheprovider -q -rA`
on the review module, the owner completion module, and
`test_p1_scenarios.py`.

Result: **19 passed, 18 subtests passed, exit `0`**.

Breakdown:

- Review module: 5 tests, 12 subtests.
- Owner completion module: 4 tests, 6 subtests.
- Original ten-scenario module: 10 tests.

Evidence:
`docs/agent_bootstrap/evidence/p1_completion_review_focused.log`
(SHA256 `2AF8C418DD9022D60DB7D31024D1C73FD9C0CD746D233D1FFE4C9A37BF3667C5`).

Test hashes:

- Review:
  `EAB301F333D120D1B35C80B7A102C7F68D4B1E4E1CA49FCFCBA3F28195336B09`
- Owner completion:
  `C6AA34E3DA7CA09454EFC6F598F9B3A2625C693B4BB1D227041ED807DA7455A3`

## Recommendation

**Accept all ten P1 scenarios as PASS.** No reviewed completion-path defect
requires repair before checkpoint. Recommended checkpoint statement: the P1
Gate is met for scenarios 1-10 through the formal Engine, with no scenario-ID
special case and no second authoritative world simulator.
