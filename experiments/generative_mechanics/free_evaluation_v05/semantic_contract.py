"""Fail-closed whole-evaluator semantic contract for v0.5."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_name("semantic_contract.json")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def current_projection(*, manifest_path: Path = MANIFEST, root: Path = ROOT) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = manifest["registered_paths"]
    return {
        "protocol_version": "gm-free-evaluation-v0.5-candidate",
        "files": {relative: _sha(root / relative) for relative in paths},
    }


def projection_digest(projection: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(projection).encode("utf-8")).hexdigest()


def validate_semantic_contract(*, manifest_path: Path = MANIFEST, root: Path = ROOT) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("protocol_version") != "gm-free-evaluation-v0.5-candidate":
        raise ValueError("v0.5 semantic contract protocol mismatch")
    projection = current_projection(manifest_path=manifest_path, root=root)
    if projection != manifest.get("canonical_projection"):
        raise ValueError("v0.5 semantic contract projection mismatch")
    digest = projection_digest(projection)
    if digest != manifest.get("semantic_contract_digest"):
        raise ValueError("v0.5 semantic contract digest mismatch")
    return manifest
