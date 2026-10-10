# Operator Semantics v0.6

All seven operators have strict parameters, catalog capability checks, PMW Law
lowering, and lifecycle semantics.

1. `impulse`: an instant bounded write to a Field or authorized Stock. It does
   not alter future dynamics, so the next tick resumes the base trajectory.
2. `drive`: a timed/permanent contribution slot. Field drives enter every
   normalized tick. Stock source/sink laws account for bounded flow; transfer
   emits paired deltas using `min(rate, source, destination free capacity)`.
3. `attractor_modifier`: contributes a target and non-negative weight without
   writing current state. Multiple slots use normalized weighted combination.
4. `dynamics_modifier`: contributes alpha or Relation conductivity delta. It
   changes response or coupling without specifying a final state.
5. `process_start`: writes the real Process running state; a timed expiry stops
   it and ordinary world-step laws produce its downstream effects.
6. `process_modify`: contributes to an allowlisted Process parameter slot.
   Expiry removes only that contribution.
7. `relation_modifier`: creates/deletes a real PMW Relation or modifies an
   allowlisted parameter slot. Subsequent relation joins observe the topology.

Lifecycle is exactly `instant`, `timed(steps >= 1)`, or `permanent`. Permanent
effects require a capability privilege. Timed activation schedules a compiler-
namespaced per-instance handle; expiry clears only its owned slot or lifecycle
object, never rolls current Field state back. The trusted execution harness
validates the complete activation payload and handle namespace before PMW runs.
An instance with any pending timed operator cannot be activated again. Operators
from one activation may expire independently; explicit cancellation removes only
the still-pending operators from that activation and rejects unknown or stale
activation IDs. This prevents mixed activation ownership while allowing a
partially expired activation to be cancelled safely.

Operator lowering is pure: it builds validated Law data and never performs a
world effect. Runtime changes are visible as PMW proposals, deltas, scheduler
records, and causal traces.
