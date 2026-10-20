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
