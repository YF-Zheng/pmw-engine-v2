"""Fault-isolated, resumable batch evaluation for generated mechanics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .compiler import canonical_json, compile_skill
from .diversity import parametric_fingerprint, structural_fingerprint
from .power_v02 import (
    ContextualSearchCache,
    evaluate_contextual_power,
    evaluate_power,
)
from .exploit import detect_exploits
from .generation import (
    DirectEffectSpec, GeneratedSample, IngestionError, POWER_BANDS,
    balanced_sample, compile_direct_effect, prepare_direct_world, skill_to_dict,
)
from .runner import load_skill_catalog, run_scenario
from .scenario import load_scenario, normalize_split
from .smoke import ROOT
from .spec import SkillSpec, validate_skill

BATCH_SCHEMA_VERSION = "gm-batch-v0.2"


@dataclass(frozen=True, slots=True)
class BatchConfig:
    profile: str = "ci"
    split: str = "evaluation"
    sample_limit: int | None = 12
    scenario_limit: int = 2
    # Deprecated v0.1 compatibility input. v0.2 always uses scenario backpacks.
    contextual_pool: tuple[str, ...] = ()
    contextual_mode: str = "deferred"
    revision_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": BATCH_SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def full_fixture(cls) -> "BatchConfig":
        return cls(profile="full_fixture_240", sample_limit=None, scenario_limit=6)


def config_hash(config: BatchConfig) -> str:
    return hashlib.sha256(canonical_json(config.to_dict()).encode("utf-8")).hexdigest()


def load_scenarios(split: str = "evaluation", limit: int | None = None) -> tuple[Any, ...]:
    split = normalize_split(split)
    result = tuple(
        load_scenario(path) for path in sorted((ROOT / "scenarios" / split).glob("*.json"))
    )
    return result[:limit] if limit is not None else result


def compile_mechanic(mechanic: Any) -> dict[str, Any]:
    if isinstance(mechanic, SkillSpec):
        return compile_skill(mechanic)
    if isinstance(mechanic, DirectEffectSpec):
        return compile_direct_effect(mechanic)
    # MatchedDirectOutcome is optional at this layer and deliberately duck-typed
    # so the authoritative evaluator does not depend on a baseline implementation.
    from .baseline_v02 import MatchedDirectOutcomeSpec, compile_matched_direct_outcome
    if isinstance(mechanic, MatchedDirectOutcomeSpec):
        return compile_matched_direct_outcome(mechanic)
    raise TypeError(f"unsupported mechanic type: {type(mechanic).__name__}")


def _dispatcher(mechanic: SkillSpec | DirectEffectSpec) -> dict[str, Any]:
    return compile_mechanic(mechanic)


def execution_score(
    scenarios: Iterable[Any], build: Iterable[str], catalog: dict[str, Any],
) -> tuple[float, list[float], float, float]:
    """Compatibility facade over the authoritative PowerScaleContract."""
    scenario_tuple = tuple(scenarios)
    if not scenario_tuple:
        raise ValueError("execution_score requires at least one scenario")
    first = scenario_tuple[0]
    split = normalize_split(first["split"] if isinstance(first, dict) else first.split)
    profile = evaluate_power(
        scenario_tuple, build, split=split, catalog=catalog,
        compile_mechanic=_dispatcher, world_setup=prepare_direct_world,
    )
    return (
        profile.typical_power,
        [item.value for item in profile.scenario_scores],
        profile.interaction_surface,
        profile.persistent_world_impact,
    )


def static_heuristic(mechanic: SkillSpec | DirectEffectSpec) -> float:
    if isinstance(mechanic, DirectEffectSpec):
        magnitude = mechanic.magnitude
    else:
        magnitude = sum(abs(effect.delta) for effect in mechanic.effects)
        if mechanic.periodic:
            magnitude *= 1 + mechanic.periodic.repeats
    return 100.0 * magnitude + min(20.0, mechanic.duration / 15.0) - 0.15 * mechanic.resource_cost


def mechanic_fingerprint(mechanic: Any) -> str:
    """Deprecated v0.1 alias for the exact parametric fingerprint."""
    return parametric_fingerprint(mechanic)


def _catalog(sample: GeneratedSample) -> dict[str, Any]:
    result: dict[str, Any] = load_skill_catalog()
    if sample.mechanic.id in result:
        raise ValueError(f"generated id collides with seed catalog: {sample.mechanic.id}")
    result[sample.mechanic.id] = sample.mechanic
    return result


def evaluate_four_baselines(
    sample: GeneratedSample, scenarios: Iterable[Any], contextual_pool: Iterable[str],
    *, contextual_base_values: dict[tuple[str, ...], float] | None = None,
    contextual_cache: ContextualSearchCache | None = None,
    contextual_mode: str = "deferred",
) -> dict[str, dict[str, Any]]:
    scenario_tuple = tuple(scenarios)
    catalog = _catalog(sample)
    standard, _, surface, persistence = execution_score(scenario_tuple, (sample.mechanic.id,), catalog)
    if contextual_mode not in {"deferred", "exact"}:
        raise ValueError("contextual_mode must be 'deferred' or 'exact'")
    contextual = None
    if contextual_mode == "exact":
        split = scenario_tuple[0].split if not isinstance(scenario_tuple[0], dict) else scenario_tuple[0]["split"]
        contextual = evaluate_contextual_power(
            scenario_tuple, sample.mechanic.id, split=split, catalog=catalog,
            compile_mechanic=_dispatcher, world_setup=prepare_direct_world,
            cache=contextual_cache,
        )
    self_rating = sample.declared_power
    return {
        "self_rating": {"available": self_rating is not None, "score": self_rating},
        "static_heuristic": {"available": True, "score": static_heuristic(sample.mechanic)},
        "pmw_standard_simulation": {
            "available": True, "score": standard,
            "interaction_surface": surface, "persistent_world_impact": persistence,
        },
        "pmw_contextual_search": {
            **({
                "available": True, "score": contextual.mean,
                "mean": contextual.mean, "p90": contextual.p90, "max": contextual.maximum,
                "estimand": "ContextualMarginalPower",
                "contexts": [item.to_dict() for item in contextual.contexts],
            } if contextual is not None else {
                "available": False,
                "score": None,
                "estimand": "ContextualMarginalPower",
                "reason": "deferred; rerun with contextual_mode='exact'",
            }),
        },
    }


def revise_sample(sample: GeneratedSample, realized_score: float) -> GeneratedSample:
    """Deterministically revise the actual mechanic, never an evaluator score."""
    low, high = POWER_BANDS[sample.target_band]
    midpoint = (low + high) / 2.0
    if low <= realized_score <= high:
        return sample
    denominator = max(1.0, abs(realized_score))
    factor = max(0.25, min(4.0, midpoint / denominator))
    if isinstance(sample.mechanic, DirectEffectSpec):
        revised = replace(sample.mechanic, magnitude=max(0.01, min(1.0, round(sample.mechanic.magnitude * factor, 6))))
        raw = asdict(revised)
    else:
        from .baseline_v02 import MatchedDirectOutcomeSpec, validate_matched_direct_outcome
        matched = isinstance(sample.mechanic, MatchedDirectOutcomeSpec)
        raw = sample.mechanic.to_dict() if matched else skill_to_dict(sample.mechanic)
        for effect in raw["effects"]:
            value = effect["delta"]
            if realized_score == 0:
                value = math.copysign(min(1.0, abs(value) + 0.2), value)
            else:
                value = max(-1.0, min(1.0, value * factor))
            effect["delta"] = round(value, 6)
        revised = validate_matched_direct_outcome(raw) if matched else validate_skill(raw)
    return replace(sample, mechanic=revised, raw_mechanic=raw)


def _in_band(score: float, band: str) -> bool:
    low, high = POWER_BANDS[band]
    return low <= score <= high


def evaluate_sample(
    sample: GeneratedSample, config: BatchConfig, *, scenarios: Iterable[Any] | None = None,
    contextual_base_values: dict[tuple[str, ...], float] | None = None,
    contextual_cache: ContextualSearchCache | None = None,
) -> dict[str, Any]:
    scenarios = tuple(scenarios) if scenarios is not None else load_scenarios(config.split, config.scenario_limit)
    compiled = compile_mechanic(sample.mechanic)
    evaluators = evaluate_four_baselines(
        sample, scenarios, config.contextual_pool,
        contextual_base_values=contextual_base_values,
        contextual_cache=contextual_cache,
        contextual_mode=config.contextual_mode,
    )
    standard = float(evaluators["pmw_standard_simulation"]["score"])
    revised = revise_sample(sample, standard) if config.revision_enabled else sample
    revised_score = standard
    if revised.mechanic != sample.mechanic:
        revised_catalog = _catalog(revised)
        revised_score = execution_score(
            scenarios, (revised.mechanic.id,), revised_catalog,
        )[0]
    exploit = detect_exploits(compiled).to_dict()
    return {
        "sample_id": sample.sample_id, "baseline": sample.baseline,
        "target_band": sample.target_band, "source_kind": sample.source_kind,
        "status": "ok", "schema_valid": True, "compile_valid": True,
        "execution_valid": True, "evaluators": evaluators, "exploit": exploit,
        "prediction_tables": {
            "IntrinsicPower": {
                key: evaluators[key]
                for key in ("self_rating", "static_heuristic", "pmw_standard_simulation")
            },
            "ContextualMarginalPower": {
                "pmw_contextual_search": evaluators["pmw_contextual_search"],
            },
        },
        "one_shot_hit": _in_band(standard, sample.target_band),
        "guided_score": revised_score,
        "guided_hit": _in_band(revised_score, sample.target_band),
        "revision_method": "deterministic_controller",
        "controller_score": revised_score,
        "controller_hit": _in_band(revised_score, sample.target_band),
        "revision_applied": revised.mechanic != sample.mechanic,
        "revision_changed_spec": revised.raw_mechanic != sample.raw_mechanic,
        "revised_mechanic": revised.raw_mechanic if revised.mechanic != sample.mechanic else None,
        "mechanic_fingerprint": mechanic_fingerprint(sample.mechanic),
        "structural_fingerprint": structural_fingerprint(sample.raw_mechanic),
        "parametric_fingerprint": parametric_fingerprint(sample.raw_mechanic),
        "self_containment": float(
            evaluators["pmw_standard_simulation"]["interaction_surface"] == 0
        ),
    }


def summarize(
    records: Iterable[dict[str, Any]], ingestion_errors: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    rows = tuple(records); ingest_failures = tuple(ingestion_errors)
    ok = tuple(row for row in rows if row.get("status") == "ok")
    schema_valid = tuple(row for row in rows if row.get("schema_valid"))
    compile_valid = tuple(row for row in schema_valid if row.get("compile_valid"))
    def rate(key):
        return sum(bool(row.get(key)) for row in ok) / len(ok) if ok else 0.0
    structural_signatures = {
        row.get("structural_fingerprint", row["mechanic_fingerprint"]) for row in ok
    }
    parametric_signatures = {
        row.get("parametric_fingerprint", row["mechanic_fingerprint"]) for row in ok
    }
    scores = [row["evaluators"]["pmw_standard_simulation"]["score"] for row in ok]
    by_baseline = {}
    for baseline in sorted({row["baseline"] for row in ok}):
        selected = [row for row in ok if row["baseline"] == baseline]
        baseline_scores = [row["evaluators"]["pmw_standard_simulation"]["score"] for row in selected]
        by_baseline[baseline] = {
            "n": len(selected),
            "mean_power": mean_value(baseline_scores),
            "mean_interaction_surface": mean_value(
                row["evaluators"]["pmw_standard_simulation"]["interaction_surface"] for row in selected
            ),
            "self_containment_rate": mean_value(row["self_containment"] for row in selected),
        }
    by_target_band = {}
    for band in POWER_BANDS:
        selected = [row for row in ok if row["target_band"] == band]
        by_target_band[band] = {
            "n": len(selected),
            "one_shot_hit_rate": mean_value(float(row["one_shot_hit"]) for row in selected),
            "deterministic_controller_hit_rate": mean_value(float(row["controller_hit"]) for row in selected),
            "guided_hit_rate": mean_value(float(row["guided_hit"]) for row in selected),
        }
    total_inputs = len(rows) + len(ingest_failures)
    return {
        "schema_version": BATCH_SCHEMA_VERSION,
        "fixture_disclaimer": "Deterministic fixture pipeline result; not an LLM or paper conclusion.",
        "total": total_inputs, "succeeded": len(ok), "failed": total_inputs - len(ok),
        "ingestion_failed": len(ingest_failures),
        "schema_validity": len(schema_valid) / total_inputs if total_inputs else 0.0,
        "compile_rate": len(compile_valid) / len(schema_valid) if schema_valid else 0.0,
        "execution_validity": len(ok) / len(compile_valid) if compile_valid else 0.0,
        "diversity": {
            "structural_unique": len(structural_signatures),
            "structural_ratio": len(structural_signatures) / len(ok) if ok else 0.0,
            "parametric_unique": len(parametric_signatures),
            "parametric_ratio": len(parametric_signatures) / len(ok) if ok else 0.0,
        },
        # v0.1 read compatibility; this was exact-parametric diversity despite its name.
        "mechanic_diversity": len(parametric_signatures) / len(ok) if ok else 0.0,
        "mean_self_containment": sum(row["self_containment"] for row in ok) / len(ok) if ok else 0.0,
        "mean_interaction_surface": sum(row["evaluators"]["pmw_standard_simulation"]["interaction_surface"] for row in ok) / len(ok) if ok else 0.0,
        "mean_persistent_world_impact": sum(row["evaluators"]["pmw_standard_simulation"]["persistent_world_impact"] for row in ok) / len(ok) if ok else 0.0,
        "power_distribution": {
            "min": min(scores) if scores else None, "mean": sum(scores) / len(scores) if scores else None,
            "max": max(scores) if scores else None,
        },
        "one_shot_hit_rate": rate("one_shot_hit"),
        "deterministic_controller_hit_rate": rate("controller_hit"),
        "guided_hit_rate": rate("guided_hit"),
        "by_baseline": by_baseline, "by_target_band": by_target_band,
        "errors": [row for row in rows if row.get("status") != "ok"],
        "ingestion_errors": list(ingest_failures),
    }


def mean_value(values: Iterable[float]) -> float:
    items = tuple(values)
    return sum(items) / len(items) if items else 0.0


def run_batch(
    samples: Iterable[GeneratedSample], output_dir: str | Path, config: BatchConfig = BatchConfig(),
    *, ingestion_errors: Iterable[IngestionError | dict[str, Any]] = (),
) -> dict[str, Any]:
    """Evaluate independently, checkpoint canonically, and resume by config hash."""
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    manifest_path, records_path = output / "manifest.json", output / "records.jsonl"
    digest = config_hash(config)
    existing: dict[str, dict[str, Any]] = {}
    if manifest_path.exists() and records_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("config_hash") != digest:
            raise ValueError("existing batch manifest has a different config hash")
        for line in records_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line); existing[row["sample_id"]] = row
    selected = balanced_sample(samples, config.sample_limit)
    scenarios = load_scenarios(config.split, config.scenario_limit)
    contextual_cache = ContextualSearchCache()
    for sample in selected:
        if sample.sample_id in existing:
            continue
        base = {
            "sample_id": sample.sample_id, "baseline": sample.baseline,
            "target_band": sample.target_band, "source_kind": sample.source_kind,
            "schema_valid": True, "compile_valid": False, "execution_valid": False,
        }
        try:
            compile_mechanic(sample.mechanic)
            base["compile_valid"] = True
            existing[sample.sample_id] = evaluate_sample(
                sample, config, scenarios=scenarios,
                contextual_cache=contextual_cache,
            )
        except Exception as exc:  # per-sample isolation is part of the batch contract
            existing[sample.sample_id] = {
                **base, "status": "error", "error_type": type(exc).__name__,
                "message": str(exc),
            }
        content = "".join(canonical_json(existing[key]) + "\n" for key in sorted(existing))
        records_path.write_text(content, encoding="utf-8")
    records = [existing[key] for key in sorted(existing)]
    serialized_ingestion_errors = [
        item.to_dict() if isinstance(item, IngestionError) else dict(item)
        for item in ingestion_errors
    ]
    summary = summarize(records, serialized_ingestion_errors)
    manifest = {
        "schema_version": BATCH_SCHEMA_VERSION, "config": config.to_dict(),
        "config_hash": digest, "record_count": len(records),
        "records_sha256": hashlib.sha256(records_path.read_bytes()).hexdigest(),
        "source_kind": sorted({sample.source_kind for sample in selected}),
        "ingestion_error_count": len(serialized_ingestion_errors),
        "paper_conclusion": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"manifest": manifest, "summary": summary, "records": records}
