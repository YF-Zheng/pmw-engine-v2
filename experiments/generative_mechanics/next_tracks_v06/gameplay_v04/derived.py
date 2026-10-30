"""Trusted, bounded Area Derived catalog and Core state-Law lowering."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from pmw import parse_law

from .contracts import GameplayContractError
from .dynamics import DYNAMICS_COMPONENT


DERIVED_COMPONENT = "pmw_gameplay_derived"
MAX_DERIVED_SPECS = 8
_ID = re.compile(r"[a-z][a-z0-9_]{1,47}\Z")
_KINDS = {"weighted_sum", "threshold"}
_COMPARATORS = {"gt", "gte", "lt", "lte"}


@dataclass(frozen=True, slots=True)
class DerivedSpec:
    id: str
    kind: str
    terms: tuple[tuple[str, float], ...] = ()
    bias: float = 0.0
    minimum: float = 0.0
    maximum: float = 1.0
    field_id: str | None = None
    comparator: str | None = None
    value: float | None = None


def parse_derived_spec(raw: Any, path: str = "$.derived") -> DerivedSpec:
    """Parse one strict trusted Derived specification."""
    if not isinstance(raw, dict):
        raise GameplayContractError(f"{path} must be an object")
    if "kind" not in raw or not isinstance(raw["kind"], str):
        raise GameplayContractError(f"{path}.kind is invalid")
    kind = raw["kind"]
    if kind not in _KINDS:
        raise GameplayContractError(f"{path}.kind is invalid")
    if kind == "weighted_sum":
        expected = {"id", "kind", "terms", "bias", "minimum", "maximum"}
        _require_keys(raw, expected, path)
        identifier = _identifier(raw["id"], f"{path}.id")
        raw_terms = raw["terms"]
        if not isinstance(raw_terms, (list, tuple)) or not 1 <= len(raw_terms) <= 8:
            raise GameplayContractError(f"{path}.terms must contain 1..8 entries")
        terms = []
        for index, item in enumerate(raw_terms):
            item_path = f"{path}.terms[{index}]"
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise GameplayContractError(f"{item_path} must be a field/weight pair")
            field_id = _identifier(item[0], f"{item_path}[0]")
            weight = _bounded_number(
                item[1], f"{item_path}[1]", minimum=-8.0, maximum=8.0
            )
            terms.append((field_id, weight))
        if len({field_id for field_id, _ in terms}) != len(terms):
            raise GameplayContractError(f"{path}.terms contains duplicate Field IDs")
        bias = _bounded_number(
            raw["bias"], f"{path}.bias", minimum=-8.0, maximum=8.0
        )
        minimum = _bounded_number(
            raw["minimum"], f"{path}.minimum",
            minimum=-1000.0, maximum=1000.0,
        )
        maximum = _bounded_number(
            raw["maximum"], f"{path}.maximum",
            minimum=-1000.0, maximum=1000.0,
        )
        if minimum >= maximum:
            raise GameplayContractError(f"{path}.minimum must be less than maximum")
        return DerivedSpec(
            identifier, kind, tuple(terms), bias, minimum, maximum
        )
    expected = {"id", "kind", "field_id", "comparator", "value"}
    _require_keys(raw, expected, path)
    identifier = _identifier(raw["id"], f"{path}.id")
    field_id = _identifier(raw["field_id"], f"{path}.field_id")
    comparator = raw["comparator"]
    if comparator not in _COMPARATORS:
        raise GameplayContractError(f"{path}.comparator is invalid")
    value = _number(raw["value"], f"{path}.value")
    return DerivedSpec(
        identifier, kind, field_id=field_id, comparator=comparator, value=value
    )


def normalize_derived_by_area(
    raw: Mapping[str, Sequence[DerivedSpec]] | None,
) -> dict[str, tuple[DerivedSpec, ...]]:
    """Validate and canonically order trusted per-Area Derived bindings."""
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise GameplayContractError("derived_by_area must be an Area mapping")
    result: dict[str, tuple[DerivedSpec, ...]] = {}
    for area_id, specs in sorted(raw.items()):
        if not isinstance(area_id, str) or not area_id:
            raise GameplayContractError("derived_by_area Area ID must be non-empty")
        result[area_id] = validate_derived_specs(specs, f"$.derived_by_area[{area_id!r}]")
    return result


def validate_derived_specs(
    specs: Sequence[DerivedSpec], path: str = "$.derived",
) -> tuple[DerivedSpec, ...]:
    if not isinstance(specs, (list, tuple)):
        raise GameplayContractError(f"{path} must be a list of DerivedSpec values")
    if len(specs) > MAX_DERIVED_SPECS:
        raise GameplayContractError(
            f"{path} exceeds the maximum of {MAX_DERIVED_SPECS} specs"
        )
    normalized = []
    for index, spec in enumerate(specs):
        if not isinstance(spec, DerivedSpec):
            raise GameplayContractError(f"{path}[{index}] must be a DerivedSpec")
        _validate_spec(spec, f"{path}[{index}]")
        normalized.append(spec)
    normalized.sort(key=lambda item: item.id)
    if len({item.id for item in normalized}) != len(normalized):
        raise GameplayContractError(f"{path} contains duplicate Derived IDs")
    return tuple(normalized)


def canonical_spec_document(spec: DerivedSpec) -> dict[str, Any]:
    _validate_spec(spec, "$.derived")
    if spec.kind == "weighted_sum":
        return {
            "id": spec.id,
            "kind": spec.kind,
            "terms": [[field_id, weight] for field_id, weight in spec.terms],
            "bias": spec.bias,
            "minimum": spec.minimum,
            "maximum": spec.maximum,
        }
    return {
        "id": spec.id,
        "kind": spec.kind,
        "field_id": spec.field_id,
        "comparator": spec.comparator,
        "value": spec.value,
    }


def canonical_spec_hash(specs: Sequence[DerivedSpec]) -> str:
    normalized = validate_derived_specs(specs)
    document = [canonical_spec_document(spec) for spec in normalized]
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def derived_component(
    specs: Sequence[DerivedSpec], fields: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    normalized = validate_derived_specs(specs)
    _validate_fields(normalized, fields)
    return {
        "values": {
            spec.id: compute_derived_value(spec, fields) for spec in normalized
        },
        "spec_hash": canonical_spec_hash(normalized),
    }


def compute_derived_value(
    spec: DerivedSpec, fields: Mapping[str, Mapping[str, Any]],
) -> float:
    _validate_spec(spec, "$.derived")
    if spec.kind == "weighted_sum":
        total = spec.bias
        for field_id, weight in spec.terms:
            total += weight * float(fields[field_id]["value"])
        return max(spec.minimum, min(spec.maximum, total))
    actual = float(fields[spec.field_id]["value"])
    holds = {
        "gt": actual > spec.value,
        "gte": actual >= spec.value,
        "lt": actual < spec.value,
        "lte": actual <= spec.value,
    }[spec.comparator]
    return 1.0 if holds else 0.0


def build_derived_laws(
    derived_by_area: Mapping[str, Sequence[DerivedSpec]] | None,
) -> tuple[dict[str, Any], ...]:
    normalized = normalize_derived_by_area(derived_by_area)
    laws: list[dict[str, Any]] = []
    for area_id, specs in normalized.items():
        spec_hash = canonical_spec_hash(specs)
        for spec in specs:
            laws.extend(_derived_laws(area_id, spec, spec_hash))
    result = tuple(sorted(laws, key=lambda item: item["id"]))
    for law in result:
        parse_law(law)
    return result


def _derived_laws(
    area_id: str, spec: DerivedSpec, spec_hash: str,
) -> list[dict[str, Any]]:
    prefix = f"pmw.v04.derived.{area_id}.{spec.id}"
    root = f"$area.{DERIVED_COMPONENT}"
    identity = [
        {"ref": "$area.id", "eq": area_id},
        {"ref": f"{root}.spec_hash", "eq": spec_hash},
    ]
    bindings = {
        "area": {
            "kind": "entity",
            "requires": [
                "pmw_gameplay_area", DYNAMICS_COMPONENT, DERIVED_COMPONENT,
            ],
        },
    }
    if spec.kind == "weighted_sum":
        expression = _weighted_sum_expression(spec)
        return [{
            "id": f"{prefix}.weighted_sum",
            "mode": "state",
            "priority": 100,
            "bindings": bindings,
            "when": {"all": [
                *identity,
                {"ref": f"{root}.values.{spec.id}", "neq": expression},
            ]},
            "effects": [{
                "op": "set",
                "target": f"{root}.values.{spec.id}",
                "value": deepcopy(expression),
            }],
        }]
    laws = []
    for suffix, holds, value in (("true", True, 1.0), ("false", False, 0.0)):
        comparator = spec.comparator if holds else _inverse(spec.comparator)
        laws.append({
            "id": f"{prefix}.threshold.{suffix}",
            "mode": "state",
            "priority": 100,
            "bindings": bindings,
            "when": {"all": [
                *identity,
                {
                    "ref": (
                        f"$area.{DYNAMICS_COMPONENT}.fields."
                        f"{spec.field_id}.value"
                    ),
                    comparator: spec.value,
                },
                {"ref": f"{root}.values.{spec.id}", "neq": value},
            ]},
            "effects": [{
                "op": "set",
                "target": f"{root}.values.{spec.id}",
                "value": value,
            }],
        })
    return laws


def _weighted_sum_expression(spec: DerivedSpec) -> dict[str, Any]:
    terms: list[Any] = [spec.bias]
    terms.extend(
        {"mul": [
            f"$area.{DYNAMICS_COMPONENT}.fields.{field_id}.value",
            weight,
        ]}
        for field_id, weight in spec.terms
    )
    return {
        "clamp": [
            {"add": terms},
            spec.minimum,
            spec.maximum,
        ]
    }


def _inverse(comparator: str) -> str:
    return {
        "gt": "lte",
        "gte": "lt",
        "lt": "gte",
        "lte": "gt",
    }[comparator]


def _validate_spec(spec: DerivedSpec, path: str) -> None:
    if not isinstance(spec, DerivedSpec):
        raise GameplayContractError(f"{path} must be a DerivedSpec")
    _identifier(spec.id, f"{path}.id")
    if spec.kind not in _KINDS:
        raise GameplayContractError(f"{path}.kind is invalid")
    if spec.kind == "weighted_sum":
        if not 1 <= len(spec.terms) <= 8:
            raise GameplayContractError(f"{path}.terms must contain 1..8 entries")
        field_ids = []
        for index, item in enumerate(spec.terms):
            if not isinstance(item, tuple) or len(item) != 2:
                raise GameplayContractError(
                    f"{path}.terms[{index}] must be a field/weight tuple"
                )
            field_ids.append(_identifier(item[0], f"{path}.terms[{index}][0]"))
            _bounded_number(
                item[1], f"{path}.terms[{index}][1]",
                minimum=-8.0, maximum=8.0,
            )
        if len(field_ids) != len(set(field_ids)):
            raise GameplayContractError(f"{path}.terms contains duplicate Field IDs")
        _bounded_number(
            spec.bias, f"{path}.bias", minimum=-8.0, maximum=8.0
        )
        minimum = _bounded_number(
            spec.minimum, f"{path}.minimum",
            minimum=-1000.0, maximum=1000.0,
        )
        maximum = _bounded_number(
            spec.maximum, f"{path}.maximum",
            minimum=-1000.0, maximum=1000.0,
        )
        if minimum >= maximum:
            raise GameplayContractError(f"{path}.minimum must be less than maximum")
        return
    _identifier(spec.field_id, f"{path}.field_id")
    if spec.comparator not in _COMPARATORS:
        raise GameplayContractError(f"{path}.comparator is invalid")
    _number(spec.value, f"{path}.value")


def _validate_fields(
    specs: Sequence[DerivedSpec], fields: Mapping[str, Mapping[str, Any]],
) -> None:
    for spec in specs:
        field_ids = (
            (field_id for field_id, _ in spec.terms)
            if spec.kind == "weighted_sum" else (spec.field_id,)
        )
        for field_id in field_ids:
            field = fields.get(field_id)
            if not isinstance(field, Mapping) or "value" not in field:
                raise GameplayContractError(
                    f"Derived {spec.id!r} references unavailable Field {field_id!r}"
                )


def _require_keys(raw: Mapping[str, Any], expected: set[str], path: str) -> None:
    if set(raw) != expected:
        raise GameplayContractError(
            f"{path} schema mismatch; expected={sorted(expected)}"
        )


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise GameplayContractError(f"{path} must be a gameplay identifier")
    return value


def _number(value: Any, path: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise GameplayContractError(f"{path} must be a finite number")
    return float(value)


def _bounded_number(
    value: Any, path: str, *, minimum: float, maximum: float,
) -> float:
    number = _number(value, path)
    if not minimum <= number <= maximum:
        raise GameplayContractError(
            f"{path} must be in [{minimum:g}, {maximum:g}]"
        )
    return number
