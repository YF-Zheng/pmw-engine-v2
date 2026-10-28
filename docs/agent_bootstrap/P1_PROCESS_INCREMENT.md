# P1.2 Stock Conversion Process Increment

Date: 2026-10-28  
Scope: bounded sidecar only; no Engine, Gameplay runtime, curve, Alpha, or cost-tool changes.

## Delivered Surface

`experiments/generative_mechanics/next_tracks_v06/gameplay_v04/processes.py` provides:

- Typed `StockRef`, `StockBinding`, `ConversionPort`, `ProcessTemplate`, `ProcessProfile`, `ProcessLimits`, and `ProcessController`.
- Detached constructors `stock_entity()`, `stock_component()`, and `instantiate_process()`.
- Data-only template lowering through `build_process_laws()` into event Laws on the existing `WORLD_TICK_EVENT`.
- Trusted start, modify, pause, and resume commands routed through staged Gameplay sessions and formal PMW events.
- An expiry event that owns and clears its scheduler handle without requiring its Stock entities to survive.
- Independent registered-instance and active-instance limits.

No simulator, second tick, arbitrary Python evaluation, Law text from a candidate, direct authoritative component write, or dynamic catalog editing is provided.

## Execution Contract

For a conversion step, the trusted event proposes all writes together:

```text
q = min(rate, each input amount / input coefficient,
        each output free capacity / output coefficient)
```

Every input loses `q * input_coefficient`; every output gains
`q * output_coefficient` in the same PMW commit batch. Clamped arithmetic must
not be used to hide a negative balance; preflight rejects invalid, missing, or
unit-mismatched Stock before activation. The converter also rejects an empty
input at start/resume, an overlapping or duplicate Stock endpoint, a wrong
owner, a profile/hash mismatch, and an unauthorized profile.

A fully empty input pauses a running Process with
`last_failure="insufficient_input"` and clears its expiry handle. A
capacity-saturated output loses nothing and does not claim conversion progress;
the Process marks the step to prevent duplicate execution and remains running.

Low-level saved or legacy Process/Stock data is not trusted merely because it
passed WorldState validation. Conversion, saturation, and shortage tick Laws
recheck Process rate bounds and Stock amount/capacity domains before arithmetic.
An out-of-domain Process or Stock therefore no-ops for that tick; it does not
reverse the conversion direction, create Stock, or admit non-finite values.
The DSL treats booleans as Python numbers, so boolean discrimination is not
claimed as a generic type guard; the bounded numerical window is used only to
reject out-of-domain numbers and never lowers the 80-case arithmetic oracle's
tolerance.

## Time and Lifecycle Semantics

- Duration is half-open `[start, start + duration_ticks)`.
- At time `T`, the existing runtime dispatches due scheduled events before the
  `WORLD_TICK_EVENT` at `T`. Expiry therefore stops a Process before dynamics
  settle at that same boundary.
- Consequently, `duration_ticks=1` produces zero conversion ticks.
- `last_step` prevents the same Process from converting twice for one step.
- Start and modification require a completed gameplay Tick boundary.
- Rate and remaining duration are editable through formal modify events.
- Repeated duration edits cannot extend the stored hard deadline, which is
  fixed from the trusted template maximum at first start.
- Pause cancels the expiry handle and converts the scheduled deadline into
  remaining whole ticks. Resume schedules a new expiry no later than the
  original hard deadline.

## Trust and Conflict Boundary

Profiles are preallocated trusted content for this increment. The controller
validates source ownership against the profile owner and validates all numeric
values as finite, non-boolean values within fixed bounds. It verifies Stock
shape as exactly `components.stock = {amount, capacity, unit}` and requires
each endpoint's unit to match its declared port.

Activation, resume, and modification conservatively reject:

- a configured `external_stock_writers` entry for any participating Stock;
- any unknown running Process writer in the world;
- another registered running Profile that shares a participating Stock.

This prevents PMW set/delta writers from unknowingly overdrawing the same
Stock. Precisely identifying every Alpha inventory/world writer would require
an authority registry integrated into Alpha; that registry is not present and
is not claimed here.

The lowered conversion Laws also bind the exact registered peer Process
entities that share any Stock endpoint. If two such registered instances are
present as running in a loaded or forged state, both conversion branches are
vetoed for that Tick rather than allowing set writes to double-spend one input.
An unregistered forged Process outside the controller's Law configuration has
no generated conversion route and remains outside this guard.

Detached constructors may attach or load trusted Stock and Process entities,
but they do not mutate an active authority. Live writes occur only through
PMW events.

## Bridge Gaps

- Alpha inventory remains a separate Area-local Stock dictionary; conversion
  does not bridge Alpha harvest/material inventory to entity Stock.
- Alpha's route flags and other existing world writers are not enrolled in a
  shared writer-authority registry. Callers must configure known writers in
  `external_stock_writers`; unknown writers that do not expose a Process
  component cannot be detected generically.
- Registered shared-Process conflicts are guarded by lowering; unregistered
  forged Process entities are outside the generated Law route and are not
  claimed as an authority-registry integration.
- Profiles are static at construction. There is no dynamic catalog edit or
  generated-template registration in this increment.
- The sidecar does not alter `WORLD_TICK_EVENT`, the Engine, or the canonical
  Gameplay curve implementation.
- Save/load restores Process state, expiry scheduler events, and deterministic
  continuation only when the same trusted profiles and Laws are supplied again.

## Verification

Focused suite:

```text
python -m pytest -q tests/test_sandbox_processes.py
...........                                                              [100%]
11 passed

python -m pytest -q \
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_independent_qa.py \
  -k Process
.....                                                                    [100%]
5 passed, 3 deselected, 80 subtests passed
```

The same suite also passes through `python -m unittest -q
tests.test_sandbox_processes`. Tests use `build_runtime()` and
`build_process_laws()` with the real gameplay clock and
`advance_world_tick()`. They cover two profiles compiled from one generic
template, one-batch ratios/conservation, shortage and saturation, rate and
duration modification, pause/resume, expiry ordering, duration-one behavior,
invalid input, source authority, duplicate-step guarding, competing active
resources, rollback of state/revisions, and save/load replay.
The independent 80-case stoichiometric oracle passes unchanged, including its
`1e-9 * max(1, |expected|)` tolerance; no rounding-loss allowance was added.
