"""Name-independent read/write analysis for generated action builds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .actions import ActionDefinition, ActionRegistry
from .conditions import ConditionSpec


@dataclass(frozen=True, slots=True, order=True)
class SemanticRead:
    scope: str
    path: str
    predicate: str
    value: object
    source: str


@dataclass(frozen=True, slots=True, order=True)
class SemanticWrite:
    scope: str
    path: str
    operation: str
    availability_delay: int
    source: str


@dataclass(frozen=True, slots=True)
class ActionSemantics:
    action_id: str
    reads: tuple[SemanticRead, ...]
    writes: tuple[SemanticWrite, ...]


class ActionSemanticsProvider(Protocol):
    """Gate-3 SkillBlueprint adapters can satisfy this narrow protocol."""

    def semantics(self, action_id: str) -> ActionSemantics: ...


@dataclass(frozen=True, slots=True)
class SynergyEdge:
    producer_action_id: str
    consumer_action_id: str
    kind: str
    producer_write: SemanticWrite
    consumer_read: SemanticRead


@dataclass(frozen=True, slots=True)
class BuildGraph:
    action_ids: tuple[str, ...]
    edges: tuple[SynergyEdge, ...]

    def successors(self, action_id: str) -> tuple[str, ...]:
        return tuple(sorted({edge.consumer_action_id for edge in self.edges if edge.producer_action_id == action_id}))


class RegistrySemanticsProvider:
    def __init__(self, registry: ActionRegistry):
        self.registry = registry

    def semantics(self, action_id: str) -> ActionSemantics:
        return semantics_from_action(self.registry.actions[action_id])


class BuildAnalyzer:
    def __init__(self, provider: ActionSemanticsProvider):
        self.provider = provider

    def analyze(self, action_ids) -> BuildGraph:
        ids = tuple(sorted(set(action_ids)))
        rows = {action_id: self.provider.semantics(action_id) for action_id in ids}
        edges: list[SynergyEdge] = []
        for producer_id in ids:
            for consumer_id in ids:
                if producer_id == consumer_id:
                    continue
                for write in rows[producer_id].writes:
                    for read in rows[consumer_id].reads:
                        kind = _edge_kind(write, read)
                        if kind is not None:
                            edges.append(SynergyEdge(producer_id, consumer_id, kind, write, read))
        return BuildGraph(ids, tuple(sorted(
            edges,
            key=lambda edge: (
                edge.producer_action_id, edge.consumer_action_id, edge.kind,
                edge.producer_write, edge.consumer_read,
            ),
        )))


def semantics_from_action(action: ActionDefinition) -> ActionSemantics:
    reads: list[SemanticRead] = [
        SemanticRead("self", "resource:mana", "gte", action.cost.mana, "cost")
    ]
    writes: list[SemanticWrite] = []
    for modifier in action.cost_modifiers:
        reads.extend(_condition_reads(modifier.condition, f"cost_modifier:{modifier.id}"))
    for effect in action.effects:
        reads.extend(_condition_reads(effect.condition, f"effect:{effect.id}:condition"))
        for term in effect.terms:
            term_value = (
                term.coefficient if term.kind == "scaling"
                else term.threshold if term.kind in {"threshold", "check"}
                else term.value
            )
            reads.append(SemanticRead("self", f"attribute:{term.attribute}", term.kind, term_value, f"effect:{effect.id}:term"))
        scope = effect.target.kind
        path = {
            "damage": "resource:hp",
            "heal": "resource:hp",
            "shield": "resource:shield",
            "add_resource": f"resource:{effect.resource}",
            "apply_status": f"status:{effect.status_id}",
            "grant_trait": f"trait:{effect.trait_id}",
            "modify_field": f"field:{effect.field_id}:value",
            "modify_attractor": f"field:{effect.field_id}:target",
            "modify_rate": f"field:{effect.field_id}:rate",
        }[effect.kind]
        delay = 1 if effect.kind == "modify_rate" else 0
        writes.append(SemanticWrite(scope, path, effect.kind, delay, f"effect:{effect.id}"))
    return ActionSemantics(action.id, tuple(sorted(set(reads))), tuple(sorted(set(writes))))


def _condition_reads(condition: ConditionSpec, source: str) -> list[SemanticRead]:
    if condition.kind == "always":
        return []
    if condition.kind in {"all", "any", "not"}:
        return [item for child in condition.children for item in _condition_reads(child, source)]
    if condition.kind == "attribute":
        path = f"attribute:{condition.key}"
    elif condition.kind == "resource":
        path = f"resource:{condition.key}"
    elif condition.kind == "field":
        path = f"field:{condition.key}:value"
    elif condition.kind == "has_trait":
        path = f"trait:{condition.key}"
    elif condition.kind == "has_status":
        path = f"status:{condition.key}"
    else:
        return []
    return [SemanticRead(condition.subject or "self", path, condition.comparator or condition.kind, condition.value, source)]


def _edge_kind(write: SemanticWrite, read: SemanticRead) -> str | None:
    if write.scope != read.scope or write.path != read.path:
        # A recovery-rate change can supply the corresponding resource on a
        # later tick even though its normalized paths intentionally differ.
        if (
            write.scope == read.scope
            and write.path.startswith("field:") and write.path.endswith(":rate")
            and read.path == f"resource:{write.path.split(':')[1]}"
        ):
            return "changes_recovery_for_later_resource"
        return None
    if write.path.startswith("status:"):
        return "applies_then_consumes_status"
    if write.path.startswith("resource:"):
        return "supplies_resource"
    if write.path.startswith("field:"):
        return "enables_field_condition"
    if write.path.startswith("trait:"):
        return "enables_trait_condition"
    return "enables_condition"
