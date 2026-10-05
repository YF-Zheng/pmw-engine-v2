from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from pmw import Engine, Event, load_world

from experiments.generative_mechanics.scenario import (
    Advance,
    CATEGORIES,
    Cast,
    ScenarioError,
    Step,
    load_scenario,
    normalize_split,
    public_calibration_paths,
    split_directory,
    validate_scenario,
)
from experiments.generative_mechanics.runner import run_scenario
from experiments.generative_mechanics.substrate import CHANNELS, public_fields_are_bounded, system_laws


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"


def scenario_paths() -> list[Path]:
    return sorted(SCENARIOS.glob("*/*.json"))


def valid_raw() -> dict:
    return json.loads((SCENARIOS / "calibration" / "short_combat.json").read_text(encoding="utf-8"))


class ScenarioSuiteTests(unittest.TestCase):
    def test_exactly_twelve_scenarios_load(self):
        scenarios = [load_scenario(path) for path in scenario_paths()]
        self.assertEqual(len(scenarios), 12)
        self.assertEqual(len({scenario.id for scenario in scenarios}), 12)

    def test_each_split_covers_all_six_categories_once(self):
        scenarios = [load_scenario(path) for path in scenario_paths()]
        for split in ("calibration", "evaluation"):
            categories = [item.category for item in scenarios if item.split == split]
            self.assertEqual(len(categories), 6)
            self.assertEqual(set(categories), set(CATEGORIES))

    def test_all_four_environments_are_covered(self):
        scenarios = [load_scenario(path) for path in scenario_paths()]
        self.assertEqual(
            {item.environment for item in scenarios},
            {"mine", "wetland", "industrial_yard", "fragile_bridge"},
        )

    def test_multi_target_scenarios_execute_three_distinct_zones(self):
        for scenario in (load_scenario(path) for path in scenario_paths() if path.name == "multi_target.json"):
            self.assertEqual(scenario.target_count, 3)
            result = run_scenario(scenario, ("static_grave",))
            zones = [item for item in result.final_state["entities"] if "zone" in item.get("components", {})]
            self.assertEqual(len(zones), 3)

    def test_build_contract_is_backpack_ten_active_six(self):
        for path in scenario_paths():
            scenario = load_scenario(path)
            self.assertEqual(len(scenario.build.backpack), 10)
            self.assertEqual(len(scenario.build.active), 6)
            self.assertLessEqual(set(scenario.build.active), set(scenario.build.backpack))

    def test_default_programs_are_build_independent(self):
        for path in scenario_paths():
            casts = [item for item in load_scenario(path).program if isinstance(item, Cast)]
            self.assertTrue(casts)
            self.assertTrue(all(item.skill == "each_active" for item in casts))

    def test_program_suite_exercises_all_instruction_types(self):
        instructions = [item for path in scenario_paths() for item in load_scenario(path).program]
        self.assertTrue(any(isinstance(item, Cast) for item in instructions))
        self.assertTrue(any(isinstance(item, Step) for item in instructions))
        self.assertTrue(any(isinstance(item, Advance) for item in instructions))

    def test_weights_are_canonical_probability_vectors(self):
        for path in scenario_paths():
            scenario = load_scenario(path)
            self.assertAlmostEqual(sum(scenario.weights.values()), 1.0)
            self.assertEqual(
                set(scenario.weights),
                {"combat", "survival", "control", "utility", "exploration_world_impact"},
            )

    def test_horizons_are_ordered(self):
        for path in scenario_paths():
            horizon = load_scenario(path).horizons
            self.assertLessEqual(horizon["combat_end"], horizon["short"])
            self.assertLessEqual(horizon["short"], horizon["medium"])

    def test_horizon_weights_are_strict_probability_vectors(self):
        vectors = set()
        for path in scenario_paths():
            weights = load_scenario(path).horizon_weights
            self.assertEqual(set(weights), {"combat_end", "short", "medium"})
            self.assertAlmostEqual(sum(weights.values()), 1.0)
            vectors.add(tuple(weights[key] for key in ("combat_end", "short", "medium")))
        self.assertGreaterEqual(len(vectors), 4)

    def test_initial_field_overrides_are_public_and_normalized(self):
        for path in scenario_paths():
            values = load_scenario(path).initial_fields
            self.assertLessEqual(set(values), set(CHANNELS))
            self.assertTrue(all(0.0 <= value <= 1.0 for value in values.values()))

    def test_legacy_held_out_alias_is_explicit_and_canonical(self):
        self.assertEqual(normalize_split("held_out"), "evaluation")
        self.assertEqual(split_directory("held_out").name, "evaluation")
        raw = valid_raw()
        raw["split"] = "held_out"
        raw["id"] = "held_out_short_combat"
        scenario = validate_scenario(raw)
        self.assertEqual((scenario.split, scenario.id), ("evaluation", "evaluation_short_combat"))
        redirected = load_scenario(SCENARIOS / "held_out" / "short_combat.json")
        self.assertEqual((redirected.split, redirected.id), ("evaluation", "evaluation_short_combat"))

    def test_prompt_asset_surface_is_calibration_only(self):
        paths = public_calibration_paths()
        self.assertEqual(len(paths), 6)
        self.assertTrue(all(path.parent.name == "calibration" for path in paths))

    def test_all_scenarios_execute_from_clean_worlds(self):
        for path in scenario_paths():
            scenario = load_scenario(path)
            result = run_scenario(scenario)
            self.assertEqual(result.scenario_id, scenario.id)
            self.assertEqual(result.final_state["time"]["sim_time"], scenario.horizons["medium"])
            self.assertEqual(set(result.horizons), {"combat_end", "short", "medium"})
            self.assertTrue(public_fields_are_bounded(result.initial_state))
            self.assertTrue(all(public_fields_are_bounded(state) for state in result.horizons.values()))
            self.assertTrue(public_fields_are_bounded(result.final_state))

    def test_bounds_are_a_traced_pmw_closure_not_python_mutation(self):
        raw = valid_raw()
        raw["initial_fields"] = {"electric_field": 1.0}
        result = run_scenario(validate_scenario(raw), ("static_grave",))
        activation = result.roots[0]
        self.assertIn("gm.substrate.01.normalized_bounds", activation.triggered_law_ids)
        deltas = [
            delta
            for event in activation.trace["events"]
            for commit in event["commits"]
            for delta in commit["state_deltas"]
            if delta["address"].endswith("fields/electric_field")
        ]
        self.assertTrue(any(delta["new"] > 1.0 for delta in deltas))
        self.assertTrue(any(delta["new"] == 1.0 and "gm.substrate.01.normalized_bounds" in delta["law_ids"] for delta in deltas))
        self.assertTrue(public_fields_are_bounded(result.final_state))

    def test_each_step_has_one_explicit_dissipation_root(self):
        scenario = load_scenario(SCENARIOS / "calibration" / "short_combat.json")
        result = run_scenario(scenario, ())
        steps = [root for root in result.roots if root.event_type == "lab.step"]
        dissipation = [root for root in result.roots if root.event_type == "lab.dissipate"]
        self.assertEqual(len(steps), 2)
        self.assertEqual(len(dissipation), len(steps))
        self.assertTrue(all("gm.substrate.02.dissipation" in root.triggered_law_ids for root in dissipation))

    def test_dissipation_relaxes_fields_toward_neutral_values(self):
        world = load_world(ROOT / "environments" / "mine.json")
        runtime = Engine(system_laws()).attach(world)
        zone = runtime.state.entities["zone:mine"]
        before = dict(zone.components["fields"])
        result = runtime.run_event(Event("dissipate", "lab.dissipate", target=zone.id))
        after = runtime.state.entities["zone:mine"].components["fields"]
        self.assertIn("gm.substrate.02.dissipation", result.triggered_law_ids)
        self.assertLess(after["electric_field"], before["electric_field"])
        self.assertGreater(after["visibility"], before["visibility"])
        self.assertGreater(after["temperature"], before["temperature"])
        self.assertTrue(public_fields_are_bounded(runtime.state.to_dict()))


def unknown_top_level(raw):
    raw["notes"] = "not in the executable contract"


def split_id_mismatch(raw):
    raw["split"] = "evaluation"


def unknown_environment(raw):
    raw["environment"] = "moon"


def short_backpack(raw):
    raw["build"]["backpack"].pop()


def duplicate_active(raw):
    raw["build"]["active"][1] = raw["build"]["active"][0]


def active_not_in_backpack(raw):
    raw["build"]["active"][0] = "flash_flood"


def active_slot_overflow(raw):
    high_cost = ["flare_mark", "drainage_cut", "dew_circuit", "blackout", "quiet_geometry", "heat_engine"]
    raw["build"]["backpack"] = high_cost + ["static_grave", "cold_sink", "firebreak", "mud_anchor"]
    raw["build"]["active"] = high_cost


def unknown_skill(raw):
    raw["build"]["backpack"][0] = "nonexistent_skill"


def inactive_cast(raw):
    raw["program"][0]["skill"] = "firebreak"


def illegal_target(raw):
    raw["program"][0]["target"] = "entity"


def unknown_instruction(raw):
    raw["program"][0] = {"op": "delete_world"}


def zero_steps(raw):
    raw["program"][1]["repeats"] = 0


def non_monotonic_advance(raw):
    raw["program"] = [{"op": "advance", "to": 5}, {"op": "advance", "to": 5}]


def advance_past_horizon(raw):
    raw["program"] = [{"op": "advance", "to": 41}]


def advance_after_combat_end(raw):
    raw["program"] = [{"op": "advance", "to": 1}]


def reversed_horizons(raw):
    raw["horizons"] = {"combat_end": 20, "short": 10, "medium": 40}


def non_normalized_weights(raw):
    raw["weights"]["combat"] = 0.9


def unknown_weight(raw):
    raw["weights"]["damage"] = raw["weights"].pop("combat")


def unknown_environment_variant(raw):
    raw["environment_variant"] = "secret_moon"


def hidden_initial_component(raw):
    raw["initial_fields"]["material.fuel"] = 1.0


def out_of_range_initial_field(raw):
    raw["initial_fields"]["wetness"] = 1.01


def non_normalized_horizon_weights(raw):
    raw["horizon_weights"]["medium"] = 0.9


def unknown_horizon_weight(raw):
    raw["horizon_weights"]["final"] = raw["horizon_weights"].pop("medium")


INVALID_CASES = {
    "unknown_top_level": unknown_top_level,
    "split_id_mismatch": split_id_mismatch,
    "unknown_environment": unknown_environment,
    "short_backpack": short_backpack,
    "duplicate_active": duplicate_active,
    "active_not_in_backpack": active_not_in_backpack,
    "active_slot_overflow": active_slot_overflow,
    "unknown_skill": unknown_skill,
    "inactive_cast": inactive_cast,
    "illegal_target": illegal_target,
    "unknown_instruction": unknown_instruction,
    "zero_steps": zero_steps,
    "non_monotonic_advance": non_monotonic_advance,
    "advance_past_horizon": advance_past_horizon,
    "advance_after_combat_end": advance_after_combat_end,
    "reversed_horizons": reversed_horizons,
    "non_normalized_weights": non_normalized_weights,
    "unknown_weight": unknown_weight,
    "unknown_environment_variant": unknown_environment_variant,
    "hidden_initial_component": hidden_initial_component,
    "out_of_range_initial_field": out_of_range_initial_field,
    "non_normalized_horizon_weights": non_normalized_horizon_weights,
    "unknown_horizon_weight": unknown_horizon_weight,
}


def _invalid_test(mutator):
    def test(self):
        raw = deepcopy(valid_raw())
        mutator(raw)
        with self.assertRaises(ScenarioError):
            validate_scenario(raw)
    return test


class ScenarioValidationTests(unittest.TestCase):
    pass


for _name, _mutator in INVALID_CASES.items():
    setattr(ScenarioValidationTests, f"test_reject_{_name}", _invalid_test(_mutator))


if __name__ == "__main__":
    unittest.main()
