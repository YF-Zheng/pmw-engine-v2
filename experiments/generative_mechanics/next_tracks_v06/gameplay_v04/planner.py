"""Deterministic bounded planning for the generic AI controller."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import time
from typing import Any, Callable

from .actions import ActionRegistry
from .build_analysis import BuildAnalyzer, RegistrySemanticsProvider
from .contracts import GameplayContractError
from .legal_actions import LegalAction, LegalActionGenerator
from .observation import ActorObservation, canonical_json
from .simulation import SandboxSimulator, SimulationResult
from .utility import UtilityEvaluator, UtilityScore


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    max_legal_actions: int = 32
    max_nodes: int = 128
    max_response_branches: int = 12
    max_second_actions: int = 16
    deadline_ms: int | None = 1000

    def __post_init__(self):
        values = (self.max_legal_actions, self.max_nodes, self.max_response_branches, self.max_second_actions)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values):
            raise GameplayContractError("planner limits must be positive integers")
        if self.max_nodes < self.max_legal_actions:
            raise GameplayContractError("node budget must reserve one simulation per legal action")
        if self.deadline_ms is not None and (
            isinstance(self.deadline_ms, bool) or not isinstance(self.deadline_ms, int) or self.deadline_ms < 1
        ):
            raise GameplayContractError("deadline_ms must be positive or None")


@dataclass(frozen=True, slots=True)
class DecisionLog:
    document_json: str
    canonical_sha256: str

    @classmethod
    def create(cls, document: dict[str, Any]) -> "DecisionLog":
        raw = canonical_json(document)
        return cls(raw, hashlib.sha256(raw.encode("ascii")).hexdigest())

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.document_json)


@dataclass(frozen=True, slots=True)
class PlanResult:
    selected: LegalAction | None
    score: float | None
    nodes_used: int
    fallback_used: bool
    decision_log: DecisionLog


@dataclass(frozen=True, slots=True)
class _ScoredSimulation:
    action: LegalAction
    result: SimulationResult
    score: UtilityScore


class BoundedPlanner:
    def __init__(
        self,
        registry: ActionRegistry,
        *,
        config: PlannerConfig | None = None,
        utility: UtilityEvaluator | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.registry = registry
        self.config = config or PlannerConfig()
        self.utility = utility or UtilityEvaluator()
        self.clock = clock
        self.generator = LegalActionGenerator(registry, max_candidates=self.config.max_legal_actions)
        self.simulator = SandboxSimulator(registry)
        self.analyzer = BuildAnalyzer(RegistrySemanticsProvider(registry))

    def choose(self, observation: ActorObservation) -> PlanResult:
        actor_id = observation.observer_id
        started = self.clock()
        deadline = None if self.config.deadline_ms is None else started + self.config.deadline_ms / 1000.0
        roots = self.generator.generate(observation, request_namespace="root")
        config_hash = hashlib.sha256(canonical_json(asdict(self.config)).encode("ascii")).hexdigest()
        registry_hash = _visible_registry_hash(self.registry, observation)
        if not roots:
            log = self._log(observation, config_hash, registry_hash, (), (), None, 0, "no_legal_action", False, ())
            return PlanResult(None, None, 0, False, log)

        action_ids = observation.to_dict()["known_actions"].get(actor_id, ())
        graph = self.analyzer.analyze(action_ids)
        potential_scale = max(1, len(set(action_ids)) - 1)

        # Mandatory complete one-step table.  The wall deadline is deliberately
        # not consulted until this deterministic fallback exists.
        baseline: list[_ScoredSimulation] = []
        node_rows: list[dict[str, Any]] = []
        nodes = 0
        for action in roots:
            result = self.simulator.simulate(observation, action.request)
            if not result.legal:
                continue  # A projected state should agree with generation.
            nodes += 1
            score = self.utility.evaluate(
                observation, result.next_observation, perspective_actor_id=actor_id,
                future_potential_delta=min(
                    1.0, len(graph.successors(action.request.action_id)) / potential_scale,
                ),
            )
            baseline.append(_ScoredSimulation(action, result, score))
            node_rows.append(_node_row("one_step", action, result, score))
        if not baseline:
            log = self._log(observation, config_hash, registry_hash, roots, (), None, nodes, "no_legal_action", False, tuple(node_rows))
            return PlanResult(None, None, nodes, False, log)
        fallback = _best(baseline)
        if nodes >= self.config.max_nodes:
            return self._fallback(observation, config_hash, registry_hash, roots, baseline, fallback, nodes, "node_budget", node_rows)
        if deadline is not None and self.clock() >= deadline:
            return self._fallback(observation, config_hash, registry_hash, roots, baseline, fallback, nodes, "deadline", node_rows)

        completed_paths: list[tuple[float, str, _ScoredSimulation, dict[str, Any]]] = []
        cutoff: str | None = None
        for root in baseline:
            if _budget_exhausted(nodes, self.config.max_nodes, deadline, self.clock):
                cutoff = "node_budget" if nodes >= self.config.max_nodes else "deadline"; break
            after_root = root.result.next_observation
            opponent_id = _first_living_opponent(after_root, actor_id)
            response_row: dict[str, Any] | None = None
            after_response = after_root
            if opponent_id is not None:
                opponent_obs = after_root.for_observer(opponent_id)
                responses = self.generator.generate(
                    opponent_obs, actor_id=opponent_id,
                    request_namespace=f"response_{root.action.canonical_key}",
                )[:self.config.max_response_branches]
                response_scores: list[_ScoredSimulation] = []
                for response in responses:
                    if _budget_exhausted(nodes, self.config.max_nodes, deadline, self.clock):
                        cutoff = "node_budget" if nodes >= self.config.max_nodes else "deadline"; break
                    result = self.simulator.simulate(
                        opponent_obs, response.request,
                        owner_turn_before=True, complete_round_after=True,
                    )
                    nodes += 1
                    if not result.legal:
                        continue
                    score = self.utility.evaluate(
                        opponent_obs, result.next_observation,
                        perspective_actor_id=opponent_id,
                    )
                    response_scores.append(_ScoredSimulation(response, result, score))
                    node_rows.append(_node_row("opponent_response", response, result, score))
                if cutoff is not None:
                    break
                if response_scores:
                    modeled = _best(response_scores)
                    after_response = modeled.result.next_observation.for_observer(actor_id)
                    response_row = {
                        "action": modeled.action.canonical_key,
                        "opponent_score": modeled.score.to_dict(),
                    }
            second_actions = self.generator.generate(
                after_response, actor_id=actor_id,
                request_namespace=f"second_{root.action.canonical_key}",
            )
            successors = set(graph.successors(root.action.request.action_id))
            second_actions = tuple(sorted(
                second_actions,
                key=lambda action: (0 if action.request.action_id in successors else 1, action.canonical_key),
            ))[:self.config.max_second_actions]
            for second in second_actions:
                if _budget_exhausted(nodes, self.config.max_nodes, deadline, self.clock):
                    cutoff = "node_budget" if nodes >= self.config.max_nodes else "deadline"; break
                result = self.simulator.simulate(after_response, second.request, owner_turn_before=True)
                nodes += 1
                if not result.legal:
                    continue
                continuation = self.utility.evaluate(
                    after_root, result.next_observation,
                    perspective_actor_id=actor_id, depth=1,
                )
                total = root.score.total + continuation.total
                node_rows.append(_node_row("second_action", second, result, continuation))
                completed_paths.append((total, root.action.canonical_key, root, {
                    "first": root.action.canonical_key,
                    "response": response_row,
                    "second": second.canonical_key,
                    "total": total,
                    "continuation": continuation.to_dict(),
                }))
            if cutoff is not None:
                break
        if cutoff is not None:
            return self._fallback(observation, config_hash, registry_hash, roots, baseline, fallback, nodes, cutoff, node_rows)
        if not completed_paths:
            return self._fallback(observation, config_hash, registry_hash, roots, baseline, fallback, nodes, "complete", node_rows)
        completed_paths.sort(key=lambda row: (-row[0], row[1], canonical_json(row[3])))
        best_total, _, best_root, best_path = completed_paths[0]
        paths = tuple(row[3] for row in sorted(completed_paths, key=lambda row: (row[1], canonical_json(row[3]))))
        log = self._log(observation, config_hash, registry_hash, roots, baseline, best_root.action, nodes,
                        "complete", False, tuple(node_rows), paths, best_path)
        return PlanResult(best_root.action, best_total, nodes, False, log)

    def _fallback(self, observation, config_hash, registry_hash, roots, baseline, fallback, nodes, reason, rows):
        log = self._log(observation, config_hash, registry_hash, roots, baseline, fallback.action, nodes,
                        reason, True, tuple(rows))
        return PlanResult(fallback.action, fallback.score.total, nodes, True, log)

    def _log(
        self, observation, config_hash, registry_hash, roots, baseline, selected, nodes, cutoff_reason,
        fallback_used, node_rows, paths=(), selected_path=None,
    ) -> DecisionLog:
        baseline_map = {row.action.canonical_key: row for row in baseline}
        candidates = []
        for action in roots:
            scored = baseline_map.get(action.canonical_key)
            candidates.append({
                "canonical_key": action.canonical_key,
                "request": _request_dict(action),
                "one_step_score": None if scored is None else scored.score.to_dict(),
                "one_step_trace": None if scored is None else scored.result.trace(),
            })
        return DecisionLog.create({
            "protocol": "pmw-ai-decision-v0.4",
            "observation_sha256": observation.canonical_sha256,
            "config_sha256": config_hash,
            "visible_registry_sha256": registry_hash,
            "candidates": candidates,
            "nodes": list(node_rows),
            "paths": list(paths),
            "selected": None if selected is None else _request_dict(selected),
            "selected_path": selected_path,
            "nodes_used": nodes,
            "node_budget": self.config.max_nodes,
            "cutoff_reason": cutoff_reason,
            "fallback_used": fallback_used,
        })


def _best(rows: list[_ScoredSimulation]) -> _ScoredSimulation:
    return sorted(rows, key=lambda row: (-row.score.total, row.action.canonical_key))[0]


def _budget_exhausted(nodes: int, maximum: int, deadline: float | None, clock) -> bool:
    return nodes >= maximum or deadline is not None and clock() >= deadline


def _first_living_opponent(observation: ActorObservation, actor_id: str) -> str | None:
    actors = observation.to_dict()["actors"]
    return next((key for key, value in sorted(actors.items()) if key != actor_id and value["hp"] > 0), None)


def _request_dict(action: LegalAction) -> dict[str, Any]:
    request = action.request
    return {
        "request_id": request.request_id, "actor_id": request.actor_id,
        "action_id": request.action_id, "target_actor_id": request.target_actor_id,
    }


def _node_row(kind: str, action: LegalAction, result: SimulationResult, score: UtilityScore) -> dict[str, Any]:
    return {
        "kind": kind,
        "action": action.canonical_key,
        "next_observation_sha256": result.next_observation.canonical_sha256,
        "score": score.to_dict(),
        "trace": result.trace(),
    }


def _visible_registry_hash(registry: ActionRegistry, observation: ActorObservation) -> str:
    document = observation.to_dict()
    ids = sorted({item for rows in document["known_actions"].values() for item in rows})
    rows = [
        {"id": action_id, "canonical_hash": registry.actions[action_id].canonical_hash}
        for action_id in ids if action_id in registry.actions
    ]
    return hashlib.sha256(canonical_json(rows).encode("ascii")).hexdigest()
