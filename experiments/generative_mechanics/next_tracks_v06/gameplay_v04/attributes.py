"""Explicit attribute terms; attributes never imply ambient combat rules."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .contracts import ATTRIBUTES, GameplayContractError


@dataclass(frozen=True, slots=True)
class AttributeTerm:
    kind: str
    attribute: str
    coefficient: float = 0.0
    comparator: str | None = None
    threshold: float | None = None
    operation: str | None = None
    value: float | None = None
    maximum: float | None = None


def parse_attribute_term(raw: Any, path: str = "$.attribute_term") -> AttributeTerm:
    if not isinstance(raw, dict) or raw.get("kind") not in {"scaling", "threshold", "check", "modifier"}:
        raise GameplayContractError(f"{path}.kind is invalid")
    kind = raw["kind"]
    allowed = {
        "scaling": {"kind", "attribute", "coefficient", "maximum"},
        "threshold": {"kind", "attribute", "comparator", "threshold"},
        "check": {"kind", "attribute", "comparator", "threshold"},
        "modifier": {"kind", "attribute", "operation", "value"},
    }[kind]
    required = allowed - ({"maximum"} if kind == "scaling" else set())
    if set(raw) - allowed or not required <= set(raw):
        raise GameplayContractError(f"{path} has missing or unknown fields")
    attribute = raw.get("attribute")
    if attribute not in ATTRIBUTES:
        raise GameplayContractError(f"{path}.attribute must explicitly name one of {ATTRIBUTES}")
    if kind == "scaling":
        coefficient = _number(raw["coefficient"], f"{path}.coefficient")
        maximum = None if "maximum" not in raw else _number(raw["maximum"], f"{path}.maximum")
        if maximum is not None and maximum < 0: raise GameplayContractError(f"{path}.maximum must be non-negative")
        return AttributeTerm(kind, attribute, coefficient=coefficient, maximum=maximum)
    if kind in {"threshold", "check"}:
        comparator = raw["comparator"]
        if comparator not in {"eq", "neq", "gt", "gte", "lt", "lte"}:
            raise GameplayContractError(f"{path}.comparator is invalid")
        return AttributeTerm(kind, attribute, comparator=comparator, threshold=_number(raw["threshold"], f"{path}.threshold"))
    operation = raw["operation"]
    if operation not in {"add", "multiply"}: raise GameplayContractError(f"{path}.operation is invalid")
    return AttributeTerm(kind, attribute, operation=operation, value=_number(raw["value"], f"{path}.value"))


def evaluate_terms(base: float, terms: tuple[AttributeTerm, ...], actor: Mapping[str, Any]) -> tuple[bool, float, tuple[dict, ...]]:
    value = _number(base, "base")
    trace = []
    for term in terms:
        attr = _number(actor.get(term.attribute), term.attribute)
        if term.kind in {"threshold", "check"}:
            passed = _compare(attr, term.comparator, term.threshold)
            trace.append({"kind": term.kind, "attribute": term.attribute, "actual": attr, "passed": passed})
            if not passed: return False, value, tuple(trace)
    for term in terms:
        attr = _number(actor.get(term.attribute), term.attribute)
        old = value
        if term.kind == "scaling":
            contribution = attr * term.coefficient
            if term.maximum is not None: contribution = min(contribution, term.maximum)
            value += contribution
        elif term.kind == "modifier" and term.operation == "add": value += attr * term.value
        trace.append({"kind": term.kind, "attribute": term.attribute, "old": old, "new": value}) if value != old else None
    for term in terms:
        if term.kind == "modifier" and term.operation == "multiply":
            attr = _number(actor.get(term.attribute), term.attribute); old = value; value *= 1.0 + attr * term.value
            trace.append({"kind": term.kind, "attribute": term.attribute, "old": old, "new": value})
    if not math.isfinite(value): raise GameplayContractError("attribute expression is non-finite")
    return True, value, tuple(trace)


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GameplayContractError(f"{path} must be finite numeric")
    return float(value)


def _compare(left: float, op: str | None, right: float | None) -> bool:
    return {"eq": left == right, "neq": left != right, "gt": left > right, "gte": left >= right,
            "lt": left < right, "lte": left <= right}[op]
