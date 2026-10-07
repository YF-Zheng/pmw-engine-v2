"""Collection and analysis infrastructure for the isolated v0.5 DEV pilot.

This module deliberately contains no provider client. Collection is a separate,
explicit operation; failed model content is evidence and is never retried here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
from typing import Any, Iterable, Mapping

from ...compiler import canonical_json, compile_skill
from ...free_evaluation_v05.profile import evaluate_free_invention_profile_v05
from ...free_evaluation_v05.semantic_contract import validate_semantic_contract
from ...free_invention import (
    PROTOCOL_VERSION as GENERATION_PROTOCOL,
    FreeInventionSample,
    prompt_hash,
    prompt_request,
)
from ...generation import Provenance, render_prompt
from ...spec import validate_skill


ROOT = Path(__file__).resolve().parent
DATASET_KIND = "dev_pilot"
DATASET_NAMESPACE = "free-v05-dev-pilot"
BATCH_ID = "free-v05-dev-pilot-batch-001"
BASELINE = "world_substrate"
EVALUATION_PROTOCOL = "gm-free-evaluation-v0.5"
PROVIDER = "OpenAI Codex CLI"
REQUESTS_PER_MODEL = 15
MODELS = (
    {"exact_model_identifier": "gpt-5.6-luna", "reasoning_effort": "high"},
    {"exact_model_identifier": "gpt-5.6-terra", "reasoning_effort": "high"},
)
PROVIDER_SEED_ENFORCED = False
PROVIDER_SEED_UNAVAILABLE_REASON = (
    "OpenAI Codex CLI does not expose a provider-enforced sampling seed for this collection path"
)
SAMPLING_PARAMETER_UNAVAILABLE_REASON = (
    "OpenAI Codex CLI does not expose this sampling control for this collection path"
)
FORMAL_DATA_EXCLUSION = (
    "DEV/PILOT DATASET ONLY; prohibited from formal/paper dataset ingestion"
)
FREEZE_COMMIT = "89e0c6ad24f62c68f4e326b361e0f3c5f807c756"
PREREGISTRATION_COMMIT = "b9a29bf868071ec8af63706f8e0ad848a4a703e8"
PREREGISTRATION_MANIFEST_SHA256 = "64836b2ea4912cfd9cf91e8d136bd84a83f96742454ba08ccf0dc11e4e527a03"
FINAL_MANIFEST_RELATIVE_PATH = Path("manifest/final_artifact_manifest.json")


class PilotContractError(ValueError):
    """A pilot artifact violates collection or isolation rules."""


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _identity(model: str, index: int) -> tuple[str, str, int]:
    slug = model.removeprefix("gpt-5.6-")
    material = f"{DATASET_NAMESPACE}|{BATCH_ID}|{model}|{index}"
    digest = _digest(material)
    request_id = f"{DATASET_NAMESPACE}-{slug}-{index + 1:02d}-{digest[:10]}"
    nonce = digest[10:42]
    seed = int(digest[42:58], 16) & ((1 << 63) - 1)
    return request_id, nonce, seed


def build_canonical_requests() -> tuple[dict[str, Any], ...]:
    """Build 2 x 15 v0.3 canonical prompts with pilot-only identities."""
    rows = []
    for model in MODELS:
        model_id = model["exact_model_identifier"]
        for index in range(REQUESTS_PER_MODEL):
            request_id, nonce, seed = _identity(model_id, index)
            request = prompt_request(BASELINE, seed, request_id, nonce)
            rows.append({
                "dataset_kind": DATASET_KIND,
                "dataset_namespace": DATASET_NAMESPACE,
                "formal_data_exclusion": FORMAL_DATA_EXCLUSION,
                "request_batch_id": BATCH_ID,
                "request_id": request_id,
                "sample_id": request_id,
                "sample_nonce": nonce,
                "canonical_seed": seed,
                "provider_seed_enforced": PROVIDER_SEED_ENFORCED,
                "provider_seed_unavailable_reason": PROVIDER_SEED_UNAVAILABLE_REASON,
                "provider": PROVIDER,
                "exact_model_identifier": model_id,
                "reasoning_effort": model["reasoning_effort"],
                "sampling_parameters": {
                    "temperature": None,
                    "temperature_unavailable_reason": SAMPLING_PARAMETER_UNAVAILABLE_REASON,
                    "top_p": None,
                    "top_p_unavailable_reason": SAMPLING_PARAMETER_UNAVAILABLE_REASON,
                    "max_output_tokens": None,
                    "max_output_tokens_unavailable_reason": SAMPLING_PARAMETER_UNAVAILABLE_REASON,
                },
                "generation_protocol": GENERATION_PROTOCOL,
                "evaluation_protocol": EVALUATION_PROTOCOL,
                "baseline": BASELINE,
                "sample_index_within_model": index,
                "prompt": render_prompt(request),
                "prompt_sha256": prompt_hash(request),
            })
    return tuple(rows)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical_json(dict(row)) + "\n" for row in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PilotContractError(f"{path}:{number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise PilotContractError(f"{path}:{number}: expected JSON object")
        rows.append(value)
    return rows


def _request_index(requests: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result = {}
    for request in requests:
        request_id = request.get("request_id")
        if request_id in result:
            raise PilotContractError(f"duplicate request_id: {request_id}")
        result[request_id] = request
    return result


def _check_raw_record(record: Mapping[str, Any], request: Mapping[str, Any]) -> None:
    required = {
        "dataset_kind", "dataset_namespace", "request_batch_id", "request_id",
        "sample_id", "attempt", "repair", "provider", "requested_model_identifier",
        "requested_reasoning_effort", "returned_model_identifier",
        "returned_model_identifier_unavailable_reason", "provider_seed_enforced",
        "provider_seed_unavailable_reason", "provider_request_id",
        "provider_request_id_unavailable_reason", "timestamp_utc", "provider_success",
        "transport_status", "response_text", "raw_provider_response",
    }
    missing = sorted(required - set(record))
    if missing:
        raise PilotContractError(f"raw record missing fields: {missing}")
    bindings = {
        "dataset_kind": DATASET_KIND,
        "dataset_namespace": DATASET_NAMESPACE,
        "request_batch_id": BATCH_ID,
        "sample_id": request["sample_id"],
        "provider": PROVIDER,
        "requested_model_identifier": request["exact_model_identifier"],
        "requested_reasoning_effort": request["reasoning_effort"],
        "provider_seed_enforced": False,
    }
    for field, expected in bindings.items():
        if record[field] != expected:
            raise PilotContractError(f"{field}: expected {expected!r}")
    if record["attempt"] != 1 or record["repair"] is not False:
        raise PilotContractError("main pilot accepts first attempt only; repair attempts require a separate experiment")
    if record["provider_seed_unavailable_reason"] != PROVIDER_SEED_UNAVAILABLE_REASON:
        raise PilotContractError("provider seed limitation must be recorded exactly")
    if record["provider_request_id"] is None and not record["provider_request_id_unavailable_reason"]:
        raise PilotContractError("null provider_request_id requires an explicit unavailable reason")
    if record["returned_model_identifier"] is None and not record["returned_model_identifier_unavailable_reason"]:
        raise PilotContractError("null returned_model_identifier requires an explicit unavailable reason")
    if not isinstance(record["response_text"], str):
        raise PilotContractError("response_text must preserve the exact assistant text")


def ingest_raw_records(
    raw_records: Iterable[Mapping[str, Any]],
    requests: Iterable[Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Validate provenance and classify content without retrying it."""
    request_rows = tuple(requests or build_canonical_requests())
    request_by_id = _request_index(request_rows)
    seen = set()
    ingested = []
    for raw in raw_records:
        request_id = raw.get("request_id")
        if request_id not in request_by_id:
            raise PilotContractError(f"unknown pilot request_id: {request_id}")
        if request_id in seen:
            raise PilotContractError(f"multiple first attempts for request_id: {request_id}")
        seen.add(request_id)
        request = request_by_id[request_id]
        _check_raw_record(raw, request)
        raw_sha = _digest(canonical_json(raw["raw_provider_response"]))
        row = {
            "dataset_kind": DATASET_KIND,
            "dataset_namespace": DATASET_NAMESPACE,
            "request_batch_id": BATCH_ID,
            "request_id": request_id,
            "sample_id": request["sample_id"],
            "attempt": 1,
            "repair": False,
            "analyzed_as_first_attempt": True,
            "provider": PROVIDER,
            "requested_model_identifier": request["exact_model_identifier"],
            "requested_reasoning_effort": request["reasoning_effort"],
            "returned_model_identifier": raw["returned_model_identifier"],
            "returned_model_identifier_unavailable_reason": raw["returned_model_identifier_unavailable_reason"],
            "provider_seed_enforced": False,
            "provider_seed_unavailable_reason": PROVIDER_SEED_UNAVAILABLE_REASON,
            "provider_request_id": raw["provider_request_id"],
            "provider_request_id_unavailable_reason": raw["provider_request_id_unavailable_reason"],
            "timestamp_utc": raw["timestamp_utc"],
            "prompt_sha256": request["prompt_sha256"],
            "canonical_seed": request["canonical_seed"],
            "raw_provider_response_sha256": raw_sha,
            "raw_response_preserved": True,
            "provider_success": bool(raw["provider_success"]),
            "schema_valid": False,
            "compile_valid": False,
            "execution_valid": None,
            "evaluation_profile": EVALUATION_PROTOCOL,
            "status": "provider_error",
            "error_type": None,
            "error_message": None,
            "parsed_mechanic": None,
        }
        if not raw["provider_success"]:
            ingested.append(row)
            continue
        try:
            response = json.loads(raw["response_text"])
            if not isinstance(response, dict) or set(response) != {"mechanic"}:
                raise PilotContractError("response must be a strict object containing only mechanic")
            mechanic = validate_skill(response["mechanic"])
            row["schema_valid"] = True
            row["parsed_mechanic"] = response["mechanic"]
            compile_skill(mechanic)
            row["compile_valid"] = True
            row["status"] = "ready_for_evaluation"
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            row["status"] = "content_invalid"
            row["error_type"] = type(exc).__name__
            row["error_message"] = str(exc)
        ingested.append(row)
    return tuple(ingested)


def _sample_for(row: Mapping[str, Any]) -> FreeInventionSample:
    mechanic = validate_skill(row["parsed_mechanic"])
    model = row["returned_model_identifier"] or row["requested_model_identifier"]
    return FreeInventionSample(
        sample_id=row["sample_id"], baseline=BASELINE,
        master_seed=row["canonical_seed"], sample_index=0,
        source_kind="model_response",
        provenance=Provenance(
            provider=PROVIDER, model=model, prompt_sha256=row["prompt_sha256"],
            seed=row["canonical_seed"], raw_id=row["raw_provider_response_sha256"],
        ),
        mechanic=mechanic, raw_mechanic=row["parsed_mechanic"],
    )


def run_frozen_profiles(
    ingested: Iterable[Mapping[str, Any]],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    """Run only compile-valid first attempts through frozen v0.5."""
    validate_semantic_contract()
    updated, profiles = [], []
    for source in ingested:
        row = dict(source)
        if row.get("attempt") != 1 or row.get("analyzed_as_first_attempt") is not True:
            raise PilotContractError("profile input must be an admitted first attempt")
        if row.get("compile_valid") is not True:
            updated.append(row)
            continue
        profile_row = {
            "dataset_kind": DATASET_KIND,
            "dataset_namespace": DATASET_NAMESPACE,
            "request_batch_id": BATCH_ID,
            "request_id": row["request_id"],
            "sample_id": row["sample_id"],
            "model_identifier": row["requested_model_identifier"],
            "evaluation_protocol": EVALUATION_PROTOCOL,
            "evaluation_status": "error",
            "profile": None,
            "error_type": None,
            "error_message": None,
        }
        try:
            profile_row["profile"] = evaluate_free_invention_profile_v05(_sample_for(row))
            profile_row["evaluation_status"] = "success"
            row["execution_valid"] = True
            row["status"] = "evaluated"
        except Exception as exc:  # evaluator failure must remain pilot evidence
            profile_row["error_type"] = type(exc).__name__
            profile_row["error_message"] = str(exc)
            row["execution_valid"] = False
            row["status"] = "execution_invalid"
        updated.append(row)
        profiles.append(profile_row)
    return tuple(updated), tuple(profiles)


def _distribution(values: Iterable[float | int]) -> dict[str, Any]:
    values = list(values)
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None, "histogram": {}}
    return {
        "count": len(values), "min": min(values), "median": statistics.median(values),
        "mean": math.fsum(values) / len(values), "max": max(values),
        "histogram": dict(sorted(Counter(str(value) for value in values).items())),
    }


def _model_summary(
    model: str, ingested: list[Mapping[str, Any]], profiles: list[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = [row for row in ingested if row["requested_model_identifier"] == model]
    successful = [row for row in profiles if row["model_identifier"] == model and row["evaluation_status"] == "success"]
    values = [row["profile"] for row in successful]
    structures = [profile["structural_evidence"] for profile in values]
    eligible = [value for value in structures if value.get("available")]
    realized = [depth for profile in values for depth in profile["dynamic_reach"]["conditional_on_activation"]["realized_dependency_depth_distribution"]]
    necessity = [depth for profile in values for depth in profile["dynamic_reach"]["conditional_on_activation"]["necessity_backed_depth_distribution"]]
    gaps = [depth for profile in values for depth in profile["dynamic_reach"]["conditional_on_activation"]["depth_gap_distribution"]]
    context_rows = [context for profile in values for context in profile["environmental_behavior"]["contexts"]]
    quadrants = Counter(
        (context["outcome_differentiated"], context["causal_path_differentiated"])
        for context in context_rows
    )
    semantic = {value["semantic_structure"]["fingerprint"] for value in eligible}
    abstract = {value["abstract_topology"]["fingerprint"] for value in eligible}
    inert = sum(profile["behavioral_inertness"]["behaviorally_inert"] for profile in values)
    summary = {
        "model_identifier": model,
        "interpretation_guard": "DEV evaluator-health evidence only; no model ranking or formal conclusion",
        "n_requested": REQUESTS_PER_MODEL,
        "n_provider_success": sum(row["provider_success"] for row in rows),
        "n_schema_valid": sum(row["schema_valid"] for row in rows),
        "n_compile_valid": sum(row["compile_valid"] for row in rows),
        "n_execution_valid": sum(row["execution_valid"] is True for row in rows),
        "n_schema_invalid": sum(row["provider_success"] and not row["schema_valid"] for row in rows),
        "n_compile_invalid": sum(row["schema_valid"] and not row["compile_valid"] for row in rows),
        "n_execution_invalid": sum(row["execution_valid"] is False for row in rows),
        "activation_rate_distribution": _distribution(profile["activation"]["activation_rate"] for profile in values),
        "behaviorally_inert_count": inert,
        "behaviorally_inert_rate": inert / len(values) if values else None,
        "exact_match_rate": sum(value["exact_match"] for value in eligible) / len(eligible) if eligible else None,
        "near_copy_rate": sum(value["near_copy"] for value in eligible) / len(eligible) if eligible else None,
        "recombination_rate": sum(value["recombination"]["recombination_detected"] for value in eligible) / len(eligible) if eligible else None,
        "distinct_semantic_structure_count": len(semantic),
        "distinct_abstract_topology_count": len(abstract),
        "semantic_to_abstract_distinct_ratio": len(semantic) / len(abstract) if abstract else None,
        "structurally_nonmatching_and_behaviorally_inert_count": sum(
            structure.get("available") and not structure["exact_match"] and profile["behavioral_inertness"]["behaviorally_inert"]
            for structure, profile in zip(structures, values)
        ),
        "outcome_differentiated_context_rate": sum(row["outcome_differentiated"] for row in context_rows) / len(context_rows) if context_rows else None,
        "causal_path_differentiated_context_rate": sum(row["causal_path_differentiated"] for row in context_rows) / len(context_rows) if context_rows else None,
        "outcome_path_quadrants": {
            "outcome_same_path_same": quadrants[(False, False)],
            "outcome_same_path_different": quadrants[(False, True)],
            "outcome_different_path_same": quadrants[(True, False)],
            "outcome_different_path_different": quadrants[(True, True)],
        },
    }
    distributions = {
        "model_identifier": model,
        "realized_dependency_depth": _distribution(realized),
        "necessity_backed_depth": _distribution(necessity),
        "depth_gap": _distribution(gaps),
    }
    return summary, distributions


def summarize(
    ingested: Iterable[Mapping[str, Any]], profiles: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ingested_rows, profile_rows = list(ingested), list(profiles)
    summaries, distributions = [], []
    for config in MODELS:
        summary, distribution = _model_summary(
            config["exact_model_identifier"], ingested_rows, profile_rows,
        )
        summaries.append(summary)
        distributions.append(distribution)
    common = {
        "dataset_kind": DATASET_KIND,
        "dataset_namespace": DATASET_NAMESPACE,
        "request_batch_id": BATCH_ID,
        "generation_protocol": GENERATION_PROTOCOL,
        "evaluation_protocol": EVALUATION_PROTOCOL,
        "provider": PROVIDER,
        "provider_seed_enforced": False,
        "provider_seed_unavailable_reason": PROVIDER_SEED_UNAVAILABLE_REASON,
        "formal_experiment_status": "NOT STARTED",
        "ranking_prohibited": True,
    }
    return ({**common, "models": summaries}, {**common, "models": distributions})


def build_manual_audit_scaffold(profiles: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    successful = [row for row in profiles if row.get("evaluation_status") == "success"]
    def complexity(row: Mapping[str, Any]) -> tuple[float, str]:
        profile = row["profile"]
        depth = profile["dynamic_reach"]["conditional_on_activation"]["maximum_realized_dependency_depth"]
        return (float(depth if depth is not None else -1), row["sample_id"])
    high = sorted(successful, key=complexity, reverse=True)[:10]
    low = sorted(successful, key=complexity)[:10]
    anomalies = sorted(successful, key=lambda row: (
        not row["profile"]["behavioral_inertness"]["behaviorally_inert"],
        not row["profile"]["structural_evidence"].get("near_copy", False),
        row["sample_id"],
    ))[:10]
    rows = []
    for category, selected in (("high_complex_dynamic", high), ("low_simple", low), ("anomalous_counterintuitive", anomalies)):
        for row in selected:
            rows.append({
                "dataset_kind": DATASET_KIND,
                "dataset_namespace": DATASET_NAMESPACE,
                "request_batch_id": BATCH_ID,
                "sample_id": row["sample_id"],
                "model_identifier": row["model_identifier"],
                "selection_category": category,
                "selection_reason": "deterministic pilot scaffold; category overlap is allowed when fewer than 30 valid samples exist",
                "metric_output_semantically_reasonable": None,
                "auditor_reason": None,
                "near_copy_reasonable": None,
                "recombination_reasonable": None,
                "abstract_topology_reasonable": None,
                "dependency_depth_trace_consistent": None,
                "outcome_path_split_reasonable": None,
                "inertness_reasonable": None,
                "metric_values_modified": False,
            })
    return tuple(rows)


def _validate_requests(rows: list[Mapping[str, Any]]) -> None:
    expected = list(build_canonical_requests())
    if rows != expected:
        raise PilotContractError("canonical requests do not match deterministic 2 x 15 preregistration")
    if len(rows) != 30:
        raise PilotContractError("pilot must contain exactly 30 canonical requests")
    for field in ("request_id", "sample_id", "sample_nonce", "canonical_seed", "prompt_sha256"):
        if len({row[field] for row in rows}) != len(rows):
            raise PilotContractError(f"canonical request field is not unique: {field}")


def _validate_preregistration_artifacts(root: Path) -> dict[str, Any]:
    requests_path = root / "requests" / "canonical_requests.jsonl"
    rows = read_jsonl(requests_path)
    _validate_requests(rows)
    manifest_path = root / "manifest" / "artifact_manifest.json"
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != PREREGISTRATION_MANIFEST_SHA256:
        raise PilotContractError("historical preregistration manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["dataset_kind"] != DATASET_KIND or manifest["dataset_namespace"] != DATASET_NAMESPACE:
        raise PilotContractError("artifact manifest is not bound to the DEV namespace")
    # Mutable report/docs now describe the completed pilot. Their preregistration
    # bytes remain recoverable from PREREGISTRATION_COMMIT and are authenticated by
    # the fixed manifest hash above. The two experiment-defining inputs must also
    # remain byte-identical in the live tree.
    immutable = {"manifest/preregistration.json", "requests/canonical_requests.jsonl"}
    for item in manifest["artifacts"]:
        if not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64:
            raise PilotContractError(f"invalid historical artifact digest: {item.get('path')}")
        if item["path"] in immutable:
            path = root / item["path"]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise PilotContractError(f"immutable preregistration artifact mismatch: {item['path']}")
    contract = validate_semantic_contract()
    if contract["semantic_contract_digest"] != manifest["v05_semantic_contract_digest"]:
        raise PilotContractError("frozen v0.5 semantic contract digest drift")
    return {
        "status": "VALID", "stage": "preregistration", "dataset_kind": DATASET_KIND,
        "dataset_namespace": DATASET_NAMESPACE, "canonical_request_count": len(rows),
        "artifact_count": len(manifest["artifacts"]),
        "formal_dataset_ingestion_allowed": False,
    }


def _all_final_artifact_paths(root: Path) -> tuple[Path, ...]:
    excluded_names = {".DS_Store"}
    paths = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative == FINAL_MANIFEST_RELATIVE_PATH:
            continue
        if "__pycache__" in relative.parts or "started" in relative.parts:
            continue
        if path.suffix in {".pyc", ".tmp"} or path.name in excluded_names:
            continue
        if path.name.startswith(".") and "in_progress" in path.name:
            continue
        paths.append(relative)
    return tuple(sorted(paths, key=lambda item: item.as_posix()))


def _load_final_rows(root: Path, area: str) -> list[dict[str, Any]]:
    rows = []
    for model in ("luna", "terra"):
        rows.extend(read_jsonl(root / area / f"{model}.jsonl"))
    return rows


def _bound_artifact(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise PilotContractError(f"raw evidence path escapes pilot root: {relative}") from exc
    if not path.is_file():
        raise PilotContractError(f"raw evidence artifact is missing: {relative}")
    return path


def _validate_raw_evidence(root: Path, raw: list[dict[str, Any]]) -> int:
    calls = 0
    model_counts = Counter(row.get("requested_model_identifier") for row in raw)
    if model_counts != Counter({model["exact_model_identifier"]: 15 for model in MODELS}):
        raise PilotContractError("raw evidence must contain exactly 15 responses per model")
    unresolved = list((root / "raw_provider_responses").glob("*/started/*.json"))
    if unresolved:
        raise PilotContractError("raw evidence contains unresolved started markers")
    for row in raw:
        request_id = row["request_id"]
        slug = row["requested_model_identifier"].removeprefix("gpt-5.6-")
        record_path = root / "raw_provider_responses" / slug / "records" / f"{request_id}.json"
        if not record_path.is_file() or json.loads(record_path.read_text(encoding="utf-8")) != row:
            raise PilotContractError(f"raw record/JSONL mismatch: {request_id}")
        attempts = row.get("raw_provider_response", {}).get("transport_attempts")
        if (
            row.get("transport_attempt_count") != 1
            or row.get("transport_retry_limit") != 0
            or not isinstance(attempts, list)
            or len(attempts) != 1
        ):
            raise PilotContractError(f"pilot requires one transport attempt and no retry: {request_id}")
        attempt = attempts[0]
        if attempt.get("transport_attempt") != 1 or attempt.get("exit_code") != 0:
            raise PilotContractError(f"invalid transport attempt evidence: {request_id}")
        paths = attempt.get("event_log_paths", {})
        stdout = _bound_artifact(root, paths.get("stdout", "")).read_text(encoding="utf-8")
        stderr = _bound_artifact(root, paths.get("stderr", "")).read_text(encoding="utf-8")
        last = _bound_artifact(
            root, row["raw_provider_response"].get("last_message_path", ""),
        ).read_text(encoding="utf-8")
        if (
            stdout != attempt.get("stdout_jsonl")
            or stderr != attempt.get("stderr")
            or last != attempt.get("last_message")
            or stdout != row["raw_provider_response"].get("stdout_jsonl")
            or stderr != row["raw_provider_response"].get("stderr")
            or last != row.get("response_text")
        ):
            raise PilotContractError(f"external and embedded raw evidence differ: {request_id}")
        calls += 1
    return calls


def _require_final_inputs(root: Path) -> dict[str, Any]:
    requests = read_jsonl(root / "requests" / "canonical_requests.jsonl")
    _validate_requests(requests)
    raw = []
    for model in ("luna", "terra"):
        raw.extend(read_jsonl(root / "raw_provider_responses" / model / "first_attempts.jsonl"))
    if len(raw) != 30:
        raise PilotContractError(f"finalize requires 30 raw first attempts, found {len(raw)}")
    admitted = ingest_raw_records(raw, requests)
    if len(admitted) != 30:
        raise PilotContractError("all 30 raw first attempts must have complete provenance")
    if not all(row["provider_success"] for row in raw):
        raise PilotContractError("finalize requires 30 genuine provider-success responses")
    if len({row["request_id"] for row in raw}) != 30:
        raise PilotContractError("raw first-attempt request ids must be unique")
    genuine_provider_call_count = _validate_raw_evidence(root, raw)

    ingested = _load_final_rows(root, "ingested")
    if len(ingested) != 30 or {row["request_id"] for row in ingested} != {row["request_id"] for row in raw}:
        raise PilotContractError("finalize requires exactly 30 request-bound ingested rows")
    if not all(
        row.get("dataset_kind") == DATASET_KIND
        and row.get("dataset_namespace") == DATASET_NAMESPACE
        and row.get("attempt") == 1
        and row.get("analyzed_as_first_attempt") is True
        for row in ingested
    ):
        raise PilotContractError("ingested rows violate DEV or first-attempt binding")
    compile_ids = {row["request_id"] for row in ingested if row.get("compile_valid") is True}

    profiles = _load_final_rows(root, "profiles")
    if len(profiles) != len(compile_ids):
        raise PilotContractError(
            f"profile count {len(profiles)} does not equal compile-valid count {len(compile_ids)}"
        )
    if {row["request_id"] for row in profiles} != compile_ids:
        raise PilotContractError("profiles must correspond exactly to compile-valid requests")
    if not all(
        row.get("dataset_kind") == DATASET_KIND
        and row.get("dataset_namespace") == DATASET_NAMESPACE
        and row.get("evaluation_status") == "success"
        and isinstance(row.get("profile"), dict)
        and row["profile"].get("protocol_version") == EVALUATION_PROTOCOL
        for row in profiles
    ):
        raise PilotContractError("every final profile must be a successful frozen v0.5 profile")

    audit = read_jsonl(root / "manual_audit" / "manual_audit.jsonl")
    if len(audit) < 30:
        raise PilotContractError("manual audit requires at least 30 category selections")
    categorical = {
        "metric_output_semantically_reasonable", "near_copy_reasonable",
        "recombination_reasonable", "abstract_topology_reasonable",
        "dependency_depth_trace_consistent", "outcome_path_split_reasonable",
        "inertness_reasonable",
    }
    allowed = {"yes", "no", "uncertain"}
    for index, row in enumerate(audit, 1):
        if row.get("dataset_kind") != DATASET_KIND or row.get("dataset_namespace") != DATASET_NAMESPACE:
            raise PilotContractError(f"manual audit row {index} violates DEV namespace")
        if any(row.get(field) not in allowed for field in categorical):
            raise PilotContractError(f"manual audit row {index} is not fully adjudicated")
        if not isinstance(row.get("auditor_reason"), str) or not row["auditor_reason"].strip():
            raise PilotContractError(f"manual audit row {index} lacks auditor reasoning")
        if row.get("metric_values_modified") is not False:
            raise PilotContractError(f"manual audit row {index} modified metric values")

    for name in ("summary.json", "metric_distributions.json"):
        artifact = json.loads((root / "analysis" / name).read_text(encoding="utf-8"))
        if (
            artifact.get("dataset_kind") != DATASET_KIND
            or artifact.get("dataset_namespace") != DATASET_NAMESPACE
            or artifact.get("formal_experiment_status") != "NOT STARTED"
        ):
            raise PilotContractError(f"analysis artifact has invalid isolation metadata: {name}")
    report = (root / "analysis" / "PILOT_REPORT.md").read_text(encoding="utf-8")
    if "## Bias Audit" not in report or "| Metric |" not in report:
        raise PilotContractError("pilot report must contain the bias audit table")
    if "pending" in report.lower() or "Status: `NOT STARTED`" in report:
        raise PilotContractError("pilot report and bias audit are not finalized")
    readiness = {
        "FORMAL_EXPERIMENT_READY", "MINOR_MEASUREMENT_ISSUE", "MAJOR_MEASUREMENT_ISSUE",
    }
    present = [value for value in readiness if value in report]
    if len(present) != 1:
        raise PilotContractError("pilot report must contain exactly one final readiness judgment")
    bias = json.loads((root / "analysis" / "bias_audit.json").read_text(encoding="utf-8"))
    if (
        bias.get("dataset_kind") != DATASET_KIND
        or bias.get("dataset_namespace") != DATASET_NAMESPACE
        or bias.get("formal_experiment_status") != "NOT STARTED"
        or bias.get("readiness") != present[0]
    ):
        raise PilotContractError("bias audit isolation or readiness mismatch")
    questions = bias.get("required_questions")
    if not isinstance(questions, list) or [row.get("number") for row in questions] != list(range(1, 17)):
        raise PilotContractError("bias audit must answer required questions 1 through 16")
    expected_metrics = {
        "Activation", "Inertness", "Exact match", "Near-copy", "Recombination",
        "Semantic structure", "Abstract topology", "Dependency depth",
        "Necessity depth", "Outcome differentiation", "Path differentiation",
    }
    if {row.get("metric") for row in bias.get("metrics", [])} != expected_metrics:
        raise PilotContractError("bias audit metric table is incomplete")
    return {
        "raw_count": len(raw), "ingested_count": len(ingested),
        "compile_valid_count": len(compile_ids), "profile_count": len(profiles),
        "manual_audit_row_count": len(audit), "readiness": present[0],
        "genuine_provider_call_count": genuine_provider_call_count,
    }


def _freeze_bindings() -> dict[str, str]:
    gm_root = ROOT.parents[1]
    freeze_manifest = gm_root / "free_evaluation_v05" / "FREEZE_MANIFEST.json"
    semantic = validate_semantic_contract()
    return {
        "semantic_contract_digest": semantic["semantic_contract_digest"],
        "freeze_manifest_sha256": hashlib.sha256(freeze_manifest.read_bytes()).hexdigest(),
    }


def _manifest_projection(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "pilot_artifact_digest"}


def _final_digest(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(_manifest_projection(manifest)).encode("utf-8")).hexdigest()


def finalize_pilot_artifacts(root: Path = ROOT) -> dict[str, Any]:
    counts = _require_final_inputs(root)
    artifacts = [
        {
            "path": relative.as_posix(),
            "sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest(),
            "bytes": (root / relative).stat().st_size,
        }
        for relative in _all_final_artifact_paths(root)
    ]
    manifest = {
        "manifest_version": "free-v05-dev-final-artifacts-v1",
        "stage": "final",
        "dataset_kind": DATASET_KIND,
        "dataset_namespace": DATASET_NAMESPACE,
        "collection_status": "COMPLETE",
        "formal_experiment_status": "NOT STARTED",
        "formal_dataset_ingestion_allowed": False,
        "generation_protocol": GENERATION_PROTOCOL,
        "evaluation_protocol": EVALUATION_PROTOCOL,
        "freeze_commit": FREEZE_COMMIT,
        "preregistration_commit": PREREGISTRATION_COMMIT,
        **_freeze_bindings(),
        **counts,
        "artifacts": artifacts,
    }
    manifest["pilot_artifact_digest"] = _final_digest(manifest)
    output = root / FINAL_MANIFEST_RELATIVE_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    validate_pilot_artifacts(root, stage="final")
    return manifest


def _validate_final_artifacts(root: Path) -> dict[str, Any]:
    path = root / FINAL_MANIFEST_RELATIVE_PATH
    if not path.is_file():
        raise PilotContractError("final artifact manifest does not exist")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "stage": "final", "dataset_kind": DATASET_KIND,
        "dataset_namespace": DATASET_NAMESPACE, "collection_status": "COMPLETE",
        "formal_experiment_status": "NOT STARTED", "formal_dataset_ingestion_allowed": False,
        "freeze_commit": FREEZE_COMMIT, "preregistration_commit": PREREGISTRATION_COMMIT,
        "genuine_provider_call_count": 30,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise PilotContractError(f"final manifest field mismatch: {field}")
    if manifest.get("pilot_artifact_digest") != _final_digest(manifest):
        raise PilotContractError("pilot artifact digest mismatch")
    current_paths = [path.as_posix() for path in _all_final_artifact_paths(root)]
    recorded_paths = [row["path"] for row in manifest.get("artifacts", [])]
    if recorded_paths != current_paths:
        raise PilotContractError("final artifact inventory mismatch")
    for row in manifest["artifacts"]:
        artifact = root / row["path"]
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != row["sha256"]:
            raise PilotContractError(f"final artifact hash mismatch: {row['path']}")
        if artifact.stat().st_size != row["bytes"]:
            raise PilotContractError(f"final artifact size mismatch: {row['path']}")
    bindings = _freeze_bindings()
    if any(manifest.get(field) != value for field, value in bindings.items()):
        raise PilotContractError("final manifest frozen-contract binding mismatch")
    counts = _require_final_inputs(root)
    if any(manifest.get(field) != value for field, value in counts.items()):
        raise PilotContractError("final manifest count or readiness mismatch")
    return {
        "status": "VALID", "stage": "final", "dataset_kind": DATASET_KIND,
        "dataset_namespace": DATASET_NAMESPACE,
        "artifact_count": len(recorded_paths),
        "pilot_artifact_digest": manifest["pilot_artifact_digest"],
        "formal_dataset_ingestion_allowed": False,
    }


def validate_pilot_artifacts(root: Path = ROOT, *, stage: str = "auto") -> dict[str, Any]:
    if stage not in {"auto", "preregistration", "final"}:
        raise PilotContractError("validation stage must be auto, preregistration, or final")
    final_exists = (root / FINAL_MANIFEST_RELATIVE_PATH).is_file()
    if stage == "final" or (stage == "auto" and final_exists):
        return _validate_final_artifacts(root)
    return _validate_preregistration_artifacts(root)


def main() -> int:
    print(canonical_json(validate_pilot_artifacts()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
