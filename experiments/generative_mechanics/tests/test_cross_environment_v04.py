from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.cross_environment_v04 import (
    PUBLIC_INITIAL_FIELDS,
    PublicFieldContext,
    QUARTET_ENVIRONMENTS,
    REGISTERED_CONTEXTS,
    context_panel_digest,
    evaluate_cross_environment_differentiation,
    evaluate_cross_environment_panel,
    public_field_coverage,
)
from experiments.generative_mechanics.baseline_v02 import validate_matched_direct_outcome
from experiments.generative_mechanics.free_invention import FreeInventionSample
from experiments.generative_mechanics.generation import DirectEffectSpec, Provenance
from experiments.generative_mechanics.spec import validate_skill
from experiments.generative_mechanics.substrate import SUBSTRATE_SYSTEM_LAWS


PROVENANCE = Provenance("test", "fixture", 1, "0" * 64, "fixture")


def sample(mechanic, baseline: str) -> FreeInventionSample:
    return FreeInventionSample(
        f"test.{baseline}", baseline, 1, 0, "synthetic", PROVENANCE,
        mechanic, {},
    )


def fire_candidate():
    return validate_skill({
        "id": "environmental_flame",
        "name": "Environmental Flame",
        "target_scope": "zone",
        "effects": [{"field": "fire_intensity", "delta": 0.8}],
        "duration": 0,
        "periodic": None,
        "trigger_conditions": [],
        "resource_cost": 1,
        "charges": 1,
        "slot_cost": 1,
    })


def triggered_fire_candidate():
    raw = {
        "id": "threshold_flame",
        "name": "Threshold Flame",
        "target_scope": "zone",
        "effects": [{"field": "fire_intensity", "delta": 0.8}],
        "duration": 0,
        "periodic": None,
        "trigger_conditions": [{"field": "temperature", "op": "gt", "value": 0.7}],
        "resource_cost": 1,
        "charges": 1,
        "slot_cost": 1,
    }
    return validate_skill(raw)


class CrossEnvironmentDifferentiationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world_result = evaluate_cross_environment_differentiation(
            sample(fire_candidate(), "world_substrate")
        )
        cls.world_report = cls.world_result.to_dict()

    def test_quartet_is_matched_on_public_state_and_varies_hidden_material(self):
        effects = self.world_result.environment_effects
        self.assertEqual(
            {tuple(sorted(item.public_initial_fields.items())) for item in effects},
            {tuple(sorted(PUBLIC_INITIAL_FIELDS.items()))},
        )
        self.assertEqual(len({
            tuple(sorted(item.hidden_initial_material.items())) for item in effects
        }), 4)
        self.assertEqual(len(self.world_result.pairwise_contrasts), 6)

    def test_world_substrate_candidate_differentiates(self):
        summary = self.world_report["summary"]
        self.assertTrue(summary["environmentally_differentiated"])
        self.assertGreater(
            summary["differentiating_state_coordinate_count"]
            + summary["differentiating_world_law_count"],
            0,
        )
        self.assertGreater(summary["distinct_net_signature_count"], 1)
        self.assertTrue(summary["differentiated_contexts"])

    def test_environment_order_does_not_change_result(self):
        reversed_result = evaluate_cross_environment_differentiation(
            sample(fire_candidate(), "world_substrate"),
            environments=reversed(QUARTET_ENVIRONMENTS),
        )
        self.assertEqual(self.world_report, reversed_result.to_dict())

    def test_repeated_evaluation_is_deterministic(self):
        repeated = evaluate_cross_environment_differentiation(
            sample(fire_candidate(), "world_substrate")
        )
        self.assertEqual(self.world_report, repeated.to_dict())

    def test_direct_isolation_and_background_subtraction_produce_zero(self):
        direct = DirectEffectSpec(
            "isolated_blast", "Isolated Blast", "damage", 0.75, 0.0, 1.0, 1, 1,
        )
        report = evaluate_cross_environment_differentiation(
            sample(direct, "isolated_direct_effect")
        ).to_dict()
        self.assertFalse(report["summary"]["environmentally_differentiated"])
        self.assertEqual(report["summary"]["mean_pairwise_state_l1"], 0.0)
        self.assertEqual(report["summary"]["mean_pairwise_world_law_l1"], 0.0)
        self.assertEqual(report["summary"]["distinct_net_signature_count"], 1)
        self.assertEqual(report["summary"]["differentiated_contexts"], [])
        # The four backgrounds have different hidden material, yet the paired
        # candidate effect is identical because background evolution is removed.
        effects = report["environment_effects"]
        self.assertEqual(len({
            tuple(sorted(item["hidden_initial_material"].items())) for item in effects
        }), 4)
        self.assertEqual(len({
            tuple(sorted(item["candidate_effect"].items())) for item in effects
        }), 1)
        self.assertGreater(len({
            tuple(sorted(item["candidate_absent_observation"].items())) for item in effects
        }), 1)

    def test_expression_matched_direct_outcome_is_also_zero(self):
        mechanic = validate_matched_direct_outcome({
            "id": "matched_blast",
            "name": "Matched Blast",
            "target_scope": "zone",
            "effects": [{"field": "damage", "delta": 0.75}],
            "duration": 0,
            "periodic": None,
            "trigger_conditions": [],
            "resource_cost": 1,
            "charges": 1,
            "slot_cost": 1,
        })
        report = evaluate_cross_environment_differentiation(
            sample(mechanic, "matched_direct_outcome")
        ).to_dict()
        self.assertFalse(report["summary"]["environmentally_differentiated"])
        self.assertEqual(report["summary"]["distinct_net_signature_count"], 1)

    def test_output_is_evidence_profile_not_creativity_total(self):
        report = self.world_report
        self.assertEqual(report["dimension"], "cross_environment_differentiation")
        self.assertEqual(report["design"]["active_build"], ["environmental_flame"])
        self.assertEqual(report["design"]["program"][0]["skill"], "environmental_flame")
        self.assertNotIn("creativity", report["summary"])
        self.assertNotIn("score", report["summary"])
        self.assertIn("difference-in-differences", report["estimand"])

    def test_quartet_rejects_missing_duplicate_or_unknown_environment(self):
        candidate = sample(fire_candidate(), "world_substrate")
        invalid = (
            QUARTET_ENVIRONMENTS[:-1],
            (*QUARTET_ENVIRONMENTS[:-1], QUARTET_ENVIRONMENTS[0]),
            (*QUARTET_ENVIRONMENTS[:-1], "unknown"),
        )
        for environments in invalid:
            with self.subTest(environments=environments):
                with self.assertRaisesRegex(ValueError, "frozen four-environment quartet"):
                    evaluate_cross_environment_differentiation(
                        candidate, environments=environments,
                    )


class StratifiedContextPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = sample(triggered_fire_candidate(), "world_substrate")
        cls.panel = evaluate_cross_environment_panel(cls.sample)
        cls.report = cls.panel.to_dict()

    def test_panel_is_preregistered_and_covers_low_neutral_high_per_field(self):
        self.assertGreaterEqual(len(REGISTERED_CONTEXTS), 6)
        self.assertEqual(self.report["panel"]["digest"], context_panel_digest())
        self.assertEqual(self.report["panel"]["context_count"], 6)
        coverage = public_field_coverage(REGISTERED_CONTEXTS)
        self.assertTrue(all(
            set(levels) == {"low", "neutral", "high"}
            for levels in coverage.values()
        ))
        self.assertEqual(self.report["panel"]["public_field_coverage"], coverage)

    def test_each_context_is_a_complete_matched_quartet(self):
        self.assertEqual(len(self.report["context_quartets"]), 6)
        for quartet in self.report["context_quartets"]:
            self.assertEqual(len(quartet["environment_effects"]), 4)
            expected = quartet["design"]["public_initial_fields"]
            self.assertEqual(
                {tuple(sorted(item["public_initial_fields"].items()))
                 for item in quartet["environment_effects"]},
                {tuple(sorted(expected.items()))},
            )

    def test_trigger_missed_at_neutral_but_activates_elsewhere_in_panel(self):
        quartets = {
            item["design"]["context_id"]: item
            for item in self.report["context_quartets"]
        }
        neutral = quartets["neutral"]
        self.assertTrue(all(
            not item["candidate_effect"]
            for item in neutral["environment_effects"]
        ))
        self.assertTrue(any(
            item["candidate_effect"]
            for context_id, quartet in quartets.items() if context_id != "neutral"
            for item in quartet["environment_effects"]
        ))

    def test_context_order_does_not_change_panel(self):
        reversed_panel = evaluate_cross_environment_panel(
            self.sample, contexts=reversed(REGISTERED_CONTEXTS),
        )
        self.assertEqual(self.report, reversed_panel.to_dict())

    def test_panel_reports_distribution_not_one_point_or_composite(self):
        distribution = self.report["distribution"]
        self.assertEqual(len(distribution["per_context"]), 6)
        self.assertNotIn("score", distribution)
        self.assertNotIn("creativity", distribution)
        self.assertNotIn("mean", distribution)
        self.assertEqual(
            {item["context_id"] for item in distribution["per_context"]},
            {context.id for context in REGISTERED_CONTEXTS},
        )

    def test_unregistered_context_or_manifest_digest_fails_closed(self):
        changed = list(REGISTERED_CONTEXTS)
        changed[0] = PublicFieldContext(
            changed[0].id,
            {**changed[0].public_initial_fields, "temperature": 0.16},
        )
        with self.assertRaisesRegex(ValueError, "preregistered"):
            evaluate_cross_environment_panel(self.sample, contexts=changed)

        manifest_path = (
            Path(__file__).parents[1] / "evaluation" / "protocol_v0.4.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["metrics"]["cross_environment_differentiation"]["context_panel"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            tampered = Path(directory) / "protocol.json"
            tampered.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                evaluate_cross_environment_panel(self.sample, manifest_path=tampered)

    def test_semantic_program_and_world_law_drift_fail_closed(self):
        manifest_path = (
            Path(__file__).parents[1] / "evaluation" / "protocol_v0.4.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        semantic = manifest["metrics"]["cross_environment_differentiation"]["context_panel"]["semantic_contract"]
        semantic["canonical_projection"]["program"][1]["repeats"] = 9
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            tampered_manifest = directory / "protocol.json"
            tampered_manifest.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "projection mismatch"):
                evaluate_cross_environment_panel(
                    self.sample, manifest_path=tampered_manifest,
                )

            world_laws = Path(__file__).parents[1] / "substrate" / "world_laws.json"
            tampered_laws = directory / "world_laws.json"
            tampered_laws.write_bytes(world_laws.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "projection mismatch"):
                evaluate_cross_environment_panel(
                    self.sample, world_laws_path=tampered_laws,
                )

    def test_environment_asset_and_system_law_drift_fail_closed(self):
        environments = Path(__file__).parents[1] / "environments"
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for environment in QUARTET_ENVIRONMENTS:
                source = environments / f"{environment}.json"
                (directory / source.name).write_bytes(source.read_bytes())

            mine_path = directory / "mine.json"
            mine = json.loads(mine_path.read_text(encoding="utf-8"))
            mine["entities"][1]["components"]["material"]["fuel"] += 0.01
            mine_path.write_text(json.dumps(mine), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "projection mismatch"):
                evaluate_cross_environment_panel(
                    self.sample, environments_dir=directory,
                )

        changed_laws = json.loads(json.dumps(SUBSTRATE_SYSTEM_LAWS))
        changed_laws[0]["priority"] += 1
        with self.assertRaisesRegex(ValueError, "projection mismatch"):
            evaluate_cross_environment_panel(
                self.sample, substrate_system_laws=changed_laws,
            )


if __name__ == "__main__":
    unittest.main()
