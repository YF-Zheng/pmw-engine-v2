from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import tempfile
import unittest

from pmw import Engine, Entity, Event, Relation, WorldState, load_world, parse_law, save_world

from experiments.generative_mechanics.next_tracks_v06.dynamics import (
    AttractorContribution,
    Coupling,
    CouplingLawProfile,
    DynamicsLawProfile,
    DynamicsNode,
    TickProtocolError,
    advance_dynamics_step,
    build_dynamics_laws,
    normalized_network_step,
    normalized_step,
)


CLOCK_ID = "gm:v06:clock"


def clock(next_step=1):
    return Entity(CLOCK_ID, components={"gm_v06_clock": {
        "next_step": next_step, "next_time": float(next_step),
        "last_completed_step": next_step - 1,
    }})


def dynamic(
    object_id, *, value=.5, attractor=.5, weight=1.0, alpha=.2,
    drive_limit=.5, attractors=None, alphas=None, drives=None,
):
    return Entity(object_id, components={"gm_v06_dynamics": {
        "value": value,
        "base_attractor": attractor,
        "base_weight": weight,
        "base_alpha": alpha,
        "drive_limit": drive_limit,
        "attractor_slots": attractors or {},
        "alpha_slots": alphas or {},
        "drive_slots": drives or {},
        "scratch": {"intrinsic": 0.0, "coupling": 0.0},
        "diagnostics": {
            "effective_attractor": attractor, "effective_alpha": alpha,
            "effective_drive": 0.0, "intrinsic": 0.0, "coupling": 0.0,
            "unclamped": value, "clamp_loss": 0.0,
        },
    }})


def runtime_for(entities, profiles, couplings=(), relations=(), extra_laws=()):
    laws = [parse_law(item) for item in build_dynamics_laws(profiles, couplings)]
    laws.extend(extra_laws)
    state = WorldState(entities={CLOCK_ID: clock(), **{item.id: item for item in entities}},
                       relations={item.id: item for item in relations})
    return Engine(laws).attach(state)


class ReferenceDynamicsTest(unittest.TestCase):
    def test_fixed_point(self):
        result = normalized_step(DynamicsNode(.4, .4, 1, .8))
        self.assertEqual(result.next_value, .4)
        self.assertEqual(result.intrinsic, 0.0)

    def test_alpha_zero(self):
        self.assertEqual(normalized_step(DynamicsNode(.8, .1, 1, 0)).next_value, .8)

    def test_alpha_one_reaches_attractor(self):
        self.assertAlmostEqual(normalized_step(DynamicsNode(.8, .1, 1, 1)).next_value, .1)

    def test_weighted_competing_attractors(self):
        node = DynamicsNode(.5, .5, 1, .2, (
            AttractorContribution("cold", 0, 2),
            AttractorContribution("hot", 1, 1),
        ))
        result = normalized_step(node)
        self.assertAlmostEqual(result.effective_attractor, .375)
        self.assertAlmostEqual(result.next_value, .475)

    def test_zero_weight_source_is_inactive(self):
        base = DynamicsNode(.8, .2, 1, .5)
        modified = DynamicsNode(.8, .2, 1, .5, (AttractorContribution("off", 1, 0),))
        self.assertEqual(normalized_step(base), normalized_step(modified))

    def test_source_order_is_irrelevant(self):
        sources = (
            AttractorContribution("a", .1, .3),
            AttractorContribution("b", .9, .7),
        )
        left = DynamicsNode(.4, .5, 1, .2, sources, (("a", .1), ("b", -.03)), (("a", .04), ("b", -.01)))
        right = DynamicsNode(.4, .5, 1, .2, tuple(reversed(sources)), (("b", -.03), ("a", .1)), (("b", -.01), ("a", .04)))
        self.assertEqual(normalized_step(left), normalized_step(right))

    def test_alpha_modifier_clamps(self):
        high = DynamicsNode(.2, .8, 1, .8, alpha_deltas=(("boost", .7),))
        low = DynamicsNode(.2, .8, 1, .1, alpha_deltas=(("brake", -.7),))
        self.assertEqual(normalized_step(high).effective_alpha, 1.0)
        self.assertEqual(normalized_step(low).effective_alpha, 0.0)

    def test_drive_clamps_before_state_boundary(self):
        node = DynamicsNode(.5, .5, 1, 0, drives=(("a", .8), ("b", .7)), drive_limit=.2)
        result = normalized_step(node)
        self.assertEqual(result.effective_drive, .2)
        self.assertEqual(result.next_value, .7)

    def test_boundary_saturation_is_auditable(self):
        result = normalized_step(DynamicsNode(.9, .9, 1, 0, drives=(("source", .5),), drive_limit=1))
        self.assertEqual(result.next_value, 1.0)
        self.assertAlmostEqual(result.unclamped, 1.4)
        self.assertAlmostEqual(result.clamp_loss, -.4)

    def test_coupling_is_simultaneous_and_conservative(self):
        nodes = {"a": DynamicsNode(.8, .8, 1, 0), "b": DynamicsNode(.2, .2, 1, 0)}
        result = normalized_network_step(nodes, [Coupling("ab", "a", "b", .1)])
        self.assertAlmostEqual(result["a"].next_value, .74)
        self.assertAlmostEqual(result["b"].next_value, .26)
        self.assertAlmostEqual(result["a"].next_value + result["b"].next_value, 1.0)

    def test_self_loop_is_noop(self):
        node = DynamicsNode(.3, .3, 1, 0)
        result = normalized_network_step({"a": node}, [Coupling("self", "a", "a", .8)])
        self.assertEqual(result["a"].coupling, 0.0)

    def test_rejects_bool_nan_and_invalid_bounds(self):
        bad = [
            DynamicsNode(True, .5, 1, .2),
            DynamicsNode(.5, math.nan, 1, .2),
            DynamicsNode(.5, .5, 0, .2),
            DynamicsNode(1.1, .5, 1, .2),
        ]
        for node in bad:
            with self.subTest(node=node), self.assertRaises(ValueError):
                normalized_step(node)

    def test_unknown_coupling_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            normalized_network_step({"a": DynamicsNode(.2, .2, 1, 0)}, [Coupling("x", "a", "missing", .1)])

    def test_duplicate_and_negative_couplings_rejected(self):
        nodes = {"a": DynamicsNode(.2, .2, 1, 0), "b": DynamicsNode(.8, .8, 1, 0)}
        with self.assertRaises(ValueError):
            normalized_network_step(nodes, [Coupling("x", "a", "b", .1), Coupling("x", "a", "b", .2)])
        with self.assertRaises(ValueError):
            normalized_network_step(nodes, [Coupling("x", "a", "b", -.1)])

    def test_parallel_edges_add_deterministically(self):
        nodes = {"a": DynamicsNode(.2, .2, 1, 0), "b": DynamicsNode(.8, .8, 1, 0)}
        result = normalized_network_step(nodes, [
            Coupling("b", "a", "b", .1), Coupling("a", "a", "b", .2),
        ])
        self.assertAlmostEqual(result["a"].coupling, .18)
        self.assertAlmostEqual(result["b"].coupling, -.18)

    def test_long_horizon_remains_finite_and_bounded(self):
        node = DynamicsNode(.99, .01, 1, .87, drives=(("source", .09),), drive_limit=.1)
        for _ in range(10_000):
            result = normalized_step(node)
            self.assertTrue(math.isfinite(result.next_value))
            self.assertTrue(0.0 <= result.next_value <= 1.0)
            node = DynamicsNode(result.next_value, node.base_attractor, node.base_weight,
                                node.base_alpha, drives=node.drives, drive_limit=node.drive_limit)


class LawBuilderAndTickTest(unittest.TestCase):
    def test_builder_is_canonical_across_profile_order(self):
        a = DynamicsLawProfile("a", ("cold",), ("brake",), ("heater",))
        b = DynamicsLawProfile("b")
        self.assertEqual(build_dynamics_laws([a, b]), build_dynamics_laws([b, a]))

    def test_builder_rejects_duplicate_profile_and_bad_slot(self):
        with self.assertRaises(ValueError):
            build_dynamics_laws([DynamicsLawProfile("a"), DynamicsLawProfile("a")])
        with self.assertRaises(ValueError):
            build_dynamics_laws([DynamicsLawProfile("a", ("bad.slot",))])

    def test_builder_rejects_coupling_without_dynamic_endpoint(self):
        with self.assertRaises(ValueError):
            build_dynamics_laws([DynamicsLawProfile("a")], [CouplingLawProfile("ab", "heat", "a", "b")])

    def test_three_phase_trace_and_diagnostics(self):
        entity = dynamic("a", value=.8, attractor=.2, alpha=.5)
        runtime = runtime_for([entity], [DynamicsLawProfile("a")])
        result = advance_dynamics_step(runtime)
        state = runtime.state.entities["a"].components["gm_v06_dynamics"]
        self.assertAlmostEqual(state["value"], .5)
        self.assertEqual([item.event.type for item in result.dynamics_result.trace.events], [
            "gm.v06.dynamics.tick", "gm.v06.dynamics.accumulate", "gm.v06.dynamics.commit",
        ])
        self.assertAlmostEqual(state["diagnostics"]["effective_attractor"], .2)
        self.assertAlmostEqual(state["diagnostics"]["intrinsic"], -.3)
        self.assertEqual(result.snapshot.sim_time, 1.0)

    def test_pmw_competing_slots(self):
        sources = {
            "cold": {"target": 0.0, "weight": 2.0, "active": True, "owner": "cold"},
            "hot": {"target": 1.0, "weight": 1.0, "active": True, "owner": "hot"},
        }
        entity = dynamic("a", value=.5, attractor=.5, alpha=.2, attractors=sources)
        runtime = runtime_for([entity], [DynamicsLawProfile("a", attractor_slots=("hot", "cold"))])
        advance_dynamics_step(runtime)
        value = runtime.state.entities["a"].components["gm_v06_dynamics"]["value"]
        self.assertAlmostEqual(value, .475)

    def test_pmw_strong_drive_records_clamp_loss(self):
        entity = dynamic("a", value=.9, attractor=.9, alpha=0, drive_limit=1,
                         drives={"source": {"drive": .5, "active": True, "owner": "x"}})
        runtime = runtime_for([entity], [DynamicsLawProfile("a", drive_slots=("source",))])
        advance_dynamics_step(runtime)
        dynamics = runtime.state.entities["a"].components["gm_v06_dynamics"]
        self.assertEqual(dynamics["value"], 1.0)
        self.assertAlmostEqual(dynamics["diagnostics"]["unclamped"], 1.4)
        self.assertAlmostEqual(dynamics["diagnostics"]["clamp_loss"], -.4)

    def test_pmw_relation_coupling_is_symmetric(self):
        entities = [dynamic("a", value=.8, attractor=.8, alpha=0), dynamic("b", value=.2, attractor=.2, alpha=0)]
        relation = Relation("ab", "heat", "a", "b", components={"gm_v06_coupling": {
            "base_conductivity": .1, "modifier_slots": {},
        }})
        runtime = runtime_for(
            entities, [DynamicsLawProfile("a"), DynamicsLawProfile("b")],
            [CouplingLawProfile("ab", "heat", "a", "b")], [relation],
        )
        advance_dynamics_step(runtime)
        values = [runtime.state.entities[key].components["gm_v06_dynamics"]["value"] for key in ("a", "b")]
        self.assertAlmostEqual(values[0], .74)
        self.assertAlmostEqual(values[1], .26)
        self.assertAlmostEqual(sum(values), 1.0)

    def test_absent_relation_means_no_coupling(self):
        entities = [dynamic("a", value=.8, attractor=.8, alpha=0), dynamic("b", value=.2, attractor=.2, alpha=0)]
        runtime = runtime_for(
            entities, [DynamicsLawProfile("a"), DynamicsLawProfile("b")],
            [CouplingLawProfile("ab", "heat", "a", "b")], [],
        )
        advance_dynamics_step(runtime)
        self.assertEqual(runtime.state.entities["a"].components["gm_v06_dynamics"]["value"], .8)

    def test_conductivity_modifier_changes_future_trajectory(self):
        entities = [dynamic("a", value=.8, attractor=.8, alpha=0), dynamic("b", value=.2, attractor=.2, alpha=0)]
        relation = Relation("ab", "heat", "a", "b", components={"gm_v06_coupling": {
            "base_conductivity": .05,
            "modifier_slots": {"boost": {"delta": .15, "active": True, "owner": "artifact"}},
        }})
        runtime = runtime_for(
            entities, [DynamicsLawProfile("a"), DynamicsLawProfile("b")],
            [CouplingLawProfile("ab", "heat", "a", "b", ("boost",))], [relation],
        )
        advance_dynamics_step(runtime)
        self.assertAlmostEqual(runtime.state.entities["a"].components["gm_v06_dynamics"]["value"], .68)

    def test_relation_deleted_before_tick_stops_propagation(self):
        entities = [dynamic("a", value=.8, attractor=.8, alpha=0), dynamic("b", value=.2, attractor=.2, alpha=0)]
        relation = Relation("ab", "heat", "a", "b", components={"gm_v06_coupling": {
            "base_conductivity": .1, "modifier_slots": {},
        }})
        disconnect = parse_law({
            "id": "test.disconnect", "mode": "event", "priority": 100,
            "bindings": {"link": {"kind": "relation", "type": "heat"}},
            "when": {"all": [
                {"event.type": {"eq": "test.disconnect"}}, {"ref": "$link.id", "eq": "ab"},
            ]},
            "effects": [{"op": "delete_relation", "target": "$link"}],
        })
        runtime = runtime_for(
            entities, [DynamicsLawProfile("a"), DynamicsLawProfile("b")],
            [CouplingLawProfile("ab", "heat", "a", "b")], [relation], (disconnect,),
        )
        runtime.schedule(Event("disconnect", "test.disconnect", time=1))
        advance_dynamics_step(runtime)
        self.assertNotIn("ab", runtime.state.relations)
        self.assertEqual(runtime.state.entities["a"].components["gm_v06_dynamics"]["value"], .8)

    def test_due_expiry_runs_before_tick(self):
        entity = dynamic("a", value=.5, attractor=.5, alpha=0, drive_limit=1,
                         drives={"source": {"drive": .4, "active": True, "owner": "artifact"}})
        expire = parse_law({
            "id": "test.expire", "mode": "event", "priority": 100,
            "bindings": {"field": {"kind": "entity", "requires": ["gm_v06_dynamics"]}},
            "when": {"all": [
                {"event.type": {"eq": "test.expire"}}, {"ref": "$field.id", "eq": "a"},
            ]},
            "effects": [{"op": "set", "target": "$field.gm_v06_dynamics.drive_slots.source.drive", "value": 0.0}],
        })
        runtime = runtime_for([entity], [DynamicsLawProfile("a", drive_slots=("source",))], extra_laws=(expire,))
        runtime.schedule(Event("expire:source", "test.expire", time=1))
        result = advance_dynamics_step(runtime)
        self.assertEqual(result.advance_result.processed_event_ids, ["expire:source"])
        self.assertEqual(runtime.state.entities["a"].components["gm_v06_dynamics"]["value"], .5)

    def test_invalid_root_time_does_not_run_pipeline(self):
        runtime = runtime_for([dynamic("a", value=.8, attractor=.2)], [DynamicsLawProfile("a")])
        result = runtime.run_event(Event("bad", "gm.v06.dynamics.tick", time=9, payload={"step": 1}))
        self.assertEqual(result.triggered_law_ids, [])
        self.assertEqual(runtime.state.entities["a"].components["gm_v06_dynamics"]["value"], .8)

    def test_replayed_step_is_noop(self):
        runtime = runtime_for([dynamic("a", value=.8, attractor=.2)], [DynamicsLawProfile("a")])
        advance_dynamics_step(runtime)
        before = deepcopy(runtime.state.to_dict())
        replay = runtime.run_event(Event("replay", "gm.v06.dynamics.tick", time=1, payload={"step": 1}))
        self.assertEqual(replay.triggered_law_ids, [])
        self.assertEqual(runtime.state.to_dict(), before)

    def test_protocol_rejects_corrupt_clock(self):
        runtime = runtime_for([dynamic("a")], [DynamicsLawProfile("a")])
        runtime.state.entities[CLOCK_ID].components["gm_v06_clock"]["next_time"] = 2.0
        with self.assertRaises(TickProtocolError):
            advance_dynamics_step(runtime)

    def test_world_step_reads_committed_value(self):
        world_law = parse_law({
            "id": "world.after", "mode": "event", "priority": 1,
            "bindings": {"field": {"kind": "entity", "requires": ["gm_v06_dynamics", "observed"]}},
            "when": {"all": [
                {"event.type": {"eq": "gm.v06.world.step"}},
                {"ref": "$field.gm_v06_dynamics.value", "lt": .6},
            ]},
            "effects": [{"op": "set", "target": "$field.observed.low", "value": True}],
        })
        entity = dynamic("a", value=.8, attractor=.2, alpha=.5)
        entity.components["observed"] = {"low": False}
        runtime = runtime_for([entity], [DynamicsLawProfile("a")], extra_laws=(world_law,))
        result = advance_dynamics_step(runtime)
        self.assertTrue(runtime.state.entities["a"].components["observed"]["low"])
        self.assertIn("world.after", result.world_step_result.triggered_law_ids)

    def test_state_closure_never_observes_unbounded_physical_value(self):
        audit = parse_law({
            "id": "audit.bounds", "mode": "state", "priority": 1,
            "bindings": {"field": {"kind": "entity", "requires": ["gm_v06_dynamics", "audit"]}},
            "when": {"all": [{"ref": "$field.gm_v06_dynamics.value", "gt": 1.0}]},
            "effects": [{"op": "set", "target": "$field.audit.violation", "value": True}],
        })
        entity = dynamic("a", value=.9, attractor=.9, alpha=0, drive_limit=1,
                         drives={"source": {"drive": .8, "active": True, "owner": "x"}})
        entity.components["audit"] = {"violation": False}
        runtime = runtime_for([entity], [DynamicsLawProfile("a", drive_slots=("source",))], extra_laws=(audit,))
        advance_dynamics_step(runtime)
        self.assertEqual(runtime.state.entities["a"].components["gm_v06_dynamics"]["value"], 1.0)
        self.assertFalse(runtime.state.entities["a"].components["audit"]["violation"])

    def test_save_load_continue_matches_uninterrupted_execution(self):
        profiles = [DynamicsLawProfile("a")]
        law_documents = build_dynamics_laws(profiles)
        laws = [parse_law(item) for item in law_documents]
        initial = WorldState(entities={CLOCK_ID: clock(), "a": dynamic("a", value=.9, attractor=.1, alpha=.25)})
        uninterrupted = Engine(laws).attach(deepcopy(initial))
        resumed = Engine(laws).attach(deepcopy(initial))
        advance_dynamics_step(uninterrupted)
        advance_dynamics_step(resumed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            save_world(path, resumed.state)
            resumed = Engine(laws).attach(load_world(path))
        left = advance_dynamics_step(uninterrupted)
        right = advance_dynamics_step(resumed)
        self.assertEqual(uninterrupted.state.to_dict(), resumed.state.to_dict())
        self.assertEqual(left.dynamics_result.trace.semantic_projection(), right.dynamics_result.trace.semantic_projection())


if __name__ == "__main__":
    unittest.main()
