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
from .status import DurationSpec, STATUS_COMPONENT, StatusSpec, active_status_slot, neutral_status_slot, parse_status_spec


ACTION_EVENT = "pmw.v04.action.resolve"
ACTOR_COMPONENT = "pmw_gameplay_actor"
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


def resolve_action(session, registry: ActionRegistry, request: ActionRequest, *, execution_kind: str = "primary",
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
        if effect.kind == "damage":
            absorbed = min(actor_state["shield"], amount); actor_state["shield"] -= absorbed
            actor_state["hp"] = max(0.0, actor_state["hp"] - (amount - absorbed))
            row.update({"shield": actor_state["shield"], "hp": actor_state["hp"]})
        elif effect.kind == "heal": actor_state["hp"] = min(actor_state["max_hp"], actor_state["hp"] + amount); row["hp"] = actor_state["hp"]
        elif effect.kind == "shield": actor_state["shield"] = max(actor_state["shield"], amount); row["shield"] = actor_state["shield"]
        else:
            key = effect.resource; maximum = actor_state.get(f"max_{key}")
            actor_state[key] = max(0.0, min(maximum, actor_state[key] + amount)) if maximum is not None else max(0.0, actor_state[key] + amount)
            row[key] = actor_state[key]
        values = {key: row[key] for key in ({"hp", "shield"} if effect.kind == "damage" else {"hp"} if effect.kind == "heal" else {"shield"} if effect.kind == "shield" else {effect.resource}) if key in row}
    elif effect.kind in {"apply_status", "grant_trait"}:
        if actor_state is None: raise GameplayContractError(f"{effect.kind} target must be Actor")
        slots = actor_state.setdefault("status_slots", {f"slot_{i}": neutral_status_slot() for i in range(8)})
        spec = registry.statuses.get(effect.status_id) if effect.kind == "apply_status" else StatusSpec(
            f"trait_{effect.trait_id}", 1, "buff", 1, "refresh",
            DurationSpec("owner_turn", effect.duration),
            (effect.trait_id,), None, None, f"trait:{effect.trait_id}")
        existing = next(((name, value) for name, value in slots.items() if value["active"] and value["spec_id"] == spec.id), None)
        if existing and spec.stack_policy == "reject": raise GameplayContractError("status stacking rejected")
        slot = existing[0] if existing else next((name for name, value in sorted(slots.items()) if not value["active"]), None)
        if slot is None: raise GameplayContractError("status capacity exhausted")
        prior = slots[slot]; stacks = min(spec.max_stacks, prior["stacks"] + 1) if existing and spec.stack_policy == "add_stacks" else 1
        value = active_status_slot(spec, instance_id=f"{request.request_id}:{effect.id}", source_id=definition.id,
                                   owner_id=request.actor_id, stacks=stacks)
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
    return result
