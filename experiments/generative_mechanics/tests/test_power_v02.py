from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path
import unittest

from experiments.generative_mechanics.batch import execution_score
from experiments.generative_mechanics.build_search import (
    MAX_AUGMENTED_BACKPACK,
    legal_builds,
)
from experiments.generative_mechanics.evaluator import evaluate_build
from experiments.generative_mechanics.generation import (
    DirectEffectSpec, compile_direct_effect, prepare_direct_world,
)
from experiments.generative_mechanics.power_v02 import (
    ContextualSearchCache,
    POWER_SCALE,
    evaluate_contextual_power,
    evaluate_power,
)
from experiments.generative_mechanics.runner import load_skill_catalog
from experiments.generative_mechanics.scenario import load_scenario


ROOT = Path(__file__).resolve().parents[1]


def evaluation_scenarios():
    return tuple(
        load_scenario(path)
        for path in sorted((ROOT / "scenarios" / "evaluation").glob("*.json"))
    )


class PowerScaleV02Tests(unittest.TestCase):
    def test_batch_and_power_profile_share_exact_scale(self):
        suite = evaluation_scenarios()
        catalog = load_skill_catalog()
        batch_value = execution_score(suite, ("static_grave",), catalog)[0]
        profile_value = evaluate_build(
            suite, ("static_grave",), split="evaluation", catalog=catalog,
        ).typical_power
        self.assertEqual(batch_value, profile_value)
        self.assertEqual(POWER_SCALE.schema_version, "gm-power-scale-v0.2")

    def test_scenario_value_is_weighted_across_three_horizons(self):
        scenario = evaluation_scenarios()[0]
        profile = evaluate_power((scenario,), ("static_grave",), split="evaluation")
        row = profile.scenario_scores[0]
        expected_capabilities = {
            capability: sum(
                horizon.weight * horizon.capabilities[capability]
                for horizon in row.horizons
            )
            for capability in row.capabilities
        }
        self.assertEqual(tuple(item.name for item in row.horizons), ("combat_end", "short", "medium"))
        for capability, expected in expected_capabilities.items():
            self.assertAlmostEqual(row.capabilities[capability], expected)

    def test_short_duration_direct_effects_do_not_collapse_to_zero(self):
        scenario = next(item for item in evaluation_scenarios() if item.category == "short_combat")
        scores = {}
        persistence = {}
        for duration in (0.0, 8.0, 25.0, 300.0):
            spec = DirectEffectSpec(
                f"duration_{int(duration)}", "Duration probe", "damage", 1.0,
                duration, 0.0, 10, 1,
            )
            catalog = {**load_skill_catalog(), spec.id: spec}
            profile = evaluate_power(
                (scenario,), (spec.id,), split="evaluation", catalog=catalog,
                compile_mechanic=compile_direct_effect,
                world_setup=prepare_direct_world,
            )
            scores[duration] = profile.typical_power
            persistence[duration] = profile.persistent_world_impact
        self.assertTrue(all(scores[duration] > 0 for duration in (0.0, 8.0, 25.0, 300.0)))
        self.assertEqual(persistence[8.0], 0)
        self.assertGreater(persistence[300.0], 0)


class ContextualV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = evaluation_scenarios()[0]
        cls.seed_catalog = load_skill_catalog()
        template = next(item for item in cls.seed_catalog.values() if item.slot_cost == 1)
        cls.candidate_a = replace(template, id="context_candidate_a", name="Context candidate A")
        cls.candidate_b = replace(template, id="context_candidate_b", name="Context candidate B")

    def _catalog(self, *candidates):
        return {**self.seed_catalog, **{item.id: item for item in candidates}}

    def test_real_scenario_backpack_drives_exact_ten_to_eleven_search(self):
        seen = Counter()

        def score(_scenario, build):
            seen.update(build)
            return (100.0 if self.candidate_a.id in build else 0.0) + len(build)

        result = evaluate_contextual_power(
            (self.scenario,), self.candidate_a.id, split="evaluation",
            catalog=self._catalog(self.candidate_a), score_fn=score,
        )
        audit = result.contexts[0]
        backpack_specs = [self.seed_catalog[item] for item in self.scenario.build.backpack]
        augmented_specs = [*backpack_specs, self.candidate_a]
        self.assertEqual(audit.backpack, tuple(sorted(self.scenario.build.backpack)))
        self.assertEqual(audit.before_legal_builds, len(legal_builds(backpack_specs)))
        self.assertEqual(
            audit.after_legal_builds,
            len(legal_builds(augmented_specs, max_backpack=MAX_AUGMENTED_BACKPACK)),
        )
        self.assertIn(self.candidate_a.id, audit.best_after.skills)
        self.assertGreater(result.mean, 0)

    def test_before_search_cache_is_reused_without_changing_exact_result(self):
        cache = ContextualSearchCache()
        calls = Counter()

        def score(_scenario, build):
            calls["seed" if not {self.candidate_a.id, self.candidate_b.id} & set(build) else "candidate"] += 1
            return float(len(build))

        evaluate_contextual_power(
            (self.scenario,), self.candidate_a.id, split="evaluation",
            catalog=self._catalog(self.candidate_a, self.candidate_b),
            score_fn=score, cache=cache,
        )
        seed_calls = calls["seed"]
        cached = evaluate_contextual_power(
            (self.scenario,), self.candidate_b.id, split="evaluation",
            catalog=self._catalog(self.candidate_a, self.candidate_b),
            score_fn=score, cache=cache,
        )
        self.assertEqual(calls["seed"], seed_calls)
        fresh = evaluate_contextual_power(
            (self.scenario,), self.candidate_b.id, split="evaluation",
            catalog=self._catalog(self.candidate_a, self.candidate_b),
            score_fn=lambda _scenario, build: float(len(build)),
        )
        self.assertEqual(cached.to_dict(), fresh.to_dict())

    def test_contextual_schema_is_not_intrinsic_power(self):
        result = evaluate_contextual_power(
            (self.scenario,), self.candidate_a.id, split="evaluation",
            catalog=self._catalog(self.candidate_a),
            score_fn=lambda _scenario, build: float(len(build)),
        ).to_dict()
        intrinsic = evaluate_power(
            (self.scenario,), (), split="evaluation",
        ).to_dict()
        self.assertEqual(result["estimand"], "ContextualMarginalPower")
        self.assertEqual(intrinsic["estimand"], "IntrinsicPower")
        self.assertNotIn("TypicalPower", result)
        self.assertNotIn("mean", intrinsic)


if __name__ == "__main__":
    unittest.main()
