"""Strict SkillSpec v0.1 data model and validator."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any

from .substrate import CHANNEL_SET

TOP_LEVEL_FIELDS = frozenset({
    "id", "name", "target_scope", "effects", "duration", "periodic",
    "trigger_conditions", "resource_cost", "charges", "slot_cost",
})
TARGET_SCOPES = frozenset({"zone"})
ID_PATTERN = re.compile(r"[a-z][a-z0-9_]{1,47}")
MAX_ABS_DELTA = 1.0
MAX_DURATION = 300.0
MAX_PERIODIC_REPEATS = 12
MAX_RESOURCE_COST = 100.0


class SkillSpecError(ValueError):
    """Raised when untrusted generated skill data violates SkillSpec v0.1."""


@dataclass(frozen=True, slots=True)
class FieldEffect:
    field: str
    delta: float


@dataclass(frozen=True, slots=True)
class TriggerCondition:
    field: str
    op: str
    value: float


@dataclass(frozen=True, slots=True)
class Periodic:
    interval: float
    repeats: int


@dataclass(frozen=True, slots=True)
class SkillSpec:
    id: str
    name: str
    target_scope: str
    effects: tuple[FieldEffect, ...]
    duration: float
    periodic: Periodic | None
    trigger_conditions: tuple[TriggerCondition, ...]
    resource_cost: float
    charges: int
    slot_cost: int


def _fail(path: str, message: str) -> None:
    raise SkillSpecError(f"{path}: {message}")


def _number(value: Any, path: str, *, low: float, high: float, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(path, "must be a finite number")
    result = float(value)
    if result < low or result > high or positive and result <= 0:
        _fail(path, f"must be in {'(' if positive else '['}{low}, {high}]")
    return result


def validate_skill(raw: Any) -> SkillSpec:
    if not isinstance(raw, dict):
        _fail("$", "must be an object")
    unknown = set(raw) - TOP_LEVEL_FIELDS
    missing = TOP_LEVEL_FIELDS - set(raw)
    if unknown or missing:
        _fail("$", f"strict fields required; unknown={sorted(unknown)} missing={sorted(missing)}")
    skill_id = raw["id"]
    if not isinstance(skill_id, str) or not ID_PATTERN.fullmatch(skill_id) or skill_id.startswith(("gm_", "pmw_", "lab_")):
        _fail("id", "must match [a-z][a-z0-9_]{1,47} and use no reserved namespace")
    if not isinstance(raw["name"], str) or not raw["name"].strip() or len(raw["name"]) > 80:
        _fail("name", "must be a non-empty string of at most 80 characters")
    if raw["target_scope"] not in TARGET_SCOPES:
        _fail("target_scope", "only public zone scope is supported")
    if not isinstance(raw["effects"], list) or not raw["effects"]:
        _fail("effects", "must be a non-empty list")
    effects: list[FieldEffect] = []
    seen: set[str] = set()
    for index, item in enumerate(raw["effects"]):
        path = f"effects[{index}]"
        if not isinstance(item, dict) or set(item) != {"field", "delta"}:
            _fail(path, "requires exactly field and delta; PMW effects/outcomes are forbidden")
        if item["field"] not in CHANNEL_SET:
            _fail(f"{path}.field", "must be one of the eight public channels")
        if item["field"] in seen:
            _fail(path, "duplicate field perturbation")
        seen.add(item["field"])
        effects.append(FieldEffect(item["field"], _number(item["delta"], f"{path}.delta", low=-MAX_ABS_DELTA, high=MAX_ABS_DELTA)))
    duration = _number(raw["duration"], "duration", low=0.0, high=MAX_DURATION)
    periodic_raw = raw["periodic"]
    periodic = None
    if periodic_raw is not None:
        if not isinstance(periodic_raw, dict) or set(periodic_raw) != {"interval", "repeats"}:
            _fail("periodic", "must be null or exactly {interval, repeats}")
        interval = _number(periodic_raw["interval"], "periodic.interval", low=0.0, high=MAX_DURATION, positive=True)
        repeats = periodic_raw["repeats"]
        if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= MAX_PERIODIC_REPEATS:
            _fail("periodic.repeats", f"must be an integer in [1, {MAX_PERIODIC_REPEATS}]")
        periodic = Periodic(interval, repeats)
    if duration > 0 and periodic is not None:
        _fail("periodic", "duration and periodic are mutually exclusive in SkillSpec v0.1")
    conditions_raw = raw["trigger_conditions"]
    if not isinstance(conditions_raw, list):
        _fail("trigger_conditions", "must be a list")
    conditions: list[TriggerCondition] = []
    for index, item in enumerate(conditions_raw):
        path = f"trigger_conditions[{index}]"
        if not isinstance(item, dict) or set(item) != {"field", "op", "value"}:
            _fail(path, "requires exactly public field, op, and value")
        if item["field"] not in CHANNEL_SET:
            _fail(f"{path}.field", "hidden-state reads are forbidden")
        if item["op"] not in {"eq", "neq", "gt", "gte", "lt", "lte"}:
            _fail(f"{path}.op", "invalid comparator")
        conditions.append(TriggerCondition(item["field"], item["op"], _number(item["value"], f"{path}.value", low=0.0, high=1.0)))
    cost = _number(raw["resource_cost"], "resource_cost", low=0.0, high=MAX_RESOURCE_COST)
    charges = raw["charges"]
    if isinstance(charges, bool) or not isinstance(charges, int) or not 1 <= charges <= 99:
        _fail("charges", "must be an integer in [1, 99]")
    slot_cost = raw["slot_cost"]
    if isinstance(slot_cost, bool) or not isinstance(slot_cost, int) or slot_cost not in {1, 2}:
        _fail("slot_cost", "must be 1 or 2")
    return SkillSpec(skill_id, raw["name"].strip(), raw["target_scope"], tuple(effects), duration, periodic, tuple(conditions), cost, charges, slot_cost)


def load_skill(path: str | Path) -> SkillSpec:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillSpecError(f"{path}: cannot load SkillSpec: {exc}") from exc
    return validate_skill(raw)
