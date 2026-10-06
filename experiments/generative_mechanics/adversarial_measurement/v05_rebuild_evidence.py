"""Rebuild v0.5 evidence in its required upstream-to-downstream order."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .v05_production_validation import OUTPUT as PRODUCTION_OUTPUT, run as run_production
from .v05_run_audit import (
    PRODUCTION_RESULTS_SHA256,
    RESULTS as AUDIT_RESULTS,
    SUMMARY as AUDIT_SUMMARY,
    run as run_audit,
)


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "results" / "v05_pipeline_manifest.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> dict[str, object]:
    run_production()
    first = PRODUCTION_OUTPUT.read_bytes()
    first_sha = hashlib.sha256(first).hexdigest()
    run_production()
    second = PRODUCTION_OUTPUT.read_bytes()
    second_sha = hashlib.sha256(second).hexdigest()
    if first != second or first_sha != PRODUCTION_RESULTS_SHA256:
        raise RuntimeError(
            "production evidence is not deterministic or does not match the audit binding: "
            f"first={first_sha}, second={second_sha}, expected={PRODUCTION_RESULTS_SHA256}"
        )
    audit = run_audit()
    if audit["judgement_counts"].get("FAIL", 0):
        raise RuntimeError("v0.5 audit contains a FAIL")
    preregistration = json.loads((ROOT / "v05_preregistration.json").read_text(encoding="utf-8"))
    semantic = json.loads((ROOT.parent / "free_evaluation_v05" / "semantic_contract.json").read_text(encoding="utf-8"))
    manifest = {
        "protocol_version": "gm-free-evaluation-v0.5-candidate",
        "required_order": ["production_run_1", "production_run_2", "audit"],
        "production_run_sha256": [first_sha, second_sha],
        "production_runs_byte_identical": first == second,
        "audit_bound_production_sha256": PRODUCTION_RESULTS_SHA256,
        "audit_results_sha256": _sha(AUDIT_RESULTS),
        "audit_summary_sha256": _sha(AUDIT_SUMMARY),
        "preregistration_digest": preregistration["preregistration_digest"],
        "semantic_contract_digest": semantic["semantic_contract_digest"],
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
