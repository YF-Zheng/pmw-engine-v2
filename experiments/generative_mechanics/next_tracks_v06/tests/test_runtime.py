from __future__ import annotations

from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

from experiments.generative_mechanics.next_tracks_v06.compiler import compile_mechanism
from experiments.generative_mechanics.next_tracks_v06.execution import ExecutionContractError, activate, activation_event, build_runtime, cancel_activation, load_checkpoint, run_step, save_checkpoint, validate_activation_event
from experiments.generative_mechanics.next_tracks_v06.validator import validate_mechanism
from experiments.generative_mechanics.next_tracks_v06.worlds import build_electric_world, build_thermal_world
from experiments.generative_mechanics.next_tracks_v06.tests.helpers import VALID_OPERATORS, mechanism, operator


def _compiled(raw, cat):
    return compile_mechanism(validate_mechanism(raw, cat), cat)


class RuntimeTests(unittest.TestCase):
    def thermal(self, raw):
        world, laws, cat = build_thermal_world()
        compiled = _compiled(raw, cat)
        runtime = build_runtime(world, laws, [compiled])
        event = activation_event(compiled, activation_id="cast_01", instance_index=0, time=0)
        result = activate(runtime, compiled, event)
        return runtime, laws, compiled, result

    def test_impulse_changes_current_only(self):
        runtime, _, _, result = self.thermal(mechanism())
        dynamics = runtime.state.entities["reactor"].components["gm_v06_dynamics"]
        self.assertAlmostEqual(dynamics["value"], 0.6)
        self.assertEqual(dynamics["base_attractor"], 0.8)
        self.assertTrue(result.trace.events)

    def test_impulse_recovers_on_next_tick(self):
        runtime, _, _, _ = self.thermal(mechanism())
        before = runtime.state.entities["reactor"].components["gm_v06_dynamics"]["value"]
        run_step(runtime)
        self.assertGreater(runtime.state.entities["reactor"].components["gm_v06_dynamics"]["value"], before)

    def test_attractor_changes_future_not_current(self):
        runtime, _, _, _ = self.thermal(mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="anchor"))
        self.assertEqual(runtime.state.entities["reactor"].components["gm_v06_dynamics"]["value"], 0.8)
        run_step(runtime)
        self.assertLess(runtime.state.entities["reactor"].components["gm_v06_dynamics"]["value"], 0.8)

    def test_drive_expires_without_rollback(self):
        runtime, _, _, _ = self.thermal(mechanism([VALID_OPERATORS["drive"]], artifact_id="drive"))
        run_step(runtime); run_step(runtime)
        before = runtime.state.entities["reactor"].components["gm_v06_dynamics"]["value"]
        run_step(runtime)
        slot = runtime.state.entities["reactor"].components["gm_v06_dynamics"]["drive_slots"]["temp_drive_0"]
        self.assertFalse(slot["active"])
        self.assertNotEqual(runtime.state.entities["reactor"].components["gm_v06_dynamics"]["value"], 0.8)
        self.assertNotEqual(before, 0.8)

    def test_active_instance_cannot_overwrite_its_slot(self):
        runtime, _, compiled, _ = self.thermal(mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="no_reentry"))
        slot_before = deepcopy(runtime.state.entities["reactor"].components["gm_v06_dynamics"]["attractor_slots"]["temp_attractor_0"])
        second = activation_event(compiled, activation_id="cast_02", instance_index=0, time=0)
        with self.assertRaises(ExecutionContractError):
            activate(runtime, compiled, second)
        self.assertEqual(runtime.state.entities["reactor"].components["gm_v06_dynamics"]["attractor_slots"]["temp_attractor_0"], slot_before)
        self.assertEqual(len(runtime.state.scheduled_events), 1)

    def test_cancellation_clears_slot_and_pending_handle(self):
        runtime, _, compiled, _ = self.thermal(mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="cancel_me"))
        results = cancel_activation(runtime, compiled, activation_id="cast_01", instance_index=0)
        slot = runtime.state.entities["reactor"].components["gm_v06_dynamics"]["attractor_slots"]["temp_attractor_0"]
        self.assertFalse(slot["active"])
        self.assertEqual(runtime.state.scheduled_events, [])
        self.assertTrue(results[0].cancelled_event_ids)

    def test_wrong_activation_cannot_cancel_live_slot(self):
        runtime, _, compiled, _ = self.thermal(mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="owned_cancel"))
        with self.assertRaises(ExecutionContractError):
            cancel_activation(runtime, compiled, activation_id="wrong_cast", instance_index=0)
        slot = runtime.state.entities["reactor"].components["gm_v06_dynamics"]["attractor_slots"]["temp_attractor_0"]
        self.assertTrue(slot["active"])
        self.assertEqual(len(runtime.state.scheduled_events), 1)

    def test_out_of_range_instance_rejected(self):
        _, _, cat = build_thermal_world(); compiled = _compiled(mechanism(), cat)
        with self.assertRaises(ExecutionContractError):
            activation_event(compiled, activation_id="cast", instance_index=1, time=0)

    def test_competing_expiries_are_independent(self):
        one = deepcopy(VALID_OPERATORS["attractor_modifier"]); one["id"] = "anchor_one"; one["lifecycle"]["steps"] = 2
        two = deepcopy(VALID_OPERATORS["attractor_modifier"]); two["id"] = "anchor_two"; two["parameters"] = {"attractor": 1.0, "weight": 1.0}; two["lifecycle"]["steps"] = 4
        runtime, _, _, _ = self.thermal(mechanism([one, two], artifact_id="compete"))
        run_step(runtime); run_step(runtime)
        slots = runtime.state.entities["reactor"].components["gm_v06_dynamics"]["attractor_slots"]
        self.assertFalse(slots["temp_attractor_0"]["active"])
        self.assertTrue(slots["temp_attractor_1"]["active"])

    def test_process_start_drives_world_law(self):
        raw = mechanism([VALID_OPERATORS["process_start"]], artifact_id="pump", anchor="coolant_pump")
        runtime, _, _, _ = self.thermal(raw)
        run_step(runtime)
        self.assertLess(runtime.state.entities["coolant_tank"].components["stock"]["amount"], 0.8)

    def test_process_modify_changes_consumption(self):
        baseline, _, _, _ = self.thermal(mechanism([VALID_OPERATORS["process_start"]], artifact_id="base_pump", anchor="coolant_pump"))
        start = deepcopy(VALID_OPERATORS["process_start"])
        modified, _, _, _ = self.thermal(mechanism([start, VALID_OPERATORS["process_modify"]], artifact_id="fast_pump", anchor="coolant_pump"))
        run_step(baseline); run_step(modified)
        self.assertLess(modified.state.entities["coolant_tank"].components["stock"]["amount"], baseline.state.entities["coolant_tank"].components["stock"]["amount"])

    def test_relation_parameter_changes_coupling(self):
        base_world, base_laws, _ = build_thermal_world(); baseline = build_runtime(base_world, base_laws)
        raw = mechanism([VALID_OPERATORS["relation_modifier"]], artifact_id="conductivity", anchor="thermal_link")
        modified, _, _, _ = self.thermal(raw)
        run_step(baseline); run_step(modified)
        self.assertLess(modified.state.entities["reactor"].components["gm_v06_dynamics"]["value"], baseline.state.entities["reactor"].components["gm_v06_dynamics"]["value"])

    def test_stock_transfer_is_conserved(self):
        transfer = deepcopy(VALID_OPERATORS["drive"])
        transfer["target"] = {"object": "reserve_coolant"}
        transfer["parameters"] = {"mode": "stock_transfer", "rate": 0.1, "destination": "waste_coolant"}
        runtime, _, _, _ = self.thermal(mechanism([transfer], artifact_id="transfer", anchor="reserve_coolant"))
        before = sum(runtime.state.entities[item].components["stock"]["amount"] for item in ("reserve_tank", "waste_tank"))
        run_step(runtime)
        after = sum(runtime.state.entities[item].components["stock"]["amount"] for item in ("reserve_tank", "waste_tank"))
        self.assertAlmostEqual(before, after)

    def test_relation_create_and_expiry_change_topology(self):
        world, laws, cat = build_electric_world()
        create = operator("relation_modifier", "power_link_create", "power_link_template", {"action":"create"}, {"mode":"timed","steps":2}, "create_link")
        compiled = _compiled(mechanism([create], artifact_id="grid", anchor="bus_voltage"), cat)
        runtime = build_runtime(world, laws, [compiled])
        activate(runtime, compiled, activation_event(compiled, activation_id="cast", instance_index=0, time=0))
        self.assertTrue(runtime.state.relations)
        run_step(runtime); run_step(runtime)
        self.assertFalse(runtime.state.relations)

    def test_permanent_relation_delete_changes_topology(self):
        delete = operator("relation_modifier", "link_modify", "thermal_link", {"action":"delete"}, {"mode":"permanent"}, "delete_link")
        runtime, _, _, result = self.thermal(mechanism([delete], artifact_id="cut_link", anchor="thermal_link"))
        self.assertTrue(result.changed)
        self.assertNotIn("thermal_link_ab", runtime.state.relations)

    def test_save_load_continue_equivalence(self):
        raw = mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="persist")
        runtime, laws, compiled, _ = self.thermal(raw)
        run_step(runtime)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            save_checkpoint(path, runtime)
            loaded = load_checkpoint(path, laws, [compiled])
            run_step(runtime); run_step(loaded)
            self.assertEqual(runtime.state.to_dict(), loaded.state.to_dict())

    def test_activation_wrong_time_rejected(self):
        world, laws, cat = build_thermal_world(); compiled = _compiled(mechanism(), cat); runtime = build_runtime(world, laws, [compiled])
        event = activation_event(compiled, activation_id="late", instance_index=0, time=1)
        with self.assertRaises(ExecutionContractError): activate(runtime, compiled, event)

    def test_activation_payload_tamper_rejected(self):
        world, laws, cat = build_thermal_world(); compiled = _compiled(mechanism(), cat)
        event = activation_event(compiled, activation_id="cast", instance_index=0, time=0)
        event.payload["artifact_id"] = "other"
        with self.assertRaises(ExecutionContractError): validate_activation_event(compiled, event)

    def test_activation_unknown_field_rejected(self):
        _, _, cat = build_thermal_world(); compiled = _compiled(mechanism(), cat)
        event = activation_event(compiled, activation_id="cast", instance_index=0, time=0)
        event.payload["secret"] = True
        with self.assertRaises(ExecutionContractError): validate_activation_event(compiled, event)

    def test_state_delta_names_compiled_law(self):
        _, _, compiled, result = self.thermal(mechanism())
        self.assertTrue(set(result.triggered_law_ids) <= set(compiled.source_map))


if __name__ == "__main__":
    unittest.main()
