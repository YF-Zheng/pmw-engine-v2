"""Cross-environment, aftermath, evaluator, and kill-criteria analysis."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .batch import compile_mechanic
from .compiler import canonical_json
from .generation import DirectEffectSpec, GeneratedSample, balanced_sample, prepare_direct_world
from .runner import run_scenario

ANALYSIS_VERSION = "gm-analysis-v0.2"
ENVIRONMENTS = ("mine", "wetland", "industrial_yard", "fragile_bridge")


@dataclass(frozen=True, slots=True)
class KillThresholds:
    version: str = "kill-criteria-v0.1"
    direct_collapse_max: float = 0.35
    mean_downstream_min: float = 0.25
    environment_difference_min: float = 0.20
    contextual_gain_min: float = 0.0
    validity_min: float = 0.90
    warning_margin: float = 0.10


def _probe_scenario(environment: str) -> dict[str, Any]:
    return {
        "id": f"evaluation_probe_{environment}", "split": "evaluation",
        "category": "environmental_hazard",
        "environment_variant": "standard",
        "initial_fields": {},
        "build": {"backpack": [
            "ash_bloom", "bedrock_memory", "blackout", "boiler_field", "clear_sky",
            "cold_sink", "dew_circuit", "drainage_cut", "drying_wind", "ember_pulse",
        ], "active": [
            "ash_bloom", "bedrock_memory", "blackout", "boiler_field", "clear_sky", "cold_sink",
        ]},
        "environment": environment, "program": (
            {"op": "cast", "skill": "each_active", "target": "zone"},
            {"op": "step", "repeats": 1},
        ),
        "horizons": {"combat_end": 0.0, "short": 5.0, "medium": 20.0},
        "horizon_weights": {"combat_end": .5, "short": .3, "medium": .2},
        "weights": {"combat": .2, "survival": .2, "control": .2, "utility": .2,
                    "exploration_world_impact": .2},
        "target_count": 1,
    }


def _zone_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    zone = next(item for item in state["entities"] if "zone" in item.get("components", {}))
    components = zone["components"]
    return {
        key: components[key] for key in ("fields", "process", "outcome", "direct_outcome")
        if key in components
    }


def _leaf_count(left: Any, right: Any) -> int:
    if isinstance(left, dict) and isinstance(right, dict):
        return sum(_leaf_count(left.get(key), right.get(key)) for key in set(left) | set(right))
    return int(left != right)


def cross_environment(sample: GeneratedSample) -> dict[str, Any]:
    """Execute an unchanged mechanic in all four worlds and retain compact signatures."""
    catalog = {sample.mechanic.id: sample.mechanic}
    environments: dict[str, Any] = {}
    for environment in ENVIRONMENTS:
        scenario = _probe_scenario(environment)
        run = run_scenario(
            scenario, (sample.mechanic.id,), catalog=catalog,
            compile_mechanic=compile_mechanic, world_setup=prepare_direct_world,
        )
        baseline = run_scenario(
            scenario, (), catalog=catalog, compile_mechanic=compile_mechanic,
            world_setup=prepare_direct_world,
        )
        with_world = Counter(
            law for root in run.roots for law in root.triggered_law_ids if law.startswith("gm.world.")
        )
        base_world = Counter(
            law for root in baseline.roots for law in root.triggered_law_ids if law.startswith("gm.world.")
        )
        downstream = sorted((with_world - base_world).elements())
        trajectories = {}
        for horizon in ("combat_end", "short", "medium"):
            current, control = _zone_snapshot(run.horizons[horizon]), _zone_snapshot(baseline.horizons[horizon])
            trajectories[horizon] = {
                "difference_count": _leaf_count(current, control),
                "signature": canonical_json(current),
            }
        final = _zone_snapshot(run.final_state)
        direct = final.get("direct_outcome", {})
        environments[environment] = {
            "downstream_laws": downstream,
            "downstream_count": len(set(downstream)),
            "direct_outcome": direct,
            "final_signature": canonical_json(final),
            "trajectories": trajectories,
        }
    signatures = {item["final_signature"] for item in environments.values()}
    # Environment-specific initial state is not evidence. Compare downstream law signatures.
    downstream_signatures = {canonical_json(item["downstream_laws"]) for item in environments.values()}
    direct_signatures = {canonical_json(item["direct_outcome"]) for item in environments.values()}
    return {
        "sample_id": sample.sample_id, "baseline": sample.baseline,
        "source_kind": sample.source_kind, "mechanic_unchanged": True,
        "environments": environments,
        "environment_difference": len(downstream_signatures) > 1,
        "environment_difference_rate": (len(downstream_signatures) - 1) / 3.0,
        "direct_outcome_consistent": len(direct_signatures) == 1,
        "total_downstream": sum(item["downstream_count"] for item in environments.values()),
        "aftermath": {
            horizon: mean(item["trajectories"][horizon]["difference_count"] for item in environments.values())
            for horizon in ("combat_end", "short", "medium")
        },
    }


def _comparison_task(
    records: Iterable[dict[str, Any]], ground_truth: dict[str, float],
    names: tuple[str, ...], estimand: str, oracle_target: str,
) -> dict[str, Any]:
    rows = [row for row in records if row.get("sample_id") in ground_truth and row.get("status") == "ok"]
    result: dict[str, Any] = {}
    for name in names:
        pairs = [
            (float(row["evaluators"][name]["score"]), float(ground_truth[row["sample_id"]]))
            for row in rows
            if row.get("evaluators", {}).get(name, {}).get("available")
            and row["evaluators"][name].get("score") is not None
        ]
        if len(pairs) < 2:
            result[name] = {"correlation": None, "mae": None, "n": len(pairs)}
            continue
        xs, ys = zip(*pairs)
        xbar, ybar = mean(xs), mean(ys)
        denom = math.sqrt(sum((x-xbar)**2 for x in xs) * sum((y-ybar)**2 for y in ys))
        correlation = sum((x-xbar)*(y-ybar) for x, y in pairs) / denom if denom else None
        result[name] = {"correlation": correlation, "mae": mean(abs(x-y) for x, y in pairs), "n": len(pairs)}
    return {
        "available": any(item["n"] >= 2 for item in result.values()),
        "estimand": estimand,
        "oracle_target": oracle_target,
        "evaluators": result,
    }


def evaluator_comparison(
    records: Iterable[dict[str, Any]], ground_truth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare estimators only against the Oracle target for the same estimand.

    A legacy ``sample_id -> scalar`` input remains readable and is interpreted
    solely as IntrinsicPower. It can never score the contextual estimator.
    """
    intrinsic_names = ("self_rating", "static_heuristic", "pmw_standard_simulation")
    contextual_names = ("pmw_contextual_search", "llm_contextual_judge", "static_contextual_heuristic")
    if ground_truth and all(isinstance(value, (int, float)) for value in ground_truth.values()):
        intrinsic_truth = ground_truth
        contextual_truth: dict[str, float] = {}
        input_schema = "legacy-intrinsic-only"
    else:
        source = ground_truth or {}
        intrinsic_truth = source.get("IntrinsicPower", {})
        contextual_truth = source.get("ContextualMarginalPower", {})
        input_schema = "two-estimand"
    rows = tuple(records)
    tasks = {
        "IntrinsicPower": _comparison_task(
            rows, intrinsic_truth, intrinsic_names, "IntrinsicPower", "OracleIntrinsicPower",
        ),
        "ContextualMarginalPower": _comparison_task(
            rows, contextual_truth, contextual_names, "ContextualMarginalPower",
            "OraclePersonalizedDelta",
        ),
    }
    available = any(task["available"] for task in tasks.values())
    result = {
        "schema_version": "gm-evaluator-comparison-v0.2",
        "available": available,
        "input_schema": input_schema,
        "reason": None if available else "matching Oracle ground truth was not supplied; no metric was fabricated",
        "tasks": tasks,
        "cross_estimand_comparisons": False,
    }
    # Read compatibility for consumers of v0.1. This alias contains intrinsic
    # estimators only and therefore cannot recreate the invalid mixed table.
    result["evaluators"] = tasks["IntrinsicPower"]["evaluators"]
    return result


def _status(value: float, threshold: float, *, higher: bool, margin: float) -> str:
    passed = value >= threshold if higher else value <= threshold
    if passed:
        return "PASS"
    distance = threshold - value if higher else value - threshold
    return "WARN" if distance <= margin else "FAIL"


def kill_criteria(
    summary: dict[str, Any], records: Iterable[dict[str, Any]],
    environment_rows: Iterable[dict[str, Any]],
    evaluator_result: dict[str, Any] | None = None,
    thresholds: KillThresholds = KillThresholds(),
) -> dict[str, Any]:
    rows = [row for row in records if row.get("status") == "ok"]
    world = [row for row in rows if row["baseline"] == "world_substrate"]
    env = [row for row in environment_rows if row["baseline"] == "world_substrate"]
    direct_collapse = (
        sum(row["evaluators"]["pmw_standard_simulation"]["interaction_surface"] == 0 for row in world) / len(world)
        if world else 1.0
    )
    downstream = mean((row["total_downstream"] for row in env)) if env else 0.0
    environment_difference = mean((float(row["environment_difference"]) for row in env)) if env else 0.0
    validity = min(summary.get("schema_validity", 0.0), summary.get("compile_rate", 0.0), summary.get("execution_validity", 0.0))
    definitions = (
        ("direct_collapse", direct_collapse, thresholds.direct_collapse_max, False),
        ("downstream_scarcity", downstream, thresholds.mean_downstream_min, True),
        ("environment_sameness", environment_difference, thresholds.environment_difference_min, True),
        ("validity_bottleneck", validity, thresholds.validity_min, True),
    )
    checks = {
        name: {"value": value, "threshold": target,
               "status": _status(value, target, higher=higher, margin=thresholds.warning_margin)}
        for name, value, target, higher in definitions
    }
    comparison = evaluator_result or {"available": False}
    if comparison.get("available"):
        contextual_task = comparison.get("tasks", {}).get("ContextualMarginalPower", {})
        metrics = contextual_task.get("evaluators", {}) if contextual_task.get("available") else {}
        contextual_mae = metrics.get("pmw_contextual_search", {}).get("mae")
        baselines = [
            metrics.get(name, {}).get("mae")
            for name in ("llm_contextual_judge", "static_contextual_heuristic")
        ]
        baselines = [value for value in baselines if value is not None]
        if contextual_mae is not None and baselines:
            contextual_gain = min(baselines) - contextual_mae
            checks["contextual_evaluator_no_gain"] = {
                "value": contextual_gain, "threshold": thresholds.contextual_gain_min,
                "status": _status(
                    contextual_gain, thresholds.contextual_gain_min,
                    higher=True, margin=thresholds.warning_margin,
                ),
            }
        else:
            checks["contextual_evaluator_no_gain"] = {
                "value": None, "threshold": thresholds.contextual_gain_min,
                "status": "UNAVAILABLE", "reason": "insufficient paired evaluator data",
            }
    else:
        checks["contextual_evaluator_no_gain"] = {
            "value": None, "threshold": thresholds.contextual_gain_min,
            "status": "UNAVAILABLE",
            "reason": "independent ground truth was not supplied",
        }
    statuses = {item["status"] for item in checks.values()}
    return {
        "version": thresholds.version, "thresholds": asdict(thresholds), "checks": checks,
        "fixture_disclaimer": "Fixture diagnostics only; PASS/WARN/FAIL is not a paper conclusion.",
        "overall": "FAIL" if "FAIL" in statuses else "INCOMPLETE" if "UNAVAILABLE" in statuses else
                   "WARN" if "WARN" in statuses else "PASS",
    }


def analyze(
    records: Iterable[dict[str, Any]], samples: Iterable[GeneratedSample],
    summary: dict[str, Any], *, cross_environment_limit: int | None = None,
    ground_truth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sample_rows = balanced_sample(samples, cross_environment_limit)
    environments = [cross_environment(sample) for sample in sample_rows]
    comparison = evaluator_comparison(records, ground_truth)
    def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "n": len(rows),
            "difference_rate": mean(float(row["environment_difference"]) for row in rows) if rows else None,
            "mean_downstream": mean(row["total_downstream"] for row in rows) if rows else None,
            "aftermath": {
                horizon: mean(row["aftermath"][horizon] for row in rows) if rows else None
                for horizon in ("combat_end", "short", "medium")
            },
        }
    baselines = sorted({row["baseline"] for row in environments})
    return {
        "schema_version": ANALYSIS_VERSION,
        "fixture_disclaimer": "Deterministic fixtures validate the pipeline; they are not model findings.",
        "cross_environment": environments,
        "cross_environment_aggregate": {
            "overall_secondary": aggregate(environments),
            "by_baseline": {
                baseline: aggregate([row for row in environments if row["baseline"] == baseline])
                for baseline in baselines
            },
            "primary_reporting": "by_baseline",
        },
        "evaluator_comparison": comparison,
        "kill_criteria": kill_criteria(summary, records, environments, comparison),
    }
