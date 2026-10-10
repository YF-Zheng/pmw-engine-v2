from __future__ import annotations

import random
import tempfile
from pathlib import Path
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import instantiate_actor, instantiate_area, parse_actor_blueprint, parse_area_blueprint
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.benchmarks import (
    active_world_row, run_gate1_demo, run_locality,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import DynamicsSource, FieldDefinition, GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.dynamics import evaluate_field
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick, apply_source, build_runtime, clock_entity,
    load_checkpoint, remove_source, run_phase_event, save_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate1_blueprints import actor_raw, area_raw
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import build_gameplay_world


def session():
    area = instantiate_area(parse_area_blueprint(area_raw()), "marsh_west")
    world = build_gameplay_world("dynamics_world", areas=[area, clock_entity()])
    return build_runtime(world)


class ReferenceTests(unittest.TestCase):
    def test_randomized_two_curve_manual_oracle_600_cases(self):
        rng = random.Random(40401)
        for index in range(600):
            curve = "linear" if index % 2 == 0 else "distance_squared"
            low = rng.uniform(-4.0, 0.0); width = rng.uniform(0.2, 5.0); high = low + width
            rate_limit = 1.0 if curve == "linear" else 1.0 / width
            rate = rng.uniform(0.0, rate_limit)
            target = rng.uniform(low, high); value = rng.uniform(low, high)
            definition = FieldDefinition("oracle_field", low, high, value, target, rate, curve, 1, 1)
            result = evaluate_field(definition, value)
            difference = target - value
            delta = rate * difference if curve == "linear" else rate * difference * abs(difference)
            expected = min(high, max(low, value + delta))
            self.assertAlmostEqual(result.value, expected, delta=1e-12, msg=f"case={index}")
            self.assertGreaterEqual((result.value - value) * difference, -1e-12)
            self.assertLessEqual(abs(result.value - target), abs(value - target) + 1e-12)


class RuntimeDynamicsTests(unittest.TestCase):
    def test_linear_tick_uses_pmw_law_and_advances_once(self):
        game = session()
        result = advance_world_tick(game)
        state = game.state.entities["marsh_west"].components["pmw_gameplay_dynamics"]["fields"]["temperature"]
        self.assertAlmostEqual(state["value"], 0.68)
        self.assertEqual(state["diagnostics"]["effective_curve"], "linear")
        self.assertEqual(result.step, 1)
        self.assertTrue(result.event_result.triggered_law_ids)

    def test_distance_squared_pmw_tick_matches_oracle(self):
        raw = area_raw(); raw["fields"][0]["curve"] = "distance_squared"; raw["fields"][0]["rate"] = 0.5
        area = instantiate_area(parse_area_blueprint(raw), "squared_area")
        game = build_runtime(build_gameplay_world("squared", areas=[area, clock_entity()]))
        advance_world_tick(game)
        state = game.state.entities["squared_area"].components["pmw_gameplay_dynamics"]["fields"]["temperature"]
        self.assertAlmostEqual(state["value"], 0.62)
        self.assertEqual(state["diagnostics"]["effective_curve"], "distance_squared")

    def test_adjacent_areas_do_not_implicitly_diffuse(self):
        blueprint = parse_area_blueprint(area_raw())
        west = instantiate_area(blueprint, "marsh_west")
        east = instantiate_area(blueprint, "marsh_east")
        game = build_runtime(build_gameplay_world(
            "two_areas", areas=[west, east, clock_entity()],
            adjacencies=[("marsh_west", "marsh_east")],
        ))
        apply_source(game, entity_id="marsh_west", field_id="temperature", layer="persistent", source=DynamicsSource("west_only", "ecology", target=0.0, target_weight=4.0))
        advance_world_tick(game)
        left = game.state.entities["marsh_west"].components["pmw_gameplay_dynamics"]["fields"]["temperature"]
        right = game.state.entities["marsh_east"].components["pmw_gameplay_dynamics"]["fields"]["temperature"]
        self.assertNotEqual(left["value"], right["value"])
        self.assertAlmostEqual(right["value"], 0.68)

    def test_actor_mana_uses_same_dynamics_and_stays_synchronized(self):
        actor = instantiate_actor(parse_actor_blueprint(actor_raw()), "hero_actor", controller="human")
        game = build_runtime(build_gameplay_world("actor_mana", areas=[clock_entity()], actors=[actor]))
        advance_world_tick(game)
        entity = game.state.entities["hero_actor"]
        self.assertAlmostEqual(entity.components["pmw_gameplay_actor"]["mana"], 71.0)
        self.assertEqual(entity.components["pmw_gameplay_actor"]["mana"], entity.components["pmw_gameplay_dynamics"]["fields"]["mana"]["value"])

    def test_persistent_patch_is_weighted_and_removable(self):
        game = session()
        source = DynamicsSource("cold_patch", "skill_alpha", target=0.0, target_weight=3.0, rate_add=0.1)
        apply = apply_source(game, entity_id="marsh_west", field_id="temperature", layer="persistent", source=source)
        self.assertTrue(apply.changed)
        advance_world_tick(game)
        field = game.state.entities["marsh_west"].components["pmw_gameplay_dynamics"]["fields"]["temperature"]
        self.assertAlmostEqual(field["diagnostics"]["effective_target"], 0.05)
        removal = remove_source(game, entity_id="marsh_west", field_id="temperature", source_id="cold_patch", owner="skill_alpha")
        self.assertTrue(removal.changed)
        self.assertEqual(game.state.scheduled_events, [])

    def test_temporary_modifier_expires_exact_owner_slot(self):
        game = session()
        source = DynamicsSource("quick_recovery", "status_one", rate_multiplier=2.0, duration_ticks=2)
        apply_source(game, entity_id="marsh_west", field_id="temperature", layer="temporary", source=source)
        self.assertEqual(len(game.state.scheduled_events), 1)
        advance_world_tick(game); advance_world_tick(game)
        field = game.state.entities["marsh_west"].components["pmw_gameplay_dynamics"]["fields"]["temperature"]
        self.assertFalse(field["temporary_modifiers"]["slot_0"]["active"])
        self.assertEqual(game.state.scheduled_events, [])

    def test_curve_override_priority_and_conflict(self):
        game = session()
        low = DynamicsSource("curve_low", "trait_one", curve="distance_squared", curve_priority=1)
        high = DynamicsSource("curve_high", "weather_one", curve="linear", curve_priority=2, duration_ticks=3)
        apply_source(game, entity_id="marsh_west", field_id="temperature", layer="persistent", source=low)
        apply_source(game, entity_id="marsh_west", field_id="temperature", layer="temporary", source=high)
        with self.assertRaises(GameplayContractError):
            apply_source(game, entity_id="marsh_west", field_id="temperature", layer="temporary", source=DynamicsSource("curve_tie", "bad", curve="linear", curve_priority=2, duration_ticks=1))
        advance_world_tick(game)
        field = game.state.entities["marsh_west"].components["pmw_gameplay_dynamics"]["fields"]["temperature"]
        self.assertEqual(field["diagnostics"]["effective_curve"], "linear")

    def test_source_capacity_and_owner_checks_fail_closed(self):
        game = session()
        for index in range(2):
            apply_source(game, entity_id="marsh_west", field_id="temperature", layer="persistent", source=DynamicsSource(f"patch_{index}", f"owner_{index}"))
        with self.assertRaises(GameplayContractError):
            apply_source(game, entity_id="marsh_west", field_id="temperature", layer="persistent", source=DynamicsSource("patch_extra", "owner_extra"))
        with self.assertRaises(GameplayContractError):
            remove_source(game, entity_id="marsh_west", field_id="temperature", source_id="patch_0", owner="wrong_owner")

    def test_non_world_phases_do_not_advance_dynamics(self):
        game = session()
        before = game.state.to_dict()
        run_phase_event(game, "combat_round")
        run_phase_event(game, "owner_turn", actor_id="someone")
        after = game.state.to_dict()
        self.assertEqual(before["entities"], after["entities"])
        self.assertEqual(game.state.entities["pmw:v04:clock"].components["pmw_gameplay_clock"]["next_step"], 1)

    def test_save_load_replay_equivalence(self):
        game = session()
        source = DynamicsSource("persisted_patch", "skill_one", target=0.5, target_weight=2.0)
        apply_source(game, entity_id="marsh_west", field_id="temperature", layer="persistent", source=source)
        advance_world_tick(game)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            save_checkpoint(path, game)
            loaded = load_checkpoint(path)
            advance_world_tick(game); advance_world_tick(loaded)
            self.assertEqual(game.state.to_dict(), loaded.state.to_dict())

    def test_reproducible_demo_exposes_no_implicit_diffusion(self):
        first = run_gate1_demo(); second = run_gate1_demo()
        self.assertEqual(first, second)
        self.assertNotEqual(first["trajectory"][-1]["west"], first["trajectory"][-1]["east"])


class LocalityTests(unittest.TestCase):
    def test_structural_work_is_constant_through_100k_unrelated_entities(self):
        rows = run_locality((1_000, 10_000, 100_000))
        for key in ("candidate_rows", "partial_bindings", "complete_bindings", "matches", "index_builds", "exact_constraint_lookups"):
            self.assertEqual(len({row[key] for row in rows}), 1, key)
        self.assertEqual(rows[-1]["index_builds"], 0)

    def test_multiple_active_area_actor_fields_advance_once_each(self):
        row = active_world_row(4, 4, modifiers_per_field=2)
        self.assertEqual(row["active_fields"], 8)
        self.assertEqual(row["active_modifiers"], 16)
        self.assertEqual(row["triggered_laws"], 9)  # one per Field plus the clock
        self.assertEqual(row["state_full_scans"], 0)


if __name__ == "__main__":
    unittest.main()
