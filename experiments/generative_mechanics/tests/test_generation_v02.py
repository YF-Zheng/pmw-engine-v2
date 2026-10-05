from __future__ import annotations

import copy
from contextlib import redirect_stdout
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
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_V02,
    build_request_rows_v02,
    calibration_examples_v02,
    generate_fixture_envelopes,
    ingest_jsonl,
    prompt_request_v02,
    public_rule_summary,
    validate_envelope,
)
from experiments.generative_mechanics.generators.archive import build_deterministic_archive
from experiments.generative_mechanics.power_v02 import evaluate_power
from experiments.generative_mechanics.runner import load_skill_catalog
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

    def test_exactly_two_calibration_examples_per_band_with_rebuild_provenance(self):
        examples = calibration_examples_v02()
        self.assertEqual(len(examples), 6)
        for band in ("Low", "Mid", "High"):
            self.assertEqual(sum(item["target_band"] == band for item in examples), 2)
        for item in examples:
            provenance = item["provenance"]
            self.assertEqual(provenance["split"], "calibration")
            self.assertTrue(provenance["scenario_id"].startswith("calibration/"))
            self.assertEqual(provenance["scorer_interface"], "gm-authoritative-scorer-v0.1")
            self.assertTrue(provenance["score_rebuild_key"])

    def test_calibration_example_scores_rebuild_through_authoritative_scorer(self):
        root = Path(__file__).parents[1]
        scenarios = tuple(
            load_scenario(path)
            for path in sorted((root / "scenarios" / "calibration").glob("*.json"))
        )
        catalog = load_skill_catalog()
        for item in calibration_examples_v02():
            skill_id = item["mechanic"]["id"]
            rebuilt = evaluate_power(
                scenarios, (skill_id,), split="calibration", catalog=catalog,
            ).typical_power
            self.assertAlmostEqual(item["realized_score"], rebuilt)
            low, high = {"Low": (20, 30), "Mid": (40, 50), "High": (60, 70)}[item["target_band"]]
            self.assertLessEqual(low, rebuilt)
            self.assertLessEqual(rebuilt, high)


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
