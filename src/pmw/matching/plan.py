from dataclasses import dataclass

@dataclass(frozen=True)
class BindingPlan:
    name: str
    spec: dict
    endpoint_dependencies: tuple[str, ...]

@dataclass(frozen=True)
class ConditionClause:
    expression: dict
    bindings: tuple[str, ...]
    event_only: bool


@dataclass(frozen=True)
class ExactConstraint:
    """A planner-only equality that can reduce a binding's candidate domain."""
    binding: str
    field: str
    rhs: object

@dataclass(frozen=True)
class MatchPlan:
    law: object
    binding_names: tuple[str, ...]
    bindings: tuple[BindingPlan, ...]
    clauses: tuple[ConditionClause, ...]
    exact_constraints: tuple[ExactConstraint, ...]

def compile_match_plan(law):
    names=tuple(sorted(law.bindings)); clauses=[]; exact_constraints=[]
    for item in law.when.get("all", []):
        deps, uses_event=expression_dependencies(item)
        clauses.append(ConditionClause(item,tuple(sorted(deps)),not deps and uses_event))
        constraint = _exact_constraint(item, law.bindings)
        if constraint is not None: exact_constraints.append(constraint)
    return MatchPlan(law,names,tuple(BindingPlan(n,law.bindings[n],tuple(x[1:] for x in (law.bindings[n].get("source"),law.bindings[n].get("target")) if x)) for n in names),tuple(clauses),tuple(exact_constraints))


def _exact_constraint(expression, bindings):
    if not isinstance(expression, dict): return None
    if "ref" in expression and set(expression) == {"ref", "eq"}:
        reference, rhs = expression["ref"], expression["eq"]
    elif len(expression) == 1:
        reference, comparison = next(iter(expression.items()))
        if not isinstance(comparison, dict) or set(comparison) != {"eq"}: return None
        reference, rhs = f"${reference}", comparison["eq"]
    else:
        return None
    if not isinstance(reference, str) or not reference.startswith("$") or not isinstance(rhs, str): return None
    parts = reference[1:].split(".")
    if len(parts) != 2 or parts[0] not in bindings: return None
    field = parts[1]
    kind = bindings[parts[0]].get("kind", "entity")
    if (kind == "entity" and field != "id") or (kind == "relation" and field not in {"id", "source", "target", "type"}): return None
    if rhs.startswith("$") and not rhs.startswith("$event."): return None
    return ExactConstraint(parts[0], field, rhs)

def expression_dependencies(expr):
    bindings=set(); event=False
    def walk(value):
        nonlocal event
        if isinstance(value,str) and value.startswith("$"):
            root=value[1:].split(".")[0]; event |= root == "event"; bindings.add(root) if root != "event" else None
        elif isinstance(value,list):
            for item in value: walk(item)
        elif isinstance(value,dict):
            for key,item in value.items():
                if key.startswith("event."): event=True
                elif "." in key and key.split(".")[0] not in {"ref"}: bindings.add(key.split(".")[0])
                walk(item)
    walk(expr); return bindings,event
