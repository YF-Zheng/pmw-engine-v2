"""Matched direct-outcome baseline for generation protocol v0.2.

The baseline intentionally writes only ``direct_outcome`` (plus bookkeeping on
the actor/skill entities). Generic ``gm.world.*`` laws never read that surface.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from pmw import parse_law

from .generation import GenerationContractError
from .spec import ID_PATTERN
from .substrate import CHANNEL_SET


OUTCOME_FIELDS = ("damage", "heal", "buff", "debuff")
MATCHED_FIELDS = frozenset({
    "id", "name", "target_scope", "effects", "duration", "periodic",
    "trigger_conditions", "resource_cost", "charges", "slot_cost",
})


@dataclass(frozen=True, slots=True)
class DirectOutcomeEffect:
    field: str
    delta: float


@dataclass(frozen=True, slots=True)
class PublicTrigger:
    field: str
    op: str
    value: float


@dataclass(frozen=True, slots=True)
class MatchedPeriodic:
    interval: float
    repeats: int


@dataclass(frozen=True, slots=True)
class MatchedDirectOutcomeSpec:
    id: str
    name: str
    target_scope: str
    effects: tuple[DirectOutcomeEffect, ...]
    duration: float
    periodic: MatchedPeriodic | None
    trigger_conditions: tuple[PublicTrigger, ...]
    resource_cost: float
    charges: int
    slot_cost: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "target_scope": self.target_scope,
            "effects": [asdict(item) for item in self.effects],
            "duration": self.duration,
            "periodic": asdict(self.periodic) if self.periodic else None,
            "trigger_conditions": [asdict(item) for item in self.trigger_conditions],
            "resource_cost": self.resource_cost,
            "charges": self.charges,
            "slot_cost": self.slot_cost,
        }


def _number(value: Any, path: str, low: float, high: float, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GenerationContractError(f"{path}: must be a finite number")
    value = float(value)
    if value < low or value > high or positive and value <= 0:
        raise GenerationContractError(f"{path}: out of range")
    return value


def validate_matched_direct_outcome(raw: Any) -> MatchedDirectOutcomeSpec:
    if not isinstance(raw, dict) or set(raw) != MATCHED_FIELDS:
        unknown = sorted(set(raw) - MATCHED_FIELDS) if isinstance(raw, dict) else []
        missing = sorted(MATCHED_FIELDS - set(raw)) if isinstance(raw, dict) else sorted(MATCHED_FIELDS)
        raise GenerationContractError(
            f"response.mechanic: strict fields required; unknown={unknown} missing={missing}"
        )
    if not isinstance(raw["id"], str) or not ID_PATTERN.fullmatch(raw["id"]):
        raise GenerationContractError("response.mechanic.id: invalid identifier")
    if raw["id"].startswith(("gm_", "pmw_", "lab_")):
        raise GenerationContractError("response.mechanic.id: reserved identifier")
    if not isinstance(raw["name"], str) or not raw["name"].strip() or len(raw["name"]) > 80:
        raise GenerationContractError("response.mechanic.name: invalid name")
    if raw["target_scope"] != "zone":
        raise GenerationContractError("response.mechanic.target_scope: must be zone")
    if not isinstance(raw["effects"], list) or not raw["effects"]:
        raise GenerationContractError("response.mechanic.effects: must be a non-empty list")
    effects: list[DirectOutcomeEffect] = []
    seen: set[str] = set()
    for index, item in enumerate(raw["effects"]):
        if not isinstance(item, dict) or set(item) != {"field", "delta"}:
            raise GenerationContractError(f"response.mechanic.effects[{index}]: invalid fields")
        if item["field"] not in OUTCOME_FIELDS or item["field"] in seen:
            raise GenerationContractError(f"response.mechanic.effects[{index}].field: invalid or duplicate")
        seen.add(item["field"])
        effects.append(DirectOutcomeEffect(
            item["field"], _number(item["delta"], f"response.mechanic.effects[{index}].delta", -1, 1),
        ))
    duration = _number(raw["duration"], "response.mechanic.duration", 0, 300)
    periodic = None
    if raw["periodic"] is not None:
        item = raw["periodic"]
        if not isinstance(item, dict) or set(item) != {"interval", "repeats"}:
            raise GenerationContractError("response.mechanic.periodic: invalid fields")
        interval = _number(item["interval"], "response.mechanic.periodic.interval", 0, 300, positive=True)
        repeats = item["repeats"]
        if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 12:
            raise GenerationContractError("response.mechanic.periodic.repeats: must be in [1, 12]")
        periodic = MatchedPeriodic(interval, repeats)
    if duration > 0 and periodic is not None:
        raise GenerationContractError("response.mechanic.periodic: mutually exclusive with duration")
    if not isinstance(raw["trigger_conditions"], list):
        raise GenerationContractError("response.mechanic.trigger_conditions: must be a list")
    triggers: list[PublicTrigger] = []
    for index, item in enumerate(raw["trigger_conditions"]):
        if not isinstance(item, dict) or set(item) != {"field", "op", "value"}:
            raise GenerationContractError(f"response.mechanic.trigger_conditions[{index}]: invalid fields")
        if item["field"] not in CHANNEL_SET or item["op"] not in {"eq", "neq", "gt", "gte", "lt", "lte"}:
            raise GenerationContractError(f"response.mechanic.trigger_conditions[{index}]: invalid condition")
        triggers.append(PublicTrigger(
            item["field"], item["op"],
            _number(item["value"], f"response.mechanic.trigger_conditions[{index}].value", 0, 1),
        ))
    cost = _number(raw["resource_cost"], "response.mechanic.resource_cost", 0, 100)
    charges, slot_cost = raw["charges"], raw["slot_cost"]
    if isinstance(charges, bool) or not isinstance(charges, int) or not 1 <= charges <= 99:
        raise GenerationContractError("response.mechanic.charges: must be in [1, 99]")
    if isinstance(slot_cost, bool) or slot_cost not in (1, 2):
        raise GenerationContractError("response.mechanic.slot_cost: must be 1 or 2")
    return MatchedDirectOutcomeSpec(
        raw["id"], raw["name"].strip(), "zone", tuple(effects), duration, periodic,
        tuple(triggers), cost, charges, slot_cost,
    )


def compile_matched_direct_outcome(spec: MatchedDirectOutcomeSpec) -> dict[str, Any]:
    """Compile to laws whose semantic writes are isolated from world channels."""
    prefix = f"gm.baseline.matched.{spec.id}"
    bindings = {
        "actor": {"kind": "entity", "requires": ["resource"]},
        "skill": {"kind": "entity", "requires": ["skill"]},
        "zone": {"kind": "entity", "requires": ["direct_outcome", "fields", "zone"]},
    }
    common: list[dict[str, Any]] = [
        {"event.source": {"eq": "$actor.id"}},
        {"event.target": {"eq": "$zone.id"}},
        {"ref": "$event.payload.skill_id", "eq": spec.id},
        {"ref": "$event.payload.skill_instance_id", "eq": "$skill.id"},
        {"ref": "$skill.skill.spec_id", "eq": spec.id},
        {"ref": "$skill.skill.owner", "eq": "$actor.id"},
    ]
    trigger_checks = [
        {"ref": f"$zone.fields.{item.field}", item.op: item.value}
        for item in spec.trigger_conditions
    ]
    effects: list[dict[str, Any]] = [
        {"op": "delta", "target": f"$zone.direct_outcome.{item.field}", "value": item.delta}
        for item in spec.effects
    ]
    effects.extend([
        {"op": "delta", "target": "$actor.resource.energy", "value": -spec.resource_cost},
        {"op": "delta", "target": "$skill.skill.charges", "value": -1},
    ])
    if spec.duration > 0:
        effects.append({"op": "schedule_event", "event": {
            "id": "$event.payload.expiry_event_id",
            "type": f"{prefix}.expire",
            "time": {"add": ["$event.time", spec.duration]},
            "source": "$actor.id", "target": "$zone.id",
            "payload": {"skill_id": spec.id, "skill_instance_id": "$skill.id"},
        }})
    if spec.periodic:
        for index in range(1, spec.periodic.repeats + 1):
            effects.append({"op": "schedule_event", "event": {
                "id": f"$event.payload.pulse_{index:02d}_event_id",
                "type": f"{prefix}.pulse.{index:02d}",
                "time": {"add": ["$event.time", spec.periodic.interval * index]},
                "source": "$actor.id", "target": "$zone.id",
                "payload": {"skill_id": spec.id, "skill_instance_id": "$skill.id"},
            }})
    laws: list[dict[str, Any]] = [{
        "id": f"{prefix}.activate", "mode": "event", "priority": 100,
        "bindings": bindings,
        "when": {"all": [
            {"event.type": {"eq": "lab.skill.activate"}}, *common, *trigger_checks,
            {"ref": "$actor.resource.energy", "gte": spec.resource_cost},
            {"ref": "$skill.skill.charges", "gt": 0},
        ]},
        "effects": effects,
    }]
    if spec.duration > 0:
        laws.append({
            "id": f"{prefix}.expire", "mode": "event", "priority": 100,
            "bindings": bindings,
            "when": {"all": [{"event.type": {"eq": f"{prefix}.expire"}}, *common]},
            "effects": [
                {"op": "delta", "target": f"$zone.direct_outcome.{item.field}",
                 "value": -item.delta}
                for item in spec.effects
            ],
        })
    if spec.periodic:
        for index in range(1, spec.periodic.repeats + 1):
            laws.append({
                "id": f"{prefix}.pulse.{index:02d}", "mode": "event", "priority": 100,
                "bindings": bindings,
                "when": {"all": [{"event.type": {"eq": f"{prefix}.pulse.{index:02d}"}}, *common]},
                "effects": [
                    {"op": "delta", "target": f"$zone.direct_outcome.{item.field}",
                     "value": item.delta}
                    for item in spec.effects
                ],
            })
    for law in laws:
        parse_law(law)
    return {"schema_version": "2.0", "laws": laws}


def semantic_write_targets(compiled: dict[str, Any]) -> tuple[str, ...]:
    """Expose write targets for static isolation audits."""
    return tuple(
        effect["target"]
        for law in compiled["laws"]
        for effect in law["effects"]
        if effect["op"] == "delta"
    )
