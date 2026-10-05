"""Command line interface for the Generative Mechanics Lab."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .compiler import canonical_json, compile_skill
from .build_search import pairwise_synergy, personalized_delta, search_best
from .evaluator import emergent_reach, evaluate_build, evaluate_candidate
from .exploit import detect_exploits
from .runner import load_skill_catalog, run_scenario
from .scenario import load_scenario
from .smoke import ROOT, default_smoke
from .spec import SkillSpecError, load_skill
from .analysis import analyze
from .batch import BatchConfig, run_batch
from .figures import render_figures
from .generation import (
    GenerationContractError, ingest_path, write_fixture_jsonl, write_request_jsonl,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="generative-mechanics")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-skills", help="strictly validate SkillSpec JSON files")
    validate.add_argument("paths", nargs="*", type=Path)
    compile_one = commands.add_parser("compile-skill", help="compile one SkillSpec to canonical PMW JSON")
    compile_one.add_argument("path", type=Path)
    commands.add_parser("smoke", help="run one skill in all four environments")
    run = commands.add_parser("run-scenario", help="execute one scenario from a clean world")
    run.add_argument("path", type=Path)
    run.add_argument("--skills", nargs="*", default=None)
    skill = commands.add_parser("evaluate-skill", help="evaluate one skill on a strict scenario split")
    skill.add_argument("skill_id"); skill.add_argument("--split", choices=("calibration", "held_out"), default="held_out")
    build = commands.add_parser("evaluate-build", help="evaluate an active build")
    build.add_argument("skill_ids", nargs="+"); build.add_argument("--split", choices=("calibration", "held_out"), default="held_out")
    search = commands.add_parser("search-build", help="exhaustively search a backpack once")
    search.add_argument("skill_ids", nargs="+"); search.add_argument("--split", choices=("calibration", "held_out"), default="calibration")
    candidate = commands.add_parser("evaluate-candidate", help="compare exhaustive best builds before and after a candidate")
    candidate.add_argument("candidate_skill"); candidate.add_argument("existing_backpack", nargs="*")
    candidate.add_argument("--split", choices=("calibration", "held_out"), default="held_out")
    fixture = commands.add_parser("generate-fixture", help="write balanced deterministic JSONL fixtures")
    fixture.add_argument("output", type=Path); fixture.add_argument("--seed", type=int, default=2601)
    requests = commands.add_parser("generate-requests", help="write provider-neutral prompt request JSONL")
    requests.add_argument("output", type=Path); requests.add_argument("--seed", type=int, default=2601)
    requests.add_argument("--per-cell", type=int, default=40)
    ingest = commands.add_parser("ingest-responses", help="strictly ingest versioned response JSONL")
    ingest.add_argument("input", type=Path)
    batch = commands.add_parser("run-batch", help="run a fault-isolated generated-mechanic batch")
    batch.add_argument("input", type=Path); batch.add_argument("output", type=Path)
    batch.add_argument("--profile", choices=("ci", "full"), default="ci")
    analysis = commands.add_parser("analyze-results", help="compute cross-environment and kill-criteria tables")
    analysis.add_argument("input", type=Path); analysis.add_argument("batch_dir", type=Path)
    analysis.add_argument("output", type=Path); analysis.add_argument("--limit", type=int, default=None)
    analysis.add_argument("--ground-truth", type=Path, default=None)
    figures = commands.add_parser("render-figures", help="render Figures 1-5 as PDF/SVG/PNG")
    figures.add_argument("batch_dir", type=Path); figures.add_argument("analysis", type=Path)
    figures.add_argument("output", type=Path)
    return parser


def _scenarios():
    return [load_scenario(path) for path in sorted((ROOT / "scenarios").glob("*/*.json"))]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-skills":
            paths = args.paths or sorted((ROOT / "skills").glob("*.json"))
            paths = [path for path in paths if path.name != "manifest.json"]
            validated = [load_skill(path).id for path in paths]
            print(canonical_json({"count": len(validated), "skills": sorted(validated), "valid": True}))
        elif args.command == "compile-skill":
            print(canonical_json(compile_skill(load_skill(args.path))))
        elif args.command == "smoke":
            print(canonical_json(default_smoke()))
        elif args.command == "run-scenario":
            print(canonical_json(run_scenario(load_scenario(args.path), args.skills).to_dict()))
        elif args.command == "evaluate-skill":
            catalog = load_skill_catalog(); spec = catalog[args.skill_id]
            scenarios = _scenarios(); profile = evaluate_build(scenarios, (spec.id,), split=args.split)
            relevant = next(item for item in scenarios if item.split == args.split)
            compiled = compile_skill(spec)
            print(canonical_json({
                "PowerProfile": profile.to_dict(),
                "EmergentReach": emergent_reach(relevant, (spec.id,), spec.id).to_dict(),
                "ExploitReport": detect_exploits(compiled).to_dict(),
            }))
        elif args.command == "evaluate-build":
            print(canonical_json(evaluate_build(_scenarios(), args.skill_ids, split=args.split).to_dict()))
        elif args.command == "search-build":
            catalog = load_skill_catalog()
            specs = [catalog[item] for item in args.skill_ids]
            cache = {}
            def value(build):
                if build not in cache:
                    cache[build] = evaluate_build(_scenarios(), build, split=args.split).typical_power
                return cache[build]
            result = search_best(specs, value)
            print(canonical_json({
                "best": {"skills": list(result.best.skills), "value": result.best.value},
                "evaluations": result.evaluations, "legal_builds": result.legal_builds,
                "pairwise_synergy": pairwise_synergy(specs, value),
            }))
        elif args.command == "evaluate-candidate":
            print(canonical_json(evaluate_candidate(
                _scenarios(), args.existing_backpack, args.candidate_skill, split=args.split,
            ).to_dict()))
        elif args.command == "generate-fixture":
            digest = write_fixture_jsonl(args.output, seed=args.seed)
            print(canonical_json({"count": 240, "output": str(args.output), "sha256": digest,
                                  "source_kind": "deterministic_fixture"}))
        elif args.command == "generate-requests":
            if args.per_cell < 1:
                raise ValueError("per-cell must be positive")
            digest = write_request_jsonl(args.output, seed=args.seed, per_cell=args.per_cell)
            print(canonical_json({
                "count": 6 * args.per_cell, "output": str(args.output),
                "sha256": digest, "source_kind": "provider_request",
            }))
        elif args.command == "ingest-responses":
            result = ingest_path(args.input)
            print(canonical_json({"valid": len(result.samples), "invalid": len(result.errors),
                                  "samples": [item.to_dict() for item in result.samples],
                                  "errors": [item.to_dict() for item in result.errors]}))
            return 0 if not result.errors else 2
        elif args.command == "run-batch":
            ingestion = ingest_path(args.input)
            config = BatchConfig.full_fixture() if args.profile == "full" else BatchConfig()
            result = run_batch(
                ingestion.samples, args.output, config,
                ingestion_errors=ingestion.errors,
            )
            print(canonical_json({"manifest": result["manifest"], "summary": result["summary"],
                                  "ingestion_errors": result["summary"]["ingestion_errors"]}))
        elif args.command == "analyze-results":
            ingestion = ingest_path(args.input)
            records = [json.loads(line) for line in (args.batch_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()]
            summary = json.loads((args.batch_dir / "summary.json").read_text(encoding="utf-8"))
            ground_truth = None
            if args.ground_truth is not None:
                ground_truth = json.loads(args.ground_truth.read_text(encoding="utf-8"))
                if not isinstance(ground_truth, dict):
                    raise ValueError("ground truth must be a JSON object mapping sample IDs to scores")
            result = analyze(
                records, ingestion.samples, summary,
                cross_environment_limit=args.limit, ground_truth=ground_truth,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(canonical_json({"output": str(args.output), "cross_environment_n": result["cross_environment_aggregate"]["n"]}))
        elif args.command == "render-figures":
            records = [json.loads(line) for line in (args.batch_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()]
            summary = json.loads((args.batch_dir / "summary.json").read_text(encoding="utf-8"))
            analysis_data = json.loads(args.analysis.read_text(encoding="utf-8"))
            manifest = render_figures({"records": records, "summary": summary}, analysis_data, args.output)
            print(canonical_json(manifest))
    except (GenerationContractError, SkillSpecError, ValueError) as exc:
        print(canonical_json({"error": str(exc), "valid": False}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
