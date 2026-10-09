from __future__ import annotations

import unittest

from experiments.generative_mechanics.formal_statistics import (
    P1, P2, P3, P4, P5, P6,
    FormalStatisticsError,
    benjamini_hochberg_adjust,
    endpoint_estimate,
    endpoint_value,
    holm_adjust,
    matched_pairwise_bootstrap,
    percentile_bootstrap,
    within_block_permutation_omnibus,
)


def row(block: int, model: str, *, valid: bool = True, activation: float = 0.5,
        depths=(1, 3), fingerprint="a",
        outcome=(True, False, False, False, False, False),
        path=(False, False, False, False, False, False)):
    contexts = [
        {"outcome_differentiated": left, "causal_path_differentiated": right}
        for left, right in zip(outcome, path)
    ]
    return {
        "base_sample_index": block,
        "model_id": model,
        "execution_valid": valid,
        "profile": None if not valid else {
            "dynamic_reach": {
                "activation_rate": activation,
                "conditional_on_activation": {
                    "available": bool(depths),
                    "realized_dependency_depth_distribution": list(depths),
                },
            },
            "environmental_behavior": {"contexts": contexts},
            "structural_evidence": {
                "available": True,
                "abstract_topology": {"fingerprint": fingerprint},
            },
        },
    }


class EndpointTests(unittest.TestCase):
    def test_p1_to_p6_are_mechanism_level_and_preserve_na(self):
        valid = row(
            0, "a", activation=0.25, depths=(1, 2, 9),
            outcome=(True, False, True, False, True, False),
            path=(True, True, True, True, True, True),
        )
        invalid = row(1, "a", valid=False)
        self.assertEqual(endpoint_value(valid, P1), 1.0)
        self.assertEqual(endpoint_value(invalid, P1), 0.0)
        self.assertEqual(endpoint_value(valid, P2), 0.25)
        self.assertEqual(endpoint_value(valid, P3), 2.0)
        self.assertEqual(endpoint_value(valid, P4), "a")
        self.assertEqual(endpoint_value(valid, P5), 0.5)
        self.assertEqual(endpoint_value(valid, P6), 1.0)
        for endpoint in (P2, P3, P4, P5, P6):
            self.assertIsNone(endpoint_value(invalid, endpoint))

    def test_never_activated_is_zero_p2_but_na_p3(self):
        mechanism = row(0, "a", activation=0.0, depths=())
        self.assertEqual(endpoint_value(mechanism, P2), 0.0)
        self.assertIsNone(endpoint_value(mechanism, P3))

    def test_p3_summarizes_each_mechanism_before_model(self):
        rows = [row(0, "a", depths=(0, 100)), row(1, "a", depths=(4,))]
        self.assertEqual(endpoint_estimate(rows, P3), 27.0)

    def test_p4_is_pairwise_collision_probability(self):
        rows = [row(0, "a", fingerprint=x) for x in ("x", "x", "y", "z")]
        self.assertAlmostEqual(endpoint_estimate(rows, P4), 1 / 6)
        self.assertIsNone(endpoint_estimate(rows[:1], P4))

    def test_registered_context_count_and_activation_bounds_fail_closed(self):
        malformed_contexts = row(0, "a", outcome=(True,), path=(False,))
        with self.assertRaisesRegex(FormalStatisticsError, "exactly 6"):
            endpoint_value(malformed_contexts, P5)
        with self.assertRaisesRegex(FormalStatisticsError, "outside"):
            endpoint_value(row(0, "a", activation=1.1), P2)


class ResamplingTests(unittest.TestCase):
    def test_percentile_bootstrap_is_deterministic_and_p4_recomputed(self):
        rows = [row(i, "a", fingerprint=("x" if i < 2 else f"u{i}")) for i in range(6)]
        first = percentile_bootstrap(rows, P4, replicates=200, seed=41, minimum_valid_fraction=0.0)
        second = percentile_bootstrap(rows, P4, replicates=200, seed=41, minimum_valid_fraction=0.0)
        self.assertEqual(first, second)
        self.assertEqual(first["estimate"], endpoint_estimate(rows, P4))
        self.assertEqual(first["resampling_unit"], "generated_mechanism")
        self.assertEqual(first["replicates_valid"], 200)

    def test_matched_bootstrap_resamples_blocks_and_keeps_na_attached(self):
        rows = []
        for block in range(8):
            rows.extend((
                row(block, "a", activation=1.0),
                row(block, "b", activation=0.0, depths=()),
            ))
        result = matched_pairwise_bootstrap(rows, "a", "b", P2, replicates=250, seed=9)
        self.assertEqual(result["complete_block_count"], 8)
        self.assertEqual(result["estimate"], 1.0)
        self.assertEqual(result["ci_low"], 1.0)
        self.assertEqual(result["ci_high"], 1.0)
        self.assertEqual(result["resampling_unit"], "base_sample_index_block")

    def test_matched_bootstrap_p4_is_recomputed_not_row_averaged(self):
        rows = []
        for block, (left, right) in enumerate(zip("aabc", "wwww")):
            rows.extend((row(block, "a", fingerprint=left), row(block, "b", fingerprint=right)))
        result = matched_pairwise_bootstrap(
            rows, "a", "b", P4, replicates=200, seed=7, minimum_valid_fraction=0.0,
        )
        self.assertAlmostEqual(result["estimate"], 1 / 6 - 1.0)
        self.assertEqual(result["replicates_valid"], 200)


class PermutationAndMultiplicityTests(unittest.TestCase):
    def test_within_block_permutation_exact_and_deterministic(self):
        rows = [
            row(0, "a", activation=1.0), row(0, "b", activation=0.0, depths=()),
            row(1, "a", activation=1.0), row(1, "b", activation=0.0, depths=()),
        ]
        result = within_block_permutation_omnibus(rows, ("a", "b"), P2, permutations=10, seed=3)
        self.assertTrue(result["exact"])
        self.assertEqual(result["admissible_permutations"], 4)
        self.assertEqual(result["permutations_evaluated"], 4)
        self.assertAlmostEqual(result["p_value"], 0.5)

    def test_p4_permutation_runs_on_whole_fingerprints(self):
        rows = []
        for block, (left, right) in enumerate(zip("aaaa", "wxyz")):
            rows.extend((row(block, "a", fingerprint=left), row(block, "b", fingerprint=right)))
        first = within_block_permutation_omnibus(rows, ("a", "b"), P4, permutations=10, seed=11)
        second = within_block_permutation_omnibus(rows, ("a", "b"), P4, permutations=10, seed=11)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "ESTIMATED")
        self.assertFalse(first["exact"])

    def test_incomplete_blocks_are_excluded(self):
        rows = [row(0, "a"), row(0, "b"), row(1, "a")]
        result = within_block_permutation_omnibus(rows, ("a", "b"), P1, permutations=4)
        self.assertEqual(result["complete_block_count"], 1)

    def test_holm_and_bh_preserve_na(self):
        values = {"a": 0.01, "b": 0.04, "c": 0.03, "missing": None}
        self.assertEqual(holm_adjust(values), {"a": 0.03, "b": 0.06, "c": 0.06, "missing": None})
        bh = benjamini_hochberg_adjust(values)
        self.assertAlmostEqual(bh["a"], 0.03)
        self.assertAlmostEqual(bh["b"], 0.04)
        self.assertAlmostEqual(bh["c"], 0.04)
        self.assertIsNone(bh["missing"])

    def test_invalid_options_and_unknown_endpoint_fail_closed(self):
        with self.assertRaises(FormalStatisticsError):
            endpoint_estimate([], "not-an-endpoint")
        with self.assertRaises(FormalStatisticsError):
            percentile_bootstrap([], P1, replicates=0)
        with self.assertRaises(FormalStatisticsError):
            holm_adjust({"bad": 1.1})


if __name__ == "__main__":
    unittest.main()
