"""Production-stack evidence for v0.5 construct separation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..compiler import compile_skill
from ..cross_environment_v04 import QUARTET_ENVIRONMENTS, REGISTERED_CONTEXTS, matched_quartet_scenario
from ..free_evaluation_v05.causal import evaluate_dependency_profile
from ..free_evaluation_v05.environment import _environment_row, summarize_environment_rows
from ..free_evaluation_v05.structure import evaluate_structural_evidence
from ..spec import validate_skill
from .production_validation import VALIDATIONS, raw_spec


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "results" / "v05_production_validation.json"


def _sample(raw: dict[str, Any]):
    return SimpleNamespace(
        sample_id=f"v05.production.{raw['id']}", baseline="world_substrate",
        mechanic=validate_skill(raw), raw_mechanic=raw,
    )


def _full_stack(raw: dict[str, Any], context_id: str, purpose: str) -> dict[str, Any]:
    item = _sample(raw)
    context = next(value for value in REGISTERED_CONTEXTS if value.id == context_id)
    environment_rows = [
        _environment_row(item, environment, dict(context.public_initial_fields))
        for environment in QUARTET_ENVIRONMENTS
    ]
    environmental = summarize_environment_rows(environment_rows)
    scenario = matched_quartet_scenario(item, "mine", public_initial_fields=dict(context.public_initial_fields))
    dynamic = evaluate_dependency_profile(
        scenario, item.mechanic.id, catalog={item.mechanic.id: item.mechanic},
        compile_mechanic=compile_skill,
    )
    structural = evaluate_structural_evidence(raw)
    inert = all(not row["net_outcome_effect"] for row in environment_rows) and all(
        not row["normalized_path_signature"]["nodes"] and not row["normalized_path_signature"]["edges"]
        for row in environment_rows
    )
    return {
        "purpose": purpose,
        "execution_level": "full_production_stack",
        "context_id": context_id,
        "mechanic": raw,
        "dynamic_reach": dynamic,
        "environmental_behavior": environmental,
        "structural_evidence": structural,
        "behaviorally_inert": inert,
    }


def run() -> dict[str, Any]:
    rows = [
        _full_stack(raw, context_id, f"retained_v04_{purpose}")
        for purpose, raw, context_id, _expectation in VALIDATIONS
    ]
    near_trigger = raw_spec("v05_near_trigger", [("temperature", 0.3)], triggers=[("wetness", "gt", 0.5)])
    near_effect = raw_spec("v05_near_effect", [("temperature", 0.3), ("wetness", 0.2)])
    recombination = raw_spec("v05_recombination", [("temperature", 0.3), ("wetness", -0.4)])
    semantic_wet = raw_spec("v05_semantic_wet", [("wetness", 0.3)])
    semantic_sound = raw_spec("v05_semantic_sound", [("sound_level", 0.3)])
    topology_periodic = raw_spec("v05_periodic_topology", [("temperature", 0.3)], periodic={"interval": 2.0, "repeats": 2})
    additions = (
        (near_trigger, "near_copy_one_trigger"),
        (near_effect, "near_copy_one_effect"),
        (recombination, "conservative_two_module_recombination"),
        (semantic_wet, "semantic_field_wetness"),
        (semantic_sound, "semantic_field_sound_same_abstract_topology"),
        (topology_periodic, "same_field_different_abstract_temporal_topology"),
    )
    rows.extend(_full_stack(raw, "neutral", purpose) for raw, purpose in additions)
    synthetic_only = [
        {
            "purpose": "isolated_overdetermined_source_intervention",
            "execution_level": "synthetic_only_construct_test",
            "reason": "a production depth gap exists, but isolating the exact redundant-source intervention requires controlled traces",
            "covered_by_case": "V05-CD-01",
        },
        {
            "purpose": "event_and_absolute_time_identity_replacement",
            "execution_level": "synthetic_only_construct_test",
            "reason": "frozen SkillSpec cannot author replacement event ids or absolute timestamps",
            "covered_by_case": "V05-CD-06",
        },
    ]
    all_rows = rows + synthetic_only
    for index, row in enumerate(all_rows, 1):
        row["validation_id"] = f"V05-PV-{index:02d}"
    by_purpose = {row["purpose"]: row for row in rows}
    wet = by_purpose["semantic_field_wetness"]["structural_evidence"]
    sound = by_purpose["semantic_field_sound_same_abstract_topology"]["structural_evidence"]
    checks = {
        "dependency_depth_exceeds_necessity_depth": any(
            row["dynamic_reach"].get("depth_gap", 0) > 0 for row in rows
        ),
        "same_outcome_different_path": any(
            not row["environmental_behavior"]["outcome_differentiated"]
            and row["environmental_behavior"]["causal_path_differentiated"] for row in rows
        ),
        "different_outcome_same_path": any(
            row["environmental_behavior"]["outcome_differentiated"]
            and not row["environmental_behavior"]["causal_path_differentiated"] for row in rows
        ),
        "semantic_different_abstract_same": (
            wet["semantic_structure"]["fingerprint"] != sound["semantic_structure"]["fingerprint"]
            and wet["abstract_topology"]["fingerprint"] == sound["abstract_topology"]["fingerprint"]
        ),
        "one_trigger_near_copy": by_purpose["near_copy_one_trigger"]["structural_evidence"]["near_copy"],
        "one_effect_near_copy": by_purpose["near_copy_one_effect"]["structural_evidence"]["near_copy"],
        "simple_union_recombination": by_purpose["conservative_two_module_recombination"]["structural_evidence"]["recombination"]["recombination_detected"],
        "structurally_nonmatching_and_behaviorally_inert": any(
            not row["structural_evidence"]["exact_match"] and row["behaviorally_inert"] for row in rows
        ),
        "exact_match_and_realized_depth_at_least_two": any(
            row["structural_evidence"]["exact_match"]
            and (row["dynamic_reach"].get("realized_dependency_depth") or 0) >= 2 for row in rows
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"production construct validation failed: {checks}")
    output = {
        "protocol_version": "gm-free-evaluation-v0.5-candidate",
        "validation_count": len(all_rows),
        "full_production_stack_count": len(rows),
        "synthetic_only_count": len(synthetic_only),
        "retained_v04_production_validation_count": len(VALIDATIONS),
        "construct_checks": checks,
        "validations": all_rows,
        "construct_boundaries": {
            "necessity": "single-law ablation lower bound",
            "recombination_false": "not proof of non-recombination",
            "exact_non_match": "weak registry evidence only",
        },
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    result = run()
    print(json.dumps({
        "validation_count": result["validation_count"],
        "full_production_stack_count": result["full_production_stack_count"],
        "synthetic_only_count": result["synthetic_only_count"],
        "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
    }, indent=2, sort_keys=True))
