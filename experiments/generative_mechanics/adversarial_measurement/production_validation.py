"""End-to-end validation supplement for the synthetic adversarial attacks.

These runs use validated SkillSpec objects, the trusted compiler, fresh PMW
worlds, registered environment assets, and the production v0.4 evaluators.
They do not replace the precisely controlled synthetic attacks; they establish
that key positive/negative boundaries also occur through the full stack.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from experiments.generative_mechanics.causal_depth_v04 import evaluate_causal_depth
from experiments.generative_mechanics.compiler import compile_skill
from experiments.generative_mechanics.cross_environment_v04 import (
    PUBLIC_INITIAL_FIELDS,
    REGISTERED_CONTEXTS,
    evaluate_cross_environment_differentiation,
    matched_quartet_scenario,
)
from experiments.generative_mechanics.spec import validate_skill
from experiments.generative_mechanics.structural_novelty import evaluate_structural_novelty


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "results" / "production_validation.json"


def raw_spec(
    mechanic_id: str,
    effects: list[tuple[str, float]],
    *,
    duration: float = 0.0,
    periodic: dict[str, Any] | None = None,
    triggers: list[tuple[str, str, float]] | None = None,
) -> dict[str, Any]:
    return {
        "id": mechanic_id,
        "name": mechanic_id.replace("_", " ").title(),
        "target_scope": "zone",
        "effects": [{"field": field, "delta": delta} for field, delta in effects],
        "duration": duration,
        "periodic": periodic,
        "trigger_conditions": [
            {"field": field, "op": op, "value": value}
            for field, op, value in (triggers or [])
        ],
        "resource_cost": 0.0,
        "charges": 12,
        "slot_cost": 1,
    }


VALIDATIONS = (
    ("zero_effect_and_background_cancellation", raw_spec("audit_zero", [("temperature", 0.0)]), "neutral", "all four net signatures are empty despite distinct environment backgrounds"),
    ("equal_nonzero_net_effect", raw_spec("audit_equal_temperature", [("temperature", -0.8)]), "all_low", "all four environments share one nonzero net signature"),
    ("one_plus_three_partition", raw_spec("audit_one_env", [("wetness", 0.8)]), "all_low", "fragile_bridge differs while the other three environments share a signature"),
    ("two_plus_two_partition", raw_spec("audit_two_by_two", [("electric_field", 0.4)]), "all_low", "fragile_bridge/wetland and industrial_yard/mine form two signature groups"),
    ("deep_environment_invariant", raw_spec("audit_deep_invariant", [("wetness", 0.4)]), "all_low", "the same production signature in every environment still reaches a depth-two chain"),
    ("shallow_environment_sensitive", raw_spec("audit_shallow_sensitive", [("fire_intensity", -0.8)]), "all_low", "depth zero in the mine arm coexists with two environment signatures"),
    ("complex_self_contained", raw_spec("audit_complex_self", [("temperature", -0.8), ("fire_intensity", -0.8), ("sound_level", -0.4)]), "all_low", "a multi-effect exact-novel declaration can have little or no downstream depth"),
    ("simple_but_emergent", raw_spec("audit_environment_probe", [("electric_field", 0.65)]), "neutral", "one simple write reaches a deep, differentiated production world chain"),
    ("parallel_fanout", raw_spec("audit_parallel", [("fire_intensity", 0.7), ("water_level", 0.7), ("electric_field", 0.7)]), "neutral", "multi-field fanout exercises realized parallel and chained world consequences"),
    ("periodic_repeat", raw_spec("audit_periodic", [("wetness", 0.2)], periodic={"interval": 2.0, "repeats": 3}), "neutral", "repeated candidate pulses exercise multiplicity without counting candidate laws as depth"),
    ("delayed_duration", raw_spec("audit_delayed", [("temperature", 0.5)], duration=6.0), "neutral", "scheduled expiry and later world effects exercise temporal execution"),
    ("dead_trigger", raw_spec("audit_dead", [("temperature", 0.5)], triggers=[("temperature", "gt", 1.0)]), "neutral", "candidate never activates and all dynamic dimensions remain inert"),
)


def sample(raw: dict[str, Any]):
    return SimpleNamespace(
        sample_id=f"production.{raw['id']}",
        baseline="world_substrate",
        mechanic=validate_skill(raw),
        raw_mechanic=raw,
    )


def run() -> dict[str, Any]:
    rows = []
    contexts = {context.id: context for context in REGISTERED_CONTEXTS}
    for purpose, raw, context_id, semantic_expectation in VALIDATIONS:
        item = sample(raw)
        context = contexts[context_id]
        cross = evaluate_cross_environment_differentiation(
            item,
            context_id=context.id,
            public_initial_fields=dict(context.public_initial_fields),
        ).to_dict()
        scenario = matched_quartet_scenario(
            item,
            "mine",
            public_initial_fields=dict(context.public_initial_fields),
        )
        causal = evaluate_causal_depth(
            scenario,
            item.mechanic.id,
            catalog={item.mechanic.id: item.mechanic},
            compile_mechanic=compile_skill,
        ).to_dict()
        novelty = evaluate_structural_novelty(raw)
        signature_groups: dict[str, list[str]] = {}
        for effect in cross["environment_effects"]:
            signature = json.dumps(
                {
                    "state": effect["candidate_effect"],
                    "world_laws": effect["candidate_world_law_effect"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            signature_groups.setdefault(signature, []).append(effect["environment"])
        rows.append({
            "validation_id": f"PV-{len(rows)+1:02d}",
            "purpose": purpose,
            "semantic_expectation": semantic_expectation,
            "context_id": context.id,
            "execution_level": "full_production_stack",
            "mechanic": raw,
            "causal_depth": causal,
            "cross_environment": cross,
            "net_signature_environment_groups": sorted(
                (sorted(group) for group in signature_groups.values()),
                key=lambda group: (len(group), group),
            ),
            "structural_novelty": novelty,
        })
    output = {
        "execution_contract": {
            "skill_validation": "validate_skill",
            "compiler": "compile_skill",
            "world_execution": "run_scenario via production evaluators",
            "environment_scope": "registered four-environment neutral matched quartet",
            "causal_scope": "registered mine arm with production law ablations",
        },
        "validation_count": len(rows),
        "validations": rows,
        "limitations": [
            "Exact redundant-path and identity-shift interventions require controlled traces because SkillSpec cannot author world laws or event identities.",
            "The selected one-plus-three and two-plus-two production examples are descriptive validation fixtures, not additional confirmatory sampling strata.",
            "Background-noise cancellation is end-to-end demonstrated by the zero-effect arm, but arbitrary extra background laws cannot be injected without changing the frozen semantic contract.",
        ],
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    result = run()
    print(json.dumps({
        "validation_count": result["validation_count"],
        "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        "summaries": [
            {
                "id": row["validation_id"],
                "purpose": row["purpose"],
                "depth": row["causal_depth"]["depth"],
                "activated": row["causal_depth"]["candidate_activated"],
                "environmentally_differentiated": row["cross_environment"]["summary"]["environmentally_differentiated"],
                "distinct_net_signatures": row["cross_environment"]["summary"]["distinct_net_signature_count"],
                "novelty_available": row["structural_novelty"]["available"],
                "exact_novel": row["structural_novelty"].get("exact_novel_against_registry"),
            }
            for row in result["validations"]
        ],
    }, indent=2))
