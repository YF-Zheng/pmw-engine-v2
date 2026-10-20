from __future__ import annotations

import unittest

from examples.storm_relay.content import (
    ACTOR_COMPONENT, AREA_COMPONENT, GUARD_ID, PLAYER_ID, SHALLOWS_ID, TOWER_ID,
    build_storm_relay_session, make_storm_relay_world,
)


class StormRelayContentTests(unittest.TestCase):
    def test_fresh_world_has_authoritative_two_area_content(self) -> None:
        world = make_storm_relay_world()
        self.assertEqual(world.entities[PLAYER_ID].components["pmw_gameplay_actor"]["hp"], 32)
        self.assertEqual(world.entities[PLAYER_ID].components["pmw_gameplay_actor"]["mana"], 8)
        self.assertEqual(world.entities[GUARD_ID].components["pmw_gameplay_actor"]["hp"], 42)
        self.assertIn("conductive", world.entities[GUARD_ID].tags)
        self.assertEqual(world.entities[SHALLOWS_ID].components[AREA_COMPONENT]["stock"],
                         {"wet_moss": 2, "thunder_crystal": 2})
        self.assertEqual(world.entities[TOWER_ID].components[AREA_COMPONENT]["stock"], {"storm_glass": 1})
        self.assertFalse(world.entities[GUARD_ID].components[ACTOR_COMPONENT]["encounter_active"])

    def test_area_instances_are_independent(self) -> None:
        world = make_storm_relay_world()
        shallow = world.entities[SHALLOWS_ID].components["pmw_gameplay_dynamics"]["fields"]
        tower = world.entities[TOWER_ID].components["pmw_gameplay_dynamics"]["fields"]
        self.assertIsNot(shallow, tower)
        self.assertEqual(shallow["humidity"]["value"], .65)
        self.assertEqual(tower["humidity"]["value"], .40)
        shallow["humidity"]["value"] = .91
        self.assertEqual(tower["humidity"]["value"], .40)

    def test_stock_is_not_dynamic_abundance(self) -> None:
        world = make_storm_relay_world()
        area = world.entities[SHALLOWS_ID]
        state = area.components[AREA_COMPONENT]
        fields = area.components["pmw_gameplay_dynamics"]["fields"]
        self.assertEqual(state["stock"]["wet_moss"], 2)
        self.assertEqual(fields["wet_moss_abundance"]["value"], .80)
        self.assertNotEqual(type(state["stock"]["wet_moss"]), type(fields["wet_moss_abundance"]["value"]))

    def test_factory_returns_live_pmw_gameplay_session(self) -> None:
        session = build_storm_relay_session()
        self.assertEqual(session.state.world_id, "storm_relay_m0")
        self.assertEqual(session.state.entities["pmw:v04:clock"].components["pmw_gameplay_time_budget"]["remaining_ticks"], 23)


if __name__ == "__main__":
    unittest.main()
