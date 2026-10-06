"""Build and validate the administrative v0.5 evaluator freeze manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .semantic_contract import validate_semantic_contract


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path(__file__).with_name("FREEZE_MANIFEST.json")
MARKDOWN = Path(__file__).with_name("FREEZE_MANIFEST.md")
PROTOCOL_VERSION = "gm-free-evaluation-v0.5"
BASE_COMMIT = "fdb5c845dea48db41255b9c38aee830c77e8d87a"
CORE_MANIFEST_SHA256 = "0cb9271e7dcfa9b1882246190f78afddfb1f153e699c7609182cbcd921cacf5d"
PRE_FREEZE_REVIEWED_SEMANTIC_CONTRACT_DIGEST = "01635c9e500c22250bb8fe3309c54a213bcd9a0638a8429b730f07e8121851d2"
REVIEWED_MEASUREMENT_SOURCE_HASHES = {
    "experiments/generative_mechanics/free_evaluation_v05/causal.py": "59f60ab40a9eff77f640a3e95014e601a58278cf96174693cd813f08a8d5ab54",
    "experiments/generative_mechanics/free_evaluation_v05/environment.py": "a6099184c569270b998f43c719689a45906d1c56184fc78e84c6d4afdcee950e",
    "experiments/generative_mechanics/free_evaluation_v05/structure.py": "804d31745a7bb28044cac7dab195539b4141fd34dba898cc6738869bc750b905",
}

EVALUATOR_SOURCES = (
    "experiments/generative_mechanics/free_evaluation_v05/causal.py",
    "experiments/generative_mechanics/free_evaluation_v05/environment.py",
    "experiments/generative_mechanics/free_evaluation_v05/structure.py",
    "experiments/generative_mechanics/free_evaluation_v05/protocol.json",
)
WORLD_SYSTEM_LAWS = (
    "experiments/generative_mechanics/substrate/world_laws.json",
    "experiments/generative_mechanics/substrate.py",
)
ENVIRONMENT_ASSETS = (
    "experiments/generative_mechanics/environments/fragile_bridge.json",
    "experiments/generative_mechanics/environments/industrial_yard.json",
    "experiments/generative_mechanics/environments/mine.json",
    "experiments/generative_mechanics/environments/wetland.json",
)
SCENARIO_CONTEXT_ASSETS = (
    "experiments/generative_mechanics/cross_environment_v04.py",
    *(f"experiments/generative_mechanics/scenarios/{split}/{name}.json"
      for split in ("calibration", "evaluation")
      for name in (
          "aftermath", "environmental_hazard", "long_combat",
          "multi_target", "resource_limited", "short_combat",
      )),
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hashes(root: Path, paths: tuple[str, ...]) -> dict[str, str]:
    return {path: _sha(root / path) for path in paths}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def expected_manifest(*, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    gm_root = repo_root / "experiments" / "generative_mechanics"
    protocol = json.loads((gm_root / "free_evaluation_v05" / "protocol.json").read_text(encoding="utf-8"))
    controlled = json.loads((gm_root / "generators" / "protocol_v0.2.json").read_text(encoding="utf-8"))
    free = json.loads((gm_root / "generators" / "protocol_v0.3.json").read_text(encoding="utf-8"))
    registry_path = gm_root / "structural_novelty" / "reference_registry_v0.4.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    preregistration_path = gm_root / "adversarial_measurement" / "v05_preregistration.json"
    preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
    preregistered_cases_path = gm_root / "adversarial_measurement" / "v05_preregistered_cases.jsonl"
    semantic_path = gm_root / "free_evaluation_v05" / "semantic_contract.json"
    semantic = validate_semantic_contract(manifest_path=semantic_path, root=gm_root)
    administrative_source = "experiments/generative_mechanics/free_evaluation_v05/freeze_manifest.py"

    if protocol.get("status") != "frozen":
        raise ValueError("v0.5 protocol is not frozen")
    if protocol.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("v0.5 protocol identifier mismatch")
    if free.get("protocol_version") != "gm-free-invention-v0.3":
        raise ValueError("free generation protocol mismatch")
    if controlled.get("protocol_version") != "gm-generation-v0.2-controlled":
        raise ValueError("controlled generation protocol mismatch")
    if _sha(gm_root / str(registry["source_manifest"])) != registry["source_manifest_sha256"]:
        raise ValueError("reference source manifest digest mismatch")
    if _sha(preregistered_cases_path) != preregistration["cases_sha256"]:
        raise ValueError("adversarial preregistered cases digest mismatch")
    preregistration_projection = {
        "protocol_sha256": preregistration["protocol_sha256"],
        "cases_sha256": preregistration["cases_sha256"],
    }
    calculated_preregistration_digest = hashlib.sha256(
        _canonical(preregistration_projection).encode("utf-8")
    ).hexdigest()
    if calculated_preregistration_digest != preregistration["preregistration_digest"]:
        raise ValueError("adversarial preregistration digest mismatch")
    current_measurement_hashes = _hashes(repo_root, tuple(REVIEWED_MEASUREMENT_SOURCE_HASHES))
    if current_measurement_hashes != REVIEWED_MEASUREMENT_SOURCE_HASHES:
        raise ValueError("reviewed v0.5 measurement source hash mismatch")
    if "free_evaluation_v05/freeze_manifest.py" in semantic["registered_paths"]:
        raise ValueError("administrative freeze source is in evaluator semantic projection")

    return {
        "manifest_version": "gm-free-evaluation-freeze-manifest-v0.5",
        "freeze_scope": "evaluator_contract_only",
        "protocols": {
            "free_generation": "gm-free-invention-v0.3",
            "free_evaluation": PROTOCOL_VERSION,
            "controlled_generation": "gm-generation-v0.2-controlled",
        },
        "administrative_transition": {
            "from_protocol": "gm-free-evaluation-v0.5-candidate",
            "from_status": "preregistered_candidate_not_frozen",
            "to_protocol": PROTOCOL_VERSION,
            "to_status": "frozen",
            "change_scope": "administrative_identifier_and_status_only",
            "base_commit": BASE_COMMIT,
            "pre_freeze_reviewed_semantic_contract_digest": PRE_FREEZE_REVIEWED_SEMANTIC_CONTRACT_DIGEST,
        },
        "status": {
            "free_evaluation": "frozen",
            "formal_paper_experiment": "NOT STARTED",
            "dev_pilot": "NOT STARTED",
        },
        "git_commit": {
            "base_commit": BASE_COMMIT,
            "freeze_commit": "COMMIT_CONTAINING_THIS_MANIFEST",
            "resolution": "git log -1 --format=%H -- experiments/generative_mechanics/free_evaluation_v05/FREEZE_MANIFEST.json",
        },
        "contract_digests": {
            "core_manifest_sha256": CORE_MANIFEST_SHA256,
            "reference_registry_projection_sha256": registry["reference_projection_sha256"],
            "reference_registry_file_sha256": _sha(registry_path),
            "reference_source_sha256": registry["source_manifest_sha256"],
            "adversarial_preregistration_digest": preregistration["preregistration_digest"],
            "adversarial_preregistration_file_sha256": _sha(preregistration_path),
            "semantic_contract_digest": semantic["semantic_contract_digest"],
            "semantic_contract_file_sha256": _sha(semantic_path),
        },
        "evaluator_source_hashes": _hashes(repo_root, EVALUATOR_SOURCES),
        "administrative_source_hashes": {
            administrative_source: _sha(repo_root / administrative_source),
        },
        "world_system_law_digests": _hashes(repo_root, WORLD_SYSTEM_LAWS),
        "environment_asset_digests": _hashes(repo_root, ENVIRONMENT_ASSETS),
        "scenario_context_digests": _hashes(repo_root, SCENARIO_CONTEXT_ASSETS),
        "freeze_statement": (
            "v0.5 freeze only freezes the evaluator contract; it does not mean "
            "that any real-model experiment has been completed."
        ),
        "post_freeze_policy": (
            "DEV pilot work must not change v0.5 metric semantics. A required "
            "measurement fix must become v0.6, preserve the original v0.5 pilot "
            "results, and document the freeze-break reason."
        ),
    }


def render_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Free-Invention Evaluator v0.5 Freeze Manifest",
        "",
        manifest["freeze_statement"],
        "",
        "## Protocols and status",
        "",
        f"- Free generation protocol: `{manifest['protocols']['free_generation']}`",
        f"- Free evaluation protocol: `{manifest['protocols']['free_evaluation']}`",
        f"- Controlled protocol: `{manifest['protocols']['controlled_generation']}`",
        f"- Evaluator status: `{manifest['status']['free_evaluation']}`",
        f"- Formal paper experiment: `{manifest['status']['formal_paper_experiment']}`",
        f"- DEV pilot: `{manifest['status']['dev_pilot']}`",
        "",
        "## Administrative transition",
        "",
        f"- Candidate protocol: `{manifest['administrative_transition']['from_protocol']}`",
        f"- Candidate status: `{manifest['administrative_transition']['from_status']}`",
        f"- Frozen protocol: `{manifest['administrative_transition']['to_protocol']}`",
        f"- Frozen status: `{manifest['administrative_transition']['to_status']}`",
        f"- Change scope: `{manifest['administrative_transition']['change_scope']}`",
        f"- Base commit: `{manifest['administrative_transition']['base_commit']}`",
        f"- Pre-freeze reviewed semantic contract digest: `{manifest['administrative_transition']['pre_freeze_reviewed_semantic_contract_digest']}`",
        "- Measurement source continuity: the causal, cross-environment, and structural evaluator hashes below are identical to the reviewed candidate hashes.",
        "",
        "## Git provenance",
        "",
        f"- Base commit: `{manifest['git_commit']['base_commit']}`",
        f"- Freeze commit: `{manifest['git_commit']['freeze_commit']}`",
        f"- Resolution: `{manifest['git_commit']['resolution']}`",
        "",
        "The freeze commit is necessarily identified by the commit containing this manifest; a Git commit cannot embed its own object ID without changing that ID.",
        "",
        "## Contract digests",
        "",
    ]
    for key, value in manifest["contract_digests"].items():
        lines.append(f"- {key}: `{value}`")
    for title, key in (
        ("Evaluator source hashes", "evaluator_source_hashes"),
        ("Administrative source hashes", "administrative_source_hashes"),
        ("World/system law digests", "world_system_law_digests"),
        ("Environment asset digests", "environment_asset_digests"),
        ("Scenario/context digests", "scenario_context_digests"),
    ):
        lines.extend(("", f"## {title}", ""))
        for path, digest in manifest[key].items():
            lines.append(f"- `{path}`: `{digest}`")
    lines.extend(("", "## Post-freeze policy", "", manifest["post_freeze_policy"], ""))
    return "\n".join(lines)


def build(*, repo_root: Path = REPO_ROOT, manifest_path: Path = MANIFEST, markdown_path: Path = MARKDOWN) -> dict[str, Any]:
    manifest = expected_manifest(repo_root=repo_root)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(manifest), encoding="utf-8")
    return manifest


def validate_freeze_manifest(
    *, repo_root: Path = REPO_ROOT, manifest_path: Path = MANIFEST, markdown_path: Path = MARKDOWN,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = expected_manifest(repo_root=repo_root)
    if manifest != expected:
        raise ValueError("v0.5 freeze manifest mismatch")
    if markdown_path.read_text(encoding="utf-8") != render_markdown(expected):
        raise ValueError("v0.5 freeze manifest Markdown mismatch")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
