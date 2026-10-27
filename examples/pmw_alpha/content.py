"""Declarative world content for PMW Alpha v0.2.

This module is deliberately boring in the useful sense: it declares the map,
actors, materials, and their time-zero state, then builds a normal Gameplay
``WorldState``.  Exploration rules, combat, skills, and narrative progression
belong to their own Alpha modules; none of them need a parallel world model.
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
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import clock_entity
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import initialize_time_budget
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import build_gameplay_world


CLOCK_ID = "pmw:v04:clock"
AREA_COMPONENT = "pmw_alpha_area"
ACTOR_COMPONENT = "pmw_alpha_actor"

MIST_CAMP_ID = "mist_camp"
MOSS_SHALLOWS_ID = "moss_shallows"
THUNDER_MINE_ID = "thunder_mine"
FROST_FOREST_ID = "frost_forest"
ASH_OBSERVATORY_ID = "ash_observatory"
AREA_IDS = (
    MIST_CAMP_ID,
    MOSS_SHALLOWS_ID,
    THUNDER_MINE_ID,
    FROST_FOREST_ID,
    ASH_OBSERVATORY_ID,
)

PLAYER_ID = "seventh_walker"
MIST_STALKER_ID = "mist_stalker"
SENTINEL_ID = "conductive_sentinel"
MYCELIAL_MASS_ID = "mycelial_mass"
ASH_OBSERVER_ID = "ash_observer"
ENEMY_IDS = (MIST_STALKER_ID, SENTINEL_ID, MYCELIAL_MASS_ID, ASH_OBSERVER_ID)

# Cores and glyphs are the crafting language.  The three gathered materials
# retain their competing world uses and are intentionally distinct from them.
CORE_MATERIAL_IDS = ("tide_core", "thunder_core", "spore_core", "ash_core")
GLYPH_MATERIAL_IDS = ("instant_glyph", "sustaining_glyph", "echo_glyph")
WORLD_MATERIAL_IDS = ("wet_moss", "thunder_crystal", "spore_bud", "ash_cinder")
MATERIAL_IDS = (*CORE_MATERIAL_IDS, *GLYPH_MATERIAL_IDS, *WORLD_MATERIAL_IDS)

# These are the traversable edges at time zero.  The two Observatory edges are
# declared separately because their lifecycle is controlled by mine/forest
# world state rather than being a hidden quest boolean.
STARTING_MAP_EDGES = (
    (MIST_CAMP_ID, MOSS_SHALLOWS_ID),
    (MIST_CAMP_ID, THUNDER_MINE_ID),
    (MOSS_SHALLOWS_ID, FROST_FOREST_ID),
)
LOCKED_ROUTE_SPECS = {
    "mine_lift": {"from": THUNDER_MINE_ID, "to": ASH_OBSERVATORY_ID, "unlock": "lift_powered"},
    "forest_root_bridge": {"from": FROST_FOREST_ID, "to": ASH_OBSERVATORY_ID, "unlock": "root_bridge_formed"},
}


def area_blueprint_documents() -> dict[str, dict[str, Any]]:
    """Return fresh blueprint documents for all five independent Areas."""
    return {
        MIST_CAMP_ID: _area_blueprint(
            "mist_camp_bp",
            (_field("humidity", .42, .42), _field("temperature", .46, .46), _field("charge", .05, .05)),
        ),
        MOSS_SHALLOWS_ID: _area_blueprint(
            "moss_shallows_bp",
            (
                _field("humidity", .66, .74), _field("temperature", .40, .42),
                _field("charge", .12, .10), _field("biomass", .72, .68),
                _field("moss_abundance", .85, .76),
            ),
        ),
        THUNDER_MINE_ID: _area_blueprint(
            "thunder_mine_bp",
            (
                _field("humidity", .25, .22), _field("temperature", .38, .38),
                _field("charge", .32, .46), _field("crystal_abundance", .82, .70),
            ),
        ),
        FROST_FOREST_ID: _area_blueprint(
            "frost_forest_bp",
            (
                _field("humidity", .58, .62), _field("temperature", .24, .26),
                _field("charge", .08, .06), _field("biomass", .38, .44),
                _field("spore_abundance", .74, .68),
            ),
            ecology_state="declining",
        ),
        ASH_OBSERVATORY_ID: _area_blueprint(
            "ash_observatory_bp",
            (
                _field("humidity", .20, .18), _field("temperature", .68, .62),
                _field("charge", .28, .24), _field("smoke", .42, .35),
            ),
        ),
    }


def actor_blueprint_documents() -> dict[str, dict[str, Any]]:
    """Return fresh Actor blueprints for the player and four enemy families."""
    return {
        PLAYER_ID: _actor_blueprint("seventh_walker_bp", 36, 10, (2, 2, 2, 2), ("traveler",)),
        MIST_STALKER_ID: _actor_blueprint("mist_stalker_bp", 24, 0, (2, 3, 1, 3), ("mist_hunter", "visual_lock")),
        SENTINEL_ID: _actor_blueprint("conductive_sentinel_bp", 34, 0, (3, 1, 3, 1), ("conductive", "charge_user")),
        MYCELIAL_MASS_ID: _actor_blueprint("mycelial_mass_bp", 40, 0, (2, 2, 4, 1), ("biomass_bound", "regenerative")),
        ASH_OBSERVER_ID: _actor_blueprint("ash_observer_bp", 64, 8, (4, 3, 4, 2), ("observer", "power_linked")),
    }


def make_alpha_world(*, time_budget: int = 72):
    """Build a detached time-zero PMW Gameplay world for a new Alpha run.

    The default 72 ticks is a deliberately finite, generous first-Alpha
    economy.  It is a content constant, not a second simulation clock.
    """
    area_documents = area_blueprint_documents()
    actor_documents = actor_blueprint_documents()
    areas = tuple(
        instantiate_area(parse_area_blueprint(area_documents[area_id]), area_id)
        for area_id in AREA_IDS
    )
    actors = (
        instantiate_actor(parse_actor_blueprint(actor_documents[PLAYER_ID]), PLAYER_ID, controller="human"),
        *(instantiate_actor(parse_actor_blueprint(actor_documents[actor_id]), actor_id, controller="ai") for actor_id in ENEMY_IDS),
    )
    for area in areas:
        area.components[AREA_COMPONENT] = _area_state(area.id)
    for actor in actors:
        actor.components[ACTOR_COMPONENT] = _actor_state(actor.id)
        for trait in actor.components["pmw_gameplay_actor"]["traits"]:
            actor.tags.add(trait)

    world = build_gameplay_world(
        "pmw_alpha_seventh_night",
        areas=areas,
        actors=actors,
        placements=(
            (PLAYER_ID, MIST_CAMP_ID),
            (MIST_STALKER_ID, MOSS_SHALLOWS_ID),
            (SENTINEL_ID, THUNDER_MINE_ID),
            (MYCELIAL_MASS_ID, FROST_FOREST_ID),
            (ASH_OBSERVER_ID, ASH_OBSERVATORY_ID),
        ),
        adjacencies=STARTING_MAP_EDGES,
    )
    world.entities[CLOCK_ID] = clock_entity(CLOCK_ID)
    initialized = initialize_content_world(
        world,
        make_content(basic_registry(), material_ids=MATERIAL_IDS),
    )
    initialized = initialize_time_budget(initialized, time_budget)
    inventory = initialized.entities[PLAYER_ID].components["pmw_gameplay_material_inventory"]["quantities"]
    inventory.update({"wet_moss": 1.0, "instant_glyph": 1.0, "sustaining_glyph": 1.0})
    return initialized


def _field(field_id: str, initial: float, target: float, *, rate: float = .05) -> dict[str, Any]:
    return {
        "id": field_id,
        "domain": {"min": 0.0, "max": 1.0},
        "initial": initial,
        "target": target,
        "rate": rate,
        "curve": "linear",
    }


def _area_blueprint(blueprint_id: str, fields: tuple[dict[str, Any], ...], *, ecology_state: str = "stable") -> dict[str, Any]:
    return {"protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint", "id": blueprint_id,
            "fields": list(fields), "ecology_state": ecology_state}


def _actor_blueprint(
    blueprint_id: str,
    hp: int,
    mana: int,
    attributes: tuple[int, int, int, int],
    traits: tuple[str, ...],
) -> dict[str, Any]:
    power, control, resilience, agility = attributes
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "actor_blueprint", "id": blueprint_id,
        "hp": {"max": hp, "initial": hp},
        "mana": {"max": mana, "initial": mana, "dynamics": None},
        "attributes": {"power": power, "control": control, "resilience": resilience, "agility": agility},
        "traits": list(traits),
    }


def _area_state(area_id: str) -> dict[str, Any]:
    names = {
        MIST_CAMP_ID: "雾栖营地", MOSS_SHALLOWS_ID: "雾苔浅滩", THUNDER_MINE_ID: "鸣雷矿穴",
        FROST_FOREST_ID: "霜痕森林", ASH_OBSERVATORY_ID: "灰烬观测站",
    }
    interactions = {
        MIST_CAMP_ID: ("insight_dais", "supply_fire", "survey_map"),
        MOSS_SHALLOWS_ID: ("hydrology_stele", "moss_bed", "fungal_grove", "mist_beast"),
        THUNDER_MINE_ID: ("crystal_vein", "generator", "sentinel", "mine_lift"),
        FROST_FOREST_ID: ("spore_bed", "forest_heart", "root_bridge", "mycelial_mass"),
        ASH_OBSERVATORY_ID: ("control_console", "stabilizer", "ash_observer"),
    }
    return {
        "name": names[area_id], "interactions": list(interactions[area_id]), "discovered": [],
        "visited": area_id == MIST_CAMP_ID,
        "route_state": "locked" if area_id == ASH_OBSERVATORY_ID else "open",
        "world_flags": {"lift_powered": False, "root_bridge_formed": False},
    }


def _actor_state(actor_id: str) -> dict[str, Any]:
    role = "player" if actor_id == PLAYER_ID else "enemy"
    return {
        "role": role,
        "encounter_active": False,
        "defeated": False,
        "ai_profile": None if role == "player" else actor_id,
        "knowledge": [] if role == "player" else None,
    }
