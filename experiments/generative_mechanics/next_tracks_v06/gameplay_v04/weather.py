"""Area weather with hysteresis, bounded duration, and explicit interactions."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping

from pmw import parse_law

from .actions import ACTOR_COMPONENT
from .conditions import ConditionSpec
from .contracts import GameplayContractError
from .dynamics import DYNAMICS_COMPONENT, WORLD_TICK_EVENT
from .effects import EffectSpec, parse_effect
from .status import STATUS_COMPONENT, StatusSpec


WEATHER_COMPONENT = "pmw_gameplay_weather"
TRAIT_PROJECTION_COMPONENT = "pmw_gameplay_trait_projection"
WEATHER_CHANGED_EVENT = "pmw.v04.weather.changed"
WEATHER_PULSE_EVENT = "pmw.v04.weather.pulse"
_ID = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")


@dataclass(frozen=True, slots=True)
class WeatherTraitInteraction:
    subject_kind: str
    subject_id: str
    effect: EffectSpec


@dataclass(frozen=True, slots=True)
class WeatherSpec:
    id: str
    label: str
    field_id: str
    enter_at: float
    exit_at: float
    duration_ticks: int
    source_id: str
    common_effects: tuple[EffectSpec, ...]
    trait_interactions: tuple[WeatherTraitInteraction, ...]
    canonical_hash: str


def parse_weather_spec(raw: Any, statuses: Mapping[str, StatusSpec] | None = None,
                       path: str = "$.weather") -> WeatherSpec:
    required = {"protocol", "id", "label", "field_id", "enter_at", "exit_at", "duration_ticks",
                "source_id", "common_effects", "trait_interactions"}
    if not isinstance(raw, dict) or set(raw) != required or raw.get("protocol") != "pmw-gameplay-v0.4":
        raise GameplayContractError(f"{path} has missing/unknown fields or invalid protocol")
    weather_id = _identifier(raw["id"], f"{path}.id")
    field_id = _identifier(raw["field_id"], f"{path}.field_id")
    source_id = _identifier(raw["source_id"], f"{path}.source_id")
    if not isinstance(raw["label"], str) or not raw["label"].strip():
        raise GameplayContractError(f"{path}.label is invalid")
    enter, exit_at = _number(raw["enter_at"], f"{path}.enter_at"), _number(raw["exit_at"], f"{path}.exit_at")
    if enter <= exit_at:
        raise GameplayContractError(f"{path} requires enter_at > exit_at for hysteresis")
    duration = raw["duration_ticks"]
    if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 10_000:
        raise GameplayContractError(f"{path}.duration_ticks is invalid")
    statuses = statuses or {}
    if not isinstance(raw["common_effects"], list) or not isinstance(raw["trait_interactions"], list):
        raise GameplayContractError(f"{path} effects must be lists")
    common = tuple(parse_effect(item, statuses, f"{path}.common_effects[{i}]") for i, item in enumerate(raw["common_effects"]))
    for effect in common:
        if effect.target.kind != "current_area" or effect.kind != "modify_field":
            raise GameplayContractError("common weather effects must be Area modify_field effects")
        if effect.sensing != "none":
            raise GameplayContractError("sensing-dependent weather effects require an explicit trait interaction")
        if effect.condition.kind != "always":
            raise GameplayContractError("common weather effects cannot hide conditional targeting")
    interactions = []
    for index, item in enumerate(raw["trait_interactions"]):
        item_path = f"{path}.trait_interactions[{index}]"
        if not isinstance(item, dict) or set(item) not in ({"trait_id", "effect"}, {"status_id", "effect"}):
            raise GameplayContractError(f"{item_path} is invalid")
        subject_kind = "trait" if "trait_id" in item else "status"
        subject_key = f"{subject_kind}_id"
        subject_id = _identifier(item[subject_key], f"{item_path}.{subject_key}")
        if subject_kind == "status" and subject_id not in statuses:
            raise GameplayContractError(f"{item_path}.status_id is unknown")
        effect = parse_effect(item["effect"], statuses, f"{item_path}.effect")
        if effect.target.kind != "self" or effect.condition.kind != "always":
            raise GameplayContractError("weather trait effect must target self with no hidden condition")
        interactions.append(WeatherTraitInteraction(subject_kind, subject_id, effect))
    ids = [item.id for item in common] + [item.effect.id for item in interactions]
    if len(ids) != len(set(ids)):
        raise GameplayContractError(f"{path} contains duplicate Effect IDs")
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return WeatherSpec(weather_id, raw["label"], field_id, enter, exit_at, duration, source_id,
                       common, tuple(interactions), hashlib.sha256(canonical).hexdigest())


def weather_component(specs: tuple[WeatherSpec, ...]) -> dict[str, Any]:
    if len({item.id for item in specs}) != len(specs):
        raise GameplayContractError("duplicate WeatherSpec")
    return {"states": {item.id: {"active": False, "remaining": 0, "source_id": item.source_id,
                                  "spec_hash": item.canonical_hash} for item in sorted(specs, key=lambda row: row.id)}}


def trait_projection_component(actor_component: Mapping[str, Any], trait_ids: tuple[str, ...]) -> dict[str, Any]:
    """Build a detached-world projection; runtime Laws consume this formal component."""
    traits = actor_component.get("traits")
    if not isinstance(traits, list) or any(not isinstance(item, str) or not item for item in traits):
        raise GameplayContractError("Actor trait source is invalid")
    if len(set(trait_ids)) != len(trait_ids) or any(_ID.fullmatch(item) is None for item in trait_ids):
        raise GameplayContractError("trait projection allowlist is invalid")
    return {"traits": {item: item in traits for item in sorted(trait_ids)}}


def build_weather_laws(bindings: Mapping[str, tuple[WeatherSpec, ...]],
                       statuses: Mapping[str, StatusSpec] | None = None) -> tuple[dict, ...]:
    laws: list[dict] = []
    for area_id, specs in sorted(bindings.items()):
        for spec in sorted(specs, key=lambda row: row.id):
            laws.extend(_weather_laws(area_id, spec, statuses or {}))
    result = tuple(sorted(laws, key=lambda row: row["id"]))
    for law in result:
        parse_law(law)
    return result


def _weather_laws(area_id: str, spec: WeatherSpec, statuses: Mapping[str, StatusSpec]) -> list[dict]:
    prefix = f"pmw.v04.weather.{area_id}.{spec.id}"
    state = f"$area.{WEATHER_COMPONENT}.states.{spec.id}"
    field = f"$area.{DYNAMICS_COMPONENT}.fields.{spec.field_id}"
    bindings = {"area": {"kind": "entity", "requires": ["pmw_gameplay_area", WEATHER_COMPONENT, DYNAMICS_COMPONENT]}}
    common = [{"event.type": {"eq": WORLD_TICK_EVENT}}, {"ref": "$area.id", "eq": area_id},
              {"ref": f"{state}.spec_hash", "eq": spec.canonical_hash}]
    changed = lambda active: {"op": "emit_event", "event": {
        "type": WEATHER_CHANGED_EVENT, "time": "$event.time", "source": spec.source_id, "target": "$area.id",
        "payload": {"weather_id": spec.id, "active": active, "source_id": spec.source_id,
                    "spec_hash": spec.canonical_hash},
    }}
    pulse = {"op": "emit_event", "event": {
        "type": WEATHER_PULSE_EVENT, "time": "$event.time", "source": spec.source_id, "target": "$area.id",
        "payload": {"weather_id": spec.id, "source_id": spec.source_id, "spec_hash": spec.canonical_hash},
    }}
    laws = [
        {"id": f"{prefix}.enter", "mode": "event", "priority": 100, "bindings": bindings,
         "when": {"all": [*common, {"ref": f"{state}.active", "eq": False},
                            {"ref": f"{field}.value", "gte": spec.enter_at}]},
         "effects": [{"op": "set", "target": f"{state}.active", "value": True},
                     {"op": "set", "target": f"{state}.remaining", "value": spec.duration_ticks}, changed(True), pulse]},
        {"id": f"{prefix}.continue", "mode": "event", "priority": 100, "bindings": bindings,
         "when": {"all": [*common, {"ref": f"{state}.active", "eq": True},
                            {"ref": f"{state}.remaining", "gt": 1}, {"ref": f"{field}.value", "gt": spec.exit_at}]},
         "effects": [{"op": "delta", "target": f"{state}.remaining", "value": -1}, pulse]},
        {"id": f"{prefix}.exit_threshold", "mode": "event", "priority": 100, "bindings": bindings,
         "when": {"all": [*common, {"ref": f"{state}.active", "eq": True},
                            {"ref": f"{field}.value", "lte": spec.exit_at}]},
         "effects": [{"op": "set", "target": f"{state}.active", "value": False},
                     {"op": "set", "target": f"{state}.remaining", "value": 0}, changed(False)]},
        {"id": f"{prefix}.expire", "mode": "event", "priority": 100, "bindings": bindings,
         "when": {"all": [*common, {"ref": f"{state}.active", "eq": True},
                            {"ref": f"{state}.remaining", "eq": 1}, {"ref": f"{field}.value", "gt": spec.exit_at}]},
         "effects": [{"op": "set", "target": f"{state}.active", "value": False},
                     {"op": "set", "target": f"{state}.remaining", "value": 0}, changed(False)]},
    ]
    pulse_common = [{"event.type": {"eq": WEATHER_PULSE_EVENT}}, {"ref": "$area.id", "eq": area_id},
                    {"ref": "$event.target", "eq": "$area.id"},
                    {"ref": "$event.payload.weather_id", "eq": spec.id},
                    {"ref": "$event.payload.spec_hash", "eq": spec.canonical_hash}]
    for effect in spec.common_effects:
        target = f"$area.{DYNAMICS_COMPONENT}.fields.{effect.field_id}"
        laws.append({"id": f"{prefix}.effect.{effect.id}", "mode": "event", "priority": 90, "bindings": bindings,
                     "when": {"all": [*pulse_common, {"ref": f"{state}.active", "eq": True}]},
                     "effects": [{"op": "set", "target": f"{target}.value", "value": {"clamp": [
                         {"add": [f"{target}.value", effect.amount]}, f"{target}.domain_min", f"{target}.domain_max"]}}]})
    for interaction in spec.trait_interactions:
        effect = interaction.effect
        effects = _actor_effect(effect)
        if interaction.subject_kind == "trait":
            actor_bindings = {**bindings, "actor": {"kind": "entity", "requires": [ACTOR_COMPONENT, TRAIT_PROJECTION_COMPONENT]},
                              "location": {"kind": "relation", "type": "located_in", "source": "$actor", "target": "$area"}}
            conditions = [*pulse_common, {"ref": f"{state}.active", "eq": True},
                          {"ref": f"$actor.{TRAIT_PROJECTION_COMPONENT}.traits.{interaction.subject_id}", "eq": True}]
            laws.append({"id": f"{prefix}.trait.{interaction.subject_id}.{effect.id}", "mode": "event", "priority": 90,
                         "bindings": actor_bindings, "when": {"all": conditions}, "effects": effects})
            # A Status-granted trait is runtime state, so compile explicit slot
            # variants instead of relying on the detached base-trait projection.
            granting = sorted(item.id for item in statuses.values()
                              if interaction.subject_id in item.granted_traits)
            for status_id in granting:
                for slot_index in range(8):
                    slot = f"$actor.{STATUS_COMPONENT}.slots.slot_{slot_index}"
                    status_bindings = {**bindings, "actor": {"kind": "entity", "requires": [ACTOR_COMPONENT, STATUS_COMPONENT, TRAIT_PROJECTION_COMPONENT]},
                                       "location": {"kind": "relation", "type": "located_in", "source": "$actor", "target": "$area"}}
                    status_conditions = [*pulse_common, {"ref": f"{state}.active", "eq": True},
                                         {"ref": f"$actor.{TRAIT_PROJECTION_COMPONENT}.traits.{interaction.subject_id}", "eq": False},
                                         {"ref": f"{slot}.active", "eq": True},
                                         {"ref": f"{slot}.spec_id", "eq": status_id}]
                    for earlier in range(slot_index):
                        earlier_slot = f"$actor.{STATUS_COMPONENT}.slots.slot_{earlier}"
                        status_conditions.append({"not": {"all": [
                            {"ref": f"{earlier_slot}.active", "eq": True},
                            {"any": [{"ref": f"{earlier_slot}.spec_id", "eq": granted_id}
                                     for granted_id in granting]},
                        ]}})
                    laws.append({"id": f"{prefix}.trait_status.{interaction.subject_id}.{status_id}.slot_{slot_index}.{effect.id}",
                                 "mode": "event", "priority": 90, "bindings": status_bindings,
                                 "when": {"all": status_conditions}, "effects": effects})
        else:
            for slot_index in range(8):
                slot = f"$actor.{STATUS_COMPONENT}.slots.slot_{slot_index}"
                actor_bindings = {**bindings, "actor": {"kind": "entity", "requires": [ACTOR_COMPONENT, STATUS_COMPONENT]},
                                  "location": {"kind": "relation", "type": "located_in", "source": "$actor", "target": "$area"}}
                conditions = [*pulse_common, {"ref": f"{state}.active", "eq": True},
                              {"ref": f"{slot}.active", "eq": True},
                              {"ref": f"{slot}.spec_id", "eq": interaction.subject_id}]
                laws.append({"id": f"{prefix}.status.{interaction.subject_id}.slot_{slot_index}.{effect.id}",
                             "mode": "event", "priority": 90, "bindings": actor_bindings,
                             "when": {"all": conditions}, "effects": effects})
    return laws


def _actor_effect(effect: EffectSpec) -> list[dict]:
    root = f"$actor.{ACTOR_COMPONENT}"
    if effect.kind == "damage":
        return [{"op": "set", "target": f"{root}.hp", "value": {"max": [0.0, {"sub": [f"{root}.hp", effect.amount]}]}}]
    if effect.kind == "heal":
        return [{"op": "set", "target": f"{root}.hp", "value": {"min": [f"{root}.max_hp", {"add": [f"{root}.hp", effect.amount]}]}}]
    if effect.kind == "shield":
        return [{"op": "set", "target": f"{root}.shield", "value": {"max": [f"{root}.shield", effect.amount]}}]
    if effect.kind == "add_resource" and effect.resource in {"mana", "hp", "shield"}:
        high = f"{root}.max_{effect.resource}" if effect.resource in {"mana", "hp"} else {"add": [f"{root}.shield", effect.amount]}
        return [{"op": "set", "target": f"{root}.{effect.resource}", "value": {"clamp": [
            {"add": [f"{root}.{effect.resource}", effect.amount]}, 0.0, high]}}]
    raise GameplayContractError("weather trait interaction uses an unsupported Effect template")


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GameplayContractError(f"{path} must be finite numeric")
    return float(value)


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise GameplayContractError(f"{path} is invalid")
    return value
