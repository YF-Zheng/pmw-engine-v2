"""Deterministic Gate 3 content-domain demonstration."""

from __future__ import annotations

import json

from .actions import ActionRegistry, ActionRequest, resolve_action
from .basics import basic_registry_document
from .blueprints import instantiate_actor, instantiate_area, parse_actor_blueprint, parse_area_blueprint
from .content_compiler import build_content_session, compile_content, initialize_content_world, make_content
from .ecology import parse_ecology_spec, sample_ecology
from .harvest import HarvestRequest, parse_harvest_spec, resolve_harvest
from .loadout import change_loadout, skill_ref
from .materials import material_authority, parse_material
from .runtime import advance_world_tick, clock_entity
from .skills import parse_skill_blueprint
from .weather import parse_weather_spec
from .worlds import build_gameplay_world


def build_gate3_demo():
    actor_raw = {"protocol": "pmw-gameplay-v0.4", "kind": "actor_blueprint", "id": "demo_actor",
                 "hp": {"max": 40, "initial": 40}, "mana": {"max": 30, "initial": 10, "dynamics": None},
                 "attributes": {"power": 4, "control": 5, "resilience": 3, "agility": 3}, "traits": ["mist_attuned"]}
    plain_actor_raw = {**actor_raw, "id": "plain_actor", "traits": []}
    area_raw = {"protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint", "id": "forest_area",
                "fields": [
                    {"id": "mist", "domain": {"min": 0, "max": 1}, "initial": .8, "target": .7,
                     "rate": .05, "curve": "linear", "max_persistent_patches": 3, "max_temporary_modifiers": 4},
                    {"id": "herbs", "domain": {"min": 0, "max": 1}, "initial": .7, "target": .7,
                     "rate": .1, "curve": "linear", "max_persistent_patches": 3, "max_temporary_modifiers": 4},
                ]}
    hero = instantiate_actor(parse_actor_blueprint(actor_raw), "hero_actor", controller="human")
    plain = instantiate_actor(parse_actor_blueprint(plain_actor_raw), "plain_actor", controller="ai")
    area = instantiate_area(parse_area_blueprint(area_raw), "mist_forest")
    world = build_gameplay_world("gate3_demo", areas=[area], actors=[hero, plain],
                                 placements=[(hero.id, area.id), (plain.id, area.id)])
    clock = clock_entity(); world.entities[clock.id] = clock

    registry_doc = basic_registry_document()
    registry_doc["actions"].append({
        "id": "gather_herbs", "version": 1, "action_type": "harvest",
        "cost": {"duration": 2, "mana": 0}, "scope": {"selectors": ["self"], "relation_types": []},
        "effects": [{"id": "harvest_marker", "kind": "add_resource", "target": {"kind": "self"},
                     "commitment": "required", "resource": "mana", "amount": 0}],
    })
    base_registry = ActionRegistry.parse(registry_doc)
    material = parse_material({
        "id": "mist_crystal", "tier": "rare", "region_rarity": "uncommon",
        "traits": [{"id": "mist_shaping", "effect_kinds": ["damage", "modify_field"],
                    "selectors": ["target_actor", "current_area"], "budget_points": 10}],
    })
    skill = parse_skill_blueprint({
        "protocol": "pmw-gameplay-v0.4", "kind": "skill_blueprint", "id": "mist_bolt", "version": 1,
        "trigger": "on_use", "condition": None, "duration": None,
        "cost": {"duration": 1, "mana": 2},
        "scope": {"selectors": ["current_area", "target_actor"], "relation_types": []},
        "effects": [
            {"id": "thicken_mist", "kind": "modify_field", "target": {"kind": "current_area"},
             "commitment": "required", "field_id": "mist", "amount": .05},
            {"id": "mist_damage", "kind": "damage", "target": {"kind": "target_actor"},
             "commitment": "required", "amount": 3,
             "targeting": {"sensing": "visual", "evadable": False}},
        ], "budget": {"limit": 8}, "max_firings_per_root": 1, "material_ids": ["mist_crystal"],
    }, base_registry.statuses, material_authority((material,)))
    weather = parse_weather_spec({
        "protocol": "pmw-gameplay-v0.4", "id": "living_mist", "label": "Living Mist", "field_id": "mist",
        "enter_at": .6, "exit_at": .4, "duration_ticks": 3, "source_id": "forest_weather",
        "common_effects": [{"id": "mist_feed", "kind": "modify_field", "target": {"kind": "current_area"},
                            "commitment": "required", "field_id": "mist", "amount": .01}],
        "trait_interactions": [{"trait_id": "mist_attuned", "effect": {
            "id": "mist_mana", "kind": "add_resource", "target": {"kind": "self"},
            "commitment": "required", "resource": "mana", "amount": 1,
            "targeting": {"sensing": "mana", "evadable": False}}}],
    }, base_registry.statuses)
    ecology = parse_ecology_spec({
        "protocol": "pmw-gameplay-v0.4", "id": "forest_cycle", "label": "Forest Cycle",
        "initial_regime": "thriving", "sample_count": 2,
        "regimes": [
            {"id": "thriving", "label": "Thriving", "clue": "Dense herb beds return quickly.",
             "baselines": [{"field_id": "herbs", "target": .7, "rate": .1, "curve": "linear"}]},
            {"id": "depleted", "label": "Depleted", "clue": "Bare soil replaces harvested beds.",
             "baselines": [{"field_id": "herbs", "target": .2, "rate": .02, "curve": "linear"}]},
        ],
        "transitions": [{"id": "overharvested", "from": "thriving", "to": "depleted",
                         "condition": {"field_id": "herbs", "comparator": "lte", "threshold": .5},
                         "window_ticks": 2, "clue": "Herb beds remain below half abundance."}],
    })
    harvest = parse_harvest_spec({
        "protocol": "pmw-gameplay-v0.4", "id": "forest_herbs", "label": "Forest Herbs",
        "action_id": "gather_herbs", "source": {"kind": "abundance", "id": "herbs"},
        "material_id": "mist_crystal", "threshold": .2, "consumption": .2, "base_yield": 1,
        "overharvest": {"below": .5, "target_delta": -.1, "rate_delta": -.02},
        "lucky": {"permission": "lucky_harvest", "duration_delta": -1, "yield_delta": 1},
    })
    plan = sample_ecology(ecology, 17)
    content = make_content(base_registry, skills=(skill,), weather_by_area={area.id: (weather,)},
                           ecology_by_area={area.id: plan}, harvest_by_area={area.id: (harvest,)},
                           material_ids=(material.id,))
    initialized = initialize_content_world(world, content)
    compiled = compile_content(content)
    return build_content_session(initialized, compiled), content, skill, harvest


def run_gate3_demo() -> dict:
    session, content, skill, harvest = build_gate3_demo()
    loadout = change_loadout(session, content.manifest, actor_id="hero_actor", operation="equip_active",
                             skill=skill_ref(skill), slot=0)
    first_tick = advance_world_tick(session)
    hero_mana_after_weather = session.state.entities["hero_actor"].components["pmw_gameplay_actor"]["mana"]
    plain_mana_after_weather = session.state.entities["plain_actor"].components["pmw_gameplay_actor"]["mana"]
    first_harvest = resolve_harvest(session, content.action_registry, harvest,
                                    HarvestRequest("harvest_one", "hero_actor", harvest.id, True),
                                    permissions=("lucky_harvest",))
    advance_world_tick(session)
    second_harvest = resolve_harvest(session, content.action_registry, harvest,
                                     HarvestRequest("harvest_two", "hero_actor", harvest.id))
    third_tick = advance_world_tick(session)
    cast = resolve_action(session, content.action_registry,
                          ActionRequest("cast_mist_bolt", "hero_actor", skill.id, "plain_actor"))
    area = session.state.entities["mist_forest"]
    actor = session.state.entities["hero_actor"]
    return {
        "weather": {"hero_mana": hero_mana_after_weather, "plain_mana": plain_mana_after_weather,
                    "state": area.components["pmw_gameplay_weather"]["states"]["living_mist"]},
        "harvest": {"first_duration": first_harvest.duration, "first_yield": first_harvest.yield_amount,
                    "first_consumption": first_harvest.consumption, "second_yield": second_harvest.yield_amount,
                    "inventory": actor.components["pmw_gameplay_material_inventory"]["quantities"]["mist_crystal"],
                    "abundance": area.components["pmw_gameplay_dynamics"]["fields"]["herbs"]["value"]},
        "ecology": {"current": area.components["pmw_gameplay_ecology"]["current"],
                    "baseline": area.components["pmw_gameplay_dynamics"]["fields"]["herbs"]["baseline"]},
        "skill": {"enemy_hp": session.state.entities["plain_actor"].components["pmw_gameplay_actor"]["hp"],
                  "budget_used": skill.budget_used, "trace_events": len(cast.event_result.trace.events)},
        "loadout_changed": loadout.changed,
        "world_step": third_tick.step,
        "scheduled_events": len(session.state.scheduled_events),
        "registry_entries": len(content.manifest.entries),
        "trace_present": bool(first_tick.event_result.trace.events and first_harvest.event_result.trace.events),
    }


if __name__ == "__main__":
    print(json.dumps(run_gate3_demo(), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
