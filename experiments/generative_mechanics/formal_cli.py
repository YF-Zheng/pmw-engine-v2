"""Offline CLI for formal preregistration validation and analysis.

This module intentionally contains no provider transport or collection command.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .formal_experiment import (
    analyze_free_invention,
    build_dry_manifest_example,
    validate_formal_lineage,
    validate_raw_data_manifest,
    write_analysis_artifacts,
    write_jsonl,
)


def _read_json(path: str | Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    rows = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ValueError(f"expected JSON object at {path}:{line_number}")
        rows.append(value)
    return tuple(rows)


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _command_dry_manifest(args: argparse.Namespace) -> None:
    rows = build_dry_manifest_example()
    digest = write_jsonl(args.output, rows)
    _print_json({"status": "SYNTHETIC_MOCK_ONLY", "rows": len(rows), "sha256": digest})


def _command_validate_lineage(args: argparse.Namespace) -> None:
    rows = _read_jsonl(args.rows)
    raw_manifest = _read_json(args.raw_manifest)
    validate_raw_data_manifest(args.artifact_root, raw_manifest)
    _print_json(validate_formal_lineage(rows, raw_manifest, artifact_root=args.artifact_root))


def _command_analyze(args: argparse.Namespace) -> None:
    rows = _read_jsonl(args.rows)
    manifest_rows: Iterable[Mapping[str, Any]] | None = None
    raw_manifest: Mapping[str, Any] | None = None
    if not args.non_formal_test_run:
        missing = [
            name for name, value in (
                ("--manifest", args.manifest),
                ("--raw-manifest", args.raw_manifest),
                ("--artifact-root", args.artifact_root),
            ) if not value
        ]
        if missing:
            raise ValueError(f"formal analysis requires: {', '.join(missing)}")
        manifest_rows = _read_jsonl(args.manifest)
        raw_manifest = _read_json(args.raw_manifest)
        validate_raw_data_manifest(args.artifact_root, raw_manifest)
    analysis = analyze_free_invention(
        rows,
        non_formal_test_run=args.non_formal_test_run,
        manifest_rows=manifest_rows,
        raw_manifest=raw_manifest,
        artifact_root=args.artifact_root,
        bootstrap_replicates=args.bootstrap_replicates,
        permutation_replicates=args.permutation_replicates,
    )
    artifacts = write_analysis_artifacts(args.output_dir, analysis)
    _print_json({"run_status": analysis["run_status"], "artifacts": artifacts})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry = subparsers.add_parser("generate-dry-manifest")
    dry.add_argument("--output", required=True)
    dry.set_defaults(handler=_command_dry_manifest)

    lineage = subparsers.add_parser("validate-formal-lineage")
    lineage.add_argument("--rows", required=True)
    lineage.add_argument("--raw-manifest", required=True)
    lineage.add_argument("--artifact-root", required=True)
    lineage.set_defaults(handler=_command_validate_lineage)

    analyze = subparsers.add_parser("analyze-formal-free-invention")
    analyze.add_argument("--rows", required=True)
    analyze.add_argument("--output-dir", required=True)
    analyze.add_argument("--manifest")
    analyze.add_argument("--raw-manifest")
    analyze.add_argument("--artifact-root")
    analyze.add_argument("--non-formal-test-run", action="store_true")
    analyze.add_argument("--bootstrap-replicates", type=int, default=10_000)
    analyze.add_argument("--permutation-replicates", type=int, default=100_000)
    analyze.set_defaults(handler=_command_analyze)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
