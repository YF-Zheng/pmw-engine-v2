# P1 Scenario Conformance Independent Review

## Verdict

The owner report's classifications are honest. **No scenario is downgraded.**
The seven PASS claims are supported by at least one causal, non-baseline
assertion. The three PARTIAL claims disclose their missing capability rather
than presenting it as covered.

The collected module passed **10/10** in 4.494 seconds, exit `0`:
`evidence/p1_scenarios_review_run.log`. The reviewed test file remained
`06653F28E28A3B2FD8B1271B5A805346B5633B69D4552B394327C94BD1D7AC62`.

| # | Owner status | Independent verdict | Basis |
|---|---|---|---|
| 1 | PARTIAL | **CONFIRMED PARTIAL** | Paid persistent Area source and evolution are genuine; off-Area departure has no formal action. |
| 2 | PASS | **CONFIRMED PASS** | Target and rate use distinct paid sources and produce independently changed effective values. |
| 3 | PASS | **CONFIRMED PASS** | Two paid modifiers expire on different ticks; active state and effective rates prove independence. |
| 4 | PASS | **CONFIRMED PASS** | Trusted Process start and Tick convert input Stock to output Stock through compiled Laws. |
| 5 | PASS | **CONFIRMED PASS** | Paid modify changes rate, remaining, duration and progress, then conversion continues. |
| 6 | PASS | **CONFIRMED PASS** | Same parsed passive fires for both actors; duplicate root is visibly skipped and HP stays non-baseline. |
| 7 | PARTIAL | **CONFIRMED PARTIAL** | Paid overlay and expiry are genuine; no formal consumer turns availability into supply/path behavior. |
| 8 | PASS | **CONFIRMED PASS** | The paid Field effect causes the dry-to-wet transition; a zero-effect control remains dry. |
| 9 | PARTIAL | **CONFIRMED PARTIAL** | Diagnostics react to the paid change; no unified candidate-facing Derived catalog exists. |
| 10 | PASS | **CONFIRMED PASS** | Both controllers execute the identical parsed/compiled Skill and both effects are causally required. |

## Method And Formal-Chain Audit

The fixtures create initial Actors, Areas, Fields, Stocks, a trusted Process or
Relation profile, and a time-zero clock. Those values are legitimate setup.
After initialization, the tests do not call `apply_source`, `remove_source`,
Process/Relation controller `start`/`modify`, a private action resolver, or a
Law/Event injector. Runtime changes result from `submit_timed_primary_action`,
`run_combat_round`, and real ticks; the only later direct
`advance_world_tick` calls are explicit tick observations.

The chain is implemented as claimed:

- `_skill` parses raw JSON through `parse_skill_blueprint` with a material
  authority. `_formal_runtime` uses `make_content`, `initialize_content_world`,
  `compile_content`, `build_content_session`,
  `MechanismRegistryRuntime.from_compiled_content`, and `change_loadout`.
- Timed actions stage, authorize an exact currently equipped registry hash,
  resolve, dispatch hooks, spend clock time, then publish. Mana is deducted by
  the paid-action path; duration is charged by `spend_world_time`.
- The registry rebuilds its active registry and Laws from the formal manifest.
  Process and Relation controllers contribute trusted Laws during compilation;
  their `prepare_*` calls are preflight-only and their effects arrive through
  emitted runtime Events.
- PLAYER/NPC parity means the same parsed Skill object and action hash execute
  under each controller, not merely that two similar fixtures reach the same
  constant. Scenarios 1–5, 7–10 exercise both actors where an actor effect is
  relevant. Scenario 6's passive is managed by one combat root but executes
  for both owners. Scenario 7 uses two independent time-zero worlds because the
  trusted profile has one owner; the same Skill object is used.

No PASS assertion is accepted solely because it equals its initialized value.
The controls below establish sensitivity where an arithmetic assertion alone
could otherwise look ambiguous.

## Per-Scenario Review

### 1. Off-Area persistent change — CONFIRMED PARTIAL

**Honest scope.** A paid `dynamics_modifier` creates an owned temporary source
at `0.44`; subsequent ticks use the modified rate and produce
`0.584, 0.6704, 0.72224`. The source remains active with a non-null expiry. The
PLAYER and NPC worlds share the parsed Skill.

**Mutation evidence.** Delete/zero `rate_add=0.2`. The paid action then creates
a neutral-rate source and the Field stays at the initial `0.2` rather than
reaching `0.44`; all four value assertions fail.

**Gap is correctly declared.** `move_actor` is not an Effect kind. The test does
not claim a relocation occurred, and it keeps the owner in the Area. Calling
the claimed portion "persistent Area change" is accurate, but "off-Area
persistent change" remains partial because the departure action is absent.

### 2. Target vs rate separation — CONFIRMED PASS

**Honest scope.** Two paid effect rows produce distinct source IDs. The target
source reports `target=0.4`; the rate source reports `target_weight=0`.
Effective target/rate become `0.6/0.3`, the paid tick gives `0.32`, and an
explicit tick gives `0.404`.

**Mutation evidence.** Set `modify_attractor.amount` to `0`. Effective target
returns to baseline `0.8`, the first value becomes `0.24`, and the second
`0.348`; the `0.6`, `0.32`, `0.4`, and `0.404` assertions fail. Independently
setting `modify_rate.amount` to `0` makes effective rate `0.2`, first value
`0.28`, and second `0.344`. Either mechanism is therefore required.

The source-ID checks demonstrate separation; the paid values demonstrate both
sources affect world state.

### 3. Independent modifier expiry — CONFIRMED PASS

**Honest scope.** Humidity and temperature begin with owned modifiers at rates
`0.4` and `0.3`. After one tick, humidity is inactive/`0.2` while temperature
is active/`0.3`; after two more ticks, temperature is inactive/`0.1`.
Scheduled events are empty and the action spent one Tick. PLAYER and NPC use
the same parsed Skill in independent worlds.

**Mutation evidence.** If humidity's duration is changed to `4`, its first
tick remains active and the `effective_rate=0.2` assertion fails. If
temperature's duration is changed to `2`, it expires with humidity and the
first-tick `effective_rate=0.3` assertion fails. If either slot effect is
removed, the two-slot layout and its active-rate assertions fail.

The test proves independent expiry timing, not only that the fixture supplied
two different slots.

### 4. Process Stock conversion — CONFIRMED PASS

**Honest scope.** A parsed `process_start` costs one Tick and 4 Mana. The
trusted controller preflights the exact owner-local profile, emits
`PROCESS_START_EVENT`, and an installed Process start Law activates it. The
same paid Tick converts ore `8 -> 7` and ingot `0 -> 1`; a later explicit tick
produces `6` and `2`.

**Mutation evidence.** Set conversion `quantity` to zero (or remove the
conversion Law from compilation). Start can still activate, but ore stays `8`
and ingot `0`; the first-tick `7/1` assertions fail. Removing the start effect
leaves the Process stopped and fails its `running` assertion.

The initial `8/0` Stocks are setup; the asserted `7/1` and `6/2` are paid/real-
tick outcomes.

### 5. Process rate/duration modification — CONFIRMED PASS

**Honest scope.** Each actor spends one Tick and 4 Mana on start and another
on `process_modify`. The trusted modify preflight computes `rate=2.0`,
`remaining=2`, `duration=4`, `elapsed=2`; the installed modify Law reschedules
the expiry, and subsequent conversion yields ore `5`/ingot `3`.

**Mutation evidence.** Set `rate=1.0`: the paid start/modify ticks produce ore
`6`/ingot `2`, so the asserted `5/3` values fail. Set `remaining=4`: the
asserted remaining/duration/progress substitution fails. Removing the modify
effect leaves the Process at its initial rate and does not satisfy the rate
assertions.

The test checks both configuration and consequence, not just a prepared
payload.

### 6. Passive recursion prevention — CONFIRMED PASS

**Honest scope.** Managed combat with the same parsed passive equipped for
PLAYER and NPC fires `damage=4` at hook depths 1 and 2. HP is `36` for PLAYER
(40 primary damage plus 4) and `46` for NPC (4). A third record is skipped with
`duplicate owner+hook source in this root`; HP is unchanged afterward and one
Tick is spent.

**Mutation evidence.** Set passive `amount=0`. `resolved_damage` is zero, so the
damage hook does not emit and the expected fired records disappear; PLAYER
stays at `40`, not `36`, and NPC at `50`, not `46`. Removing the
`max_firings_per_root` duplicate bound admits another record/HP reduction. The
specific skipped reason would also be absent.

The HP values are not no-op outcomes. Both owners' passive effects are
observed in the same managed root despite only NPC supplying the primary
attack.

### 7. Relation change alters supply/path — CONFIRMED PARTIAL

**Honest scope.** A paid `relation_modifier` disables a base-enabled typed
Relation, costs one Tick and 1 Mana, sets `enabled/effective_enabled=false`,
and schedules expiry at `3.0`. Three real ticks expire it and restore effective
availability to base `true`.

**Mutation evidence.** Remove/zero the relation modifier. The overlay stays
base-enabled, so the post-action `effective_enabled=False` assertion fails.
Remove expiry handling and the post-three-tick restoration assertion fails.

**Gap is correctly declared.** No generated consumer reads this Relation
component to alter supply, reachability, movement, or Stock. The test therefore
does not claim the scenario's supply/path consequence, only the paid overlay
and lifecycle. PARTIAL is honest.

### 8. Discrete transition triggered by a Law — CONFIRMED PASS

**Honest scope.** The paid `+0.5 modify_field` raises humidity `0.20 -> 0.58`
as a direct Field write. The same paid action then charges its Tick; the
compiled ecology commit Law sees the `0.55` threshold, changes `dry -> wet`,
emits one `ECOLOGY_CHANGED_EVENT`, and commits the wet baseline target `0.9`.
A later explicit tick produces `0.644`.

**Causal control (executed).** The probe keeps the parsed Skill, formal
compilation/equip/payment/Tick path, and ecology Plan, but changes the Field
effect to `amount=0`. Result:

```text
changed_event_count: 0
ecology_after_tick: dry
field_value_after_tick: 0.18
spent_ticks: 1
```

Without the paid effect, humidity falls from `0.20` toward the dry target and
the transition event never appears. The `dry -> wet` change is caused by the
Skill and is not an inevitable Tick transition. The original test's event,
state, baseline, and `0.58/0.644` assertions all reject the no-effect control.
Full transcript: `evidence/p1_scenarios_review_probe.log`.

### 9. Derived value reacts to dependency change — CONFIRMED PARTIAL

**Honest scope.** A paid `dynamics_modifier` reduces effective rate `0.2 ->
0.1`. The diagnostic assertion proves the dependency change; the modifier
expires on the next tick and rate returns to `0.2`. Both actors use the same
parsed Skill.

**Mutation evidence.** Set `rate_add=0`. Effective rate remains `0.2`, failing
the post-action `0.1` assertion and the linked modifier expiry expectations.

**Qualification, not downgrade.** The `value=0.26` assertion is weak by itself:
`0.2 + 0.2*(0.8-0.2) = 0.32`, but after the paid Tick it is also `0.26` if
the modifier's rate is `0.2`, so this value alone does not discriminate. The
reviewed test also asserts `effective_rate=0.1`, which is discriminating and
matches the scenario's dependency-change claim. Removing the final Derived
catalog/product remains a real declared GAP; PARTIAL is honest and should not
be promoted to PASS.

### 10. PLAYER/NPC same execution — CONFIRMED PASS

**Honest scope.** One parsed Skill/action hash is registered and equipped for
both Actors. Each request reports that action hash, costs one Tick and 3 Mana,
and ends at Mana `27`/shield `7`; the clock shows two spent Ticks. Separate
Area placements prevent current-Area identity from being the cause.

**Causal control (executed).** With `shield amount=0` but the same parsed,
equipped, paid action for both Actors:

```text
PLAYER: mana 27.0, shield 0
NPC:    mana 27.0, shield 0
spent_ticks: 2
```

The shield assertions fail for both controllers, while Mana/time payment and
identical execution remain visible. Removing NPC's equip/execution or changing
its action hash also breaks the parity assertions. The test genuinely exercises
the same Skill, not merely equal constants.

## Findings

1. **No fixture-time fabrication or payment bypass found.** Initial setup is
   legitimate; live outcomes are Law/Event driven through the normal paid and
   tick boundaries.
2. **No undisclosed PASS overclaim found.** Scenario 8 is causally sensitive;
   scenario 9's redundant value check is qualified above but its required
   diagnostic mutation is asserted.
3. **The three gaps are real and correctly kept PARTIAL.** They are missing
   actor relocation, Relation supply/path semantics, and a unified
   candidate-facing Derived bridge. None is silently simulated in the tests.
4. **The only coverage limitation to retain is the scenario 9 value assertion.**
   It should not be cited alone as mutation sensitivity; the effective-rate
   assertion carries that proof.

## Evidence

- Collected result: `evidence/p1_scenarios_review_run.log` — 10 tests, all
  passed, 4.494s, exit `0`.
- Focused no-effect controls:
  `evidence/p1_scenarios_review_probe.log` — scenario 8 remains `dry`/no event;
  scenario 10 shield `7 -> 0` for both Actors.
- Probe source: `evidence/p1_scenarios_review_probe.py` (non-collected).
- Test hash:
  `06653F28E28A3B2FD8B1271B5A805346B5633B69D4552B394327C94BD1D7AC62`.
