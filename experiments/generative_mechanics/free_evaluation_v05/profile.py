"""Integrated, non-aggregated v0.5 capability profile."""

from __future__ import annotations

import math
from typing import Any

from ..cross_environment_v04 import QUARTET_ENVIRONMENTS, REGISTERED_CONTEXTS, matched_quartet_scenario, mechanic_runtime
from ..free_invention import FreeInventionSample, evaluate_free_invention_sample
from .causal import evaluate_dependency_profile
from .environment import evaluate_environmental_behavior
from .semantic_contract import validate_semantic_contract
from .structure import evaluate_structural_evidence


PROTOCOL_VERSION = "gm-free-evaluation-v0.5-candidate"


def _dynamic_reach(sample: FreeInventionSample) -> dict[str, Any]:
    compiler, world_setup = mechanic_runtime(sample)
    catalog = {sample.mechanic.id: sample.mechanic}
    arms = []
    for context in sorted(REGISTERED_CONTEXTS, key=lambda item: item.id):
        for environment in QUARTET_ENVIRONMENTS:
            scenario = matched_quartet_scenario(
                sample, environment, public_initial_fields=context.public_initial_fields,
            )
            result = evaluate_dependency_profile(
                scenario, sample.mechanic.id, catalog=catalog,
                compile_mechanic=compiler, world_setup=world_setup,
            )
            arms.append({"context_id": context.id, "environment": environment, **result})
    activated = [row for row in arms if row.get("candidate_activated") is True]
    realized = [row["realized_dependency_depth"] for row in activated]
    necessity = [row["necessity_backed_depth"] for row in activated]
    gaps = [row["depth_gap"] for row in activated]
    return {
        "available": all(row.get("available") for row in arms),
        "registered_arm_count": len(arms),
        "activated_arm_count": len(activated),
        "activation_rate": len(activated) / len(arms) if arms else None,
        "conditional_on_activation": {
            "available": bool(activated),
            "realized_dependency_depth_distribution": realized,
            "necessity_backed_depth_distribution": necessity,
            "depth_gap_distribution": gaps,
            "mean_realized_dependency_depth": math.fsum(realized) / len(realized) if realized else None,
            "mean_necessity_backed_depth": math.fsum(necessity) / len(necessity) if necessity else None,
            "maximum_realized_dependency_depth": max(realized, default=None),
            "maximum_necessity_backed_depth": max(necessity, default=None),
            "nonzero_gap_arm_count": sum(gap > 0 for gap in gaps),
        },
        "arms": arms,
    }


def _structural(sample: FreeInventionSample) -> dict[str, Any]:
    if sample.baseline != "world_substrate":
        return {
            "available": False,
            "reason": "the 36-reference registry is WorldSubstrate-only; cross-schema structure is undefined",
        }
    return evaluate_structural_evidence(sample.raw_mechanic)


def _behavioral_inertness(environment: dict[str, Any]) -> dict[str, Any]:
    rows = [row for context in environment["contexts"] for row in context["environment_rows"]]
    no_outcome = all(not row["net_outcome_effect"] for row in rows)
    no_paths = all(
        not row["normalized_path_signature"]["nodes"]
        and not row["normalized_path_signature"]["edges"]
        for row in rows
    )
    return {
        "behaviorally_inert": no_outcome and no_paths,
        "no_committed_observed_state_difference": no_outcome,
        "no_candidate_induced_world_law_activity": no_paths,
        "registered_arm_count": len(rows),
        "interpretation": "runtime paired behavior only; structural evidence is reported independently",
    }


def evaluate_free_invention_profile_v05(sample: FreeInventionSample) -> dict[str, Any]:
    contract = validate_semantic_contract()
    static = evaluate_free_invention_sample(sample)
    dynamic = _dynamic_reach(sample)
    environment = evaluate_environmental_behavior(sample)
    structural = _structural(sample)
    eligible_tracks = ["representation_interface"]
    if sample.baseline == "world_substrate":
        eligible_tracks.append("model_invention")
    return {
        "protocol_version": PROTOCOL_VERSION,
        "semantic_contract_digest": contract["semantic_contract_digest"],
        "generation_protocol": static["protocol_version"],
        "sample_id": sample.sample_id,
        "baseline": sample.baseline,
        "eligible_tracks": eligible_tracks,
        "aggregation_policy": "capability_profile_only_no_score_no_rank",
        "validity": {
            "static_evidence": static["static_evidence"],
            "contract_safety": static["contract_safety"],
        },
        "activation": {
            "activation_rate": dynamic["activation_rate"],
            "activated_arm_count": dynamic["activated_arm_count"],
            "registered_arm_count": dynamic["registered_arm_count"],
            "definition": "effective candidate committed write",
        },
        "behavioral_inertness": _behavioral_inertness(environment),
        "structural_evidence": structural,
        "dynamic_reach": dynamic,
        "environmental_behavior": environment,
    }
