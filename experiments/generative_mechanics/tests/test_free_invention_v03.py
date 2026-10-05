from __future__ import annotations

import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

from experiments.generative_mechanics.cli import main as cli_main
from experiments.generative_mechanics.compiler import canonical_json
from experiments.generative_mechanics.free_invention import (
    BASELINES,
    EVALUATION_DIMENSIONS,
    PROTOCOL_VERSION,
    build_request_rows,
    compile_sample,
    evaluate_free_invention_sample,
    ingest_jsonl,
    validate_envelope,
)


def mechanic_for(baseline: str) -> dict:
    common = {
        "id": f"free_{baseline[:12]}",
        "name": "Free Mechanic",
        "resource_cost": 13.0,
        "charges": 3,
        "slot_cost": 1,
    }
    if baseline == "isolated_direct_effect":
        return {
            **common,
            "effect_kind": "damage",
            "magnitude": 0.37,
            "duration": 0.0,
        }
    return {
        **common,
        "target_scope": "zone",
        "effects": [{
            "field": "wetness" if baseline == "world_substrate" else "debuff",
            "delta": 0.37,
        }],
        "duration": 0.0,
        "periodic": {"interval": 4.0, "repeats": 2},
        "trigger_conditions": [{"field": "temperature", "op": "gte", "value": 0.2}],
    }


def envelope_for(row: dict) -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "sample_id": row["sample_id"],
        "sample_nonce": row["sample_nonce"],
        "baseline": row["baseline"],
        "request_coordinates": row["request_coordinates"],
        "source_kind": "model_response",
        "provenance": {
            "provider": "test-provider",
            "model": "test-model",
            "prompt_sha256": row["prompt_sha256"],
            "seed": row["seed"],
            "raw_id": f"raw-{row['sample_id']}",
        },
        "response": {"mechanic": mechanic_for(row["baseline"])},
    }


class FreeInventionRequestTests(unittest.TestCase):
    def test_balanced_unique_requests_are_reproducible(self):
        rows = build_request_rows(77, 40)
        self.assertEqual(rows, build_request_rows(77, 40))
        self.assertEqual(len(rows), 120)
        self.assertEqual({row["baseline"] for row in rows}, set(BASELINES))
        for field in ("sample_id", "sample_nonce", "seed", "prompt_sha256", "prompt"):
            self.assertEqual(len({row[field] for row in rows}), 120)
        for baseline in BASELINES:
            self.assertEqual(sum(row["baseline"] == baseline for row in rows), 40)

    def test_prompt_omits_controlled_track_cues_and_private_state(self):
        for row in build_request_rows(per_baseline=1):
            prompt = row["prompt"].lower()
            for forbidden in (
                "target power", "calibration_examples",
                "calibration examples", "deterministic controller", "oracle",
                "held_out", "industrial_yard", "fragile_bridge", '"entities"',
            ):
                self.assertNotIn(forbidden, prompt)
            self.assertIsNone(re.search(r"\b(low|mid|high)\b", prompt))
            for channel in (
                "temperature", "wetness", "electric_field", "fire_intensity",
                "sound_level", "ground_stability", "water_level", "visibility",
            ):
                self.assertIn(channel, prompt)
            for dimension in EVALUATION_DIMENSIONS:
                self.assertNotIn(dimension, prompt)

    def test_cli_has_independent_generation_command(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "free.jsonl"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = cli_main([
                    "generate-free-invention-requests", str(output),
                    "--seed", "9", "--per-baseline", "2",
                ])
            report = json.loads(stdout.getvalue())
            rows = output.read_text(encoding="utf-8").splitlines()
        self.assertEqual(result, 0)
        self.assertEqual(report["protocol"], PROTOCOL_VERSION)
        self.assertEqual(report["count"], 6)
        self.assertEqual(len(rows), 6)


class FreeInventionEnvelopeTests(unittest.TestCase):
    def test_all_baselines_reuse_validator_and_trusted_compiler(self):
        for row in build_request_rows(per_baseline=1):
            sample = validate_envelope(envelope_for(row))
            compiled = compile_sample(sample)
            self.assertTrue(compiled["laws"])

    def test_response_is_strict_and_has_no_score_field(self):
        row = build_request_rows(per_baseline=1)[0]
        envelope = envelope_for(row)
        envelope["response"]["declared_power"] = 50
        with self.assertRaisesRegex(ValueError, "strict fields"):
            validate_envelope(envelope)

    def test_prompt_hash_binds_nonce_and_identity(self):
        row = build_request_rows(per_baseline=1)[0]
        envelope = envelope_for(row)
        tampered = copy.deepcopy(envelope)
        tampered["sample_nonce"] += "x"
        result = ingest_jsonl([canonical_json(tampered), canonical_json(envelope)])
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(len(result.samples), 1)

    def test_envelope_identity_must_match_issued_request_coordinates(self):
        row = build_request_rows(master_seed=41, per_baseline=1)[0]
        envelope = envelope_for(row)
        for path, replacement in (
            (("sample_id",), "free.forged.0000.deadbeef00"),
            (("sample_nonce",), "0" * 32),
            (("provenance", "seed"), envelope["provenance"]["seed"] + 1),
            (("request_coordinates", "sample_index"), 9),
            (("request_coordinates", "master_seed"), 42),
        ):
            forged = copy.deepcopy(envelope)
            target = forged
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = replacement
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "request coordinates"):
                    validate_envelope(forged)

    def test_batch_ingestion_rejects_duplicate_identity_fields(self):
        rows = build_request_rows(per_baseline=2)
        first = envelope_for(rows[0])
        second = envelope_for(rows[1])
        second["sample_id"] = first["sample_id"]
        # Recomputed hash is intentionally omitted: either binding or duplicate
        # protection must reject the second envelope.
        result = ingest_jsonl([canonical_json(first), canonical_json(second)])
        self.assertEqual((len(result.samples), len(result.errors)), (1, 1))

    def test_cli_ingests_free_track_without_v02_model(self):
        row = build_request_rows(per_baseline=1)[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "responses.jsonl"
            path.write_text(canonical_json(envelope_for(row)) + "\n", encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = cli_main(["ingest-free-invention-responses", str(path)])
            report = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual((report["valid"], report["invalid"]), (1, 0))
        self.assertNotIn("target_band", report["samples"][0])
        self.assertNotIn("declared_power", report["samples"][0])


class FreeInventionEvaluationTests(unittest.TestCase):
    def test_static_evaluation_never_fabricates_dynamic_scores(self):
        row = next(
            item for item in build_request_rows(per_baseline=1)
            if item["baseline"] == "world_substrate"
        )
        result = evaluate_free_invention_sample(validate_envelope(envelope_for(row)))
        dimensions = result["dimensions"]
        self.assertEqual(set(dimensions), set(EVALUATION_DIMENSIONS))
        self.assertTrue(dimensions["structural_novelty"]["available"])
        for name in (
            "interaction_surface", "causal_depth",
            "cross_environment_differentiation", "downstream_consequences",
            "combinatorial_potential", "self_containment",
        ):
            self.assertEqual(dimensions[name]["available"], False)
            self.assertTrue(dimensions[name]["reason"])
            self.assertNotIn("value", dimensions[name])
        self.assertEqual(result["static_evidence"]["effect_fields"], ["wetness"])
        self.assertTrue(result["contract_safety"]["trusted_compiler_passed"])


if __name__ == "__main__":
    unittest.main()
