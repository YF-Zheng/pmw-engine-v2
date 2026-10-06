"""Layered, non-scalar structural evidence for v0.5."""

from __future__ import annotations

from collections import Counter
import hashlib
from itertools import combinations
import json
from typing import Any, Iterable, Mapping

from ..structural_novelty import (
    REFERENCE_REGISTRY,
    _load_registry,
    _statically_unreachable_triggers,
    canonical_structure,
    difference_components,
    structure_fingerprint,
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _abstract_projection(semantic: Mapping[str, Any]) -> dict[str, Any]:
    """Canonicalize field names while retaining field-role relationships."""
    fields = sorted({
        item["field"]
        for key in ("trigger_terms", "write_terms")
        for item in semantic[key]
    })
    roles = {}
    for field in fields:
        roles[field] = {
            "reads": sorted(item["op"] for item in semantic["trigger_terms"] if item["field"] == field),
            "writes": sorted(item["polarity"] for item in semantic["write_terms"] if item["field"] == field),
        }
    ordered = sorted(fields, key=lambda field: (_canonical(roles[field]), field))
    renaming = {field: f"field_{index}" for index, field in enumerate(ordered)}
    return {
        "schema": semantic["schema"],
        "target_scope": semantic["target_scope"],
        "temporal_shape": semantic["temporal_shape"],
        "field_nodes": [
            {"field": renaming[field], **roles[field]} for field in ordered
        ],
        "trigger_terms": sorted(
            ({"field": renaming[item["field"]], "op": item["op"]} for item in semantic["trigger_terms"]),
            key=lambda item: (item["field"], item["op"]),
        ),
        "write_terms": sorted(
            ({"field": renaming[item["field"]], "polarity": item["polarity"]} for item in semantic["write_terms"]),
            key=lambda item: (item["field"], item["polarity"]),
        ),
        "effect_cardinality": len(semantic["write_terms"]),
        "trigger_cardinality": len(semantic["trigger_terms"]),
    }


def _fingerprint(projection: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(projection).encode("utf-8")).hexdigest()


def _edit_profile(candidate: Mapping[str, Any], reference: Mapping[str, Any]) -> list[dict[str, Any]]:
    changes = difference_components(candidate, reference)
    edits: list[dict[str, Any]] = []
    for value in changes["trigger_terms_added"]:
        edits.append({"kind": "add_trigger", "term": value})
    for value in changes["trigger_terms_removed"]:
        edits.append({"kind": "remove_trigger", "term": value})
    for value in changes["write_terms_added"]:
        # A same-field polarity replacement is represented below as one edit.
        if not any(change["field"] == value["field"] for change in changes["effect_polarity_changes"]):
            edits.append({"kind": "add_effect", "term": value})
    for value in changes["write_terms_removed"]:
        if not any(change["field"] == value["field"] for change in changes["effect_polarity_changes"]):
            edits.append({"kind": "remove_effect", "term": value})
    edits.extend({"kind": "change_polarity", **value} for value in changes["effect_polarity_changes"])
    if changes["temporal_shape_changed"]:
        edits.append({"kind": "change_temporal_shape", "from": reference["temporal_shape"], "to": candidate["temporal_shape"]})
    if changes["target_scope_changed"]:
        edits.append({"kind": "change_target_scope", "from": reference["target_scope"], "to": candidate["target_scope"]})
    return edits


def _atoms(projection: Mapping[str, Any]) -> Counter[str]:
    values = [f"trigger:{_canonical(item)}" for item in projection["trigger_terms"]]
    values.extend(f"write:{_canonical(item)}" for item in projection["write_terms"])
    return Counter(values)


def _recombination(candidate: Mapping[str, Any], references: Iterable[Any]) -> dict[str, Any]:
    target = _atoms(candidate)
    if not target:
        return {
            "recombination_detected": False, "source_references": [],
            "coverage": 0.0, "purity": 0.0,
            "each_source_has_independent_contribution": False,
            "covered_terms": [],
            "policy": "detected only when two compatible references have exact union equality and each contributes a distinct term; false does not prove non-recombination",
        }
    best: tuple[float, float, tuple[str, ...], Counter[str], bool] = (0.0, 0.0, (), Counter(), False)
    compatible = [
        ref for ref in references
        if ref.projection["target_scope"] == candidate["target_scope"]
        and ref.projection["temporal_shape"] == candidate["temporal_shape"]
    ]
    for left, right in combinations(compatible, 2):
        left_atoms = _atoms(left.projection)
        right_atoms = _atoms(right.projection)
        union = left_atoms | right_atoms
        covered = union & target
        count = sum(covered.values())
        coverage = count / sum(target.values())
        purity = count / sum(union.values()) if union else 0.0
        independent = bool(left_atoms - right_atoms) and bool(right_atoms - left_atoms)
        identity = tuple(sorted((left.reference_id, right.reference_id)))
        if (coverage, purity, independent, tuple(reversed(identity))) > (best[0], best[1], best[4], tuple(reversed(best[2]))):
            best = (coverage, purity, identity, covered, independent)
    detected = (
        best[0] == 1.0 and best[1] == 1.0 and best[4]
        and all(_atoms(ref.projection) != target for ref in compatible)
    )
    return {
        "recombination_detected": detected,
        "source_references": list(best[2]) if detected else [],
        "coverage": best[0],
        "purity": best[1],
        "each_source_has_independent_contribution": best[4],
        "covered_terms": sorted(best[3].elements()),
        "policy": "detected only when two compatible references have exact union equality and each contributes a distinct term; false does not prove non-recombination",
    }


def evaluate_structural_evidence(
    mechanic: Mapping[str, Any], *, registry_path=REFERENCE_REGISTRY,
) -> dict[str, Any]:
    metadata, references = _load_registry(registry_path)
    semantic = canonical_structure(mechanic)
    semantic_fp = structure_fingerprint(semantic)
    abstract = _abstract_projection(semantic)
    abstract_fp = _fingerprint(abstract)
    reference_rows = [
        (ref, _abstract_projection(ref.projection)) for ref in references
    ]
    exact = sorted(ref.reference_id for ref in references if ref.fingerprint == semantic_fp)
    abstract_matches = sorted(ref.reference_id for ref, projection in reference_rows if _fingerprint(projection) == abstract_fp)
    abstract_nearest = []
    for ref, projection in reference_rows:
        edits = _edit_profile(abstract, projection)
        abstract_nearest.append((len(edits), ref.reference_id, edits))
    abstract_edit_count, abstract_nearest_id, abstract_edits = min(
        abstract_nearest, key=lambda row: (row[0], row[1]),
    )
    nearest = []
    for ref in references:
        edits = _edit_profile(semantic, ref.projection)
        nearest.append((len(edits), ref.reference_id, edits))
    edit_count, nearest_id, edits = min(nearest, key=lambda row: (row[0], row[1]))
    unreachable = _statically_unreachable_triggers(mechanic)
    has_writes = bool(semantic["write_terms"])
    return {
        "available": has_writes and not unreachable,
        "reason": (
            "one or more trigger conditions are provably unreachable over normalized [0, 1] public fields"
            if unreachable else None if has_writes else "all declared effects are zero; no effective write topology"
        ),
        "structural_projection_available": has_writes,
        "excluded_from_novelty_rate": not has_writes or bool(unreachable),
        "reference_count": len(references),
        "reference_projection_sha256": metadata["reference_projection_sha256"],
        "exact_match": bool(exact),
        "matched_reference_ids": exact,
        "exact_non_match_interpretation": "weak registry evidence only; not a claim of genuine novelty",
        "near_copy": edit_count == 1,
        "nearest_reference": nearest_id,
        "near_copy_edit_count": edit_count,
        "near_copy_edits": edits,
        "recombination": _recombination(semantic, references),
        "semantic_structure": {
            "projection": semantic,
            "fingerprint": semantic_fp,
            "field_identity_matters": True,
            "exact_reference_match": bool(exact),
        },
        "abstract_topology": {
            "projection": abstract,
            "fingerprint": abstract_fp,
            "field_identity_matters": False,
            "matched_reference_ids": abstract_matches,
            "exact_reference_match": bool(abstract_matches),
            "nearest_reference": abstract_nearest_id,
            "nearest_edit_count": abstract_edit_count,
            "nearest_edits": abstract_edits,
            "edit_policy": "unweighted explicit edit components; not a scalar creativity or novelty score",
        },
        "static_guard": {
            "passed": not unreachable,
            "statically_unreachable_triggers": unreachable,
            "behavioral_inertness_not_inferred_beyond_guard": True,
        },
        "deprecated_exact_novel_against_registry": {
            "value": not bool(exact),
            "status": "weak_evidence_only",
        },
    }
