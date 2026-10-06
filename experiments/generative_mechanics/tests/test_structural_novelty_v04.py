from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.structural_novelty import (
    ALGORITHM_VERSION,
    REFERENCE_REGISTRY,
    StructuralNoveltyError,
    canonical_structure,
    duplicate_structure_profile,
    evaluate_structural_novelty,
    structure_fingerprint,
)


ROOT = Path(__file__).parents[1]


def mechanic() -> dict:
    return {
        "id": "candidate_arc",
        "name": "Candidate Arc",
        "target_scope": "zone",
        "effects": [
            {"field": "wetness", "delta": 0.31},
            {"field": "electric_field", "delta": -0.44},
        ],
        "duration": 0.0,
        "periodic": {"interval": 4.0, "repeats": 3},
        "trigger_conditions": [
            {"field": "temperature", "op": "gte", "value": 0.2},
            {"field": "visibility", "op": "lt", "value": 0.8},
        ],
        "resource_cost": 17.0,
        "charges": 2,
        "slot_cost": 1,
    }


class CanonicalStructureTests(unittest.TestCase):
    def test_identity_and_all_numeric_tuning_are_invariant(self):
        original = mechanic()
        tuned = copy.deepcopy(original)
        tuned.update({"id": "renamed_mechanic", "name": "Entirely Different", "resource_cost": 99.0, "charges": 9, "slot_cost": 2})
        tuned["effects"][0]["delta"] = 0.99
        tuned["effects"][1]["delta"] = -0.01
        tuned["periodic"] = {"interval": 250.0, "repeats": 11}
        tuned["trigger_conditions"][0]["value"] = 0.91
        self.assertEqual(structure_fingerprint(original), structure_fingerprint(tuned))

    def test_effect_polarity_is_structural_but_same_direction_magnitude_is_not(self):
        positive = mechanic()
        positive_tuned = copy.deepcopy(positive)
        positive_tuned["effects"][0]["delta"] = 0.001
        negative = copy.deepcopy(positive)
        negative["effects"][0]["delta"] = -0.31
        self.assertEqual(structure_fingerprint(positive), structure_fingerprint(positive_tuned))
        self.assertNotEqual(structure_fingerprint(positive), structure_fingerprint(negative))

    def test_all_zero_effect_is_excluded_from_novelty_rate(self):
        zero = copy.deepcopy(mechanic())
        zero["effects"][0]["delta"] = 0.0
        zero["effects"][1]["delta"] = 0.0
        report = evaluate_structural_novelty(zero)
        self.assertFalse(report["available"])
        self.assertTrue(report["excluded_from_novelty_rate"])
        self.assertIn("no effective write topology", report["reason"])
        self.assertTrue(report["no_op_evidence"]["has_zero_effect"])
        self.assertEqual(
            report["no_op_evidence"]["zero_effect_fields"],
            ["electric_field", "wetness"],
        )
        self.assertNotIn("exact_novel_against_registry", report)

    def test_zero_effect_in_mixed_mechanic_does_not_create_novel_topology(self):
        mixed = copy.deepcopy(mechanic())
        mixed["effects"][1]["delta"] = 0.0
        effective_only = copy.deepcopy(mixed)
        effective_only["effects"] = [effective_only["effects"][0]]
        self.assertEqual(structure_fingerprint(mixed), structure_fingerprint(effective_only))
        mixed_report = evaluate_structural_novelty(mixed)
        effective_report = evaluate_structural_novelty(effective_only)
        self.assertEqual(
            mixed_report["exact_novel_against_registry"],
            effective_report["exact_novel_against_registry"],
        )
        self.assertEqual(
            mixed_report["pareto_reference_frontier"],
            effective_report["pareto_reference_frontier"],
        )
        self.assertEqual(mixed_report["no_op_evidence"]["zero_effect_fields"], ["electric_field"])

    def test_effect_and_condition_order_are_invariant(self):
        reordered = copy.deepcopy(mechanic())
        reordered["effects"].reverse()
        reordered["trigger_conditions"].reverse()
        self.assertEqual(canonical_structure(mechanic()), canonical_structure(reordered))

    def test_write_topology_change_changes_structure(self):
        changed = copy.deepcopy(mechanic())
        changed["effects"][0]["field"] = "fire_intensity"
        self.assertNotEqual(structure_fingerprint(mechanic()), structure_fingerprint(changed))

    def test_trigger_topology_and_operator_changes_change_structure(self):
        changed_read = copy.deepcopy(mechanic())
        changed_read["trigger_conditions"][0]["field"] = "water_level"
        changed_operator = copy.deepcopy(mechanic())
        changed_operator["trigger_conditions"][0]["op"] = "lte"
        base = structure_fingerprint(mechanic())
        self.assertNotEqual(base, structure_fingerprint(changed_read))
        self.assertNotEqual(base, structure_fingerprint(changed_operator))

    def test_temporal_mode_changes_structure_but_temporal_numbers_do_not(self):
        sustained = copy.deepcopy(mechanic())
        sustained["periodic"] = None
        sustained["duration"] = 20.0
        instantaneous = copy.deepcopy(sustained)
        instantaneous["duration"] = 0.0
        self.assertNotEqual(structure_fingerprint(mechanic()), structure_fingerprint(sustained))
        self.assertNotEqual(structure_fingerprint(sustained), structure_fingerprint(instantaneous))


class StructuralNoveltyProfileTests(unittest.TestCase):
    def test_registered_duplicate_is_not_exactly_novel(self):
        raw = json.loads((ROOT / "skills" / "ash_bloom.json").read_text(encoding="utf-8"))
        renamed = copy.deepcopy(raw)
        renamed["id"] = "renamed_ash"
        renamed["name"] = "Renamed Ash"
        renamed["effects"][0]["delta"] = 0.91
        report = evaluate_structural_novelty(renamed)
        self.assertFalse(report["exact_novel_against_registry"])
        self.assertIn("ash_bloom", report["exact_reference_matches"])
        self.assertEqual(report["algorithm_version"], ALGORITHM_VERSION)

    def test_novel_profile_has_raw_components_and_no_scalar_score(self):
        report = evaluate_structural_novelty(mechanic())
        self.assertTrue(report["exact_novel_against_registry"])
        self.assertTrue(report["pareto_reference_frontier"])
        self.assertNotIn("score", report)
        self.assertNotIn("distance", report)
        expected = {
            "write_terms_added", "write_terms_removed",
            "write_fields_added", "write_fields_removed",
            "effect_polarity_changes",
            "read_fields_added", "read_fields_removed",
            "trigger_operators_added", "trigger_operators_removed",
            "trigger_terms_added", "trigger_terms_removed",
            "temporal_shape_changed", "target_scope_changed",
            "effect_cardinality_delta", "condition_cardinality_delta",
        }
        for reference in report["pareto_reference_frontier"]:
            self.assertIn("source_catalog_category", reference)
            self.assertNotIn("registered_family", reference)
            self.assertEqual(set(reference["difference_components"]), expected)

    def test_reference_registry_is_digest_checked(self):
        metadata = json.loads(REFERENCE_REGISTRY.read_text(encoding="utf-8"))
        metadata["reference_projection_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(StructuralNoveltyError, "projection digest mismatch"):
                evaluate_structural_novelty(mechanic(), registry_path=path)

    def test_duplicate_mechanics_are_grouped_despite_renaming_and_tuning(self):
        duplicate = copy.deepcopy(mechanic())
        duplicate["id"] = "other_identity"
        duplicate["name"] = "Other Identity"
        duplicate["effects"][0]["delta"] = 0.02
        distinct = copy.deepcopy(mechanic())
        distinct["effects"][0]["field"] = "fire_intensity"
        profile = duplicate_structure_profile((
            ("sample-a", mechanic()), ("sample-b", duplicate), ("sample-c", distinct),
        ))
        self.assertEqual(profile["sample_count"], 3)
        self.assertEqual(profile["unique_structure_count"], 2)
        self.assertEqual(profile["duplicate_sample_count"], 2)
        self.assertEqual(profile["duplicate_structure_groups"][0]["sample_ids"], ["sample-a", "sample-b"])


if __name__ == "__main__":
    unittest.main()
