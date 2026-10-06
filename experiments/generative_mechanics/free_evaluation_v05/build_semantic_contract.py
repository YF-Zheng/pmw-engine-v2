"""Build the external whole-evaluator semantic manifest after source freeze."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(__file__).with_name("semantic_contract.json")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, object]:
    fixed = [
        "free_evaluation_v05/protocol.json",
        "free_evaluation_v05/design_summary.json",
        "free_evaluation_v05/metric_mapping.json",
        "free_evaluation_v05/causal.py",
        "free_evaluation_v05/environment.py",
        "free_evaluation_v05/structure.py",
        "free_evaluation_v05/profile.py",
        "free_evaluation_v05/semantic_contract.py",
        "free_evaluation_v05/__init__.py",
        "cli.py",
        "causal_depth_v04.py",
        "cross_environment_v04.py",
        "structural_novelty.py",
        "baseline_v02.py",
        "generation.py",
        "runner.py",
        "execution.py",
        "diversity.py",
        "compiler.py",
        "substrate.py",
        "spec.py",
        "free_invention.py",
        "generators/protocol_v0.3.json",
        "substrate/world_laws.json",
        "structural_novelty/reference_registry_v0.4.json",
        "skills/manifest.json",
        "adversarial_measurement/v05_preregistered_cases.jsonl",
        "adversarial_measurement/v05_preregistration.json",
    ]
    assets = [
        str(path.relative_to(ROOT))
        for pattern in ("environments/*.json", "scenarios/calibration/*.json", "scenarios/evaluation/*.json", "skills/*.json")
        for path in sorted(ROOT.glob(pattern))
    ]
    paths = sorted(set(fixed + assets))
    projection = {
        "protocol_version": "gm-free-evaluation-v0.5",
        "files": {path: _sha(ROOT / path) for path in paths},
    }
    canonical = json.dumps(projection, sort_keys=True, separators=(",", ":"))
    manifest = {
        "protocol_version": "gm-free-evaluation-v0.5",
        "scope": "whole_evaluator_environment_world_system_context_reference_and_shared_sources",
        "registered_paths": paths,
        "canonical_projection": projection,
        "semantic_contract_digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
