from __future__ import annotations

from collections import Counter
from pathlib import Path
import unittest

from experiments.generative_mechanics.build_search import (
    BuildSearchError, legal_builds, pairwise_synergy, personalized_delta, search_best,
)
from experiments.generative_mechanics.evaluator import CAPABILITIES, emergent_reach, evaluate_build, evaluate_candidate
from experiments.generative_mechanics.runner import load_skill_catalog, run_scenario
from experiments.generative_mechanics.scenario import load_scenario


ROOT = Path(__file__).resolve().parents[1]


def scenarios():
    return [load_scenario(path) for path in sorted((ROOT / "scenarios").glob("*/*.json"))]


class RunnerTests(unittest.TestCase):
    def test_clean_world_runs_are_byte_equivalent(self):
        scenario = scenarios()[0]
        one = run_scenario(scenario, ("static_grave",)).to_dict()
        two = run_scenario(scenario, ("static_grave",)).to_dict()
        self.assertEqual(one, two)

    def test_multi_skill_cast_routes_each_instance_once(self):
        run = run_scenario(scenarios()[0], ("static_grave", "kindling_arc"))
        entities = {item["id"]: item for item in run.final_state["entities"]}
        self.assertEqual(entities["skill:static_grave"]["components"]["skill"]["charges"], 2)
        self.assertEqual(entities["skill:kindling_arc"]["components"]["skill"]["charges"], 2)

    def test_root_event_ids_are_unique_and_canonical(self):
        run = run_scenario(scenarios()[0], ("static_grave", "kindling_arc"))
        ids = [root.event_id for root in run.roots]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(item.startswith(run.scenario_id) or item.startswith("gm.handle.") for item in ids))

    def test_runner_rejects_unknown_skill(self):
        with self.assertRaisesRegex(ValueError, "unknown active"):
            run_scenario(scenarios()[0], ("not_a_skill",))

    def test_horizon_snapshots_are_all_materialized(self):
        scenario = scenarios()[0]
        run = run_scenario(scenario, ("static_grave",))
        self.assertEqual(set(run.horizons), {"combat_end", "short", "medium"})
        self.assertEqual(run.final_state["time"]["sim_time"], scenario.horizons["medium"])


class EvaluatorTests(unittest.TestCase):
    def test_evaluation_profile_uses_exactly_six_scenarios(self):
        profile = evaluate_build(scenarios(), ("static_grave",), split="held_out")
        self.assertEqual(len(profile.scenario_scores), 6)
        self.assertEqual(profile.split, "evaluation")
        self.assertTrue(all(item.scenario_id.startswith("evaluation_") for item in profile.scenario_scores))

    def test_calibration_and_held_out_are_separate(self):
        calibration = evaluate_build(scenarios(), ("static_grave",), split="calibration")
        held_out = evaluate_build(scenarios(), ("static_grave",), split="held_out")
        self.assertTrue(all(item.scenario_id.startswith("calibration_") for item in calibration.scenario_scores))
        self.assertNotEqual({item.scenario_id for item in calibration.scenario_scores}, {item.scenario_id for item in held_out.scenario_scores})

    def test_profile_statistics_follow_definitions(self):
        profile = evaluate_build(scenarios(), ("static_grave",), split="held_out")
        values = sorted(item.value for item in profile.scenario_scores)
        self.assertAlmostEqual(profile.typical_power, sum(values) / len(values))
        self.assertEqual(profile.p90_power, values[5])
        self.assertEqual(profile.ceiling_power, max(values))

    def test_capability_vector_has_frozen_dimensions(self):
        profile = evaluate_build(scenarios(), ("static_grave",), split="held_out")
        self.assertEqual(set(profile.capability_vector), set(CAPABILITIES))

    def test_power_profile_has_all_eight_core_metrics(self):
        profile = evaluate_build(scenarios(), ("static_grave", "kindling_arc"), split="held_out")
        raw = profile.to_dict()
        self.assertEqual(
            {"TypicalPower", "P90Power", "CeilingPower", "PersonalizedBuildDelta", "SynergyAmplification", "InteractionSurface", "ExploitRisk", "PersistentWorldImpact"} - set(raw),
            set(),
        )
        self.assertIsNone(raw["PersonalizedBuildDelta"])
        self.assertIn(raw["ExploitRisk"], {"LOW", "MEDIUM", "HIGH", "CRITICAL"})

    def test_synergy_amplification_uses_execution_scores(self):
        suite = scenarios()
        pair = evaluate_build(suite, ("static_grave", "kindling_arc"), split="held_out")
        first = evaluate_build(suite, ("static_grave",), split="held_out")
        second = evaluate_build(suite, ("kindling_arc",), split="held_out")
        empty = evaluate_build(suite, (), split="held_out")
        expected = pair.typical_power - first.typical_power - second.typical_power + empty.typical_power
        self.assertAlmostEqual(pair.synergy_amplification, expected)

    def test_candidate_evaluation_populates_personalized_delta(self):
        result = evaluate_candidate(scenarios(), ("kindling_arc", "clear_sky"), "static_grave", split="calibration")
        self.assertIsNotNone(result.profile.personalized_build_delta)
        self.assertIn("PersonalizedBuildDelta", result.to_dict()["PowerProfile"])
        self.assertIn("static_grave", result.best_after)

    def test_interaction_and_persistence_are_execution_derived(self):
        profile = evaluate_build(scenarios(), ("static_grave",), split="held_out")
        self.assertGreater(profile.interaction_surface, 0)
        self.assertGreater(profile.persistent_world_impact, 0)

    def test_emergent_reach_uses_paired_counterfactual(self):
        wetland = next(item for item in scenarios() if item.split == "evaluation" and item.environment == "wetland")
        reach = emergent_reach(wetland, ("static_grave",), "static_grave")
        self.assertGreater(reach.direct_law_count, 0)
        self.assertGreater(reach.downstream_law_count, 0)
        self.assertEqual(reach.causal_depth, 2)
        self.assertTrue(all(item.startswith("gm.world.") for item in reach.downstream_laws))
        self.assertGreater(reach.affected_subsystem_count, 0)
        self.assertGreater(reach.persistent_consequence_count, 0)

    def test_direct_only_change_is_not_counted_as_downstream(self):
        mine = next(item for item in scenarios() if item.split == "evaluation" and item.environment == "mine")
        reach = emergent_reach(mine, ("stability_charge",), "stability_charge")
        self.assertGreater(reach.direct_law_count, 0)
        self.assertEqual((reach.downstream_law_count, reach.affected_subsystem_count, reach.persistent_consequence_count), (0, 0, 0))
        self.assertEqual(reach.causal_depth, 1)

    def test_emergent_reach_candidate_must_be_in_build(self):
        with self.assertRaisesRegex(ValueError, "present"):
            emergent_reach(scenarios()[0], (), "static_grave")


class BuildSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog = load_skill_catalog()
        cls.one_slot = tuple(item for item in catalog.values() if item.slot_cost == 1)[:10]
        cls.catalog = catalog

    def test_ten_one_slot_skills_have_848_legal_subsets(self):
        self.assertEqual(len(self.one_slot), 10)
        self.assertEqual(len(legal_builds(self.one_slot)), 848)

    def test_every_legal_build_obeys_active_and_slot_caps(self):
        by_id = {item.id: item for item in self.one_slot}
        for build in legal_builds(self.one_slot):
            self.assertLessEqual(len(build), 6)
            self.assertLessEqual(sum(by_id[item].slot_cost for item in build), 6)

    def test_search_evaluates_each_legal_subset_exactly_once(self):
        seen = Counter()
        result = search_best(self.one_slot, lambda build: seen.update([build]) or len(build))
        self.assertEqual(result.evaluations, 848)
        self.assertEqual(set(seen.values()), {1})

    def test_search_tie_break_is_canonical(self):
        result = search_best(self.one_slot[:3], lambda build: 1)
        self.assertEqual(result.best.skills, ())

    def test_pairwise_synergy_formula(self):
        specs = self.one_slot[:3]
        values = {(): 0, (specs[0].id,): 1, (specs[1].id,): 2}
        def score(build):
            return values.get(build, sum(values.get((item,), 0) for item in build) + (3 if len(build) == 2 else 0))
        synergy = pairwise_synergy(specs, score)
        self.assertTrue(all(value == 3 for value in synergy.values()))

    def test_personalized_delta_compares_best_before_after(self):
        specs = self.one_slot[:4]
        candidate = self.one_slot[4]
        result = personalized_delta(specs, candidate, lambda build: 10 if candidate.id in build else len(build))
        self.assertEqual(result.delta, 6)
        self.assertIn(candidate.id, result.after.skills)

    def test_backpack_over_ten_is_rejected(self):
        specs = tuple(self.catalog.values())[:11]
        with self.assertRaises(BuildSearchError):
            legal_builds(specs)


if __name__ == "__main__":
    unittest.main()
