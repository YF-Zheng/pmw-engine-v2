"""Human-authored v0.5 expectations, defined before evaluator execution."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .case_registry import CASES as V04_CASES


SUSPECT_RESOLUTIONS = {
    "CD-08": ("RESOLVED_BY_SPLIT", "realized depth retains the redundant dependency while necessity-backed depth may omit it; the gap is diagnostic only"),
    "CD-11": ("RESOLVED_BY_DEFINITION", "binding identity is semantic by default; a changed binding is not silently paired without a registered equivalence class"),
    "CE-05": ("RESOLVED_BY_SPLIT", "equal net outcomes and unequal normalized paths are reported on separate axes"),
    "CE-15": ("RESOLVED_BY_SPLIT", "multiplicity-sensitive path differentiation is separate from outcome differentiation"),
    "SN-06": ("RESOLVED_BY_SPLIT", "semantic structure differs while canonical abstract topology may match"),
    "SN-10": ("RESOLVED_BY_SPLIT", "exact non-match is weak evidence and conservative two-reference union coverage is reported separately"),
    "SN-11": ("RESOLVED_BY_SPLIT", "one-trigger edit is explicitly reported as near-copy evidence"),
    "SN-12": ("RESOLVED_BY_SPLIT", "one-effect edit is explicitly reported as near-copy evidence"),
    "SN-15": ("KNOWN_LIMITATION", "duplicate-field cancellation is outside frozen SkillSpec and remains a construct-language ceiling"),
}


def _old_expected(case: dict[str, Any]) -> dict[str, Any]:
    metric = case["target_metric"]
    if metric == "downstream_causal_depth":
        semantics = "report realized dependency and necessity-backed depths separately; preserve ordered committed write/read dependencies"
    elif metric == "cross_environment_differentiation":
        semantics = "report paired net outcome and normalized candidate-induced causal-path differentiation separately"
    else:
        semantics = "report exact, near-copy, recombination, semantic-structure, and abstract-topology evidence without a scalar novelty score"
    status, note = SUSPECT_RESOLUTIONS.get(case["case_id"], ("UNCHANGED_EXPECTATION", semantics))
    return {
        "case_id": case["case_id"],
        "origin": "v0.4-retained",
        "v04_expected_outcome": case["expected_outcome"],
        "v04_expected_metric_relation": case["expected_metric_relation"],
        "expected_v05_semantics": note if case["case_id"] in SUSPECT_RESOLUTIONS else semantics,
        "expected_v05_assertions": [],
        "v04_suspect_resolution": status,
        "fixture": deepcopy(case["mechanic/spec"]),
        "tags": list(case["tags"]),
    }


def _new(case_id: str, construct: str, fixture: str, semantics: str, assertions: list[str], **parameters: Any) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "origin": "v0.5-new",
        "construct": construct,
        "fixture": {"fixture": fixture, "parameters": parameters},
        "expected_v05_semantics": semantics,
        "expected_v05_assertions": assertions,
        "v04_suspect_resolution": None,
        "tags": [],
    }


NEW_CASES = [
    _new("V05-CD-01", "dynamic_reach", "overdetermination", "redundant realized edges survive although single-law necessity can miss them", ["realized_dependency_depth > necessity_backed_depth", "possible_redundant_causation == true"]),
    _new("V05-CD-02", "dynamic_reach", "necessary_chain", "pure necessary chain agrees on both depths", ["realized_dependency_depth == 3", "necessity_backed_depth == 3", "depth_gap == 0"], depth=3),
    _new("V05-CD-03", "dynamic_reach", "wide_fanout", "fanout width does not become path depth", ["realized_dependency_depth == 1", "necessity_backed_depth == 1"], width=8),
    _new("V05-CD-04", "dynamic_reach", "redundant_then_deep", "a redundant layer followed by a necessary downstream layer exposes a nonzero gap", ["realized_dependency_depth == 3", "necessity_backed_depth < realized_dependency_depth"]),
    _new("V05-CD-05", "binding_semantics", "binding_identity", "unregistered binding replacement is semantically different", ["binding_pairing == identity", "equivalence_applied == false"]),
    _new("V05-CD-06", "occurrence_identity", "event_time_shift", "event ids and absolute timestamps do not alter semantic occurrence identity", ["semantic_occurrence_equal == true"]),
    _new("V05-CD-07", "dynamic_reach", "noop_writer", "no-op commits cannot source realized or necessity edges", ["realized_dependency_depth == 0", "necessity_backed_depth == 0"]),
    _new("V05-CD-08", "activation_inertness", "activated_inert", "activation and paired behavioral inertness are independently reportable", ["activated == true", "behaviorally_inert == true"]),
    _new("V05-CE-01", "environmental_behavior", "same_outcome_different_path", "same outcome and different causal path occupy their own quadrant", ["outcome_differentiated == false", "causal_path_differentiated == true"]),
    _new("V05-CE-02", "environmental_behavior", "different_outcome_same_path", "different outcomes can share one normalized path structure", ["outcome_differentiated == true", "causal_path_differentiated == false"]),
    _new("V05-CE-03", "environmental_behavior", "different_outcome_different_path", "both axes can differ", ["outcome_differentiated == true", "causal_path_differentiated == true"]),
    _new("V05-CE-04", "environmental_behavior", "same_outcome_same_path", "both axes can remain invariant", ["outcome_differentiated == false", "causal_path_differentiated == false"]),
    _new("V05-CE-05", "outcome_differentiation", "outcome_partitions", "one-plus-three, two-plus-two, gradient, sign split, transient and recovery patterns remain auditable", ["partition_signatures_are_explicit == true"]),
    _new("V05-CE-06", "causal_path_differentiation", "path_multiplicity", "path signature is identity-insensitive and multiplicity-sensitive", ["id_time_invariant == true", "multiplicity_preserved == true"]),
    _new("V05-SN-01", "structural_evidence", "exact_duplicate", "registered duplicate is an exact match", ["exact_match == true"]),
    _new("V05-SN-02", "structural_evidence", "one_trigger_edit", "one added trigger is an explicit near-copy", ["near_copy == true", "edit_count == 1", "edit_kind == add_trigger"]),
    _new("V05-SN-03", "structural_evidence", "one_effect_edit", "one added effect is an explicit near-copy", ["near_copy == true", "edit_count == 1", "edit_kind == add_effect"]),
    _new("V05-SN-04", "structural_evidence", "simple_union", "a two-reference structural union yields conservative recombination evidence", ["recombination_detected == true", "source_reference_count == 2", "coverage == 1.0"]),
    _new("V05-SN-05", "structural_evidence", "field_substitution", "field substitution changes semantic structure but preserves abstract topology", ["semantic_exact_match == false", "abstract_topology_exact_match == true"]),
    _new("V05-SN-06", "structural_evidence", "same_fields_different_topology", "read/write or temporal relations can differ over the same fields", ["abstract_topology_exact_match == false"]),
    _new("V05-SN-07", "activation_inertness", "novel_but_inert", "structural evidence remains while runtime behavior is inert", ["semantic_exact_match == false", "behaviorally_inert == true"]),
    _new("V05-SN-08", "cross_construct", "simple_but_deep", "low structural novelty and high realized reach can coexist", ["exact_match == true", "realized_dependency_depth >= 2"]),
]


CASES = [_old_expected(case) for case in V04_CASES] + NEW_CASES
