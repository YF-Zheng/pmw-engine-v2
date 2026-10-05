"""Fault-isolated, resumable batch evaluation for generated mechanics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .build_search import search_best
from .compiler import canonical_json, compile_skill
from .evaluator import CAPABILITIES, _delta, _weights
from .exploit import detect_exploits
from .generation import (
    DirectEffectSpec, GeneratedSample, IngestionError, POWER_BANDS,
    balanced_sample, compile_direct_effect, prepare_direct_world, skill_to_dict,
)
from .runner import load_skill_catalog, run_scenario
from .scenario import load_scenario
from .smoke import ROOT
from .spec import SkillSpec, validate_skill

BATCH_SCHEMA_VERSION = "gm-batch-v0.1"
REALIZED_POWER_SCALE = 8.0


@dataclass(frozen=True, slots=True)
class BatchConfig:
    profile: str = "ci"
    split: str = "held_out"
    sample_limit: int | None = 12
    scenario_limit: int = 2
    contextual_pool: tuple[str, ...] = ("static_grave", "kindling_arc")
    revision_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": BATCH_SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def full_fixture(cls) -> "BatchConfig":
        return cls(profile="full_fixture_240", sample_limit=None, scenario_limit=6)


def config_hash(config: BatchConfig) -> str:
    return hashlib.sha256(canonical_json(config.to_dict()).encode("utf-8")).hexdigest()


def load_scenarios(split: str = "held_out", limit: int | None = None) -> tuple[Any, ...]:
    result = tuple(
        load_scenario(path) for path in sorted((ROOT / "scenarios" / split).glob("*.json"))
    )
    return result[:limit] if limit is not None else result


def compile_mechanic(mechanic: SkillSpec | DirectEffectSpec) -> dict[str, Any]:
    return compile_skill(mechanic) if isinstance(mechanic, SkillSpec) else compile_direct_effect(mechanic)


def _direct_capabilities(with_run, baseline) -> dict[str, float]:
    def totals(run):
        result = {key: 0.0 for key in ("damage", "heal", "buff", "debuff")}
        for entity in run.final_state["entities"]:
            values = entity.get("components", {}).get("direct_outcome")
            if values:
                for key in result:
                    result[key] += float(values[key])
        return result
    left, right = totals(with_run), totals(baseline)
    delta = {key: left[key] - right[key] for key in left}
    return {
        "Combat": 100.0 * delta["damage"],
        "Survival": 100.0 * delta["heal"],
        "Control": 100.0 * delta["debuff"],
        "Utility": 100.0 * delta["buff"],
        "ExplorationWorldImpact": 0.0,
    }


def _dispatcher(mechanic: SkillSpec | DirectEffectSpec) -> dict[str, Any]:
    return compile_mechanic(mechanic)


def execution_score(
    scenarios: Iterable[Any], build: Iterable[str], catalog: dict[str, Any],
) -> tuple[float, list[float], float, float]:
    """Return mean score, per-scenario scores, interaction surface, persistence."""
    values: list[float] = []
    surfaces: list[int] = []
    persistence: list[int] = []
    for scenario in scenarios:
        with_run = run_scenario(
            scenario, build, catalog=catalog, compile_mechanic=_dispatcher,
            world_setup=prepare_direct_world,
        )
        baseline = run_scenario(
            scenario, (), catalog=catalog, compile_mechanic=_dispatcher,
            world_setup=prepare_direct_world,
        )
        capabilities, differences, _ = _delta(with_run, baseline)
        direct = _direct_capabilities(with_run, baseline)
        combined = {name: capabilities[name] + direct[name] for name in CAPABILITIES}
        weights = _weights(scenario)
        values.append(sum(combined[name] * weights[name] for name in CAPABILITIES))
        with_world = {law for root in with_run.roots for law in root.triggered_law_ids if law.startswith("gm.world.")}
        base_world = {law for root in baseline.roots for law in root.triggered_law_ids if law.startswith("gm.world.")}
        surfaces.append(len(with_world - base_world))
        persistence.append(differences)
    scaled = [value * REALIZED_POWER_SCALE for value in values]
    return sum(scaled) / len(scaled), scaled, sum(surfaces) / len(surfaces), sum(persistence) / len(persistence)


def static_heuristic(mechanic: SkillSpec | DirectEffectSpec) -> float:
    if isinstance(mechanic, DirectEffectSpec):
        magnitude = mechanic.magnitude
    else:
        magnitude = sum(abs(effect.delta) for effect in mechanic.effects)
        if mechanic.periodic:
            magnitude *= 1 + mechanic.periodic.repeats
    return 100.0 * magnitude + min(20.0, mechanic.duration / 15.0) - 0.15 * mechanic.resource_cost


def mechanic_fingerprint(mechanic: SkillSpec | DirectEffectSpec) -> str:
    """Hash mechanic structure while ignoring labels that inflate diversity."""
    raw = asdict(mechanic) if isinstance(mechanic, DirectEffectSpec) else skill_to_dict(mechanic)
    raw.pop("id", None)
    raw.pop("name", None)
    return hashlib.sha256(canonical_json(raw).encode("utf-8")).hexdigest()


def _catalog(sample: GeneratedSample) -> dict[str, Any]:
    result: dict[str, Any] = load_skill_catalog()
    if sample.mechanic.id in result:
        raise ValueError(f"generated id collides with seed catalog: {sample.mechanic.id}")
    result[sample.mechanic.id] = sample.mechanic
    return result


def evaluate_four_baselines(
    sample: GeneratedSample, scenarios: Iterable[Any], contextual_pool: Iterable[str],
    *, contextual_base_values: dict[tuple[str, ...], float] | None = None,
) -> dict[str, dict[str, Any]]:
    scenario_tuple = tuple(scenarios)
    catalog = _catalog(sample)
    standard, _, surface, persistence = execution_score(scenario_tuple, (sample.mechanic.id,), catalog)
    pool = tuple(sorted(contextual_pool))
    missing = set(pool) - set(catalog)
    if missing:
        raise ValueError(f"unknown contextual pool skills: {sorted(missing)}")
    cache: dict[tuple[str, ...], float] = dict(contextual_base_values or {})
    cache[()] = 0.0
    cache[(sample.mechanic.id,)] = standard
    def value(build: tuple[str, ...]) -> float:
        canonical = tuple(sorted(build))
        if canonical not in cache:
            cache[canonical] = execution_score(scenario_tuple, canonical, catalog)[0]
        return cache[canonical]
    before = search_best((catalog[item] for item in pool), value).best
    after = search_best((catalog[item] for item in (*pool, sample.mechanic.id)), value).best
    self_rating = sample.declared_power
    return {
        "self_rating": {"available": self_rating is not None, "score": self_rating},
        "static_heuristic": {"available": True, "score": static_heuristic(sample.mechanic)},
        "pmw_standard_simulation": {
            "available": True, "score": standard,
            "interaction_surface": surface, "persistent_world_impact": persistence,
        },
        "pmw_contextual_search": {
            "available": True, "score": after.value - before.value,
            "best_before": list(before.skills), "best_after": list(after.skills),
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
        raw = skill_to_dict(sample.mechanic)
        for effect in raw["effects"]:
            value = effect["delta"]
            if realized_score == 0:
                value = math.copysign(min(1.0, abs(value) + 0.2), value)
            else:
                value = max(-1.0, min(1.0, value * factor))
            effect["delta"] = round(value, 6)
        revised = validate_skill(raw)
    return replace(sample, mechanic=revised, raw_mechanic=raw)


def _in_band(score: float, band: str) -> bool:
    low, high = POWER_BANDS[band]
    return low <= score <= high


def evaluate_sample(
    sample: GeneratedSample, config: BatchConfig, *, scenarios: Iterable[Any] | None = None,
    contextual_base_values: dict[tuple[str, ...], float] | None = None,
) -> dict[str, Any]:
    scenarios = tuple(scenarios) if scenarios is not None else load_scenarios(config.split, config.scenario_limit)
    compiled = compile_mechanic(sample.mechanic)
    evaluators = evaluate_four_baselines(
        sample, scenarios, config.contextual_pool,
        contextual_base_values=contextual_base_values,
    )
    standard = float(evaluators["pmw_standard_simulation"]["score"])
    revised = revise_sample(sample, standard) if config.revision_enabled else sample
    revised_score = standard
    if revised.mechanic != sample.mechanic:
        revised_score = float(evaluate_four_baselines(
            revised, scenarios, config.contextual_pool,
            contextual_base_values=contextual_base_values,
        )["pmw_standard_simulation"]["score"])
    exploit = detect_exploits(compiled).to_dict()
    return {
        "sample_id": sample.sample_id, "baseline": sample.baseline,
        "target_band": sample.target_band, "source_kind": sample.source_kind,
        "status": "ok", "schema_valid": True, "compile_valid": True,
        "execution_valid": True, "evaluators": evaluators, "exploit": exploit,
        "one_shot_hit": _in_band(standard, sample.target_band),
        "guided_score": revised_score,
        "guided_hit": _in_band(revised_score, sample.target_band),
        "revision_applied": revised.mechanic != sample.mechanic,
        "revision_changed_spec": revised.raw_mechanic != sample.raw_mechanic,
        "revised_mechanic": revised.raw_mechanic if revised.mechanic != sample.mechanic else None,
        "mechanic_fingerprint": mechanic_fingerprint(sample.mechanic),
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
    signatures = {row["mechanic_fingerprint"] for row in ok}
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
        "mechanic_diversity": len(signatures) / len(ok) if ok else 0.0,
        "mean_self_containment": sum(row["self_containment"] for row in ok) / len(ok) if ok else 0.0,
        "mean_interaction_surface": sum(row["evaluators"]["pmw_standard_simulation"]["interaction_surface"] for row in ok) / len(ok) if ok else 0.0,
        "mean_persistent_world_impact": sum(row["evaluators"]["pmw_standard_simulation"]["persistent_world_impact"] for row in ok) / len(ok) if ok else 0.0,
        "power_distribution": {
            "min": min(scores) if scores else None, "mean": sum(scores) / len(scores) if scores else None,
            "max": max(scores) if scores else None,
        },
        "one_shot_hit_rate": rate("one_shot_hit"), "guided_hit_rate": rate("guided_hit"),
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
    seed_catalog = load_skill_catalog()
    missing_pool = set(config.contextual_pool) - set(seed_catalog)
    if missing_pool:
        raise ValueError(f"unknown contextual pool skills: {sorted(missing_pool)}")
    contextual_base_values: dict[tuple[str, ...], float] = {(): 0.0}
    def seed_value(build: tuple[str, ...]) -> float:
        canonical = tuple(sorted(build))
        if canonical not in contextual_base_values:
            contextual_base_values[canonical] = execution_score(scenarios, canonical, seed_catalog)[0]
        return contextual_base_values[canonical]
    search_best((seed_catalog[item] for item in config.contextual_pool), seed_value)
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
                contextual_base_values=contextual_base_values,
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
