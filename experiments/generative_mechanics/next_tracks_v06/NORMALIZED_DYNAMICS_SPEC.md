# Normalized Dynamics v0.6

Status: TODO1 implementation contract. This document does not freeze a future
benchmark and does not alter PMW Core semantics.

## State and formula

Every normalized field has `x in [0, 1]`, a base attractor `a0 in [0, 1]`, a
strictly positive base weight `w0`, and `alpha0 in [0, 1]`. Catalog-bounded
slots contribute attractors, alpha deltas, and drives:

```text
A = (w0*a0 + sum(ws*as)) / (w0 + sum(ws))
alpha = clamp(alpha0 + sum(delta_alpha_s), 0, 1)
drive = clamp(sum(drive_s), -drive_limit, drive_limit)
coupling_i = sum(k_e * (x_j - x_i))
u = x + alpha*(A-x) + drive + coupling
x_next = clamp(u, 0, 1)
```

All numeric inputs are finite and booleans are not numbers. Modifier weights
and conductivities are non-negative. The base weight prevents division by
zero. Inputs, slots, profiles, relations, and generated laws are sorted by
stable identifiers. Identical data therefore do not depend on mapping,
installation, or law-loading order.

Clamping is a declared boundary correction rather than conservation. Each
commit records the unclamped value and signed `clamp_loss = x_next-u`; two
mechanisms which saturate at the same boundary can still be distinguished.
For symmetric coupling without intrinsic terms or boundary saturation, the two
endpoint changes are equal and opposite. A profile that requires convex,
non-oscillatory diffusion must additionally enforce incident `sum(k) <= 1`.

## PMW representation

The public component roots are:

```text
gm_v06_dynamics
gm_v06_coupling
gm_v06_clock
```

`gm_v06_dynamics` contains `value`, base parameters, `drive_limit`, fixed slot
maps, `scratch.{intrinsic,coupling}`, and diagnostics. Inactive slots retain
their owner but contribute numeric zero. Slot allocation and ownership belong
to the catalog/compiler; the law builder only expands an already allocated,
bounded list.

`gm_v06_coupling` lives on a PMW Relation. Its effective conductivity is the
base value plus fixed modifier slots, clamped to `[0,1]`. Relation existence
therefore controls whether its join law contributes at all. Both endpoint
effects read the same event snapshot.

## Three-phase tick

A physical tick is one root `gm.v06.dynamics.tick` event with two immediate
derived events:

1. **PREPARE** uniquely sets both scratch accumulators to zero.
2. **ACCUMULATE** emits only `delta` proposals to scratch. Intrinsic and all
   relation coupling contributions are deterministically aggregated by PMW.
3. **COMMIT** uniquely sets the bounded current value and diagnostics.

This staging is required. A base `set` combined with coupling `delta` would be
a PMW proposal conflict. Writing deltas directly to the real field and using a
later state law to clamp would expose an out-of-domain intermediate state to
state closure and trace consumers. Scratch is ordinary auditable PMW state;
there is no Python physics mutation.

The root tick time must equal `WorldRuntime.state.sim_time`. Otherwise PMW
correctly treats a later derived event as scheduled future work. The execution
protocol enforces equality with `gm_v06_clock.next_time` and an exact integer
step token, preventing duplicate ticks.

For physical step `t`:

1. `runtime.advance_to(t)` dispatches every scheduled event due at or before
   `t`, including modifier expiry.
2. The dynamics root event runs PREPARE, ACCUMULATE, COMMIT and their normal
   PMW state closures.
3. One `gm.v06.world.step` event runs against the updated fields.
4. A canonical snapshot is taken.

`WorldState.tick` counts Scheduler dispatches and is not physical time. The
v0.6 clock is authoritative. A timed lifecycle uses positive integer steps;
permanent is explicit and there is no ambiguous duration zero. Expiry clears
only its owner's slot and never restores or rolls back the current field.

## Reference model

`dynamics/reference.py` is a pure, PMW-independent oracle. It validates and
sorts its own inputs and computes simultaneous network steps from an immutable
snapshot. It intentionally shares no expression-building code with the PMW law
builder. Differential tests compare values and every diagnostic, then separately
check PMW events, deltas, clock advancement, relation activation, and temporal
lifecycle.

## Declared Core boundaries

PMW has no dynamic reduction, conditional value expression, dynamic slot
allocator, string concatenation, or native normalized-field type. v0.6 uses
strict external validation, statically bounded slots, and fully expanded PMW
expression trees. Scheduler and lifecycle operations remain event-law-only.
These are documented modeling constraints, not silent Core extensions.
