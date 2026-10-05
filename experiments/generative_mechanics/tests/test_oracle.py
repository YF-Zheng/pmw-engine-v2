from __future__ import annotations

import json
from pathlib import Path
import unittest

from experiments.generative_mechanics.compiler import canonical_json
from experiments.generative_mechanics.oracle import (
    MANIFEST_PATH,
    build_oracle_suite,
    canonical_oracle_cases,
    evaluate_oracle_intrinsic,
    evaluate_oracle_personalized_delta,
    public_scenario_assets,
)
from experiments.generative_mechanics.runner import load_skill_catalog
from experiments.generative_mechanics.runner import run_scenario
from experiments.generative_mechanics.substrate import CHANNELS, public_fields_are_bounded


ROOT = Path(__file__).resolve().parents[1]


class HiddenOracleSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = build_oracle_suite()

    def test_manifest_freezes_compact_suite_of_144(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["protocol"], "gm-oracle-v0.2")
        self.assertEqual(manifest["case_count"], 144)
        self.assertEqual(len(self.suite), 144)
        self.assertFalse(any((ROOT / "oracle").glob("trace*")))

    def test_reconstruction_is_byte_canonical(self):
        first = canonical_json(canonical_oracle_cases())
        second = canonical_json(canonical_oracle_cases())
        self.assertEqual(first, second)

    def test_distribution_has_required_diversity(self):
        self.assertEqual(len({case.category for case in self.suite}), 6)
        self.assertEqual(len({case.environment for case in self.suite}), 4)
        self.assertEqual(len({case.environment_variant for case in self.suite}), 6)
        self.assertEqual(
            {field for case in self.suite for field in case.initial_fields},
            set(CHANNELS),
        )
        self.assertGreaterEqual(len({canonical_json(case.initial_fields) for case in self.suite}), 100)
        self.assertGreaterEqual(len({canonical_json([
            {name: getattr(command, name) for name in command.__dataclass_fields__}
            for command in case.program
        ]) for case in self.suite}), 12)

    def test_every_case_has_ten_backpack_and_legal_six_active(self):
        for case in self.suite:
            self.assertEqual(len(case.build.backpack), 10)
            self.assertEqual(len(case.build.active), 6)
            self.assertLessEqual(set(case.build.active), set(case.build.backpack))
            self.assertAlmostEqual(sum(case.horizon_weights.values()), 1.0)

    def test_prompt_surface_cannot_expose_evaluation_or_oracle(self):
        assets = public_scenario_assets()
        self.assertEqual(len(assets), 6)
        self.assertTrue(all("/scenarios/calibration/" in path.as_posix() for path in assets))
        self.assertTrue(all("oracle" not in path.as_posix() and "evaluation" not in path.as_posix() for path in assets))

    def test_all_144_oracle_cases_execute_and_remain_bounded(self):
        for case in self.suite:
            result = run_scenario(case, (case.build.active[0],))
            self.assertEqual(set(result.horizons), {"combat_end", "short", "medium"})
            self.assertTrue(public_fields_are_bounded(result.initial_state))
            self.assertTrue(all(public_fields_are_bounded(value) for value in result.horizons.values()))

    def test_two_oracle_targets_are_distinct_executable_estimands(self):
        catalog = load_skill_catalog()
        candidate = next(skill_id for skill_id in catalog if skill_id not in self.suite[0].build.backpack)
        intrinsic = evaluate_oracle_intrinsic(
            (candidate,), catalog=catalog, suite=self.suite[:1],
        )
        contextual = evaluate_oracle_personalized_delta(
            candidate, catalog=catalog, suite=self.suite[:1],
            score_fn=lambda _scenario, build: float(len(build)),
        )
        self.assertEqual(intrinsic.to_dict()["estimand"], "IntrinsicPower")
        self.assertEqual(contextual.to_dict()["estimand"], "ContextualMarginalPower")
        self.assertNotEqual(set(intrinsic.to_dict()), set(contextual.to_dict()))


if __name__ == "__main__":
    unittest.main()
