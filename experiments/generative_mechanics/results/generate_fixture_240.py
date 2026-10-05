"""Rebuild the deterministic 240-sample pipeline artifact from source contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from experiments.generative_mechanics.analysis import analyze
from experiments.generative_mechanics.batch import BatchConfig, run_batch
from experiments.generative_mechanics.compiler import canonical_json
from experiments.generative_mechanics.figures import render_figures
from experiments.generative_mechanics.generation import (
    ingest_path, write_fixture_jsonl, write_request_jsonl,
)

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "fixture_240"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--resume-batch", type=Path, default=None,
        help="reuse a complete compatible batch directory, then regenerate analysis and figures",
    )
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="pmw-gml-") as temporary:
        temp = Path(temporary)
        fixture_path = temp / "fixture.jsonl"
        request_path = temp / "requests.jsonl"
        fixture_sha256 = write_fixture_jsonl(fixture_path)
        request_sha256 = write_request_jsonl(request_path)
        ingestion = ingest_path(fixture_path)
        if ingestion.errors or len(ingestion.samples) != 240:
            raise RuntimeError("deterministic fixture failed its own ingestion contract")

        staged = temp / "fixture_240"
        if args.resume_batch is not None:
            shutil.copytree(args.resume_batch, staged)
            for name in ("analysis.json", "cross_environment.jsonl", "artifact_manifest.json"):
                path = staged / name
                if path.exists():
                    path.unlink()
            if (staged / "figures").exists():
                shutil.rmtree(staged / "figures")
        batch = run_batch(
            ingestion.samples, staged, BatchConfig.full_fixture(),
            ingestion_errors=ingestion.errors,
        )
        analysis = analyze(batch["records"], ingestion.samples, batch["summary"])
        render_figures(batch, analysis, staged / "figures")
        compact_analysis = {
            key: value for key, value in analysis.items() if key != "cross_environment"
        }
        analysis_path = staged / "analysis.json"
        analysis_path.write_text(
            json.dumps(compact_analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        table_path = staged / "cross_environment.jsonl"
        table_path.write_text("".join(
            canonical_json({
                "sample_id": row["sample_id"], "baseline": row["baseline"],
                "environment_difference": row["environment_difference"],
                "environment_difference_rate": row["environment_difference_rate"],
                "total_downstream": row["total_downstream"], "aftermath": row["aftermath"],
            }) + "\n"
            for row in analysis["cross_environment"]
        ), encoding="utf-8")
        manifest = {
            "artifact": "deterministic_fixture_240",
            "paper_conclusion": False,
            "source_kind": "deterministic_fixture",
            "fixture_count": 240,
            "fixture_jsonl_sha256": fixture_sha256,
            "request_jsonl_sha256": request_sha256,
            "raw_fixture_checked_in": False,
            "raw_requests_checked_in": False,
            "files": {
                str(path.relative_to(staged)): _sha256(path)
                for path in sorted(staged.rglob("*")) if path.is_file()
            },
        }
        (staged / "artifact_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if OUTPUT.exists():
            shutil.rmtree(OUTPUT)
        shutil.copytree(staged, OUTPUT)

    print(canonical_json({
        "output": str(OUTPUT), "fixture_count": 240,
        "source_kind": "deterministic_fixture", "paper_conclusion": False,
    }))


if __name__ == "__main__":
    main()
