from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from experiments.generative_mechanics.free_invention import prompt_hash, prompt_request
from experiments.generative_mechanics.pilots.free_v05_dev.pilot import (
    DATASET_KIND,
    DATASET_NAMESPACE,
    EVALUATION_PROTOCOL,
    MODELS,
    PROVIDER_SEED_UNAVAILABLE_REASON,
    PilotContractError,
    build_canonical_requests,
    finalize_pilot_artifacts,
    ingest_raw_records,
    read_jsonl,
    validate_pilot_artifacts,
    write_jsonl,
)
from experiments.generative_mechanics.pilots.free_v05_dev.provider_codex import (
    collect_model,
    extract_provider_metadata,
)


def raw_for(request: dict, response_text: str = "not json") -> dict:
    return {
        "dataset_kind": DATASET_KIND,
        "dataset_namespace": DATASET_NAMESPACE,
        "request_batch_id": request["request_batch_id"],
        "request_id": request["request_id"],
        "sample_id": request["sample_id"],
        "attempt": 1,
        "repair": False,
        "provider": request["provider"],
        "requested_model_identifier": request["exact_model_identifier"],
        "requested_reasoning_effort": "high",
        "returned_model_identifier": None,
        "returned_model_identifier_unavailable_reason": "Codex CLI response did not expose it",
        "provider_seed_enforced": False,
        "provider_seed_unavailable_reason": PROVIDER_SEED_UNAVAILABLE_REASON,
        "provider_request_id": None,
        "provider_request_id_unavailable_reason": "Codex CLI response did not expose it",
        "timestamp_utc": "2026-10-06T00:00:00Z",
        "provider_success": True,
        "transport_status": "success",
        "response_text": response_text,
        "raw_provider_response": {"preserved": response_text},
    }


class CanonicalPilotRequestTests(unittest.TestCase):
    def test_two_models_by_fifteen_are_unique_and_reproducible(self):
        rows = build_canonical_requests()
        self.assertEqual(rows, build_canonical_requests())
        self.assertEqual(len(rows), 30)
        self.assertEqual({row["exact_model_identifier"] for row in rows}, {
            model["exact_model_identifier"] for model in MODELS
        })
        for model in MODELS:
            self.assertEqual(sum(row["exact_model_identifier"] == model["exact_model_identifier"] for row in rows), 15)
        for field in ("request_id", "sample_id", "sample_nonce", "canonical_seed", "prompt_sha256"):
            self.assertEqual(len({row[field] for row in rows}), 30)

    def test_requests_reuse_v03_canonical_prompt_api(self):
        for row in build_canonical_requests():
            request = prompt_request(
                "world_substrate", row["canonical_seed"], row["sample_id"], row["sample_nonce"],
            )
            self.assertEqual(row["prompt_sha256"], prompt_hash(request))
            self.assertEqual(row["generation_protocol"], "gm-free-invention-v0.3")
            self.assertTrue(row["sample_id"].startswith("free-v05-dev-pilot-"))
            self.assertFalse(row["provider_seed_enforced"])
            self.assertIsNone(row["sampling_parameters"]["temperature"])
            self.assertTrue(row["sampling_parameters"]["temperature_unavailable_reason"])

    def test_dev_namespace_is_explicitly_excluded_from_formal_data(self):
        for row in build_canonical_requests():
            self.assertEqual(row["dataset_kind"], "dev_pilot")
            self.assertIn("prohibited", row["formal_data_exclusion"])


class RawIngestionTests(unittest.TestCase):
    def test_invalid_first_response_is_retained_as_content_failure(self):
        request = build_canonical_requests()[0]
        result = ingest_raw_records([raw_for(request)], [request])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["provider_success"])
        self.assertFalse(result[0]["schema_valid"])
        self.assertEqual(result[0]["status"], "content_invalid")
        self.assertTrue(result[0]["raw_response_preserved"])

    def test_repair_or_second_attempt_cannot_enter_main_pilot(self):
        request = build_canonical_requests()[0]
        for mutation in ({"attempt": 2}, {"repair": True}):
            raw = raw_for(request)
            raw.update(mutation)
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(PilotContractError, "first attempt only"):
                    ingest_raw_records([raw], [request])

    def test_null_provider_metadata_requires_reason(self):
        request = build_canonical_requests()[0]
        raw = raw_for(request)
        raw["provider_request_id_unavailable_reason"] = None
        with self.assertRaisesRegex(PilotContractError, "explicit unavailable reason"):
            ingest_raw_records([raw], [request])

    def test_duplicate_completed_first_attempt_is_rejected(self):
        request = build_canonical_requests()[0]
        with self.assertRaisesRegex(PilotContractError, "multiple first attempts"):
            ingest_raw_records([raw_for(request), raw_for(request)], [request])


class ArtifactValidationTests(unittest.TestCase):
    def test_checked_in_pilot_manifest_validates(self):
        result = validate_pilot_artifacts(stage="preregistration")
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["canonical_request_count"], 30)
        self.assertFalse(result["formal_dataset_ingestion_allowed"])

    def test_request_tamper_fails_closed(self):
        source = Path(__file__).parents[1] / "pilots" / "free_v05_dev"
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "free_v05_dev"
            import shutil
            shutil.copytree(source, copied)
            path = copied / "requests" / "canonical_requests.jsonl"
            rows = path.read_text(encoding="utf-8").splitlines()
            row = json.loads(rows[0])
            row["canonical_seed"] += 1
            rows[0] = json.dumps(row, sort_keys=True, separators=(",", ":"))
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            with self.assertRaises(PilotContractError):
                validate_pilot_artifacts(copied)

    def test_historical_preregistration_manifest_tamper_fails_closed(self):
        source = Path(__file__).parents[1] / "pilots" / "free_v05_dev"
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "free_v05_dev"
            import shutil
            shutil.copytree(source, copied)
            path = copied / "manifest" / "artifact_manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["collection_status"] = "COMPLETE"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(PilotContractError, "historical preregistration manifest hash mismatch"):
                validate_pilot_artifacts(copied, stage="preregistration")


class CodexProviderDriverTests(unittest.TestCase):
    @staticmethod
    def _copy_root(directory: str) -> Path:
        copied = Path(directory) / "free_v05_dev"
        write_jsonl(copied / "requests" / "canonical_requests.jsonl", build_canonical_requests())
        return copied

    def test_mock_collection_is_atomic_resumable_and_never_overwrites(self):
        event = json.dumps({
            "thread_id": "thread-1", "session_id": "session-1",
            "response_id": "response-1", "model": "gpt-5.6-luna",
        }) + "\n"

        def fake_run(command, **kwargs):
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text("not valid json", encoding="utf-8")
            return __import__("subprocess").CompletedProcess(command, 0, event, "")

        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_root(directory)
            runner = Mock(side_effect=fake_run)
            result = collect_model("gpt-5.6-luna", root=root, runner=runner)
            self.assertEqual((result["completed_now"], runner.call_count), (15, 15))
            raw_path = root / "raw_provider_responses" / "luna" / "first_attempts.jsonl"
            rows = read_jsonl(raw_path)
            self.assertEqual(len(rows), 15)
            self.assertTrue(all(row["attempt"] == 1 and not row["repair"] for row in rows))
            self.assertTrue(all(row["provider_request_id"] == "response-1" for row in rows))
            self.assertTrue(all(row["response_text"] == "not valid json" for row in rows))
            executed_commands = [call.args[0] for call in runner.call_args_list]
            for row in rows:
                recorded = row["raw_provider_response"]["command"]
                self.assertIn(recorded, executed_commands)
                self.assertNotIn("--output-schema", recorded)
                self.assertEqual(
                    row["raw_provider_response"]["transport_attempts"][0]["command"],
                    recorded,
                )
            self.assertEqual(len(list((raw_path.parent / "events").glob("*.stdout.jsonl"))), 15)
            second_runner = Mock(side_effect=AssertionError("must not call provider"))
            resumed = collect_model("gpt-5.6-luna", root=root, runner=second_runner)
            self.assertEqual((resumed["completed_now"], resumed["already_completed"]), (0, 15))
            self.assertEqual(second_runner.call_count, 0)

    def test_invalid_first_output_survives_then_ingests_as_invalid(self):
        def fake_run(command, **kwargs):
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text("```json\n{}\n```", encoding="utf-8")
            return __import__("subprocess").CompletedProcess(command, 0, "{}\n", "warning")

        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_root(directory)
            collect_model("gpt-5.6-terra", root=root, runner=fake_run)
            raw = read_jsonl(root / "raw_provider_responses" / "terra" / "first_attempts.jsonl")
            ingested = ingest_raw_records(raw)
            self.assertEqual(len(ingested), 15)
            self.assertTrue(all(row["status"] == "content_invalid" for row in ingested))
            self.assertTrue(all(row["raw_response_preserved"] for row in ingested))
            self.assertTrue(all(row["provider_request_id"] is None for row in raw))
            self.assertTrue(all(row["provider_request_id_unavailable_reason"] for row in raw))

    def test_unresolved_started_marker_blocks_possible_second_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_root(directory)
            request = next(
                row for row in build_canonical_requests()
                if row["exact_model_identifier"] == "gpt-5.6-luna"
            )
            marker = root / "raw_provider_responses" / "luna" / "started" / f"{request['request_id']}.json"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("{}\n", encoding="utf-8")
            runner = Mock()
            with self.assertRaisesRegex(PilotContractError, "refusing a possible second call"):
                collect_model("gpt-5.6-luna", root=root, runner=runner)
            self.assertEqual(runner.call_count, 0)

    def test_metadata_extraction_and_absence_are_explicit(self):
        metadata = extract_provider_metadata(json.dumps({
            "threadId": "t", "sessionId": "s", "requestId": "r", "model_id": "m",
        }))
        self.assertEqual(metadata, {
            "provider_thread_id": "t", "provider_session_id": "s",
            "provider_request_id": "r", "returned_model_identifier": "m",
        })
        self.assertTrue(all(value is None for value in extract_provider_metadata("not-json").values()))


class FinalArtifactFreezeTests(unittest.TestCase):
    @staticmethod
    def _valid_mechanic(index: int) -> dict:
        return {
            "id": f"pilot_fixture_{index}", "name": f"Pilot Fixture {index}",
            "target_scope": "zone",
            "effects": [{"field": "wetness", "delta": 0.25}],
            "duration": 0.0, "periodic": None, "trigger_conditions": [],
            "resource_cost": 1.0, "charges": 1, "slot_cost": 1,
        }

    @classmethod
    def _final_fixture(cls, directory: str, *, complete_report: bool = True) -> Path:
        root = Path(directory) / "free_v05_dev"
        requests = list(build_canonical_requests())
        write_jsonl(root / "requests" / "canonical_requests.jsonl", requests)
        call_index = 0

        def fake_run(command, **kwargs):
            nonlocal call_index
            response = (
                json.dumps({"mechanic": cls._valid_mechanic(call_index)})
                if call_index < 27 else "invalid first response"
            )
            call_index += 1
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(response, encoding="utf-8")
            event = json.dumps({"thread_id": f"thread-{call_index}"}) + "\n"
            return __import__("subprocess").CompletedProcess(command, 0, event, "")

        collect_model("gpt-5.6-luna", root=root, runner=fake_run)
        collect_model("gpt-5.6-terra", root=root, runner=fake_run)
        raw = []
        for slug in ("luna", "terra"):
            raw.extend(read_jsonl(root / "raw_provider_responses" / slug / "first_attempts.jsonl"))
        ingested = list(ingest_raw_records(raw, requests))
        for slug, model in (("luna", "gpt-5.6-luna"), ("terra", "gpt-5.6-terra")):
            model_ingested = [row for row in ingested if row["requested_model_identifier"] == model]
            write_jsonl(root / "ingested" / f"{slug}.jsonl", model_ingested)
            profiles = [{
                "dataset_kind": DATASET_KIND,
                "dataset_namespace": DATASET_NAMESPACE,
                "request_batch_id": row["request_batch_id"],
                "request_id": row["request_id"],
                "sample_id": row["sample_id"],
                "model_identifier": model,
                "evaluation_protocol": EVALUATION_PROTOCOL,
                "evaluation_status": "success",
                "profile": {"protocol_version": EVALUATION_PROTOCOL},
                "error_type": None,
                "error_message": None,
            } for row in model_ingested if row["compile_valid"]]
            write_jsonl(root / "profiles" / f"{slug}.jsonl", profiles)
        audit = []
        for index, request in enumerate(requests):
            audit.append({
                "dataset_kind": DATASET_KIND, "dataset_namespace": DATASET_NAMESPACE,
                "sample_id": request["sample_id"], "selection_category": "fixture",
                "metric_output_semantically_reasonable": "yes",
                "near_copy_reasonable": "yes", "recombination_reasonable": "yes",
                "abstract_topology_reasonable": "yes",
                "dependency_depth_trace_consistent": "yes",
                "outcome_path_split_reasonable": "yes", "inertness_reasonable": "yes",
                "auditor_reason": f"fixture audit {index}", "metric_values_modified": False,
            })
        write_jsonl(root / "manual_audit" / "manual_audit.jsonl", audit)
        analysis = {
            "dataset_kind": DATASET_KIND, "dataset_namespace": DATASET_NAMESPACE,
            "formal_experiment_status": "NOT STARTED", "models": [],
        }
        (root / "analysis").mkdir(parents=True)
        for name in ("summary.json", "metric_distributions.json"):
            (root / "analysis" / name).write_text(json.dumps(analysis), encoding="utf-8")
        bias = {
            **analysis,
            "readiness": "FORMAL_EXPERIMENT_READY",
            "metrics": [{"metric": metric} for metric in (
                "Activation", "Inertness", "Exact match", "Near-copy", "Recombination",
                "Semantic structure", "Abstract topology", "Dependency depth",
                "Necessity depth", "Outcome differentiation", "Path differentiation",
            )],
            "required_questions": [
                {"number": number, "answer": f"fixture answer {number}"}
                for number in range(1, 17)
            ],
        }
        (root / "analysis" / "bias_audit.json").write_text(json.dumps(bias), encoding="utf-8")
        report = """# Pilot Report

## Bias Audit

| Metric | Saturated? | Missing? | Agreement? | Anomaly? | Blocks? |
|---|---|---|---|---|---|
| Activation | no | no | yes | no | no |

FORMAL_EXPERIMENT_READY
"""
        if not complete_report:
            report = report.replace("no | no | yes | no | no", "pending | pending | pending | pending | pending")
        (root / "analysis" / "PILOT_REPORT.md").write_text(report, encoding="utf-8")
        return root

    def test_final_manifest_recursively_binds_complete_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._final_fixture(directory)
            manifest = finalize_pilot_artifacts(root)
            self.assertEqual(manifest["collection_status"], "COMPLETE")
            self.assertEqual(manifest["genuine_provider_call_count"], 30)
            self.assertEqual((manifest["ingested_count"], manifest["profile_count"]), (30, 27))
            result = validate_pilot_artifacts(root, stage="final")
            self.assertEqual(result["pilot_artifact_digest"], manifest["pilot_artifact_digest"])
            summary = root / "analysis" / "summary.json"
            summary.write_text(summary.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(PilotContractError, "hash mismatch"):
                validate_pilot_artifacts(root, stage="final")

    def test_finalize_rejects_external_raw_evidence_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._final_fixture(directory)
            event = next((root / "raw_provider_responses" / "luna" / "events").glob("*.stdout.jsonl"))
            event.write_text(event.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")
            with self.assertRaisesRegex(PilotContractError, "external and embedded raw evidence differ"):
                finalize_pilot_artifacts(root)

    def test_finalize_rejects_unfinished_bias_audit_without_partial_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._final_fixture(directory, complete_report=False)
            with self.assertRaisesRegex(PilotContractError, "not finalized"):
                finalize_pilot_artifacts(root)
            self.assertFalse((root / "manifest" / "final_artifact_manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
