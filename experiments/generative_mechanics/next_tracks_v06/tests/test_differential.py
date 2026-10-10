from __future__ import annotations

import random
import unittest

from pmw import Engine, Entity, Relation, WorldState, parse_law

from experiments.generative_mechanics.next_tracks_v06.dynamics import (
    AttractorContribution,
    Coupling,
    CouplingLawProfile,
    DynamicsLawProfile,
    DynamicsNode,
    advance_dynamics_step,
    build_dynamics_laws,
    normalized_network_step,
)
from experiments.generative_mechanics.next_tracks_v06.compiler import compile_mechanism
from experiments.generative_mechanics.next_tracks_v06.execution import activate, activation_event, build_runtime, run_step
from experiments.generative_mechanics.next_tracks_v06.tests.helpers import mechanism, operator
from experiments.generative_mechanics.next_tracks_v06.validator import validate_mechanism
from experiments.generative_mechanics.next_tracks_v06.worlds.common import catalog, clock, dynamic_entity


CLOCK_ID = "gm:v06:clock"


def _clock():
    return Entity(CLOCK_ID, components={"gm_v06_clock": {
        "next_step": 1, "next_time": 1.0, "last_completed_step": 0,
    }})


class DynamicsDifferentialTest(unittest.TestCase):
    def test_reference_matches_pmw_for_1000_deterministic_cases(self):
        rng = random.Random(606_1000)
        for case in range(1000):
            with self.subTest(case=case):
                count = 1 + (case % 3)
                nodes = {}
                entities = {CLOCK_ID: _clock()}
                profiles = []
                for index in range(count):
                    object_id = f"n{index}"
                    attractor_count = rng.randrange(4)
                    alpha_count = rng.randrange(3)
                    drive_count = rng.randrange(3)
                    attractors = tuple(
                        AttractorContribution(f"a{slot}", rng.random(), rng.random() * 2)
                        for slot in range(attractor_count)
                    )
                    alpha_deltas = tuple((f"p{slot}", rng.uniform(-.4, .4)) for slot in range(alpha_count))
                    drives = tuple((f"d{slot}", rng.uniform(-.4, .4)) for slot in range(drive_count))
                    node = DynamicsNode(
                        rng.random(), rng.random(), rng.uniform(.1, 2), rng.random(),
                        attractors, alpha_deltas, drives, rng.uniform(0, .6),
                    )
                    nodes[object_id] = node
                    components = {
                        "value": node.value,
                        "base_attractor": node.base_attractor,
                        "base_weight": node.base_weight,
                        "base_alpha": node.base_alpha,
                        "drive_limit": node.drive_limit,
                        "attractor_slots": {
                            item.source_id: {"target": item.target, "weight": item.weight, "active": item.weight > 0, "owner": item.source_id}
                            for item in attractors
                        },
                        "alpha_slots": {
                            source: {"delta": value, "active": value != 0, "owner": source}
                            for source, value in alpha_deltas
                        },
                        "drive_slots": {
                            source: {"drive": value, "active": value != 0, "owner": source}
                            for source, value in drives
                        },
                        "scratch": {"intrinsic": rng.uniform(-1, 1), "coupling": rng.uniform(-1, 1)},
                        "diagnostics": {
                            "effective_attractor": 0.0, "effective_alpha": 0.0,
                            "effective_drive": 0.0, "intrinsic": 0.0, "coupling": 0.0,
                            "unclamped": 0.0, "clamp_loss": 0.0,
                        },
                    }
                    entities[object_id] = Entity(object_id, components={"gm_v06_dynamics": components})
                    profiles.append(DynamicsLawProfile(
                        object_id,
                        tuple(item.source_id for item in attractors),
                        tuple(source for source, _ in alpha_deltas),
                        tuple(source for source, _ in drives),
                    ))

                relations = {}
                coupling_specs = []
                coupling_profiles = []
                for left in range(count):
                    for right in range(left + 1, count):
                        if rng.random() >= .55:
                            continue
                        edge_id = f"e{left}_{right}"
                        base = rng.uniform(0, .25)
                        modifier_count = rng.randrange(3)
                        modifiers = {f"k{slot}": rng.uniform(-.1, .1) for slot in range(modifier_count)}
                        effective = max(0.0, min(base + sum(modifiers.values()), 1.0))
                        coupling_specs.append(Coupling(edge_id, f"n{left}", f"n{right}", effective))
                        coupling_profiles.append(CouplingLawProfile(
                            edge_id, "gm.v06.coupling", f"n{left}", f"n{right}", tuple(modifiers),
                        ))
                        relations[edge_id] = Relation(
                            edge_id, "gm.v06.coupling", f"n{left}", f"n{right}",
                            components={"gm_v06_coupling": {
                                "base_conductivity": base,
                                "modifier_slots": {
                                    slot: {"delta": value, "active": value != 0, "owner": slot}
                                    for slot, value in modifiers.items()
                                },
                            }},
                        )

                expected = normalized_network_step(nodes, coupling_specs)
                law_documents = build_dynamics_laws(profiles, coupling_profiles)
                runtime = Engine([parse_law(item) for item in law_documents]).attach(
                    WorldState(entities=entities, relations=relations)
                )
                result = advance_dynamics_step(runtime)
                self.assertEqual(
                    [item.event.type for item in result.dynamics_result.trace.events],
                    ["gm.v06.dynamics.tick", "gm.v06.dynamics.accumulate", "gm.v06.dynamics.commit"],
                )
                self.assertEqual(runtime.state.entities[CLOCK_ID].components["gm_v06_clock"]["next_step"], 2)
                for object_id, oracle in expected.items():
                    actual = runtime.state.entities[object_id].components["gm_v06_dynamics"]
                    self.assertAlmostEqual(actual["value"], oracle.next_value, delta=1e-12)
                    diagnostics = actual["diagnostics"]
                    pairs = {
                        "effective_attractor": oracle.effective_attractor,
                        "effective_alpha": oracle.effective_alpha,
                        "effective_drive": oracle.effective_drive,
                        "intrinsic": oracle.intrinsic,
                        "coupling": oracle.coupling,
                        "unclamped": oracle.unclamped,
                        "clamp_loss": oracle.clamp_loss,
                    }
                    for name, expected_value in pairs.items():
                        self.assertAlmostEqual(diagnostics[name], expected_value, delta=1e-12, msg=f"case={case} node={object_id} metric={name}")
                    self.assertTrue(0.0 <= actual["value"] <= 1.0)

    def test_1000_randomized_lifecycles_match_independent_reference(self):
        rng = random.Random(606_2000)
        thermal_catalog = catalog("thermal_fluid")
        for case in range(1000):
            with self.subTest(case=case):
                initial = rng.random()
                base = rng.random()
                alpha = rng.random()
                target_one, target_two = rng.random(), rng.random()
                weight_one, weight_two = rng.random() * 3, rng.random() * 3
                duration_one, duration_two = rng.randrange(1, 5), rng.randrange(1, 5)
                first = operator(
                    "attractor_modifier", "temperature_attractor", parameters={"attractor": target_one, "weight": weight_one},
                    lifecycle={"mode": "timed", "steps": duration_one}, operator_id="anchor_one",
                )
                second = operator(
                    "attractor_modifier", "temperature_attractor", parameters={"attractor": target_two, "weight": weight_two},
                    lifecycle={"mode": "timed", "steps": duration_two}, operator_id="anchor_two",
                )
                compiled = compile_mechanism(validate_mechanism(
                    mechanism([first, second], artifact_id=f"life_{case}"), thermal_catalog,
                ), thermal_catalog)
                reactor = dynamic_entity(
                    "reactor", initial, base, alpha,
                    attractor_slots=("temp_attractor_0", "temp_attractor_1"),
                )
                world = WorldState(entities={"gm:v06:clock": clock(), "reactor": reactor})
                laws = build_dynamics_laws([DynamicsLawProfile(
                    "reactor", ("temp_attractor_0", "temp_attractor_1"), (), (),
                )])
                runtime = build_runtime(world, laws, [compiled])
                activation = activate(runtime, compiled, activation_event(
                    compiled, activation_id="cast", instance_index=0, time=0,
                ))
                self.assertEqual(len(activation.scheduled_event_ids), 2)
                expected = initial
                dispatched = []
                for step in range(1, 6):
                    numerator = base
                    denominator = 1.0
                    if step < duration_one:
                        numerator += weight_one * target_one
                        denominator += weight_one
                    if step < duration_two:
                        numerator += weight_two * target_two
                        denominator += weight_two
                    attractor = numerator / denominator
                    expected = max(0.0, min(expected + alpha * (attractor - expected), 1.0))
                    result = run_step(runtime)
                    dispatched.extend(item.event_id for item in result.advance_result.dispatches)
                    self.assertAlmostEqual(
                        runtime.state.entities["reactor"].components["gm_v06_dynamics"]["value"],
                        expected, delta=1e-12,
                    )
                self.assertEqual(len(dispatched), 2)
                self.assertEqual(runtime.state.scheduled_events, [])
                slots = runtime.state.entities["reactor"].components["gm_v06_dynamics"]["attractor_slots"]
                self.assertTrue(all(not item["active"] and item["owner"] is None for item in slots.values()))


if __name__ == "__main__":
    unittest.main()
