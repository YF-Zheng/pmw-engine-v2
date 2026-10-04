from __future__ import annotations
from collections import defaultdict
from . import __name__ as _ignore
from ..types import WorldState


class WorldIndex:
    def __init__(self, world: WorldState) -> None:
        self.world = world; self.entity_by_id = world.entities; self.relation_by_id = world.relations
        self.entities_by_component = defaultdict(set)
        self.relations_by_type = defaultdict(set)
        self.relations_by_component = defaultdict(set)
        self.relations_by_key = defaultdict(set)
        self.relations_by_source = defaultdict(set); self.relations_by_target = defaultdict(set)
        for entity in world.entities.values():
            for component in entity.components: self.entities_by_component[component].add(entity.id)
        for relation in world.relations.values():
            self.relations_by_type[relation.type].add(relation.id)
            for component in relation.components: self.relations_by_component[component].add(relation.id)
            self.relations_by_source[relation.source].add(relation.id); self.relations_by_target[relation.target].add(relation.id)
            for key in ((relation.type, relation.source, relation.target), (relation.type, relation.source, None), (relation.type, None, relation.target), (None, relation.source, relation.target)):
                self.relations_by_key[key].add(relation.id)

    def entities(self, requires: tuple[str, ...], exact_id: str | None = None) -> list:
        if exact_id is not None: return [self.world.entities[exact_id]] if exact_id in self.world.entities and all(c in self.world.entities[exact_id].components for c in requires) else []
        if not requires: ids = set(self.world.entities)
        else:
            postings = sorted((self.entities_by_component[c] for c in requires), key=len)
            ids = set(postings[0])
            for posting in postings[1:]: ids &= posting
        return [self.world.entities[key] for key in sorted(ids)]

    def relations(self, spec: dict, bindings: dict, exact: dict | None = None) -> list:
        exact = exact or {}
        typ = exact.get("type", spec.get("type")); source = exact.get("source", _bound(spec.get("source"), bindings)); target = exact.get("target", _bound(spec.get("target"), bindings))
        candidates = self.relations_by_key.get((typ, source, target))
        if candidates is None:
            candidates = self.relations_by_key.get((typ, source, None)) if target is None else None
        if candidates is None:
            candidates = self.relations_by_key.get((typ, None, target)) if source is None else None
        if candidates is None and typ is None and source is not None and target is None: candidates=self.relations_by_source[source]
        if candidates is None and typ is None and target is not None and source is None: candidates=self.relations_by_target[target]
        if candidates is None: candidates = self.relations_by_type.get(typ, set()) if typ is not None else set(self.world.relations)
        required = tuple(spec.get("requires", []))
        if required:
            postings=sorted((self.relations_by_component[c] for c in required),key=len)
            candidates=set(candidates) & set(postings[0])
            for posting in postings[1:]: candidates &= posting
        return [self.world.relations[key] for key in sorted(candidates)]

    def estimate_entities(self, requires, exact_id=None):
        if exact_id is not None: return int(exact_id in self.world.entities)
        return len(self.world.entities) if not requires else min(len(self.entities_by_component[c]) for c in requires)
    def estimate_relations(self, spec, bindings, exact=None):
        exact=exact or {}; typ=exact.get("type",spec.get("type")); source=exact.get("source",_bound(spec.get("source"),bindings)); target=exact.get("target",_bound(spec.get("target"),bindings))
        if typ is not None and source is not None and target is not None: base=len(self.relations_by_key[(typ,source,target)])
        elif typ is not None and source is not None: base=len(self.relations_by_key[(typ,source,None)])
        elif typ is not None and target is not None: base=len(self.relations_by_key[(typ,None,target)])
        elif source is not None: base=len(self.relations_by_source[source])
        elif target is not None: base=len(self.relations_by_target[target])
        else: base=len(self.relations_by_type[typ]) if typ is not None else len(self.world.relations)
        required = spec.get("requires", [])
        return min([base, *(len(self.relations_by_component[c]) for c in required)])

    def add_entity(self, entity):
        for component in entity.components: self.entities_by_component[component].add(entity.id)

    def remove_entity(self, entity):
        for component in entity.components: self.entities_by_component[component].discard(entity.id)

    def add_relation(self, relation):
        self.relations_by_type[relation.type].add(relation.id)
        for component in relation.components: self.relations_by_component[component].add(relation.id)
        self.relations_by_source[relation.source].add(relation.id); self.relations_by_target[relation.target].add(relation.id)
        for key in ((relation.type, relation.source, relation.target), (relation.type, relation.source, None), (relation.type, None, relation.target), (None, relation.source, relation.target)):
            self.relations_by_key[key].add(relation.id)

    def remove_relation(self, relation):
        self.relations_by_type[relation.type].discard(relation.id)
        for component in relation.components: self.relations_by_component[component].discard(relation.id)
        self.relations_by_source[relation.source].discard(relation.id); self.relations_by_target[relation.target].discard(relation.id)
        for key in ((relation.type, relation.source, relation.target), (relation.type, relation.source, None), (relation.type, None, relation.target), (None, relation.source, relation.target)):
            self.relations_by_key[key].discard(relation.id)


def _bound(reference, bindings):
    return bindings[reference[1:]].id if isinstance(reference, str) and reference.startswith("$") and reference[1:] in bindings else None
