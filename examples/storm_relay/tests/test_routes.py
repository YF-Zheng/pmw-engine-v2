from __future__ import annotations

import unittest

from examples.storm_relay.routes import (direct_assault_route, fog_build_route,
                                         run_commands, storm_build_route)
from examples.storm_relay.session import StormRelaySession


class StormRelayRouteTests(unittest.TestCase):
    def test_direct_assault_uses_exact_ten_tick_route(self) -> None:
        result = direct_assault_route()
        self.assertEqual(result["state"]["outcome"], "victory")
        self.assertEqual(result["state"]["combat"]["guard_hp"], 0.0)
        self.assertEqual(result["state"]["time"]["remaining"], 13)
        self.assertEqual(result["state"]["player"]["hp"], 2.0)
        self.assertEqual(len(result["transcript"]), 10)

    def test_storm_build_uses_exact_nineteen_tick_route(self) -> None:
        result = storm_build_route()
        self.assertEqual(result["state"]["outcome"], "victory")
        self.assertEqual(result["state"]["time"]["remaining"], 4)
        self.assertEqual(len(result["transcript"]), 17)

    def test_fog_build_can_close_core_on_last_tick(self) -> None:
        result = fog_build_route()
        self.assertEqual(result["state"]["outcome"], "victory")
        self.assertEqual(result["state"]["time"]["remaining"], 0)
        self.assertEqual(len(result["transcript"]), 21)

    def test_rejected_command_is_atomic(self) -> None:
        session = StormRelaySession.new_game()
        before = session.state.to_dict()
        with self.assertRaises(ValueError):
            session.perform("attack")
        self.assertEqual(session.state.to_dict(), before)

    def test_runner_is_only_public_commands(self) -> None:
        result = run_commands([{"action": "investigate_inscription"}])
        self.assertEqual(result["state"]["recipes"], ["fog_echo", "lightning_seed"])
