# Object Model v0.6

The trusted catalog exposes six strict object variants. Generated documents can
name catalog IDs but cannot supply PMW paths or grant capabilities.

## Objects

- **Field**: bounded continuous state with optional normalized dynamics. Its
  current value, base attractor/alpha, and finite contribution slots are backed
  by an Entity component.
- **Stock**: an amount, capacity, unit, and bounded-flow policy. Conserved
  transfer uses one PMW expression for paired negative/positive deltas. Explicit
  sources and sinks require separate privileges.
- **Process**: an Entity with a real running state, source/target declarations,
  base parameters, and additive modifier slots. World-step laws consume it.
- **Relation**: an existing PMW Relation or an allowlisted template. Relation
  lifecycle changes the topology matched by later world laws.
- **Discrete**: a finite enum and allowlisted transition graph. Generated
  operators cannot write it arbitrarily; trusted process/world laws transition it.
- **Derived**: a read-only value produced by named PMW state laws. Every direct
  generated write is rejected as `DERIVED_READ_ONLY`.

Each state reference is a typed `{kind, object_id, path, value_type}` value found
only in the trusted catalog. Unknown fields, objects, slots, endpoints, domains,
and duplicate IDs fail closed. Numeric values reject booleans and non-finite
numbers.

## Ownership

World-owned objects require explicit privileges for destructive or persistent
operations. Artifact-owned Relation IDs, event types, Law IDs, effect-slot
owners, and temporal handles are compiler-derived. A reservation is unique to
`(target, artifact, operator, instance)`; capacity exhaustion is an error rather
than an overwrite.

The checked-in Thermal/Fluid, Electric/Network, and Mechanical/Structural
catalogs collectively instantiate every object type.
