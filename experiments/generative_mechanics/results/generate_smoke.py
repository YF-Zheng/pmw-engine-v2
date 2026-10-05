"""Reproduce the checked-in deterministic Phase 2 smoke result."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.generative_mechanics.build_search import legal_builds
from experiments.generative_mechanics.compiler import compile_skill
from experiments.generative_mechanics.evaluator import emergent_reach, evaluate_build, evaluate_candidate
from experiments.generative_mechanics.exploit import detect_exploits
from experiments.generative_mechanics.runner import ROOT, load_skill_catalog
from experiments.generative_mechanics.scenario import load_scenario
from experiments.generative_mechanics.smoke import default_smoke


def result():
    catalog = load_skill_catalog()
    scenarios = [load_scenario(path) for path in sorted((ROOT / "scenarios").glob("*/*.json"))]
    skill = catalog["static_grave"]
    evaluation_wetland = next(item for item in scenarios if item.split == "evaluation" and item.environment == "wetland")
    one_slot = tuple(item for item in catalog.values() if item.slot_cost == 1)[:10]
    return {
        "build_enumeration_count": len(legal_builds(one_slot)),
        "candidate_evaluation": evaluate_candidate(scenarios, ("kindling_arc", "clear_sky"), skill.id, split="evaluation").to_dict(),
        "cross_environment": default_smoke(),
        "emergent_reach": emergent_reach(evaluation_wetland, (skill.id,), skill.id).to_dict(),
        "exploit_report": detect_exploits(compile_skill(skill)).to_dict(),
        "power_profile": evaluate_build(scenarios, (skill.id,), split="evaluation").to_dict(),
        "scenario_split": {"calibration": 6, "evaluation": 6},
    }


if __name__ == "__main__":
    path = Path(__file__).with_name("phase2_smoke.json")
    path.write_text(json.dumps(result(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
