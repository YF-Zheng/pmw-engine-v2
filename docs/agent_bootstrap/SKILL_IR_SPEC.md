# Skill IR v1: Requirements And Status

P2 specification draft, not an implemented or accepted v1 language.

Existing v06 `MechanismSpec` supports an operator sequence and catalog scope,
but not the complete player action contract. Existing Gameplay `SkillBlueprint`
supports costs/materials/conditions/registry hashes but restricts effects and
uses one trigger per blueprint. Neither alone satisfies the new contract.

The v1 IR must join their capabilities WITHOUT accepting arbitrary code or
raw PMW Law bundles from a model. Required groups: Identity, Origin,
Capability, Targeting, Costs, Triggers, Conditions, Effects, Lifecycle,
Limits, Display. The canonical document includes IR/catalog versions and a
content hash; stored compiled definitions are validated on load without API.

Selectors include self, selected actor/object, current area, and bounded
matching actor/object/process/relation sets. Cross-area scope requires trusted
capabilities; a model-authored area ID grants no authority. Conditions are pure
typed comparisons/ranges/trait/discrete/process/relation/event matches with
AND/OR/NOT and bounded continuity; query and expression depth are limited.

Triggers include on_use/on_tick/on_event/on_expire and condition edges. Each
event has a causal parent and deduplication key; global per-tick and per-root
budgets prevent passive recursion. Ordered/dependency-linked effects lower to
the seven trusted operators. All costs and world steps are settled in the same
staged Gameplay transaction, never in a provider request.

Acceptance is thirty reference skills through one compiler/runtime plus
permission, budget, expiry, cross-area, save/load and replay tests. No such
acceptance is claimed by this draft.
