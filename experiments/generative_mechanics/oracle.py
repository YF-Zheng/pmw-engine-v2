"""Deterministic hidden Oracle Suite construction.

This module is deliberately not imported by generation or the standard
evaluator.  The compact manifest and fixed algorithm rebuild the suite; runs
and traces are not checked in.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from .scenario import Scenario, public_calibration_paths, validate_scenario
from .spec import load_skill
from .substrate import CHANNELS, ENVIRONMENT_VARIANTS


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "oracle" / "manifest.json"
CONTEXTUAL_COUNTS = (12, 18, 24)
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
    expected = {"protocol", "seed", "case_count", "contextual_subset"}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError(
            "oracle manifest must contain exactly protocol, seed, case_count, contextual_subset"
        )
    if raw["protocol"] != "gm-oracle-v0.2":
        raise ValueError("unsupported oracle protocol")
    if not isinstance(raw["seed"], int) or not 120 <= raw["case_count"] <= 300:
        raise ValueError("oracle seed/count contract violated")
    contextual = raw["contextual_subset"]
    contextual_expected = {
        "protocol", "selection_seed", "default_case_count", "allowed_case_counts",
        "selection", "digests",
    }
    if not isinstance(contextual, dict) or set(contextual) != contextual_expected:
        raise ValueError("contextual subset manifest contract violated")
    if contextual["protocol"] != "gm-contextual-oracle-v0.3":
        raise ValueError("unsupported contextual Oracle protocol")
    if contextual["selection"] != "nested-category-environment-stratified-v1":
        raise ValueError("unsupported contextual Oracle selection")
    if contextual["allowed_case_counts"] != list(CONTEXTUAL_COUNTS):
        raise ValueError("contextual subset allowed counts must be 12, 18, 24")
    if contextual["default_case_count"] != 24 or not isinstance(contextual["selection_seed"], int):
        raise ValueError("contextual subset seed/default contract violated")
    if set(contextual["digests"]) != {str(value) for value in CONTEXTUAL_COUNTS}:
        raise ValueError("contextual subset digest contract violated")
    if not all(
        isinstance(value, str) and len(value) == 64
        for value in contextual["digests"].values()
    ):
        raise ValueError("contextual subset digests must be SHA-256 hex strings")
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
    """Return the full execution-semantic projection for determinism audits."""
    return [_scenario_projection(scenario) for scenario in build_oracle_suite()]


def _scenario_projection(scenario: Scenario) -> dict[str, Any]:
    """Canonical projection of every field that can affect execution utility."""
    return {
        "id": scenario.id,
        "split": scenario.split,
        "category": scenario.category,
        "environment": scenario.environment,
        "environment_variant": scenario.environment_variant,
        "initial_fields": dict(sorted(scenario.initial_fields.items())),
        "build": {
            "backpack": list(scenario.build.backpack),
            "active": list(scenario.build.active),
        },
        "program": [
            {name: getattr(command, name) for name in command.__dataclass_fields__}
            for command in scenario.program
        ],
        "horizons": dict(sorted(scenario.horizons.items())),
        "horizon_weights": dict(sorted(scenario.horizon_weights.items())),
        "weights": dict(sorted(scenario.weights.items())),
        "target_count": scenario.target_count,
    }


def contextual_subset_digest(suite: tuple[Scenario, ...]) -> str:
    """Hash selection plus every scenario input that affects execution utility."""
    payload = json.dumps(
        [_scenario_projection(item) for item in suite],
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def contextual_subset_audit(suite: tuple[Scenario, ...]) -> dict[str, Any]:
    """Return the compact, serializable coverage record used for preregistration."""
    return {
        "case_count": len(suite),
        "digest": contextual_subset_digest(suite),
        "case_ids": [item.id for item in suite],
        "categories": sorted({item.category for item in suite}),
        "environments": sorted({item.environment for item in suite}),
        "environment_variants": sorted({item.environment_variant for item in suite}),
        "distinct_backpacks": len({item.build.backpack for item in suite}),
        "distinct_active_builds": len({item.build.active for item in suite}),
        "distinct_initial_fields": len({
            json.dumps(item.initial_fields, sort_keys=True, separators=(",", ":"))
            for item in suite
        }),
    }


def _validate_contextual_coverage(suite: tuple[Scenario, ...], case_count: int) -> None:
    audit = contextual_subset_audit(suite)
    if audit["case_count"] != case_count:
        raise ValueError("contextual Oracle subset has the wrong size")
    if len(audit["categories"]) != len(CATEGORY_ORDER):
        raise ValueError("contextual Oracle subset must cover every category")
    if len(audit["environments"]) != len(ENVIRONMENTS):
        raise ValueError("contextual Oracle subset must cover every environment")
    if len(audit["environment_variants"]) < 3:
        raise ValueError("contextual Oracle subset has insufficient variant coverage")
    for key in ("distinct_backpacks", "distinct_active_builds", "distinct_initial_fields"):
        if audit[key] < case_count // 2:
            raise ValueError(f"contextual Oracle subset has insufficient {key} coverage")


def build_contextual_oracle_suite(
    manifest_path: str | Path = MANIFEST_PATH, *, case_count: int | None = None,
) -> tuple[Scenario, ...]:
    """Select the preregistered exact-search subset from the 144-case Oracle.

    Counts 12 and 18 are deterministic sensitivity-analysis profiles. The
    formal paper target defaults to 24: one case in every category/environment
    stratum. No contexts are generated specially for the contextual target.
    """
    manifest = _manifest(manifest_path)
    contract = manifest["contextual_subset"]
    requested = contract["default_case_count"] if case_count is None else case_count
    if requested not in CONTEXTUAL_COUNTS:
        raise ValueError("contextual Oracle case_count must be one of 12, 18, 24")

    suite = build_oracle_suite(manifest_path)
    by_stratum = {
        (category, environment): [
            item for item in suite
            if item.category == category and item.environment == environment
        ]
        for category in CATEGORY_ORDER for environment in ENVIRONMENTS
    }
    per_category = requested // len(CATEGORY_ORDER)
    offset = contract["selection_seed"] % len(ENVIRONMENTS)
    selected: list[Scenario] = []
    for category_index, category in enumerate(CATEGORY_ORDER):
        environment_indices = (
            range(len(ENVIRONMENTS)) if per_category == len(ENVIRONMENTS)
            else (
                (category_index + offset + step) % len(ENVIRONMENTS)
                for step in range(per_category)
            )
        )
        for environment_index in environment_indices:
            environment = ENVIRONMENTS[environment_index]
            candidates = by_stratum[(category, environment)]
            if not candidates:
                raise ValueError(f"empty Oracle stratum {category}/{environment}")
            selected.append(min(
                candidates,
                key=lambda item: hashlib.sha256(
                    f"{contract['selection_seed']}:{item.id}".encode("ascii")
                ).hexdigest(),
            ))
    result = tuple(sorted(selected, key=lambda item: item.id))
    _validate_contextual_coverage(result, requested)
    actual = contextual_subset_digest(result)
    expected = contract["digests"][str(requested)]
    if actual != expected:
        raise ValueError(
            f"contextual Oracle digest mismatch for {requested} cases: "
            f"expected {expected}, got {actual}"
        )
    return result


def public_scenario_assets() -> tuple[Path, ...]:
    """Assets permitted in generator prompts: calibration only."""
    return public_calibration_paths()


def _registered_intrinsic_suite(suite: tuple[Scenario, ...] | None) -> tuple[Scenario, ...]:
    canonical = build_oracle_suite()
    if suite is None:
        return canonical
    supplied = tuple(suite)
    if supplied != canonical:
        raise ValueError("custom intrinsic Oracle suites are not registered")
    return supplied


def _registered_contextual_suite(suite: tuple[Scenario, ...] | None) -> tuple[Scenario, ...]:
    if suite is None:
        return build_contextual_oracle_suite()
    supplied = tuple(suite)
    if len(supplied) not in CONTEXTUAL_COUNTS:
        raise ValueError("custom contextual Oracle suites are not registered")
    canonical = build_contextual_oracle_suite(case_count=len(supplied))
    if supplied != canonical:
        raise ValueError("custom contextual Oracle suites are not registered")
    return supplied


def evaluate_oracle_intrinsic(
    active_skill_ids, *, catalog=None, compile_mechanic=None, world_setup=None,
    suite: tuple[Scenario, ...] | None = None,
):
    """Compute the hidden ``OracleIntrinsicPower`` executable target."""
    from .power_v02 import evaluate_power
    from .compiler import compile_skill

    return evaluate_power(
        _registered_intrinsic_suite(suite), active_skill_ids, split="oracle",
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
        _registered_contextual_suite(suite),
        candidate_skill, split="oracle",
        catalog=catalog,
        compile_mechanic=compile_mechanic or compile_skill,
        world_setup=world_setup, score_fn=score_fn, cache=cache,
    )
