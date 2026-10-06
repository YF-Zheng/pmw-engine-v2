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
from pathlib import Path
import statistics
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


def validate_pilot_artifacts(root: Path = ROOT) -> dict[str, Any]:
    requests_path = root / "requests" / "canonical_requests.jsonl"
    rows = read_jsonl(requests_path)
    _validate_requests(rows)
    manifest = json.loads((root / "manifest" / "artifact_manifest.json").read_text(encoding="utf-8"))
    if manifest["dataset_kind"] != DATASET_KIND or manifest["dataset_namespace"] != DATASET_NAMESPACE:
        raise PilotContractError("artifact manifest is not bound to the DEV namespace")
    for item in manifest["artifacts"]:
        path = root / item["path"]
        if not path.is_file():
            raise PilotContractError(f"missing artifact: {item['path']}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != item["sha256"]:
            raise PilotContractError(f"artifact hash mismatch: {item['path']}")
    contract = validate_semantic_contract()
    if contract["semantic_contract_digest"] != manifest["v05_semantic_contract_digest"]:
        raise PilotContractError("frozen v0.5 semantic contract digest drift")
    return {
        "status": "VALID", "dataset_kind": DATASET_KIND,
        "dataset_namespace": DATASET_NAMESPACE, "canonical_request_count": len(rows),
        "artifact_count": len(manifest["artifacts"]),
        "formal_dataset_ingestion_allowed": False,
    }


def main() -> int:
    print(canonical_json(validate_pilot_artifacts()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
