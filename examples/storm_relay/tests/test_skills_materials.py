from __future__ import annotations

import unittest

from examples.storm_relay.session import StormRelaySession


class StormRelaySkillsMaterialsTests(unittest.TestCase):
    def test_craft_consumes_real_inventory_and_registers_skill(self) -> None:
        session = StormRelaySession.new_game()
        session.perform("investigate_inscription")
        session.perform("harvest_wet_moss")
        session.perform("harvest_thunder_crystal")
        session.perform("craft_lightning_seed")
        inventory = {row["id"]: row["count"] for row in session.public_state()["inventory"]}
        self.assertEqual(inventory["wet_moss"], 0.0)
        # One calibrated crystal is part of the starting expedition kit; the
        # harvested second crystal remains for the Storm Glass Relay recipe.
        self.assertEqual(inventory["thunder_crystal"], 1.0)
        self.assertEqual(session.public_state()["registered_skills"][0]["id"], "lightning_seed")

    def test_unavailable_recipe_does_not_change_world(self) -> None:
        session = StormRelaySession.new_game()
        before = session.state.to_dict()
        with self.assertRaises(ValueError):
            session.perform("craft_lightning_seed")
        self.assertEqual(session.state.to_dict(), before)
