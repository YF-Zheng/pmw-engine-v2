# PMW v0.4 Gate 0 Report

Status: `DONE` for G0.01-G0.03 implementation and v0.6 regression. This report
does not freeze a benchmark or authorize TODO2 collection.

## Environment and baseline

- Repository baseline: `a98ff51561760f87689093c815508fa93120807d`.
- Branch used by the integration owner: `feature/pmw-v04-gameplay-foundations`.
- PMW Core was not modified.
- CPython 3.10.12 (`/usr/bin/python3`) and managed CPython 3.13.13 were both
  used for the final v0.6 suite.
- The collaboration API exposed agent creation but no model or reasoning-effort
  selector. The Role A model configuration is therefore `unverified`; this
  report does not claim Luna High.

## G0.01 Compound activation atomicity

The pre-fix reproduction compiled one instant impulse and one permanent
attractor modifier into one mechanism. The first activation changed the field
from `0.8` to `0.6000000000000001` and occupied its permanent slot. A second
activation returned `changed=True`, triggered only the impulse Law, and changed
the field to `0.4000000000000001`. The occupied modifier Law silently did not
match. This was a required-operator partial activation.

The compiler now emits a deterministic `activation_requirements` manifest for
every mechanism instance. The optional operator field `commitment` is a strict
`required|conditional` enum and defaults to `required`, so all existing v0.6
documents retain their behavior. Before `runtime.run_event`, the trusted
execution adapter checks every required state handle, contribution slot,
Process start state, Relation existence/absence, Relation endpoint, and the
existing pending-handle guard. Any failed required member raises
`ExecutionContractError` before PMW receives the event. Consequently the
formal WorldState, Scheduler queue, tick counters, and trace production remain
unchanged on rejection.

An explicitly `conditional` operator is omitted from the mechanism-level
preflight and keeps its own Law conditions. A regression activates a required
impulse plus conditional permanent attractor twice: on the second activation
the occupied attractor naturally skips while the impulse runs. Unknown
commitment values fail closed during validation.

Regression coverage includes the required instant-plus-permanent reproduction
and the existing staggered-expiry contract: after one of two timed operators
expires naturally, cancellation still removes only the remaining live handle
and leaves both slots inactive.

The preflight is intentionally a trusted read-only adapter because PMW event
Law matching does not itself report that one member of a compound activation
failed to match. PMW remains the only writer of authoritative world state.

## G0.02 Normalized Dynamics domain

The pre-fix catalog validator accepted a dynamic Field with domain `[0,2]` and
initial value `1.5`, while the generated COMMIT Law clamped it to `[0,1]`. One
tick changed the otherwise stationary value from `1.5` to `1.0` and recorded
`clamp_loss=-0.5`.

Catalog validation now rejects every Field with normalized Dynamics unless its
declared domain is exactly `[0,1]`, using `DYNAMICS_DOMAIN_MISMATCH`. A Field
without normalized Dynamics may retain any finite ordered declared domain; a
`[-10,50]` regression proves that distinction.

Gate 1 may introduce a separate domain-aware Dynamics definition, but it must
carry its bounds through validation, formulas, and generated clamps. It must
not weaken this legacy unit-domain contract implicitly.

## G0.03 Demo semantic and byte contracts

The previous checked-result test used exact Python float equality, while its
same-run determinism test compared re-serialized in-memory summaries rather
than every emitted file. These are now separate contracts:

1. Every checked-in full Demo result and summary is compared recursively for
   exact structure and non-float values, with absolute float tolerance `1e-12`.
   This includes Event, Delta, Trace, WorldState, and trajectory data.
2. Two independent rebuild directories produced by the same interpreter are
   compared byte-for-byte for all six JSON files.

Observed interpreter scope is explicit:

- CPython 3.10.12 rebuilds all six checked-in files byte-identically.
- CPython 3.13.13 differs from the checked-in bytes for four detailed Demos and
  the summary; `relation_propagation.json` remains identical. Differences are
  floating-point results between `2.7755575615628914e-17` and
  `1.1102230246251565e-16` (for example `0.71` versus
  `0.7100000000000001`). Full structural/semantic comparison passes at
  `1e-12`, and two CPython 3.13.13 rebuilds are byte-identical to each other.

No cross-version byte-identity claim is made.

## Tests and logs

Commands:

```text
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/tests -v
PYTHONPATH=src:. python3.13 -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/tests -v
```

Results:

- CPython 3.10.12: `170/170`, 0 failures, 0 skips, 0 expected failures,
  unittest time `25.545 s`.
- CPython 3.13.13: `170/170`, 0 failures, 0 skips, 0 expected failures,
  unittest time `20.831 s`.
- CPython 3.10 log: `/tmp/pmw_v04_gate0_v06_310.log`, SHA-256
  `d7096ba115827e821702702d749065bb296c1fb0c3c11a7abeddbfea51350bd5`.
- CPython 3.13 log: `/tmp/pmw_v04_gate0_v06_313.log`, SHA-256
  `879d8a4aa0c7fe20903648c7f5fa63dc2811b1c9dfb21e430cca1943acafacaf`.

## Remaining boundary

- Existing v0.6 documents remain backward compatible because omitted
  `commitment` means `required`; only an explicit `conditional` opts into
  natural per-Law skipping.
- This Gate does not implement Blueprint/Instance, Area/Actor, new Dynamics
  curves, gameplay actions, or AI.
- Core and old GM compatibility suites are integration-owner Gate 0/Gate 5
  responsibilities and are not claimed by this role's v0.6-only run.

## G0.04 Integration-owner compatibility

After reviewing the production diff and the new regressions, the integration
owner reran all three suites on CPython 3.10.12:

- PMW Core: `254/254` in 26.018 s.
- Pre-v0.6 Generative Mechanics: `345/345` in 69.252 s.
- v0.6 TODO1 including Gate 0: `170/170` in 25.611 s.
- Failures, skips, expected failures: `0/0/0`.

The change set is confined to `next_tracks_v06`; PMW Core and frozen research
assets have no tracked modification. The explicitly defined protected-path
manifest and digest are recorded in `gameplay_v04/BASELINE_REPORT.md` and will
be recomputed at Gate 5.
