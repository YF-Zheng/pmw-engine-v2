"""Pre-collection infrastructure for the formal Free-Invention experiment.

This module has deliberately no provider client.  It creates immutable request
coordinates and analysis artifacts, and fails closed until the three owner
gates have been resolved and the preregistration has been frozen.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import hmac
import io
from itertools import combinations, permutations as label_permutations, product
import json
import math
from pathlib import Path
import random
import statistics
from typing import Any, Iterable, Mapping, Sequence

from .compiler import canonical_json
from .free_invention import (
    PROTOCOL_VERSION as GENERATION_PROTOCOL,
    derive_identity,
    prompt_hash,
    prompt_request,
)
from .generation import render_prompt
from .formal_statistics import (
    PRIMARY_ENDPOINTS as STATISTICAL_PRIMARY_ENDPOINTS,
    benjamini_hochberg_adjust,
    endpoint_estimate,
    holm_adjust,
    matched_pairwise_bootstrap,
    percentile_bootstrap,
    within_block_permutation_omnibus,
)


EVALUATION_PROTOCOL = "gm-free-evaluation-v0.5"
BASELINE = "world_substrate"
FORMAL_DATASET_KIND = "formal"
NOT_SENT = "NOT_SENT"
NON_FORMAL_TEST_RUN = "NON_FORMAL_TEST_RUN"
MAX_TRANSPORT_ATTEMPTS = 3
OWNER_GATE_FIELDS = (
    "model_matrix",
    "samples_per_model",
    "inference_budget_policy",
)
PRIMARY_ENDPOINTS = (
    "end_to_end_executable_validity",
    "activation_rate",
    "median_realized_dependency_depth",
    "abstract_topology_collision_probability",
    "outcome_differentiation_rate",
    "path_differentiation_rate",
)
SECONDARY_ENDPOINTS = (
    "schema_validity",
    "compile_validity",
    "behavioral_inertness",
    "necessity_backed_depth",
    "depth_gap",
    "possible_redundant_causation",
    "semantic_structure_collision_probability",
    "exact_match",
    "near_copy",
    "recombination",
    "outcome_path_quadrants",
)
FORBIDDEN_AGGREGATES = frozenset({
    "creativity_score", "creativity_total", "total_creativity_score",
    "overall_creativity", "aggregate_creativity_rank",
})
NON_FORMAL_KINDS = frozenset({"dev_pilot", "fixture", "adversarial", "calibration"})
TERMINAL_FAILURE_CLASSES = frozenset({
    "transport_failure", "provider_failure", "safety_refusal", "empty_response",
    "malformed_json", "schema_invalid", "compile_invalid", "execution_invalid", "valid",
})


class FormalExperimentError(ValueError):
    """A formal preregistration, collection, or analysis contract failed."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _gate_value(decisions: Mapping[str, Any], name: str) -> Any:
    value = decisions.get(name)
    if value is None or value == "OWNER_DECISION_REQUIRED" or value == []:
        raise FormalExperimentError(f"owner gate unresolved: {name}")
    return value


def require_owner_gates(decisions: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the minimum owner choices without silently choosing defaults."""
    result = {name: _gate_value(decisions, name) for name in OWNER_GATE_FIELDS}
    models = result["model_matrix"]
    if not isinstance(models, list) or len(models) not in {4, 5, 6} or not all(isinstance(x, str) and x for x in models):
        raise FormalExperimentError("model_matrix must be a selected 4/5/6-model candidate")
    if len(set(models)) != len(models):
        raise FormalExperimentError("model_matrix contains duplicate model IDs")
    size = result["samples_per_model"]
    if isinstance(size, bool) or size not in {100, 150, 200}:
        raise FormalExperimentError("samples_per_model must be one of 100, 150, or 200")
    if result["inference_budget_policy"] not in {
        "system_level_configuration", "matched_inference_budget",
    }:
        raise FormalExperimentError("unknown inference_budget_policy")
    return result


def require_collection_ready(
    registry: Mapping[str, Any], *, manifest_bytes: bytes, schedule_bytes: bytes,
) -> dict[str, Any]:
    """Fail before any collection action unless gates and freeze are explicit."""
    free = registry.get("free_invention")
    if not isinstance(free, Mapping):
        raise FormalExperimentError("registry.free_invention is required")
    decisions = require_owner_gates(free)
    if registry.get("preregistration_frozen", free.get("preregistration_frozen")) is not True:
        raise FormalExperimentError("preregistration is not frozen")
    if not registry.get("preregistration_tag", free.get("preregistration_tag")):
        raise FormalExperimentError("preregistration freeze tag is missing")
    if registry.get("formal_collection_started") is not True:
        raise FormalExperimentError("formal collection is not owner-authorized")
    expected_manifest = free.get("formal_request_manifest_sha256", registry.get("formal_request_manifest_sha256"))
    expected_schedule = free.get("collection_schedule_sha256", registry.get("collection_schedule_sha256"))
    if not expected_manifest or _sha256_bytes(manifest_bytes) != expected_manifest:
        raise FormalExperimentError("final request manifest hash is missing or mismatched")
    if not expected_schedule or _sha256_bytes(schedule_bytes) != expected_schedule:
        raise FormalExperimentError("final collection schedule hash is missing or mismatched")
    return decisions


def _formal_identity(experiment_id: str, model_id: str, base_index: int) -> tuple[str, str]:
    digest = _sha256_text(f"formal-request|{experiment_id}|{model_id}|{base_index}")
    formal_id = f"formal-mechanism.{base_index:04d}.{digest[:16]}"
    request_id = f"formal-request.{digest[16:48]}"
    return formal_id, request_id


def deterministic_collection_schedule(
    model_ids: Sequence[str], samples_per_model: int, collection_order_seed: int,
) -> tuple[dict[str, Any], ...]:
    """Return block-interleaved order, with an independently shuffled model order per block."""
    if len(set(model_ids)) != len(model_ids) or len(model_ids) < 2:
        raise FormalExperimentError("schedule requires at least two unique models")
    if samples_per_model < 1:
        raise FormalExperimentError("samples_per_model must be positive")
    rows: list[dict[str, Any]] = []
    for base_index in range(samples_per_model):
        order = list(model_ids)
        block_seed = int(_sha256_text(f"{collection_order_seed}|{base_index}")[:16], 16)
        random.Random(block_seed).shuffle(order)
        for position, model_id in enumerate(order):
            rows.append({
                "collection_sequence": len(rows),
                "base_sample_index": base_index,
                "within_block_position": position,
                "model_id": model_id,
            })
    return tuple(rows)


def build_formal_request_manifest(
    decisions: Mapping[str, Any], *, formal_experiment_id: str,
    collection_order_seed: int, master_seed: int,
    dev_exclusion_registry: Iterable[Any] | None,
    provider_request_configs: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], ...]:
    """Build the final request manifest after, and only after, owner decisions.

    A generation identity belongs to a matched base sample and is intentionally
    shared across models so v0.3 renders exactly the same visible prompt.  The
    outer formal_sample_id and request_id remain unique per generated mechanism.
    """
    gates = require_owner_gates(decisions)
    if dev_exclusion_registry is None:
        raise FormalExperimentError("DEV exclusion registry is required")
    excluded = {str(item) for item in dev_exclusion_registry}
    if not excluded:
        raise FormalExperimentError("DEV exclusion registry must not be empty")
    if provider_request_configs is None or set(provider_request_configs) != set(gates["model_matrix"]):
        raise FormalExperimentError("exact provider request config is required for every model")
    schedule = deterministic_collection_schedule(
        gates["model_matrix"], gates["samples_per_model"], collection_order_seed,
    )
    schedule_by_coordinate = {
        (row["base_sample_index"], row["model_id"]): row for row in schedule
    }
    rows = []
    for base_index in range(gates["samples_per_model"]):
        generation_id, seed, nonce = derive_identity(master_seed, BASELINE, base_index)
        request_object = prompt_request(BASELINE, seed, generation_id, nonce)
        visible_prompt = render_prompt(request_object)
        visible_sha = prompt_hash(request_object)
        for model_id in gates["model_matrix"]:
            formal_id, request_id = _formal_identity(formal_experiment_id, model_id, base_index)
            schedule_row = schedule_by_coordinate[(base_index, model_id)]
            provider_config = dict(provider_request_configs[model_id])
            if not provider_config or provider_config.get("model_id") != model_id:
                raise FormalExperimentError(f"provider request config is incomplete for {model_id}")
            full_request = {
                "formal_experiment_id": formal_experiment_id,
                "formal_sample_id": formal_id,
                "request_id": request_id,
                "provider_request_config": provider_config,
                "visible_prompt": visible_prompt,
            }
            row = {
                "formal_experiment_id": formal_experiment_id,
                "dataset_kind": FORMAL_DATASET_KIND,
                "collection_status": NOT_SENT,
                "model_id": model_id,
                "base_sample_index": base_index,
                "formal_sample_id": formal_id,
                "sample_id": generation_id,
                "generation_sample_id": generation_id,
                "nonce": nonce,
                "canonical_seed": seed,
                "request_coordinates": {"master_seed": master_seed, "sample_index": base_index},
                "request_id": request_id,
                "visible_prompt": visible_prompt,
                "visible_prompt_sha256": visible_sha,
                "full_request_sha256": _sha256_text(canonical_json(full_request)),
                "provider_request_config": provider_config,
                "canonical_full_request": full_request,
                "generation_protocol": GENERATION_PROTOCOL,
                "evaluation_protocol": EVALUATION_PROTOCOL,
                "baseline": BASELINE,
                "inference_budget_policy": gates["inference_budget_policy"],
                "collection_order_seed": collection_order_seed,
                "selected_model_matrix": list(gates["model_matrix"]),
                "samples_per_model": gates["samples_per_model"],
                "master_seed": master_seed,
                "collection_sequence": schedule_row["collection_sequence"],
                "within_block_position": schedule_row["within_block_position"],
            }
            for value in (formal_id, request_id, generation_id, nonce, seed):
                if str(value) in excluded:
                    raise FormalExperimentError("formal identity overlaps an excluded DEV identity")
            rows.append(row)
    validate_request_manifest(rows)
    return tuple(sorted(rows, key=lambda row: row["collection_sequence"]))


def build_dry_manifest_example() -> tuple[dict[str, Any], ...]:
    """Return a non-runnable schema example using conspicuous placeholder models."""
    models = ["PLACEHOLDER_MODEL_ALPHA", "PLACEHOLDER_MODEL_BETA"]
    rows = []
    for schedule in deterministic_collection_schedule(models, 2, 0):
        index = schedule["base_sample_index"]
        generation_id, seed, nonce = derive_identity(0, BASELINE, index)
        request = prompt_request(BASELINE, seed, generation_id, nonce)
        formal_id, request_id = _formal_identity("DRY-RUN-NOT-A-FORMAL-COLLECTION", schedule["model_id"], index)
        rows.append({
            "formal_experiment_id": "DRY-RUN-NOT-A-FORMAL-COLLECTION",
            "dataset_kind": "synthetic_mock",
            "record_kind": "synthetic_mock",
            "collection_status": NOT_SENT,
            "sendable": False,
            "dry_manifest_example": True,
            "model_id": schedule["model_id"],
            "base_sample_index": index,
            "formal_sample_id": formal_id,
            "sample_id": generation_id,
            "generation_sample_id": generation_id,
            "nonce": nonce,
            "canonical_seed": seed,
            "request_coordinates": {"master_seed": 0, "sample_index": index},
            "request_id": request_id,
            "visible_prompt": render_prompt(request),
            "visible_prompt_sha256": prompt_hash(request),
            "full_request_sha256": None,
            "generation_protocol": GENERATION_PROTOCOL,
            "evaluation_protocol": EVALUATION_PROTOCOL,
            "baseline": BASELINE,
            "inference_budget_policy": "PLACEHOLDER_OWNER_POLICY",
            "collection_order_seed": 0,
            "selected_model_matrix": models,
            "samples_per_model": 2,
            "master_seed": 0,
            "collection_sequence": schedule["collection_sequence"],
            "within_block_position": schedule["within_block_position"],
        })
    validate_request_manifest(rows, allow_synthetic_mock=True)
    return tuple(sorted(rows, key=lambda row: row["collection_sequence"]))


def validate_request_manifest(
    rows: Iterable[Mapping[str, Any]], *, allow_synthetic_mock: bool = False,
) -> dict[str, Any]:
    rows = tuple(rows)
    if not rows:
        raise FormalExperimentError("formal request manifest is empty")
    is_dry = all(row.get("record_kind") == "synthetic_mock" for row in rows)
    if is_dry != allow_synthetic_mock:
        raise FormalExperimentError("synthetic mock manifest requires explicit validation mode")
    unique_fields = ("formal_sample_id", "request_id")
    if not is_dry:
        unique_fields += ("full_request_sha256",)
    for field in unique_fields:
        values = [row.get(field) for row in rows]
        if None in values or len(values) != len(set(values)):
            raise FormalExperimentError(f"manifest field must be globally unique: {field}")
    blocks: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        expected_kind = "synthetic_mock" if is_dry else FORMAL_DATASET_KIND
        if row.get("dataset_kind") != expected_kind or row.get("collection_status") != NOT_SENT:
            raise FormalExperimentError(f"request rows must be {expected_kind}/NOT_SENT")
        if row.get("generation_protocol") != GENERATION_PROTOCOL:
            raise FormalExperimentError("wrong generation protocol")
        if row.get("evaluation_protocol") != EVALUATION_PROTOCOL:
            raise FormalExperimentError("wrong evaluation protocol")
        if _sha256_text(str(row["visible_prompt"])) != row["visible_prompt_sha256"]:
            raise FormalExperimentError("visible prompt hash mismatch")
        if not is_dry:
            full_request = row.get("canonical_full_request")
            if not isinstance(full_request, Mapping):
                raise FormalExperimentError("canonical full provider request is missing")
            if full_request.get("provider_request_config") != row.get("provider_request_config"):
                raise FormalExperimentError("provider config is not bound into canonical full request")
            if _sha256_text(canonical_json(full_request)) != row["full_request_sha256"]:
                raise FormalExperimentError("canonical full request hash mismatch")
        blocks[int(row["base_sample_index"])].append(row)
    matrices = {tuple(row.get("selected_model_matrix", ())) for row in rows}
    sample_counts = {row.get("samples_per_model") for row in rows}
    master_seeds = {row.get("master_seed") for row in rows}
    if len(matrices) != 1 or len(sample_counts) != 1 or len(master_seeds) != 1:
        raise FormalExperimentError("manifest design coordinates are inconsistent")
    selected_matrix = next(iter(matrices))
    samples_per_model = next(iter(sample_counts))
    if (
        not selected_matrix
        or len(selected_matrix) != len(set(selected_matrix))
        or isinstance(samples_per_model, bool)
        or not isinstance(samples_per_model, int)
        or samples_per_model < 1
    ):
        raise FormalExperimentError("manifest design coordinates are invalid")
    expected_models = set(selected_matrix)
    if {row["model_id"] for row in rows} != expected_models:
        raise FormalExperimentError("manifest model set differs from selected model matrix")
    if set(blocks) != set(range(samples_per_model)):
        raise FormalExperimentError("manifest base-sample blocks are incomplete")
    generation_tuples = set()
    for block_rows in blocks.values():
        block_models = [row["model_id"] for row in block_rows]
        if len(block_models) != len(set(block_models)) or set(block_models) != expected_models:
            raise FormalExperimentError("each block must contain every model exactly once")
        for field in ("generation_sample_id", "nonce", "canonical_seed", "visible_prompt_sha256", "visible_prompt"):
            if len({row[field] for row in block_rows}) != 1:
                raise FormalExperimentError(f"matched block differs in {field}")
        if not is_dry and len({row["full_request_sha256"] for row in block_rows}) != len(block_rows):
            raise FormalExperimentError("model-specific full requests are not unique")
        generation_tuples.add((
            block_rows[0]["generation_sample_id"], block_rows[0]["nonce"],
            block_rows[0]["canonical_seed"],
        ))
    if len(generation_tuples) != len(blocks):
        raise FormalExperimentError("generation coordinates repeat across base samples")
    sequence = sorted(int(row["collection_sequence"]) for row in rows)
    if sequence != list(range(len(rows))):
        raise FormalExperimentError("collection schedule is not contiguous")
    return {
        "status": "VALID", "request_count": len(rows), "block_count": len(blocks),
        "model_visible_prompt_matching": "EXACT",
    }


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> str:
    content = "".join(canonical_json(dict(row)) + "\n" for row in rows)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return _sha256_text(content)


def validate_formal_dataset(rows: Iterable[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    rows = tuple(rows)
    for row in rows:
        kind = row.get("dataset_kind")
        if kind != FORMAL_DATASET_KIND:
            raise FormalExperimentError(f"formal analysis rejects dataset_kind={kind!r}")
    return rows


def retry_action(failure_class: str, completed_attempts: int) -> str:
    """Return the only allowed next action for a first-response collection."""
    if completed_attempts < 1:
        raise FormalExperimentError("completed_attempts must be positive")
    if failure_class == "transport_failure" and completed_attempts < MAX_TRANSPORT_ATTEMPTS:
        return "RETRY_SAME_REQUEST"
    if failure_class == "transport_failure":
        return "STOP_TRANSPORT_EXHAUSTED"
    return "STOP_RETAIN_FIRST_CONTENT"


def validate_transport_attempts(attempts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    attempts = tuple(attempts)
    if not attempts or len(attempts) > MAX_TRANSPORT_ATTEMPTS:
        raise FormalExperimentError("transport attempt count outside preregistered bounds")
    request_ids = {row.get("request_id") for row in attempts}
    request_hashes = {row.get("full_request_sha256") for row in attempts}
    if len(request_ids) != 1 or len(request_hashes) != 1:
        raise FormalExperimentError("transport retry changed the exact request")
    expected = list(range(1, len(attempts) + 1))
    if [row.get("attempt") for row in attempts] != expected:
        raise FormalExperimentError("transport attempts must be consecutive")
    if any(row.get("failure_class") != "transport_failure" for row in attempts[:-1]):
        raise FormalExperimentError("content/provider response cannot be retried")
    return {"status": "VALID", "attempt_count": len(attempts)}


def create_blinding_mapping(model_ids: Sequence[str], seed: int) -> dict[str, str]:
    if len(set(model_ids)) != len(model_ids):
        raise FormalExperimentError("cannot blind duplicate model IDs")
    shuffled = list(model_ids)
    random.Random(seed).shuffle(shuffled)
    return {model_id: f"Model {chr(65 + index)}" for index, model_id in enumerate(shuffled)}


def seal_blinding_mapping(
    path: str | Path, mapping: Mapping[str, str], *, seal_key: bytes,
) -> dict[str, Any]:
    """Write an integrity-sealed, access-restricted mapping for an unblinding custodian."""
    if not seal_key:
        raise FormalExperimentError("seal_key is required")
    payload = canonical_json(dict(mapping)).encode("utf-8")
    envelope = {
        "format": "owner-custodied-integrity-sealed-v1",
        "mapping": dict(mapping),
        "payload_sha256": _sha256_bytes(payload),
        "hmac_sha256": hmac.new(seal_key, payload, hashlib.sha256).hexdigest(),
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(envelope) + "\n", encoding="utf-8")
    output.chmod(0o600)
    return {"path": str(output), "payload_sha256": envelope["payload_sha256"]}


def unseal_blinding_mapping(path: str | Path, *, seal_key: bytes) -> dict[str, str]:
    envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    payload = canonical_json(envelope["mapping"]).encode("utf-8")
    expected = hmac.new(seal_key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, envelope.get("hmac_sha256", "")):
        raise FormalExperimentError("blinding mapping seal verification failed")
    if _sha256_bytes(payload) != envelope.get("payload_sha256"):
        raise FormalExperimentError("blinding mapping payload hash mismatch")
    return dict(envelope["mapping"])


def apply_blinding(rows: Iterable[Mapping[str, Any]], mapping: Mapping[str, str]) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        model = row.get("model_id")
        if model not in mapping:
            raise FormalExperimentError(f"model missing from blind mapping: {model!r}")
        blinded = dict(row)
        blinded["model_blind_label"] = mapping[model]
        blinded.pop("model_id", None)
        result.append(blinded)
    return tuple(result)


def build_raw_data_manifest(root: str | Path, relative_paths: Iterable[str | Path]) -> dict[str, Any]:
    root = Path(root).resolve()
    files = []
    for relative in sorted(str(Path(path)) for path in relative_paths):
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise FormalExperimentError(f"raw artifact missing or outside root: {relative}")
        data = path.read_bytes()
        files.append({"path": relative, "sha256": _sha256_bytes(data), "bytes": len(data)})
    categories = {Path(row["path"]).parts[0] for row in files if Path(row["path"]).parts}
    required = {"raw_requests", "raw_provider_responses"}
    if not required <= categories:
        raise FormalExperimentError("raw manifest requires raw_requests and raw_provider_responses artifacts")
    return {"schema_version": 1, "immutable_raw_layer": True, "files": files}


def validate_raw_data_manifest(root: str | Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    if manifest.get("immutable_raw_layer") is not True:
        raise FormalExperimentError("raw manifest must declare immutable_raw_layer")
    expected = build_raw_data_manifest(root, (row["path"] for row in manifest.get("files", [])))
    if expected != manifest:
        raise FormalExperimentError("raw artifact hash/size mismatch")
    return {"status": "VALID", "file_count": len(expected["files"])}


def validate_formal_lineage(
    rows: Iterable[Mapping[str, Any]], raw_manifest: Mapping[str, Any], *,
    artifact_root: str | Path,
) -> dict[str, Any]:
    stages = (
        "raw_request", "raw_provider_response", "parsed_response", "skill_spec",
        "compiled_mechanic", "execution_trace", "profile", "analysis_row",
    )
    root = Path(artifact_root).resolve()
    raw_index = {row["path"]: row["sha256"] for row in raw_manifest.get("files", [])}
    count = 0
    for row in validate_formal_dataset(rows):
        lineage = row.get("lineage")
        if not isinstance(lineage, Mapping):
            raise FormalExperimentError("lineage descriptor map is required")
        parent_hash = None
        for index, stage in enumerate(stages):
            descriptor = lineage.get(stage)
            if not isinstance(descriptor, Mapping):
                raise FormalExperimentError(f"lineage stage missing: {stage}")
            relative = descriptor.get("path")
            digest = descriptor.get("sha256")
            if not isinstance(relative, str) or not isinstance(digest, str) or len(digest) != 64:
                raise FormalExperimentError(f"invalid lineage descriptor: {stage}")
            try:
                int(digest, 16)
            except ValueError as exc:
                raise FormalExperimentError(f"invalid SHA-256 in lineage stage: {stage}") from exc
            path = (root / relative).resolve()
            if root not in path.parents or not path.is_file() or _sha256_bytes(path.read_bytes()) != digest:
                raise FormalExperimentError(f"lineage artifact hash mismatch: {stage}")
            if index < 2:
                expected_prefix = "raw_requests/" if stage == "raw_request" else "raw_provider_responses/"
                if not relative.startswith(expected_prefix) or raw_index.get(relative) != digest:
                    raise FormalExperimentError(f"raw lineage stage is not manifest-linked: {stage}")
            if parent_hash is not None and descriptor.get("parent_sha256") != parent_hash:
                raise FormalExperimentError(f"lineage parent hash mismatch: {stage}")
            parent_hash = digest
        if not row.get("paper_statistic_ids"):
            raise FormalExperimentError("lineage row requires paper_statistic_ids")
        count += 1
    return {"status": "VALID", "mechanism_count": count}


def _collision_probability(values: Sequence[Any]) -> float | None:
    if len(values) < 2:
        return None
    counts = Counter(values)
    collisions = sum(count * (count - 1) // 2 for count in counts.values())
    return collisions / (len(values) * (len(values) - 1) / 2)


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _mean(values: Sequence[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


def _omnibus_mean_statistic(groups: Mapping[str, Sequence[float]]) -> float | None:
    populated = {name: tuple(values) for name, values in groups.items() if values}
    if len(populated) < 2:
        return None
    pooled = [value for values in populated.values() for value in values]
    grand = _mean(pooled)
    assert grand is not None
    return math.fsum(len(values) * ((_mean(values) or 0.0) - grand) ** 2 for values in populated.values())


def _within_block_field_permutation_omnibus(
    mechanisms: Sequence[Mapping[str, Any]], models: Sequence[str], field: str, *,
    seed: int = 20261007, permutations: int = 100_000,
) -> dict[str, Any]:
    """Permutation omnibus for exploratory scalar fields, preserving matched blocks."""
    if isinstance(permutations, bool) or not isinstance(permutations, int) or permutations < 1:
        raise FormalExperimentError("permutations must be a positive integer")
    model_order = tuple(models)
    grouped: dict[Any, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in mechanisms:
        block = row.get("base_sample_index")
        model = row.get("model_id")
        if block is None or model not in model_order:
            continue
        if model in grouped[block]:
            raise FormalExperimentError(f"duplicate model row in base_sample_index {block!r}")
        grouped[block][str(model)] = row
    blocks = tuple(
        tuple(grouped[block][model] for model in model_order)
        for block in sorted(grouped, key=lambda value: (str(type(value)), str(value)))
        if set(grouped[block]) == set(model_order)
    )

    def statistic(block_rows: Sequence[Sequence[Mapping[str, Any]]]) -> float | None:
        values: dict[str, list[float]] = defaultdict(list)
        for block in block_rows:
            for index, model in enumerate(model_order):
                value = block[index].get(field)
                if value is not None:
                    values[model].append(float(value))
        return _omnibus_mean_statistic(values)

    observed = statistic(blocks)
    base = {
        "endpoint": field,
        "test": "within_block_permutation_omnibus_between_model_means",
        "analysis_unit": "generated_mechanism",
        "permutation_unit": "labels_within_base_sample_index_block",
        "complete_block_count": len(blocks),
        "observed_statistic": observed,
        "seed": seed,
    }
    if not blocks or observed is None:
        return base | {"status": "NOT_ESTIMABLE", "p_value": None, "permutations_evaluated": 0, "exact": False}

    assignments = tuple(label_permutations(range(len(model_order))))
    exact_count = len(assignments) ** len(blocks)

    def permuted_statistic(assignment_set: Sequence[Sequence[int]]) -> float | None:
        permuted_blocks = tuple(
            tuple(block[source] for source in assignment)
            for block, assignment in zip(blocks, assignment_set)
        )
        return statistic(permuted_blocks)

    exceedances = 0
    evaluated = 0
    exact = exact_count <= permutations
    if exact:
        iterator = product(assignments, repeat=len(blocks))
    else:
        randomizer = random.Random(seed + int(_sha256_text(field)[:8], 16))
        iterator = (
            tuple(assignments[randomizer.randrange(len(assignments))] for _ in blocks)
            for _ in range(permutations)
        )
    for assignment_set in iterator:
        value = permuted_statistic(assignment_set)
        if value is not None:
            evaluated += 1
            if value >= observed - 1e-15:
                exceedances += 1
    p_value = (
        exceedances / evaluated if exact and evaluated
        else (exceedances + 1) / (evaluated + 1) if evaluated
        else None
    )
    return base | {
        "status": "ESTIMATED" if p_value is not None else "NOT_ESTIMABLE",
        "p_value": p_value,
        "permutations_evaluated": evaluated,
        "exact": exact,
        "admissible_permutations": exact_count,
    }


def _mechanism_analysis_row(row: Mapping[str, Any]) -> dict[str, Any]:
    for field in ("schema_valid", "compile_valid", "execution_valid"):
        if not isinstance(row.get(field), bool):
            raise FormalExperimentError(f"{field} must be boolean")
    if row["compile_valid"] and not row["schema_valid"]:
        raise FormalExperimentError("validity chain violation: compile valid without schema valid")
    if row["execution_valid"] and not row["compile_valid"]:
        raise FormalExperimentError("validity chain violation: execution valid without compile valid")
    valid = bool(row.get("execution_valid"))
    profile = row.get("profile") if isinstance(row.get("profile"), Mapping) else {}
    dynamic = profile.get("dynamic_reach", {}) if valid else {}
    conditional = dynamic.get("conditional_on_activation", {})
    environment = profile.get("environmental_behavior", {}) if valid else {}
    structural = profile.get("structural_evidence", {}) if valid else {}
    contexts = environment.get("contexts", [])
    if valid:
        if dynamic.get("registered_arm_count") != 24:
            raise FormalExperimentError("execution-valid profile must contain exactly 24 registered arms")
        if len(contexts) != 6 or environment.get("context_count", 6) != 6:
            raise FormalExperimentError("execution-valid profile must contain exactly 6 registered contexts")
        if any(
            not isinstance(context.get(field), bool)
            for context in contexts
            for field in ("outcome_differentiated", "causal_path_differentiated")
        ):
            raise FormalExperimentError("context differentiation fields must be boolean")
        activation_rate = dynamic.get("activation_rate")
        if not isinstance(activation_rate, (int, float)) or isinstance(activation_rate, bool) or not 0 <= activation_rate <= 1:
            raise FormalExperimentError("activation_rate must be numeric in [0,1]")
    realized = conditional.get("realized_dependency_depth_distribution", [])
    necessity = conditional.get("necessity_backed_depth_distribution", [])
    gaps = conditional.get("depth_gap_distribution", [])
    quadrants = Counter()
    for context in contexts:
        outcome = bool(context.get("outcome_differentiated"))
        path = bool(context.get("causal_path_differentiated"))
        quadrants[f"{'different' if outcome else 'same'}_outcome__{'different' if path else 'same'}_path"] += 1
    return {
        "dataset_kind": row.get("dataset_kind"),
        "formal_sample_id": row.get("formal_sample_id", row.get("sample_id")),
        "model_id": row.get("model_blind_label", row.get("model_id")),
        "base_sample_index": row.get("base_sample_index"),
        "failure_class": row.get("failure_class"),
        "collection_time_block": row.get("collection_time_block"),
        "schema_valid": bool(row.get("schema_valid")),
        "compile_valid": bool(row.get("compile_valid")),
        "execution_valid": valid,
        "activation_rate": dynamic.get("activation_rate") if valid else None,
        "arm_count": dynamic.get("registered_arm_count") if valid else None,
        "median_realized_dependency_depth": _median(realized) if valid else None,
        "max_realized_dependency_depth": max(realized, default=None) if valid else None,
        "median_necessity_backed_depth": _median(necessity) if valid else None,
        "mean_depth_gap": _mean(gaps) if valid else None,
        "outcome_differentiation_rate": (
            sum(x["outcome_differentiated"] for x in contexts) / 6
            if valid else None
        ),
        "path_differentiation_rate": (
            sum(x["causal_path_differentiated"] for x in contexts) / 6
            if valid else None
        ),
        "semantic_fingerprint": structural.get("semantic_structure", {}).get("fingerprint") if valid else None,
        "abstract_fingerprint": structural.get("abstract_topology", {}).get("fingerprint") if valid else None,
        "behaviorally_inert": profile.get("behavioral_inertness", {}).get("behaviorally_inert") if valid else None,
        "exact_match": structural.get("exact_match") if valid else None,
        "near_copy": structural.get("near_copy") if valid else None,
        "recombination": structural.get("recombination", {}).get("recombination_detected") if valid else None,
        "outcome_path_quadrants": dict(quadrants) if valid else None,
    }


def analyze_free_invention(
    rows: Iterable[Mapping[str, Any]], *, non_formal_test_run: bool = False,
    manifest_rows: Iterable[Mapping[str, Any]] | None = None,
    raw_manifest: Mapping[str, Any] | None = None,
    artifact_root: str | Path | None = None,
    bootstrap_replicates: int = 10_000,
    permutation_replicates: int = 100_000,
) -> dict[str, Any]:
    """Run the frozen mechanism-level analysis; arms are repeated observations only."""
    rows = tuple(rows)
    kinds = {row.get("dataset_kind") for row in rows}
    if kinds != {FORMAL_DATASET_KIND}:
        if not non_formal_test_run or not kinds or not kinds <= NON_FORMAL_KINDS:
            raise FormalExperimentError(f"formal analyzer rejects dataset kinds: {sorted(map(str, kinds))}")
        run_status = NON_FORMAL_TEST_RUN
    else:
        if any(row.get("record_kind") == "synthetic_mock" or row.get("dry_manifest_example") for row in rows):
            raise FormalExperimentError("synthetic mock rows cannot enter formal analysis")
        if manifest_rows is None or raw_manifest is None or artifact_root is None:
            raise FormalExperimentError("formal analysis requires frozen manifest membership and raw lineage")
        manifest = tuple(manifest_rows)
        validate_request_manifest(manifest)
        issued = {
            (row["formal_sample_id"], row["request_id"]): row for row in manifest
        }
        observed_keys = []
        for row in rows:
            key = (row.get("formal_sample_id"), row.get("request_id"))
            if key not in issued:
                raise FormalExperimentError("analysis row is not a member of the frozen request manifest")
            observed_keys.append(key)
        if len(observed_keys) != len(set(observed_keys)):
            raise FormalExperimentError("formal analysis contains duplicate request rows")
        if set(observed_keys) != set(issued):
            raise FormalExperimentError("formal analysis must account for every frozen request")
        for row in rows:
            failure_class = row.get("failure_class")
            if failure_class not in TERMINAL_FAILURE_CLASSES:
                raise FormalExperimentError("formal row has an invalid terminal failure_class")
            if (failure_class == "valid") != (row.get("execution_valid") is True):
                raise FormalExperimentError("failure_class and execution validity disagree")
        validate_raw_data_manifest(artifact_root, raw_manifest)
        validate_formal_lineage(rows, raw_manifest, artifact_root=artifact_root)
        run_status = "FORMAL_ANALYSIS"
    mechanisms = tuple(_mechanism_analysis_row(row) for row in rows)
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in mechanisms:
        if not row["formal_sample_id"] or not row["model_id"]:
            raise FormalExperimentError("analysis rows require mechanism and model identity")
        by_model[row["model_id"]].append(row)
    profiles = []
    for model, model_rows in sorted(by_model.items()):
        valid = [row for row in model_rows if row["execution_valid"]]
        intervals = {
            endpoint: percentile_bootstrap(
                model_rows, endpoint, replicates=bootstrap_replicates,
            )
            for endpoint in STATISTICAL_PRIMARY_ENDPOINTS
        }
        profiles.append({
            "model_id": model,
            "requested_mechanism_count": len(model_rows),
            "schema_validity": _mean([float(row["schema_valid"]) for row in model_rows]),
            "compile_validity": _mean([float(row["compile_valid"]) for row in model_rows]),
            "end_to_end_executable_validity": _mean([float(row["execution_valid"]) for row in model_rows]),
            "activation_rate": _mean([row["activation_rate"] for row in valid if row["activation_rate"] is not None]),
            "median_realized_dependency_depth": _median([row["median_realized_dependency_depth"] for row in valid if row["median_realized_dependency_depth"] is not None]),
            "outcome_differentiation_rate": _mean([row["outcome_differentiation_rate"] for row in valid if row["outcome_differentiation_rate"] is not None]),
            "path_differentiation_rate": _mean([row["path_differentiation_rate"] for row in valid if row["path_differentiation_rate"] is not None]),
            "abstract_topology_collision_probability": _collision_probability([row["abstract_fingerprint"] for row in valid if row["abstract_fingerprint"]]),
            "semantic_structure_collision_probability": _collision_probability([row["semantic_fingerprint"] for row in valid if row["semantic_fingerprint"]]),
            "primary_endpoint_intervals": intervals,
        })
    primary = {
        "analysis_unit": "generated_mechanism",
        "endpoints": list(PRIMARY_ENDPOINTS),
        "model_profiles": profiles,
    }
    secondary = {
        "analysis_unit": "generated_mechanism",
        "endpoints": list(SECONDARY_ENDPOINTS),
        "reference_relative_status": "SECONDARY_DIAGNOSTIC_ONLY",
        "mechanism_rows": list(mechanisms),
    }
    models = sorted(by_model)
    omnibus = (
        [
            within_block_permutation_omnibus(
                mechanisms, models, endpoint, permutations=permutation_replicates,
            )
            for endpoint in STATISTICAL_PRIMARY_ENDPOINTS
        ]
        if len(models) >= 2
        else [
            {
                "endpoint": endpoint,
                "analysis_unit": "generated_mechanism",
                "status": "NOT_ESTIMABLE",
                "reason": "fewer than two model groups",
                "p_value": None,
            }
            for endpoint in STATISTICAL_PRIMARY_ENDPOINTS
        ]
    )
    omnibus_adjusted = holm_adjust({row["endpoint"]: row.get("p_value") for row in omnibus})
    for test in omnibus:
        test["holm_adjusted_p_value"] = omnibus_adjusted[test["endpoint"]]
        test["pairwise_gate_open"] = (
            test["holm_adjusted_p_value"] is not None
            and test["holm_adjusted_p_value"] <= 0.05
        )

    pairwise = []
    raw_primary_p: dict[str, float | None] = {}
    for left, right in combinations(models, 2):
        for endpoint in STATISTICAL_PRIMARY_ENDPOINTS:
            comparison_id = f"{endpoint}|{left}|{right}"
            effect = matched_pairwise_bootstrap(
                mechanisms, left, right, endpoint,
                replicates=bootstrap_replicates,
            )
            gate_open = bool(next(row for row in omnibus if row["endpoint"] == endpoint)["pairwise_gate_open"])
            comparison = {
                "comparison_id": comparison_id,
                "endpoint": endpoint,
                "models": [left, right],
                "effect_size": effect,
                "confirmatory_status": "OPENED" if gate_open else "NOT_OPENED_BY_OMNIBUS_GATE",
                "raw_p_value": None,
                "holm_adjusted_p_value": None,
            }
            if gate_open:
                test = within_block_permutation_omnibus(
                    mechanisms, (left, right), endpoint,
                    permutations=permutation_replicates,
                )
                comparison["raw_p_value"] = test["p_value"]
                raw_primary_p[comparison_id] = test["p_value"]
            pairwise.append(comparison)
    adjusted_primary = holm_adjust(raw_primary_p)
    for comparison in pairwise:
        if comparison["comparison_id"] in adjusted_primary:
            comparison["holm_adjusted_p_value"] = adjusted_primary[comparison["comparison_id"]]

    secondary_fields = (
        "schema_valid", "compile_valid", "behaviorally_inert", "exact_match",
        "near_copy", "recombination", "median_necessity_backed_depth", "mean_depth_gap",
    )
    secondary_tests = (
        [
            _within_block_field_permutation_omnibus(
                mechanisms, models, field, permutations=permutation_replicates,
            )
            for field in secondary_fields
        ]
        if len(models) >= 2
        else [
            {
                "endpoint": field,
                "analysis_unit": "generated_mechanism",
                "status": "NOT_ESTIMABLE",
                "reason": "fewer than two model groups",
                "p_value": None,
            }
            for field in secondary_fields
        ]
    )
    adjusted_secondary = benjamini_hochberg_adjust({
        row["endpoint"]: row.get("p_value") for row in secondary_tests
    })
    for test in secondary_tests:
        test["benjamini_hochberg_adjusted_p_value"] = adjusted_secondary[test["endpoint"]]

    sensitivity = {
        "S1_execution_valid_only": {
            model: {
                endpoint: endpoint_estimate(valid_rows, endpoint)
                for endpoint in STATISTICAL_PRIMARY_ENDPOINTS[1:]
            }
            for model, model_rows in sorted(by_model.items())
            for valid_rows in ([row for row in model_rows if row["execution_valid"]],)
        },
        "S2_median_vs_max_depth": {
            model: {
                "median_per_mechanism": _median([row["median_realized_dependency_depth"] for row in model_rows if row["median_realized_dependency_depth"] is not None]),
                "max_per_mechanism": _median([row["max_realized_dependency_depth"] for row in model_rows if row["max_realized_dependency_depth"] is not None]),
            }
            for model, model_rows in sorted(by_model.items())
        },
        "S3_abstract_vs_semantic_collision": {
            model: {
                "abstract": _collision_probability([row["abstract_fingerprint"] for row in model_rows if row["abstract_fingerprint"]]),
                "semantic": _collision_probability([row["semantic_fingerprint"] for row in model_rows if row["semantic_fingerprint"]]),
            }
            for model, model_rows in sorted(by_model.items())
        },
        "S4_safety_refusal_validity": {
            model: {
                "including_refusals": _mean([float(row["execution_valid"]) for row in model_rows]),
                "excluding_refusals": _mean([float(row["execution_valid"]) for row in model_rows if row["failure_class"] != "safety_refusal"]),
                "safety_refusal_count": sum(row["failure_class"] == "safety_refusal" for row in model_rows),
            }
            for model, model_rows in sorted(by_model.items())
        },
        "S5_backend_time_blocks": {
            model: {
                str(block): _mean([float(row["execution_valid"]) for row in model_rows if row["collection_time_block"] == block])
                for block in sorted({row["collection_time_block"] for row in model_rows if row["collection_time_block"] is not None}, key=str)
            }
            for model, model_rows in sorted(by_model.items())
        },
    }
    tests = {
        "analysis_unit": "generated_mechanism",
        "arm_rows_are_repeated_observations": True,
        "confirmatory_omnibus": "permutation",
        "confirmatory_pairwise_correction": "Holm",
        "exploratory_secondary_correction": "Benjamini-Hochberg",
        "production_defaults": {"bootstrap_replicates": 10_000, "permutation_replicates": 100_000},
        "replicates_used": {"bootstrap": bootstrap_replicates, "permutation": permutation_replicates},
        "primary_omnibus": omnibus,
        "primary_pairwise": pairwise,
        "secondary_exploratory": secondary_tests,
        "sensitivity_analyses": sensitivity,
        "status": "NON_FORMAL_ESTIMATES" if run_status == NON_FORMAL_TEST_RUN else "FORMAL_ESTIMATES",
    }
    result = {
        "run_status": run_status,
        "primary_results": primary,
        "secondary_results": secondary,
        "model_profiles": profiles,
        "statistical_tests": tests,
        "figure_data": {"capability_profiles": profiles, "mechanism_rows": list(mechanisms)},
        "table_data": {"table_1": profiles},
    }
    serialized = canonical_json(result)
    if any(name in serialized for name in FORBIDDEN_AGGREGATES):
        raise FormalExperimentError("forbidden creativity aggregate was emitted")
    return result


def write_analysis_artifacts(output_dir: str | Path, analysis: Mapping[str, Any]) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    json_outputs = {
        "primary_results.json": analysis["primary_results"],
        "secondary_results.json": analysis["secondary_results"],
        "model_profiles.json": analysis["model_profiles"],
        "statistical_tests.json": analysis["statistical_tests"],
        "figure_data/capability_profiles.json": analysis["figure_data"],
        "table_data/table_1.json": analysis["table_data"],
    }
    for relative, value in json_outputs.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"run_status": analysis["run_status"], "data": value}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        artifacts[relative] = _sha256_bytes(path.read_bytes())
    csv_path = output / "model_profiles.csv"
    profiles = list(analysis["model_profiles"])
    fieldnames = ["run_status", *(profiles[0].keys() if profiles else ["model_id"])]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for profile in profiles:
        writer.writerow({"run_status": analysis["run_status"], **profile})
    csv_path.write_text(buffer.getvalue(), encoding="utf-8")
    artifacts["model_profiles.csv"] = _sha256_bytes(csv_path.read_bytes())
    return artifacts


def _read_jsonl(path: str | Path) -> tuple[dict[str, Any], ...]:
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FormalExperimentError(f"{path}:{number}: invalid JSON") from exc
        if not isinstance(row, dict):
            raise FormalExperimentError(f"{path}:{number}: expected object")
        rows.append(row)
    return tuple(rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed formal experiment tooling")
    subparsers = parser.add_subparsers(dest="command", required=True)
    dry = subparsers.add_parser("generate-dry-manifest")
    dry.add_argument("output")
    lineage = subparsers.add_parser("validate-formal-lineage")
    lineage.add_argument("rows")
    lineage.add_argument("raw_manifest")
    lineage.add_argument("artifact_root")
    analyze = subparsers.add_parser("analyze-formal-free-invention")
    analyze.add_argument("rows")
    analyze.add_argument("output_dir")
    analyze.add_argument("--manifest")
    analyze.add_argument("--raw-manifest")
    analyze.add_argument("--artifact-root")
    analyze.add_argument("--non-formal-test-run", action="store_true")
    analyze.add_argument("--bootstrap-replicates", type=int, default=10_000)
    analyze.add_argument("--permutation-replicates", type=int, default=100_000)
    args = parser.parse_args(argv)
    if args.command == "generate-dry-manifest":
        rows = build_dry_manifest_example()
        digest = write_jsonl(args.output, rows)
        print(canonical_json({"status": NON_FORMAL_TEST_RUN, "rows": len(rows), "sha256": digest}))
        return 0
    if args.command == "validate-formal-lineage":
        result = validate_formal_lineage(
            _read_jsonl(args.rows), json.loads(Path(args.raw_manifest).read_text(encoding="utf-8")),
            artifact_root=args.artifact_root,
        )
        print(canonical_json(result))
        return 0
    if args.non_formal_test_run:
        manifest_rows = None
        raw_manifest = None
    else:
        if not args.manifest or not args.raw_manifest or not args.artifact_root:
            parser.error("formal analysis requires --manifest, --raw-manifest, and --artifact-root")
        manifest_rows = _read_jsonl(args.manifest)
        raw_manifest = json.loads(Path(args.raw_manifest).read_text(encoding="utf-8"))
    result = analyze_free_invention(
        _read_jsonl(args.rows),
        non_formal_test_run=args.non_formal_test_run,
        manifest_rows=manifest_rows,
        raw_manifest=raw_manifest,
        artifact_root=args.artifact_root,
        bootstrap_replicates=args.bootstrap_replicates,
        permutation_replicates=args.permutation_replicates,
    )
    artifacts = write_analysis_artifacts(args.output_dir, result)
    print(canonical_json({"run_status": result["run_status"], "artifacts": artifacts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
