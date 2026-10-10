"""Reproducible Gate-4 generic-AI synergy demonstration."""

from __future__ import annotations

import json

from .action_compiler import build_action_session
from .actions import ActionRegistry
from .basics import basic_registry_document
from .blueprints import instantiate_actor, instantiate_area, parse_actor_blueprint, parse_area_blueprint
from .observation import ActorObservationBuilder, ObservationDisclosure
from .planner import BoundedPlanner, PlannerConfig
from .runtime import clock_entity
from .simulation import revalidate_and_execute
from .worlds import build_gameplay_world


def ai_demo_registry() -> ActionRegistry:
    document = basic_registry_document(attack_base=6.0, power_scale=0.0, wait_mana=4.0)
    document["actions"].extend([
        {
            "id": "raise_mist", "version": 1, "action_type": "skill", "builtin": False,
            "cost": {"duration": 1, "mana": 0.0},
            "scope": {"selectors": ["current_area"], "relation_types": []},
            "effects": [{
                "id": "mist_setup", "kind": "modify_field", "target": {"kind": "current_area"},
                "commitment": "required", "field_id": "mist", "amount": 0.8,
            }],
        },
        {
            "id": "mist_burst", "version": 1, "action_type": "skill", "builtin": False,
            "cost": {"duration": 1, "mana": 0.0},
            "scope": {"selectors": ["target_actor"], "relation_types": []},
            "effects": [{
                "id": "mist_damage", "kind": "damage", "target": {"kind": "target_actor"},
                "commitment": "required", "amount": 20.0,
                "condition": {"field": {"subject": "current_area", "key": "mist", "comparator": "gte", "value": 0.8}},
            }],
        },
    ])
    return ActionRegistry.parse(document)


def ai_demo_session():
    actor_blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4", "kind": "actor_blueprint", "id": "ai_demo_actor",
        "hp": {"max": 50, "initial": 50},
        "mana": {"max": 20, "initial": 10, "dynamics": None},
        "attributes": {"power": 0, "control": 0, "resilience": 0, "agility": 0},
        "traits": [],
    })
    area_blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint", "id": "ai_demo_area",
        "fields": [{
            "id": "mist", "domain": {"min": 0, "max": 1}, "initial": 0,
            "target": 0, "rate": 0, "curve": "linear",
            "max_persistent_patches": 2, "max_temporary_modifiers": 4,
        }],
    })
    monster = instantiate_actor(actor_blueprint, "ai_monster", controller="ai")
    hero = instantiate_actor(actor_blueprint, "ai_hero", controller="human")
    monster.components["pmw_gameplay_actor"]["active_equipped"][:2] = ["raise_mist", "mist_burst"]
    area = instantiate_area(area_blueprint, "ai_arena")
    world = build_gameplay_world(
        "gate4_ai_demo", areas=[area], actors=[monster, hero],
        placements=[(monster.id, area.id), (hero.id, area.id)],
    )
    clock = clock_entity(); world.entities[clock.id] = clock
    registry = ai_demo_registry()
    return build_action_session(world, registry=registry), registry


def run_ai_demo() -> dict:
    session, registry = ai_demo_session()
    disclosure = ObservationDisclosure.create(hostile_actor_ids=("ai_hero",))
    observation = ActorObservationBuilder().build(session, registry, "ai_monster", disclosure)
    planner = BoundedPlanner(registry, config=PlannerConfig(deadline_ms=None))
    planned = planner.choose(observation)
    executed = revalidate_and_execute(session, registry, planned.selected.request, disclosure=disclosure)
    return {
        "selected_action": planned.selected.request.action_id,
        "accepted": executed.accepted,
        "nodes_used": planned.nodes_used,
        "fallback_used": planned.fallback_used,
        "decision_log_sha256": planned.decision_log.canonical_sha256,
        "mist": session.state.entities["ai_arena"].components["pmw_gameplay_dynamics"]["fields"]["mist"]["value"],
    }


if __name__ == "__main__":
    print(json.dumps(run_ai_demo(), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
