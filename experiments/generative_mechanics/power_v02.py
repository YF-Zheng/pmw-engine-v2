"""Authoritative horizon-aware power and contextual estimands (v0.2)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Any, Callable, Iterable, Protocol

from .build_search import (
    MAX_AUGMENTED_BACKPACK,
    BuildScore,
    SearchResult,
    search_best,
)
from .compiler import compile_skill
from .runner import ScenarioRun, load_skill_catalog, run_scenario

CAPABILITIES = ("Combat", "Survival", "Control", "Utility", "ExplorationWorldImpact")
HORIZONS = ("combat_end", "short", "medium")


@dataclass(frozen=True, slots=True)
class PowerScaleContract:
    """The single numerical scale used by every execution-based evaluator."""

    schema_version: str = "gm-power-scale-v0.2"
    multiplier: float = 8.0
    horizons: tuple[str, ...] = HORIZONS
    intrinsic_estimand: str = "IntrinsicPower"
    contextual_estimand: str = "ContextualMarginalPower"

    def scale(self, value: float) -> float:
        return float(value) * self.multiplier

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "multiplier": self.multiplier,
            "horizons": list(self.horizons),
            "estimands": [self.intrinsic_estimand, self.contextual_estimand],
        }


POWER_SCALE = PowerScaleContract()


class MechanicCompiler(Protocol):
    def __call__(self, mechanic: Any) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class HorizonScore:
    name: str
    weight: float
    capabilities: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "weight": self.weight, "capabilities": self.capabilities}


@dataclass(frozen=True, slots=True)
class ScenarioScore:
    scenario_id: str
    value: float
    capabilities: dict[str, float]
    horizons: tuple[HorizonScore, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "value": self.value,
            "capabilities": self.capabilities,
            "horizons": [item.to_dict() for item in self.horizons],
        }


@dataclass(frozen=True, slots=True)
class IntrinsicPower:
    split: str
    typical_power: float
    p90_power: float
    ceiling_power: float
    capability_vector: dict[str, float]
    interaction_surface: float
    persistent_world_impact: float
    scenario_scores: tuple[ScenarioScore, ...]
    scale: PowerScaleContract = POWER_SCALE

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimand": self.scale.intrinsic_estimand,
            "split": self.split,
            "TypicalPower": self.typical_power,
            "P90Power": self.p90_power,
            "CeilingPower": self.ceiling_power,
            "capability_vector": self.capability_vector,
            "InteractionSurface": self.interaction_surface,
            "PersistentWorldImpact": self.persistent_world_impact,
            "power_scale": self.scale.to_dict(),
            "scenario_scores": [item.to_dict() for item in self.scenario_scores],
        }


@dataclass(frozen=True, slots=True)
class ContextAudit:
    scenario_id: str
    backpack: tuple[str, ...]
    best_before: BuildScore
    best_after: BuildScore
    delta: float
    before_legal_builds: int
    after_legal_builds: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "backpack": list(self.backpack),
            "best_before": {"skills": list(self.best_before.skills), "value": self.best_before.value},
            "best_after": {"skills": list(self.best_after.skills), "value": self.best_after.value},
            "delta": self.delta,
            "before_legal_builds": self.before_legal_builds,
            "after_legal_builds": self.after_legal_builds,
        }


@dataclass(frozen=True, slots=True)
class ContextualMarginalPower:
    candidate_skill: str
    split: str
    mean: float
    p90: float
    maximum: float
    contexts: tuple[ContextAudit, ...]
    scale: PowerScaleContract = POWER_SCALE

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimand": self.scale.contextual_estimand,
            "candidate_skill": self.candidate_skill,
            "split": self.split,
            "mean": self.mean,
            "p90": self.p90,
            "max": self.maximum,
            "power_scale": self.scale.to_dict(),
            "contexts": [item.to_dict() for item in self.contexts],
        }


@dataclass(slots=True)
class ContextualSearchCache:
    """Reusable exact-search cache; keys include the full scenario and backpack context."""

    before: dict[tuple[str, tuple[str, ...]], SearchResult]
    values: dict[tuple[str, str, tuple[str, ...]], float]

    def __init__(self) -> None:
        self.before = {}
        self.values = {}


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _split(value: str) -> str:
    # held_out is a read compatibility alias; v0.2 artifacts emit evaluation.
    return "evaluation" if value == "held_out" else value


def _zones(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {
        item["id"]: item["components"]
        for item in state["entities"]
        if "zone" in item.get("components", {})
    }
    if not result:
        raise ValueError("evaluation requires at least one zone")
    return result


def _leaf_differences(left: Any, right: Any, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    if isinstance(left, dict) and isinstance(right, dict):
        result: set[tuple[str, ...]] = set()
        for key in set(left) | set(right):
            result |= _leaf_differences(left.get(key), right.get(key), (*prefix, str(key)))
        return result
    return {prefix} if left != right else set()


def _direct_totals(state: dict[str, Any]) -> dict[str, float]:
    result = {key: 0.0 for key in ("damage", "heal", "buff", "debuff")}
    for entity in state["entities"]:
        values = entity.get("components", {}).get("direct_outcome")
        if values:
            for key in result:
                result[key] += float(values.get(key, 0.0))
    return result


def state_capability_delta(
    with_state: dict[str, Any], baseline_state: dict[str, Any],
) -> tuple[dict[str, float], int, set[str]]:
    """Compute a paired capability vector at one explicit observation horizon."""
    with_zones, base_zones = _zones(with_state), _zones(baseline_state)
    if set(with_zones) != set(base_zones):
        raise ValueError("paired runs have different zone sets")

    def aggregate(zones, component, field, *, total=False):
        values = [float(zone[component][field]) for zone in zones.values()]
        return sum(values) if total else sum(values) / len(values)

    def delta(component, key, *, total=False):
        return aggregate(with_zones, component, key, total=total) - aggregate(
            base_zones, component, key, total=total
        )

    direct_with, direct_base = _direct_totals(with_state), _direct_totals(baseline_state)
    direct = {key: direct_with[key] - direct_base[key] for key in direct_with}
    capabilities = {
        "Combat": (
            20.0 * delta("outcome", "discharges", total=True)
            + 12.0 * delta("outcome", "charged_ore", total=True)
            + 5.0 * max(0.0, delta("fields", "fire_intensity"))
            + 100.0 * direct["damage"]
        ),
        "Survival": (
            10.0 * delta("fields", "ground_stability")
            + 6.0 * delta("fields", "visibility")
            - 4.0 * max(0.0, delta("fields", "fire_intensity"))
            - 3.0 * max(0.0, delta("fields", "water_level"))
            + 100.0 * direct["heal"]
        ),
        "Control": 4.0 * sum(
            abs(delta("fields", key))
            for key in ("wetness", "electric_field", "sound_level", "visibility", "ground_stability")
        ) + 100.0 * direct["debuff"],
        "Utility": 3.0 * sum(
            abs(delta("fields", key)) for key in ("temperature", "water_level", "visibility")
        ) + 2.0 * abs(delta("process", "alert")) + 100.0 * direct["buff"],
        "ExplorationWorldImpact": 5.0 * sum(
            len(_leaf_differences(base_zones[key], with_zones[key])) for key in with_zones
        ),
    }
    differences = {
        (zone_id, *path)
        for zone_id in with_zones
        for path in _leaf_differences(base_zones[zone_id], with_zones[zone_id])
    }
    return capabilities, len(differences), {path[1] for path in differences if len(path) > 1}


def _capability_weights(scenario: Any) -> dict[str, float]:
    aliases = {
        "combat": "Combat", "survival": "Survival", "control": "Control",
        "utility": "Utility", "world_impact": "ExplorationWorldImpact",
        "exploration_world_impact": "ExplorationWorldImpact",
    }
    result = {name: 0.0 for name in CAPABILITIES}
    for key, value in _field(scenario, "weights").items():
        canonical = aliases.get(key, key)
        if canonical not in result:
            raise ValueError(f"unknown capability weight {key!r}")
        result[canonical] = float(value)
    return result


def _horizon_weights(scenario: Any) -> dict[str, float]:
    raw = _field(scenario, "horizon_weights", None)
    if raw is None:
        # Compatibility for v0.1 fixtures only; v0.2 scenarios must carry this field.
        raw = {"combat_end": 0.5, "short": 0.3, "medium": 0.2}
    result = {name: float(raw[name]) for name in HORIZONS}
    if not math.isclose(sum(result.values()), 1.0, abs_tol=1e-9):
        raise ValueError("horizon weights must sum to 1.0")
    return result


def _law_counter(run: ScenarioRun, prefix: str) -> Counter[str]:
    return Counter(
        law_id for root in run.roots for law_id in root.triggered_law_ids
        if law_id.startswith(prefix)
    )


def evaluate_power(
    scenarios: Iterable[Any], active_skill_ids: Iterable[str], *,
    split: str = "evaluation", catalog: dict[str, Any] | None = None,
    compile_mechanic: MechanicCompiler = compile_skill,
    world_setup: Callable[[Any], None] | None = None,
    scale: PowerScaleContract = POWER_SCALE,
) -> IntrinsicPower:
    """Evaluate intrinsic build power through the one authoritative v0.2 path."""
    requested_split = _split(split)
    selected = tuple(sorted(
        (item for item in scenarios if _split(_field(item, "split")) == requested_split),
        key=lambda item: _field(item, "id"),
    ))
    if not selected:
        raise ValueError(f"no scenarios in split {requested_split!r}")
    catalog = catalog or load_skill_catalog()
    active = tuple(sorted(active_skill_ids))
    missing = set(active) - set(catalog)
    if missing:
        raise ValueError(f"unknown active skills: {sorted(missing)}")

    scores: list[ScenarioScore] = []
    surfaces: list[int] = []
    persistent: list[int] = []
    for scenario in selected:
        with_run = run_scenario(
            scenario, active, catalog=catalog,
            compile_mechanic=compile_mechanic, world_setup=world_setup,
        )
        baseline = run_scenario(
            scenario, (), catalog=catalog,
            compile_mechanic=compile_mechanic, world_setup=world_setup,
        )
        horizon_weights = _horizon_weights(scenario)
        horizon_scores: list[HorizonScore] = []
        combined = {name: 0.0 for name in CAPABILITIES}
        medium_difference = 0
        for horizon in HORIZONS:
            capabilities, differences, _ = state_capability_delta(
                with_run.horizons[horizon], baseline.horizons[horizon]
            )
            scaled = {name: scale.scale(value) for name, value in capabilities.items()}
            weight = horizon_weights[horizon]
            for name in CAPABILITIES:
                combined[name] += weight * scaled[name]
            horizon_scores.append(HorizonScore(horizon, weight, scaled))
            if horizon == "medium":
                medium_difference = differences
        weights = _capability_weights(scenario)
        value = sum(combined[name] * weights[name] for name in CAPABILITIES)
        scores.append(ScenarioScore(_field(scenario, "id"), value, combined, tuple(horizon_scores)))
        surfaces.append(len(_law_counter(with_run, "gm.world.") - _law_counter(baseline, "gm.world.")))
        persistent.append(medium_difference)

    values = sorted(item.value for item in scores)
    vector = {
        name: sum(item.capabilities[name] for item in scores) / len(scores)
        for name in CAPABILITIES
    }
    return IntrinsicPower(
        requested_split,
        sum(values) / len(values),
        values[max(0, math.ceil(0.9 * len(values)) - 1)],
        max(values), vector,
        sum(surfaces) / len(surfaces),
        sum(persistent) / len(persistent),
        tuple(scores), scale,
    )


def _scenario_backpack(scenario: Any) -> tuple[str, ...]:
    build = _field(scenario, "build", {})
    backpack = tuple(_field(build, "backpack", ()))
    if len(backpack) != 10:
        raise ValueError(f"scenario {_field(scenario, 'id')!r} must provide a 10-skill backpack")
    return backpack


def evaluate_contextual_power(
    scenarios: Iterable[Any], candidate_skill: str, *, split: str = "evaluation",
    catalog: dict[str, Any] | None = None,
    compile_mechanic: MechanicCompiler = compile_skill,
    world_setup: Callable[[Any], None] | None = None,
    cache: ContextualSearchCache | None = None,
    score_fn: Callable[[Any, tuple[str, ...]], float] | None = None,
) -> ContextualMarginalPower:
    """Exact Best10 versus Best10+Candidate marginal power in every context."""
    requested_split = _split(split)
    selected = tuple(sorted(
        (item for item in scenarios if _split(_field(item, "split")) == requested_split),
        key=lambda item: _field(item, "id"),
    ))
    if not selected:
        raise ValueError(f"no scenarios in split {requested_split!r}")
    catalog = catalog or load_skill_catalog()
    if candidate_skill not in catalog:
        raise ValueError(f"unknown candidate skill: {candidate_skill}")
    cache = cache or ContextualSearchCache()
    candidate_cache_key = repr(catalog[candidate_skill])
    audits: list[ContextAudit] = []

    for scenario in selected:
        scenario_id = _field(scenario, "id")
        backpack = tuple(sorted(_scenario_backpack(scenario)))
        if candidate_skill in backpack:
            raise ValueError(f"candidate {candidate_skill!r} already exists in {scenario_id!r} backpack")
        missing = set(backpack) - set(catalog)
        if missing:
            raise ValueError(f"unknown backpack skills: {sorted(missing)}")

        def value(build: tuple[str, ...]) -> float:
            canonical = tuple(sorted(build))
            namespace = candidate_cache_key if candidate_skill in canonical else "__seed_backpack__"
            key = (namespace, scenario_id, canonical)
            if key not in cache.values:
                cache.values[key] = (
                    float(score_fn(scenario, canonical)) if score_fn is not None
                    else evaluate_power(
                        (scenario,), canonical, split=requested_split, catalog=catalog,
                        compile_mechanic=compile_mechanic, world_setup=world_setup,
                    ).typical_power
                )
            return cache.values[key]

        before_key = (scenario_id, backpack)
        if before_key not in cache.before:
            cache.before[before_key] = search_best((catalog[item] for item in backpack), value)
        before = cache.before[before_key]
        after = search_best(
            (catalog[item] for item in (*backpack, candidate_skill)), value,
            max_backpack=MAX_AUGMENTED_BACKPACK,
        )
        audits.append(ContextAudit(
            scenario_id, backpack, before.best, after.best,
            after.best.value - before.best.value,
            before.legal_builds, after.legal_builds,
        ))

    deltas = sorted(item.delta for item in audits)
    return ContextualMarginalPower(
        candidate_skill, requested_split,
        sum(deltas) / len(deltas),
        deltas[max(0, math.ceil(0.9 * len(deltas)) - 1)],
        max(deltas), tuple(audits),
    )
