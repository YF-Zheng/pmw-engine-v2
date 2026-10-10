"""Strict, scoped conditions shared by actions, effects, statuses, and hooks."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .contracts import ATTRIBUTES, GameplayContractError


@dataclass(frozen=True, slots=True)
class ConditionSpec:
    kind: str
    subject: str | None = None
    key: str | None = None
    comparator: str | None = None
    value: Any = None
    children: tuple["ConditionSpec", ...] = ()


def parse_condition(raw: Any, path: str = "$.condition") -> ConditionSpec:
    if raw is None:
        return ConditionSpec("always")
    if not isinstance(raw, dict) or len(raw) != 1:
        raise GameplayContractError(f"{path} must contain exactly one condition operator")
    kind, value = next(iter(raw.items()))
    if kind in {"all", "any"}:
        if not isinstance(value, list) or not value:
            raise GameplayContractError(f"{path}.{kind} must be a non-empty list")
        return ConditionSpec(kind, children=tuple(parse_condition(item, f"{path}.{kind}[{i}]") for i, item in enumerate(value)))
    if kind == "not":
        return ConditionSpec(kind, children=(parse_condition(value, f"{path}.not"),))
    if kind in {"attribute", "resource", "field"}:
        if not isinstance(value, dict):
            raise GameplayContractError(f"{path}.{kind} must be an object")
        required = {"subject", "key", "comparator", "value"}
        if set(value) != required:
            raise GameplayContractError(f"{path}.{kind} fields must be {sorted(required)}")
        subject, key, comparator = value["subject"], value["key"], value["comparator"]
        if subject not in {"self", "target_actor", "current_area"}:
            raise GameplayContractError(f"{path}.{kind}.subject is not scoped")
        if kind == "attribute" and key not in ATTRIBUTES:
            raise GameplayContractError(f"{path}.{kind}.key is not a base attribute")
        if kind == "resource" and key not in {"hp", "mana", "shield"}:
            raise GameplayContractError(f"{path}.{kind}.key is not a resource")
        if not isinstance(key, str) or not key:
            raise GameplayContractError(f"{path}.{kind}.key must be non-empty")
        if comparator not in {"eq", "neq", "gt", "gte", "lt", "lte"}:
            raise GameplayContractError(f"{path}.{kind}.comparator is invalid")
        number = value["value"]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise GameplayContractError(f"{path}.{kind}.value must be finite numeric")
        return ConditionSpec(kind, subject, key, comparator, float(number))
    if kind in {"has_trait", "has_status"}:
        if not isinstance(value, dict) or set(value) != {"subject", "id"}:
            raise GameplayContractError(f"{path}.{kind} requires subject and id")
        if value["subject"] not in {"self", "target_actor"} or not isinstance(value["id"], str) or not value["id"]:
            raise GameplayContractError(f"{path}.{kind} is invalid")
        return ConditionSpec(kind, value["subject"], value["id"])
    raise GameplayContractError(f"{path} has unknown condition {kind!r}")


def evaluate_condition(spec: ConditionSpec, context: Mapping[str, Any]) -> bool:
    if spec.kind == "always": return True
    if spec.kind == "all": return all(evaluate_condition(item, context) for item in spec.children)
    if spec.kind == "any": return any(evaluate_condition(item, context) for item in spec.children)
    if spec.kind == "not": return not evaluate_condition(spec.children[0], context)
    subject = context.get(spec.subject or "")
    if not isinstance(subject, Mapping): return False
    if spec.kind == "attribute": actual = subject.get(spec.key)
    elif spec.kind == "resource": actual = subject.get(spec.key)
    elif spec.kind == "field": actual = subject.get("fields", {}).get(spec.key, {}).get("value")
    elif spec.kind == "has_trait": return spec.key in effective_traits(subject)
    elif spec.kind == "has_status": return any(row.get("active") and row.get("spec_id") == spec.key for row in subject.get("status_slots", {}).values())
    else: return False
    if not isinstance(actual, (int, float)) or isinstance(actual, bool): return False
    return {"eq": actual == spec.value, "neq": actual != spec.value, "gt": actual > spec.value,
            "gte": actual >= spec.value, "lt": actual < spec.value, "lte": actual <= spec.value}[spec.comparator]


def effective_traits(actor: Mapping[str, Any]) -> frozenset[str]:
    result = set(actor.get("traits", ()))
    for row in actor.get("status_slots", {}).values():
        if row.get("active"):
            result.update(row.get("granted_traits", ()))
    return frozenset(result)
