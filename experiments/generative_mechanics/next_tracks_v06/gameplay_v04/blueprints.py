"""Strict Blueprint parsing and deterministic PMW Entity instantiation."""

from __future__ import annotations

import math
import re
from types import MappingProxyType
from typing import Any

from pmw import Entity

from .contracts import (
    ATTRIBUTES, CURVES, PROTOCOL_ID, ActorBlueprint, AreaBlueprint,
    FieldDefinition, GameplayContractError,
)


_ID = re.compile(r"[a-z][a-z0-9_]{1,47}\Z")


def _strict(raw: Any, required: set[str], optional: set[str], path: str) -> dict:
    if not isinstance(raw, dict):
        raise GameplayContractError(f"{path} must be an object")
    unknown = set(raw) - required - optional
    missing = required - set(raw)
    if unknown or missing:
        raise GameplayContractError(
            f"{path} schema mismatch; unknown={sorted(unknown)} missing={sorted(missing)}"
        )
    return raw


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise GameplayContractError(f"{path} must be a gameplay identifier")
    return value


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GameplayContractError(f"{path} must be a finite number")
    return float(value)


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 32:
        raise GameplayContractError(f"{path} must be an integer in [1, 32]")
    return value


def parse_field_definition(raw: Any, path: str = "$.field") -> FieldDefinition:
    data = _strict(
        raw,
        {"id", "domain", "initial", "target", "rate", "curve"},
        {"max_persistent_patches", "max_temporary_modifiers"},
        path,
    )
    domain = _strict(data["domain"], {"min", "max"}, set(), f"{path}.domain")
    low = _number(domain["min"], f"{path}.domain.min")
    high = _number(domain["max"], f"{path}.domain.max")
    if low >= high:
        raise GameplayContractError(f"{path}.domain min must be less than max")
    initial = _number(data["initial"], f"{path}.initial")
    target = _number(data["target"], f"{path}.target")
    if not low <= initial <= high or not low <= target <= high:
        raise GameplayContractError(f"{path} initial and target must be inside domain")
    curve = data["curve"]
    if curve not in CURVES:
        raise GameplayContractError(f"{path}.curve must be one of {CURVES}")
    rate = _number(data["rate"], f"{path}.rate")
    if rate < 0.0:
        raise GameplayContractError(f"{path}.rate must be non-negative")
    width = high - low
    if curve == "linear" and rate > 1.0:
        raise GameplayContractError(f"{path}.rate exceeds linear stability limit")
    if curve == "distance_squared" and rate * width > 1.0:
        raise GameplayContractError(f"{path}.rate exceeds distance-squared stability limit")
    return FieldDefinition(
        _identifier(data["id"], f"{path}.id"), low, high, initial, target,
        rate, curve,
        _positive_int(data.get("max_persistent_patches", 4), f"{path}.max_persistent_patches"),
        _positive_int(data.get("max_temporary_modifiers", 4), f"{path}.max_temporary_modifiers"),
    )


def parse_area_blueprint(raw: Any) -> AreaBlueprint:
    data = _strict(raw, {"protocol", "kind", "id", "fields"}, {"ecology_state"}, "$")
    if data["protocol"] != PROTOCOL_ID or data["kind"] != "area_blueprint":
        raise GameplayContractError("invalid AreaBlueprint protocol or kind")
    if not isinstance(data["fields"], list) or not data["fields"]:
        raise GameplayContractError("$.fields must be a non-empty list")
    fields = tuple(parse_field_definition(item, f"$.fields[{index}]") for index, item in enumerate(data["fields"]))
    if len({item.id for item in fields}) != len(fields):
        raise GameplayContractError("$.fields contains duplicate IDs")
    ecology = data.get("ecology_state", "stable")
    if not isinstance(ecology, str) or not ecology:
        raise GameplayContractError("$.ecology_state must be non-empty")
    return AreaBlueprint(_identifier(data["id"], "$.id"), fields, ecology)


def parse_actor_blueprint(raw: Any) -> ActorBlueprint:
    data = _strict(
        raw,
        {"protocol", "kind", "id", "hp", "mana", "attributes", "traits"},
        set(),
        "$",
    )
    if data["protocol"] != PROTOCOL_ID or data["kind"] != "actor_blueprint":
        raise GameplayContractError("invalid ActorBlueprint protocol or kind")
    hp = _strict(data["hp"], {"max", "initial"}, set(), "$.hp")
    mana = _strict(data["mana"], {"max", "initial", "dynamics"}, set(), "$.mana")
    max_hp = _number(hp["max"], "$.hp.max")
    initial_hp = _number(hp["initial"], "$.hp.initial")
    max_mana = _number(mana["max"], "$.mana.max")
    initial_mana = _number(mana["initial"], "$.mana.initial")
    if max_hp <= 0 or max_mana < 0 or not 0 <= initial_hp <= max_hp or not 0 <= initial_mana <= max_mana:
        raise GameplayContractError("actor HP/Mana bounds are invalid")
    attributes = _strict(data["attributes"], set(ATTRIBUTES), set(), "$.attributes")
    parsed_attributes = {key: _number(attributes[key], f"$.attributes.{key}") for key in ATTRIBUTES}
    if any(value < 0 for value in parsed_attributes.values()):
        raise GameplayContractError("attributes must be non-negative")
    if not isinstance(data["traits"], list) or any(not isinstance(item, str) or not item for item in data["traits"]):
        raise GameplayContractError("$.traits must be a string list")
    if len(set(data["traits"])) != len(data["traits"]):
        raise GameplayContractError("$.traits contains duplicates")
    mana_dynamics = None
    if mana["dynamics"] is not None:
        raw_dynamics = dict(mana["dynamics"])
        raw_dynamics["id"] = "mana"
        raw_dynamics["domain"] = {"min": 0.0, "max": max_mana}
        raw_dynamics["initial"] = initial_mana
        mana_dynamics = parse_field_definition(raw_dynamics, "$.mana.dynamics")
    return ActorBlueprint(
        _identifier(data["id"], "$.id"), max_hp, initial_hp, max_mana,
        initial_mana, MappingProxyType(parsed_attributes), tuple(data["traits"]),
        mana_dynamics,
    )


def _neutral_source() -> dict[str, Any]:
    return {
        "active": False, "source_id": None, "owner": None,
        "target": 0.0, "target_weight": 0.0, "rate_add": 0.0,
        "rate_multiplier": 1.0, "curve": None, "curve_priority": -1,
        "expiry_handle": None,
    }


def field_state(definition: FieldDefinition) -> dict[str, Any]:
    return {
        "value": definition.initial,
        "domain_min": definition.minimum,
        "domain_max": definition.maximum,
        "baseline": {
            "target": definition.target, "target_weight": 1.0,
            "rate": definition.rate, "curve": definition.curve,
        },
        "persistent_patches": {
            f"slot_{index}": _neutral_source()
            for index in range(definition.max_persistent_patches)
        },
        "temporary_modifiers": {
            f"slot_{index}": _neutral_source()
            for index in range(definition.max_temporary_modifiers)
        },
        "diagnostics": {
            "effective_target": definition.target,
            "effective_rate": definition.rate,
            "effective_curve": definition.curve,
            "unclamped": definition.initial,
            "clamp_loss": 0.0,
        },
    }


def instantiate_area(blueprint: AreaBlueprint, instance_id: str) -> Entity:
    instance_id = _identifier(instance_id, "instance_id")
    return Entity(instance_id, "pmw_gameplay_area", components={
        "pmw_gameplay_area": {
            "blueprint_id": blueprint.id,
            "ecology_state": blueprint.ecology_state,
        },
        "pmw_gameplay_dynamics": {
            "fields": {item.id: field_state(item) for item in blueprint.fields},
        },
    })


def instantiate_actor(blueprint: ActorBlueprint, instance_id: str, *, controller: str) -> Entity:
    instance_id = _identifier(instance_id, "instance_id")
    if controller not in {"human", "ai"}:
        raise GameplayContractError("controller must be human or ai")
    actor = {
        "blueprint_id": blueprint.id, "controller": controller,
        "hp": blueprint.initial_hp, "max_hp": blueprint.max_hp,
        "mana": blueprint.initial_mana, "max_mana": blueprint.max_mana,
        "shield": 0.0,
        **{name: blueprint.attributes[name] for name in ATTRIBUTES},
        "traits": list(blueprint.traits),
        "active_equipped": [None] * 6, "active_stowed": [None] * 6,
        "passive_equipped": [None] * 6,
    }
    components = {"pmw_gameplay_actor": actor}
    if blueprint.mana_dynamics is not None:
        components["pmw_gameplay_dynamics"] = {
            "fields": {"mana": field_state(blueprint.mana_dynamics)},
        }
    return Entity(instance_id, "pmw_gameplay_actor", components=components)
