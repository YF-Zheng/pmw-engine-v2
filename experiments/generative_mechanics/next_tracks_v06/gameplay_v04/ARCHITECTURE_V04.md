# Gameplay v0.4 Shared Architecture

Status: Gate 1 shared contract. Later gates may extend this contract without
weakening its validation, ownership, or PMW-authority rules.

## Authority and layers

PMW `WorldState` is the only authoritative runtime state. Blueprint, template,
and registry objects are immutable definitions. Trusted adapters may validate,
resolve authorized selectors, and construct Events; only PMW Laws commit world
changes and produce `StateDelta` and `CausalTrace`.

The gameplay package is layered as follows:

1. Gate 1: contracts, Blueprint/Instance, scope resolution, Area/Actor state,
   dynamics composition, and clock boundary events.
2. Gate 2: conditions, attributes, effects, statuses, hooks, actions, combat,
   and the three base actions.
3. Gate 3: weather, ecology, harvest, materials, skills, loadouts, explanations,
   and the runtime registry/checkpoint envelope.
4. Gate 4: legal actions, observation, sandbox simulation, build analysis, and
   bounded AI planning.

No layer owns a private mutable copy of Actor, Area, resource, status, or
weather state.

## Blueprint and instance identity

`AreaBlueprint` and `ActorBlueprint` carry logical definitions. Instantiation
requires compiler-owned instance IDs and creates independent PMW Entities. Two
instances of one Blueprint never share components or contribution slots.

Player and monster instances use the same Actor component and resolution path.
Only controller metadata, values, traits, and build differ. Controller metadata
grants no write capability.

## Scoped selectors

The only target selectors are `self`, `target_actor`, `current_area`,
`linked_object`, and `adjacent_area`. Resolution starts from an action context,
uses explicit PMW Relations, and checks a capability allowlist. It never accepts
an arbitrary component path or world object ID supplied as a replacement for a
selector.

`located_in`, `adjacent`, and `linked` Relations are authoritative. Areas do
not exchange fields merely because they share a Blueprint or receive one tick.

## Dynamics

Every dynamic field declares a finite domain, current value, baseline target,
rate, and curve. Supported curves are:

```text
linear:           delta = rate * (target - x)
distance_squared: delta = rate * (target - x) * abs(target - x)
```

For a domain of width `D`, linear requires `0 <= rate <= 1`; distance-squared
requires `0 <= rate * D <= 1`. These bounds guarantee that an unforced update
approaches but does not cross the target.

Sources have three layers: one Blueprint/ecology baseline, bounded removable
persistent patches, and bounded removable temporary modifiers. Target sources
use non-negative normalized weights. Rate composition is `(base + sum(add)) *
product(multiplier)`, followed by the active curve's stable-rate clamp. Curve
overrides use explicit priority; two live overrides at one priority are invalid.
Every source records source ID and owner, and removal affects only that source.

Each world tick is one explicit PMW Event. Laws read one pre-event snapshot and
write current value plus diagnostics. `world_tick`, `combat_round`, and
`owner_turn` are separate semantic clocks. Gate 1 advances only `world_tick`;
combat later emits exactly one world tick after a complete round.

## Downstream contracts

Controllers will submit minimal `ActionRequest` objects. Trusted registered
definitions will provide costs and effects. Gate 2 must aggregate required
effects and costs into one root action transaction; conditional hooks are
bounded follow-ups. Gate 3 consumes Gate 2's effect and condition types rather
than defining alternatives. Gate 4 can choose only from generated legal actions
and receives only actor-safe observations.
