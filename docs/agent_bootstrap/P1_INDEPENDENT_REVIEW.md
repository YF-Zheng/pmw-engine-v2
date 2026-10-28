# P1 Independent Review: No-Recovery Curve and Process Sidecar

Date: 2026-10-28 (Asia/Shanghai)  
Branch: `feature/alpha-v02-seventh-night`  
Baseline: `1433e957d5391b880b71e92da4b5cf2ebd9751cd`

## Verdict

**ACCEPT P1.1 no-recovery, Process, cost ledger, and bounded Alpha time/route
authority for the frozen QA scope.** All implementations remain on the right
architectural path: the Formal Engine is the sole tick owner, Process
conversion is lowered to world-tick Laws, and Alpha route authority lives in
real relations/Laws. The two previously reported Process forged-state gaps are
fixed and independently verified.

QA scope is now frozen. No further test changes are expected unless a material
regression appears. Coding workers and the Process owner are closed; Main's
final combined run uses this frozen scope.

For no-recovery, the two previously reported gaps are now fixed:

1. **Fixed:** formal `none` ticks now clamp out-of-range state through the same
   domain range as the reference evaluator.
2. **Fixed:** ecology baseline parsing and content initialization now reuse
   `validate_curve_policy`, rejecting nonzero `none` rates.

For Process, the two previously reported gaps are now fixed:

3. **Fixed:** conversion Laws now guard tick-time rate and Stock domains. A
   forged negative rate no longer converts or creates negative Stock.
4. **Fixed:** compiled Laws now include exact conflicting-profile identities
   and require conflicting writers not to be running. A forged concurrent
   shared writer no longer spends the same input.

The final bounded QA regression below is green. Main's old-Law data comparison
also confirms that all 46 linear and 47 distance-squared Laws from HEAD remain
byte-for-byte data equal; the only additions are eight `none` override variants
per comparison. Main's focused ledger/no-recovery run was **31 passed**,
including **17 ledger tests**.

### Trust boundary clarification

`ProcessController`, `ProcessTemplate`, `ProcessProfile`, and `stock_entity`
are **privileged construction APIs**. Trusted callers cannot create a
non-positive coefficient, an invalid profile, an out-of-range stock, a
misconfigured external writer, or a competing active writer through those
APIs. Those paths fail closed in preflight and are tested below.

The world tick executes compiled Laws against current `WorldState`, including
malformed saved state, legacy writes, staged publication, or any future
administrative effect that mutates components directly. `_preflight` at
`processes.py:885` is a controller-call guard only; it does not run per tick.
Because a persistent component can be malformed outside the controller, the
final patch adds tick Law guards for rate, Stock domains, and conflicting
writers. Privileged construction remains the first boundary; these candidate
checks are the second.

## Findings

### [Resolved P1] Formal `none` now clamps state to its declared domain

- **Location:** `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/dynamics.py:184`
- **Related:** `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/dynamics.py:185`
- **Expected:** Every dynamics update obeys the Field's declared range.
- **Previous failure:** The lowered `none` law set `bounded = raw`; an injected
  value of `1.7` on a `[0, 1]` field remained `1.7` after a real tick.
- **Corrected behavior:** `dynamics.py:183-187` now lowers `none` through
  `{"clamp": [raw, field.minimum, field.maximum]}`. After the real
  `advance_world_tick`, the authoritative `session.state` value is `1.0`,
  `unclamped` is `1.7`, and `clamp_loss` is `-0.7`. The stale pre-tick dict
  remains `1.7` because Core copy-on-write replaces the entity, not because the
  formal dynamics result is stale.
- **Independent verification:** corrected test
  `gameplay_v04/tests/test_sandbox_independent_qa.py:239`
  (`NoRecoveryClampParityTests.test_out_of_range_none_state_is_clamped_by_formal_tick_and_reference`).

### [Resolved P2] Ecology now enforces the `none` zero-rate requirement

- **Location:** `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/ecology.py:204`
- **Related:** `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/content_compiler.py:95`
- **Expected:** `curve: "none"` requires `rate == 0.0`, matching
  `contracts.py:32` and `validate_curve_policy`.
- **Previous failure:** `parse_ecology_spec` accepted `curve="none"` with
  `rate=0.5` through a second, weaker policy.
- **Corrected behavior:** `ecology.py:205` and `content_compiler.py:95` reuse
  `validate_curve_policy`; a `none` baseline limit is now `0.0`. The independent
  test expecting rejection now passes.

### [Resolved P1] Tick-time forged Process rate is guarded

- **Location:** `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/processes.py:463`
- **Related:** `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/processes.py:687`
- **Expected:** The conversion quantity is positive and bounded by process
  `rate`, available inputs, free output capacity, and all declared
  coefficients; Stock remains finite, non-negative, and within capacity.
- **Previous failure:** After trusted start, changing only the formal
  `pmw_sandbox_process.rate` from `1.0` to `-1.0` and calling the real
  `advance_world_tick` changed feed Stock `4.0 -> 6.0` and product Stock
  `0.0 -> -3.0`.
- **Corrected behavior:** `processes.py:447-451` defines tick-time guards for
  positive rate `<= max_rate` and bounded Stock domains;
  `conversion_conditions` at `processes.py:495-510` requires those guards. The
  forged-rate counterexample now leaves both Stocks unchanged.
- **Independent verification:** independent test
  `gameplay_v04/tests/test_sandbox_independent_qa.py::ProcessForgedStateTests::test_tick_does_not_accept_forged_negative_rate`
  passes in the frozen Process run.

### [Resolved P1] Tick-time forged shared writer is guarded

- **Location:** `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/processes.py:411`
- **Related:** `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/processes.py:1008`
- **Expected:** At most one active Process writer may spend each Stock input;
  configured external Stock writers are excluded conservatively.
- **Previous failure:** After a trusted start, setting a second profile's state to
  `running` with a matching forged expiry event and calling
  `runtime.revalidate()` lets both conversion laws execute in the next real
  world tick. From `4.0` feed and a legal ratio of `3.0` output per `2.0`
  input, both profiles produced `6.0` total while spending each input unit
  once.
- **Corrected behavior:** `build_process_laws` derives every overlapping
  profile at `processes.py:364-375`; conflict bindings and identities are added
  at `processes.py:398-436`; conversion requires each peer state to be
  non-running at `processes.py:499-502`. The forged shared-writer
  counterexample now yields only one legal writer's output.
- **Independent verification:** independent test
  `gameplay_v04/tests/test_sandbox_independent_qa.py::ProcessForgedStateTests::test_tick_rejects_or_prevents_forged_shared_running_writer`
  passes in the frozen Process run.

### Pre-existing limitation, not a P1.1 regression

An ecology transition that changes only `baseline.curve` does not recompile the
Field's existing `FieldProfile`; subsequent ticks still execute the originally
compiled base variant. The independent ecology test at
`gameplay_v04/tests/test_sandbox_independent_qa.py:211` confirms the transition
commits, but diagnostics remain `linear`. The same limitation occurs when an
existing baseline changes from `linear` to `distance_squared`, so it predates
P1.1 and does not block this patch. Explicit curve overrides do work and are
covered separately.

### Process contract audit: valid construction and operations pass

The following checks used the real `advance_world_tick`; no test fabricates an
owner tick:

- **Genuine clock path:** `runtime.py:198-206` emits `WORLD_TICK_EVENT` with
  `source=pmw:v04:clock` and `payload={"step": next_step}`. Process Laws bind
  the clock, check `next_step`/`next_time`, and advance only after the clock Law
  completes.
- **Stoichiometric fuzz:** 80 randomized multi-input/multi-output conversions
  matched an independent Python oracle for all four ports, including
  near-zero floating boundaries and output-capacity saturation. No
  negative/overflow result occurred for valid controller-built profiles.
- **Atomic conversion:** one full output or one empty input prevented the
  entire conversion; feed, sibling output, and duration/progress state stayed
  unchanged.
- **Range/source/target/unit validation:** worker tests reject NaN/Inf/bool
  numbers, invalid units, missing Stock endpoints, reused Stock entities,
  wrong owner, and external writer conflicts before publication.
  `_validate_stock` enforces `0 <= amount <= capacity` for controller calls.
- **Staged rollback:** the worker activation-limit/shared-stock/external-writer
  test confirms rejection leaves `state.to_dict()` and revisions unchanged.
- **Expiry with missing stock:** the worker test confirms the process stops
  cleanly after output Stock deletion; expiry deliberately binds only the
  process component.
- **Pause/resume/deadline:** the worker tests and an additional independent
  probe confirm a paused process cannot resume after its hard deadline and
  cannot extend `remaining_ticks` beyond `max_duration_ticks` or the original
  deadline. Deadline-one ticks expire before conversion.
- **Final guard logic:** Process Laws derive all overlapping-profile identities
  at law-build time, bind those exact entities, and include a per-peer
  `state != running` condition in conversion. Rate is checked against
  `(0, max_rate]`; Stock amount/capacity are checked as finite, bounded,
  non-negative values with `amount <= capacity`. This closes same-input
  concurrent writers while avoiding a second scheduler or tick loop.
- **Guard scope limit:** these are bounded candidate checks, not full recovery
  from arbitrary corrupted duration/progress state. Controller-produced state
  remains within template limits, and forged rate/Stock/shared-writer cases
  are covered. Extreme malformed duration metadata is a trusted-state repair
  concern outside the P1.1 contract surface.

These passes establish that trusted Process construction and normal
controller-driven transitions are sound; they do not close the two
forged-candidate failures above.

### Alpha bounded authority review

The final Alpha changes are accepted within a bounded time/topology review:

- **Time:** `examples/pmw_alpha/session.py:93-98` uses each
  `spend_world_time` result's `tick.step` for log rows, and `_time()` at
  `session.py:271` reads `pmw_gameplay_clock.last_completed_step`. Public state,
  notes, travel logs, and multi-tick event rows therefore report completed
  world steps rather than `WorldState.tick` scheduler count.
- **Route authority:** `content.py:73-132` compiles route unlocks into event
  Laws that create a typed `adjacent` relation and set the actor's route flag
  only when the Area field threshold and route payload match. `_neighbors`
  reads actual relations rather than the flag; setting `lift_powered` alone
  does not authorize travel.
- **Restore:** `savegame.py:43` advances the schema to
  `pmw-alpha-save-v0.3`. `session.py:242-267` rejects missing/inconsistent
  canonical route relations and wrong type/source/target/component metadata.
  Save/load preserves real unlocked edges.
- **Independent evidence:** `examples/pmw_alpha/tests/test_sandbox_authority.py`
  seven tests pass in the final bounded regression, covering public time,
  scheduled roots, real lift/bridge edges, selector visibility, flag-only
  rejection, failure atomicity, save/load, and malformed-route restore
  rejection.

## Gate checks

### Passed

- **No Engine/tick fork:** the patch mutates `build_dynamics_laws` and
  `evaluate_field`; it does not create an alternate clock or scheduler. The
  independent clamp probe used the real `advance_world_tick`, which emits
  `source=clock_id` and `payload={"step": step}` at
  `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/runtime.py:206`.
- **Old curves unchanged:** an independent 5,000-case calculation against
  reconstructed baseline formulas found zero mismatches for `linear` and
  `distance_squared`, including source target/rate contributions and clamping.
- **Direct invalid Fields fail closed:** direct `FieldDefinition` construction
  plus `evaluate_field` rejected `none` rates of `0.1`, `-0.1`, `NaN`, `Inf`,
  and `True`; valid `none` with `0.0` returned the unchanged value with
  `effective_rate=0`.
- **Valid `none` holds:** repeated focused formal ticks held `0.8` with
  `effective_curve="none"` and `effective_rate=0`.
- **External impulses remain:** the implementation's
  `test_external_pmw_rule_impulse_survives_none_ticks` passed. A valid PMW law
  could change the value; subsequent no-recovery ticks preserved it.
- **Overrides and expiry:** an explicit `none` override held on its active tick;
  after expiry, the baseline `linear` curve resumed. Save, load, and continued
  replay produced equal final worlds.
- **Mana mirror:** the implementation's mana test passed, including the
  mirror write and formal dynamics law.

### Failed

- None in the final frozen scope.

Historical failures retained for audit:

- Formal `none` preserved unclamped state before the clamp repair.
- Ecology accepted a nonzero `none` rate before the shared policy repair.
- A forged non-positive Process rate created negative Stock before the
  tick-time rate/domain guard.
- Forged concurrent running Processes spent the same Stock before the
  conflicting-profile guard.

## Reproduction evidence

Focused no-recovery implementation tests:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -ra -p no:cacheprovider `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_no_recovery.py
```

Result after the clamp/ecology/content repair: **14 passed, 12 subtests passed
in 0.48s**.

Focused Process worker tests:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -ra -p no:cacheprovider `
  tests/test_sandbox_processes.py
```

Historical result before the final guard expansion: **10 passed in 0.24s**.
Frozen owner result after the final guard expansion: **11 passed**.

Independent focused tests:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -ra -p no:cacheprovider `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_independent_qa.py
```

Corrected no-recovery subset:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -ra -p no:cacheprovider `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_independent_qa.py `
  -k "none or clamp or ecology"
```

Result: **3 passed, 5 deselected in 0.38s**. No-recovery semantic assertions
(clamp, diagnostics, stale COW snapshot, policy, zero-rate, and frozen-profile
behavior) pass. The last full independent-module run before the correction was
**4 failed, 4 passed, 80 subtests passed in 1.12s**; its two no-recovery
failures are now resolved. Historical Process-only pre-repair status was not
accepted.

Frozen independent Process + independent QA run:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -ra -p no:cacheprovider `
  tests/test_sandbox_processes.py `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_independent_qa.py
```

Result: **19 passed, 80 subtests passed in 1.16s**. This is the current result:
11 root Process tests plus 8 independent QA tests. The forged-rate and forged
shared-writer failures no longer reproduce.

Frozen Alpha authority run:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -ra -p no:cacheprovider `
  examples/pmw_alpha/tests/test_sandbox_authority.py
```

Result: **7 passed, 5 subtests passed in 70.03s**.

## Cost-tool review

The available `tools/agent_cost_ledger.py` was reviewed within this bounded
scope. Its focused tests pass:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -ra -p no:cacheprovider tests/test_agent_cost_ledger.py
```

Main's final focused ledger result: **17 passed**. Independent review found no
blocking issue in the reviewed paths:
usage values fail closed, input cache is an explicit 97% assumption while
cumulative fields are ignored, reasoning is not added to output, selected
sources are deduplicated by response identity, and incomplete accounting
fails budget gates closed.

## Limitations

- The earlier combined run that hit the transient undefined
  `valid_duration` NameError is retained only as process evidence; it is not a
  current test result. The Process source changed after that run and the final
  frozen rerun is green.
- Main's final combined regression was still running when this QA scope was
  frozen. Therefore this report does not claim its total. The authoritative
  QA-owned result is the frozen 36-top-level-test run below (Process 11 +
  independent QA 8 + ledger 17), plus the Alpha authority run.
- Tick guards are deliberately bounded: rate `(0, max_rate]`, Stock
  `[0, 1e12]` with `amount <= capacity`, and normal controller-produced
  duration arithmetic. Arbitrary inconsistent duration/progress corruption is
  a trusted-state recovery concern outside this P1.1 patch, not a legal input.
- The ecology baseline curve transition still does not recompile an already
  frozen `FieldProfile`; this predates P1.1 and is documented above.
- The implementation worker's 186-passed Gameplay suite was not repeated here.
  The bounded frozen regression is authoritative for this sidecar QA.
- No implementation files were modified by independent QA. QA owns only this
  report, the independent QA test, and evidence files.

## Fixed source and test files reviewed

- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/dynamics.py`
- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/contracts.py`
- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/ecology.py`
- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/content_compiler.py`
- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/processes.py`
- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/blueprints.py`
- `examples/pmw_alpha/content.py`
- `examples/pmw_alpha/session.py`
- `examples/pmw_alpha/savegame.py`
- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_no_recovery.py`
- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_independent_qa.py`
- `tests/test_sandbox_processes.py`
- `tests/test_agent_cost_ledger.py`
- `examples/pmw_alpha/tests/test_sandbox_authority.py`

## Final frozen evidence

QA-owned final result: **36 passed, 80 subtests**, composed of:

- `tests/test_sandbox_processes.py`: 11 passed
- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_independent_qa.py`: 8 passed, 80 subtests
- `tests/test_agent_cost_ledger.py`: 17 passed (Main's focused run)
- `examples/pmw_alpha/tests/test_sandbox_authority.py`: 7 passed, 5 subtests
  (separate bounded Alpha run)

The report verdict is **ACCEPT for the frozen QA scope**. The initial failure
record above is retained as history, not as a current failure.
