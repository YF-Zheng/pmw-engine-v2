"""Materialize immutable v0.5 adversarial expectations before execution."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from .v05_case_registry import CASES


ROOT = Path(__file__).resolve().parent
PROTOCOL = ROOT.parent / "free_evaluation_v05" / "protocol.json"
CASES_PATH = ROOT / "v05_preregistered_cases.jsonl"
META_PATH = ROOT / "v05_preregistration.json"
BASE_COMMIT = "b1bdb5bb580ce85a9992bb679eb445be849c8b1b"


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register() -> dict[str, object]:
    old = [case for case in CASES if case["origin"] == "v0.4-retained"]
    new = [case for case in CASES if case["origin"] == "v0.5-new"]
    if len(old) != 48 or len(new) < 16 or len({case["case_id"] for case in CASES}) != len(CASES):
        raise RuntimeError("v0.5 preregistration requires 48 retained and >=16 unique new cases")
    CASES_PATH.write_text("\n".join(_canonical(case) for case in CASES) + "\n", encoding="utf-8")
    resolutions = Counter(case["v04_suspect_resolution"] for case in old)
    metadata = {
        "protocol_version": "gm-free-evaluation-v0.5-candidate",
        "base_commit": BASE_COMMIT,
        "execution_status": "not_run",
        "expectations_written_before_execution": True,
        "retained_v04_case_count": len(old),
        "new_v05_case_count": len(new),
        "total_case_count": len(CASES),
        "v04_suspect_resolution_counts": dict(sorted(resolutions.items())),
        "protocol_sha256": _sha(PROTOCOL),
        "cases_sha256": _sha(CASES_PATH),
    }
    digest_input = _canonical({"protocol_sha256": metadata["protocol_sha256"], "cases_sha256": metadata["cases_sha256"]})
    metadata["preregistration_digest"] = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    META_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata


if __name__ == "__main__":
    print(json.dumps(register(), ensure_ascii=False, indent=2, sort_keys=True))
