from __future__ import annotations

import unittest

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

