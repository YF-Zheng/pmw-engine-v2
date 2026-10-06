"""Versioned, interpretable structural novelty evidence for Free-Invention.

The metric deliberately has no scalar "creativity" score.  It identifies an
exact parameter-invariant structure and exposes the component differences to
the non-dominated nearest registered reference structures.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from .compiler import canonical_json


ALGORITHM_VERSION = "gm-structural-novelty-v0.4"
REFERENCE_REGISTRY = Path(__file__).with_name("structural_novelty") / "reference_registry_v0.4.json"
_REGISTRY_FIELDS = frozenset({
    "protocol_version", "algorithm_version", "source_manifest",
    "source_manifest_sha256", "reference_projection_sha256", "reference_count",
})


class StructuralNoveltyError(ValueError):
    """Raised when a mechanic or frozen reference registry is malformed."""


@dataclass(frozen=True, slots=True)
class ReferenceStructure:
    reference_id: str
    family: str
    fingerprint: str
    projection: dict[str, Any]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_mapping(value: Any, fields: frozenset[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise StructuralNoveltyError(f"{path}: expected exact fields {sorted(fields)}, got {actual}")
    return value


def canonical_structure(mechanic: Mapping[str, Any]) -> dict[str, Any]:
    """Project a SkillSpec-like mechanic to parameter/name-invariant structure.

    Numeric values, identity labels, declaration order, and economy parameters
    are intentionally absent.  Read/write topology, comparator shape, target
    scope, and temporal mode remain observable.
    """
    if not isinstance(mechanic, dict):
        raise StructuralNoveltyError("mechanic must be an object")
    effects = mechanic.get("effects")
    triggers = mechanic.get("trigger_conditions")
    if not isinstance(effects, list) or not effects:
        raise StructuralNoveltyError("mechanic.effects must be a non-empty list")
    if not isinstance(triggers, list):
        raise StructuralNoveltyError("mechanic.trigger_conditions must be a list")
    try:
        writes = sorted(
            (
                {"field": str(item["field"]), "polarity": _effect_polarity(item["delta"])}
                for item in effects
                if _effect_polarity(item["delta"]) != "zero"
            ),
            key=lambda item: (item["field"], item["polarity"]),
        )
        reads = sorted(
            ({"field": str(item["field"]), "op": str(item["op"])} for item in triggers),
            key=lambda item: (item["field"], item["op"]),
        )
    except (KeyError, TypeError) as exc:
        raise StructuralNoveltyError("effects/triggers do not have the expected shape") from exc
    periodic = mechanic.get("periodic")
    duration = mechanic.get("duration", 0)
    temporal_shape = "periodic" if periodic is not None else "sustained" if duration else "instantaneous"
    return {
        "schema": "SkillSpec-v0.1",
        "zero_write_policy": "excluded-from-novelty-topology-v1",
        "target_scope": mechanic.get("target_scope"),
        "write_terms": writes,
        "trigger_terms": reads,
        "temporal_shape": temporal_shape,
    }


def structure_fingerprint(projection_or_mechanic: Mapping[str, Any]) -> str:
    projection = (
        dict(projection_or_mechanic)
        if set(projection_or_mechanic) == {
            "schema", "zero_write_policy", "target_scope", "write_terms",
            "trigger_terms", "temporal_shape",
        }
        else canonical_structure(projection_or_mechanic)
    )
    return _sha256_bytes(canonical_json(projection).encode("utf-8"))


def _effect_polarity(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise StructuralNoveltyError("effect delta must be a finite number")
    if value < 0:
        return "negative"
    if value > 0:
        return "positive"
    return "zero"


def _counter_delta(left: Iterable[Any], right: Iterable[Any]) -> tuple[list[Any], list[Any]]:
    def key(value: Any) -> str:
        return canonical_json(value)

    left_values = {key(value): value for value in left}
    right_values = {key(value): value for value in right}
    left_counts = Counter(key(value) for value in left)
    right_counts = Counter(key(value) for value in right)
    removed = [left_values[item] for item in sorted((left_counts - right_counts).elements())]
    added = [right_values[item] for item in sorted((right_counts - left_counts).elements())]
    return removed, added


def difference_components(candidate: Mapping[str, Any], reference: Mapping[str, Any]) -> dict[str, Any]:
    """Return raw edit evidence; no subjective weighting or aggregate distance."""
    removed_writes, added_writes = _counter_delta(
        reference["write_terms"], candidate["write_terms"],
    )
    removed_write_fields, added_write_fields = _counter_delta(
        (item["field"] for item in reference["write_terms"]),
        (item["field"] for item in candidate["write_terms"]),
    )
    removed_triggers, added_triggers = _counter_delta(
        reference["trigger_terms"], candidate["trigger_terms"],
    )
    removed_reads, added_reads = _counter_delta(
        (item["field"] for item in reference["trigger_terms"]),
        (item["field"] for item in candidate["trigger_terms"]),
    )
    removed_operators, added_operators = _counter_delta(
        (item["op"] for item in reference["trigger_terms"]),
        (item["op"] for item in candidate["trigger_terms"]),
    )
    return {
        "write_terms_added": added_writes,
        "write_terms_removed": removed_writes,
        "write_fields_added": added_write_fields,
        "write_fields_removed": removed_write_fields,
        "effect_polarity_changes": _polarity_changes(candidate, reference),
        "read_fields_added": added_reads,
        "read_fields_removed": removed_reads,
        "trigger_operators_added": added_operators,
        "trigger_operators_removed": removed_operators,
        "trigger_terms_added": added_triggers,
        "trigger_terms_removed": removed_triggers,
        "temporal_shape_changed": candidate["temporal_shape"] != reference["temporal_shape"],
        "target_scope_changed": candidate["target_scope"] != reference["target_scope"],
        "effect_cardinality_delta": len(candidate["write_terms"]) - len(reference["write_terms"]),
        "condition_cardinality_delta": len(candidate["trigger_terms"]) - len(reference["trigger_terms"]),
    }


def _difference_vector(components: Mapping[str, Any]) -> tuple[int, ...]:
    return (
        len(components["write_fields_added"]),
        len(components["write_fields_removed"]),
        len(components["effect_polarity_changes"]),
        len(components["trigger_terms_added"]),
        len(components["trigger_terms_removed"]),
        int(components["temporal_shape_changed"]),
        int(components["target_scope_changed"]),
    )


def _polarity_changes(candidate: Mapping[str, Any], reference: Mapping[str, Any]) -> list[dict[str, str]]:
    candidate_by_field = {item["field"]: item["polarity"] for item in candidate["write_terms"]}
    reference_by_field = {item["field"]: item["polarity"] for item in reference["write_terms"]}
    return [
        {
            "field": field,
            "reference_polarity": reference_by_field[field],
            "candidate_polarity": candidate_by_field[field],
        }
        for field in sorted(candidate_by_field.keys() & reference_by_field.keys())
        if candidate_by_field[field] != reference_by_field[field]
    ]


def _dominates(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    return all(a <= b for a, b in zip(left, right)) and any(a < b for a, b in zip(left, right))


def _load_registry(path: Path = REFERENCE_REGISTRY) -> tuple[dict[str, Any], tuple[ReferenceStructure, ...]]:
    metadata = _strict_mapping(json.loads(path.read_text(encoding="utf-8")), _REGISTRY_FIELDS, "registry")
    if metadata["protocol_version"] != "gm-free-evaluation-v0.4-candidate":
        raise StructuralNoveltyError("registry: wrong protocol_version")
    if metadata["algorithm_version"] != ALGORITHM_VERSION:
        raise StructuralNoveltyError("registry: wrong algorithm_version")
    root = Path(__file__).with_name("skills")
    manifest_path = root.parent / str(metadata["source_manifest"])
    manifest_bytes = manifest_path.read_bytes()
    if _sha256_bytes(manifest_bytes) != metadata["source_manifest_sha256"]:
        raise StructuralNoveltyError("registry: frozen source manifest digest mismatch")
    manifest = json.loads(manifest_bytes)
    references: list[ReferenceStructure] = []
    projection_rows: list[dict[str, Any]] = []
    for entry in manifest["skills"]:
        raw = json.loads((root.parent / entry["path"]).read_text(encoding="utf-8"))
        projection = canonical_structure(raw)
        fingerprint = structure_fingerprint(projection)
        projection_rows.append({
            "reference_id": entry["id"], "family": entry["category"],
            "fingerprint": fingerprint, "projection": projection,
        })
        references.append(ReferenceStructure(entry["id"], entry["category"], fingerprint, projection))
    digest = _sha256_bytes(canonical_json(projection_rows).encode("utf-8"))
    if len(references) != metadata["reference_count"]:
        raise StructuralNoveltyError("registry: frozen reference count mismatch")
    if digest != metadata["reference_projection_sha256"]:
        raise StructuralNoveltyError("registry: frozen reference projection digest mismatch")
    return dict(metadata), tuple(references)


def evaluate_structural_novelty(
    mechanic: Mapping[str, Any], *, registry_path: Path = REFERENCE_REGISTRY,
) -> dict[str, Any]:
    """Produce an exact novelty decision plus unweighted nearest-family evidence."""
    metadata, references = _load_registry(registry_path)
    projection = canonical_structure(mechanic)
    fingerprint = structure_fingerprint(projection)
    zero_effect_fields = sorted(
        str(item["field"])
        for item in mechanic["effects"]
        if _effect_polarity(item["delta"]) == "zero"
    )
    no_op_evidence = {
        "has_zero_effect": bool(zero_effect_fields),
        "zero_effect_fields": zero_effect_fields,
        "zero_writes_excluded_from_topology": True,
    }
    if not projection["write_terms"]:
        return {
            "available": False,
            "algorithm_version": ALGORITHM_VERSION,
            "reference_registry": metadata["protocol_version"],
            "reference_projection_sha256": metadata["reference_projection_sha256"],
            "reference_count": len(references),
            "canonical_structure": projection,
            "structural_fingerprint": fingerprint,
            "no_op_evidence": no_op_evidence,
            "excluded_from_novelty_rate": True,
            "reason": "all declared effects are zero; no effective write topology exists",
        }
    exact_matches = sorted(
        reference.reference_id for reference in references if reference.fingerprint == fingerprint
    )
    candidates: list[tuple[ReferenceStructure, dict[str, Any], tuple[int, ...]]] = []
    for reference in references:
        components = difference_components(projection, reference.projection)
        candidates.append((reference, components, _difference_vector(components)))
    frontier = [
        item for item in candidates
        if not any(_dominates(other[2], item[2]) for other in candidates if other is not item)
    ]
    frontier_evidence = [
        {
            "reference_id": reference.reference_id,
            "source_catalog_category": reference.family,
            "reference_fingerprint": reference.fingerprint,
            "difference_components": components,
        }
        for reference, components, _vector in sorted(frontier, key=lambda item: item[0].reference_id)
    ]
    return {
        "available": True,
        "algorithm_version": ALGORITHM_VERSION,
        "reference_registry": metadata["protocol_version"],
        "reference_projection_sha256": metadata["reference_projection_sha256"],
        "reference_count": len(references),
        "canonical_structure": projection,
        "no_op_evidence": no_op_evidence,
        "excluded_from_novelty_rate": False,
        "structural_fingerprint": fingerprint,
        "exact_novel_against_registry": not exact_matches,
        "exact_reference_matches": exact_matches,
        "pareto_reference_frontier": frontier_evidence,
        "frontier_policy": (
            "non-dominated registered references under unweighted component differences; "
            "no scalar distance or nearest-family claim"
        ),
    }


def duplicate_structure_profile(
    mechanics: Iterable[tuple[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    """Group repeated canonical structures without treating names as diversity."""
    groups: dict[str, list[str]] = {}
    count = 0
    for sample_id, mechanic in mechanics:
        if not isinstance(sample_id, str) or not sample_id:
            raise StructuralNoveltyError("sample_id must be a non-empty string")
        groups.setdefault(structure_fingerprint(mechanic), []).append(sample_id)
        count += 1
    duplicate_groups = [
        {"structural_fingerprint": fingerprint, "sample_ids": sorted(sample_ids)}
        for fingerprint, sample_ids in sorted(groups.items())
        if len(sample_ids) > 1
    ]
    duplicate_sample_count = sum(len(group["sample_ids"]) for group in duplicate_groups)
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "sample_count": count,
        "unique_structure_count": len(groups),
        "duplicate_sample_count": duplicate_sample_count,
        "duplicate_structure_groups": duplicate_groups,
    }
