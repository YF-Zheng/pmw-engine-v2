"""Two deliberately distinct dynamic-reach measures for v0.5."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from pmw import load_laws, parse_law

from ..causal_depth_v04 import WORLD_PREFIX, _extract_occurrences, _overlap
from ..runner import ScenarioRun, run_scenario


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    source: str
    target: str
    addresses: tuple[str, ...]
    source_law_id: str
    target_law_id: str
    necessity_backed: bool
    necessity_evidence: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "addresses": list(self.addresses),
            "source_law_id": self.source_law_id,
            "target_law_id": self.target_law_id,
            "necessity_backed": self.necessity_backed,
            "necessity_evidence": self.necessity_evidence,
        }


def _longest_structural_path(nodes: Iterable[Any], edges: Iterable[DependencyEdge], roots: set[str]) -> tuple[int, list[str], list[str]]:
    occurrences = {node.node_id: node for node in nodes}
    predecessors: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        predecessors[edge.target].append(edge.source)
    states: dict[str, dict[frozenset[str], tuple[str, ...]]] = {
        root: {frozenset(): (root,)} for root in roots
    }
    ordered = sorted(
        (node for node in nodes if node.node_id not in roots),
        key=lambda node: (node.order, node.node_id),
    )
    for target in ordered:
        alternatives: dict[frozenset[str], tuple[str, ...]] = {}
        for source in sorted(predecessors.get(target.node_id, [])):
            for law_set, path in states.get(source, {}).items():
                reached = law_set | {target.law_id}
                candidate = (*path, target.node_id)
                prior = alternatives.get(reached)
                if prior is None or candidate < prior:
                    alternatives[reached] = candidate
        if alternatives:
            states[target.node_id] = alternatives
    choices = [
        (len(laws), path, tuple(dict.fromkeys(occurrences[item].law_id for item in path if item not in roots)))
        for node_id, alternatives in states.items() if node_id not in roots
        for laws, path in alternatives.items()
    ]
    if not choices:
        return 0, [], []
    depth, path, laws = max(choices, key=lambda item: (item[0], tuple(reversed(item[1]))))
    return depth, list(path), list(laws)


def dependency_profile_from_runs(
    with_candidate: ScenarioRun,
    without_candidate: ScenarioRun,
    candidate_skill: str,
    *,
    world_laws: Iterable[Any],
    candidate_laws: Iterable[Any],
    world_law_ablations: Mapping[str, ScenarioRun],
) -> dict[str, Any]:
    """Build realized and necessity-backed graphs from the same executions."""
    if with_candidate.scenario_id != without_candidate.scenario_id:
        raise ValueError("paired runs must use the same scenario")
    world = tuple(world_laws)
    candidate = tuple(candidate_laws)
    law_map = {law.law_id: law for law in (*world, *candidate)}
    candidate_ids = {law.law_id for law in candidate}
    with_nodes = _extract_occurrences(with_candidate, law_map)
    absent_counts = Counter(
        node.pair_key for node in _extract_occurrences(without_candidate, law_map)
        if node.law_id.startswith(WORLD_PREFIX)
    )
    additional = []
    for node in with_nodes:
        if not node.law_id.startswith(WORLD_PREFIX):
            continue
        if absent_counts[node.pair_key]:
            absent_counts[node.pair_key] -= 1
        else:
            additional.append(node)
    direct = [node for node in with_nodes if node.law_id in candidate_ids]
    if not direct:
        return {
            "available": True,
            "candidate_activated": False,
            "realized_dependency_depth": None,
            "necessity_backed_depth": None,
            "depth_gap": None,
            "possible_redundant_causation": False,
            "reason": "candidate produced no effective committed write",
            "dependency_nodes": [],
            "dependency_edges": [],
            "necessity_edges": [],
            "dependency_path": [],
            "necessity_path": [],
        }
    sources = (*direct, *additional)
    all_writers = tuple(
        node for node in with_nodes
        if node.law_id.startswith(WORLD_PREFIX) or node.law_id in candidate_ids
    )
    present_counts = Counter(node.pair_key for node in with_nodes if node.law_id.startswith(WORLD_PREFIX))
    ablated_counts = {
        law_id: Counter(
            node.pair_key for node in _extract_occurrences(run, law_map)
            if node.law_id.startswith(WORLD_PREFIX)
        )
        for law_id, run in world_law_ablations.items()
    }
    realized: list[DependencyEdge] = []
    for target in additional:
        last_writers: dict[str, list[Any]] = defaultdict(list)
        for read in target.reads:
            eligible = [
                source for source in all_writers
                if source.order < target.order and any(_overlap(write, read) for write in source.writes)
            ]
            if eligible:
                latest = max(source.order for source in eligible)
                last_writers[read].extend(source for source in eligible if source.order == latest)
        for source in sources:
            causal_reads = [read for read, writers in last_writers.items() if source in writers]
            addresses = tuple(sorted({
                write for write in source.writes
                if any(_overlap(write, read) for read in causal_reads)
            }))
            if not addresses:
                continue
            if source.law_id in candidate_ids:
                backed = True
                evidence = {
                    "excluded": "candidate_skill_laws",
                    "target_occurrences_present": present_counts[target.pair_key],
                    "target_occurrences_ablated": 0,
                }
            else:
                counterfactual = ablated_counts.get(source.law_id)
                backed = counterfactual is not None and counterfactual[target.pair_key] < present_counts[target.pair_key]
                evidence = None if counterfactual is None else {
                    "excluded": source.law_id,
                    "target_occurrences_present": present_counts[target.pair_key],
                    "target_occurrences_ablated": counterfactual[target.pair_key],
                }
            realized.append(DependencyEdge(
                source.node_id, target.node_id, addresses, source.law_id,
                target.law_id, backed, evidence,
            ))
    roots = {node.node_id for node in direct}
    nodes = (*direct, *additional)
    realized_depth, realized_path, realized_laws = _longest_structural_path(nodes, realized, roots)
    necessity = [edge for edge in realized if edge.necessity_backed]
    necessity_depth, necessity_path, necessity_laws = _longest_structural_path(nodes, necessity, roots)
    gap = realized_depth - necessity_depth
    node_rows = [{
        "node_id": node.node_id,
        "kind": "candidate_direct" if node.node_id in roots else "world",
        "law_id": node.law_id,
        "phase": node.phase,
        "order": list(node.order),
        "bindings": dict(node.bindings),
        "reads": list(node.reads),
        "writes": list(node.writes),
    } for node in sorted(nodes, key=lambda item: (item.order, item.node_id))]
    return {
        "available": True,
        "candidate_activated": True,
        "realized_dependency_depth": realized_depth,
        "necessity_backed_depth": necessity_depth,
        "depth_gap": gap,
        "possible_redundant_causation": gap > 0,
        "gap_interpretation": "diagnostic only; compatible with redundancy, overdetermination, or another non-necessary realized dependency",
        "necessity_interpretation": "conservative lower bound from single-law ablation",
        "binding_policy": "identity_equality",
        "dependency_nodes": node_rows,
        "dependency_edges": [edge.to_dict() for edge in realized],
        "necessity_edges": [edge.to_dict() for edge in necessity],
        "dependency_path": realized_path,
        "dependency_path_law_ids": realized_laws,
        "necessity_path": necessity_path,
        "necessity_path_law_ids": necessity_laws,
    }


def evaluate_dependency_profile(
    scenario: Any,
    candidate_skill: str,
    *,
    catalog: Mapping[str, Any],
    compile_mechanic,
    world_setup=None,
) -> dict[str, Any]:
    if candidate_skill not in catalog:
        return {"available": False, "reason": "candidate absent from catalog"}
    with_run = run_scenario(scenario, (candidate_skill,), catalog=dict(catalog), compile_mechanic=compile_mechanic, world_setup=world_setup)
    without_run = run_scenario(scenario, (), catalog=dict(catalog), compile_mechanic=compile_mechanic, world_setup=world_setup)
    compiled = compile_mechanic(catalog[candidate_skill])
    candidate_laws = tuple(parse_law(raw) for raw in compiled["laws"])
    world_laws = tuple(load_laws(ROOT / "substrate" / "world_laws.json"))
    law_map = {law.law_id: law for law in (*world_laws, *candidate_laws)}
    absent = Counter(
        node.pair_key for node in _extract_occurrences(without_run, law_map)
        if node.law_id.startswith(WORLD_PREFIX)
    )
    additional_ids: set[str] = set()
    for node in _extract_occurrences(with_run, law_map):
        if not node.law_id.startswith(WORLD_PREFIX):
            continue
        if absent[node.pair_key]:
            absent[node.pair_key] -= 1
        else:
            additional_ids.add(node.law_id)
    ablations = {
        law_id: run_scenario(
            scenario, (candidate_skill,), catalog=dict(catalog), compile_mechanic=compile_mechanic,
            world_setup=world_setup, excluded_world_law_ids=(law_id,),
        )
        for law_id in sorted(additional_ids)
    }
    return dependency_profile_from_runs(
        with_run, without_run, candidate_skill, world_laws=world_laws,
        candidate_laws=candidate_laws, world_law_ablations=ablations,
    )
