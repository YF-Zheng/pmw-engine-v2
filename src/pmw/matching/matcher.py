from __future__ import annotations
from dataclasses import dataclass
from itertools import product
import math
from ..dsl import Law, evaluate, value
from ..types import Event, Relation, WorldState
from .index import WorldIndex
from .plan import compile_match_plan

class MatchContext:
    def __init__(self, world, event, index_provider=None): self.world=world; self.event=event; self._index=None; self.index_builds=0; self._index_provider=index_provider
    @property
    def index(self):
        if self._index is None: self._index=self._index_provider() if self._index_provider else WorldIndex(self.world); self.index_builds+=1
        return self._index

@dataclass
class MatchStats:
    index_lookups: int = 0; candidate_rows_examined: int = 0; partial_bindings_created: int = 0; condition_evaluations: int = 0; complete_bindings: int = 0; matches_returned: int = 0; early_predicate_evaluations: int = 0; early_predicate_prunes: int = 0; index_builds: int = 0; exact_constraint_lookups: int = 0; exact_constraint_prunes: int = 0; constraint_pushdowns: int = 0

def match_law(law: Law, world: WorldState, event: Event, *, index: WorldIndex | None = None, stats: MatchStats | None = None, context=None, plan=None, seed_bindings=None) -> list[dict]:
    stats = stats or MatchStats()
    plan=plan or compile_match_plan(law)
    for clause in plan.clauses:
        if clause.event_only:
            stats.early_predicate_evaluations += 1
            if not evaluate(clause.expression, world, event, {}): stats.early_predicate_prunes += 1; return []
    if not law.bindings:
        stats.complete_bindings += 1; stats.final_condition_evaluations = getattr(stats, "final_condition_evaluations", 0) + 1
        return [{}] if evaluate(law.when, world, event, {}) else []
    exact = _resolve_exact_constraints(plan, world, event, stats)
    if exact is None: return []
    def get_index():
        nonlocal index
        if index is None:
            if context:
                before = context.index_builds; index = context.index; stats.index_builds += context.index_builds - before
            else:
                index = WorldIndex(world); stats.index_builds += 1
        return index
    out=[]
    def walk(bindings, checked=set()):
        newly = [clause for clause in plan.clauses if clause.bindings and set(clause.bindings) <= set(bindings) and id(clause) not in checked]
        for clause in newly:
            stats.early_predicate_evaluations += 1
            if not evaluate(clause.expression, world, event, bindings): stats.early_predicate_prunes += 1; return
        checked = checked | {id(clause) for clause in newly}
        if len(bindings) == len(law.bindings):
            stats.complete_bindings += 1; stats.condition_evaluations += 1
            if evaluate(law.when, world, event, bindings): out.append(dict(bindings))
            return
        choices=[]
        for name, spec in law.bindings.items():
            if name in bindings: continue
            constraints = exact.get(name, {})
            if "id" in constraints: estimate = int(_direct_object(world, spec, constraints["id"]) is not None)
            elif spec.get("kind", "entity") == "relation": estimate=get_index().estimate_relations(spec, bindings, constraints)
            else: estimate=get_index().estimate_entities(tuple(spec.get("requires", [])), _endpoint(name, law, bindings))
            choices.append((estimate, -sum(1 for key in ("source", "target") if spec.get(key)), name, spec))
        _, _, name, spec = min(choices, key=lambda row: (row[0], row[1], row[2]))
        constraints = exact.get(name, {})
        if "id" in constraints:
            candidate = _direct_object(world, spec, constraints["id"])
            candidates = [candidate] if candidate is not None else []
            stats.exact_constraint_lookups += 1
        elif spec.get("kind", "entity") == "relation":
            candidates = get_index().relations(spec, bindings, constraints); stats.index_lookups += 1
        else:
            candidates = get_index().entities(tuple(spec.get("requires", [])), _endpoint(name, law, bindings)); stats.index_lookups += 1
        for candidate in candidates:
            if not _candidate_satisfies_spec(candidate, spec, bindings) or not _matches_exact(candidate, constraints): continue
            if isinstance(candidate, Relation):
                for field in ("source", "target"):
                    ref=law.bindings[name].get(field)
                    if ref and ref[1:] in bindings and getattr(candidate, field) != bindings[ref[1:]].id: break
                else:
                    stats.candidate_rows_examined += 1; bindings[name]=candidate; stats.partial_bindings_created += 1; walk(bindings, checked); del bindings[name]
            else:
                if any(isinstance(bound, Relation) and spec.get(field) == f"${name}" and getattr(bound, field) != candidate.id for bound_name, bound in bindings.items() for spec in [law.bindings[bound_name]] for field in ("source", "target")):
                    continue
                stats.candidate_rows_examined += 1; bindings[name]=candidate; stats.partial_bindings_created += 1; walk(bindings, checked); del bindings[name]
    seeds = dict(seed_bindings or {})
    if any(name not in law.bindings or _kind_mismatch(item, law.bindings[name]) for name, item in seeds.items()): return []
    walk(seeds); out.sort(key=lambda row: tuple(row[name].id for name in sorted(law.bindings))); stats.matches_returned=len(out); return out


def _resolve_exact_constraints(plan, world, event, stats):
    resolved = {}
    for constraint in plan.exact_constraints:
        candidate = value(constraint.rhs, world, event, {})
        if not isinstance(candidate, str):
            stats.exact_constraint_prunes += 1
            return None
        fields = resolved.setdefault(constraint.binding, {})
        if constraint.field in fields and fields[constraint.field] != candidate:
            stats.exact_constraint_prunes += 1
            return None
        fields[constraint.field] = candidate; stats.constraint_pushdowns += 1
    return resolved


def _direct_object(world, spec, object_id):
    objects = world.relations if spec.get("kind", "entity") == "relation" else world.entities
    return objects.get(object_id)


def _matches_exact(candidate, constraints):
    return all(getattr(candidate, field, None) == expected for field, expected in constraints.items())


def _candidate_satisfies_spec(candidate, spec, bindings):
    if not all(component in candidate.components for component in spec.get("requires", [])): return False
    if not isinstance(candidate, Relation): return True
    if spec.get("type") and candidate.type != spec["type"]: return False
    for field in ("source", "target"):
        reference = spec.get(field)
        if reference and reference[1:] in bindings and getattr(candidate, field) != bindings[reference[1:]].id: return False
    return True


def _kind_mismatch(item, spec):
    return (spec.get("kind", "entity") == "relation") != isinstance(item, Relation)

def _endpoint(name, law, bindings):
    values=set()
    for bound_name, bound in bindings.items():
        if not isinstance(bound, Relation): continue
        spec=law.bindings[bound_name]
        for field in ("source", "target"):
            if spec.get(field) == f"${name}": values.add(getattr(bound, field))
    return values.pop() if len(values) == 1 else "__impossible__" if values else None

def match_law_reference(law, world, event, *, seed_bindings=None, stats=None, **_ignored):
    seeds = dict(seed_bindings or {})
    if any(name not in law.bindings or _kind_mismatch(item, law.bindings[name]) for name, item in seeds.items()): return []
    names=sorted(name for name in law.bindings if name not in seeds); domains=[]
    for name in names:
        spec=law.bindings[name]; domains.append(sorted(world.relations.values(), key=lambda x:x.id) if spec.get("kind")=="relation" else sorted(world.entities.values(), key=lambda x:x.id))
    out=[]
    for values in product(*domains) if domains else [()]:
        row={**seeds, **dict(zip(names, values))}; good=True
        for name, spec in law.bindings.items():
            obj=row[name]
            if spec.get("kind")=="relation":
                if spec.get("type") and obj.type != spec["type"]: good=False
                for f in ("source","target"):
                    if spec.get(f) and obj.__getattribute__(f) != row[spec[f][1:]].id: good=False
            if not all(c in obj.components for c in spec.get("requires", [])): good=False
        if good and evaluate(law.when, world,event,row): out.append(row)
    out.sort(key=lambda row: tuple(row[name].id for name in sorted(law.bindings)))
    if stats is not None:
        stats.complete_bindings += math.prod(len(domain) for domain in domains) if domains else 1
        stats.matches_returned = len(out)
    return out
