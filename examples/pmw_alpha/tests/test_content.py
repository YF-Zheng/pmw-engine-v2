from __future__ import annotations

import unittest

from examples.pmw_alpha.content import (
    ACTOR_COMPONENT,
    AREA_COMPONENT,
    AREA_IDS,
    ASH_OBSERVER_ID,
    ASH_OBSERVATORY_ID,
    ENEMY_IDS,
    FROST_FOREST_ID,
    MATERIAL_IDS,
    MIST_CAMP_ID,
    MIST_STALKER_ID,
    MOSS_SHALLOWS_ID,
    MYCELIAL_MASS_ID,
    PLAYER_ID,
    SENTINEL_ID,
    STARTING_MAP_EDGES,
    THUNDER_MINE_ID,
    make_alpha_world,
)


class AlphaContentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = make_alpha_world()

    def test_world_has_five_independent_areas(self) -> None:
        self.assertEqual(set(AREA_IDS), {entity.id for entity in self.world.entities.values()
                                         if AREA_COMPONENT in entity.components})
        shallow_fields = self.world.entities[MOSS_SHALLOWS_ID].components["pmw_gameplay_dynamics"]["fields"]
        mine_fields = self.world.entities[THUNDER_MINE_ID].components["pmw_gameplay_dynamics"]["fields"]
        self.assertIsNot(shallow_fields, mine_fields)
        self.assertEqual(shallow_fields["humidity"]["value"], .66)
        self.assertEqual(mine_fields["charge"]["baseline"]["target"], .46)
        self.assertEqual(self.world.entities[FROST_FOREST_ID].components["pmw_gameplay_area"]["ecology_state"], "declining")

    def test_starting_map_contains_only_initially_traversable_edges(self) -> None:
        edges = {tuple(sorted((relation.source, relation.target))) for relation in self.world.relations.values()
                 if relation.type == "adjacent"}
        self.assertEqual(edges, {tuple(sorted(edge)) for edge in STARTING_MAP_EDGES})
        self.assertFalse(any(ASH_OBSERVATORY_ID in edge for edge in edges))
        self.assertIn(MIST_CAMP_ID, {node for edge in edges for node in edge})

    def test_player_and_enemy_identities_have_real_placements(self) -> None:
        expected = {
            PLAYER_ID: MIST_CAMP_ID,
            MIST_STALKER_ID: MOSS_SHALLOWS_ID,
            SENTINEL_ID: THUNDER_MINE_ID,
            MYCELIAL_MASS_ID: FROST_FOREST_ID,
            ASH_OBSERVER_ID: ASH_OBSERVATORY_ID,
        }
        placements = {relation.source: relation.target for relation in self.world.relations.values()
                      if relation.type == "located_in"}
        self.assertEqual(placements, expected)
        self.assertEqual(set(ENEMY_IDS), {actor_id for actor_id in expected if actor_id != PLAYER_ID})
        self.assertEqual(self.world.entities[PLAYER_ID].components[ACTOR_COMPONENT]["role"], "player")
        self.assertIn("conductive", self.world.entities[SENTINEL_ID].tags)

    def test_material_catalog_and_player_starting_inventory_are_initialized(self) -> None:
        inventory = self.world.entities[PLAYER_ID].components["pmw_gameplay_material_inventory"]["quantities"]
        self.assertEqual(set(inventory), set(MATERIAL_IDS))
        self.assertEqual(inventory["wet_moss"], 1.0)
        self.assertEqual(inventory["instant_glyph"], 1.0)


if __name__ == "__main__":
    unittest.main()
