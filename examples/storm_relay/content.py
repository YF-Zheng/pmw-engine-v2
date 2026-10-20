"""Authoritative, detached M0 world content.

This module intentionally contains declarations and construction only.  Action
legality, transactions, UI projection, and skill registration are supplied by
later Storm Relay stages.  The returned session is nevertheless a normal PMW
Gameplay session and all continuous world evolution is Law-driven.
"""

from __future__ import annotations

from typing import Any

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_actor,
    instantiate_area,
    parse_actor_blueprint,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import clock_entity
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import initialize_time_budget
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import build_gameplay_world

from .laws import m0_laws


SHALLOWS_ID = "storm_shallows"
TOWER_ID = "storm_tower"
PLAYER_ID = "storm_player"
GUARD_ID = "tower_guard"
CLOCK_ID = "pmw:v04:clock"

AREA_COMPONENT = "storm_relay_area"
ACTOR_COMPONENT = "storm_relay_actor"

MATERIAL_IDS = ("wet_moss", "thunder_crystal", "storm_glass")
RECIPE_IDS = ("lightning_seed", "fog_echo", "storm_glass_relay")


def shallow_blueprint_document() -> dict[str, Any]:
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint", "id": "storm_shallows_bp",
        "fields": [
            _field("humidity", .65, .70),
            _field("charge", .20, .20),
            _field("wet_moss_abundance", .80, .70),
            _field("thunder_crystal_abundance", .80, .60),
        ],
    }


def tower_blueprint_document() -> dict[str, Any]:
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint", "id": "storm_tower_bp",
        "fields": [_field("humidity", .40, .35), _field("charge", .45, .30)],
    }


def player_blueprint_document() -> dict[str, Any]:
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "actor_blueprint", "id": "storm_player_bp",
        "hp": {"max": 32, "initial": 32},
        "mana": {"max": 10, "initial": 8, "dynamics": None},
        "attributes": {"power": 2, "control": 2, "resilience": 2, "agility": 2},
        "traits": [],
    }


def guard_blueprint_document() -> dict[str, Any]:
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "actor_blueprint", "id": "tower_guard_bp",
        "hp": {"max": 42, "initial": 42},
        "mana": {"max": 0, "initial": 0, "dynamics": None},
        "attributes": {"power": 0, "control": 0, "resilience": 0, "agility": 0},
        "traits": ["conductive"],
    }


def make_storm_relay_world(*, time_budget: int = 23):
    """Build a fresh detached M0 WorldState with two independent Areas.

    The guard is present but inactive until the future ``start_core`` session
    command marks the encounter active.  Keeping it in the real WorldState
    gives weather laws one uniform Actor model while avoiding an ad-hoc combat
    object later.
    """
    shallows = instantiate_area(parse_area_blueprint(shallow_blueprint_document()), SHALLOWS_ID)
    tower = instantiate_area(parse_area_blueprint(tower_blueprint_document()), TOWER_ID)
    player = instantiate_actor(parse_actor_blueprint(player_blueprint_document()), PLAYER_ID, controller="human")
    guard = instantiate_actor(parse_actor_blueprint(guard_blueprint_document()), GUARD_ID, controller="ai")
    guard.tags.add("conductive")

    shallows.components[AREA_COMPONENT] = _area_state(
        stocks={"wet_moss": 2, "thunder_crystal": 2},
        discoveries={"ancient_inscription": False},
    )
    tower.components[AREA_COMPONENT] = _area_state(
        stocks={"storm_glass": 1},
        discoveries={"broken_storm_glass": False},
    )
    player.components[ACTOR_COMPONENT] = {
        "role": "player", "known_recipes": [], "crafted_receipts": [], "action_serial": 0,
    }
    guard.components[ACTOR_COMPONENT] = {
        "role": "tower_guard", "encounter_active": False, "attack_tags": ["visual_lock"],
    }

    world = build_gameplay_world(
        "storm_relay_m0", areas=(shallows, tower), actors=(player, guard),
        placements=((PLAYER_ID, SHALLOWS_ID), (GUARD_ID, TOWER_ID)),
        adjacencies=((SHALLOWS_ID, TOWER_ID),),
    )
    clock = clock_entity(CLOCK_ID)
    world.entities[clock.id] = clock

    # This initializes the standard material inventory, status slots, hooks,
    # registry manifest, and time ledger used by subsequent M0 stages.
    content = make_content(basic_registry(attack_base=4, power_scale=1, guard_base=2, resilience_scale=2, wait_mana=2),
                           material_ids=MATERIAL_IDS)
    initialized = initialize_content_world(world, content)
    initialized = initialize_time_budget(initialized, time_budget)
    # The expedition starts with one calibrated thunder crystal.  A second
    # crystal remains harvestable in the Shallows, so either complete build
    # still has to interact with the world while its two recipes have the
    # declared crystal cost.
    initialized.entities[PLAYER_ID].components["pmw_gameplay_material_inventory"]["quantities"]["thunder_crystal"] = 1.0
    return initialized


def build_storm_relay_session(*, time_budget: int = 23):
    """Return a fresh real PMW Gameplay session with M0 dynamics and weather."""
    world = make_storm_relay_world(time_budget=time_budget)
    content = make_content(basic_registry(attack_base=4, power_scale=1, guard_base=2, resilience_scale=2, wait_mana=2),
                           material_ids=MATERIAL_IDS)
    compiled = compile_content(content)
    # ``build_content_session`` discovers all field profiles and constructs an
    # Engine; M0 laws are appended before attachment, not simulated outside PMW.
    from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import CompiledGate3Content
    combined = CompiledGate3Content(content, tuple(sorted((*compiled.laws, *m0_laws()), key=lambda law: law["id"])))
    return build_content_session(world, combined)


def _field(field_id: str, initial: float, target: float) -> dict[str, Any]:
    return {"id": field_id, "domain": {"min": 0.0, "max": 1.0}, "initial": initial,
            "target": target, "rate": .05, "curve": "linear"}


def _area_state(*, stocks: dict[str, int], discoveries: dict[str, bool]) -> dict[str, Any]:
    return {
        "weather": "clear", "stock": stocks, "discoveries": discoveries,
        "console": {"core_started": False, "core_closed": False},
        "weather_transitions": 0,
    }
