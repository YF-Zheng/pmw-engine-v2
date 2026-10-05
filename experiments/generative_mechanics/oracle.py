"""Deterministic hidden Oracle Suite construction.

This module is deliberately not imported by generation or the standard
evaluator.  The compact manifest and fixed algorithm rebuild the suite; runs
and traces are not checked in.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .scenario import Scenario, public_calibration_paths, validate_scenario
from .spec import load_skill
from .substrate import CHANNELS, ENVIRONMENT_VARIANTS


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "oracle" / "manifest.json"
ENVIRONMENTS = ("fragile_bridge", "industrial_yard", "mine", "wetland")
CATEGORY_ORDER = (
    "short_combat", "long_combat", "resource_limited", "multi_target",
    "environmental_hazard", "aftermath",
)
HORIZON_WEIGHTS = {
    "short_combat": {"combat_end": 0.70, "short": 0.20, "medium": 0.10},
    "long_combat": {"combat_end": 0.50, "short": 0.30, "medium": 0.20},
    "resource_limited": {"combat_end": 0.45, "short": 0.35, "medium": 0.20},
    "multi_target": {"combat_end": 0.55, "short": 0.30, "medium": 0.15},
    "environmental_hazard": {"combat_end": 0.35, "short": 0.40, "medium": 0.25},
    "aftermath": {"combat_end": 0.15, "short": 0.30, "medium": 0.55},
}
CAPABILITY_WEIGHTS = {
    "short_combat": {"combat": .50, "survival": .10, "control": .15, "utility": .10, "exploration_world_impact": .15},
    "long_combat": {"combat": .35, "survival": .25, "control": .15, "utility": .10, "exploration_world_impact": .15},
    "resource_limited": {"combat": .15, "survival": .35, "control": .20, "utility": .20, "exploration_world_impact": .10},
    "multi_target": {"combat": .25, "survival": .15, "control": .30, "utility": .10, "exploration_world_impact": .20},
    "environmental_hazard": {"combat": .05, "survival": .30, "control": .20, "utility": .25, "exploration_world_impact": .20},
    "aftermath": {"combat": .05, "survival": .10, "control": .15, "utility": .15, "exploration_world_impact": .55},
}


def _manifest(path: str | Path = MANIFEST_PATH) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {"protocol", "seed", "case_count"}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("oracle manifest must contain exactly protocol, seed, case_count")
    if raw["protocol"] != "gm-oracle-v0.2":
        raise ValueError("unsupported oracle protocol")
    if not isinstance(raw["seed"], int) or not 120 <= raw["case_count"] <= 300:
        raise ValueError("oracle seed/count contract violated")
    return raw


def _one_slot_skill_ids() -> tuple[str, ...]:
    ids = []
    for path in sorted((ROOT / "skills").glob("*.json")):
        if path.name == "manifest.json":
            continue
        skill = load_skill(path)
        if skill.slot_cost == 1:
            ids.append(skill.id)
    if len(ids) < 10:
        raise ValueError("oracle requires at least ten one-slot seed skills")
    return tuple(ids)


def _program(category: str, rng: random.Random) -> tuple[list[dict[str, Any]], float]:
    steps = rng.randint(1, 4)
    program: list[dict[str, Any]] = [
        {"op": "cast", "skill": "each_active", "target": "zone"},
        {"op": "step", "repeats": steps},
    ]
    combat_end = 0.0
    if category in {"long_combat", "environmental_hazard"}:
        combat_end = float(rng.choice((4, 6, 8, 12)))
        program.extend((
            {"op": "advance", "to": combat_end},
            {"op": "step", "repeats": rng.randint(1, 4)},
        ))
    elif category == "resource_limited":
        program.extend((
            {"op": "cast", "skill": "each_active", "target": "zone"},
            {"op": "step", "repeats": rng.randint(1, 3)},
        ))
    return program, combat_end


def build_oracle_suite(manifest_path: str | Path = MANIFEST_PATH) -> tuple[Scenario, ...]:
    """Rebuild the canonical, hidden scenario distribution."""
    manifest = _manifest(manifest_path)
    rng = random.Random(manifest["seed"])
    skill_ids = list(_one_slot_skill_ids())
    variants = tuple(sorted(ENVIRONMENT_VARIANTS))
    cases: list[Scenario] = []
    for index in range(manifest["case_count"]):
        category = CATEGORY_ORDER[index % len(CATEGORY_ORDER)]
        environment = ENVIRONMENTS[(index + rng.randrange(len(ENVIRONMENTS))) % len(ENVIRONMENTS)]
        variant = variants[(index + rng.randrange(len(variants))) % len(variants)]
        backpack = rng.sample(skill_ids, 10)
        active = rng.sample(backpack, 6)
        override_count = 1 + index % 4
        override_channels = rng.sample(list(CHANNELS), override_count)
        initial_fields = {
            channel: round(rng.randint(0, 20) / 20.0, 2)
            for channel in override_channels
        }
        program, combat_end = _program(category, rng)
        short = combat_end + float(rng.choice((8, 12, 16, 24)))
        medium = short + float(rng.choice((32, 48, 64, 96)))
        raw = {
            "id": f"oracle_{index:03d}",
            "split": "oracle",
            "category": category,
            "target_count": 3 if category == "multi_target" else 1,
            "environment": environment,
            "environment_variant": variant,
            "initial_fields": initial_fields,
            "build": {"backpack": backpack, "active": active},
            "program": program,
            "horizons": {"combat_end": combat_end, "short": short, "medium": medium},
            "horizon_weights": HORIZON_WEIGHTS[category],
            "weights": CAPABILITY_WEIGHTS[category],
        }
        cases.append(validate_scenario(raw))
    return tuple(cases)


def canonical_oracle_cases() -> list[dict[str, Any]]:
    """Return a stable projection useful for determinism auditing."""
    result = []
    for scenario in build_oracle_suite():
        result.append({
            "id": scenario.id,
            "category": scenario.category,
            "environment": scenario.environment,
            "environment_variant": scenario.environment_variant,
            "initial_fields": dict(sorted(scenario.initial_fields.items())),
            "backpack": list(scenario.build.backpack),
            "active": list(scenario.build.active),
            "program": [
                {name: getattr(command, name) for name in command.__dataclass_fields__}
                for command in scenario.program
            ],
            "horizons": scenario.horizons,
            "horizon_weights": scenario.horizon_weights,
        })
    return result


def public_scenario_assets() -> tuple[Path, ...]:
    """Assets permitted in generator prompts: calibration only."""
    return public_calibration_paths()


def evaluate_oracle_intrinsic(
    active_skill_ids, *, catalog=None, compile_mechanic=None, world_setup=None,
    suite: tuple[Scenario, ...] | None = None,
):
    """Compute the hidden ``OracleIntrinsicPower`` executable target."""
    from .power_v02 import evaluate_power
    from .compiler import compile_skill

    return evaluate_power(
        suite or build_oracle_suite(), active_skill_ids, split="oracle",
        catalog=catalog,
        compile_mechanic=compile_mechanic or compile_skill,
        world_setup=world_setup,
    )


def evaluate_oracle_personalized_delta(
    candidate_skill: str, *, catalog=None, compile_mechanic=None,
    world_setup=None, score_fn=None, cache=None,
    suite: tuple[Scenario, ...] | None = None,
):
    """Compute the hidden ``OraclePersonalizedDelta`` executable target.

    This is intentionally exact and expensive: every Oracle context performs
    the frozen 10-skill versus 11-skill legal-build search. It belongs in the
    final Oracle pass, not request generation or the cheap evaluator loop.
    """
    from .power_v02 import evaluate_contextual_power
    from .compiler import compile_skill

    return evaluate_contextual_power(
        suite or build_oracle_suite(), candidate_skill, split="oracle",
        catalog=catalog,
        compile_mechanic=compile_mechanic or compile_skill,
        world_setup=world_setup, score_fn=score_fn, cache=cache,
    )
