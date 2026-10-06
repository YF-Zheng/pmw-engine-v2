"""Independent outcome and causal-path differentiation for v0.5."""

from __future__ import annotations

from collections import Counter
import json
from typing import Any, Iterable, Mapping

from pmw import load_laws, parse_law

from ..causal_depth_v04 import WORLD_PREFIX, _extract_occurrences
from ..cross_environment_v04 import (
    QUARTET_ENVIRONMENTS,
    REGISTERED_CONTEXTS,
    _observations,
    _subtract,
    matched_quartet_scenario,
    mechanic_runtime,
)
from ..free_invention import FreeInventionSample
from ..runner import ScenarioRun, run_scenario
from .causal import ROOT, dependency_profile_from_runs


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _additional_occurrences(
    present: ScenarioRun,
    absent: ScenarioRun,
    law_map: Mapping[str, Any],
) -> tuple[Any, ...]:
    absent_counts = Counter(
        (
            node.law_id, node.phase, node.bindings, node.reads, node.writes,
        )
        for node in _extract_occurrences(absent, law_map)
        if node.law_id.startswith(WORLD_PREFIX)
    )
    additional = []
    for node in _extract_occurrences(present, law_map):
        if not node.law_id.startswith(WORLD_PREFIX):
            continue
        key = (node.law_id, node.phase, node.bindings, node.reads, node.writes)
        if absent_counts[key]:
            absent_counts[key] -= 1
        else:
            additional.append(node)
    return tuple(additional)


def normalized_path_signature(
    present: ScenarioRun,
    absent: ScenarioRun,
    *,
    world_laws: Iterable[Any],
    candidate_laws: Iterable[Any],
    candidate_skill: str,
) -> dict[str, Any]:
    """Normalize candidate-induced occurrence and dependency multiplicity.

    Generated ids, proposal ids, command ids, and absolute timestamps are not
    represented. Binding identity remains semantic.
    """
    world = tuple(world_laws)
    candidate = tuple(candidate_laws)
    law_map = {law.law_id: law for law in (*world, *candidate)}
    additional = _additional_occurrences(present, absent, law_map)
    nodes = Counter(_canonical({
        "law_id": node.law_id,
        "phase": node.phase,
        "bindings": list(node.bindings),
        "reads": list(node.reads),
        "writes": list(node.writes),
    }) for node in additional)
    graph = dependency_profile_from_runs(
        present, absent, candidate_skill, world_laws=world,
        candidate_laws=candidate, world_law_ablations={},
    )
    edges = Counter(_canonical({
        "source_law_id": edge["source_law_id"],
        "target_law_id": edge["target_law_id"],
        "addresses": edge["addresses"],
    }) for edge in graph.get("dependency_edges", []))
    return {
        "nodes": [{"signature": key, "count": count} for key, count in sorted(nodes.items())],
        "edges": [{"signature": key, "count": count} for key, count in sorted(edges.items())],
        "identity_exclusions": ["event_id", "command_id", "proposal_id", "absolute_timestamp"],
        "binding_policy": "identity_equality",
        "occurrence_multiplicity_preserved": True,
    }


def summarize_environment_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = tuple(rows)
    outcome_groups: dict[str, list[str]] = {}
    path_groups: dict[str, list[str]] = {}
    for row in rows:
        outcome_groups.setdefault(_canonical(row["net_outcome_effect"]), []).append(row["environment"])
        path_groups.setdefault(_canonical(row["normalized_path_signature"]), []).append(row["environment"])
    outcome_partitions = [sorted(values) for _, values in sorted(outcome_groups.items())]
    path_partitions = [sorted(values) for _, values in sorted(path_groups.items())]
    outcome_partitions.sort()
    path_partitions.sort()
    return {
        "outcome_differentiated": len(outcome_groups) > 1,
        "distinct_outcome_signature_count": len(outcome_groups),
        "outcome_partitions": outcome_partitions,
        "causal_path_differentiated": len(path_groups) > 1,
        "distinct_path_signature_count": len(path_groups),
        "path_partitions": path_partitions,
        "deprecated_environmentally_differentiated": {
            "value": len(outcome_groups) > 1 or len(path_groups) > 1,
            "status": "deprecated_v0.4_compatibility_only",
        },
    }


def _environment_row(sample: FreeInventionSample, environment: str, fields: dict[str, float]) -> dict[str, Any]:
    compiler, world_setup = mechanic_runtime(sample)
    catalog = {sample.mechanic.id: sample.mechanic}
    scenario = matched_quartet_scenario(sample, environment, public_initial_fields=fields)
    present = run_scenario(scenario, (sample.mechanic.id,), catalog=catalog, compile_mechanic=compiler, world_setup=world_setup)
    absent = run_scenario(scenario, (), catalog=catalog, compile_mechanic=compiler, world_setup=world_setup)
    compiled = compiler(sample.mechanic)
    candidate_laws = tuple(parse_law(raw) for raw in compiled["laws"])
    world_laws = tuple(load_laws(ROOT / "substrate" / "world_laws.json"))
    outcome = _subtract(_observations(present), _observations(absent))
    path = normalized_path_signature(
        present, absent, world_laws=world_laws, candidate_laws=candidate_laws,
        candidate_skill=sample.mechanic.id,
    )
    return {
        "environment": environment,
        "net_outcome_effect": outcome,
        "normalized_path_signature": path,
        "raw": {
            "candidate_present_observation": _observations(present),
            "candidate_absent_observation": _observations(absent),
        },
    }


def evaluate_environmental_behavior(sample: FreeInventionSample) -> dict[str, Any]:
    contexts = []
    for context in sorted(REGISTERED_CONTEXTS, key=lambda item: item.id):
        rows = tuple(
            _environment_row(sample, environment, dict(context.public_initial_fields))
            for environment in QUARTET_ENVIRONMENTS
        )
        contexts.append({
            "context_id": context.id,
            **summarize_environment_rows(rows),
            "environment_rows": list(rows),
        })
    return {
        "available": True,
        "design": "six registered public-field contexts by four matched environments; paired candidate-present minus absent",
        "context_count": len(contexts),
        "environment_count_per_context": len(QUARTET_ENVIRONMENTS),
        "outcome_differentiated_context_count": sum(row["outcome_differentiated"] for row in contexts),
        "causal_path_differentiated_context_count": sum(row["causal_path_differentiated"] for row in contexts),
        "contexts": contexts,
    }
