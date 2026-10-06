"""Paired-counterfactual downstream causal-depth evidence for Free Invention.

Depth is the longest directed path of *additional* ``gm.world.*`` law
occurrences reachable from a committed candidate-law write.  Candidate laws are
roots and do not contribute to the numeric depth. Edges are realized
write/read dependencies between strictly ordered commits, not elapsed time or
the number of scenario steps. A world-to-world edge also requires a registered
rerun with its upstream law removed and a reduced downstream occurrence count.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from pmw import load_laws

from .runner import ScenarioRun, run_scenario


WORLD_PREFIX = "gm.world."
ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class CausalNode:
    node_id: str
    kind: str
    law_id: str
    command_id: str
    event_id: str
    phase: str
    order: tuple[int, int, int]
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    counterfactual_extra: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "law_id": self.law_id,
            "command_id": self.command_id,
            "event_id": self.event_id,
            "phase": self.phase,
            "order": list(self.order),
            "reads": list(self.reads),
            "writes": list(self.writes),
            "counterfactual_extra": self.counterfactual_extra,
        }


@dataclass(frozen=True, slots=True)
class CausalEdge:
    source: str
    target: str
    addresses: tuple[str, ...]
    attribution: str
    ablation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source, "target": self.target,
            "addresses": list(self.addresses), "attribution": self.attribution,
            "ablation": self.ablation,
        }


@dataclass(frozen=True, slots=True)
class CausalDepthResult:
    available: bool
    reason: str | None
    depth: int | None
    candidate_activated: bool | None
    candidate_skill: str
    estimand: str
    nodes: tuple[CausalNode, ...]
    edges: tuple[CausalEdge, ...]
    longest_path: tuple[str, ...]
    longest_path_law_ids: tuple[str, ...]
    reached_world_law_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "depth": self.depth,
            "candidate_activated": self.candidate_activated,
            "candidate_skill": self.candidate_skill,
            "estimand": self.estimand,
            "evidence": {
                "nodes": [item.to_dict() for item in self.nodes],
                "edges": [item.to_dict() for item in self.edges],
                "longest_path": list(self.longest_path),
                "longest_path_law_ids": list(self.longest_path_law_ids),
                "reached_world_law_ids": list(self.reached_world_law_ids),
            },
        }


@dataclass(frozen=True, slots=True)
class _Occurrence:
    node_id: str
    law_id: str
    command_id: str
    event_id: str
    event_type: str
    event_time: float
    phase: str
    order: tuple[int, int, int]
    bindings: tuple[tuple[str, str], ...]
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    ordinal: int

    @property
    def pair_key(self) -> tuple[Any, ...]:
        # Root/event identity and bindings distinguish repeated matches while the
        # local ordinal handles exact duplicate matches deterministically.
        return (
            self.command_id, self.event_id, self.event_type, self.event_time,
            self.phase, self.law_id, self.bindings, self.ordinal,
        )


def _walk_refs(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        if value.startswith("$"):
            yield value
    elif isinstance(value, list) or isinstance(value, tuple):
        for item in value:
            yield from _walk_refs(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and "." in key:
                yield f"${key}"
            yield from _walk_refs(item)


def _resolve_reference(reference: str, bindings: Mapping[str, str], binding_kinds: Mapping[str, str]) -> str | None:
    parts = reference.removeprefix("$").split(".")
    if len(parts) < 2 or parts[0] not in bindings:
        return None
    return f"{binding_kinds.get(parts[0], 'entity')}:{bindings[parts[0]]}/{'/'.join(parts[1:])}"


def _law_reads(law: Any, bindings: Mapping[str, str]) -> tuple[str, ...]:
    kinds = {name: spec.get("kind", "entity") for name, spec in law.bindings.items()}
    refs = list(_walk_refs(law.when))
    for effect in law.effects:
        refs.extend(_walk_refs(effect.get("value")))
        # A delta consumes the old target value; a set overwrites it.
        if effect.get("op") == "delta":
            refs.extend(_walk_refs(effect.get("target")))
    return tuple(sorted({
        address for reference in refs
        for address in (_resolve_reference(reference, bindings, kinds),)
        if address is not None
    }))


def _overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _extract_occurrences(run: ScenarioRun, laws: Mapping[str, Any]) -> tuple[_Occurrence, ...]:
    result: list[_Occurrence] = []
    duplicate_ordinals: Counter[tuple[Any, ...]] = Counter()
    serial = 0
    for root_index, root in enumerate(run.roots):
        for event_index, event_trace in enumerate(root.trace.get("events", [])):
            event = event_trace["event"]
            proposal_commit: dict[str, tuple[int, str]] = {}
            proposal_writes: defaultdict[str, set[str]] = defaultdict(set)
            for commit_index, commit in enumerate(event_trace.get("commits", [])):
                for proposal_id in commit.get("accepted_proposal_ids", []):
                    proposal_commit[proposal_id] = (commit_index, commit["phase"])
                for delta in commit.get("state_deltas", []):
                    for proposal_id in delta.get("proposal_ids", []):
                        proposal_writes[proposal_id].add(delta["address"])
            matches = (*event_trace.get("event_law_matches", []), *event_trace.get("state_law_matches", []))
            for match in matches:
                law_id = match["law_id"]
                if law_id not in laws:
                    continue
                accepted = [pid for pid in match.get("proposal_ids", []) if pid in proposal_commit]
                writes = sorted({address for pid in accepted for address in proposal_writes.get(pid, ())})
                if not writes:
                    continue
                commit_indexes = {proposal_commit[pid] for pid in accepted}
                for commit_index, phase in sorted(commit_indexes):
                    commit_ids = [pid for pid in accepted if proposal_commit[pid] == (commit_index, phase)]
                    commit_writes = tuple(sorted({address for pid in commit_ids for address in proposal_writes.get(pid, ())}))
                    if not commit_writes:
                        continue
                    bindings = tuple(sorted(match.get("bindings", {}).items()))
                    base = (root.command_id, event["id"], event["type"], float(event["time"]), phase, law_id, bindings)
                    ordinal = duplicate_ordinals[base]
                    duplicate_ordinals[base] += 1
                    node_id = f"n{serial:05d}"
                    serial += 1
                    result.append(_Occurrence(
                        node_id, law_id, root.command_id, event["id"], event["type"],
                        float(event["time"]), phase, (root_index, event_index, commit_index),
                        bindings, _law_reads(laws[law_id], dict(bindings)), commit_writes, ordinal,
                    ))
    return tuple(result)


def causal_depth_from_runs(
    with_candidate: ScenarioRun,
    without_candidate: ScenarioRun,
    candidate_skill: str,
    *,
    world_laws: Iterable[Any] | None = None,
    candidate_laws: Iterable[Any] = (),
    world_law_ablations: Mapping[str, ScenarioRun] | None = None,
) -> CausalDepthResult:
    """Measure realized downstream depth from an explicit paired execution."""
    if with_candidate.scenario_id != without_candidate.scenario_id:
        return CausalDepthResult(False, "paired runs must use the same scenario", None, None, candidate_skill, "paired_additional_world_law_depth_v0.4", (), (), (), (), ())
    world = tuple(world_laws or load_laws(ROOT / "substrate" / "world_laws.json"))
    law_map = {law.law_id: law for law in (*world, *tuple(candidate_laws))}
    candidate_law_ids = {law.law_id for law in candidate_laws}
    with_nodes = _extract_occurrences(with_candidate, law_map)
    without_keys = Counter(item.pair_key for item in _extract_occurrences(without_candidate, law_map) if item.law_id.startswith(WORLD_PREFIX))

    additional: list[_Occurrence] = []
    for item in with_nodes:
        if not item.law_id.startswith(WORLD_PREFIX):
            continue
        if without_keys[item.pair_key]:
            without_keys[item.pair_key] -= 1
        else:
            additional.append(item)
    direct = [item for item in with_nodes if item.law_id in candidate_law_ids]
    if not direct:
        return CausalDepthResult(
            False,
            "candidate did not activate in this registered arm",
            None,
            False,
            candidate_skill,
            "paired_additional_world_law_depth_v0.4",
            (), (), (), (), (),
        )

    sources = (*direct, *additional)
    all_writers = tuple(
        item for item in with_nodes
        if item.law_id.startswith(WORLD_PREFIX) or item.law_id in candidate_law_ids
    )
    ablation_keys = {
        law_id: Counter(
            item.pair_key for item in _extract_occurrences(run, law_map)
            if item.law_id.startswith(WORLD_PREFIX)
        )
        for law_id, run in (world_law_ablations or {}).items()
    }
    with_key_counts = Counter(item.pair_key for item in with_nodes if item.law_id.startswith(WORLD_PREFIX))
    predecessors: defaultdict[str, list[tuple[str, tuple[str, ...], str, dict[str, Any]]]] = defaultdict(list)
    for target in additional:
        last_writers: defaultdict[str, list[_Occurrence]] = defaultdict(list)
        for read in target.reads:
            candidates = [
                source for source in all_writers
                if source.order < target.order and any(_overlap(write, read) for write in source.writes)
            ]
            if candidates:
                last_order = max(source.order for source in candidates)
                last_writers[read].extend(source for source in candidates if source.order == last_order)
        for source in sources:
            if source.node_id == target.node_id or source.order >= target.order:
                continue
            causal_reads = [read for read, writers in last_writers.items() if source in writers]
            addresses = tuple(sorted({
                write for write in source.writes
                if any(_overlap(write, read) for read in causal_reads)
            }))
            if not addresses:
                continue
            if source.law_id in candidate_law_ids:
                # The candidate-absent member of the primary pair is the direct
                # root ablation; target is already known to be additional there.
                evidence = {
                    "excluded": "candidate_skill_laws",
                    "target_occurrences_present": with_key_counts[target.pair_key],
                    "target_occurrences_ablated": 0,
                }
                predecessors[target.node_id].append((source.node_id, addresses, "candidate_absence", evidence))
                continue
            ablated = ablation_keys.get(source.law_id)
            if ablated is None or ablated[target.pair_key] >= with_key_counts[target.pair_key]:
                continue
            evidence = {
                "excluded": source.law_id,
                "target_occurrences_present": with_key_counts[target.pair_key],
                "target_occurrences_ablated": ablated[target.pair_key],
            }
            predecessors[target.node_id].append((source.node_id, addresses, "world_law_ablation", evidence))

    direct_ids = {item.node_id for item in direct}
    additional_ids = {item.node_id for item in additional}
    # Keep alternatives by reached law set. Repeated execution is retained in
    # occurrence evidence but cannot inflate structural depth.
    states: dict[str, dict[frozenset[str], tuple[str, ...]]] = {
        item.node_id: {frozenset(): (item.node_id,)} for item in direct
    }
    for target in sorted(additional, key=lambda item: (item.order, item.node_id)):
        target_states: dict[frozenset[str], tuple[str, ...]] = {}
        for source_id, _, _, _ in predecessors[target.node_id]:
            if source_id not in states:
                continue
            for law_set, source_path in states[source_id].items():
                reached = law_set | {target.law_id}
                path = (*source_path, target.node_id)
                prior = target_states.get(reached)
                if prior is None or path < prior:
                    target_states[reached] = path
        if target_states:
            states[target.node_id] = target_states

    reachable = {node_id for node_id in additional_ids if node_id in states}
    included_ids = direct_ids | reachable
    edges = tuple(sorted((
        CausalEdge(source_id, target_id, addresses, attribution, evidence)
        for target_id, values in predecessors.items() if target_id in reachable
        for source_id, addresses, attribution, evidence in values if source_id in included_ids and source_id in states
    ), key=lambda item: (item.source, item.target, item.addresses, item.attribution)))
    occurrences = {item.node_id: item for item in sources}
    nodes = tuple(CausalNode(
        item.node_id, "candidate_direct" if item.node_id in direct_ids else "world",
        item.law_id, item.command_id, item.event_id, item.phase, item.order,
        item.reads, item.writes, item.node_id in additional_ids,
    ) for item in sorted((occurrences[node_id] for node_id in included_ids), key=lambda item: (item.order, item.node_id)))
    world_paths = [
        (len(law_set), path, tuple(dict.fromkeys(
            occurrences[node_id].law_id for node_id in path if node_id in additional_ids
        )))
        for node_id, alternatives in states.items() if node_id in reachable
        for law_set, path in alternatives.items()
    ]
    depth, path, path_laws = max(world_paths, key=lambda item: (item[0], tuple(reversed(item[1])))) if world_paths else (0, (), ())
    return CausalDepthResult(
        True, None, depth, True, candidate_skill, "paired_additional_world_law_depth_v0.4",
        nodes, edges, path, path_laws,
        tuple(sorted({occurrences[node_id].law_id for node_id in reachable})),
    )


def evaluate_causal_depth(
    scenario: Any,
    candidate_skill: str,
    *,
    catalog: Mapping[str, Any],
    compile_mechanic,
    world_setup=None,
) -> CausalDepthResult:
    """Run the registered candidate-present/absent pair and return evidence."""
    if candidate_skill not in catalog:
        return CausalDepthResult(False, "candidate is absent from the supplied catalog", None, None, candidate_skill, "paired_additional_world_law_depth_v0.4", (), (), (), (), ())
    with_run = run_scenario(scenario, (candidate_skill,), catalog=dict(catalog), compile_mechanic=compile_mechanic, world_setup=world_setup)
    without_run = run_scenario(scenario, (), catalog=dict(catalog), compile_mechanic=compile_mechanic, world_setup=world_setup)
    compiled = compile_mechanic(catalog[candidate_skill])
    from pmw import parse_law
    candidate_laws = tuple(parse_law(raw) for raw in compiled["laws"])
    world_laws = tuple(load_laws(ROOT / "substrate" / "world_laws.json"))
    law_map = {law.law_id: law for law in (*world_laws, *candidate_laws)}
    absent_keys = Counter(
        item.pair_key for item in _extract_occurrences(without_run, law_map)
        if item.law_id.startswith(WORLD_PREFIX)
    )
    additional_law_ids: set[str] = set()
    for item in _extract_occurrences(with_run, law_map):
        if not item.law_id.startswith(WORLD_PREFIX):
            continue
        if absent_keys[item.pair_key]:
            absent_keys[item.pair_key] -= 1
        else:
            additional_law_ids.add(item.law_id)
    ablations = {
        law_id: run_scenario(
            scenario, (candidate_skill,), catalog=dict(catalog),
            compile_mechanic=compile_mechanic, world_setup=world_setup,
            excluded_world_law_ids=(law_id,),
        )
        for law_id in sorted(additional_law_ids)
    }
    return causal_depth_from_runs(
        with_run, without_run, candidate_skill, world_laws=world_laws,
        candidate_laws=candidate_laws, world_law_ablations=ablations,
    )
