from __future__ import annotations

import unittest

from examples.storm_relay.session import StormRelaySession


class StormRelayCombatTransactionTests(unittest.TestCase):
    def test_travel_changes_real_location_relation(self) -> None:
        session = StormRelaySession.new_game()
        session.perform("travel_tower")
        locations = [row for row in session.state.relations.values() if row.type == "located_in" and row.source == "storm_player"]
        self.assertEqual([(row.source, row.target) for row in locations], [("storm_player", "storm_tower")])

    def test_start_and_round_spend_exactly_one_tick(self) -> None:
        session = StormRelaySession.new_game()
        session.perform("travel_tower")
        session.perform("start_core")
        before = session.public_state()["time"]["remaining"]
        session.perform("attack")
        self.assertEqual(session.public_state()["time"]["remaining"], before - 1)

    def test_guard_is_source_owned_and_expires_without_touching_relay(self) -> None:
        session = StormRelaySession.new_game()
        session.perform("travel_tower")
        session.perform("start_core")
        session.perform("guard")
        layers = session.state.entities["storm_player"].components["pmw_gameplay_shields"]["slots"].values()
        self.assertFalse(any(row.get("active") and row.get("source_id") == "m0_guard:storm_player" for row in layers))

    def test_equipped_active_skill_is_a_full_combat_turn(self) -> None:
        session = StormRelaySession.new_game()
        for action in ("investigate_inscription", "harvest_wet_moss", "harvest_thunder_crystal", "craft_lightning_seed"):
            session.perform(action)
        session.perform("equip_active", target="lightning_seed", slot=0)
        session.perform("travel_tower")
        session.perform("start_core")
        before_time = session.public_state()["time"]["remaining"]
        before_hp = session.public_state()["player"]["hp"]
        self.assertIn("cast_lightning_seed", [row["action"] for row in session.legal_actions()])
        session.perform("cast_lightning_seed")
        self.assertEqual(session.public_state()["time"]["remaining"], before_time - 1)
        self.assertLess(session.public_state()["player"]["hp"], before_hp)

    def test_combat_projection_includes_both_visible_actors(self) -> None:
        session = StormRelaySession.new_game()
        session.perform("travel_tower")
        session.perform("start_core")
        self.assertEqual([row["id"] for row in session.public_state()["combat"]["actors"]], ["storm_player", "tower_guard"])
