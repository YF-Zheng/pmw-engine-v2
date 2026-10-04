"""Runtime-only state-law dependency metadata for incremental closure."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class StateReadDependency:
    binding: str
    kind: str
    path: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class StateDependencyPlan:
    law: object
    reads: tuple[StateReadDependency, ...]
    global_state_law: bool


class StateDependencyIndex:
    def __init__(self, plans):
        self.plans = tuple(plans)
        self.global_plans = tuple(plan for plan in self.plans if plan.global_state_law)

    def activations(self, deltas, world):
        """Return (law, seed-name, object) tuples; global laws have no seed."""
        activated = []
        for plan in self.global_plans:
            activated.append((plan.law, None, None))
        for delta in deltas:
            for plan in self.plans:
                if plan.global_state_law: continue
                for read in plan.reads:
                    if read.reason == "binding" and delta.address.path:
                        continue
                    if read.kind != delta.address.kind or not _overlaps(read.path, delta.address.path): continue
                    item = world.get_object(read.kind, delta.address.object_id)
                    if item is not None: activated.append((plan.law, read.binding, item))
        unique = {}
        for law, binding, item in activated:
            key = (law.law_id, () if binding is None else (binding, item.id))
            unique[key] = (law, binding, item)
        return [unique[key] for key in sorted(unique)]


def compile_state_dependency_plan(law):
    reads = set()
    for name, spec in law.bindings.items():
        kind = spec.get("kind", "entity")
        # Root lifecycle deltas can add/remove a candidate even when the binding is
        # used only structurally (for example, a relation join with no condition read).
        _add(reads, name, kind, (), "binding")
        for component in spec.get("requires", []): _add(reads, name, kind, (component,), "requires")
    _walk_condition(law.when, law.bindings, reads, "condition")
    for effect in law.effects: _walk_effect(effect, law.bindings, reads)
    ordered = tuple(sorted(reads, key=lambda item: (item.binding, item.path, item.reason)))
    return StateDependencyPlan(law, ordered, not any(item.reason != "binding" for item in ordered))


def _walk_condition(expression, bindings, reads, reason):
    if isinstance(expression, str):
        _reference(expression, bindings, reads, reason); return
    if isinstance(expression, list):
        for item in expression: _walk_condition(item, bindings, reads, reason)
        return
    if not isinstance(expression, dict): return
    if "has_tag" in expression:
        subject, tag = expression["has_tag"]
        name = _binding_name(subject, bindings)
        if name: _add(reads, name, bindings[name].get("kind", "entity"), ("tags", tag) if isinstance(tag, str) and not tag.startswith("$") else ("tags",), reason)
        _walk_value(tag, bindings, reads, reason)
    elif "has_component" in expression:
        subject, component = expression["has_component"]
        name = _binding_name(subject, bindings)
        if name: _add(reads, name, bindings[name].get("kind", "entity"), (component,) if isinstance(component, str) and not component.startswith("$") else (), reason)
        _walk_value(component, bindings, reads, reason)
    for key, value in expression.items():
        if key == "ref": _reference(value, bindings, reads, reason)
        elif key not in {"has_tag", "has_component"}:
            if isinstance(key, str) and "." in key and key.split(".")[0] in bindings: _reference(f"${key}", bindings, reads, reason)
            _walk_condition(value, bindings, reads, reason)


def _walk_effect(effect, bindings, reads):
    if not isinstance(effect, dict) or effect.get("op") == "emit_event": return
    target = effect.get("target")
    if not isinstance(target, str): return
    parts = target[1:].split(".") if target.startswith("$") else []
    if not parts or parts[0] not in bindings: return
    name, kind = parts[0], bindings[parts[0]].get("kind", "entity")
    if effect.get("op") in {"set", "delta", "delete_entity", "delete_relation"}:
        _add(reads, name, kind, tuple(parts[1:]), "effect_target")
    elif effect.get("op") in {"add_tag", "remove_tag"}:
        tag = effect.get("value")
        _add(reads, name, kind, ("tags", tag) if isinstance(tag, str) and not _is_reference(tag) else ("tags",), "effect_target")
    _walk_value(effect.get("value"), bindings, reads, "effect_value")


def _walk_value(expression, bindings, reads, reason="effect_value"):
    if isinstance(expression, str): _reference(expression, bindings, reads, reason)
    elif isinstance(expression, list):
        for item in expression: _walk_value(item, bindings, reads, reason)
    elif isinstance(expression, dict):
        for item in expression.values(): _walk_value(item, bindings, reads, reason)


def _reference(reference, bindings, reads, reason):
    if not _is_reference(reference): return
    parts = reference[1:].split(".")
    if parts[0] in bindings and len(parts) > 1:
        _add(reads, parts[0], bindings[parts[0]].get("kind", "entity"), tuple(parts[1:]), reason)


def _binding_name(reference, bindings):
    if _is_reference(reference):
        name = reference[1:].split(".")[0]
        return name if name in bindings else None
    return None


def _overlaps(left, right):
    return left[:len(right)] == right or right[:len(left)] == left


def _add(reads, binding, kind, path, reason):
    reads.add(StateReadDependency(binding, kind, tuple(path), reason))


def _is_reference(value):
    return isinstance(value, str) and re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", value) is not None
