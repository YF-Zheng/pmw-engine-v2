from __future__ import annotations

import unittest

from examples.storm_relay.content import AREA_COMPONENT, GUARD_ID, SHALLOWS_ID, TOWER_ID, build_storm_relay_session
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import advance_world_tick


def _field(session, area_id, field_id):
    return session.state.entities[area_id].components["pmw_gameplay_dynamics"]["fields"][field_id]


class StormRelayDynamicsWeatherTests(unittest.TestCase):
    def test_all_area_fields_advance_by_linear_recovery_and_clamp(self) -> None:
        session = build_storm_relay_session()
        _field(session, SHALLOWS_ID, "humidity")["value"] = .60
        _field(session, TOWER_ID, "charge")["value"] = .90
        advance_world_tick(session)
        self.assertAlmostEqual(_field(session, SHALLOWS_ID, "humidity")["value"], .605)
        self.assertAlmostEqual(_field(session, TOWER_ID, "charge")["value"], .87)
        _field(session, SHALLOWS_ID, "humidity")["value"] = 1.0
        _field(session, SHALLOWS_ID, "humidity")["baseline"]["target"] = 2.0
        advance_world_tick(session)
        self.assertEqual(_field(session, SHALLOWS_ID, "humidity")["value"], 1.0)

    def test_weather_enter_keep_and_exit_emit_only_on_real_transitions(self) -> None:
        session = build_storm_relay_session()
        _field(session, TOWER_ID, "humidity")["value"] = .80
        _field(session, TOWER_ID, "charge")["value"] = .80
        first = advance_world_tick(session)
        self.assertEqual(session.state.entities[TOWER_ID].components[AREA_COMPONENT]["weather"], "storm")
        transitions = _changed_events(first.event_result.trace.to_dict())
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0]["payload"]["old"], "clear")
        self.assertEqual(transitions[0]["payload"]["new"], "storm")
        second = advance_world_tick(session)
        self.assertEqual(session.state.entities[TOWER_ID].components[AREA_COMPONENT]["weather"], "storm")
        self.assertEqual(_changed_events(second.event_result.trace.to_dict()), [])
        _field(session, TOWER_ID, "humidity")["value"] = .20
        _field(session, TOWER_ID, "charge")["value"] = .10
        third = advance_world_tick(session)
        self.assertEqual(session.state.entities[TOWER_ID].components[AREA_COMPONENT]["weather"], "clear")
        self.assertEqual(len(_changed_events(third.event_result.trace.to_dict())), 1)

    def test_exclusive_fog_and_storm_transition_table(self) -> None:
        session = build_storm_relay_session()
        _field(session, SHALLOWS_ID, "humidity")["value"] = .90
        _field(session, SHALLOWS_ID, "charge")["value"] = .30
        advance_world_tick(session)
        self.assertEqual(session.state.entities[SHALLOWS_ID].components[AREA_COMPONENT]["weather"], "fog")
        _field(session, SHALLOWS_ID, "charge")["value"] = .90
        advance_world_tick(session)
        self.assertEqual(session.state.entities[SHALLOWS_ID].components[AREA_COMPONENT]["weather"], "storm")

    def test_storm_pulse_is_local_and_only_hits_living_conductive_actor(self) -> None:
        session = build_storm_relay_session()
        session.state.entities[GUARD_ID].components["storm_relay_actor"]["encounter_active"] = True
        _field(session, TOWER_ID, "humidity")["value"] = .80
        _field(session, TOWER_ID, "charge")["value"] = .80
        result = advance_world_tick(session)
        guard = session.state.entities[GUARD_ID].components["pmw_gameplay_actor"]
        self.assertEqual(guard["hp"], 37)
        pulses = [event for event in result.event_result.trace.to_dict()["events"] if event["event"]["type"] == "pmw.m0.weather.pulse"]
        self.assertEqual(len(pulses), 1)
        guard["hp"] = 0
        advance_world_tick(session)
        self.assertEqual(guard["hp"], 0)


def _changed_events(trace):
    return [event["event"] for event in trace["events"] if event["event"]["type"] == "pmw.m0.weather_changed"]


if __name__ == "__main__":
    unittest.main()
