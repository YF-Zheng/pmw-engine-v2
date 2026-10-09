from __future__ import annotations

import json
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

from experiments.generative_mechanics.formal_experiment import (
    NON_FORMAL_TEST_RUN,
    PRIMARY_ENDPOINTS,
    SECONDARY_ENDPOINTS,
    FormalExperimentError,
    analyze_free_invention,
    apply_blinding,
    build_dry_manifest_example,
    build_formal_request_manifest,
    build_raw_data_manifest,
    create_blinding_mapping,
    deterministic_collection_schedule,
    require_collection_ready,
    retry_action,
    seal_blinding_mapping,
    unseal_blinding_mapping,
    validate_formal_dataset,
    validate_formal_lineage,
    validate_raw_data_manifest,
    validate_request_manifest,
    validate_transport_attempts,
    write_analysis_artifacts,
)
from experiments.generative_mechanics.pilots.free_v05_dev.pilot import build_canonical_requests
from experiments.generative_mechanics.formal_cli import main as formal_cli_main


DECISIONS = {
    "model_matrix": [
        "provider/model-a-v1", "provider/model-b-v2",
        "provider/model-c-v3", "provider/model-d-v4",
    ],
    "samples_per_model": 100,
    "inference_budget_policy": "matched_inference_budget",
}
DEV_EXCLUSIONS = {"dev-sample", "dev-request", "dev-nonce", "12345"}
PROVIDER_CONFIGS = {
    model: {"model_id": model, "reasoning_effort": "matched", "max_output_tokens": 4096}
    for model in DECISIONS["model_matrix"]
}


def manifest(**kwargs):
    return build_formal_request_manifest(
        DECISIONS,
        formal_experiment_id=kwargs.pop("formal_experiment_id", "formal-1"),
        collection_order_seed=kwargs.pop("collection_order_seed", 123),
        master_seed=kwargs.pop("master_seed", 81073),
        dev_exclusion_registry=kwargs.pop("dev_exclusion_registry", DEV_EXCLUSIONS),
        provider_request_configs=kwargs.pop("provider_request_configs", PROVIDER_CONFIGS),
        **kwargs,
    )


def fixture_row(index: int, model: str, *, valid: bool = True, kind: str = "fixture") -> dict:
    contexts = [
        {
            "outcome_differentiated": context % 2 == 0,
            "causal_path_differentiated": (index + context) % 3 == 0,
        }
        for context in range(6)
    ]
    profile = {
        "activation": {"activation_rate": 0.5},
        "dynamic_reach": {
            "activation_rate": 0.5,
            "registered_arm_count": 24,
            "conditional_on_activation": {
                "realized_dependency_depth_distribution": [1, 3],
                "necessity_backed_depth_distribution": [1, 2],
                "depth_gap_distribution": [0, 1],
            },
        },
        "environmental_behavior": {"context_count": 6, "contexts": contexts},
        "behavioral_inertness": {"behaviorally_inert": False},
        "structural_evidence": {
            "exact_match": False,
            "near_copy": False,
            "recombination": {"recombination_detected": False},
            "semantic_structure": {"fingerprint": f"semantic-{index % 2}"},
            "abstract_topology": {"fingerprint": f"abstract-{index % 3}"},
        },
    }
    return {
        "dataset_kind": kind,
        "formal_sample_id": f"sample-{model}-{index}",
        "model_id": model,
        "base_sample_index": index,
        "schema_valid": valid,
        "compile_valid": valid,
        "execution_valid": valid,
        "profile": profile if valid else None,
    }


class OwnerGateAndManifestTests(unittest.TestCase):
    def test_unresolved_owner_gate_refuses_manifest_and_collection(self):
        unresolved = {**DECISIONS, "samples_per_model": None}
        with self.assertRaisesRegex(FormalExperimentError, "owner gate unresolved"):
            build_formal_request_manifest(
                unresolved, formal_experiment_id="formal-1", collection_order_seed=7,
                master_seed=3, dev_exclusion_registry=DEV_EXCLUSIONS,
                provider_request_configs=PROVIDER_CONFIGS,
            )
        registry = {
            "formal_collection_started": False,
            "preregistration_frozen": False,
            "free_invention": unresolved,
        }
        with self.assertRaises(FormalExperimentError):
            require_collection_ready(registry, manifest_bytes=b"x", schedule_bytes=b"y")

    def test_dry_manifest_is_placeholder_formal_not_sent(self):
        rows = build_dry_manifest_example()
        self.assertTrue(rows)
        self.assertTrue(all(row["dataset_kind"] == "synthetic_mock" for row in rows))
        self.assertTrue(all(row["collection_status"] == "NOT_SENT" for row in rows))
        self.assertTrue(all(row["model_id"].startswith("PLACEHOLDER_MODEL_") for row in rows))
        self.assertTrue(all(row["dry_manifest_example"] for row in rows))

    def test_checked_in_dry_manifest_exactly_matches_generator(self):
        path = Path(__file__).parents[1] / "formal_preregistration" / "DRY_MANIFEST_EXAMPLE.jsonl"
        checked_in = tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
        self.assertEqual(checked_in, build_dry_manifest_example())

    def test_offline_cli_generates_only_synthetic_dry_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dry.jsonl"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(formal_cli_main([
                    "generate-dry-manifest", "--output", str(output),
                ]), 0)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(rows)
            self.assertTrue(all(row["dataset_kind"] == "synthetic_mock" for row in rows))
            self.assertIn("SYNTHETIC_MOCK_ONLY", stdout.getvalue())

    def test_formal_outer_ids_unique_but_v03_prompt_exactly_matched_by_block(self):
        rows = manifest()
        self.assertEqual(validate_request_manifest(rows)["model_visible_prompt_matching"], "EXACT")
        for field in ("formal_sample_id", "request_id", "full_request_sha256"):
            self.assertEqual(len({row[field] for row in rows}), len(rows))
        for block in range(DECISIONS["samples_per_model"]):
            matched = [row for row in rows if row["base_sample_index"] == block]
            self.assertEqual(len({row["visible_prompt_sha256"] for row in matched}), 1)
            self.assertEqual(len({row["generation_sample_id"] for row in matched}), 1)
            self.assertEqual(len({row["nonce"] for row in matched}), 1)
            self.assertEqual(len({row["canonical_seed"] for row in matched}), 1)
            self.assertEqual(len({row["full_request_sha256"] for row in matched}), len(matched))
        self.assertEqual(len({row["generation_sample_id"] for row in rows}), 100)
        self.assertEqual(len({row["sample_id"] for row in rows}), 100)
        self.assertEqual(len({row["nonce"] for row in rows}), 100)
        self.assertEqual(len({row["canonical_seed"] for row in rows}), 100)

    def test_manifest_rejects_missing_model_or_base_block_and_tampered_request(self):
        rows = list(manifest())
        without_model = [dict(row) for row in rows if row["model_id"] != DECISIONS["model_matrix"][0]]
        for sequence, row in enumerate(without_model):
            row["collection_sequence"] = sequence
        with self.assertRaisesRegex(FormalExperimentError, "selected model matrix"):
            validate_request_manifest(without_model)

        without_block = [dict(row) for row in rows if row["base_sample_index"] != 99]
        with self.assertRaisesRegex(FormalExperimentError, "blocks are incomplete"):
            validate_request_manifest(without_block)

        tampered = [dict(row) for row in rows]
        tampered[0]["canonical_full_request"] = {
            **tampered[0]["canonical_full_request"], "visible_prompt": "changed",
        }
        with self.assertRaisesRegex(FormalExperimentError, "hash mismatch"):
            validate_request_manifest(tampered)

    def test_formal_and_dev_identities_are_disjoint(self):
        pilot = build_canonical_requests()
        excluded = {
            value
            for row in pilot
            for value in (row["sample_id"], row["request_id"], row["sample_nonce"], row["canonical_seed"])
        }
        rows = manifest(collection_order_seed=9, dev_exclusion_registry=excluded)
        formal = {
            value
            for row in rows
            for value in (row["formal_sample_id"], row["request_id"], row["generation_sample_id"], row["nonce"], row["canonical_seed"])
        }
        self.assertTrue(formal.isdisjoint(excluded))

    def test_schedule_is_deterministic_block_interleaved(self):
        first = deterministic_collection_schedule(DECISIONS["model_matrix"], 20, 71)
        second = deterministic_collection_schedule(DECISIONS["model_matrix"], 20, 71)
        self.assertEqual(first, second)
        self.assertNotEqual(first, deterministic_collection_schedule(DECISIONS["model_matrix"], 20, 72))
        orders = []
        for block in range(20):
            block_rows = [row for row in first if row["base_sample_index"] == block]
            self.assertEqual({row["model_id"] for row in block_rows}, set(DECISIONS["model_matrix"]))
            orders.append(tuple(row["model_id"] for row in block_rows))
        self.assertGreater(len(set(orders)), 1)


class IsolationRetryAndRawTests(unittest.TestCase):
    def test_pilot_fixture_and_adversarial_rows_cannot_enter_formal(self):
        for kind in ("dev_pilot", "fixture", "adversarial", "calibration"):
            with self.subTest(kind=kind):
                with self.assertRaises(FormalExperimentError):
                    validate_formal_dataset([{"dataset_kind": kind}])
                with self.assertRaises(FormalExperimentError):
                    analyze_free_invention([fixture_row(0, "m", kind=kind)])

    def test_transport_retry_same_request_max_three_content_never_retry(self):
        self.assertEqual(retry_action("transport_failure", 1), "RETRY_SAME_REQUEST")
        self.assertEqual(retry_action("transport_failure", 2), "RETRY_SAME_REQUEST")
        self.assertEqual(retry_action("transport_failure", 3), "STOP_TRANSPORT_EXHAUSTED")
        for failure in ("malformed_json", "schema_invalid", "safety_refusal", "valid"):
            self.assertEqual(retry_action(failure, 1), "STOP_RETAIN_FIRST_CONTENT")
        attempts = [
            {"attempt": n, "request_id": "r", "full_request_sha256": "h", "failure_class": "transport_failure"}
            for n in range(1, 4)
        ]
        self.assertEqual(validate_transport_attempts(attempts)["attempt_count"], 3)
        changed = [dict(row) for row in attempts]
        changed[1]["full_request_sha256"] = "changed"
        with self.assertRaisesRegex(FormalExperimentError, "changed the exact request"):
            validate_transport_attempts(changed)
        content_retry = [dict(attempts[0]), {**attempts[1], "failure_class": "malformed_json"}, attempts[2]]
        with self.assertRaisesRegex(FormalExperimentError, "cannot be retried"):
            validate_transport_attempts(content_retry)

    def test_raw_artifacts_are_hash_linked_and_tamper_evident(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [
                "raw_requests/r.json", "raw_provider_responses/r.json",
                "parsed/r.json", "skills/r.json", "compiled/r.json",
                "traces/r.json", "profiles/r.json", "analysis/r.json",
            ]
            for index, relative in enumerate(paths):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"stage": index}) + "\n", encoding="utf-8")
            manifest = build_raw_data_manifest(root, paths[:2])
            self.assertEqual(validate_raw_data_manifest(root, manifest)["file_count"], 2)
            stages = (
                "raw_request", "raw_provider_response", "parsed_response", "skill_spec",
                "compiled_mechanic", "execution_trace", "profile", "analysis_row",
            )
            lineage_map = {}
            parent = None
            for stage, relative in zip(stages, paths):
                import hashlib
                digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
                lineage_map[stage] = {"path": relative, "sha256": digest}
                if parent is not None:
                    lineage_map[stage]["parent_sha256"] = parent
                parent = digest
            lineage = [{
                "dataset_kind": "formal", "request_id": "r",
                "lineage": lineage_map,
                "paper_statistic_ids": ["table1.validity"],
            }]
            self.assertEqual(validate_formal_lineage(lineage, manifest, artifact_root=root)["mechanism_count"], 1)
            raw = root / "raw_provider_responses" / "r.json"
            raw.write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(FormalExperimentError):
                validate_raw_data_manifest(root, manifest)


class BlindingAndAnalysisTests(unittest.TestCase):
    def test_blinded_mapping_round_trip_and_tamper_detection(self):
        mapping = create_blinding_mapping(["model-x", "model-y"], 17)
        blinded = apply_blinding([{"model_id": "model-x", "value": 1}], mapping)
        self.assertNotIn("model_id", blinded[0])
        self.assertTrue(blinded[0]["model_blind_label"].startswith("Model "))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "BLINDING_MAPPING.sealed.json"
            seal_blinding_mapping(path, mapping, seal_key=b"owner-secret")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(unseal_blinding_mapping(path, seal_key=b"owner-secret"), mapping)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["mapping"]["model-x"] = "Model Z"
            path.write_text(json.dumps(envelope), encoding="utf-8")
            with self.assertRaises(FormalExperimentError):
                unseal_blinding_mapping(path, seal_key=b"owner-secret")

    def test_blinded_fixture_rows_are_directly_analyzable(self):
        rows = [fixture_row(index, model) for model in ("model-x", "model-y") for index in range(2)]
        mapping = create_blinding_mapping(["model-x", "model-y"], 11)
        blinded = apply_blinding(rows, mapping)
        analysis = analyze_free_invention(
            blinded, non_formal_test_run=True,
            bootstrap_replicates=30, permutation_replicates=50,
        )
        self.assertEqual(
            {row["model_id"] for row in analysis["model_profiles"]},
            set(mapping.values()),
        )

    def test_mechanism_is_unit_invalid_dynamic_is_na_and_no_total_score(self):
        rows = [fixture_row(0, "m"), fixture_row(1, "m", valid=False)]
        analysis = analyze_free_invention(
            rows, non_formal_test_run=True,
            bootstrap_replicates=30, permutation_replicates=50,
        )
        self.assertEqual(analysis["run_status"], NON_FORMAL_TEST_RUN)
        profile = analysis["model_profiles"][0]
        self.assertEqual(profile["requested_mechanism_count"], 2)
        self.assertEqual(profile["end_to_end_executable_validity"], 0.5)
        invalid = analysis["secondary_results"]["mechanism_rows"][1]
        for field in (
            "activation_rate", "median_realized_dependency_depth",
            "outcome_differentiation_rate", "abstract_fingerprint", "exact_match",
        ):
            self.assertIsNone(invalid[field])
        self.assertEqual(analysis["primary_results"]["analysis_unit"], "generated_mechanism")
        self.assertNotEqual(profile["requested_mechanism_count"], 24)
        serialized = json.dumps(analysis)
        self.assertNotIn("creativity_score", serialized)
        self.assertNotIn("creativity_total", serialized)

    def test_endpoint_roles_locked_and_fixture_outputs_reproducible(self):
        self.assertNotIn("exact_match", PRIMARY_ENDPOINTS)
        self.assertNotIn("near_copy", PRIMARY_ENDPOINTS)
        self.assertNotIn("recombination", PRIMARY_ENDPOINTS)
        self.assertIn("exact_match", SECONDARY_ENDPOINTS)
        self.assertIn("near_copy", SECONDARY_ENDPOINTS)
        self.assertIn("recombination", SECONDARY_ENDPOINTS)
        rows = [fixture_row(i, model) for model in ("m1", "m2") for i in range(3)]
        first = analyze_free_invention(
            rows, non_formal_test_run=True,
            bootstrap_replicates=30, permutation_replicates=50,
        )
        second = analyze_free_invention(
            rows, non_formal_test_run=True,
            bootstrap_replicates=30, permutation_replicates=50,
        )
        self.assertEqual(first, second)
        self.assertEqual(first["statistical_tests"]["status"], "NON_FORMAL_ESTIMATES")
        self.assertTrue(first["statistical_tests"]["primary_omnibus"])
        self.assertTrue(all(
            "holm_adjusted_p_value" in row and "pairwise_gate_open" in row
            for row in first["statistical_tests"]["primary_omnibus"]
        ))
        self.assertTrue(all(
            row["confirmatory_status"] in {"OPENED", "NOT_OPENED_BY_OMNIBUS_GATE"}
            for row in first["statistical_tests"]["primary_pairwise"]
        ))
        self.assertTrue(all(
            row["permutation_unit"] == "labels_within_base_sample_index_block"
            for row in first["statistical_tests"]["secondary_exploratory"]
            if row["status"] == "ESTIMATED"
        ))
        self.assertTrue(all(
            row["analysis_unit"] == "generated_mechanism"
            for row in first["statistical_tests"]["primary_omnibus"] if row["status"] == "ESTIMATED"
        ))
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            left_hashes = write_analysis_artifacts(left, first)
            right_hashes = write_analysis_artifacts(right, second)
            self.assertEqual(left_hashes, right_hashes)
            expected = {
                "primary_results.json", "secondary_results.json", "model_profiles.json",
                "model_profiles.csv", "statistical_tests.json",
                "figure_data/capability_profiles.json", "table_data/table_1.json",
            }
            self.assertEqual(set(left_hashes), expected)
            for relative in expected:
                self.assertIn(NON_FORMAL_TEST_RUN, (Path(left) / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
