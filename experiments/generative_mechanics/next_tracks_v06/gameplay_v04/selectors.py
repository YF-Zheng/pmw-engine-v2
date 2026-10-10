"""Capability-gated resolution of typed gameplay selectors."""

from __future__ import annotations

from typing import Any

from pmw import WorldState

from .contracts import (
    SELECTOR_KINDS, GameplayContractError, ScopeCapability, ScopedSelector,
    SelectorContext,
)


def parse_selector(raw: Any) -> ScopedSelector:
    if not isinstance(raw, dict):
        raise GameplayContractError("selector must be an object")
    kind = raw.get("kind")
    if kind not in SELECTOR_KINDS:
        raise GameplayContractError("unknown selector kind")
    allowed = {"kind", "relation_type"} if kind == "linked_object" else {"kind"}
    if set(raw) != allowed:
        raise GameplayContractError("selector has missing or unexpected fields")
    relation_type = raw.get("relation_type")
    if kind == "linked_object" and (not isinstance(relation_type, str) or not relation_type):
        raise GameplayContractError("linked_object requires relation_type")
    return ScopedSelector(kind, relation_type)


def resolve_selector(
    world: WorldState,
    selector: ScopedSelector,
    context: SelectorContext,
    capability: ScopeCapability,
) -> tuple[str, ...]:
    if selector.kind not in capability.selectors:
        raise GameplayContractError(f"selector {selector.kind!r} is not authorized")
    actor = world.entities.get(context.actor_id)
    if actor is None or "pmw_gameplay_actor" not in actor.components:
        raise GameplayContractError("selector actor is unavailable")
    if selector.kind == "self":
        return (actor.id,)
    if selector.kind == "target_actor":
        target = world.entities.get(context.target_actor_id or "")
        if target is None or "pmw_gameplay_actor" not in target.components:
            raise GameplayContractError("target_actor is unavailable")
        return (target.id,)
    current = _current_area(world, actor.id)
    if selector.kind == "current_area":
        return (current,)
    if selector.kind == "adjacent_area":
        adjacent = tuple(sorted({
            relation.target if relation.source == current else relation.source
            for relation in world.relations.values()
            if relation.type == "adjacent" and current in {relation.source, relation.target}
        }))
        if any(
            area_id not in world.entities
            or "pmw_gameplay_area" not in world.entities[area_id].components
            for area_id in adjacent
        ):
            raise GameplayContractError("adjacent relation endpoint is not an Area")
        return adjacent
    assert selector.kind == "linked_object"
    if selector.relation_type not in capability.relation_types:
        raise GameplayContractError("linked relation type is not authorized")
    return tuple(sorted({
        relation.target if relation.source == current else relation.source
        for relation in world.relations.values()
        if relation.type == selector.relation_type
        and current in {relation.source, relation.target}
    }))


def _current_area(world: WorldState, actor_id: str) -> str:
    areas = sorted(
        relation.target for relation in world.relations.values()
        if relation.type == "located_in" and relation.source == actor_id
    )
    if len(areas) != 1:
        raise GameplayContractError("actor must have exactly one current Area")
    area = world.entities.get(areas[0])
    if area is None or "pmw_gameplay_area" not in area.components:
        raise GameplayContractError("located_in target is not an Area")
    return area.id
