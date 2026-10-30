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
from .hooks import HookDispatchLimits, HookDispatchRecord


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
    condition: ConditionSpec = ConditionSpec("always")


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
    auto_hooks: tuple[HookDispatchRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class PassiveSkillBinding:
    skill_id: str
    skill_version: int
    skill_hash: str
    skill_kind: str
    action_hash: str
    hook: Any


class ActionRegistry:
    def __init__(self, actions: Iterable[ActionDefinition], statuses: Iterable[StatusSpec] = (), hooks: Iterable[Any] = (),
                 *, process_controller: Any = None, drive_controller: Any = None,
                 relation_controller: Any = None,
                 _passive_bindings: Iterable[PassiveSkillBinding] = ()):
        action_items, status_items, hook_items = tuple(actions), tuple(statuses), tuple(hooks)
        if len({x.id for x in action_items}) != len(action_items): raise GameplayContractError("duplicate action id")
        if len({x.id for x in status_items}) != len(status_items): raise GameplayContractError("duplicate status id")
        self.actions = MappingProxyType({x.id: x for x in action_items})
        self.statuses = MappingProxyType({x.id: x for x in status_items})
        if len({x.id for x in hook_items}) != len(hook_items): raise GameplayContractError("duplicate hook id")
        self.hooks = MappingProxyType({x.id: x for x in hook_items})
        if process_controller is not None:
            from .processes import ProcessController
            if not isinstance(process_controller, ProcessController):
                raise GameplayContractError("process_controller must be a trusted ProcessController")
        if drive_controller is not None:
            from .drives import DriveController
            if not isinstance(drive_controller, DriveController):
                raise GameplayContractError("drive_controller must be a trusted DriveController")
        if relation_controller is not None:
            from .relations import RelationController
            if not isinstance(relation_controller, RelationController):
                raise GameplayContractError(
                    "relation_controller must be a trusted RelationController"
                )
        self.process_controller = process_controller
        self.drive_controller = drive_controller
        self.relation_controller = relation_controller
        bindings = tuple(_passive_bindings)
        if any(not isinstance(item, PassiveSkillBinding) for item in bindings):
            raise GameplayContractError("passive bindings must be trusted PassiveSkillBinding values")
        keys = [(item.skill_id, item.skill_version) for item in bindings]
        if len(keys) != len(set(keys)):
            raise GameplayContractError("duplicate passive binding")
        self.passive_bindings = MappingProxyType({
            (item.skill_id, item.skill_version): item for item in bindings
        })
        for hook in hook_items:
            action = self.actions.get(hook.action_id)
            if action is None or tuple(effect.id for effect in action.effects) != hook.effect_ids:
                raise GameplayContractError("hook does not reference one exact trusted effect bundle")
        for binding in bindings:
            from .hooks import HookSpec
            if not isinstance(binding.hook, HookSpec):
                raise GameplayContractError(
                    "passive binding hook must be a trusted HookSpec"
                )
            action = self.actions.get(binding.skill_id)
            hook = self.hooks.get(binding.hook.id)
            if (
                binding.skill_kind != "passive_blueprint"
                or action is None
                or action.version != binding.skill_version
                or action.canonical_hash != binding.action_hash
                or hook != binding.hook
                or hook.action_id != action.id
            ):
                raise GameplayContractError(
                    "passive binding does not match one exact trusted Action and Hook"
                )

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
    optional = {"builtin", "cost_modifiers", "condition"}
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
    control_effects = {
        "process_start", "process_modify", "drive_source", "relation_modifier",
    }
    controls = sum(effect.kind in control_effects for effect in effects)
    process_controls = sum(
        effect.kind in {"process_start", "process_modify"} for effect in effects
    )
    if process_controls > 1 and sum(effect.kind == "process_start" for effect in effects) > 1:
        raise GameplayContractError(f"{path}.effects permits at most one process_start")
    if process_controls > 1:
        raise GameplayContractError(
            f"{path}.effects permits at most one Process control operation"
        )
    if controls > 1:
        raise GameplayContractError(
            f"{path}.effects permits at most one Process/Drive control operation"
        )
    footprints = []
    for effect in effects:
        if effect.target.kind not in selectors: raise GameplayContractError(f"{path}.effects target exceeds action scope")
        keys = {"damage": ("hp", "shield"), "heal": ("hp",), "shield": ("shield",),
                "add_resource": (effect.resource,), "modify_field": (f"field:{effect.field_id}:value",),
                "modify_attractor": (f"field:{effect.field_id}:target",), "modify_rate": (f"field:{effect.field_id}:rate",)}.get(effect.kind, ())
        if effect.kind in {"apply_status", "grant_trait"}: keys = ("status_component",)
        if effect.kind == "process_start":
            keys = (f"process:{effect.process_template_id}:state",)
        if effect.kind == "process_modify":
            keys = (f"process:{effect.process_template_id}:configuration",)
        if effect.kind == "drive_source":
            keys = (f"drive:{effect.drive_profile_id}:source",)
        if effect.kind == "relation_modifier":
            keys = (f"relation:{effect.relation_profile_id}:enabled",)
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
    condition = (
        parse_condition(raw["condition"], f"{path}.condition")
        if "condition" in raw else ConditionSpec("always")
    )
    canonical_raw = dict(raw)
    if canonical_raw.get("condition", object()) is None:
        canonical_raw.pop("condition", None)
    canonical = json.dumps(canonical_raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return ActionDefinition(raw["id"], raw["version"], raw["action_type"], ActionCost(duration, float(mana)),
                            ScopeCapability(raw["id"], tuple(selectors), tuple(relations)), effects,
                            hashlib.sha256(canonical).hexdigest(), tuple(modifiers), builtin, condition)


def parse_action_request(raw: Any) -> ActionRequest:
    if not isinstance(raw, dict) or set(raw) - {"request_id", "actor_id", "action_id", "target_actor_id"} or not {"request_id", "actor_id", "action_id"} <= set(raw):
        raise GameplayContractError("ActionRequest has missing or unknown fields")
    for key in ("request_id", "actor_id", "action_id"):
        if not isinstance(raw[key], str) or not _ID.fullmatch(raw[key]): raise GameplayContractError(f"ActionRequest.{key} is invalid")
    target = raw.get("target_actor_id")
    if target is not None and (not isinstance(target, str) or not _ID.fullmatch(target)): raise GameplayContractError("ActionRequest.target_actor_id is invalid")
    return ActionRequest(raw["request_id"], raw["actor_id"], raw["action_id"], target)


def resolve_action(session, registry: ActionRegistry, request: ActionRequest, *,
                   dispatch_limits: HookDispatchLimits | None = None) -> ActionOutcome:
    """Resolve an external primary request after authoritative authorization."""
    authorize_primary_action(session, registry, request)
    from .transactions import publish_gameplay_session, stage_gameplay_session
    staged = stage_gameplay_session(session)
    outcome = _resolve_action(staged, registry, request)
    outcome = _dispatch_hooks(staged, registry, outcome, dispatch_limits)
    publish_gameplay_session(session, staged)
    return outcome


def _resolve_action(session, registry: ActionRegistry, request: ActionRequest, *, execution_kind: str = "primary",
                    hook_context: Mapping[str, Any] | None = None,
                    parent_event_id: str | None = None) -> ActionOutcome:
    if execution_kind not in {"primary", "hook"}: raise GameplayContractError("invalid action execution kind")
    if (execution_kind == "hook") != (hook_context is not None): raise GameplayContractError("hook execution requires trusted hook context")
    if parent_event_id is not None and execution_kind != "hook":
        raise GameplayContractError("parent event is valid only for hook execution")
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
    if (execution_kind == "primary" and
            not evaluate_condition(
                definition.condition,
                _condition_context(session, request, shadow),
            )):
        raise GameplayContractError("action condition is not satisfied")
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
        if (effect.kind in {"process_start", "process_modify", "drive_source",
                           "relation_modifier"}
                and execution_kind != "primary"):
            raise GameplayContractError(f"{effect.kind} is supported only for active primary execution")
        targets = resolve_selector(session.state, effect.target, context, definition.capability)
        if len(targets) != 1: raise GameplayContractError("Gate 2 effects require exactly one resolved target")
        target_id = targets[0]
        cond_context = _condition_context(session, request, shadow)
        enabled = evaluate_condition(effect.condition, cond_context)
        if effect.commitment == "required" and not enabled: raise GameplayContractError(f"required effect {effect.id!r} condition failed")
        if not enabled:
            outcomes.append({"effect_id": effect.id, "kind": effect.kind, "status": "skipped", "target_id": target_id, "values": {}}); continue
        outcome = _simulate_effect(
            session, registry, request, definition, effect, target_id, shadow, writes, reservations,
            execution_kind=execution_kind,
        )
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
    provenance = (
        {"kind": "derived", "parent_event": parent_event_id}
        if parent_event_id is not None
        else {"kind": "external", "parent_event": None}
    )
    result = session.runtime.run_event(Event(f"pmw:v04:action:{request.request_id}", ACTION_EVENT,
                                              session.state.sim_time, request.actor_id, request.target_actor_id, payload,
                                              provenance))
    matched = any(event.event_law_matches for event in result.trace.events)
    if not matched:
        if session.state.to_dict() != before: raise GameplayContractError("failed action mutated state")
        raise GameplayContractError("action did not match installed definition")
    process_rows = [
        row for row in outcomes
        if row["kind"] in {"process_start", "process_modify"} and row["status"] == "applied"
    ]
    if process_rows:
        from .processes import (
            PROCESS_COMPONENT, PROCESS_MODIFY_EVENT, PROCESS_START_EVENT,
        )
        row = process_rows[0]
        values = row["values"]
        target_id = values["process_target_id"]
        target = session.state.entities.get(target_id)
        component = None if target is None else target.components.get(PROCESS_COMPONENT)
        if row["kind"] == "process_start":
            process_matched = any(
                event.event.type == PROCESS_START_EVENT
                and event.event.target == target_id
                and any(law.law_id.endswith(".start") for law in event.event_law_matches)
                for event in result.trace.events
            )
            if (
                not process_matched
                or not isinstance(component, dict)
                or component.get("state") != "running"
                or component.get("profile_hash") != values["process_profile_hash"]
            ):
                raise GameplayContractError(
                    "process_start cascade did not activate the validated Process"
                )
        else:
            prepared = values["process_prepared"]
            expected_law_id = (
                f"pmw.v04.sandbox.process.{values['process_profile_id']}.modify"
            )
            process_matched = any(
                event.event.type == PROCESS_MODIFY_EVENT
                and event.event.target == target_id
                and any(
                    law.law_id == expected_law_id for law in event.event_law_matches
                )
                for event in result.trace.events
            )
            scheduled = [
                event for event in session.state.scheduled_events
                if event.id == prepared["expiry_handle"]
            ]
            if (
                not process_matched
                or not isinstance(component, dict)
                or component.get("state") != "running"
                or component.get("profile_hash") != values["process_profile_hash"]
                or component.get("rate") != prepared["after_rate"]
                or component.get("duration_ticks") != prepared["after_duration"]
                or component.get("remaining_ticks") != prepared["after_remaining"]
                or component.get("progress") != prepared["after_progress"]
                or len(scheduled) != 1
                or scheduled[0].time != prepared["deadline"]
            ):
                raise GameplayContractError(
                    "process_modify cascade did not update and reschedule the validated Process"
                )
    drive_rows = [
        row for row in outcomes
        if row["kind"] == "drive_source" and row["status"] == "applied"
    ]
    if drive_rows:
        from .drives import DRIVE_COMPONENT, DRIVE_EXPIRE_EVENT
        row = drive_rows[0]
        values = row["values"]
        prepared = values["drive_prepared"]
        drive_target_id = values["drive_target_id"]
        expected_law_id = (
            f"pmw.v04.sandbox.drive.{values['drive_profile_id']}.start"
        )
        drive_matched = any(
            event.event.type == f"pmw.v04.sandbox.drive.start"
            and event.event.target == drive_target_id
            and any(
                law.law_id == expected_law_id
                for law in event.event_law_matches
            )
            for event in result.trace.events
        )
        drive_entity = session.state.entities.get(drive_target_id)
        component = (
            drive_entity.components.get(DRIVE_COMPONENT)
            if drive_entity is not None else None
        )
        scheduled = [
            event for event in session.state.scheduled_events
            if event.id == prepared["expiry_handle"]
        ]
        if (
            not drive_matched
            or not isinstance(component, dict)
            or component.get("profile_id") != prepared["profile_id"]
            or component.get("profile_hash") != prepared["profile_hash"]
            or component.get("owner") != prepared["owner"]
            or component.get("rate") != prepared["rate"]
            or component.get("started_at") != prepared["started_at"]
            or component.get("expires_at") != prepared["expires_at"]
            or component.get("expiry_handle") != prepared["expiry_handle"]
            or component.get("last_step") != -1
            or component.get("last_delta") != 0
            or len(scheduled) != 1
            or scheduled[0].type != DRIVE_EXPIRE_EVENT
            or scheduled[0].time != prepared["expires_at"]
            or scheduled[0].target != drive_target_id
        ):
            raise GameplayContractError(
                "drive_source cascade did not activate the validated Drive"
            )
    relation_rows = [
        row for row in outcomes
        if row["kind"] == "relation_modifier" and row["status"] == "applied"
    ]
    if relation_rows:
        from .relations import (
            RELATION_COMPONENT, RELATION_EXPIRE_EVENT, RELATION_MODIFY_EVENT,
        )
        row = relation_rows[0]
        values = row["values"]
        prepared = values["relation_prepared"]
        relation_id = values["relation_target_id"]
        expected_law_id = (
            f"pmw.v04.sandbox.relation.{values['relation_profile_id']}.modify."
            f"{'on' if prepared['enabled'] else 'off'}"
        )
        relation_matched = any(
            event.event.type == RELATION_MODIFY_EVENT
            and event.event.target == relation_id
            and any(
                law.law_id == expected_law_id
                for law in event.event_law_matches
            )
            for event in result.trace.events
        )
        relation = session.state.relations.get(relation_id)
        component = (
            relation.components.get(RELATION_COMPONENT)
            if relation is not None else None
        )
        scheduled = [
            event for event in session.state.scheduled_events
            if event.id == prepared["expiry_handle"]
        ]
        if (
            not relation_matched
            or not isinstance(component, dict)
            or component.get("profile_id") != prepared["profile_id"]
            or component.get("profile_hash") != prepared["profile_hash"]
            or component.get("owner") != prepared["owner"]
            or not isinstance(component.get("base_enabled"), bool)
            or component.get("effective_enabled") is not prepared["enabled"]
            or component.get("active") is not True
            or component.get("enabled") is not prepared["enabled"]
            or component.get("started_at") != prepared["started_at"]
            or component.get("expires_at") != prepared["expires_at"]
            or component.get("expiry_handle") != prepared["expiry_handle"]
            or len(scheduled) != 1
            or scheduled[0].type != RELATION_EXPIRE_EVENT
            or scheduled[0].time != prepared["expires_at"]
            or scheduled[0].target != relation_id
        ):
            raise GameplayContractError(
                "relation_modifier cascade did not activate the validated Relation"
            )
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


def submit_primary_action(session, registry: ActionRegistry, request: ActionRequest, *,
                          dispatch_limits: HookDispatchLimits | None = None) -> ActionOutcome:
    """Authoritative external action boundary for human and AI controllers."""
    return resolve_action(session, registry, request, dispatch_limits=dispatch_limits)


@dataclass(frozen=True, slots=True)
class TimedActionOutcome:
    action: ActionOutcome
    time: Any


def submit_timed_primary_action(session, registry: ActionRegistry, request: ActionRequest, *,
                                reason: str = "exploration",
                                dispatch_limits: HookDispatchLimits | None = None) -> TimedActionOutcome:
    """Submit one primary action and charge its final quoted duration atomically."""
    from .time_ledger import spend_world_time
    from .transactions import publish_gameplay_session, stage_gameplay_session

    staged = stage_gameplay_session(session)
    authorize_primary_action(staged, registry, request)
    outcome = _resolve_action(staged, registry, request)
    outcome = _dispatch_hooks(staged, registry, outcome, dispatch_limits)
    time_result = spend_world_time(staged, outcome.cost.duration, reason=reason)
    publish_gameplay_session(session, staged)
    return TimedActionOutcome(outcome, time_result)


def _dispatch_hooks(session, registry: ActionRegistry, outcome: ActionOutcome,
                    limits: HookDispatchLimits | None) -> ActionOutcome:
    from .hooks import dispatch_action_hooks
    if limits is None:
        limits = HookDispatchLimits()
    return dispatch_action_hooks(session, registry, outcome, limits)


def _condition_context(session, request, shadow):
    actor = shadow[request.actor_id]
    target = shadow.get(request.target_actor_id) if request.target_actor_id else None
    area = None
    located = next((r for r in session.state.relations.values() if r.type == "located_in" and r.source == request.actor_id), None)
    if located:
        entity = session.state.entities[located.target]
        area = {"fields": entity.components.get("pmw_gameplay_dynamics", {}).get("fields", {})}
    return {"self": actor, "target_actor": target or {}, "current_area": area or {}}


def _simulate_effect(session, registry, request, definition, effect, target_id, shadow, writes, reservations,
                     *, execution_kind: str):
    target_entity = session.state.entities[target_id]
    actor_state = shadow.get(target_id)
    source_actor = shadow[request.actor_id]
    passed, amount, term_trace = evaluate_terms(effect.amount or 0.0, effect.terms, source_actor)
    if not passed:
        if effect.commitment == "required": raise GameplayContractError(f"required effect {effect.id!r} attribute check failed")
        return {"effect_id": effect.id, "kind": effect.kind, "status": "skipped", "target_id": target_id,
                "values": {}, "attribute_terms": term_trace}
    if effect.kind == "process_start":
        return _simulate_process_start(
            session, registry, request, definition, effect, target_id, execution_kind
        )
    if effect.kind == "process_modify":
        return _simulate_process_modify(
            session, registry, request, effect, target_id, execution_kind
        )
    if effect.kind == "drive_source":
        return _simulate_drive_source(
            session, registry, request, effect, target_id, execution_kind
        )
    if effect.kind == "relation_modifier":
        return _simulate_relation_modifier(
            session, registry, request, effect, target_id, execution_kind
        )
    if effect.kind in {"damage", "heal", "shield", "add_resource"}:
        if actor_state is None: raise GameplayContractError(f"{effect.kind} target must be Actor")
        row = writes.setdefault(target_id, {})
        shield_state = actor_state["_shield_component"]
        if effect.kind == "damage":
            absorbed = absorb_damage(actor_state, shield_state, amount)
            hp_loss = min(float(actor_state["hp"]), max(0.0, amount - absorbed))
            actor_state["hp"] = max(0.0, actor_state["hp"] - (amount - absorbed))
            row.update({"shield": actor_state["shield"], "hp": actor_state["hp"],
                        "shield_component": shield_state,
                        "hp_loss": hp_loss,
                        "shield_absorbed": absorbed,
                        "resolved_damage": hp_loss + absorbed})
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
        if effect.kind == "damage":
            values.update({
                "hp_loss": row["hp_loss"],
                "shield_absorbed": row["shield_absorbed"],
                "resolved_damage": row["resolved_damage"],
            })
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


def _simulate_process_start(session, registry, request, definition, effect, target_id, execution_kind):
    controller = registry.process_controller
    if controller is None:
        raise GameplayContractError("process_start requires a trusted ProcessController")
    if execution_kind != "primary":
        raise GameplayContractError("process_start is supported only for active primary execution")
    profile = _resolve_process_profile(
        session, controller, effect.process_template_id, request.actor_id, target_id
    )
    prepared = controller.prepare_start(session, profile.id, owner=request.actor_id)
    if prepared.profile_hash != profile.profile_hash:
        raise GameplayContractError("Process profile changed during preflight")
    return {
        "effect_id": effect.id,
        "kind": effect.kind,
        "status": "applied",
        "target_id": target_id,
        "amount": 0.0,
        "values": {
            "process_template_id": profile.template.id,
            "process_profile_id": profile.id,
            "process_profile_hash": profile.profile_hash,
            "process_target_id": profile.process_entity_id,
        },
        "attribute_terms": (),
    }


def _simulate_process_modify(session, registry, request, effect, target_id, execution_kind):
    controller = registry.process_controller
    if controller is None:
        raise GameplayContractError("process_modify requires a trusted ProcessController")
    if execution_kind != "primary":
        raise GameplayContractError(
            "process_modify is supported only for active primary execution"
        )
    profile = _resolve_process_profile(
        session, controller, effect.process_template_id, request.actor_id, target_id
    )
    prepared = controller.prepare_modify(
        session,
        profile.id,
        owner=request.actor_id,
        rate=effect.process_rate,
        remaining_ticks=effect.process_remaining_ticks,
    )
    if prepared["profile_hash"] != profile.profile_hash:
        raise GameplayContractError("Process profile changed during preflight")
    return {
        "effect_id": effect.id,
        "kind": effect.kind,
        "status": "applied",
        "target_id": target_id,
        "amount": 0.0,
        "values": {
            "process_template_id": profile.template.id,
            "process_profile_id": profile.id,
            "process_profile_hash": profile.profile_hash,
            "process_target_id": profile.process_entity_id,
            "process_prepared": prepared,
        },
        "attribute_terms": (),
    }


def _simulate_drive_source(session, registry, request, effect, target_id, execution_kind):
    controller = registry.drive_controller
    if controller is None:
        raise GameplayContractError(
            "drive_source requires a trusted DriveController"
        )
    if execution_kind != "primary":
        raise GameplayContractError(
            "drive_source is supported only for active primary execution"
        )
    profile = _resolve_drive_profile(
        session, controller, effect.drive_profile_id, request.actor_id, target_id
    )
    prepared = controller.prepare_start(
        session,
        profile.id,
        owner=request.actor_id,
        rate=effect.drive_rate,
        duration_ticks=effect.duration,
    )
    if prepared["profile_hash"] != profile.profile_hash:
        raise GameplayContractError("Drive profile changed during preflight")
    return {
        "effect_id": effect.id,
        "kind": effect.kind,
        "status": "applied",
        "target_id": target_id,
        "amount": 0.0,
        "values": {
            "drive_profile_id": profile.id,
            "drive_profile_hash": profile.profile_hash,
            "drive_target_id": profile.drive_entity_id,
            "drive_area_id": profile.area_id,
            "drive_stock_id": profile.stock.entity_id,
            "drive_prepared": prepared,
        },
        "attribute_terms": (),
    }


def _resolve_drive_profile(session, controller, profile_id, owner, area_id):
    matches = [
        profile for profile in controller.profiles
        if profile.id == profile_id and profile.owner == owner
    ]
    if not matches:
        raise GameplayContractError(
            "no Drive profile matches the requested profile and owner"
        )
    area = session.state.entities.get(area_id)
    if area is None or "pmw_gameplay_area" not in area.components:
        raise GameplayContractError("drive_source target is not an Area")
    local = [
        profile for profile in matches
        if profile.area_id == area_id
        and _endpoint_area(session, profile.drive_entity_id) == area_id
        and _endpoint_area(session, profile.stock.entity_id) == area_id
        and _endpoint_area(session, owner) == area_id
    ]
    if len(local) != 1:
        raise GameplayContractError(
            "Drive profile scope is missing, ambiguous, or remote for this Area"
        )
    return local[0]


def _simulate_relation_modifier(
    session, registry, request, effect, target_id, execution_kind
):
    controller = registry.relation_controller
    if controller is None:
        raise GameplayContractError(
            "relation_modifier requires a trusted RelationController"
        )
    if execution_kind != "primary":
        raise GameplayContractError(
            "relation_modifier is supported only for active primary execution"
        )
    profile = _resolve_relation_profile(
        session, controller, effect.relation_profile_id,
        request.actor_id, target_id,
    )
    if profile.relation_type not in registry.actions[request.action_id].capability.relation_types:
        raise GameplayContractError(
            "relation_modifier action capability does not authorize the trusted Relation type"
        )
    prepared = controller.prepare_modify(
        session,
        profile.id,
        owner=request.actor_id,
        enabled=effect.relation_enabled,
        duration_ticks=effect.duration,
    )
    if prepared["profile_hash"] != profile.profile_hash:
        raise GameplayContractError("Relation profile changed during preflight")
    return {
        "effect_id": effect.id,
        "kind": effect.kind,
        "status": "applied",
        "target_id": target_id,
        "amount": 0.0,
        "values": {
            "relation_profile_id": profile.id,
            "relation_profile_hash": profile.profile_hash,
            "relation_target_id": profile.relation_id,
            "relation_area_id": profile.area_id,
            "relation_prepared": prepared,
        },
        "attribute_terms": (),
    }


def _resolve_relation_profile(session, controller, profile_id, owner, area_id):
    matches = [
        profile for profile in controller.profiles
        if profile.id == profile_id and profile.owner == owner
    ]
    if not matches:
        raise GameplayContractError(
            "no Relation profile matches the requested profile and owner"
        )
    area = session.state.entities.get(area_id)
    if area is None or "pmw_gameplay_area" not in area.components:
        raise GameplayContractError("relation_modifier target is not an Area")
    local = [
        profile for profile in matches
        if profile.area_id == area_id
        and _endpoint_area(session, profile.source_entity_id) == area_id
        and _endpoint_area(session, profile.target_entity_id) == area_id
    ]
    if len(local) != 1:
        raise GameplayContractError(
            "Relation profile scope is missing, ambiguous, or remote for this Area"
        )
    return local[0]


def _resolve_process_profile(session, controller, template_id, owner, area_id):
    """Resolve exactly one trusted profile whose complete endpoint scope is local.

    Remote profiles may coexist in the catalog but cannot supply local authority.
    Zero or multiple valid local profiles reject instead of choosing arbitrarily.
    """
    matches = [
        profile for profile in controller.profiles
        if profile.template.id == template_id and profile.owner == owner
    ]
    if not matches:
        raise GameplayContractError("no Process profile matches the requested template and owner")
    area = session.state.entities.get(area_id)
    if area is None or "pmw_gameplay_area" not in area.components:
        raise GameplayContractError("process_start target is not an Area")
    located = []
    for profile in matches:
        endpoints = (profile.process_entity_id, *(item.stock.entity_id for item in (*profile.inputs, *profile.outputs)))
        resolved = [_endpoint_area(session, entity_id) for entity_id in endpoints]
        if all(item == area_id for item in resolved):
            located.append(profile)
    if len(located) != 1:
        raise GameplayContractError(
            "Process profile scope is missing, ambiguous, or remote for this Area"
        )
    return located[0]


def _endpoint_area(session, entity_id):
    entity = session.state.entities.get(entity_id)
    if entity is None:
        return None
    areas = sorted(
        relation.target for relation in session.state.relations.values()
        if relation.type == "located_in" and relation.source == entity_id
    )
    if len(areas) != 1:
        return None
    area = session.state.entities.get(areas[0])
    if area is None or "pmw_gameplay_area" not in area.components:
        return None
    return area.id


def _actor_view(entity) -> dict[str, Any]:
    result = deepcopy(entity.components[ACTOR_COMPONENT])
    result["status_slots"] = deepcopy(entity.components.get(STATUS_COMPONENT, {}).get(
        "slots", {f"slot_{i}": neutral_status_slot() for i in range(8)}
    ))
    result["_shield_component"] = deepcopy(entity.components.get(SHIELD_COMPONENT, shield_component()))
    return result
