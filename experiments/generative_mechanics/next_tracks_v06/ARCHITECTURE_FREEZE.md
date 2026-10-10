# TODO1 Shared Architecture Freeze

Status: interface-frozen implementation candidate. This is not a frozen benchmark.

## Safety boundary

Generated `MechanismSpec` documents name only trusted catalog objects and
capabilities. They cannot contain PMW paths, laws, Python expressions, scheduler
IDs, or privileges. The validator resolves raw data to typed IR; the compiler
accepts typed IR only. Generated state changes are executed by PMW laws and the
resolver.

## Pipeline

```text
strict MechanismSpec v0.6
  -> catalog/capability validation and deterministic slot allocation
  -> immutable MechanismIR
  -> deterministic PMW law lowering and parse_law validation
  -> CompiledMechanism
  -> build one Engine from world laws plus all compiled artifacts
  -> activate and step through WorldRuntime
```

## Normalized dynamics

For a normalized field `x`:

```text
a_eff = (w_base*a_base + sum(w_i*a_i)) / (w_base + sum(w_i))
alpha_eff = clamp(alpha_base + sum(alpha_delta_i), 0, 1)
drive_eff = clamp(sum(drive_i), -drive_limit, drive_limit)
x_next = clamp(x + alpha_eff*(a_eff-x) + drive_eff + coupling, 0, 1)
```

`w_base > 0`; modifier weights are non-negative. Slots are declared by the
catalog and allocated by `(target, artifact, operator, instance)`. Expiry clears
only its owner's contribution and never rolls back `x`.

Each physical integer step first dispatches scheduled events due at that time,
then runs exactly one namespaced dynamics tick, then one world-step event, and
finally records a canonical snapshot. Physical steps are not state-law fixed
point iterations.

Coupling is lowered to relation-join laws. Both endpoint deltas read the same
pre-event snapshot and use opposite signs. No Python world scan performs
physics. Bounds are enforced by traced PMW closure.

## Lifecycle

Lifecycle is a strict tagged union:

```text
instant
timed(steps >= 1)
permanent
```

There is no ambiguous numeric duration zero. A permanent effect requires an
explicit capability. Handles, event types, relation IDs, and law IDs are
compiler-derived namespaces. Active instance slots and handles are never shared.

## File ownership during implementation

- Role A: `dynamics/**`, `NORMALIZED_DYNAMICS_SPEC.md`, dynamics/differential tests.
- Role B: `spec.py`, `validator.py`, `canonical.py`, catalogs, object/operator docs,
  validator/operator tests.
- Role C: `compiler.py`, `execution.py`, `worlds/**`, `demos/**`, integration tests.
- Role D: read-mostly independent adversarial QA, locality, compatibility, and
  reproduction evidence after A/B/C integration.
- Primary agent: this contract, cross-module integration, reports, Git, final tests.

## Non-goals

No Core changes, Law hot-install, TODO2 goal benchmark, formal model request, or
reinterpretation of the frozen v0.2/v0.3/v0.5 experiments is permitted.
