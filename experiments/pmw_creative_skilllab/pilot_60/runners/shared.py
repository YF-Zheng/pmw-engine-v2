"""Shared, deterministic worlds for the Creative SkillLab pilot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRegistry
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry_document
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_actor,
    instantiate_area,
    parse_actor_blueprint,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    Gate3Content,
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ecology import (
    parse_ecology_spec,
    sample_ecology,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.harvest import parse_harvest_spec
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import change_loadout, skill_ref
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    MaterialDefinition,
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import GameplaySession, clock_entity
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import SkillBlueprint, parse_skill_blueprint
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import initialize_time_budget
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.weather import parse_weather_spec
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import build_gameplay_world


SCENARIOS: dict[str, dict[str, float]] = {
    "wet_forest": {
        "temperature": 42.0, "wetness": 0.78, "electric_field": 0.25,
        "mist": 0.60, "biomass": 0.66, "ore": 0.25, "light": 0.55,
        "wind": 0.30, "toxin": 0.12, "stability": 0.70,
        "smoke": 0.08, "conductivity": 0.34,
    },
    "dry_basin": {
        "temperature": 76.0, "wetness": 0.16, "electric_field": 0.20,
        "mist": 0.10, "biomass": 0.32, "ore": 0.58, "light": 0.90,
        "wind": 0.48, "toxin": 0.20, "stability": 0.62,
        "smoke": 0.26, "conductivity": 0.18,
    },
    "storm_plateau": {
        "temperature": 52.0, "wetness": 0.62, "electric_field": 0.72,
        "mist": 0.35, "biomass": 0.44, "ore": 0.46, "light": 0.38,
        "wind": 0.82, "toxin": 0.08, "stability": 0.48,
        "smoke": 0.10, "conductivity": 0.78,
    },
    "mist_cavern": {
        "temperature": 30.0, "wetness": 0.68, "electric_field": 0.40,
        "mist": 0.82, "biomass": 0.40, "ore": 0.74, "light": 0.18,
        "wind": 0.12, "toxin": 0.36, "stability": 0.58,
        "smoke": 0.18, "conductivity": 0.52,
    },
    "depleted_grove": {
        "temperature": 58.0, "wetness": 0.34, "electric_field": 0.32,
        "mist": 0.28, "biomass": 0.24, "ore": 0.20, "light": 0.72,
        "wind": 0.25, "toxin": 0.42, "stability": 0.36,
        "smoke": 0.42, "conductivity": 0.28,
    },
    "rain_edge": {
        "temperature": 48.0, "wetness": 0.64, "electric_field": 0.22,
        "mist": 0.42, "biomass": 0.58, "ore": 0.32, "light": 0.58,
        "wind": 0.28, "toxin": 0.10, "stability": 0.66,
        "smoke": 0.06, "conductivity": 0.30,
    },
    "lush_grove": {
        "temperature": 46.0, "wetness": 0.72, "electric_field": 0.18,
        "mist": 0.44, "biomass": 0.78, "ore": 0.18, "light": 0.62,
        "wind": 0.22, "toxin": 0.08, "stability": 0.74,
        "smoke": 0.04, "conductivity": 0.30,
    },
    "frozen_hollow": {
        "temperature": 5.0, "wetness": 0.58, "electric_field": 0.16,
        "mist": 0.52, "biomass": 0.30, "ore": 0.66, "light": 0.35,
        "wind": 0.38, "toxin": 0.10, "stability": 0.68,
        "smoke": 0.03, "conductivity": 0.46,
    },
    "fever_marsh": {
        "temperature": 55.0, "wetness": 0.80, "electric_field": 0.28,
        "mist": 0.64, "biomass": 0.70, "ore": 0.16, "light": 0.42,
        "wind": 0.14, "toxin": 0.34, "stability": 0.42,
        "smoke": 0.12, "conductivity": 0.64,
    },
}


@dataclass(frozen=True, slots=True)
class CaseSession:
    session: GameplaySession
    content: Gate3Content
    skill: SkillBlueprint
    material: MaterialDefinition


def build_case_session(case: dict[str, Any], *, equip: bool = True) -> CaseSession:
    """Build one isolated, fully compiled and authorized pilot session."""
    scenario_id = case["scenario"]["environment"]
    values = SCENARIOS[scenario_id]
    registry_doc = basic_registry_document()
    registry_doc["statuses"].extend(case.get("statuses", ()))
    registry_doc["actions"].append(_harvest_action())
    base_registry = ActionRegistry.parse(registry_doc)

    material = parse_material(case["material"])
    skill = parse_skill_blueprint(
        case["blueprint"], base_registry.statuses, material_authority((material,))
    )
    hero = instantiate_actor(
        parse_actor_blueprint(_actor_document("pilot_hero", case["scenario"].get("hero_traits", ()),
                                              case["scenario"].get("hero_hp", 80.0))),
        "pilot_hero", controller="human",
    )
    target = instantiate_actor(
        parse_actor_blueprint(_actor_document("pilot_target", case["scenario"].get("target_traits", ()),
                                              case["scenario"].get("target_hp", 80.0))),
        "pilot_target", controller="ai",
    )
    area = instantiate_area(parse_area_blueprint(_area_document(scenario_id, values)), "pilot_area")
    world = build_gameplay_world(
        f"pilot_{case['case_id']}", areas=(area,), actors=(hero, target),
        placements=((hero.id, area.id), (target.id, area.id)),
    )
    clock = clock_entity()
    world.entities[clock.id] = clock

    weather = _weather_specs(base_registry)
    ecology = sample_ecology(parse_ecology_spec(_ecology_document()), 604)
    harvest = parse_harvest_spec(_harvest_document(material.id))
    content = make_content(
        base_registry,
        skills=(skill,),
        weather_by_area={area.id: weather},
        ecology_by_area={area.id: ecology},
        harvest_by_area={area.id: (harvest,)},
        material_ids=(material.id,),
    )
    initialized = initialize_content_world(world, content)
    initialized = initialize_time_budget(initialized, 24)
    session = build_content_session(initialized, compile_content(content))
    if equip:
        operation = "equip_passive" if skill.kind == "passive_blueprint" else "equip_active"
        change_loadout(session, content.manifest, actor_id="pilot_hero", operation=operation,
                       skill=skill_ref(skill), slot=0)
    return CaseSession(session, content, skill, material)


def _actor_document(actor_id: str, traits: tuple[str, ...] | list[str], hp: float) -> dict[str, Any]:
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "actor_blueprint", "id": actor_id,
        "hp": {"max": 100.0, "initial": hp},
        "mana": {"max": 60.0, "initial": 45.0, "dynamics": None},
        "attributes": {"power": 6.0, "control": 7.0, "resilience": 5.0, "agility": 6.0},
        "traits": list(traits),
    }


def _area_document(scenario_id: str, values: dict[str, float]) -> dict[str, Any]:
    fields = []
    for field_id, initial in values.items():
        if field_id == "temperature":
            domain, target, rate = {"min": 0.0, "max": 100.0}, 50.0, 0.04
        else:
            domain, target, rate = {"min": 0.0, "max": 1.0}, 0.5, 0.08
        fields.append({
            "id": field_id, "domain": domain, "initial": initial,
            "target": target, "rate": rate, "curve": "linear",
            "max_persistent_patches": 4, "max_temporary_modifiers": 8,
        })
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint",
        "id": f"{scenario_id}_area", "ecology_state": "balanced", "fields": fields,
    }


def _weather_specs(registry: ActionRegistry) -> tuple[Any, ...]:
    docs = (
        {
            "protocol": "pmw-gameplay-v0.4", "id": "thunderfront", "label": "Thunderfront",
            "field_id": "electric_field", "enter_at": 0.65, "exit_at": 0.42,
            "duration_ticks": 4, "source_id": "plateau_weather",
            "common_effects": [{"id": "storm_wets_ground", "kind": "modify_field",
                                "target": {"kind": "current_area"}, "commitment": "required",
                                "field_id": "wetness", "amount": 0.07}],
            "trait_interactions": [{"trait_id": "conductive", "effect": {
                "id": "conductive_arc", "kind": "damage", "target": {"kind": "self"},
                "commitment": "required", "amount": 2.0,
            }}],
        },
        {
            "protocol": "pmw-gameplay-v0.4", "id": "heat_haze", "label": "Heat Haze",
            "field_id": "temperature", "enter_at": 70.0, "exit_at": 56.0,
            "duration_ticks": 4, "source_id": "basin_weather",
            "common_effects": [{"id": "heat_drains_biomass", "kind": "modify_field",
                                "target": {"kind": "current_area"}, "commitment": "required",
                                "field_id": "biomass", "amount": -0.04}],
            "trait_interactions": [{"trait_id": "heat_adapted", "effect": {
                "id": "heat_adapted_mana", "kind": "add_resource", "target": {"kind": "self"},
                "commitment": "required", "resource": "mana", "amount": 1.0,
            }}],
        },
        {
            "protocol": "pmw-gameplay-v0.4", "id": "living_fog", "label": "Living Fog",
            "field_id": "mist", "enter_at": 0.65, "exit_at": 0.40,
            "duration_ticks": 3, "source_id": "cavern_weather",
            "common_effects": [{"id": "fog_dims_light", "kind": "modify_field",
                                "target": {"kind": "current_area"}, "commitment": "required",
                                "field_id": "light", "amount": -0.06}],
            "trait_interactions": [{"trait_id": "mist_attuned", "effect": {
                "id": "mist_attuned_heal", "kind": "heal", "target": {"kind": "self"},
                "commitment": "required", "amount": 1.0,
            }}],
        },
        {
            "protocol": "pmw-gameplay-v0.4", "id": "rain_front", "label": "Rain Front",
            "field_id": "wetness", "enter_at": 0.67, "exit_at": 0.45,
            "duration_ticks": 4, "source_id": "rain_weather",
            "common_effects": [{"id": "rain_cools_air", "kind": "modify_field",
                                "target": {"kind": "current_area"}, "commitment": "required",
                                "field_id": "temperature", "amount": -4.0}],
            "trait_interactions": [],
        },
        {
            "protocol": "pmw-gameplay-v0.4", "id": "verdant_surge", "label": "Verdant Surge",
            "field_id": "biomass", "enter_at": 0.72, "exit_at": 0.50,
            "duration_ticks": 4, "source_id": "grove_weather",
            "common_effects": [{"id": "verdure_filters_toxin", "kind": "modify_field",
                                "target": {"kind": "current_area"}, "commitment": "required",
                                "field_id": "toxin", "amount": -0.05}],
            "trait_interactions": [],
        },
        {
            "protocol": "pmw-gameplay-v0.4", "id": "smoke_heat_front", "label": "Smoke Heat Front",
            "field_id": "smoke", "enter_at": 0.45, "exit_at": 0.24,
            "duration_ticks": 3, "source_id": "smoke_weather",
            "common_effects": [{"id": "smoke_traps_heat", "kind": "modify_field",
                                "target": {"kind": "current_area"}, "commitment": "required",
                                "field_id": "temperature", "amount": 5.0}],
            "trait_interactions": [],
        },
    )
    return tuple(parse_weather_spec(doc, registry.statuses) for doc in docs)


def _ecology_document() -> dict[str, Any]:
    return {
        "protocol": "pmw-gameplay-v0.4", "id": "pilot_biosphere", "label": "Pilot Biosphere",
        "initial_regime": "balanced", "sample_count": 3,
        "regimes": [
            {"id": "balanced", "label": "Balanced", "clue": "Biomass is self-sustaining.",
             "baselines": [{"field_id": "biomass", "target": 0.55, "rate": 0.08, "curve": "linear"}]},
            {"id": "stressed", "label": "Stressed", "clue": "Growth has entered a low attractor.",
             "baselines": [{"field_id": "biomass", "target": 0.25, "rate": 0.03, "curve": "linear"}]},
            {"id": "recovering", "label": "Recovering", "clue": "Growth is returning slowly.",
             "baselines": [{"field_id": "biomass", "target": 0.65, "rate": 0.05, "curve": "linear"}]},
        ],
        "transitions": [
            {"id": "collapse", "from": "balanced", "to": "stressed",
             "condition": {"field_id": "biomass", "comparator": "lte", "threshold": 0.32},
             "window_ticks": 2, "clue": "Low biomass persists for two ticks."},
            {"id": "regrowth", "from": "stressed", "to": "recovering",
             "condition": {"field_id": "biomass", "comparator": "gte", "threshold": 0.48},
             "window_ticks": 2, "clue": "Restored biomass persists for two ticks."},
        ],
    }


def _harvest_action() -> dict[str, Any]:
    return {
        "id": "gather_pilot_node", "version": 1, "action_type": "harvest",
        "cost": {"duration": 2, "mana": 0},
        "scope": {"selectors": ["self"], "relation_types": []},
        "effects": [{"id": "gather_marker", "kind": "add_resource", "target": {"kind": "self"},
                     "commitment": "required", "resource": "mana", "amount": 0}],
    }


def _harvest_document(material_id: str) -> dict[str, Any]:
    return {
        "protocol": "pmw-gameplay-v0.4", "id": "pilot_biomass_node", "label": "Pilot Biomass Node",
        "action_id": "gather_pilot_node", "source": {"kind": "abundance", "id": "biomass"},
        "material_id": material_id, "threshold": 0.35, "consumption": 0.10,
        "base_yield": 1, "overharvest": None, "lucky": None,
    }
