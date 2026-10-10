"""Independent pure reference model for normalized dynamics.

This module deliberately has no dependency on the compiler, law builder, or PMW.
It is an oracle for differential tests, not a production simulation backend.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class AttractorContribution:
    source_id: str
    target: float
    weight: float


@dataclass(frozen=True, slots=True)
class DynamicsNode:
    value: float
    base_attractor: float
    base_weight: float
    base_alpha: float
    attractors: tuple[AttractorContribution, ...] = ()
    alpha_deltas: tuple[tuple[str, float], ...] = ()
    drives: tuple[tuple[str, float], ...] = ()
    drive_limit: float = 1.0


@dataclass(frozen=True, slots=True)
class Coupling:
    edge_id: str
    left: str
    right: str
    conductivity: float


@dataclass(frozen=True, slots=True)
class StepDiagnostics:
    effective_attractor: float
    effective_alpha: float
    effective_drive: float
    coupling: float
    intrinsic: float
    unclamped: float
    clamp_loss: float
    next_value: float


def _number(value: object, name: str, low: float | None = None, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite non-bool number")
    result = float(value)
    if low is not None and result < low or high is not None and result > high:
        raise ValueError(f"{name} outside [{low}, {high}]")
    return 0.0 if result == 0.0 else result


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _clamp(value: float, low: float, high: float) -> float:
    result = max(low, min(value, high))
    if result == 0.0:
        return 0.0
    if result == 1.0:
        return 1.0
    return result


def _validated_node(node: DynamicsNode, node_id: str = "node") -> DynamicsNode:
    _identifier(node_id, "node_id")
    value = _number(node.value, f"{node_id}.value", 0.0, 1.0)
    base_attractor = _number(node.base_attractor, f"{node_id}.base_attractor", 0.0, 1.0)
    base_weight = _number(node.base_weight, f"{node_id}.base_weight")
    if base_weight <= 0.0:
        raise ValueError(f"{node_id}.base_weight must be positive")
    base_alpha = _number(node.base_alpha, f"{node_id}.base_alpha", 0.0, 1.0)
    drive_limit = _number(node.drive_limit, f"{node_id}.drive_limit")
    if drive_limit < 0.0:
        raise ValueError(f"{node_id}.drive_limit must be non-negative")
    seen: set[str] = set()
    attractors = []
    for item in sorted(node.attractors, key=lambda item: item.source_id):
        source_id = _identifier(item.source_id, "attractor.source_id")
        if source_id in seen:
            raise ValueError(f"duplicate dynamics source_id {source_id!r}")
        seen.add(source_id)
        attractors.append(AttractorContribution(
            source_id,
            _number(item.target, f"attractor[{source_id}].target", 0.0, 1.0),
            _number(item.weight, f"attractor[{source_id}].weight", 0.0, None),
        ))
    alpha_deltas = _validated_pairs(node.alpha_deltas, "alpha_delta", seen)
    drives = _validated_pairs(node.drives, "drive", seen)
    return DynamicsNode(value, base_attractor, base_weight, base_alpha, tuple(attractors), alpha_deltas, drives, drive_limit)


def _validated_pairs(
    pairs: Sequence[tuple[str, float]], name: str, globally_seen: set[str]
) -> tuple[tuple[str, float], ...]:
    result = []
    local_seen: set[str] = set()
    for source_id, raw in sorted(pairs, key=lambda item: item[0]):
        source_id = _identifier(source_id, f"{name}.source_id")
        if source_id in local_seen:
            raise ValueError(f"duplicate {name} source_id {source_id!r}")
        local_seen.add(source_id)
        # A single artifact may intentionally own one source of each kind, so
        # source IDs are unique within a contribution kind rather than globally.
        result.append((source_id, _number(raw, f"{name}[{source_id}]")))
    return tuple(result)


def normalized_step(node: DynamicsNode, coupling: float = 0.0) -> StepDiagnostics:
    """Advance one node using a precomputed simultaneous coupling contribution."""

    node = _validated_node(node)
    coupling = _number(coupling, "coupling")
    weighted = node.base_weight * node.base_attractor
    total_weight = node.base_weight
    for item in node.attractors:
        weighted += item.weight * item.target
        total_weight += item.weight
    effective_attractor = weighted / total_weight
    effective_alpha = _clamp(node.base_alpha + sum(value for _, value in node.alpha_deltas), 0.0, 1.0)
    effective_drive = _clamp(sum(value for _, value in node.drives), -node.drive_limit, node.drive_limit)
    intrinsic = effective_alpha * (effective_attractor - node.value) + effective_drive
    unclamped = node.value + intrinsic + coupling
    next_value = _clamp(unclamped, 0.0, 1.0)
    return StepDiagnostics(
        effective_attractor,
        effective_alpha,
        effective_drive,
        coupling,
        intrinsic,
        unclamped,
        next_value - unclamped,
        next_value,
    )


def normalized_network_step(
    nodes: Mapping[str, DynamicsNode], couplings: Sequence[Coupling] = ()
) -> dict[str, StepDiagnostics]:
    """Advance a network simultaneously from one immutable input snapshot."""

    validated = {node_id: _validated_node(node, node_id) for node_id, node in sorted(nodes.items())}
    contributions = {node_id: 0.0 for node_id in validated}
    seen_edges: set[str] = set()
    for edge in sorted(couplings, key=lambda item: item.edge_id):
        edge_id = _identifier(edge.edge_id, "coupling.edge_id")
        if edge_id in seen_edges:
            raise ValueError(f"duplicate coupling edge_id {edge_id!r}")
        seen_edges.add(edge_id)
        if edge.left not in validated or edge.right not in validated:
            raise ValueError(f"coupling {edge_id!r} has unknown endpoint")
        conductivity = _number(edge.conductivity, f"coupling[{edge_id}].conductivity", 0.0, 1.0)
        transfer = conductivity * (validated[edge.right].value - validated[edge.left].value)
        contributions[edge.left] += transfer
        contributions[edge.right] -= transfer
    return {
        node_id: normalized_step(validated[node_id], contributions[node_id])
        for node_id in sorted(validated)
    }
