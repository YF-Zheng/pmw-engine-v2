from __future__ import annotations

from copy import deepcopy
import math
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_actor, instantiate_area, parse_actor_blueprint,
    parse_area_blueprint, parse_field_definition,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError, ScopeCapability, SelectorContext,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.selectors import parse_selector, resolve_selector
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import build_gameplay_world
from pmw import Entity, Relation


def field(curve="linear", rate=0.2):
    return {
        "id": "temperature", "domain": {"min": 0.0, "max": 1.0},
        "initial": 0.8, "target": 0.2, "rate": rate, "curve": curve,
        "max_persistent_patches": 2, "max_temporary_modifiers": 2,
    }


def area_raw():
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint",
        "id": "marsh_area", "fields": [field()], "ecology_state": "wetland",
    }


def actor_raw():
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "actor_blueprint",
        "id": "traveler_actor", "hp": {"max": 70, "initial": 70},
        "mana": {"max": 100, "initial": 70, "dynamics": {
            "target": 80, "rate": 0.1, "curve": "linear",
            "max_persistent_patches": 2, "max_temporary_modifiers": 2,
        }},
        "attributes": {"power": 8, "control": 7, "resilience": 8, "agility": 7},
        "traits": ["traveler"],
    }


class BlueprintTests(unittest.TestCase):
    def test_field_stability_contracts(self):
        self.assertEqual(parse_field_definition(field()).curve, "linear")
        self.assertEqual(parse_field_definition(field("distance_squared", 1.0)).curve, "distance_squared")
        bad = field("distance_squared", 0.51); bad["domain"] = {"min": 0.0, "max": 2.0}
        with self.assertRaises(GameplayContractError): parse_field_definition(bad)
        for value in (True, math.inf, math.nan):
            bad = field(); bad["rate"] = value
            with self.assertRaises(GameplayContractError): parse_field_definition(bad)

    def test_strict_recursive_schema(self):
        raw = area_raw(); raw["fields"][0]["domain"]["secret"] = 1
        with self.assertRaises(GameplayContractError): parse_area_blueprint(raw)
        raw = actor_raw(); raw["attributes"]["luck"] = 2
        with self.assertRaises(GameplayContractError): parse_actor_blueprint(raw)

    def test_one_area_blueprint_creates_independent_instances(self):
        blueprint = parse_area_blueprint(area_raw())
        left = instantiate_area(blueprint, "marsh_west")
        right = instantiate_area(blueprint, "marsh_east")
        left.components["pmw_gameplay_dynamics"]["fields"]["temperature"]["value"] = 0.1
        self.assertEqual(right.components["pmw_gameplay_dynamics"]["fields"]["temperature"]["value"], 0.8)

    def test_actor_instances_are_isomorphic_except_controller(self):
        blueprint = parse_actor_blueprint(actor_raw())
        human = instantiate_actor(blueprint, "hero_actor", controller="human")
        monster = instantiate_actor(blueprint, "shade_actor", controller="ai")
        h = deepcopy(human.components); m = deepcopy(monster.components)
        h["pmw_gameplay_actor"].pop("controller")
        m["pmw_gameplay_actor"].pop("controller")
        self.assertEqual(h, m)
        actor = human.components["pmw_gameplay_actor"]
        self.assertEqual(len(actor["active_equipped"]), 6)
        self.assertEqual(len(actor["active_stowed"]), 6)
        self.assertEqual(len(actor["passive_equipped"]), 6)
        self.assertNotIn("hp", human.components["pmw_gameplay_dynamics"]["fields"])


class SelectorTests(unittest.TestCase):
    def setUp(self):
        area = parse_area_blueprint(area_raw())
        actor = parse_actor_blueprint(actor_raw())
        self.west = instantiate_area(area, "marsh_west")
        self.east = instantiate_area(area, "marsh_east")
        self.hero = instantiate_actor(actor, "hero_actor", controller="human")
        self.enemy = instantiate_actor(actor, "shade_actor", controller="ai")
        self.world = build_gameplay_world(
            "selector_world", areas=[self.west, self.east], actors=[self.hero, self.enemy],
            placements=[("hero_actor", "marsh_west"), ("shade_actor", "marsh_east")],
            adjacencies=[("marsh_west", "marsh_east")],
            links=[("mana_channel", "marsh_west", "marsh_east")],
        )
        self.context = SelectorContext("hero_actor", "shade_actor")
        self.capability = ScopeCapability(
            "travel_scope", ("self", "target_actor", "current_area", "adjacent_area", "linked_object"),
            ("mana_channel",),
        )

    def test_all_typed_selectors(self):
        self.assertEqual(resolve_selector(self.world, parse_selector({"kind": "self"}), self.context, self.capability), ("hero_actor",))
        self.assertEqual(resolve_selector(self.world, parse_selector({"kind": "target_actor"}), self.context, self.capability), ("shade_actor",))
        self.assertEqual(resolve_selector(self.world, parse_selector({"kind": "current_area"}), self.context, self.capability), ("marsh_west",))
        self.assertEqual(resolve_selector(self.world, parse_selector({"kind": "adjacent_area"}), self.context, self.capability), ("marsh_east",))
        self.assertEqual(resolve_selector(self.world, parse_selector({"kind": "linked_object", "relation_type": "mana_channel"}), self.context, self.capability), ("marsh_east",))

    def test_selector_capability_and_schema_fail_closed(self):
        with self.assertRaises(GameplayContractError):
            resolve_selector(self.world, parse_selector({"kind": "adjacent_area"}), self.context, ScopeCapability("self_only", ("self",)))
        with self.assertRaises(GameplayContractError):
            parse_selector({"kind": "current_area", "path": ["components", "secret"]})
        with self.assertRaises(GameplayContractError):
            resolve_selector(self.world, parse_selector({"kind": "linked_object", "relation_type": "secret"}), self.context, self.capability)

    def test_adjacent_area_rejects_non_area_endpoint(self):
        self.world.entities["not_an_area"] = Entity("not_an_area", "object")
        self.world.relations["bad_adjacent"] = Relation(
            "bad_adjacent", "adjacent", "marsh_west", "not_an_area",
        )
        with self.assertRaises(GameplayContractError):
            resolve_selector(
                self.world,
                parse_selector({"kind": "adjacent_area"}),
                self.context,
                self.capability,
            )


if __name__ == "__main__":
    unittest.main()
