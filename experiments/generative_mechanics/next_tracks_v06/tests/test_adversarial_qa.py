"""Independent adversarial gates for TODO1.

The numerical oracle in this file intentionally does not import the v0.6
reference implementation. Production helpers are used only to construct and
execute the system under test.
"""

from __future__ import annotations

from copy import deepcopy
import random
import unittest

from pmw import Engine, Entity, Relation, WorldState, parse_law

from experiments.generative_mechanics.next_tracks_v06.benchmarks.locality import measure
from experiments.generative_mechanics.next_tracks_v06.compiler import compile_mechanisms
from experiments.generative_mechanics.next_tracks_v06.dynamics import (
    CouplingLawProfile,
    DynamicsLawProfile,
    advance_dynamics_step,
    build_dynamics_laws,
)
from experiments.generative_mechanics.next_tracks_v06.execution import (
    ExecutionContractError,
    activate,
    activation_event,
    build_runtime,
    cancel_activation,
    run_step,
)
from experiments.generative_mechanics.next_tracks_v06.tests.helpers import (
    VALID_OPERATORS,
    catalog,
    mechanism,
    operator,
    raw_catalog,
)


CLOCK_ID = "gm:v06:clock"


def _clock():
    return Entity(CLOCK_ID, components={"gm_v06_clock": {
        "next_step": 1, "next_time": 1.0, "last_completed_step": 0,
    }})


def _node(identifier, rng):
    attractors = {
        f"a{index}": {"owner": f"a{index}", "active": True,
                       "target": rng.random(), "weight": rng.uniform(0, 2)}
        for index in range(2)
    }
    alphas = {"p0": {"owner": "p0", "active": True, "delta": rng.uniform(-.4, .4)}}
    drives = {"d0": {"owner": "d0", "active": True, "drive": rng.uniform(-.4, .4)}}
    dynamics = {
        "value": rng.random(), "base_attractor": rng.random(),
        "base_weight": rng.uniform(.1, 2), "base_alpha": rng.random(),
        "drive_limit": rng.uniform(0, .6),
        "attractor_slots": attractors, "alpha_slots": alphas,
        "drive_slots": drives,
        "scratch": {"intrinsic": rng.uniform(-5, 5), "coupling": rng.uniform(-5, 5)},
        "diagnostics": {
            "effective_attractor": 0.0, "effective_alpha": 0.0,
            "effective_drive": 0.0, "intrinsic": 0.0, "coupling": 0.0,
            "unclamped": 0.0, "clamp_loss": 0.0,
        },
    }
    return Entity(identifier, components={"gm_v06_dynamics": dynamics})


def _manual_step(left, right, base_k, k_delta):
    def parts(entity):
        item = entity.components["gm_v06_dynamics"]
        numerator = item["base_weight"] * item["base_attractor"]
        denominator = item["base_weight"]
        for slot_id in sorted(item["attractor_slots"]):
            slot = item["attractor_slots"][slot_id]
            numerator += slot["weight"] * slot["target"]
            denominator += slot["weight"]
        attractor = numerator / denominator
        alpha = max(0.0, min(item["base_alpha"] + item["alpha_slots"]["p0"]["delta"], 1.0))
        limit = item["drive_limit"]
        drive = max(-limit, min(item["drive_slots"]["d0"]["drive"], limit))
        intrinsic = alpha * (attractor - item["value"]) + drive
        return item["value"], attractor, alpha, drive, intrinsic

    l = parts(left); r = parts(right)
    conductivity = max(0.0, min(base_k + k_delta, 1.0))
    transfer = conductivity * (r[0] - l[0])
    result = []
    for values, coupling in ((l, transfer), (r, -transfer)):
        raw = values[0] + values[4] + coupling
        bounded = max(0.0, min(raw, 1.0))
        result.append({
            "value": bounded, "effective_attractor": values[1],
            "effective_alpha": values[2], "effective_drive": values[3],
            "intrinsic": values[4], "coupling": coupling,
            "unclamped": raw, "clamp_loss": bounded - raw,
        })
    return result


class IndependentDynamicsDifferential(unittest.TestCase):
    def test_second_seed_1000_case_manual_oracle(self):
        profiles = [
            DynamicsLawProfile("left", ("a0", "a1"), ("p0",), ("d0",)),
            DynamicsLawProfile("right", ("a0", "a1"), ("p0",), ("d0",)),
        ]
        coupling = CouplingLawProfile("edge", "qa.coupling", "left", "right", ("k0",))
        laws = [parse_law(item) for item in build_dynamics_laws(profiles, [coupling])]
        engine = Engine(laws)
        rng = random.Random(0xD06A)
        for case in range(1000):
            with self.subTest(case=case):
                left, right = _node("left", rng), _node("right", rng)
                base_k, k_delta = rng.uniform(0, .4), rng.uniform(-.2, .2)
                relation = Relation("edge", "qa.coupling", "left", "right", components={
                    "gm_v06_coupling": {
                        "base_conductivity": base_k,
                        "modifier_slots": {"k0": {"owner": "k0", "active": True, "delta": k_delta}},
                    },
                })
                expected = _manual_step(left, right, base_k, k_delta)
                runtime = engine.attach(WorldState(
                    entities={CLOCK_ID: _clock(), "left": left, "right": right},
                    relations={"edge": relation},
                ))
                result = advance_dynamics_step(runtime)
                self.assertEqual(len(result.dynamics_result.trace.events), 3)
                for index, identifier in enumerate(("left", "right")):
                    actual = runtime.state.entities[identifier].components["gm_v06_dynamics"]
                    self.assertAlmostEqual(actual["value"], expected[index]["value"], delta=1e-12)
                    for key, value in expected[index].items():
                        if key != "value":
                            self.assertAlmostEqual(actual["diagnostics"][key], value, delta=1e-12)


class LifecycleAdversarialTest(unittest.TestCase):
    def _timed_runtime(self):
        from experiments.generative_mechanics.next_tracks_v06.compiler import compile_mechanism
        from experiments.generative_mechanics.next_tracks_v06.validator import validate_mechanism
        from experiments.generative_mechanics.next_tracks_v06.worlds import build_thermal_world

        world, laws, cat = build_thermal_world()
        raw = mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="qa_owner")
        compiled = compile_mechanism(validate_mechanism(raw, cat), cat)
        runtime = build_runtime(world, laws, [compiled])
        activate(runtime, compiled, activation_event(
            compiled, activation_id="right_owner", instance_index=0, time=0,
        ))
        return runtime, compiled

    def test_wrong_activation_cannot_cancel_or_orphan_real_handle(self):
        runtime, compiled = self._timed_runtime()
        before_slot = deepcopy(runtime.state.entities["reactor"].components[
            "gm_v06_dynamics"]["attractor_slots"]["temp_attractor_0"])
        before_events = [event.to_dict() for event in runtime.state.scheduled_events]
        with self.assertRaises(ExecutionContractError):
            cancel_activation(runtime, compiled, activation_id="wrong_owner", instance_index=0)
        self.assertEqual(
            runtime.state.entities["reactor"].components["gm_v06_dynamics"][
                "attractor_slots"]["temp_attractor_0"], before_slot,
        )
        self.assertEqual([event.to_dict() for event in runtime.state.scheduled_events], before_events)

    def test_out_of_range_instance_is_rejected_before_execution(self):
        runtime, compiled = self._timed_runtime()
        with self.assertRaises(ExecutionContractError):
            activation_event(compiled, activation_id="outside", instance_index=999, time=0)
        self.assertEqual(len(runtime.state.scheduled_events), 1)

    def test_two_concurrent_stock_sinks_do_not_underflow(self):
        from experiments.generative_mechanics.next_tracks_v06.worlds import build_thermal_world
        from experiments.generative_mechanics.next_tracks_v06.validator import MechanismValidationError

        world, laws, cat = build_thermal_world()
        sink = operator(
            "drive", "temperature_drive", "reserve_coolant",
            {"mode": "stock_sink", "rate": .1}, {"mode": "timed", "steps": 3},
            "sink",
        )
        documents = [
            mechanism([sink], artifact_id="sink_a", anchor="reserve_coolant"),
            mechanism([sink], artifact_id="sink_b", anchor="reserve_coolant"),
        ]
        with self.assertRaises(MechanismValidationError):
            compile_mechanisms(documents, cat)

        compiled = compile_mechanisms(documents[:1], cat)
        runtime = build_runtime(world, laws, compiled)
        runtime.state.entities["reserve_tank"].components["stock"]["amount"] = .1
        activate(runtime, compiled[0], activation_event(
            compiled[0], activation_id="cast_0", instance_index=0, time=0,
        ))
        run_step(runtime)
        amount = runtime.state.entities["reserve_tank"].components["stock"]["amount"]
        self.assertGreaterEqual(amount, 0.0)
        self.assertAlmostEqual(amount, 0.0)

    def test_stock_flow_cannot_open_two_runtime_instances(self):
        from experiments.generative_mechanics.next_tracks_v06.validator import MechanismValidationError

        cat = catalog()
        sink = operator(
            "drive", "temperature_drive", "reserve_coolant",
            {"mode": "stock_sink", "rate": .1}, {"mode": "timed", "steps": 3},
            "sink",
        )
        with self.assertRaises(MechanismValidationError):
            compile_mechanisms([
                mechanism([sink], artifact_id="two_instances", anchor="reserve_coolant", max_instances=2),
            ], cat)

    def test_created_relation_ids_are_artifact_namespaced(self):
        from experiments.generative_mechanics.next_tracks_v06.worlds import build_electric_world

        _, _, cat = build_electric_world()
        create = operator(
            "relation_modifier", "power_link_create", "power_link_template",
            {"action": "create"}, {"mode": "timed", "steps": 2}, "create_link",
        )
        compiled = compile_mechanisms([
            mechanism([create], artifact_id="link_alpha", anchor="bus_voltage"),
            mechanism([create], artifact_id="link_beta", anchor="bus_voltage"),
        ], cat)
        relation_ids = []
        for item in compiled:
            effect = next(
                effect for law in item.law_bundle for effect in law["effects"]
                if effect["op"] == "create_relation"
            )
            relation_ids.append(effect["value"]["id"])
            self.assertIn(item.artifact_id, effect["value"]["id"])
        self.assertEqual(len(set(relation_ids)), 2)

    def _staggered_runtime(self):
        from experiments.generative_mechanics.next_tracks_v06.compiler import compile_mechanism
        from experiments.generative_mechanics.next_tracks_v06.validator import validate_mechanism
        from experiments.generative_mechanics.next_tracks_v06.worlds import build_thermal_world

        one = deepcopy(VALID_OPERATORS["attractor_modifier"])
        one["id"] = "short_anchor"
        one["lifecycle"]["steps"] = 2
        two = deepcopy(VALID_OPERATORS["attractor_modifier"])
        two["id"] = "long_anchor"
        two["parameters"] = {"attractor": 1.0, "weight": 1.0}
        two["lifecycle"]["steps"] = 4
        world, laws, cat = build_thermal_world()
        raw = mechanism([one, two], artifact_id="staggered")
        compiled = compile_mechanism(validate_mechanism(raw, cat), cat)
        runtime = build_runtime(world, laws, [compiled])
        activate(runtime, compiled, activation_event(
            compiled, activation_id="original", instance_index=0, time=0,
        ))
        run_step(runtime)
        run_step(runtime)
        return runtime, compiled

    def test_cancel_after_partial_natural_expiry_clears_remaining_operator(self):
        runtime, compiled = self._staggered_runtime()
        self.assertEqual(len(runtime.state.scheduled_events), 1)
        cancel_activation(runtime, compiled, activation_id="original", instance_index=0)
        slots = runtime.state.entities["reactor"].components["gm_v06_dynamics"]["attractor_slots"]
        self.assertTrue(all(not item["active"] for item in slots.values()))
        self.assertEqual(runtime.state.scheduled_events, [])

    def test_partial_reentry_cannot_mix_activation_ids(self):
        runtime, compiled = self._staggered_runtime()
        before = [item.to_dict() for item in runtime.state.scheduled_events]
        event = activation_event(
            compiled, activation_id="replacement", instance_index=0,
            time=runtime.state.sim_time,
        )
        try:
            result = activate(runtime, compiled, event)
        except ExecutionContractError:
            result = None
        if result is not None:
            self.assertFalse(result.changed)
        self.assertEqual([item.to_dict() for item in runtime.state.scheduled_events], before)


class LocalityAdversarialTest(unittest.TestCase):
    def test_100k_unrelated_objects_do_not_increase_structural_work(self):
        small = measure(1_000)
        large = measure(100_000)
        for key in ("candidate_rows", "partial_bindings", "complete_bindings"):
            self.assertEqual(small[key], large[key], key)
        self.assertEqual(large["index_builds"], 0)
        self.assertEqual(large["lifecycle_global_scans"], 0)


class ValidatorAuthorizationAdversarialTest(unittest.TestCase):
    def test_negative_field_drive_is_a_legal_bounded_sink(self):
        from experiments.generative_mechanics.next_tracks_v06.validator import validate_mechanism

        cooling = deepcopy(VALID_OPERATORS["drive"])
        cooling["parameters"]["rate"] = -.05
        ir = validate_mechanism(mechanism([cooling], artifact_id="cooling_drive"), catalog())
        self.assertEqual(ir.operators[0].parameters["rate"], -.05)

    def test_world_process_requires_explicit_modify_privilege(self):
        from experiments.generative_mechanics.next_tracks_v06.validator import (
            MechanismValidationError,
            validate_catalog,
            validate_mechanism,
        )

        raw = raw_catalog()
        capability = next(item for item in raw["capabilities"] if item["id"] == "pump_start")
        capability["privileges"].remove("modify_world_owned_process")
        cat = validate_catalog(raw)
        with self.assertRaises(MechanismValidationError):
            validate_mechanism(
                mechanism([VALID_OPERATORS["process_start"]], artifact_id="unauthorized_process", anchor="coolant_pump"),
                cat,
            )

    def test_relation_action_must_be_granted_by_capability(self):
        from experiments.generative_mechanics.next_tracks_v06.validator import (
            MechanismValidationError,
            validate_catalog,
            validate_mechanism,
        )

        raw = raw_catalog()
        capability = next(item for item in raw["capabilities"] if item["id"] == "link_modify")
        capability["actions"] = ["create", "delete"]
        cat = validate_catalog(raw)
        with self.assertRaises(MechanismValidationError):
            validate_mechanism(
                mechanism([VALID_OPERATORS["relation_modifier"]], artifact_id="unauthorized_action", anchor="thermal_link"),
                cat,
            )

    def test_duplicate_impulse_writer_is_rejected_before_pmw_conflict(self):
        from experiments.generative_mechanics.next_tracks_v06.validator import MechanismValidationError, validate_mechanism

        first = deepcopy(VALID_OPERATORS["impulse"])
        second = deepcopy(first)
        first["id"], second["id"] = "impulse_one", "impulse_two"
        second["parameters"]["delta"] = -.3
        with self.assertRaises(MechanismValidationError):
            validate_mechanism(mechanism([first, second], artifact_id="double_impulse"), catalog())

    def test_duplicate_process_lifecycle_writer_is_rejected(self):
        from experiments.generative_mechanics.next_tracks_v06.validator import MechanismValidationError, validate_mechanism

        first = deepcopy(VALID_OPERATORS["process_start"])
        second = deepcopy(first)
        first["id"], second["id"] = "start_one", "start_two"
        first["lifecycle"]["steps"], second["lifecycle"]["steps"] = 2, 4
        with self.assertRaises(MechanismValidationError):
            validate_mechanism(
                mechanism([first, second], artifact_id="double_process", anchor="coolant_pump"),
                catalog(),
            )


if __name__ == "__main__":
    unittest.main()
