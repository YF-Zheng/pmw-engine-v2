"""Separate structural and parametric diversity measures for generated mechanics."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import hashlib
import json
import math
from typing import Any, Iterable


def _raw(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    return value


def _numeric_bucket(value: float) -> str:
    magnitude = abs(float(value))
    size = "zero" if magnitude == 0 else "small" if magnitude <= 0.25 else "medium" if magnitude <= 0.65 else "large"
    return ("negative:" if value < 0 else "positive:") + size


def _count_bucket(value: int) -> str:
    if value <= 1:
        return "count:single"
    if value <= 3:
        return "count:few"
    if value <= 6:
        return "count:several"
    return "count:many"


def _structure(value: Any, key: str = "") -> Any:
    value = _raw(value)
    if isinstance(value, dict):
        return {name: _structure(item, name) for name, item in sorted(value.items()) if name not in {"id", "name"}}
    if isinstance(value, (list, tuple)):
        normalized = [_structure(item, key) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and math.isfinite(value):
        if key in {"charges", "repeats", "slot_cost"}:
            return _count_bucket(int(value))
        return _numeric_bucket(float(value))
    return type(value).__name__


def structural_fingerprint(mechanic: Any) -> str:
    """Fingerprint topology and coarse numeric bins, ignoring IDs/names."""
    payload = json.dumps(_structure(mechanic), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parametric_fingerprint(mechanic: Any) -> str:
    """Fingerprint exact parameters while still ignoring identity labels."""
    raw = _raw(mechanic)
    if isinstance(raw, dict):
        raw = {key: value for key, value in raw.items() if key not in {"id", "name"}}
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def diversity_report(mechanics: Iterable[Any]) -> dict[str, Any]:
    rows = tuple(mechanics)
    structural = {structural_fingerprint(item) for item in rows}
    parametric = {parametric_fingerprint(item) for item in rows}
    total = len(rows)
    return {
        "sample_count": total,
        "structural_unique": len(structural),
        "structural_ratio": len(structural) / total if total else 0.0,
        "parametric_unique": len(parametric),
        "parametric_ratio": len(parametric) / total if total else 0.0,
    }
