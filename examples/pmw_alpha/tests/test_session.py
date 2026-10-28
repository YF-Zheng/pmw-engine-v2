from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from examples.pmw_alpha.session import AlphaSession, AlphaSessionError


class AlphaSessionTests(unittest.TestCase):
    def test_new_game_projects_five_area_player_safe_map(self) -> None:
        state = AlphaSession.new_game().public_state()
        self.assertEqual(state["area"]["id"], "mist_camp")
        self.assertEqual(len(state["map"]["areas"]), 5)
        self.assertNotIn("world_state", state)

    def test_inspection_and_travel_advance_real_time(self) -> None:
        session = AlphaSession.new_game()
        before = session.public_state()["remaining_time"]
        inspected = session.perform("inspect", target="survey_map")
        self.assertEqual(inspected["remaining_time"], before - 1)
        moved = session.perform("travel", target="moss_shallows")
        self.assertEqual(moved["remaining_time"], before - 3)
        self.assertEqual(moved["area"]["id"], "moss_shallows")

    def test_harvest_changes_real_material_inventory_and_stock(self) -> None:
        session = AlphaSession.new_game()
        session.perform("travel", target="moss_shallows")
        state = session.perform("harvest", target="moss_bed")
        self.assertEqual(state["player"]["inventory"]["wet_moss"], 2.0)
        self.assertIn("潮湿苔藓", state["feedback"][0])

    def test_locked_observatory_is_not_a_travel_control(self) -> None:
        session = AlphaSession.new_game()
        session.perform("travel", target="thunder_mine")
        self.assertNotIn("ash_observatory", [row.get("target") for row in session.controls() if row["action"] == "travel"])
        with self.assertRaises(AlphaSessionError):
            session.perform("travel", target="ash_observatory")

    def test_crafting_equipping_and_casting_use_the_gameplay_registry(self) -> None:
        session = AlphaSession.new_game()
        session._player()["knowledge"].append("insight_dais")
        session._inventory()["thunder_crystal"] = 1.0
        session._craft("thunder_instant")
        session._equip("equip_active", "thunder_instant", 0)
        session._travel("thunder_mine")
        before = session.state.entities["thunder_mine"].components["pmw_gameplay_dynamics"]["fields"]["charge"]["value"]
        session._cast("thunder_instant")
        after = session.state.entities["thunder_mine"].components["pmw_gameplay_dynamics"]["fields"]["charge"]["value"]
        self.assertGreater(after, before)
        self.assertEqual(session._inventory()["thunder_crystal"], 0.0)
        self.assertTrue(any(item["id"] == "thunder_instant" for item in session.state.entities["seventh_walker"].components["pmw_gameplay_actor"]["active_equipped"] if item))

    def test_recipe_projection_explains_costs_and_lock_state(self) -> None:
        session = AlphaSession.new_game()
        locked = next(item for item in session.public_state()["recipes"] if item["id"] == "thunder_instant")
        self.assertTrue(locked["locked"])
        session._player()["knowledge"].append("insight_dais")
        recipe = next(item for item in session.public_state()["recipes"] if item["id"] == "thunder_instant")
        self.assertFalse(recipe["locked"])
        self.assertEqual({item["name"] for item in recipe["materials"]}, {"雷晶", "瞬发纹"})

    def test_save_load_restores_world_and_registered_skill(self) -> None:
        session = AlphaSession.new_game()
        session._player()["knowledge"].append("insight_dais")
        session._inventory()["thunder_crystal"] = 1.0
        session._craft("thunder_instant")
        with TemporaryDirectory() as directory:
            session.save(directory)
            restored = AlphaSession.load(directory)
        self.assertEqual(restored.state.to_dict(), session.state.to_dict())
        self.assertEqual(restored.public_state()["skills"][0]["id"], "thunder_instant")
