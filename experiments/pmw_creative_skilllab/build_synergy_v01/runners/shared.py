"""Shared multi-skill Gameplay sessions for synergy experiments."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ACTOR_COMPONENT, ActionRegistry
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
    ECOLOGY_COMPONENT,
    parse_ecology_spec,
    sample_ecology,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.dynamics import DYNAMICS_COMPONENT
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.harvest import MATERIAL_INVENTORY_COMPONENT
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import change_loadout, skill_ref
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    MaterialDefinition,
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import GameplaySession, clock_entity
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.shields import SHIELD_COMPONENT
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import SkillBlueprint, parse_skill_blueprint
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.status import STATUS_COMPONENT
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    initialize_time_budget,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.weather import WEATHER_COMPONENT
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import build_gameplay_world
from experiments.pmw_creative_skilllab.pilot_60.runners.shared import (
    SCENARIOS,
    _area_document,
    _ecology_document,
    _weather_specs,
)


PILOT_ROOT = Path(__file__).resolve().parents[2] / "pilot_60"


@dataclass(frozen=True, slots=True)
class MultiSkillSession:
    session: GameplaySession
    content: Gate3Content
    skills: dict[str, SkillBlueprint]
    materials: tuple[MaterialDefinition, ...]
    loadout_results: tuple[Any, ...]


def load_skill_case(case_id: str) -> dict[str, Any]:
    paths = list((PILOT_ROOT / "skills").glob(f"{case_id}_*.json"))
    if len(paths) != 1:
        raise ValueError(f"expected one skill asset for {case_id}")
    return json.loads(paths[0].read_text())


def build_multi_skill_session(
    case_ids: tuple[str, ...],
    *,
    environment: str,
    field_overrides: dict[str, float] | None = None,
    hero_hp: float = 80.0,
    hero_mana: float = 45.0,
    target_hp: float = 60.0,
    target_mana: float = 20.0,
    target_traits: tuple[str, ...] = (),
    time_budget: int = 24,
    equip_skill_ids: tuple[str, ...] | None = None,
    disabled_weather_ids: tuple[str, ...] = (),
) -> MultiSkillSession:
    cases = tuple(load_skill_case(case_id) for case_id in case_ids)
    status_docs: dict[str, dict[str, Any]] = {}
    for case in cases:
        for status in case["statuses"]:
            previous = status_docs.setdefault(status["id"], status)
            if previous != status:
                raise ValueError(f"conflicting Status definition: {status['id']}")
    registry_doc = basic_registry_document()
    registry_doc["statuses"].extend(status_docs.values())
    base_registry = ActionRegistry.parse(registry_doc)

    materials = tuple(parse_material(case["material"]) for case in cases)
    skills = tuple(
        parse_skill_blueprint(
            case["blueprint"],
            base_registry.statuses,
            material_authority((material,)),
        )
        for case, material in zip(cases, materials, strict=True)
    )
    if len({skill.id for skill in skills}) != len(skills):
        raise ValueError("build contains duplicate Skill IDs")

    hero = instantiate_actor(
        parse_actor_blueprint(_actor_document("synergy_hero", hero_hp, hero_mana, ())),
        "synergy_hero",
        controller="human",
    )
    target = instantiate_actor(
        parse_actor_blueprint(
            _actor_document("synergy_target", target_hp, target_mana, target_traits)
        ),
        "synergy_target",
        controller="ai",
    )
    fields = deepcopy(SCENARIOS[environment])
    fields.update(field_overrides or {})
    area = instantiate_area(
        parse_area_blueprint(_area_document(environment, fields)),
        "synergy_area",
    )
    world = build_gameplay_world(
        "build_synergy_v01",
        areas=(area,),
        actors=(hero, target),
        placements=((hero.id, area.id), (target.id, area.id)),
    )
    clock = clock_entity()
    world.entities[clock.id] = clock
    ecology = sample_ecology(parse_ecology_spec(_ecology_document()), 1701)
    all_weather = _weather_specs(base_registry)
    unknown_weather = set(disabled_weather_ids) - {spec.id for spec in all_weather}
    if unknown_weather:
        raise ValueError(f"unknown disabled WeatherSpecs: {sorted(unknown_weather)}")
    enabled_weather = tuple(
        spec for spec in all_weather if spec.id not in set(disabled_weather_ids)
    )
    content = make_content(
        base_registry,
        skills=skills,
        weather_by_area={area.id: enabled_weather},
        ecology_by_area={area.id: ecology},
        material_ids=tuple(material.id for material in materials),
    )
    initialized = initialize_time_budget(initialize_content_world(world, content), time_budget)
    session = build_content_session(initialized, compile_content(content))
    active_slot = passive_slot = 0
    loadout_results = []
    equipped = set(equip_skill_ids if equip_skill_ids is not None else (skill.id for skill in skills))
    if equipped - {skill.id for skill in skills}:
        raise ValueError("arm equips a skill outside its build")
    for skill in skills:
        if skill.id not in equipped:
            continue
        if skill.kind == "passive_blueprint":
            operation, slot = "equip_passive", passive_slot
            passive_slot += 1
        else:
            operation, slot = "equip_active", active_slot
            active_slot += 1
        loadout_results.append(
            change_loadout(
                session,
                content.manifest,
                actor_id=hero.id,
                operation=operation,
                skill=skill_ref(skill),
                slot=slot,
            )
        )
    return MultiSkillSession(
        session,
        content,
        {skill.id: skill for skill in skills},
        materials,
        tuple(loadout_results),
    )


def _actor_document(
    actor_id: str,
    hp: float,
    mana: float,
    traits: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": actor_id,
        "hp": {"max": 100.0, "initial": hp},
        "mana": {"max": 60.0, "initial": mana, "dynamics": None},
        "attributes": {"power": 6.0, "control": 7.0, "resilience": 5.0, "agility": 6.0},
        "traits": list(traits),
    }


def observe_session(subject: Any) -> dict[str, Any]:
    state = subject.state if hasattr(subject, "state") else subject
    hero = state.entities["synergy_hero"]
    target = state.entities["synergy_target"]
    area = state.entities["synergy_area"]
    clock = state.entities["pmw:v04:clock"]
    return {
        "sim_time": state.sim_time,
        "hero": _actor_observation(hero),
        "target": _actor_observation(target),
        "fields": {
            field_id: {
                "value": row["value"],
                "effective_target": row["diagnostics"]["effective_target"],
                "effective_rate": row["diagnostics"]["effective_rate"],
            }
            for field_id, row in sorted(area.components[DYNAMICS_COMPONENT]["fields"].items())
        },
        "weather": deepcopy(area.components[WEATHER_COMPONENT]["states"]),
        "ecology": {
            "current": area.components[ECOLOGY_COMPONENT]["current"],
            "counters": deepcopy(area.components[ECOLOGY_COMPONENT]["counters"]),
        },
        "time_budget": deepcopy(clock.components[TIME_BUDGET_COMPONENT]),
        "inventory": deepcopy(hero.components[MATERIAL_INVENTORY_COMPONENT]["quantities"]),
        "scheduled_events": len(state.scheduled_events),
    }


def _actor_observation(entity: Any) -> dict[str, Any]:
    actor = entity.components[ACTOR_COMPONENT]
    statuses = entity.components[STATUS_COMPONENT]["slots"]
    shields = entity.components[SHIELD_COMPONENT]["slots"]
    return {
        "hp": actor["hp"],
        "mana": actor["mana"],
        "shield": actor["shield"],
        "traits": list(actor["traits"]),
        "statuses": [deepcopy(row) for _, row in sorted(statuses.items()) if row["active"]],
        "shield_layers": [deepcopy(row) for _, row in sorted(shields.items()) if row["active"]],
    }
