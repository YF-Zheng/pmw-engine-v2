"""Gate 3 integration: validate content, lower to PMW Laws, and attach a session."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from pmw import WorldState, parse_law

from .action_compiler import build_action_laws
from .actions import ACTOR_COMPONENT, ActionRegistry
from .contracts import GameplayContractError
from .ecology import ECOLOGY_COMPONENT, EcologyPlan, build_ecology_laws, ecology_component
from .harvest import (MATERIAL_INVENTORY_COMPONENT, RESOURCE_COMPONENT, HarvestSpec,
                      build_harvest_laws, material_inventory_component, resource_component)
from .loadout import build_loadout_laws
from .runtime import build_runtime, discover_profiles
from .skills import MechanismRegistryManifest, SkillBlueprint, passive_hook, registry_manifest
from .status import STATUS_COMPONENT, neutral_status_slot
from .weather import (TRAIT_PROJECTION_COMPONENT, WEATHER_COMPONENT, WeatherSpec,
                      build_weather_laws, trait_projection_component, weather_component)


@dataclass(frozen=True, slots=True)
class Gate3Content:
    action_registry: ActionRegistry
    skills: tuple[SkillBlueprint, ...]
    manifest: MechanismRegistryManifest
    weather_by_area: Mapping[str, tuple[WeatherSpec, ...]]
    ecology_by_area: Mapping[str, EcologyPlan]
    harvest_by_area: Mapping[str, tuple[HarvestSpec, ...]]
    stock_amounts_by_area: Mapping[str, Mapping[str, float]]
    material_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompiledGate3Content:
    content: Gate3Content
    laws: tuple[dict, ...]


def make_content(base_registry: ActionRegistry, *, skills: tuple[SkillBlueprint, ...] = (),
                 weather_by_area: Mapping[str, tuple[WeatherSpec, ...]] | None = None,
                 ecology_by_area: Mapping[str, EcologyPlan] | None = None,
                 harvest_by_area: Mapping[str, tuple[HarvestSpec, ...]] | None = None,
                 stock_amounts_by_area: Mapping[str, Mapping[str, float]] | None = None,
                 material_ids: tuple[str, ...] = ()) -> Gate3Content:
    skill_actions = tuple(item.action for item in skills)
    if set(base_registry.actions) & {item.id for item in skill_actions}:
        raise GameplayContractError("skill ID collides with an installed Action")
    hooks = (*base_registry.hooks.values(), *(passive_hook(item) for item in skills if item.kind == "passive_blueprint"))
    registry = ActionRegistry((*base_registry.actions.values(), *skill_actions), base_registry.statuses.values(), hooks)
    return Gate3Content(registry, skills, registry_manifest(skills),
                        MappingProxyType(dict(weather_by_area or {})),
                        MappingProxyType(dict(ecology_by_area or {})),
                        MappingProxyType(dict(harvest_by_area or {})),
                        MappingProxyType(dict(stock_amounts_by_area or {})), tuple(sorted(material_ids)))


def initialize_content_world(world: WorldState, content: Gate3Content) -> WorldState:
    """Return a detached initialized copy; runtime mutation remains exclusively Law-driven."""
    if world.tick != 0 or world.sim_time != 0 or world.scheduled_events:
        raise GameplayContractError("Gate 3 content initialization requires a detached time-zero WorldState")
    result = deepcopy(world)
    all_area_ids = set(content.weather_by_area) | set(content.ecology_by_area) | set(content.harvest_by_area)
    for area_id in all_area_ids:
        area = result.entities.get(area_id)
        if area is None or "pmw_gameplay_area" not in area.components:
            raise GameplayContractError(f"content Area {area_id!r} is unavailable")
    for area_id, specs in content.weather_by_area.items():
        area = result.entities[area_id]
        fields = area.components.get("pmw_gameplay_dynamics", {}).get("fields", {})
        for spec in specs:
            field = fields.get(spec.field_id)
            if field is None or not field["domain_min"] <= spec.exit_at < spec.enter_at <= field["domain_max"]:
                raise GameplayContractError("WeatherSpec threshold is outside its Area Field domain")
            if any(effect.field_id not in fields for effect in spec.common_effects):
                raise GameplayContractError("WeatherSpec effect targets an unavailable Area Field")
        area.components[WEATHER_COMPONENT] = weather_component(specs)
    for area_id, plan in content.ecology_by_area.items():
        area = result.entities[area_id]
        fields = area.components.get("pmw_gameplay_dynamics", {}).get("fields", {})
        reachable = set(plan.reachable_regimes)
        for regime in plan.spec.regimes:
            if regime.id not in reachable:
                continue
            for baseline in regime.baselines:
                field = fields.get(baseline.field_id)
                if field is None or not field["domain_min"] <= baseline.target <= field["domain_max"]:
                    raise GameplayContractError("Ecology baseline target is outside its Area Field domain")
                limit = 1.0 if baseline.curve == "linear" else 1.0 / (field["domain_max"] - field["domain_min"])
                if baseline.rate > limit:
                    raise GameplayContractError("Ecology baseline rate exceeds the stable curve limit")
        initial = next(item for item in plan.spec.regimes if item.id == plan.spec.initial_regime)
        for baseline in initial.baselines:
            fields[baseline.field_id]["baseline"].update({"target": baseline.target, "rate": baseline.rate, "curve": baseline.curve})
        area.components[ECOLOGY_COMPONENT] = ecology_component(plan)
    for area_id, specs in content.harvest_by_area.items():
        area = result.entities[area_id]
        fields = area.components.get("pmw_gameplay_dynamics", {}).get("fields", {})
        for spec in specs:
            if spec.source_kind == "abundance" and spec.source_id not in fields:
                raise GameplayContractError("Harvest abundance Field is unavailable")
        area.components[RESOURCE_COMPONENT] = resource_component(specs, stock_amounts=content.stock_amounts_by_area.get(area_id, {}))
    projected_traits = sorted({interaction.subject_id for specs in content.weather_by_area.values()
                               for spec in specs for interaction in spec.trait_interactions
                               if interaction.subject_kind == "trait"})
    for entity in result.entities.values():
        actor = entity.components.get(ACTOR_COMPONENT)
        if actor is None:
            continue
        entity.components[MATERIAL_INVENTORY_COMPONENT] = material_inventory_component(content.material_ids)
        entity.components[TRAIT_PROJECTION_COMPONENT] = trait_projection_component(actor, tuple(projected_traits))
        entity.components.setdefault(STATUS_COMPONENT, {"slots": {f"slot_{index}": neutral_status_slot() for index in range(8)}})
        entity.components.setdefault("pmw_gameplay_hooks", {"cooldowns": {item.id: -1.0 for item in content.action_registry.hooks.values()}})
    return result


def compile_content(content: Gate3Content) -> CompiledGate3Content:
    laws = [
        *build_action_laws(content.action_registry),
        *build_weather_laws(content.weather_by_area, content.action_registry.statuses),
        *build_ecology_laws(content.ecology_by_area),
        *build_harvest_laws(content.harvest_by_area),
        *build_loadout_laws(),
    ]
    ids = [item["id"] for item in laws]
    if len(ids) != len(set(ids)):
        raise GameplayContractError("Gate 3 compiled Law IDs collide")
    result = tuple(sorted(laws, key=lambda row: row["id"]))
    for law in result:
        parse_law(law)
    return CompiledGate3Content(content, result)


def build_content_session(world: WorldState, compiled: CompiledGate3Content):
    profiles = discover_profiles(world)
    return build_runtime(world, profiles, compiled.laws)
