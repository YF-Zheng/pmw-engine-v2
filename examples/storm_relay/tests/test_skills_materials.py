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

    def test_recipe_view_explains_cost_effect_and_missing_materials(self) -> None:
        session = StormRelaySession.new_game()
        session.perform("investigate_inscription")
        recipes = {row["id"]: row for row in session.public_state()["recipes"]}
        seed = recipes["lightning_seed"]
        self.assertEqual(seed["mana"], 3)
        self.assertEqual(seed["craft_ticks"], 2)
        self.assertIn("蓄电 +0.30", seed["effect"])
        self.assertFalse(seed["craftable"])
        self.assertIn("wet_moss 1", seed["missing"])
        self.assertNotIn("craft_lightning_seed", [row["action"] for row in session.legal_actions()])

    def test_action_returns_player_facing_causal_feedback(self) -> None:
        session = StormRelaySession.new_game()
        state = session.perform("investigate_inscription")
        self.assertTrue(state["feedback"])
        self.assertIn("引雷播种", state["feedback"][0])
        self.assertEqual(state["recent_events"][-1]["message"], state["feedback"][-1])

    def test_harvest_feedback_uses_player_facing_material_name(self) -> None:
        session = StormRelaySession.new_game()
        state = session.perform("harvest_wet_moss")
        self.assertIn("潮湿苔藓", state["feedback"][0])
        self.assertNotIn("wet_moss", state["feedback"][0])
