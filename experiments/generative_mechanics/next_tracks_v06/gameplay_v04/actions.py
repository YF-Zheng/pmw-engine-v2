"""Trusted action registry, strict requests, preflight, and PMW dispatch."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from pmw import Event

from .attributes import evaluate_terms
from .conditions import ConditionSpec, evaluate_condition, parse_condition
from .contracts import GameplayContractError, ScopeCapability, SelectorContext
from .effects import EffectSpec, parse_effect
from .selectors import resolve_selector
from .status import (DurationSpec, STATUS_COMPONENT, StatusSpec, active_status_slot,
                     matches_status_source, neutral_status_slot, parse_status_spec)
from .shields import (SHIELD_COMPONENT, absorb_damage, bind_layer_to_status,
                      grant_shield, release_status_layer, shield_component,
                      validate_status_shield_ownership)


ACTION_EVENT = "pmw.v04.action.resolve"
ACTOR_COMPONENT = "pmw_gameplay_actor"
REGISTRY_COMPONENT = "pmw_gameplay_mechanism_registry"
SLOT_FREE_BASIC_ACTIONS = {
    "basic_attack": "attack",
    "basic_guard": "guard",
    "basic_wait": "wait",
}
_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


@dataclass(frozen=True, slots=True)
class ActionCost:
    duration: int
    mana: float = 0.0


@dataclass(frozen=True, slots=True)
class ActionCostModifier:
    id: str
    condition: ConditionSpec
    duration_add: int
    mana_add: float


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    id: str
    version: int
    action_type: str
    cost: ActionCost
    capability: ScopeCapability
    effects: tuple[EffectSpec, ...]
    canonical_hash: str
    cost_modifiers: tuple[ActionCostModifier, ...] = ()
    builtin: bool = False


@dataclass(frozen=True, slots=True)
class ActionRequest:
    request_id: str
    actor_id: str
    action_id: str
    target_actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    request: ActionRequest
    definition: ActionDefinition
    cost: ActionCost
    effect_outcomes: tuple[Mapping[str, Any], ...]
    event_result: Any


class ActionRegistry:
    def __init__(self, actions: Iterable[ActionDefinition], statuses: Iterable[StatusSpec] = (), hooks: Iterable[Any] = ()):
        action_items, status_items, hook_items = tuple(actions), tuple(statuses), tuple(hooks)
        if len({x.id for x in action_items}) != len(action_items): raise GameplayContractError("duplicate action id")
        if len({x.id for x in status_items}) != len(status_items): raise GameplayContractError("duplicate status id")
        self.actions = MappingProxyType({x.id: x for x in action_items})
        self.statuses = MappingProxyType({x.id: x for x in status_items})
        if len({x.id for x in hook_items}) != len(hook_items): raise GameplayContractError("duplicate hook id")
        self.hooks = MappingProxyType({x.id: x for x in hook_items})
        for hook in hook_items:
            action = self.actions.get(hook.action_id)
            if action is None or tuple(effect.id for effect in action.effects) != hook.effect_ids:
                raise GameplayContractError("hook does not reference one exact trusted effect bundle")

    @classmethod
    def parse(cls, raw: Any) -> "ActionRegistry":
        required = {"protocol", "statuses", "actions"}
        if not isinstance(raw, dict) or set(raw) - required - {"hooks"} or not required <= set(raw) or raw["protocol"] != "pmw-gameplay-v0.4":
            raise GameplayContractError("invalid ActionRegistry document")
        if not isinstance(raw["statuses"], list) or not isinstance(raw["actions"], list): raise GameplayContractError("registry lists are invalid")
        statuses = tuple(parse_status_spec(item, f"$.statuses[{i}]") for i, item in enumerate(raw["statuses"]))
        status_map = {x.id: x for x in statuses}
        if len(status_map) != len(statuses): raise GameplayContractError("duplicate status id")
        actions = tuple(parse_action_definition(item, status_map, f"$.actions[{i}]") for i, item in enumerate(raw["actions"]))
        from .hooks import parse_hook
        hooks_raw = raw.get("hooks", [])
        if not isinstance(hooks_raw, list): raise GameplayContractError("registry hooks must be a list")
        hooks = tuple(parse_hook(item, f"$.hooks[{i}]") for i, item in enumerate(hooks_raw))
        return cls(actions, statuses, hooks)


def parse_action_definition(raw: Any, statuses: Mapping[str, StatusSpec], path: str = "$.action") -> ActionDefinition:
    required = {"id", "version", "action_type", "cost", "scope", "effects"}
    optional = {"builtin", "cost_modifiers"}
    if not isinstance(raw, dict) or set(raw) - required - optional or not required <= set(raw): raise GameplayContractError(f"{path} has missing or unknown fields")
    if not isinstance(raw["id"], str) or not _ID.fullmatch(raw["id"]): raise GameplayContractError(f"{path}.id is invalid")
    if isinstance(raw["version"], bool) or not isinstance(raw["version"], int) or raw["version"] < 1: raise GameplayContractError(f"{path}.version is invalid")
    if raw["action_type"] not in {"attack", "guard", "wait", "skill", "explore", "harvest"}: raise GameplayContractError(f"{path}.action_type is invalid")
    cost = raw["cost"]
    if not isinstance(cost, dict) or set(cost) != {"duration", "mana"}: raise GameplayContractError(f"{path}.cost is invalid")
    duration, mana = cost["duration"], cost["mana"]
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 1: raise GameplayContractError(f"{path}.cost.duration must be positive")
    if isinstance(mana, bool) or not isinstance(mana, (int, float)) or not math.isfinite(mana) or mana < 0: raise GameplayContractError(f"{path}.cost.mana is invalid")
    scope = raw["scope"]
    if not isinstance(scope, dict) or set(scope) != {"selectors", "relation_types"}: raise GameplayContractError(f"{path}.scope is invalid")
    selectors, relations = scope["selectors"], scope["relation_types"]
    if not isinstance(selectors, list) or not selectors or any(x not in {"self", "target_actor", "current_area", "linked_object", "adjacent_area"} for x in selectors): raise GameplayContractError(f"{path}.scope.selectors is invalid")
    if len(set(selectors)) != len(selectors) or not isinstance(relations, list) or any(not isinstance(x, str) or not x for x in relations): raise GameplayContractError(f"{path}.scope is invalid")
    if not isinstance(raw["effects"], list) or not raw["effects"]: raise GameplayContractError(f"{path}.effects must be non-empty")
    effects = tuple(parse_effect(item, statuses, f"{path}.effects[{i}]") for i, item in enumerate(raw["effects"]))
    if len({x.id for x in effects}) != len(effects): raise GameplayContractError(f"{path}.effects contains duplicate IDs")
    footprints = []
    for effect in effects:
        if effect.target.kind not in selectors: raise GameplayContractError(f"{path}.effects target exceeds action scope")
        keys = {"damage": ("hp", "shield"), "heal": ("hp",), "shield": ("shield",),
                "add_resource": (effect.resource,), "modify_field": (f"field:{effect.field_id}:value",),
                "modify_attractor": (f"field:{effect.field_id}:target",), "modify_rate": (f"field:{effect.field_id}:rate",)}.get(effect.kind, ())
        if effect.kind in {"apply_status", "grant_trait"}: keys = ("status_component",)
        for key in keys:
            footprint = (effect.target.kind, effect.target.relation_type, key)
            if footprint in footprints: raise GameplayContractError(f"{path}.effects contains conflicting writes")
            footprints.append(footprint)
    builtin = raw.get("builtin", False)
    if not isinstance(builtin, bool): raise GameplayContractError(f"{path}.builtin must be boolean")
    modifiers_raw = raw.get("cost_modifiers", [])
    if not isinstance(modifiers_raw, list): raise GameplayContractError(f"{path}.cost_modifiers must be a list")
    modifiers = []
    for index, item in enumerate(modifiers_raw):
        item_path = f"{path}.cost_modifiers[{index}]"
        if not isinstance(item, dict) or set(item) != {"id", "condition", "duration_add", "mana_add"}:
            raise GameplayContractError(f"{item_path} has missing or unknown fields")
        if not isinstance(item["id"], str) or not _ID.fullmatch(item["id"]): raise GameplayContractError(f"{item_path}.id is invalid")
        duration_add, mana_add = item["duration_add"], item["mana_add"]
        if isinstance(duration_add, bool) or not isinstance(duration_add, int): raise GameplayContractError(f"{item_path}.duration_add is invalid")
        if isinstance(mana_add, bool) or not isinstance(mana_add, (int, float)) or not math.isfinite(mana_add): raise GameplayContractError(f"{item_path}.mana_add is invalid")
        modifiers.append(ActionCostModifier(item["id"], parse_condition(item["condition"], f"{item_path}.condition"), duration_add, float(mana_add)))
    if len({item.id for item in modifiers}) != len(modifiers): raise GameplayContractError(f"{path}.cost_modifiers contains duplicates")
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return ActionDefinition(raw["id"], raw["version"], raw["action_type"], ActionCost(duration, float(mana)),
                            ScopeCapability(raw["id"], tuple(selectors), tuple(relations)), effects,
                            hashlib.sha256(canonical).hexdigest(), tuple(modifiers), builtin)


def parse_action_request(raw: Any) -> ActionRequest:
    if not isinstance(raw, dict) or set(raw) - {"request_id", "actor_id", "action_id", "target_actor_id"} or not {"request_id", "actor_id", "action_id"} <= set(raw):
        raise GameplayContractError("ActionRequest has missing or unknown fields")
    for key in ("request_id", "actor_id", "action_id"):
        if not isinstance(raw[key], str) or not _ID.fullmatch(raw[key]): raise GameplayContractError(f"ActionRequest.{key} is invalid")
    target = raw.get("target_actor_id")
    if target is not None and (not isinstance(target, str) or not _ID.fullmatch(target)): raise GameplayContractError("ActionRequest.target_actor_id is invalid")
    return ActionRequest(raw["request_id"], raw["actor_id"], raw["action_id"], target)


def resolve_action(session, registry: ActionRegistry, request: ActionRequest) -> ActionOutcome:
    """Resolve an external primary request after authoritative authorization."""
    authorize_primary_action(session, registry, request)
    return _resolve_action(session, registry, request)


def _resolve_action(session, registry: ActionRegistry, request: ActionRequest, *, execution_kind: str = "primary",
                    hook_context: Mapping[str, Any] | None = None) -> ActionOutcome:
    if execution_kind not in {"primary", "hook"}: raise GameplayContractError("invalid action execution kind")
    if (execution_kind == "hook") != (hook_context is not None): raise GameplayContractError("hook execution requires trusted hook context")
    definition = registry.actions.get(request.action_id)
    if definition is None: raise GameplayContractError("unknown registered action")
    actor_entity = session.state.entities.get(request.actor_id)
    if actor_entity is None or ACTOR_COMPONENT not in actor_entity.components: raise GameplayContractError("request actor is not an Actor")
    actor = _actor_view(actor_entity)
    if actor["hp"] <= 0: raise GameplayContractError("defeated Actor cannot act")
    target_entity = session.state.entities.get(request.target_actor_id) if request.target_actor_id else None
    if request.target_actor_id and (target_entity is None or ACTOR_COMPONENT not in target_entity.components): raise GameplayContractError("target is not an Actor")
    context = SelectorContext(request.actor_id, request.target_actor_id)
    shadow = {request.actor_id: deepcopy(actor)}
    if target_entity is not None: shadow[target_entity.id] = _actor_view(target_entity)
    quote = definition.cost
    if execution_kind == "primary":
        duration, mana = quote.duration, quote.mana
        cost_context = _condition_context(session, request, shadow)
        for modifier in definition.cost_modifiers:
            if evaluate_condition(modifier.condition, cost_context):
                duration += modifier.duration_add; mana += modifier.mana_add
        quote = ActionCost(max(1, duration), max(0.0, mana))
    else:
        quote = ActionCost(1, 0.0)
    if actor["mana"] < quote.mana: raise GameplayContractError("insufficient mana")
    shadow[request.actor_id]["mana"] -= quote.mana
    writes: dict[str, dict[str, Any]] = {request.actor_id: {"mana": shadow[request.actor_id]["mana"]}}
    outcomes = []
    reservations: list[tuple[str, str, dict]] = []
    for effect in definition.effects:
        targets = resolve_selector(session.state, effect.target, context, definition.capability)
        if len(targets) != 1: raise GameplayContractError("Gate 2 effects require exactly one resolved target")
        target_id = targets[0]
        cond_context = _condition_context(session, request, shadow)
        enabled = evaluate_condition(effect.condition, cond_context)
        if effect.commitment == "required" and not enabled: raise GameplayContractError(f"required effect {effect.id!r} condition failed")
        if not enabled:
            outcomes.append({"effect_id": effect.id, "kind": effect.kind, "status": "skipped", "target_id": target_id, "values": {}}); continue
        outcome = _simulate_effect(session, registry, request, definition, effect, target_id, shadow, writes, reservations)
        outcomes.append(outcome)
    for outcome in outcomes:
        final_actor = shadow.get(outcome["target_id"])
        if (final_actor is not None and final_actor.get("_replacement_released_shield") and
                "shield" in outcome["values"]):
            outcome["values"]["shield"] = final_actor["shield"]
            outcome["values"]["shield_component"] = final_actor["_shield_component"]
    for actor_state in shadow.values():
        validate_status_shield_ownership(
            {"slots": actor_state["status_slots"]}, actor_state["_shield_component"]
        )
    payload = {"protocol": "pmw-gameplay-v0.4", "request_id": request.request_id, "action_id": definition.id,
               "action_hash": definition.canonical_hash, "actor_id": request.actor_id, "target_actor_id": request.target_actor_id,
               "execution_kind": execution_kind, "actor_mana": shadow[request.actor_id]["mana"], "action_duration": quote.duration,
               "writes": writes, "reservations": reservations,
               "effects": {row["effect_id"]: row for row in outcomes}, "outcomes": outcomes}
    if hook_context is not None: payload["hook"] = dict(hook_context)
    payload = json.loads(json.dumps(payload, sort_keys=True, allow_nan=False))
    before = session.state.to_dict()
    result = session.runtime.run_event(Event(f"pmw:v04:action:{request.request_id}", ACTION_EVENT,
                                              session.state.sim_time, request.actor_id, request.target_actor_id, payload))
    matched = any(event.event_law_matches for event in result.trace.events)
    if not matched:
        if session.state.to_dict() != before: raise GameplayContractError("failed action mutated state")
        raise GameplayContractError("action did not match installed definition")
    return ActionOutcome(request, definition, quote, tuple(outcomes), result)


def authorize_primary_action(session, registry: ActionRegistry, request: ActionRequest) -> ActionDefinition:
    """Authorize an untrusted controller request without mutating WorldState."""
    definition = registry.actions.get(request.action_id)
    if definition is None:
        raise GameplayContractError("unknown registered action")
    actor_entity = session.state.entities.get(request.actor_id)
    if actor_entity is None or ACTOR_COMPONENT not in actor_entity.components:
        raise GameplayContractError("request actor is not an Actor")

    basic_type = SLOT_FREE_BASIC_ACTIONS.get(definition.id)
    if basic_type is not None:
        # `builtin` is definition metadata, not an authority token.  Bind each
        # slot-free action to the canonical shipped definition so a caller
        # cannot register a stronger action under a privileged basic ID.
        from .basics import basic_registry
        trusted = basic_registry().actions[definition.id]
        if (
            not definition.builtin
            or definition.action_type != basic_type
            or definition.version != trusted.version
            or definition.canonical_hash != trusted.canonical_hash
        ):
            raise GameplayContractError("slot-free basic action identity is invalid")
        return definition
    if definition.builtin or definition.action_type != "skill":
        raise GameplayContractError("only the three trusted basic actions are slot-free")

    formal_registries = [
        entity.components[REGISTRY_COMPONENT]
        for entity in session.state.entities.values()
        if REGISTRY_COMPONENT in entity.components
    ]
    reference_hash = definition.canonical_hash
    if formal_registries:
        if len(formal_registries) != 1:
            raise GameplayContractError("world mechanism registry is ambiguous")
        component = formal_registries[0]
        entries = component.get("entries") if isinstance(component, Mapping) else None
        matches = [row for row in entries or () if (
            isinstance(row, Mapping)
            and row.get("skill_id") == definition.id
            and row.get("version") == definition.version
            and row.get("kind") == "skill_blueprint"
            and row.get("enabled") is True
        )]
        if not isinstance(entries, list) or len(matches) != 1:
            raise GameplayContractError("equipped skill is not enabled in the formal registry")
        reference_hash = matches[0].get("canonical_hash")

    actor = actor_entity.components[ACTOR_COMPONENT]
    equipped = actor.get("active_equipped")
    if not isinstance(equipped, list) or len(equipped) != 6:
        raise GameplayContractError("Actor active equipped loadout is invalid")
    expected = {
        "id": definition.id,
        "version": definition.version,
        "canonical_hash": reference_hash,
        "kind": "skill_blueprint",
    }
    if not any(isinstance(row, Mapping) and dict(row) == expected for row in equipped):
        raise GameplayContractError("action is not an exact currently equipped active skill")
    return definition


def submit_primary_action(session, registry: ActionRegistry, request: ActionRequest) -> ActionOutcome:
    """Authoritative external action boundary for human and AI controllers."""
    return resolve_action(session, registry, request)


def _condition_context(session, request, shadow):
    actor = shadow[request.actor_id]
    target = shadow.get(request.target_actor_id) if request.target_actor_id else None
    area = None
    located = next((r for r in session.state.relations.values() if r.type == "located_in" and r.source == request.actor_id), None)
    if located:
        entity = session.state.entities[located.target]
        area = {"fields": entity.components.get("pmw_gameplay_dynamics", {}).get("fields", {})}
    return {"self": actor, "target_actor": target or {}, "current_area": area or {}}


def _simulate_effect(session, registry, request, definition, effect, target_id, shadow, writes, reservations):
    target_entity = session.state.entities[target_id]
    actor_state = shadow.get(target_id)
    source_actor = shadow[request.actor_id]
    passed, amount, term_trace = evaluate_terms(effect.amount or 0.0, effect.terms, source_actor)
    if not passed:
        if effect.commitment == "required": raise GameplayContractError(f"required effect {effect.id!r} attribute check failed")
        return {"effect_id": effect.id, "kind": effect.kind, "status": "skipped", "target_id": target_id,
                "values": {}, "attribute_terms": term_trace}
    if effect.kind in {"damage", "heal", "shield", "add_resource"}:
        if actor_state is None: raise GameplayContractError(f"{effect.kind} target must be Actor")
        row = writes.setdefault(target_id, {})
        shield_state = actor_state["_shield_component"]
        if effect.kind == "damage":
            absorbed = absorb_damage(actor_state, shield_state, amount)
            actor_state["hp"] = max(0.0, actor_state["hp"] - (amount - absorbed))
            row.update({"shield": actor_state["shield"], "hp": actor_state["hp"],
                        "shield_component": shield_state})
        elif effect.kind == "heal": actor_state["hp"] = min(actor_state["max_hp"], actor_state["hp"] + amount); row["hp"] = actor_state["hp"]
        elif effect.kind == "shield":
            layer_slot = grant_shield(actor_state, shield_state,
                                      source_id=f"{definition.id}:{effect.id}",
                                      owner_id=request.actor_id, amount=amount)
            actor_state["_pending_shield_layer"] = layer_slot
            row.update({"shield": actor_state["shield"],
                        "shield_component": shield_state})
        else:
            key = effect.resource; maximum = actor_state.get(f"max_{key}")
            actor_state[key] = max(0.0, min(maximum, actor_state[key] + amount)) if maximum is not None else max(0.0, actor_state[key] + amount)
            row[key] = actor_state[key]
        keys = ({"hp", "shield", "shield_component"} if effect.kind == "damage" else
                {"hp"} if effect.kind == "heal" else
                {"shield", "shield_component"} if effect.kind == "shield" else
                {effect.resource})
        values = {key: row[key] for key in keys if key in row}
    elif effect.kind in {"apply_status", "grant_trait"}:
        if actor_state is None: raise GameplayContractError(f"{effect.kind} target must be Actor")
        slots = actor_state.setdefault("status_slots", {f"slot_{i}": neutral_status_slot() for i in range(8)})
        spec = registry.statuses.get(effect.status_id) if effect.kind == "apply_status" else StatusSpec(
            f"trait_{effect.trait_id}", 1, "buff", 1, "refresh",
            DurationSpec("owner_turn", effect.duration),
            (effect.trait_id,), None, None, f"trait:{effect.trait_id}")
        if spec.stack_policy in {"reject", "replace"}:
            existing = next(((name, value) for name, value in slots.items()
                             if value.get("active") and value.get("spec_id") == spec.id and
                             value.get("spec_hash") == spec.canonical_hash), None)
        else:
            existing = next(((name, value) for name, value in slots.items()
                             if matches_status_source(value, spec, source_id=definition.id,
                                                      owner_id=request.actor_id)), None)
        if existing and spec.stack_policy == "reject": raise GameplayContractError("status stacking rejected")
        slot = existing[0] if existing else next((name for name, value in sorted(slots.items()) if not value["active"]), None)
        if slot is None: raise GameplayContractError("status capacity exhausted")
        prior = slots[slot]; stacks = min(spec.max_stacks, prior["stacks"] + 1) if existing and spec.stack_policy == "add_stacks" else 1
        instance_id = f"{request.request_id}:{effect.id}"
        candidate_layer = actor_state.pop("_pending_shield_layer", None)
        if (existing and spec.stack_policy == "replace" and
                prior.get("shield_layer_slot") != candidate_layer):
            release_status_layer(actor_state, actor_state["_shield_component"], prior)
            actor_state["_replacement_released_shield"] = True
            writes.setdefault(target_id, {}).update({
                "shield": actor_state["shield"],
                "shield_component": actor_state["_shield_component"],
            })
        shield_layer_slot = (candidate_layer if spec.on_expire_resource and
                             spec.on_expire_resource[0] == "shield" else None)
        if shield_layer_slot is not None:
            bind_layer_to_status(actor_state["_shield_component"], shield_layer_slot, instance_id)
        value = active_status_slot(spec, instance_id=instance_id, source_id=definition.id,
                                   owner_id=request.actor_id, stacks=stacks,
                                   shield_layer_slot=shield_layer_slot)
        slots[slot] = value; reservations.append((target_id, slot, value)); values = {"slot": slot, "status": value, "status_component": {"slots": slots}}
    elif effect.kind in {"modify_field", "modify_attractor", "modify_rate"}:
        fields = target_entity.components.get("pmw_gameplay_dynamics", {}).get("fields", {})
        field = fields.get(effect.field_id)
        if field is None: raise GameplayContractError("effect targets unknown Field")
        row = writes.setdefault(target_id, {})
        if effect.kind == "modify_field": row[f"field:{effect.field_id}:value"] = max(field["domain_min"], min(field["domain_max"], field["value"] + amount)); values = {"value": row[f"field:{effect.field_id}:value"]}
        else:
            slot = next((name for name, value in sorted(field["temporary_modifiers"].items()) if not value["active"]), None)
            if slot is None: raise GameplayContractError("temporary dynamics modifier capacity exhausted")
            handle = f"pmw:v04:action-expiry:{request.request_id}:{effect.id}"
            source = {"active": True, "source_id": f"{definition.id}_{effect.id}", "owner": request.actor_id,
                      "target": max(field["domain_min"], min(field["domain_max"], amount)) if effect.kind == "modify_attractor" else 0.0,
                      "target_weight": 1.0 if effect.kind == "modify_attractor" else 0.0,
                      "rate_add": amount if effect.kind == "modify_rate" else 0.0, "rate_multiplier": 1.0,
                      "curve": None, "curve_priority": -1, "expiry_handle": handle}
            values = {"slot": slot, "source": source, "expiry_handle": handle,
                      "expiry_time": session.state.sim_time + effect.duration}
    return {"effect_id": effect.id, "kind": effect.kind, "status": "applied", "target_id": target_id,
            "amount": amount, "values": values, "attribute_terms": term_trace}


def _actor_view(entity) -> dict[str, Any]:
    result = deepcopy(entity.components[ACTOR_COMPONENT])
    result["status_slots"] = deepcopy(entity.components.get(STATUS_COMPONENT, {}).get(
        "slots", {f"slot_{i}": neutral_status_slot() for i in range(8)}
    ))
    result["_shield_component"] = deepcopy(entity.components.get(SHIELD_COMPONENT, shield_component()))
    return result
