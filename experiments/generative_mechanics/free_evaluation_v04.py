"""Integrated capability profiles for Free-Invention evaluation v0.4.

The profile is deliberately a collection of auditable measurements.  It has no
composite creativity score and performs no ranking across samples or models.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .causal_depth_v04 import evaluate_causal_depth
from .cross_environment_v04 import (
    QUARTET_ENVIRONMENTS,
    REGISTERED_CONTEXTS,
    evaluate_cross_environment_panel,
    matched_quartet_scenario,
    mechanic_runtime,
)
from .free_invention import FreeInventionSample, evaluate_free_invention_sample
from .structural_novelty import evaluate_structural_novelty


PROTOCOL_VERSION = "gm-free-evaluation-v0.4-candidate"
PROTOCOL_PATH = Path(__file__).with_name("evaluation") / "protocol_v0.4.json"


def _protocol_sha256() -> str:
    raw = PROTOCOL_PATH.read_bytes()
    protocol = json.loads(raw)
    if protocol.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Free evaluation manifest protocol mismatch")
    if protocol.get("aggregation", {}).get("composite_score") is not False:
        raise ValueError("Free evaluation manifest must forbid a composite score")
    return hashlib.sha256(raw).hexdigest()


def _causal_profile(sample: FreeInventionSample) -> dict[str, Any]:
    compiler, world_setup = mechanic_runtime(sample)
    catalog = {sample.mechanic.id: sample.mechanic}
    rows = []
    for context in sorted(REGISTERED_CONTEXTS, key=lambda item: item.id):
        for environment in QUARTET_ENVIRONMENTS:
            scenario = matched_quartet_scenario(
                sample,
                environment,
                public_initial_fields=context.public_initial_fields,
            )
            result = evaluate_causal_depth(
                scenario,
                sample.mechanic.id,
                catalog=catalog,
                compile_mechanic=compiler,
                world_setup=world_setup,
            ).to_dict()
            rows.append({"context_id": context.id, "environment": environment, **result})
    activated = [row for row in rows if row["candidate_activated"] is True]
    technically_unavailable = [
        row for row in rows
        if row["candidate_activated"] is None
    ]
    depths = [int(row["depth"]) for row in activated if row["available"]]
    return {
        "available": not technically_unavailable,
        "reason": None if not technically_unavailable else "one or more registered arms could not be evaluated",
        "estimand": "paired additional reachable gm.world law depth",
        "registered_context_count": len(REGISTERED_CONTEXTS),
        "environment_count_per_context": len(QUARTET_ENVIRONMENTS),
        "registered_arm_count": len(rows),
        "total_arm_count": len(rows),
        "activated_arm_count": len(activated),
        "activation_rate": len(activated) / len(rows) if rows else None,
        "conditional_on_activation": {
            "available": bool(depths),
            "reason": None if depths else "candidate did not activate in any registered arm",
            "depth_distribution": depths,
            "mean_depth": math.fsum(depths) / len(depths) if depths else None,
            "maximum_depth": max(depths) if depths else None,
            "nonzero_depth_arm_count": sum(value > 0 for value in depths),
        },
        "arms": rows,
    }


def _novelty_profile(sample: FreeInventionSample) -> dict[str, Any]:
    if sample.baseline != "world_substrate":
        return {
            "available": False,
            "reason": (
                "the registered structural reference catalog contains only "
                "WorldSubstrate SkillSpec mechanisms; cross-schema novelty is undefined"
            ),
        }
    return evaluate_structural_novelty(sample.raw_mechanic)


def evaluate_free_invention_profile(sample: FreeInventionSample) -> dict[str, Any]:
    """Evaluate one valid response without constructing a creativity total."""
    static = evaluate_free_invention_sample(sample)
    cross_environment = evaluate_cross_environment_panel(sample).to_dict()
    eligible_tracks = ["representation_interface"]
    if sample.baseline == "world_substrate":
        eligible_tracks.append("model_invention")
    return {
        "protocol_version": PROTOCOL_VERSION,
        "protocol_sha256": _protocol_sha256(),
        "generation_protocol": static["protocol_version"],
        "sample_id": sample.sample_id,
        "baseline": sample.baseline,
        "eligible_tracks": eligible_tracks,
        "interpretation": {
            "representation_interface": (
                "compares interface affordances; zero downstream behavior for direct "
                "outcomes is a manipulation check, not model failure"
            ),
            "model_invention": (
                "eligible only for WorldSubstrate samples generated under an identical interface"
            ),
            "aggregation_policy": "profile_only",
        },
        "static_evidence": static["static_evidence"],
        "contract_safety": static["contract_safety"],
        "dimensions": {
            "downstream_causal_depth": _causal_profile(sample),
            "cross_environment_differentiation": cross_environment,
            "structural_novelty": _novelty_profile(sample),
        },
    }


def evaluate_free_invention_profiles(
    samples: Iterable[FreeInventionSample],
) -> tuple[dict[str, Any], ...]:
    return tuple(evaluate_free_invention_profile(sample) for sample in samples)
