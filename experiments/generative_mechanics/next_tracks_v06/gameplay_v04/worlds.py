"""PMW WorldState construction for gameplay Area and Actor instances."""

from __future__ import annotations

from collections.abc import Iterable

from pmw import Entity, Relation, WorldState

from .contracts import GameplayContractError


def build_gameplay_world(
    world_id: str,
    *,
    areas: Iterable[Entity],
    actors: Iterable[Entity] = (),
    placements: Iterable[tuple[str, str]] = (),
    adjacencies: Iterable[tuple[str, str]] = (),
    links: Iterable[tuple[str, str, str]] = (),
) -> WorldState:
    area_items = tuple(areas)
    actor_items = tuple(actors)
    all_entities = (*area_items, *actor_items)
    entities = {item.id: item for item in all_entities}
    if len(entities) != len(all_entities):
        raise GameplayContractError("duplicate gameplay entity ID")
    relations: dict[str, Relation] = {}
    for actor_id, area_id in sorted(placements):
        _require_entity(entities, actor_id, "pmw_gameplay_actor")
        _require_entity(entities, area_id, "pmw_gameplay_area")
        relation = Relation(f"located:{actor_id}:{area_id}", "located_in", actor_id, area_id)
        relations[relation.id] = relation
    for left, right in sorted(adjacencies):
        _require_entity(entities, left, "pmw_gameplay_area")
        _require_entity(entities, right, "pmw_gameplay_area")
        if left == right:
            raise GameplayContractError("an Area cannot be adjacent to itself")
        a, b = sorted((left, right))
        relation = Relation(f"adjacent:{a}:{b}", "adjacent", a, b)
        relations[relation.id] = relation
    for relation_type, source, target in sorted(links):
        if not isinstance(relation_type, str) or not relation_type:
            raise GameplayContractError("linked relation type must be non-empty")
        _require_entity(entities, source)
        _require_entity(entities, target)
        relation = Relation(f"linked:{relation_type}:{source}:{target}", relation_type, source, target)
        relations[relation.id] = relation
    return WorldState(world_id, entities=entities, relations=relations)


def _require_entity(entities: dict[str, Entity], entity_id: str, component: str | None = None) -> None:
    entity = entities.get(entity_id)
    if entity is None or component is not None and component not in entity.components:
        raise GameplayContractError(f"invalid gameplay entity {entity_id!r}")
