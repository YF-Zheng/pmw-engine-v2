from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.generative_mechanics.compiler import canonical_json
from experiments.generative_mechanics.oracle import (
    MANIFEST_PATH,
    build_contextual_oracle_suite,
    build_oracle_suite,
    canonical_oracle_cases,
    contextual_subset_audit,
    evaluate_oracle_intrinsic,
    evaluate_oracle_personalized_delta,
    public_scenario_assets,
)
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
        self.assertEqual(manifest["contextual_subset"]["default_case_count"], 24)
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

    def test_custom_suite_cannot_bypass_registered_oracle(self):
        contextual = build_contextual_oracle_suite()
        custom_contextual = (replace(contextual[0], target_count=4), *contextual[1:])
        with self.assertRaisesRegex(ValueError, "not registered"):
            evaluate_oracle_personalized_delta("candidate", suite=custom_contextual)
        with self.assertRaisesRegex(ValueError, "not registered"):
            evaluate_oracle_intrinsic(("candidate",), suite=self.suite[:143])

    def test_explicit_registered_profiles_remain_accepted(self):
        contextual_sentinel = object()
        intrinsic_sentinel = object()
        with patch(
            "experiments.generative_mechanics.power_v02.evaluate_contextual_power",
            return_value=contextual_sentinel,
        ):
            self.assertIs(evaluate_oracle_personalized_delta(
                "candidate", suite=build_contextual_oracle_suite(case_count=12),
            ), contextual_sentinel)
        with patch(
            "experiments.generative_mechanics.power_v02.evaluate_power",
            return_value=intrinsic_sentinel,
        ):
            self.assertIs(evaluate_oracle_intrinsic(
                ("candidate",), suite=build_oracle_suite(),
            ), intrinsic_sentinel)

    def test_contextual_subset_is_stable_and_preregistered(self):
        first = build_contextual_oracle_suite()
        second = build_contextual_oracle_suite()
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(first), 24)
        self.assertEqual([case.id for case in first], [case.id for case in second])
        self.assertEqual(
            contextual_subset_audit(first)["digest"],
            manifest["contextual_subset"]["digests"]["24"],
        )

    def test_contextual_digest_covers_every_execution_semantic_group(self):
        suite = build_contextual_oracle_suite()
        base = suite[0]
        original = contextual_subset_audit(suite)["digest"]
        horizons = dict(base.horizons)
        horizons["short"] += 1.0
        horizon_weights = dict(base.horizon_weights)
        horizon_weights["combat_end"] += 0.01
        horizon_weights["short"] -= 0.01
        capability_weights = dict(base.weights)
        capability_weights["combat"] += 0.01
        mutations = {
            "program": replace(base, program=(*base.program, base.program[-1])),
            "horizons": replace(base, horizons=horizons),
            "horizon_weights": replace(base, horizon_weights=horizon_weights),
            "capability_weights": replace(base, weights=capability_weights),
            "target_count": replace(
                base, target_count=1 if base.target_count != 1 else 2,
            ),
        }
        for semantic_group, changed in mutations.items():
            with self.subTest(semantic_group=semantic_group):
                changed_suite = (changed, *suite[1:])
                self.assertNotEqual(contextual_subset_audit(changed_suite)["digest"], original)

    def test_contextual_profiles_meet_stratified_coverage_contract(self):
        for count in (12, 18, 24):
            suite = build_contextual_oracle_suite(case_count=count)
            audit = contextual_subset_audit(suite)
            self.assertEqual(audit["case_count"], count)
            self.assertEqual(len(audit["categories"]), 6)
            self.assertEqual(len(audit["environments"]), 4)
            self.assertGreaterEqual(len(audit["environment_variants"]), 3)
            self.assertGreaterEqual(audit["distinct_backpacks"], count // 2)
            self.assertGreaterEqual(audit["distinct_active_builds"], count // 2)
            self.assertGreaterEqual(audit["distinct_initial_fields"], count // 2)

    def test_contextual_sensitivity_profiles_are_strictly_nested(self):
        ids_12 = {case.id for case in build_contextual_oracle_suite(case_count=12)}
        ids_18 = {case.id for case in build_contextual_oracle_suite(case_count=18)}
        ids_24 = {case.id for case in build_contextual_oracle_suite(case_count=24)}
        self.assertLess(ids_12, ids_18)
        self.assertLess(ids_18, ids_24)

    def test_contextual_subset_is_drawn_from_full_oracle(self):
        full = {case.id: case for case in self.suite}
        for case in build_contextual_oracle_suite():
            self.assertEqual(case, full[case.id])

    def test_changed_selection_seed_is_rejected_by_digest(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest["contextual_subset"]["selection_seed"] += 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                build_contextual_oracle_suite(path)

    def test_malformed_contextual_manifest_is_rejected(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest["contextual_subset"].pop("selection")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest contract"):
                build_contextual_oracle_suite(path)

    def test_oracle_entry_points_use_distinct_registered_suite_sizes(self):
        contextual_sentinel = object()
        intrinsic_sentinel = object()
        with patch(
            "experiments.generative_mechanics.power_v02.evaluate_contextual_power",
            side_effect=lambda suite, *_args, **_kwargs:
                contextual_sentinel if len(tuple(suite)) == 24 else None,
        ):
            self.assertIs(
                evaluate_oracle_personalized_delta("candidate"),
                contextual_sentinel,
            )
        with patch(
            "experiments.generative_mechanics.power_v02.evaluate_power",
            side_effect=lambda suite, *_args, **_kwargs:
                intrinsic_sentinel if len(tuple(suite)) == 144 else None,
        ):
            self.assertIs(evaluate_oracle_intrinsic(("candidate",)), intrinsic_sentinel)


if __name__ == "__main__":
    unittest.main()
