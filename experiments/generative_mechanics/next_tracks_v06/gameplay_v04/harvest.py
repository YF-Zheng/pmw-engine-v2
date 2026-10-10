"""Resource harvest actions with independent time, yield, and world depletion."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping

from pmw import Event, parse_law

from .actions import ACTOR_COMPONENT, ActionRegistry, ActionRequest
from .conditions import evaluate_condition
from .contracts import GameplayContractError
from .dynamics import DYNAMICS_COMPONENT


RESOURCE_COMPONENT = "pmw_gameplay_resources"
MATERIAL_INVENTORY_COMPONENT = "pmw_gameplay_material_inventory"
HARVEST_EVENT = "pmw.v04.resource.harvest"
RESOURCE_HARVESTED_EVENT = "pmw.v04.resource_harvested"
_ID = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")


@dataclass(frozen=True, slots=True)
class OverharvestSpec:
    below: float
    target_delta: float
    rate_delta: float


@dataclass(frozen=True, slots=True)
class LuckyHarvestSpec:
    permission: str
    duration_delta: int
    yield_delta: float


@dataclass(frozen=True, slots=True)
class HarvestSpec:
    id: str
    label: str
    action_id: str
    source_kind: str
    source_id: str
    material_id: str
    threshold: float
    consumption: float
    base_yield: float
    overharvest: OverharvestSpec | None
    lucky: LuckyHarvestSpec | None
    canonical_hash: str


@dataclass(frozen=True, slots=True)
class HarvestRequest:
    request_id: str
    actor_id: str
    harvest_id: str
    lucky: bool = False


@dataclass(frozen=True, slots=True)
class HarvestOutcome:
    request: HarvestRequest
    duration: int
    yield_amount: float
    consumption: float
    event_result: Any


def parse_harvest_spec(raw: Any, path: str = "$.harvest") -> HarvestSpec:
    required = {"protocol", "id", "label", "action_id", "source", "material_id", "threshold",
                "consumption", "base_yield", "overharvest", "lucky"}
    if not isinstance(raw, dict) or set(raw) != required or raw.get("protocol") != "pmw-gameplay-v0.4":
        raise GameplayContractError(f"{path} has missing/unknown fields or invalid protocol")
    source = raw["source"]
    if not isinstance(source, dict) or set(source) != {"kind", "id"} or source["kind"] not in {"abundance", "stock"}:
        raise GameplayContractError(f"{path}.source is invalid")
    threshold = _positive(raw["threshold"], f"{path}.threshold", allow_zero=True)
    consumption = _positive(raw["consumption"], f"{path}.consumption")
    base_yield = _positive(raw["base_yield"], f"{path}.base_yield")
    over = raw["overharvest"]
    overharvest = None
    if over is not None:
        if not isinstance(over, dict) or set(over) != {"below", "target_delta", "rate_delta"}:
            raise GameplayContractError(f"{path}.overharvest is invalid")
        below = _positive(over["below"], f"{path}.overharvest.below", allow_zero=True)
        target_delta = _number(over["target_delta"], f"{path}.overharvest.target_delta")
        rate_delta = _number(over["rate_delta"], f"{path}.overharvest.rate_delta")
        if target_delta > 0 or rate_delta > 0:
            raise GameplayContractError(f"{path}.overharvest may only degrade target/rate")
        if source["kind"] != "abundance":
            raise GameplayContractError(f"{path}.overharvest requires an abundance Field")
        overharvest = OverharvestSpec(below, target_delta, rate_delta)
    lucky = raw["lucky"]
    lucky_spec = None
    if lucky is not None:
        if not isinstance(lucky, dict) or set(lucky) != {"permission", "duration_delta", "yield_delta"}:
            raise GameplayContractError(f"{path}.lucky is invalid")
        if lucky["duration_delta"] != -1 or _number(lucky["yield_delta"], f"{path}.lucky.yield_delta") != 1.0:
            raise GameplayContractError("Gate 3 lucky harvest is exactly -1 time and +1 yield")
        lucky_spec = LuckyHarvestSpec(_identifier(lucky["permission"], f"{path}.lucky.permission"), -1, 1.0)
    for key in ("id", "action_id", "material_id"):
        _identifier(raw[key], f"{path}.{key}")
    if not isinstance(raw["label"], str) or not raw["label"].strip():
        raise GameplayContractError(f"{path}.label is invalid")
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return HarvestSpec(raw["id"], raw["label"], raw["action_id"], source["kind"],
                       _identifier(source["id"], f"{path}.source.id"), raw["material_id"], threshold,
                       consumption, base_yield, overharvest, lucky_spec,
                       hashlib.sha256(canonical).hexdigest())


def resource_component(specs: tuple[HarvestSpec, ...], *, stock_amounts: Mapping[str, float] | None = None) -> dict[str, Any]:
    if len({item.id for item in specs}) != len(specs):
        raise GameplayContractError("duplicate HarvestSpec")
    stock_amounts = stock_amounts or {}
    stocks = {}
    for item in specs:
        if item.source_kind == "stock":
            if item.source_id not in stock_amounts:
                raise GameplayContractError(f"missing initial stock {item.source_id!r}")
            amount = _positive(stock_amounts[item.source_id], f"stock.{item.source_id}", allow_zero=True)
            stocks[item.source_id] = {"amount": amount}
    return {"spec_hashes": {item.id: item.canonical_hash for item in specs}, "stocks": stocks}


def material_inventory_component(material_ids: tuple[str, ...]) -> dict[str, Any]:
    if len(set(material_ids)) != len(material_ids) or any(_ID.fullmatch(item) is None for item in material_ids):
        raise GameplayContractError("material inventory IDs are invalid")
    return {"quantities": {item: 0.0 for item in sorted(material_ids)}}


def build_harvest_laws(bindings: Mapping[str, tuple[HarvestSpec, ...]]) -> tuple[dict, ...]:
    laws: list[dict] = []
    for area_id, specs in sorted(bindings.items()):
        for spec in sorted(specs, key=lambda row: row.id):
            compiled = _harvest_law(area_id, spec)
            laws.extend(compiled.pop("_variants")) if "_variants" in compiled else laws.append(compiled)
    result = tuple(sorted(laws, key=lambda row: row["id"]))
    for law in result:
        parse_law(law)
    return result


def resolve_harvest(session, registry: ActionRegistry, spec: HarvestSpec, request: HarvestRequest,
                    *, permissions: tuple[str, ...] = ()) -> HarvestOutcome:
    if not _ID.fullmatch(request.request_id) or not _ID.fullmatch(request.actor_id) or request.harvest_id != spec.id:
        raise GameplayContractError("HarvestRequest is invalid")
    if not isinstance(request.lucky, bool):
        raise GameplayContractError("HarvestRequest.lucky must be boolean")
    action = registry.actions.get(spec.action_id)
    if action is None or action.action_type != "harvest":
        raise GameplayContractError("HarvestSpec action is not registered as harvest")
    actor_entity = session.state.entities.get(request.actor_id)
    if actor_entity is None or ACTOR_COMPONENT not in actor_entity.components or MATERIAL_INVENTORY_COMPONENT not in actor_entity.components:
        raise GameplayContractError("harvester is missing Actor/material inventory state")
    area_id = _current_area(session, request.actor_id)
    area = session.state.entities[area_id]
    hashes = area.components.get(RESOURCE_COMPONENT, {}).get("spec_hashes", {})
    if hashes.get(spec.id) != spec.canonical_hash:
        raise GameplayContractError("HarvestSpec is not installed in the current Area")
    actor = actor_entity.components[ACTOR_COMPONENT]
    duration, mana = action.cost.duration, action.cost.mana
    context = {"self": actor, "target_actor": {}, "current_area": {"fields": area.components.get(DYNAMICS_COMPONENT, {}).get("fields", {})}}
    for modifier in action.cost_modifiers:
        if evaluate_condition(modifier.condition, context):
            duration += modifier.duration_add; mana += modifier.mana_add
    if actor["mana"] < max(0.0, mana):
        raise GameplayContractError("insufficient mana for harvest")
    yield_amount = spec.base_yield
    if request.lucky:
        if spec.lucky is None or spec.lucky.permission not in permissions:
            raise GameplayContractError("lucky harvest is not authorized")
        duration += spec.lucky.duration_delta
        yield_amount += spec.lucky.yield_delta
    duration = max(1, duration)
    before_amount, field = _resource_state(area, spec)
    if before_amount < spec.threshold or before_amount < spec.consumption:
        raise GameplayContractError("resource is below the harvest threshold")
    after_amount = before_amount - spec.consumption
    inventory = actor_entity.components[MATERIAL_INVENTORY_COMPONENT]["quantities"]
    if spec.material_id not in inventory:
        raise GameplayContractError("material is not declared in Actor inventory")
    before_material = inventory[spec.material_id]
    degrade = (
        spec.overharvest is not None
        and after_amount < spec.overharvest.below
        and not math.isclose(after_amount, spec.overharvest.below, rel_tol=0.0, abs_tol=1e-12)
    )
    payload = {
        "harvest_id": spec.id, "spec_hash": spec.canonical_hash, "action_id": action.id,
        "action_hash": action.canonical_hash, "area_id": area_id, "source_kind": spec.source_kind,
        "source_id": spec.source_id, "material_id": spec.material_id,
        "before_amount": before_amount, "after_amount": after_amount,
        "before_material": before_material, "after_material": before_material + yield_amount,
        "consumption": spec.consumption, "yield": yield_amount, "duration": duration,
        "mana_after": actor["mana"] - max(0.0, mana), "degrade": degrade,
        "baseline_target_after": None, "baseline_rate_after": None,
    }
    if degrade:
        baseline = field["baseline"]
        payload["baseline_target_after"] = max(field["domain_min"], baseline["target"] + spec.overharvest.target_delta)
        payload["baseline_rate_after"] = max(0.0, baseline["rate"] + spec.overharvest.rate_delta)
    before = session.state.to_dict()
    result = session.runtime.run_event(Event(
        f"pmw:v04:harvest:{request.request_id}", HARVEST_EVENT, session.state.sim_time,
        request.actor_id, area_id, payload,
    ))
    if not result.changed:
        if session.state.to_dict() != before:
            raise GameplayContractError("failed harvest mutated state")
        raise GameplayContractError("harvest did not match installed Law")
    return HarvestOutcome(request, duration, yield_amount, spec.consumption, result)


def _harvest_law(area_id: str, spec: HarvestSpec) -> dict:
    bindings = {
        "actor": {"kind": "entity", "requires": [ACTOR_COMPONENT, MATERIAL_INVENTORY_COMPONENT]},
        "area": {"kind": "entity", "requires": ["pmw_gameplay_area", RESOURCE_COMPONENT] + ([DYNAMICS_COMPONENT] if spec.source_kind == "abundance" else [])},
        "location": {"kind": "relation", "type": "located_in", "source": "$actor", "target": "$area"},
    }
    amount_path = (f"$area.{DYNAMICS_COMPONENT}.fields.{spec.source_id}.value" if spec.source_kind == "abundance"
                   else f"$area.{RESOURCE_COMPONENT}.stocks.{spec.source_id}.amount")
    conditions = [
        {"event.type": {"eq": HARVEST_EVENT}}, {"ref": "$actor.id", "eq": "$event.source"},
        {"ref": "$area.id", "eq": area_id}, {"ref": "$area.id", "eq": "$event.target"},
        {"ref": "$event.payload.harvest_id", "eq": spec.id},
        {"ref": "$event.payload.spec_hash", "eq": spec.canonical_hash},
        {"ref": f"$area.{RESOURCE_COMPONENT}.spec_hashes.{spec.id}", "eq": spec.canonical_hash},
        {"ref": amount_path, "eq": "$event.payload.before_amount"},
        {"ref": f"$actor.{MATERIAL_INVENTORY_COMPONENT}.quantities.{spec.material_id}", "eq": "$event.payload.before_material"},
    ]
    effects = [
        {"op": "set", "target": amount_path, "value": "$event.payload.after_amount"},
        {"op": "set", "target": f"$actor.{MATERIAL_INVENTORY_COMPONENT}.quantities.{spec.material_id}",
         "value": "$event.payload.after_material"},
        {"op": "set", "target": f"$actor.{ACTOR_COMPONENT}.mana", "value": "$event.payload.mana_after"},
        {"op": "set", "target": f"$actor.{ACTOR_COMPONENT}.last_action_duration", "value": "$event.payload.duration"},
        {"op": "emit_event", "event": {"type": RESOURCE_HARVESTED_EVENT, "time": "$event.time",
         "source": "$actor.id", "target": "$area.id", "payload": {"harvest_id": spec.id,
         "material_id": spec.material_id, "yield": "$event.payload.yield", "consumption": "$event.payload.consumption"}}},
    ]
    if spec.overharvest is not None:
        baseline = f"$area.{DYNAMICS_COMPONENT}.fields.{spec.source_id}.baseline"
        # Separate variants keep absent nullable payloads out of numeric state writes.
        normal = {"id": f"pmw.v04.harvest.{area_id}.{spec.id}.normal", "mode": "event", "priority": 100,
                  "bindings": bindings, "when": {"all": [*conditions, {"ref": "$event.payload.degrade", "eq": False}]},
                  "effects": effects}
        degraded = {"id": f"pmw.v04.harvest.{area_id}.{spec.id}.degraded", "mode": "event", "priority": 100,
                    "bindings": {**bindings, "area": {"kind": "entity", "requires": ["pmw_gameplay_area", RESOURCE_COMPONENT, DYNAMICS_COMPONENT]}},
                    "when": {"all": [*conditions, {"ref": "$event.payload.degrade", "eq": True}]},
                    "effects": [*effects,
                        {"op": "set", "target": f"{baseline}.target", "value": "$event.payload.baseline_target_after"},
                        {"op": "set", "target": f"{baseline}.rate", "value": "$event.payload.baseline_rate_after"}]}
        # Returned through the private multi-law marker consumed by build_harvest_laws.
        return {"_variants": [normal, degraded]}
    return {"id": f"pmw.v04.harvest.{area_id}.{spec.id}", "mode": "event", "priority": 100,
            "bindings": bindings, "when": {"all": conditions}, "effects": effects}


def _current_area(session, actor_id: str) -> str:
    rows = [item.target for item in session.state.relations.values() if item.type == "located_in" and item.source == actor_id]
    if len(rows) != 1:
        raise GameplayContractError("harvester must be in exactly one Area")
    return rows[0]


def _resource_state(area, spec: HarvestSpec) -> tuple[float, dict | None]:
    if spec.source_kind == "stock":
        try: return float(area.components[RESOURCE_COMPONENT]["stocks"][spec.source_id]["amount"]), None
        except KeyError as exc: raise GameplayContractError("harvest stock is unavailable") from exc
    try:
        field = area.components[DYNAMICS_COMPONENT]["fields"][spec.source_id]
        return float(field["value"]), field
    except KeyError as exc:
        raise GameplayContractError("harvest abundance Field is unavailable") from exc


def _positive(value: Any, path: str, *, allow_zero: bool = False) -> float:
    number = _number(value, path)
    if (number < 0) if allow_zero else (number <= 0):
        raise GameplayContractError(f"{path} must be {'non-negative' if allow_zero else 'positive'}")
    return number


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GameplayContractError(f"{path} must be finite numeric")
    return float(value)


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise GameplayContractError(f"{path} is invalid")
    return value
