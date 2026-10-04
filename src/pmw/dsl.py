from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any

from .types import Entity, Event, Relation, WorldState


class DSLResolutionError(RuntimeError):
    pass


class DSLConditionTypeError(RuntimeError):
    def __init__(self, operator, left, right):
        super().__init__(f"condition operator={operator} cannot compare left={left!r} ({type(left).__name__}) right={right!r} ({type(right).__name__})")


@dataclass(frozen=True, slots=True)
class Law:
    law_id: str
    mode: str
    priority: int
    bindings: dict[str, dict[str, Any]]
    when: dict[str, Any]
    effects: tuple[dict[str, Any], ...]


def parse_law(raw: dict[str, Any], *, validate: bool = True) -> Law:
    if validate:
        from .validation.law import validate_laws
        validate_laws({"schema_version": "2.0", "laws": [raw]}, "parse_law")
    mode = str(raw.get("mode", "event"))
    if mode not in {"event", "state"}:
        raise ValueError(f"Unsupported law mode: {mode}")
    return Law(
        law_id=str(raw["id"]),
        mode=mode,
        priority=int(raw.get("priority", 0)),
        bindings=dict(raw.get("bindings", {})),
        when=dict(raw.get("when") or {"all": []}),
        effects=tuple(raw.get("effects", [])),
    )


def _match_law_reference(law: Law, world: WorldState, event: Event) -> list[dict[str, Any]]:
    names = sorted(law.bindings)
    candidates = [_binding_candidates(law.bindings[name], world, event, {}) for name in names]
    matches: list[dict[str, Any]] = []
    for values in product(*candidates) if candidates else [()]:
        bindings = dict(zip(names, values))
        if _bindings_are_consistent(law.bindings, bindings, event) and evaluate(law.when, world, event, bindings):
            matches.append(bindings)
    return matches


def match_law(law: Law, world: WorldState, event: Event, *, stats: Any = None) -> list[dict[str, Any]]:
    from .matching.matcher import match_law as optimized
    return optimized(law, world, event, stats=stats)


def _binding_candidates(spec: dict[str, Any], world: WorldState, event: Event, _: dict[str, Any]) -> list[Any]:
    kind = spec.get("kind", "entity")
    if kind == "entity":
        return [entity for _, entity in sorted(world.entities.items()) if all(key in entity.components for key in spec.get("requires", []))]
    if kind == "relation":
        return [relation for _, relation in sorted(world.relations.items()) if not spec.get("type") or relation.type == spec["type"]]
    raise ValueError(f"Unsupported binding kind: {kind}")


def _bindings_are_consistent(specs: dict[str, dict[str, Any]], bindings: dict[str, Any], event: Event) -> bool:
    for name, spec in specs.items():
        value = bindings[name]
        if isinstance(value, Relation):
            for field in ("source", "target"):
                expected = spec.get(field)
                if expected and expected.startswith("$"):
                    bound = bindings.get(expected[1:])
                    if bound is None or getattr(value, field) != bound.id:
                        return False
    return True


def evaluate(expression: Any, world: WorldState, event: Event, bindings: dict[str, Any]) -> Any:
    if not isinstance(expression, dict):
        return _resolve(expression, world, event, bindings)
    if "all" in expression:
        return all(evaluate(item, world, event, bindings) for item in expression["all"])
    if "any" in expression:
        return any(evaluate(item, world, event, bindings) for item in expression["any"])
    if "not" in expression:
        return not evaluate(expression["not"], world, event, bindings)
    if "has_tag" in expression:
        subject, tag_expression = expression["has_tag"]
        tag = value(tag_expression, world, event, bindings)
        return isinstance(tag, str) and tag in _resolve(subject, world, event, bindings).tags
    if "has_component" in expression:
        subject, component_expression = expression["has_component"]
        component = value(component_expression, world, event, bindings)
        return isinstance(component, str) and component in _resolve(subject, world, event, bindings).components
    if "ref" in expression:
        left = _resolve(expression["ref"], world, event, bindings)
        for op in ("eq", "neq", "gt", "gte", "lt", "lte"):
            if op in expression:
                right = value(expression[op], world, event, bindings)
                if op in {"eq", "neq"}: return left == right if op == "eq" else left != right
                try:
                    return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}[op]
                except TypeError as exc:
                    raise DSLConditionTypeError(op, left, right) from exc
        return left
    if len(expression) == 1:
        ref, comparison = next(iter(expression.items()))
        if isinstance(comparison, dict):
            return evaluate({"ref": f"${ref}", **comparison}, world, event, bindings)
    raise ValueError(f"Unsupported expression: {expression}")


def value(expression: Any, world: WorldState, event: Event, bindings: dict[str, Any]) -> Any:
    if not isinstance(expression, dict):
        return _resolve(expression, world, event, bindings)
    for op in ("add", "sub", "mul", "div", "min", "max"):
        if op in expression:
            values = [value(item, world, event, bindings) for item in expression[op]]
            if op == "add": return sum(values)
            if op == "sub": return values[0] - values[1]
            if op == "mul": return values[0] * values[1]
            if op == "div": return values[0] / values[1]
            if op == "min": return min(values)
            return max(values)
    if "clamp" in expression:
        current, low, high = [value(item, world, event, bindings) for item in expression["clamp"]]
        return max(low, min(current, high))
    return {key: value(item, world, event, bindings) for key, item in expression.items()}


def _resolve(reference: Any, world: WorldState, event: Event, bindings: dict[str, Any]) -> Any:
    if not isinstance(reference, str) or not reference.startswith("$"):
        return reference
    parts = reference[1:].split(".")
    root = event if parts[0] == "event" else bindings[parts[0]]
    current: Any = root
    for part in parts[1:]:
        if isinstance(current, dict):
            if part not in current: raise DSLResolutionError(f"reference={reference} missing path segment={part}")
            current = current[part]
        elif isinstance(current, (Entity, Relation)) and part not in {"id", "tags", "components", "type", "source", "target"}:
            if part not in current.components: raise DSLResolutionError(f"reference={reference} missing component={part}")
            current = current.components[part]
        else:
            if not hasattr(current, part): raise DSLResolutionError(f"reference={reference} missing path segment={part}")
            current = getattr(current, part)
    return current
