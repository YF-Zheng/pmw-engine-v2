"""Lower trusted Action definitions into PMW event Laws."""

from __future__ import annotations

from typing import Any, Iterable

from .actions import ACTION_EVENT, ACTOR_COMPONENT, ActionRegistry
from .contracts import GameplayContractError
from .runtime import GameplaySession, build_runtime
from .status import DurationSpec, STATUS_CANCEL_EVENT, STATUS_COMPONENT, StatusSpec, neutral_status_slot


def build_action_laws(registry: ActionRegistry, *, status_slots: int = 8, dynamics_slots: int = 4) -> tuple[dict, ...]:
    if isinstance(status_slots, bool) or not isinstance(status_slots, int) or not 1 <= status_slots <= 32:
        raise GameplayContractError("status_slots must be in [1, 32]")
    if isinstance(dynamics_slots, bool) or not isinstance(dynamics_slots, int) or not 1 <= dynamics_slots <= 32:
        raise GameplayContractError("dynamics_slots must be in [1, 32]")
    laws: list[dict] = []
    for action in registry.actions.values():
        action_token = _action_token(action)
        common = [
            {"event.type": {"eq": ACTION_EVENT}},
            {"ref": "$event.payload.action_id", "eq": action.id},
            {"ref": "$event.payload.action_hash", "eq": action.canonical_hash},
        ]
        base_id = f"pmw.v04.action.{action_token}.cost"
        laws.append({"id": base_id, "mode": "event", "priority": 100,
                     "bindings": {"actor": {"kind": "entity", "requires": [ACTOR_COMPONENT]}},
                     "when": {"all": [*common, {"ref": "$event.payload.execution_kind", "eq": "primary"},
                                        {"ref": "$actor.id", "eq": "$event.source"}]},
                     "effects": [
                         {"op": "set", "target": f"$actor.{ACTOR_COMPONENT}.mana", "value": "$event.payload.actor_mana"},
                         {"op": "set", "target": f"$actor.{ACTOR_COMPONENT}.last_action_duration", "value": "$event.payload.action_duration"},
                     ]})
        laws.append({"id": f"{base_id}.mana_mirror", "mode": "event", "priority": 100,
                     "bindings": {"actor": {"kind": "entity", "requires": [ACTOR_COMPONENT, "pmw_gameplay_dynamics"]}},
                     "when": {"all": [*common, {"ref": "$event.payload.execution_kind", "eq": "primary"},
                                        {"ref": "$actor.id", "eq": "$event.source"}]},
                     "effects": [{"op": "set", "target": "$actor.pmw_gameplay_dynamics.fields.mana.value",
                                  "value": "$event.payload.actor_mana"}]})
        for effect in action.effects:
            laws.extend(_effect_laws(action.id, action.version, action.canonical_hash, effect,
                                     status_slots, dynamics_slots))
    for hook in registry.hooks.values():
        laws.append({"id": f"pmw.v04.hook.{hook.id}.cooldown", "mode": "event", "priority": 100,
                     "bindings": {"actor": {"kind": "entity", "requires": [ACTOR_COMPONENT]}},
                     "when": {"all": [{"event.type": {"eq": ACTION_EVENT}},
                                        {"ref": "$event.payload.execution_kind", "eq": "hook"},
                                        {"ref": "$event.payload.hook.hook_id", "eq": hook.id},
                                        {"ref": "$actor.id", "eq": "$event.source"}]},
                     "effects": [{"op": "set", "target": f"$actor.pmw_gameplay_hooks.cooldowns.{hook.id}",
                                  "value": "$event.payload.hook.cooldown_until"}]})
    status_specs = list(registry.statuses.values())
    seen = {item.id for item in status_specs}
    for action in registry.actions.values():
        for effect in action.effects:
            if effect.kind == "grant_trait" and f"trait_{effect.trait_id}" not in seen:
                spec = StatusSpec(f"trait_{effect.trait_id}", 1, "buff", 1, "refresh",
                                  DurationSpec("owner_turn", effect.duration), (effect.trait_id,), None, None,
                                  f"trait:{effect.trait_id}")
                status_specs.append(spec); seen.add(spec.id)
    laws.extend(_status_clock_laws(status_specs, status_slots))
    return tuple(sorted(laws, key=lambda row: row["id"]))


def build_action_session(world, profiles: Iterable = (), registry: ActionRegistry | None = None) -> GameplaySession:
    if registry is None: raise GameplayContractError("ActionRegistry is required")
    profiles = tuple(profiles)
    dynamics_slots = max((item.field.max_temporary_modifiers for item in profiles), default=1)
    return build_runtime(world, profiles, build_action_laws(registry, dynamics_slots=dynamics_slots))


def _action_token(action):
    return f"{action.id}.v{action.version}.{action.canonical_hash[:12]}"


def _effect_laws(action_id, action_version, action_hash, effect, status_slots, dynamics_slots):
    token = f"{action_id}.v{action_version}.{action_hash[:12]}"
    prefix = f"pmw.v04.action.{token}.effect.{effect.id}"
    common = [
        {"event.type": {"eq": ACTION_EVENT}}, {"ref": "$event.payload.action_id", "eq": action_id},
        {"ref": "$event.payload.action_hash", "eq": action_hash},
        {"ref": f"$event.payload.effects.{effect.id}.status", "eq": "applied"},
    ]
    binding, identity = _binding(effect.target.kind)
    conditions = [*common, {"ref": f"${binding}.id", "eq": f"$event.payload.effects.{effect.id}.target_id"}]
    value_root = f"$event.payload.effects.{effect.id}.values"
    actor_paths = {
        "damage": ("hp", "shield"), "heal": ("hp",), "shield": ("shield",),
        "add_resource": (effect.resource,),
    }
    if effect.kind in actor_paths:
        if effect.kind == "add_resource" and effect.resource == "mana" and effect.target.kind == "self":
            hook_conditions = [*conditions, {"ref": "$event.payload.execution_kind", "eq": "hook"}]
            result = [{"id": f"{prefix}.hook", "mode": "event", "priority": 100, "bindings": identity,
                       "when": {"all": hook_conditions}, "effects": [{"op": "set",
                           "target": f"${binding}.{ACTOR_COMPONENT}.mana", "value": f"{value_root}.mana"}]}]
            mirror_identity = {binding: {"kind": "entity", "requires": [ACTOR_COMPONENT, "pmw_gameplay_dynamics"]}}
            result.append({"id": f"{prefix}.hook.mana_mirror", "mode": "event", "priority": 100,
                           "bindings": mirror_identity, "when": {"all": hook_conditions}, "effects": [{"op": "set",
                               "target": f"${binding}.pmw_gameplay_dynamics.fields.mana.value", "value": f"{value_root}.mana"}]})
            return result  # Primary execution is committed by the cost law exactly once.
        effects = [{"op": "set", "target": f"${binding}.{ACTOR_COMPONENT}.{key}", "value": f"{value_root}.{key}"}
                   for key in actor_paths[effect.kind]]
        result = [{"id": prefix, "mode": "event", "priority": 100, "bindings": identity,
                   "when": {"all": conditions}, "effects": effects}]
        if effect.kind == "add_resource" and effect.resource == "mana":
            mirror_identity = {binding: {"kind": "entity", "requires": [ACTOR_COMPONENT, "pmw_gameplay_dynamics"]}}
            result.append({"id": f"{prefix}.mana_mirror", "mode": "event", "priority": 100,
                           "bindings": mirror_identity, "when": {"all": conditions},
                           "effects": [{"op": "set", "target": f"${binding}.pmw_gameplay_dynamics.fields.mana.value",
                                        "value": f"{value_root}.mana"}]})
        return result
    if effect.kind == "modify_field":
        suffix, key = "value", "value"
        return [{"id": prefix, "mode": "event", "priority": 100, "bindings": identity,
                 "when": {"all": conditions}, "effects": [{"op": "set",
                    "target": f"${binding}.pmw_gameplay_dynamics.fields.{effect.field_id}.{suffix}",
                    "value": f"{value_root}.{key}"}]}]
    if effect.kind in {"modify_attractor", "modify_rate"}:
        result = []
        expiry_type = f"pmw.v04.action.{token}.{effect.id}.expire"
        for index in range(dynamics_slots):
            slot = f"slot_{index}"; slot_root = f"${binding}.pmw_gameplay_dynamics.fields.{effect.field_id}.temporary_modifiers.{slot}"
            slot_condition = {"ref": f"{value_root}.slot", "eq": slot}
            result.append({"id": f"{prefix}.{slot}.apply", "mode": "event", "priority": 100, "bindings": identity,
                           "when": {"all": [*conditions, slot_condition]}, "effects": [
                               {"op": "set", "target": slot_root, "value": f"{value_root}.source"},
                               {"op": "schedule_event", "event": {"id": f"{value_root}.expiry_handle", "type": expiry_type,
                                "time": f"{value_root}.expiry_time", "source": "$event.source", "target": f"${binding}.id",
                                "payload": {"action_id": action_id, "action_hash": action_hash, "effect_id": effect.id,
                                            "slot": slot, "field_id": effect.field_id, "owner": "$event.source",
                                            "expiry_handle": f"{value_root}.expiry_handle"}}}]})
            expire_conditions = [{"event.type": {"eq": expiry_type}}, {"ref": "$event.id", "eq": "$event.payload.expiry_handle"},
                                 {"ref": f"${binding}.id", "eq": "$event.target"}, {"ref": f"{slot_root}.active", "eq": True},
                                 {"ref": f"{slot_root}.owner", "eq": "$event.payload.owner"},
                                 {"ref": f"{slot_root}.expiry_handle", "eq": "$event.id"}]
            result.append({"id": f"{prefix}.{slot}.expire", "mode": "event", "priority": 100, "bindings": identity,
                           "when": {"all": expire_conditions}, "effects": [
                               {"op": "set", "target": slot_root, "value": {"active": False, "source_id": None, "owner": None,
                                "target": 0.0, "target_weight": 0.0, "rate_add": 0.0, "rate_multiplier": 1.0,
                                "curve": None, "curve_priority": -1, "expiry_handle": None}},
                               {"op": "cancel_scheduled", "value": "$event.id"}]})
        return result
    if effect.kind in {"apply_status", "grant_trait"}:
        return [{"id": prefix, "mode": "event", "priority": 100, "bindings": identity,
                 "when": {"all": conditions}, "effects": [{"op": "set", "target": f"${binding}.{STATUS_COMPONENT}",
                                                               "value": f"{value_root}.status_component"}]}]
    raise GameplayContractError(f"unsupported compiled effect {effect.kind}")


def _binding(selector):
    if selector == "self": return "target", {"target": {"kind": "entity", "requires": [ACTOR_COMPONENT]}}
    if selector == "target_actor": return "target", {"target": {"kind": "entity", "requires": [ACTOR_COMPONENT]}}
    if selector == "current_area": return "target", {"target": {"kind": "entity", "requires": ["pmw_gameplay_area"]}}
    if selector in {"linked_object", "adjacent_area"}: return "target", {"target": {"kind": "entity"}}
    raise GameplayContractError("unknown compiled selector")


def _status_clock_laws(status_specs, status_slots):
    laws = []
    for spec in status_specs:
        event_type = {"world_tick": "pmw.v04.world_tick", "combat_round": "pmw.v04.combat_round",
                      "owner_turn": "pmw.v04.owner_turn"}[spec.duration.unit]
        for index in range(status_slots):
            slot = f"slot_{index}"; root = f"$owner.{STATUS_COMPONENT}.slots.{slot}"
            base = [{"event.type": {"eq": event_type}}, {"ref": f"{root}.active", "eq": True},
                    {"ref": f"{root}.spec_id", "eq": spec.id}, {"ref": f"{root}.spec_hash", "eq": spec.canonical_hash}]
            if spec.duration.unit == "owner_turn": base.append({"ref": "$owner.id", "eq": "$event.payload.actor_id"})
            bindings = {"owner": {"kind": "entity", "requires": [ACTOR_COMPONENT, STATUS_COMPONENT]}}
            effects = []
            if spec.periodic_resource:
                resource, delta = spec.periodic_resource
                maximum = f"$owner.{ACTOR_COMPONENT}.max_{resource}"
                value = {"clamp": [{"add": [f"$owner.{ACTOR_COMPONENT}.{resource}", delta]}, 0.0, maximum]} if resource in {"hp", "mana"} else {"max": [0.0, {"add": [f"$owner.{ACTOR_COMPONENT}.{resource}", delta]}]}
                effects.append({"op": "set", "target": f"$owner.{ACTOR_COMPONENT}.{resource}", "value": value})
            laws.append({"id": f"pmw.v04.status.{spec.id}.{slot}.tick", "mode": "event", "priority": 100,
                         "bindings": bindings, "when": {"all": [*base, {"ref": f"{root}.remaining", "gt": 1}]},
                         "effects": [*effects, {"op": "delta", "target": f"{root}.remaining", "value": -1}]})
            laws.append({"id": f"pmw.v04.status.{spec.id}.{slot}.expire", "mode": "event", "priority": 100,
                         "bindings": bindings, "when": {"all": [*base, {"ref": f"{root}.remaining", "eq": 1}]},
                         "effects": [*effects, *([{"op": "set", "target": f"$owner.{ACTOR_COMPONENT}.{spec.on_expire_resource[0]}",
                                                  "value": spec.on_expire_resource[1]}] if spec.on_expire_resource else []),
                                     {"op": "set", "target": root, "value": neutral_status_slot()}]})
            cancel_base = [{"event.type": {"eq": STATUS_CANCEL_EVENT}}, {"ref": "$owner.id", "eq": "$event.target"},
                           {"ref": "$event.source", "eq": "$event.payload.owner_id"},
                           {"ref": "$event.payload.slot", "eq": slot}, {"ref": f"{root}.active", "eq": True},
                           {"ref": f"{root}.instance_id", "eq": "$event.payload.instance_id"},
                           {"ref": f"{root}.spec_hash", "eq": spec.canonical_hash}]
            laws.append({"id": f"pmw.v04.status.{spec.id}.{slot}.cancel", "mode": "event", "priority": 100,
                         "bindings": bindings, "when": {"all": cancel_base},
                         "effects": [*([{"op": "set", "target": f"$owner.{ACTOR_COMPONENT}.{spec.on_expire_resource[0]}",
                                        "value": spec.on_expire_resource[1]}] if spec.on_expire_resource else []),
                                     {"op": "set", "target": root, "value": neutral_status_slot()}]})
    return laws
