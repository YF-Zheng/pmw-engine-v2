"""Exact four-world belief solver whose transitions are real PMW executions."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from typing import Any

from .actions import execute_preparation, execute_repair, legal_actions
from .engine_scenario import ROOTS, WORLD_PRIOR, build_f2_runtime


World = tuple[str, str]


@dataclass(frozen=True, slots=True)
class SolveResult:
    value: float
    optimal_actions: tuple[str, ...]
    q_values: dict[str, float]
    policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "optimal_actions": list(self.optimal_actions),
            "q_values": self.q_values,
            "policy": self.policy,
        }


def solve_equivalent(cf: float, ci: float, *, information_ablation: bool = False) -> SolveResult:
    return _solve(_belief_tuple(WORLD_PRIOR), (), cf, ci, information_ablation, native=False)


def solve_native(*, information_ablation: bool = False) -> SolveResult:
    return _solve(_belief_tuple(WORLD_PRIOR), (), 0.0, 0.0, information_ablation, native=True)


@lru_cache(maxsize=None)
def _solve(
    belief_rows: tuple[tuple[World, float], ...],
    history: tuple[str, ...],
    cf: float,
    ci: float,
    information_ablation: bool,
    *,
    native: bool,
) -> SolveResult:
    belief = dict(belief_rows)
    actions = _legal(next(iter(belief)), history)
    q_values: dict[str, float] = {}
    branches_by_action: dict[str, Any] = {}
    for action in actions:
        if action.startswith("repair_"):
            value = 0.0
            outcomes = {}
            for world, probability in belief.items():
                success, final_stability = _terminal(world, history, action)
                value += probability * float(success)
                outcomes[_world_id(world)] = {
                    "probability": probability,
                    "success": success,
                    "final_stability": final_stability,
                }
            q_values[action] = value
            branches_by_action[action] = {"terminal": outcomes}
            continue

        groups: dict[str, dict[World, float]] = {}
        observations: dict[str, dict[str, Any]] = {}
        for world, probability in belief.items():
            public = _prep_observation(world, history, action, information_ablation)
            key = json.dumps(public, sort_keys=True, separators=(",", ":"), allow_nan=False)
            groups.setdefault(key, {})[world] = probability
            observations[key] = public
        expected = 0.0
        branch_rows = []
        for key, raw_group in sorted(groups.items()):
            mass = sum(raw_group.values())
            posterior = {world: probability / mass for world, probability in raw_group.items()}
            child = _solve(
                _belief_tuple(posterior), (*history, action), cf, ci,
                information_ablation, native=native,
            )
            expected += mass * child.value
            branch_rows.append({
                "observation": observations[key],
                "probability": mass,
                "posterior": {_world_id(world): value for world, value in sorted(posterior.items())},
                "value": child.value,
                "optimal_actions": list(child.optimal_actions),
                "policy": child.policy,
            })
        cost = 0.0 if native else ci if action == "calibrate" else cf if action.startswith("forge_") else 0.0
        q_values[action] = expected - cost
        branches_by_action[action] = {"cost": cost, "branches": branch_rows}

    best = max(q_values.values())
    optimal = tuple(sorted(action for action, value in q_values.items() if abs(value - best) < 1e-12))
    return SolveResult(
        best,
        optimal,
        q_values,
        {
            "history": list(history),
            "belief": {_world_id(world): value for world, value in sorted(belief.items())},
            "actions": branches_by_action,
        },
    )


def _replay(world: World, history: tuple[str, ...]):
    runtime = build_f2_runtime(*world)
    transitions = []
    for action in history:
        transitions.append(execute_preparation(runtime, action))
    return runtime, transitions


@lru_cache(maxsize=None)
def _legal(world: World, history: tuple[str, ...]) -> tuple[str, ...]:
    return legal_actions(_replay(world, history)[0])


@lru_cache(maxsize=None)
def _prep_raw(world: World, history: tuple[str, ...], action: str) -> str:
    runtime, _ = _replay(world, history)
    transition = execute_preparation(runtime, action)
    row = {
        "calibrated_interface": transition.response["calibrated_interface"],
        "probe_implemented": transition.response["probe_implemented"],
        "stability_delta": transition.response["stability_delta"],
        "forged_probe": transition.after["forged_probe"],
    }
    return json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _prep_observation(
    world: World,
    history: tuple[str, ...],
    action: str,
    ablated: bool,
) -> dict[str, Any]:
    row = json.loads(_prep_raw(world, history, action))
    if action == "calibrate":
        return {"calibrated_interface": row["calibrated_interface"]}
    if action == "probe":
        if ablated:
            return {"probe_result": "withheld"}
        return {
            "probe_implemented": row["probe_implemented"],
            "stability_delta": row["stability_delta"],
        }
    return {"forged_probe": row["forged_probe"]}


@lru_cache(maxsize=None)
def _terminal(world: World, history: tuple[str, ...], action: str) -> tuple[bool, float]:
    runtime, _ = _replay(world, history)
    transition, success = execute_repair(runtime, action)
    return success, transition.after["stability"]


def _world_id(world: World) -> str:
    return f"H={world[0]},X={world[1]}"


def _belief_tuple(belief: dict[World, float]) -> tuple[tuple[World, float], ...]:
    return tuple(sorted((world, round(value, 15)) for world, value in belief.items()))
