"""Deterministic Area ecology regimes and sustained-threshold transitions."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping

from pmw import parse_law

from .contracts import CURVES, GameplayContractError
from .dynamics import DYNAMICS_COMPONENT, WORLD_TICK_EVENT


ECOLOGY_COMPONENT = "pmw_gameplay_ecology"
ECOLOGY_CHANGED_EVENT = "pmw.v04.ecology.changed"
_ID = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")


@dataclass(frozen=True, slots=True)
class EcologyBaseline:
    field_id: str
    target: float
    rate: float
    curve: str


@dataclass(frozen=True, slots=True)
class EcologyRegime:
    id: str
    label: str
    clue: str
    baselines: tuple[EcologyBaseline, ...]


@dataclass(frozen=True, slots=True)
class EcologyTransition:
    id: str
    source: str
    target: str
    field_id: str
    comparator: str
    threshold: float
    window_ticks: int
    clue: str


@dataclass(frozen=True, slots=True)
class EcologySpec:
    id: str
    label: str
    initial_regime: str
    sample_count: int
    regimes: tuple[EcologyRegime, ...]
    transitions: tuple[EcologyTransition, ...]
    canonical_hash: str


@dataclass(frozen=True, slots=True)
class EcologyPlan:
    spec: EcologySpec
    seed: int
    reachable_regimes: tuple[str, ...]
    transitions: tuple[EcologyTransition, ...]


def parse_ecology_spec(raw: Any, path: str = "$.ecology") -> EcologySpec:
    required = {"protocol", "id", "label", "initial_regime", "sample_count", "regimes", "transitions"}
    if not isinstance(raw, dict) or set(raw) != required or raw.get("protocol") != "pmw-gameplay-v0.4":
        raise GameplayContractError(f"{path} has missing/unknown fields or invalid protocol")
    ecology_id = _identifier(raw["id"], f"{path}.id")
    if not isinstance(raw["label"], str) or not raw["label"].strip():
        raise GameplayContractError(f"{path}.label is invalid")
    if not isinstance(raw["regimes"], list) or not raw["regimes"]:
        raise GameplayContractError(f"{path}.regimes must be non-empty")
    regimes = tuple(_regime(item, f"{path}.regimes[{i}]") for i, item in enumerate(raw["regimes"]))
    if len({item.id for item in regimes}) != len(regimes):
        raise GameplayContractError(f"{path}.regimes contains duplicates")
    regime_ids = {item.id for item in regimes}
    initial = _identifier(raw["initial_regime"], f"{path}.initial_regime")
    if initial not in regime_ids:
        raise GameplayContractError(f"{path}.initial_regime is unknown")
    count = raw["sample_count"]
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= len(regimes):
        raise GameplayContractError(f"{path}.sample_count is invalid")
    if not isinstance(raw["transitions"], list):
        raise GameplayContractError(f"{path}.transitions must be a list")
    transitions = tuple(_transition(item, regime_ids, f"{path}.transitions[{i}]") for i, item in enumerate(raw["transitions"]))
    if len({item.id for item in transitions}) != len(transitions):
        raise GameplayContractError(f"{path}.transitions contains duplicates")
    outgoing: dict[str, int] = {}
    for item in transitions:
        outgoing[item.source] = outgoing.get(item.source, 0) + 1
    if any(value > 1 for value in outgoing.values()):
        raise GameplayContractError("Gate 3 ecology permits one unambiguous outgoing transition per regime")
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return EcologySpec(ecology_id, raw["label"], initial, count, regimes, transitions,
                       hashlib.sha256(canonical).hexdigest())


def sample_ecology(spec: EcologySpec, seed: int) -> EcologyPlan:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise GameplayContractError("ecology seed must be a non-negative integer")
    chosen = [spec.initial_regime]
    transition_map = {item.source: item for item in spec.transitions}
    while len(chosen) < spec.sample_count:
        candidates = [transition_map[item] for item in chosen if item in transition_map and transition_map[item].target not in chosen]
        if not candidates:
            raise GameplayContractError("sample_count is not reachable from the initial ecology regime")
        candidates.sort(key=lambda item: hashlib.sha256(f"{seed}:{item.id}".encode()).hexdigest())
        chosen.append(candidates[0].target)
    allowed = set(chosen)
    transitions = tuple(item for item in spec.transitions if item.source in allowed and item.target in allowed)
    return EcologyPlan(spec, seed, tuple(chosen), transitions)


def ecology_component(plan: EcologyPlan) -> dict[str, Any]:
    return {
        "spec_id": plan.spec.id, "spec_hash": plan.spec.canonical_hash,
        "seed": plan.seed, "current": plan.spec.initial_regime,
        "reachable": list(plan.reachable_regimes),
        "counters": {item.id: 0 for item in plan.transitions},
        "clues": {item.id: item.clue for item in plan.transitions},
    }


def build_ecology_laws(bindings: Mapping[str, EcologyPlan]) -> tuple[dict, ...]:
    laws: list[dict] = []
    for area_id, plan in sorted(bindings.items()):
        regimes = {item.id: item for item in plan.spec.regimes}
        for transition in plan.transitions:
            laws.extend(_transition_laws(area_id, plan, transition, regimes[transition.target]))
    result = tuple(sorted(laws, key=lambda row: row["id"]))
    for law in result:
        parse_law(law)
    return result


def _transition_laws(area_id: str, plan: EcologyPlan, transition: EcologyTransition,
                     target: EcologyRegime) -> list[dict]:
    prefix = f"pmw.v04.ecology.{area_id}.{plan.spec.id}.{transition.id}"
    root = f"$area.{ECOLOGY_COMPONENT}"
    field = f"$area.{DYNAMICS_COMPONENT}.fields.{transition.field_id}"
    bindings = {"area": {"kind": "entity", "requires": ["pmw_gameplay_area", ECOLOGY_COMPONENT, DYNAMICS_COMPONENT]}}
    base = [{"event.type": {"eq": WORLD_TICK_EVENT}}, {"ref": "$area.id", "eq": area_id},
            {"ref": f"{root}.spec_hash", "eq": plan.spec.canonical_hash},
            {"ref": f"{root}.current", "eq": transition.source}]
    threshold = {"ref": f"{field}.value", transition.comparator: transition.threshold}
    opposite = {"ref": f"{field}.value", "lt" if transition.comparator == "gte" else "gt": transition.threshold}
    counter = f"{root}.counters.{transition.id}"
    changes = [
        {"op": "set", "target": f"{root}.current", "value": transition.target},
        {"op": "set", "target": "$area.pmw_gameplay_area.ecology_state", "value": transition.target},
    ]
    for item in target.baselines:
        baseline = f"$area.{DYNAMICS_COMPONENT}.fields.{item.field_id}.baseline"
        changes.extend([
            {"op": "set", "target": f"{baseline}.target", "value": item.target},
            {"op": "set", "target": f"{baseline}.rate", "value": item.rate},
            {"op": "set", "target": f"{baseline}.curve", "value": item.curve},
        ])
    for item in plan.transitions:
        changes.append({"op": "set", "target": f"{root}.counters.{item.id}", "value": 0})
    changes.append({"op": "emit_event", "event": {
        "type": ECOLOGY_CHANGED_EVENT, "time": "$event.time", "source": plan.spec.id, "target": "$area.id",
        "payload": {"ecology_id": plan.spec.id, "from": transition.source, "to": transition.target,
                    "transition_id": transition.id, "clue": transition.clue, "spec_hash": plan.spec.canonical_hash},
    }})
    return [
        {"id": f"{prefix}.progress", "mode": "event", "priority": 100, "bindings": bindings,
         "when": {"all": [*base, threshold, {"ref": counter, "lt": transition.window_ticks - 1}]},
         "effects": [{"op": "delta", "target": counter, "value": 1}]},
        {"id": f"{prefix}.commit", "mode": "event", "priority": 100, "bindings": bindings,
         "when": {"all": [*base, threshold, {"ref": counter, "eq": transition.window_ticks - 1}]},
         "effects": changes},
        {"id": f"{prefix}.reset", "mode": "event", "priority": 100, "bindings": bindings,
         "when": {"all": [*base, opposite, {"ref": counter, "gt": 0}]},
         "effects": [{"op": "set", "target": counter, "value": 0}]},
    ]


def _regime(raw: Any, path: str) -> EcologyRegime:
    if not isinstance(raw, dict) or set(raw) != {"id", "label", "clue", "baselines"}:
        raise GameplayContractError(f"{path} is invalid")
    for key in ("label", "clue"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            raise GameplayContractError(f"{path}.{key} is invalid")
    if not isinstance(raw["baselines"], list) or not raw["baselines"]:
        raise GameplayContractError(f"{path}.baselines must be non-empty")
    baselines = tuple(_baseline(item, f"{path}.baselines[{i}]") for i, item in enumerate(raw["baselines"]))
    if len({item.field_id for item in baselines}) != len(baselines):
        raise GameplayContractError(f"{path}.baselines contains duplicate fields")
    return EcologyRegime(_identifier(raw["id"], f"{path}.id"), raw["label"], raw["clue"], baselines)


def _baseline(raw: Any, path: str) -> EcologyBaseline:
    if not isinstance(raw, dict) or set(raw) != {"field_id", "target", "rate", "curve"}:
        raise GameplayContractError(f"{path} is invalid")
    target, rate = _number(raw["target"], f"{path}.target"), _number(raw["rate"], f"{path}.rate")
    if rate < 0 or raw["curve"] not in CURVES:
        raise GameplayContractError(f"{path} rate/curve is invalid")
    return EcologyBaseline(_identifier(raw["field_id"], f"{path}.field_id"), target, rate, raw["curve"])


def _transition(raw: Any, regimes: set[str], path: str) -> EcologyTransition:
    required = {"id", "from", "to", "condition", "window_ticks", "clue"}
    if not isinstance(raw, dict) or set(raw) != required:
        raise GameplayContractError(f"{path} is invalid")
    condition = raw["condition"]
    if not isinstance(condition, dict) or set(condition) != {"field_id", "comparator", "threshold"}:
        raise GameplayContractError(f"{path}.condition is invalid")
    if condition["comparator"] not in {"gte", "lte"}:
        raise GameplayContractError(f"{path}.condition.comparator must be gte or lte")
    source, target = raw["from"], raw["to"]
    if source not in regimes or target not in regimes or source == target:
        raise GameplayContractError(f"{path} has invalid regime endpoints")
    window = raw["window_ticks"]
    if isinstance(window, bool) or not isinstance(window, int) or not 1 <= window <= 10_000:
        raise GameplayContractError(f"{path}.window_ticks is invalid")
    if not isinstance(raw["clue"], str) or not raw["clue"].strip():
        raise GameplayContractError(f"{path}.clue is invalid")
    return EcologyTransition(_identifier(raw["id"], f"{path}.id"), source, target,
                              _identifier(condition["field_id"], f"{path}.condition.field_id"),
                              condition["comparator"], _number(condition["threshold"], f"{path}.condition.threshold"),
                              window, raw["clue"])


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GameplayContractError(f"{path} must be finite numeric")
    return float(value)


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise GameplayContractError(f"{path} is invalid")
    return value
