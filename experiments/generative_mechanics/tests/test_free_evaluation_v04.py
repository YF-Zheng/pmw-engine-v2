from __future__ import annotations

import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.cli import main as cli_main
from experiments.generative_mechanics.compiler import canonical_json
from experiments.generative_mechanics.free_evaluation_v04 import (
    PROTOCOL_VERSION,
    evaluate_free_invention_profile,
)
from experiments.generative_mechanics.free_invention import (
    build_request_rows,
    validate_envelope,
)


def _mechanic(baseline: str) -> dict:
    common = {
        "id": f"profile_{baseline[:12]}", "name": "Profile Mechanic",
        "resource_cost": 5.0, "charges": 3, "slot_cost": 1,
    }
    if baseline == "isolated_direct_effect":
        return {**common, "effect_kind": "damage", "magnitude": 0.4, "duration": 0.0}
    return {
        **common,
        "target_scope": "zone",
        "effects": [{"field": "electric_field" if baseline == "world_substrate" else "damage", "delta": 0.4}],
        "duration": 0.0,
        "periodic": None,
        "trigger_conditions": [],
    }


def _sample(baseline: str):
    row = next(item for item in build_request_rows(per_baseline=1) if item["baseline"] == baseline)
    envelope = {
        "protocol_version": row["protocol_version"],
        "sample_id": row["sample_id"],
        "sample_nonce": row["sample_nonce"],
        "baseline": baseline,
        "request_coordinates": row["request_coordinates"],
        "source_kind": "model_response",
        "provenance": {
            "provider": "profile-test", "model": "fixture",
            "prompt_sha256": row["prompt_sha256"], "seed": row["seed"],
            "raw_id": f"raw-{baseline}",
        },
        "response": {"mechanic": _mechanic(baseline)},
    }
    return validate_envelope(envelope)


def _envelope(baseline: str) -> dict:
    row = next(item for item in build_request_rows(per_baseline=1) if item["baseline"] == baseline)
    return {
        "protocol_version": row["protocol_version"],
        "sample_id": row["sample_id"],
        "sample_nonce": row["sample_nonce"],
        "baseline": baseline,
        "request_coordinates": row["request_coordinates"],
        "source_kind": "model_response",
        "provenance": {
            "provider": "profile-test", "model": "fixture",
            "prompt_sha256": row["prompt_sha256"], "seed": row["seed"],
            "raw_id": f"raw-{baseline}",
        },
        "response": {"mechanic": _mechanic(baseline)},
    }


def _walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


class FreeEvaluationV04Tests(unittest.TestCase):
    def test_world_substrate_profile_integrates_three_evidence_dimensions(self):
        profile = evaluate_free_invention_profile(_sample("world_substrate"))
        self.assertEqual(profile["protocol_version"], PROTOCOL_VERSION)
        self.assertEqual(
            set(profile["dimensions"]),
            {"downstream_causal_depth", "cross_environment_differentiation", "structural_novelty"},
        )
        self.assertEqual(profile["eligible_tracks"], ["representation_interface", "model_invention"])
        self.assertTrue(all(item["available"] for item in profile["dimensions"].values()))
        causal = profile["dimensions"]["downstream_causal_depth"]
        self.assertEqual(causal["registered_arm_count"], 24)
        self.assertEqual(causal["total_arm_count"], 24)
        self.assertEqual(causal["activated_arm_count"], 24)
        self.assertEqual(causal["activation_rate"], 1.0)
        self.assertEqual(
            profile["dimensions"]["cross_environment_differentiation"]["panel"]["context_count"],
            6,
        )

    def test_direct_interface_is_not_mislabelled_as_model_invention(self):
        profile = evaluate_free_invention_profile(_sample("isolated_direct_effect"))
        self.assertEqual(profile["eligible_tracks"], ["representation_interface"])
        self.assertFalse(profile["dimensions"]["structural_novelty"]["available"])
        causal = profile["dimensions"]["downstream_causal_depth"]
        self.assertEqual(causal["conditional_on_activation"]["maximum_depth"], 0)
        cross_environment = profile["dimensions"]["cross_environment_differentiation"]
        self.assertEqual(cross_environment["distribution"]["differentiated_context_count"], 0)
        self.assertTrue(all(
            not item["environmentally_differentiated"]
            for item in cross_environment["distribution"]["per_context"]
        ))
        self.assertIn("not model failure", profile["interpretation"]["representation_interface"])

    def test_never_activated_mechanic_is_excluded_from_depth_statistics(self):
        envelope = _envelope("world_substrate")
        envelope["response"]["mechanic"]["trigger_conditions"] = [
            {"field": "temperature", "op": "gt", "value": 0.9},
        ]
        profile = evaluate_free_invention_profile(validate_envelope(envelope))
        causal = profile["dimensions"]["downstream_causal_depth"]
        self.assertEqual(causal["total_arm_count"], 24)
        self.assertEqual(causal["activated_arm_count"], 0)
        self.assertEqual(causal["activation_rate"], 0.0)
        self.assertFalse(causal["conditional_on_activation"]["available"])
        self.assertEqual(causal["conditional_on_activation"]["depth_distribution"], [])
        self.assertIsNone(causal["conditional_on_activation"]["mean_depth"])
        self.assertIsNone(causal["conditional_on_activation"]["maximum_depth"])
        self.assertTrue(all(not arm["candidate_activated"] for arm in causal["arms"]))
        self.assertTrue(all(arm["depth"] is None for arm in causal["arms"]))

    def test_profile_has_no_score_or_ranking_field(self):
        profile = evaluate_free_invention_profile(_sample("world_substrate"))
        forbidden = {
            "creativity_score", "composite_creativity_score", "total_score",
            "ranking", "rank",
        }
        self.assertFalse(forbidden & set(_walk_keys(profile)))
        self.assertEqual(profile["interpretation"]["aggregation_policy"], "profile_only")

    def test_profile_is_deterministic(self):
        sample = _sample("world_substrate")
        self.assertEqual(
            evaluate_free_invention_profile(sample),
            evaluate_free_invention_profile(copy.deepcopy(sample)),
        )

    def test_cli_writes_profile_and_isolates_bad_ingestion(self):
        valid = _envelope("world_substrate")
        invalid = copy.deepcopy(_envelope("isolated_direct_effect"))
        invalid["sample_nonce"] += "tampered"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "responses.jsonl"
            output = Path(directory) / "profiles.json"
            source.write_text(
                canonical_json(valid) + "\n" + canonical_json(invalid) + "\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = cli_main(["evaluate-free-invention", str(source), str(output)])
            report = json.loads(stdout.getvalue())
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(status, 2)
        self.assertEqual((report["profiles"], report["ingestion_errors"]), (1, 1))
        self.assertEqual(len(payload["profiles"]), 1)
        self.assertEqual(len(payload["ingestion_errors"]), 1)
        self.assertEqual(payload["evaluation_errors"], [])


if __name__ == "__main__":
    unittest.main()
