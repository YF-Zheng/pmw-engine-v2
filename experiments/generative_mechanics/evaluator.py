"""Execution-based PowerProfile and paired emergent-reach evaluation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import math
from typing import Any, Iterable

from .build_search import search_best
from .compiler import compile_skill
from .exploit import detect_exploits
from .runner import ScenarioRun, run_scenario
from .spec import SkillSpec

CAPABILITIES = ("Combat", "Survival", "Control", "Utility", "ExplorationWorldImpact")


@dataclass(frozen=True, slots=True)
class ScenarioScore:
    scenario_id: str
    value: float
    capabilities: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {"scenario_id": self.scenario_id, "value": self.value, "capabilities": self.capabilities}


@dataclass(frozen=True, slots=True)
class PowerProfile:
    split: str
    typical_power: float
    p90_power: float
    ceiling_power: float
    personalized_build_delta: float | None
    synergy_amplification: float
    capability_vector: dict[str, float]
    interaction_surface: float
    exploit_risk: str
    persistent_world_impact: float
    scenario_scores: tuple[ScenarioScore, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "split": self.split, "TypicalPower": self.typical_power, "P90Power": self.p90_power,
            "CeilingPower": self.ceiling_power,
            "PersonalizedBuildDelta": self.personalized_build_delta,
            "SynergyAmplification": self.synergy_amplification,
            "capability_vector": self.capability_vector,
            "InteractionSurface": self.interaction_surface,
            "ExploitRisk": self.exploit_risk,
            "PersistentWorldImpact": self.persistent_world_impact,
            "scenario_scores": [item.to_dict() for item in self.scenario_scores],
        }


@dataclass(frozen=True, slots=True)
class EmergentReach:
    candidate_skill: str
    direct_law_count: int
    downstream_law_count: int
    affected_subsystem_count: int
    causal_depth: int
    persistent_consequence_count: int
    downstream_laws: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_skill": self.candidate_skill, "direct_law_count": self.direct_law_count,
            "downstream_law_count": self.downstream_law_count,
            "affected_subsystem_count": self.affected_subsystem_count, "causal_depth": self.causal_depth,
            "persistent_consequence_count": self.persistent_consequence_count,
            "downstream_laws": list(self.downstream_laws),
        }


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    candidate_skill: str
    best_before: tuple[str, ...]
    best_after: tuple[str, ...]
    profile: PowerProfile

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_skill": self.candidate_skill,
            "best_before": list(self.best_before), "best_after": list(self.best_after),
            "PowerProfile": self.profile.to_dict(),
        }


def _entities(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in state["entities"]}


def _zones(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    zones = {item["id"]: item["components"] for item in state["entities"] if "zone" in item.get("components", {})}
    if not zones:
        raise ValueError("evaluation requires at least one zone")
    return zones


def _leaf_differences(left: Any, right: Any, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    if isinstance(left, dict) and isinstance(right, dict):
        result: set[tuple[str, ...]] = set()
        for key in set(left) | set(right):
            result |= _leaf_differences(left.get(key), right.get(key), (*prefix, str(key)))
        return result
    if left != right:
        return {prefix}
    return set()


def _delta(with_run: ScenarioRun, baseline: ScenarioRun) -> tuple[dict[str, float], int, set[str]]:
    with_zones = _zones(with_run.final_state)
    base_zones = _zones(baseline.final_state)
    if set(with_zones) != set(base_zones):
        raise ValueError("paired runs have different zone sets")
    def aggregate(zones, component, field, *, total=False):
        values = [float(zone[component][field]) for zone in zones.values()]
        return sum(values) if total else sum(values) / len(values)
    with_zone = next(iter(with_zones.values())); base_zone = next(iter(base_zones.values()))
    wf, bf = with_zone["fields"], base_zone["fields"]
    d = lambda key: aggregate(with_zones, "fields", key) - aggregate(base_zones, "fields", key)
    outcome_delta = lambda key: aggregate(with_zones, "outcome", key, total=True) - aggregate(base_zones, "outcome", key, total=True)
    process_delta = lambda key: aggregate(with_zones, "process", key) - aggregate(base_zones, "process", key)
    capabilities = {
        "Combat": 20.0 * outcome_delta("discharges") + 12.0 * outcome_delta("charged_ore") + 5.0 * max(0.0, d("fire_intensity")),
        "Survival": 10.0 * d("ground_stability") + 6.0 * d("visibility") - 4.0 * max(0.0, d("fire_intensity")) - 3.0 * max(0.0, d("water_level")),
        "Control": 4.0 * sum(abs(d(key)) for key in ("wetness", "electric_field", "sound_level", "visibility", "ground_stability")),
        "Utility": 3.0 * sum(abs(d(key)) for key in ("temperature", "water_level", "visibility")) + 2.0 * abs(process_delta("alert")),
        "ExplorationWorldImpact": 5.0 * sum(len(_leaf_differences(base_zones[key], with_zones[key])) for key in with_zones),
    }
    differences = {(zone_id, *path) for zone_id in with_zones for path in _leaf_differences(base_zones[zone_id], with_zones[zone_id])}
    subsystems = {path[1] for path in differences if len(path) > 1}
    return capabilities, len(differences), subsystems


def _weights(scenario: Any) -> dict[str, float]:
    raw = scenario["weights"] if isinstance(scenario, dict) else scenario.weights
    aliases = {"combat": "Combat", "survival": "Survival", "control": "Control", "utility": "Utility", "world_impact": "ExplorationWorldImpact", "exploration_world_impact": "ExplorationWorldImpact"}
    result = {name: 0.0 for name in CAPABILITIES}
    for key, value in raw.items():
        canonical = aliases.get(key, key)
        if canonical not in result:
            raise ValueError(f"unknown capability weight {key!r}")
        result[canonical] = float(value)
    return result


def _law_counter(run: ScenarioRun, prefix: str) -> Counter[str]:
    return Counter(law_id for root in run.roots for law_id in root.triggered_law_ids if law_id.startswith(prefix))


def _evaluate_core(
    scenarios: tuple[Any, ...], active: tuple[str, ...], split: str,
    catalog: dict[str, SkillSpec] | None = None,
) -> PowerProfile:
    selected_scenarios = tuple(sorted((item for item in scenarios if (item["split"] if isinstance(item, dict) else item.split) == split), key=lambda item: item["id"] if isinstance(item, dict) else item.id))
    if not selected_scenarios:
        raise ValueError(f"no scenarios in split {split!r}")
    scores: list[ScenarioScore] = []
    surfaces: list[int] = []
    persistent: list[int] = []
    for scenario in selected_scenarios:
        with_run = run_scenario(scenario, active, catalog=catalog)
        baseline = run_scenario(scenario, (), catalog=catalog)
        capabilities, difference_count, _ = _delta(with_run, baseline)
        weights = _weights(scenario)
        value = sum(capabilities[name] * weights[name] for name in CAPABILITIES)
        scenario_id = scenario["id"] if isinstance(scenario, dict) else scenario.id
        scores.append(ScenarioScore(scenario_id, value, capabilities))
        world_delta = _law_counter(with_run, "gm.world.") - _law_counter(baseline, "gm.world.")
        surfaces.append(len(world_delta))
        persistent.append(difference_count)
    values = sorted(item.value for item in scores)
    p90 = values[max(0, math.ceil(.9 * len(values)) - 1)]
    vector = {name: sum(item.capabilities[name] for item in scores) / len(scores) for name in CAPABILITIES}
    return PowerProfile(
        split, sum(values) / len(values), p90, max(values), None, 0.0, vector,
        sum(surfaces) / len(surfaces), "LOW", sum(persistent) / len(persistent), tuple(scores),
    )


def _exploit_risk(active: tuple[str, ...], catalog: dict[str, SkillSpec]) -> str:
    laws = [law for skill_id in active for law in compile_skill(catalog[skill_id])["laws"]]
    return detect_exploits({"laws": laws}).severity.name


def _complete_profile(core, active, get_core, catalog, *, personalized=None):
    if active:
        empty_value = get_core(()).typical_power
        synergy = core.typical_power - sum(get_core((skill_id,)).typical_power for skill_id in active) + (len(active) - 1) * empty_value
    else:
        synergy = 0.0
    return replace(
        core, personalized_build_delta=personalized,
        synergy_amplification=synergy, exploit_risk=_exploit_risk(active, catalog),
    )


def evaluate_build(
    scenarios: Iterable[Any], active_skill_ids: Iterable[str], *, split: str = "held_out",
    catalog: dict[str, SkillSpec] | None = None,
) -> PowerProfile:
    from .runner import load_skill_catalog
    scenario_tuple = tuple(scenarios)
    active = tuple(sorted(active_skill_ids))
    cache: dict[tuple[str, ...], PowerProfile] = {}
    def get_core(build):
        canonical = tuple(sorted(build))
        if canonical not in cache:
            cache[canonical] = _evaluate_core(scenario_tuple, canonical, split, catalog)
        return cache[canonical]
    catalog = catalog or load_skill_catalog()
    missing = set(active) - set(catalog)
    if missing:
        raise ValueError(f"unknown active skills: {sorted(missing)}")
    return _complete_profile(get_core(active), active, get_core, catalog)


def evaluate_candidate(
    scenarios: Iterable[Any], existing_backpack: Iterable[str], candidate_skill: str,
    *, split: str = "held_out", catalog: dict[str, SkillSpec] | None = None,
) -> CandidateEvaluation:
    from .runner import load_skill_catalog
    scenario_tuple = tuple(scenarios)
    catalog = catalog or load_skill_catalog()
    existing = tuple(sorted(existing_backpack))
    if candidate_skill in existing:
        raise ValueError("candidate already exists in backpack")
    missing = set((*existing, candidate_skill)) - set(catalog)
    if missing:
        raise ValueError(f"unknown skills: {sorted(missing)}")
    cache: dict[tuple[str, ...], PowerProfile] = {}
    def get_core(build):
        canonical = tuple(sorted(build))
        if canonical not in cache:
            cache[canonical] = _evaluate_core(scenario_tuple, canonical, split, catalog)
        return cache[canonical]
    before = search_best((catalog[item] for item in existing), lambda build: get_core(build).typical_power).best
    after = search_best((catalog[item] for item in (*existing, candidate_skill)), lambda build: get_core(build).typical_power).best
    delta = after.value - before.value
    profile = _complete_profile(get_core(after.skills), after.skills, get_core, catalog, personalized=delta)
    return CandidateEvaluation(candidate_skill, before.skills, after.skills, profile)


def _world_address_counter(run: ScenarioRun) -> Counter[str]:
    addresses: Counter[str] = Counter()
    for root in run.roots:
        for event in root.trace.get("events", []):
            for commit in event.get("commits", []):
                for delta in commit.get("state_deltas", []):
                    if any(law_id.startswith("gm.world.") for law_id in delta.get("law_ids", [])):
                        addresses[delta["address"]] += 1
    return addresses


def _address_parts(address: str) -> tuple[str, str, tuple[str, ...]]:
    head, *path = address.split("/")
    kind, object_id = head.split(":", 1)
    return kind, object_id, tuple(path)


def _address_value(state: dict[str, Any], address: str) -> Any:
    kind, object_id, path = _address_parts(address)
    collection = state["entities"] if kind == "entity" else state["relations"]
    item = next((value for value in collection if value["id"] == object_id), None)
    if item is None:
        return None
    current: Any = item
    for index, segment in enumerate(path):
        if index == 0 and segment in item.get("components", {}):
            current = item["components"][segment]
        elif isinstance(current, dict):
            current = current.get(segment)
        else:
            return None
    return current


def emergent_reach(
    scenario: Any, build: Iterable[str], candidate_skill: str,
    *, catalog: dict[str, SkillSpec] | None = None,
) -> EmergentReach:
    active = tuple(sorted(build))
    if candidate_skill not in active:
        raise ValueError("candidate skill must be present in build")
    counterfactual = tuple(item for item in active if item != candidate_skill)
    with_run = run_scenario(scenario, active, catalog=catalog)
    without_run = run_scenario(scenario, counterfactual, catalog=catalog)
    direct = _law_counter(with_run, f"gm.skill.{candidate_skill}.")
    downstream_counter = _law_counter(with_run, "gm.world.") - _law_counter(without_run, "gm.world.")
    downstream = tuple(sorted(downstream_counter))
    downstream_addresses = _world_address_counter(with_run) - _world_address_counter(without_run)
    subsystems = {_address_parts(address)[2][0] for address in downstream_addresses if _address_parts(address)[2]}
    persistent_count = sum(
        1 for address in downstream_addresses
        if _address_value(with_run.final_state, address) != _address_value(without_run.final_state, address)
    )
    depth = 2 if downstream else 1 if direct else 0
    return EmergentReach(candidate_skill, sum(direct.values()), len(downstream), len(subsystems), depth, persistent_count, downstream)
