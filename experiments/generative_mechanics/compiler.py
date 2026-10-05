"""Deterministic SkillSpec v0.1 to canonical PMW law compiler."""

from __future__ import annotations

import json
from typing import Any

from pmw import parse_law

from .spec import SkillSpec


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _conditions(spec: SkillSpec, event_type: str, *, triggers: bool = False) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = [
        {"event.type": {"eq": event_type}},
        {"event.source": {"eq": "$actor.id"}},
        {"event.target": {"eq": "$zone.id"}},
        {"ref": "$event.payload.skill_id", "eq": spec.id},
        {"ref": "$event.payload.skill_instance_id", "eq": "$skill.id"},
        {"ref": "$skill.skill.spec_id", "eq": spec.id},
        {"ref": "$skill.skill.owner", "eq": "$actor.id"},
    ]
    if triggers:
        result.extend({"ref": f"$zone.fields.{item.field}", item.op: item.value} for item in spec.trigger_conditions)
    return result


def _delta_effects(spec: SkillSpec, factor: float = 1.0) -> list[dict[str, Any]]:
    return [{"op": "delta", "target": f"$zone.fields.{item.field}", "value": item.delta * factor} for item in spec.effects]


def compile_skill(spec: SkillSpec) -> dict[str, Any]:
    prefix = f"gm.skill.{spec.id}"
    bindings = {
        "actor": {"kind": "entity", "requires": ["resource"]},
        "skill": {"kind": "entity", "requires": ["skill"]},
        "zone": {"kind": "entity", "requires": ["fields", "zone"]},
    }
    activation_effects = _delta_effects(spec)
    activation_effects += [
        {"op": "delta", "target": "$actor.resource.energy", "value": -spec.resource_cost},
        {"op": "delta", "target": "$skill.skill.charges", "value": -1},
    ]
    if spec.duration > 0:
        activation_effects.append({"op": "schedule_event", "event": {
            "id": "$event.payload.expiry_event_id", "type": f"{prefix}.expire",
            "time": {"add": ["$event.time", spec.duration]}, "source": "$actor.id", "target": "$zone.id",
            "payload": {"skill_id": spec.id, "skill_instance_id": "$skill.id"},
        }})
    if spec.periodic:
        for index in range(1, spec.periodic.repeats + 1):
            activation_effects.append({"op": "schedule_event", "event": {
                "id": f"$event.payload.pulse_{index:02d}_event_id", "type": f"{prefix}.pulse.{index:02d}",
                "time": {"add": ["$event.time", spec.periodic.interval * index]}, "source": "$actor.id", "target": "$zone.id",
                "payload": {"skill_id": spec.id, "skill_instance_id": "$skill.id"},
            }})
    laws: list[dict[str, Any]] = [{
        "id": f"{prefix}.activate", "mode": "event", "priority": 100,
        "bindings": bindings,
        "when": {"all": _conditions(spec, "lab.skill.activate", triggers=True) + [
            {"ref": "$actor.resource.energy", "gte": spec.resource_cost},
            {"ref": "$skill.skill.charges", "gt": 0},
        ]},
        "effects": activation_effects,
    }]
    if spec.duration > 0:
        laws.append({
            "id": f"{prefix}.expire", "mode": "event", "priority": 100,
            "bindings": bindings, "when": {"all": _conditions(spec, f"{prefix}.expire")},
            "effects": _delta_effects(spec, -1.0),
        })
    if spec.periodic:
        for index in range(1, spec.periodic.repeats + 1):
            laws.append({
                "id": f"{prefix}.pulse.{index:02d}", "mode": "event", "priority": 100,
                "bindings": bindings, "when": {"all": _conditions(spec, f"{prefix}.pulse.{index:02d}")},
                "effects": _delta_effects(spec),
            })
    document = {"schema_version": "2.0", "laws": laws}
    for law in laws:
        parse_law(law)
    return document
