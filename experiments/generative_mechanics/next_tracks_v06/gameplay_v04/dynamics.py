"""Gate 1 dynamics reference model and deterministic PMW Law lowering."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Iterable, Mapping

from pmw import parse_law

from .contracts import CURVES, DynamicsSource, FieldDefinition, FieldProfile, GameplayContractError


DYNAMICS_COMPONENT = "pmw_gameplay_dynamics"
CLOCK_COMPONENT = "pmw_gameplay_clock"
WORLD_TICK_EVENT = "pmw.v04.world_tick"
COMBAT_ROUND_EVENT = "pmw.v04.combat_round"
OWNER_TURN_EVENT = "pmw.v04.owner_turn"
SOURCE_APPLY_EVENT = "pmw.v04.dynamics.source.apply"
SOURCE_REMOVE_EVENT = "pmw.v04.dynamics.source.remove"
SOURCE_EXPIRE_EVENT = "pmw.v04.dynamics.source.expire"

_SOURCE_ID = re.compile(r"[a-z][a-z0-9_]{1,47}\Z")


@dataclass(frozen=True, slots=True)
class DynamicsEvaluation:
    value: float
    effective_target: float
    effective_rate: float
    effective_curve: str
    unclamped: float
    clamp_loss: float


def validate_source(source: DynamicsSource, field: FieldDefinition, *, temporary: bool) -> None:
    if _SOURCE_ID.fullmatch(source.source_id) is None or not isinstance(source.owner, str) or not source.owner:
        raise GameplayContractError("dynamics source identity is invalid")
    numbers = (source.target_weight, source.rate_add, source.rate_multiplier)
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in numbers):
        raise GameplayContractError("dynamics source numbers must be finite")
    if source.target_weight < 0 or source.rate_multiplier < 0:
        raise GameplayContractError("target weight and rate multiplier must be non-negative")
    if source.target is None and source.target_weight != 0:
        raise GameplayContractError("target_weight requires a target")
    if source.target is not None:
        if isinstance(source.target, bool) or not isinstance(source.target, (int, float)) or not math.isfinite(source.target):
            raise GameplayContractError("source target must be finite")
        if not field.minimum <= source.target <= field.maximum:
            raise GameplayContractError("source target is outside the Field domain")
    if (source.curve is None) != (source.curve_priority is None):
        raise GameplayContractError("curve and curve_priority must be supplied together")
    if source.curve is not None:
        if source.curve not in CURVES:
            raise GameplayContractError("unknown dynamics curve override")
        if isinstance(source.curve_priority, bool) or not isinstance(source.curve_priority, int) or source.curve_priority < 0:
            raise GameplayContractError("curve_priority must be a non-negative integer")
    if temporary:
        if isinstance(source.duration_ticks, bool) or not isinstance(source.duration_ticks, int) or source.duration_ticks < 1:
            raise GameplayContractError("temporary source requires positive duration_ticks")
    elif source.duration_ticks is not None:
        raise GameplayContractError("persistent source cannot have duration_ticks")


def evaluate_field(
    field: FieldDefinition,
    value: float,
    persistent: Iterable[DynamicsSource] = (),
    temporary: Iterable[DynamicsSource] = (),
) -> DynamicsEvaluation:
    sources = tuple(persistent) + tuple(temporary)
    for item in persistent:
        validate_source(item, field, temporary=False)
    for item in temporary:
        validate_source(item, field, temporary=True)
    overrides = [item for item in sources if item.curve is not None]
    priorities = [item.curve_priority for item in overrides]
    if len(priorities) != len(set(priorities)):
        raise GameplayContractError("curve override priorities must be unique")
    curve = max(overrides, key=lambda item: item.curve_priority).curve if overrides else field.curve
    numerator = field.target
    denominator = 1.0
    for item in sources:
        if item.target is not None:
            numerator += item.target_weight * item.target
            denominator += item.target_weight
    target = numerator / denominator
    rate = field.rate + sum(item.rate_add for item in sources)
    for item in sources:
        rate *= item.rate_multiplier
    limit = 1.0 if curve == "linear" else 1.0 / field.width
    rate = min(limit, max(0.0, rate))
    difference = target - value
    delta = rate * difference if curve == "linear" else rate * difference * abs(difference)
    raw = value + delta
    bounded = min(field.maximum, max(field.minimum, raw))
    return DynamicsEvaluation(bounded, target, rate, curve, raw, bounded - raw)


def build_dynamics_laws(profiles: Iterable[FieldProfile], *, clock_id: str = "pmw:v04:clock") -> tuple[dict, ...]:
    laws: list[dict] = []
    normalized = tuple(sorted(profiles, key=lambda item: (item.entity_id, item.field.id)))
    if len({(item.entity_id, item.field.id) for item in normalized}) != len(normalized):
        raise GameplayContractError("duplicate FieldProfile")
    for profile in normalized:
        laws.extend(_field_tick_laws(profile, clock_id))
        laws.extend(_source_laws(profile))
    laws.append({
        "id": "pmw.v04.dynamics.900.clock_complete", "mode": "event", "priority": 100,
        "bindings": {"clock": {"kind": "entity", "requires": [CLOCK_COMPONENT]}},
        "when": {"all": [
            {"event.type": {"eq": WORLD_TICK_EVENT}},
            {"ref": "$clock.id", "eq": clock_id},
            {"ref": "$event.payload.step", "eq": "$clock.pmw_gameplay_clock.next_step"},
            {"ref": "$event.time", "eq": "$clock.pmw_gameplay_clock.next_time"},
        ]},
        "effects": [
            {"op": "set", "target": "$clock.pmw_gameplay_clock.last_completed_step", "value": "$event.payload.step"},
            {"op": "delta", "target": "$clock.pmw_gameplay_clock.next_step", "value": 1},
            {"op": "delta", "target": "$clock.pmw_gameplay_clock.next_time", "value": 1.0},
        ],
    })
    result = tuple(sorted(laws, key=lambda item: item["id"]))
    for law in result:
        parse_law(law)
    return result


def _field_tick_laws(profile: FieldProfile, clock_id: str) -> list[dict]:
    field = profile.field
    base = f"$subject.{DYNAMICS_COMPONENT}.fields.{field.id}"
    slots = _slot_paths(profile)
    target = _effective_target(base, slots)
    raw_rate = _raw_rate(base, slots)
    common = [
        {"event.type": {"eq": WORLD_TICK_EVENT}},
        {"ref": "$subject.id", "eq": profile.entity_id},
        {"ref": "$clock.id", "eq": clock_id},
        {"ref": "$event.payload.step", "eq": "$clock.pmw_gameplay_clock.next_step"},
        {"ref": "$event.time", "eq": "$clock.pmw_gameplay_clock.next_time"},
    ]
    variants: list[tuple[str, str, list[dict]]] = []
    no_override = [{"ref": f"{path}.curve_priority", "lt": 0} for path in slots]
    variants.append(("base", field.curve, no_override))
    for index, path in enumerate(slots):
        winner = [
            {"ref": f"{path}.active", "eq": True},
            {"ref": f"{path}.curve_priority", "gte": 0},
        ] + [
            {"ref": f"{other}.curve_priority", "lt": f"{path}.curve_priority"}
            for other in slots if other != path
        ]
        for curve in CURVES:
            variants.append((f"slot_{index}_{curve}", curve, winner + [{"ref": f"{path}.curve", "eq": curve}]))
    laws: list[dict] = []
    for variant, curve, conditions in variants:
        rate_limit = 1.0 if curve == "linear" else 1.0 / field.width
        rate = {"clamp": [raw_rate, 0.0, rate_limit]}
        difference = {"sub": [target, f"{base}.value"]}
        directions = [("all", [])] if curve == "linear" else [
            ("up", [{"ref": f"{base}.value", "lte": target}]),
            ("down", [{"ref": f"{base}.value", "gt": target}]),
        ]
        for direction, sign_conditions in directions:
            if curve == "linear":
                delta = {"mul": [rate, difference]}
            elif direction == "up":
                delta = _mul([rate, difference, difference])
            else:
                delta = _mul([rate, difference, {"sub": [f"{base}.value", target]}])
            raw = {"add": [f"{base}.value", delta]}
            bounded = {"clamp": [raw, field.minimum, field.maximum]}
            effects = [
                {"op": "set", "target": f"{base}.diagnostics.effective_target", "value": target},
                {"op": "set", "target": f"{base}.diagnostics.effective_rate", "value": rate},
                {"op": "set", "target": f"{base}.diagnostics.effective_curve", "value": curve},
                {"op": "set", "target": f"{base}.diagnostics.unclamped", "value": raw},
                {"op": "set", "target": f"{base}.diagnostics.clamp_loss", "value": {"sub": [bounded, raw]}},
                {"op": "set", "target": f"{base}.value", "value": bounded},
            ]
            if profile.mirror_path:
                effects.append({
                    "op": "set", "target": "$subject." + ".".join(profile.mirror_path),
                    "value": bounded,
                })
            laws.append({
                "id": f"pmw.v04.dynamics.200.{profile.entity_id}.{field.id}.{variant}.{direction}",
                "mode": "event", "priority": 100,
                "bindings": {
                    "clock": {"kind": "entity", "requires": [CLOCK_COMPONENT]},
                    "subject": {"kind": "entity", "requires": [DYNAMICS_COMPONENT]},
                },
                "when": {"all": common + conditions + sign_conditions},
                "effects": effects,
            })
    return laws


def _source_laws(profile: FieldProfile) -> list[dict]:
    laws: list[dict] = []
    for layer, count in (
        ("persistent", profile.field.max_persistent_patches),
        ("temporary", profile.field.max_temporary_modifiers),
    ):
        root = "persistent_patches" if layer == "persistent" else "temporary_modifiers"
        for index in range(count):
            slot = f"slot_{index}"
            path = f"$subject.{DYNAMICS_COMPONENT}.fields.{profile.field.id}.{root}.{slot}"
            bindings = {"subject": {"kind": "entity", "requires": [DYNAMICS_COMPONENT]}}
            match = [
                {"ref": "$subject.id", "eq": profile.entity_id},
                {"ref": "$event.payload.entity_id", "eq": profile.entity_id},
                {"ref": "$event.payload.field_id", "eq": profile.field.id},
                {"ref": "$event.payload.layer", "eq": layer},
                {"ref": "$event.payload.slot", "eq": slot},
            ]
            effects = [{"op": "set", "target": path, "value": "$event.payload.source"}]
            if layer == "temporary":
                effects.append({"op": "schedule_event", "event": {
                    "id": "$event.payload.expiry_event.id",
                    "type": "$event.payload.expiry_event.type",
                    "time": "$event.payload.expiry_event.time",
                    "source": "$event.payload.expiry_event.source",
                    "target": "$event.payload.expiry_event.target",
                    "payload": "$event.payload.expiry_event.payload",
                }})
            laws.append({
                "id": f"pmw.v04.dynamics.010.apply.{profile.entity_id}.{profile.field.id}.{layer}.{slot}",
                "mode": "event", "priority": 100, "bindings": bindings,
                "when": {"all": [{"event.type": {"eq": SOURCE_APPLY_EVENT}}, *match, {"ref": f"{path}.active", "eq": False}]},
                "effects": effects,
            })
            neutral = neutral_source_state()
            remove_effects = [{"op": "set", "target": path, "value": neutral}]
            if layer == "temporary":
                remove_effects.append({"op": "cancel_scheduled", "value": "$event.payload.expiry_handle"})
            owner_match = [
                {"ref": f"{path}.source_id", "eq": "$event.payload.source_id"},
                {"ref": f"{path}.owner", "eq": "$event.payload.owner"},
            ]
            laws.append({
                "id": f"pmw.v04.dynamics.020.remove.{profile.entity_id}.{profile.field.id}.{layer}.{slot}",
                "mode": "event", "priority": 100, "bindings": bindings,
                "when": {"all": [{"event.type": {"eq": SOURCE_REMOVE_EVENT}}, *match, *owner_match]},
                "effects": remove_effects,
            })
            if layer == "temporary":
                laws.append({
                    "id": f"pmw.v04.dynamics.030.expire.{profile.entity_id}.{profile.field.id}.{slot}",
                    "mode": "event", "priority": 100, "bindings": bindings,
                    "when": {"all": [
                        {"event.type": {"eq": SOURCE_EXPIRE_EVENT}}, *match, *owner_match,
                        {"ref": "$event.id", "eq": "$event.payload.expiry_handle"},
                    ]},
                    "effects": [
                        {"op": "set", "target": path, "value": neutral},
                        {"op": "cancel_scheduled", "value": "$event.payload.expiry_handle"},
                    ],
                })
    return laws


def source_state(source: DynamicsSource, expiry_handle: str | None = None) -> dict[str, Any]:
    return {
        "active": True, "source_id": source.source_id, "owner": source.owner,
        "target": 0.0 if source.target is None else float(source.target),
        "target_weight": float(source.target_weight),
        "rate_add": float(source.rate_add),
        "rate_multiplier": float(source.rate_multiplier),
        "curve": source.curve,
        "curve_priority": -1 if source.curve_priority is None else source.curve_priority,
        "expiry_handle": expiry_handle,
    }


def neutral_source_state() -> dict[str, Any]:
    return {
        "active": False, "source_id": None, "owner": None,
        "target": 0.0, "target_weight": 0.0, "rate_add": 0.0,
        "rate_multiplier": 1.0, "curve": None, "curve_priority": -1,
        "expiry_handle": None,
    }


def _slot_paths(profile: FieldProfile) -> list[str]:
    base = f"$subject.{DYNAMICS_COMPONENT}.fields.{profile.field.id}"
    return [
        *[f"{base}.persistent_patches.slot_{i}" for i in range(profile.field.max_persistent_patches)],
        *[f"{base}.temporary_modifiers.slot_{i}" for i in range(profile.field.max_temporary_modifiers)],
    ]


def _effective_target(base: str, slots: list[str]) -> object:
    numerator: list[object] = [f"{base}.baseline.target"]
    denominator: list[object] = [f"{base}.baseline.target_weight"]
    for path in slots:
        numerator.append({"mul": [f"{path}.target", f"{path}.target_weight"]})
        denominator.append(f"{path}.target_weight")
    return {"div": [{"add": numerator}, {"add": denominator}]}


def _raw_rate(base: str, slots: list[str]) -> object:
    additive: list[object] = [f"{base}.baseline.rate"]
    additive.extend(f"{path}.rate_add" for path in slots)
    multiplicative: list[object] = [{"add": additive}]
    multiplicative.extend(f"{path}.rate_multiplier" for path in slots)
    return _mul(multiplicative)


def _mul(values: list[object]) -> object:
    result = values[0]
    for item in values[1:]:
        result = {"mul": [result, item]}
    return result
