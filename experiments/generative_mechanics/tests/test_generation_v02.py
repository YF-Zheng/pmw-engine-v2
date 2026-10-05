from __future__ import annotations

import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from experiments.generative_mechanics.baseline_v02 import (
    compile_matched_direct_outcome,
    semantic_write_targets,
    validate_matched_direct_outcome,
)
from experiments.generative_mechanics.compiler import canonical_json
from experiments.generative_mechanics.cli import main as cli_main
from experiments.generative_mechanics.diversity import (
    diversity_report,
    parametric_fingerprint,
    structural_fingerprint,
)
from experiments.generative_mechanics.generation import (
    _load_calibration_artifact_v02,
    LEGACY_PROTOCOL_VERSION_V02,
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_V02,
    PROTOCOL_DISPLAY_NAME_V02,
    PROTOCOL_TRACK_V02,
    build_request_rows_v02,
    calibration_examples_v02,
    compile_direct_effect,
    derive_sample_identity,
    generate_fixture_envelopes,
    ingest_jsonl,
    legacy_prompt_hash_v02,
    legacy_prompt_request_v02,
    prepare_direct_world,
    prompt_request_v02,
    prompt_hash_v02,
    public_rule_summary,
    validate_direct_effect,
    validate_envelope,
)
from experiments.generative_mechanics.compiler import compile_skill
from experiments.generative_mechanics.spec import validate_skill
from experiments.generative_mechanics.generators.archive import build_deterministic_archive
from experiments.generative_mechanics.power_v02 import evaluate_power
from experiments.generative_mechanics.scenario import load_scenario


def matched_raw() -> dict:
    return {
        "id": "matched_pulse",
        "name": "Matched Pulse",
        "target_scope": "zone",
        "effects": [
            {"field": "damage", "delta": 0.4},
            {"field": "debuff", "delta": 0.2},
        ],
        "duration": 0.0,
        "periodic": {"interval": 5.0, "repeats": 3},
        "trigger_conditions": [{"field": "wetness", "op": "gte", "value": 0.4}],
        "resource_cost": 18.0,
        "charges": 3,
        "slot_cost": 2,
    }


class GenerationV02IdentityTests(unittest.TestCase):
    @staticmethod
    def _artifact_raw() -> dict:
        path = Path(__file__).parents[1] / "generators" / "calibration_examples_v0.2-controlled.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _assert_mutated_artifact_rejected(self, artifact: dict, message: str) -> None:
        content = canonical_json(artifact).encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            path.write_bytes(content)
            with self.assertRaisesRegex(ValueError, message):
                _load_calibration_artifact_v02(
                    path, expected_sha256=hashlib.sha256(content).hexdigest(),
                )

    def test_cli_defaults_new_collection_to_v02(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "requests.jsonl"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(cli_main([
                    "generate-requests", str(output), "--per-cell", "1",
                ]), 0)
            report = json.loads(stdout.getvalue())
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(report["protocol"], PROTOCOL_VERSION_V02)
        self.assertEqual(report["count"], 9)
        self.assertEqual({row["protocol_version"] for row in rows}, {PROTOCOL_VERSION_V02})

    def test_forty_requests_in_each_cell_have_unique_identity_and_prompt(self):
        rows = build_request_rows_v02(per_cell=40)
        cells: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            cells.setdefault((row["baseline"], row["target_band"]), []).append(row)
        self.assertEqual(len(cells), 9)
        for cell in cells.values():
            self.assertEqual(len({row["sample_id"] for row in cell}), 40)
            self.assertEqual(len({row["sample_nonce"] for row in cell}), 40)
            self.assertEqual(len({row["seed"] for row in cell}), 40)
            self.assertEqual(len({row["prompt_sha256"] for row in cell}), 40)
            for row in cell:
                self.assertIn(row["sample_id"], row["prompt"])
                self.assertIn(row["sample_nonce"], row["prompt"])
                self.assertIn(str(row["seed"]), row["prompt"])

    def test_request_generation_is_deterministic(self):
        self.assertEqual(build_request_rows_v02(99, 3), build_request_rows_v02(99, 3))
        self.assertNotEqual(build_request_rows_v02(99, 1), build_request_rows_v02(100, 1))

    def test_prompt_has_public_semantics_rules_and_no_private_world_data(self):
        row = build_request_rows_v02(per_cell=1)[0]
        prompt = row["prompt"].lower()
        for channel in (
            "temperature", "wetness", "electric_field", "fire_intensity",
            "sound_level", "ground_stability", "water_level", "visibility",
        ):
            self.assertIn(channel, prompt)
        for forbidden in ("held_out", "oracle", "industrial_yard", "fragile_bridge", '"entities"'):
            self.assertNotIn(forbidden, prompt)
        summary = public_rule_summary()
        self.assertEqual(summary["schema"], "gm-public-rule-summary-v0.1")
        self.assertTrue(summary["rules"])
        self.assertTrue(all(set(rule) == {
            "rule", "events", "reads", "writes", "public_predicates",
            "public_mutations", "has_undisclosed_guards",
        } for rule in summary["rules"]))

    def test_controlled_track_keeps_compatible_machine_protocol_id(self):
        request = prompt_request_v02(
            "world_substrate", "Low", 1, "sample-id", "sample-nonce",
            master_seed=1, sample_index=0,
        )
        self.assertEqual(request["protocol_version"], "gm-generation-v0.2-controlled")
        self.assertEqual(request["protocol_display_name"], PROTOCOL_DISPLAY_NAME_V02)
        self.assertEqual(request["track"], PROTOCOL_TRACK_V02)
        self.assertEqual(PROTOCOL_DISPLAY_NAME_V02, "Protocol v0.2-Controlled")
        self.assertEqual(PROTOCOL_TRACK_V02, "controlled")

    def test_exactly_two_calibration_examples_per_baseline_band(self):
        examples = calibration_examples_v02()
        self.assertEqual(len(examples), 18)
        for baseline in (
            "isolated_direct_effect", "world_substrate", "matched_direct_outcome",
        ):
            selected = calibration_examples_v02(baseline)
            self.assertEqual(len(selected), 6)
            self.assertEqual({item["baseline"] for item in selected}, {baseline})
            for band in ("Low", "Mid", "High"):
                self.assertEqual(sum(item["target_band"] == band for item in selected), 2)
        for item in examples:
            provenance = item["provenance"]
            self.assertEqual(provenance["split"], "calibration")
            self.assertTrue(provenance["scenario_id"].startswith("calibration/"))
            self.assertEqual(provenance["scorer_interface"], "gm-authoritative-scorer-v0.1")
            self.assertTrue(provenance["score_rebuild_key"])

    def test_all_eighteen_scores_rebuild_through_matching_authoritative_path(self):
        root = Path(__file__).parents[1]
        scenarios = tuple(
            load_scenario(path)
            for path in sorted((root / "scenarios" / "calibration").glob("*.json"))
        )
        for item in calibration_examples_v02():
            baseline = item["baseline"]
            raw = item["mechanic"]
            if baseline == "isolated_direct_effect":
                mechanic = validate_direct_effect(raw)
                compiler, world_setup = compile_direct_effect, prepare_direct_world
            elif baseline == "world_substrate":
                mechanic = validate_skill(raw)
                compiler, world_setup = compile_skill, None
            else:
                mechanic = validate_matched_direct_outcome(raw)
                compiler, world_setup = compile_matched_direct_outcome, prepare_direct_world
            rebuilt = evaluate_power(
                scenarios, (mechanic.id,), split="calibration",
                catalog={mechanic.id: mechanic}, compile_mechanic=compiler,
                world_setup=world_setup,
            ).typical_power
            self.assertAlmostEqual(item["realized_score"], rebuilt)
            low, high = {"Low": (20, 30), "Mid": (40, 50), "High": (60, 70)}[item["target_band"]]
            self.assertLessEqual(low, rebuilt)
            self.assertLessEqual(rebuilt, high)

    def test_calibration_artifact_sha_is_manifest_bound(self):
        path = Path(__file__).parents[1] / "generators" / "calibration_examples_v0.2-controlled.json"
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            _load_calibration_artifact_v02(path, expected_sha256="0" * 64)

    def test_calibration_artifact_rejects_deleted_example(self):
        artifact = self._artifact_raw()
        artifact["examples"].pop()
        self._assert_mutated_artifact_rejected(artifact, "invalid controlled calibration artifact contract")

    def test_calibration_artifact_rejects_duplicate_example_id(self):
        artifact = self._artifact_raw()
        artifact["examples"][1]["example_id"] = artifact["examples"][0]["example_id"]
        self._assert_mutated_artifact_rejected(artifact, "example_id is invalid or duplicate")

    def test_calibration_artifact_rejects_out_of_band_score(self):
        artifact = self._artifact_raw()
        artifact["examples"][0]["realized_score"] = 99.0
        self._assert_mutated_artifact_rejected(artifact, "outside its target band")

    def test_calibration_artifact_rejects_wrong_mechanic_schema(self):
        artifact = self._artifact_raw()
        del artifact["examples"][0]["mechanic"]["duration"]
        self._assert_mutated_artifact_rejected(artifact, "invalid controlled calibration mechanic")

    def test_prompt_discloses_only_matching_baseline_examples(self):
        validators = {
            "isolated_direct_effect": validate_direct_effect,
            "world_substrate": validate_skill,
            "matched_direct_outcome": validate_matched_direct_outcome,
        }
        all_examples = calibration_examples_v02()
        for baseline, validator in validators.items():
            request = prompt_request_v02(
                baseline, "Mid", 7, f"sample-{baseline}", "nonce",
                master_seed=7, sample_index=0,
            )
            disclosed = request["calibration_examples"]
            self.assertEqual(len(disclosed), 6)
            self.assertEqual({item["baseline"] for item in disclosed}, {baseline})
            self.assertEqual(
                {item["example_id"] for item in disclosed},
                {item["example_id"] for item in all_examples if item["baseline"] == baseline},
            )
            for item in disclosed:
                validator(item["mechanic"])
                self.assertEqual(item["provenance"]["split"], "calibration")

    def test_prompt_examples_never_reference_evaluation_or_oracle(self):
        for baseline in (
            "isolated_direct_effect", "world_substrate", "matched_direct_outcome",
        ):
            request = prompt_request_v02(
                baseline, "Low", 11, baseline, "nonce",
                master_seed=11, sample_index=0,
            )
            serialized = canonical_json(request["calibration_examples"]).lower()
            self.assertNotIn("evaluation", serialized)
            self.assertNotIn("oracle", serialized)
            self.assertEqual(serialized.count('"split":"calibration"'), 6)


class MatchedBaselineTests(unittest.TestCase):
    def test_matched_baseline_has_skill_like_expression_budget(self):
        spec = validate_matched_direct_outcome(matched_raw())
        self.assertEqual(len(spec.effects), 2)
        self.assertEqual(len(spec.trigger_conditions), 1)
        self.assertIsNotNone(spec.periodic)
        self.assertEqual((spec.resource_cost, spec.charges, spec.slot_cost), (18.0, 3, 2))
        compiled = compile_matched_direct_outcome(spec)
        self.assertEqual(len(compiled["laws"]), 4)  # activation plus three pulses

    def test_matched_baseline_semantic_writes_are_downstream_isolated(self):
        compiled = compile_matched_direct_outcome(validate_matched_direct_outcome(matched_raw()))
        targets = semantic_write_targets(compiled)
        allowed_bookkeeping = {"$actor.resource.energy", "$skill.skill.charges"}
        self.assertTrue(targets)
        self.assertTrue(all(target.startswith("$zone.direct_outcome.") or target in allowed_bookkeeping for target in targets))
        world_laws = json.loads(
            (Path(__file__).parents[1] / "substrate" / "world_laws.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("direct_outcome", canonical_json(world_laws))

    def test_duration_and_periodic_are_mutually_exclusive(self):
        raw = matched_raw()
        raw["duration"] = 3.0
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            validate_matched_direct_outcome(raw)


class ProtocolCompatibilityTests(unittest.TestCase):
    @staticmethod
    def _v02_envelope(protocol_version: str, prompt_sha256: str) -> dict:
        return {
            "protocol_version": protocol_version,
            "sample_id": "matched_direct_outcome.mid.0000.compat",
            "sample_nonce": "compat-nonce",
            "baseline": "matched_direct_outcome",
            "target_band": "Mid",
            "source_kind": "model_response",
            "provenance": {
                "provider": "test-provider", "model": "test-model",
                "prompt_sha256": prompt_sha256, "seed": 1234, "raw_id": "raw-compat",
            },
            "response": {"mechanic": matched_raw(), "declared_power": 45.0},
        }

    def test_v01_is_still_accepted_without_schema_rewrite(self):
        row = generate_fixture_envelopes(per_cell=1)[0]
        self.assertEqual(row["protocol_version"], PROTOCOL_VERSION)
        sample = validate_envelope(row)
        self.assertEqual(sample.sample_id, row["sample_id"])

    def test_v02_envelope_is_accepted_and_hash_bound_to_nonce(self):
        request_row = next(
            row for row in build_request_rows_v02(per_cell=1)
            if row["baseline"] == "matched_direct_outcome"
        )
        envelope = {
            "protocol_version": PROTOCOL_VERSION_V02,
            "sample_id": request_row["sample_id"],
            "sample_nonce": request_row["sample_nonce"],
            "baseline": request_row["baseline"],
            "target_band": request_row["target_band"],
            "source_kind": "model_response",
            "request_coordinates": request_row["request_coordinates"],
            "provenance": {
                "provider": "test-provider", "model": "test-model",
                "prompt_sha256": request_row["prompt_sha256"],
                "seed": request_row["seed"], "raw_id": "raw-1",
            },
            "response": {"mechanic": matched_raw(), "declared_power": 45.0},
        }
        self.assertEqual(validate_envelope(envelope).baseline, "matched_direct_outcome")
        tampered = copy.deepcopy(envelope)
        tampered["sample_nonce"] += "x"
        result = ingest_jsonl([canonical_json(tampered), canonical_json(envelope)])
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(len(result.samples), 1)

    def test_archived_v02_envelope_rebuilds_legacy_shared_example_prompt(self):
        request = legacy_prompt_request_v02(
            "matched_direct_outcome", "Mid", 1234,
            "matched_direct_outcome.mid.0000.compat", "compat-nonce",
        )
        self.assertEqual(request["protocol_version"], LEGACY_PROTOCOL_VERSION_V02)
        self.assertEqual(len(request["calibration_examples"]), 6)
        self.assertEqual(
            {item["mechanic"]["id"] for item in request["calibration_examples"]},
            {"bedrock_memory", "mud_anchor", "floodgate", "flash_flood", "kindling_arc", "ash_bloom"},
        )
        envelope = self._v02_envelope(
            LEGACY_PROTOCOL_VERSION_V02, legacy_prompt_hash_v02(request),
        )
        self.assertEqual(validate_envelope(envelope).baseline, "matched_direct_outcome")
        self.assertEqual(len(ingest_jsonl([canonical_json(envelope)]).samples), 1)

    def test_legacy_and_controlled_prompt_hashes_are_not_interchangeable(self):
        sample_id, seed, nonce = derive_sample_identity(
            2602, "matched_direct_outcome", "Mid", 0,
        )
        coordinates = ("matched_direct_outcome", "Mid", seed, sample_id, nonce)
        legacy_hash = legacy_prompt_hash_v02(legacy_prompt_request_v02(*coordinates))
        controlled_hash = prompt_hash_v02(prompt_request_v02(
            *coordinates, master_seed=2602, sample_index=0,
        ))
        self.assertNotEqual(legacy_hash, controlled_hash)
        with self.assertRaisesRegex(ValueError, "canonical v0.2 request"):
            legacy = self._v02_envelope(LEGACY_PROTOCOL_VERSION_V02, controlled_hash)
            legacy["sample_id"], legacy["sample_nonce"] = sample_id, nonce
            legacy["provenance"]["seed"] = seed
            validate_envelope(legacy)
        with self.assertRaisesRegex(ValueError, "canonical v0.2 request"):
            controlled = self._v02_envelope(PROTOCOL_VERSION_V02, legacy_hash)
            controlled["sample_id"], controlled["sample_nonce"] = sample_id, nonce
            controlled["provenance"]["seed"] = seed
            controlled["request_coordinates"] = {"master_seed": 2602, "sample_index": 0}
            validate_envelope(controlled)

    def test_unknown_generation_version_has_explicit_error(self):
        row = generate_fixture_envelopes(per_cell=1)[0]
        row["protocol_version"] = "gm-generation-v9"
        with self.assertRaisesRegex(ValueError, "unsupported version"):
            validate_envelope(row)


class DiversityAndArchiveTests(unittest.TestCase):
    def test_small_parameter_change_is_parametric_not_structural_diversity(self):
        first = matched_raw()
        second = copy.deepcopy(first)
        second["id"] = "matched_pulse_variant"
        second["effects"][0]["delta"] = 0.41
        self.assertEqual(structural_fingerprint(first), structural_fingerprint(second))
        self.assertNotEqual(parametric_fingerprint(first), parametric_fingerprint(second))
        self.assertEqual(diversity_report((first, second))["structural_unique"], 1)
        self.assertEqual(diversity_report((first, second))["parametric_unique"], 2)

    def test_topology_change_is_structural_diversity(self):
        first = matched_raw()
        second = copy.deepcopy(first)
        second["effects"].append({"field": "heal", "delta": 0.1})
        self.assertNotEqual(structural_fingerprint(first), structural_fingerprint(second))

    def test_archive_is_byte_reproducible_with_fixed_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            files = {"responses/data.jsonl": "{}\n", "requests/data.jsonl": '{"a":1}\n'}
            self.assertEqual(build_deterministic_archive(first, files), build_deterministic_archive(second, dict(reversed(list(files.items())))))
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                for info in archive.infolist():
                    self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(info.external_attr >> 16, 0o100644)


if __name__ == "__main__":
    unittest.main()
