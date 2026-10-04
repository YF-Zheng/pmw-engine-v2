from typing import Any
import re

from .errors import LawValidationError, ReferenceValidationError
from .world import validate_state_value


OPS = {"set", "delta", "add_tag", "remove_tag", "emit_event", "schedule_event", "cancel_scheduled", "reschedule_scheduled", "create_entity", "delete_entity", "create_relation", "delete_relation"}


def validate_laws(raw: Any, document: str) -> None:
    if not isinstance(raw, dict) or raw.get("schema_version") != "2.0" or not isinstance(raw.get("laws"), list):
        raise LawValidationError(f"document={document} path=laws expected v2 law document")
    ids: set[str] = set()
    for index, law in enumerate(raw["laws"]):
        path = f"laws[{index}]"
        if not isinstance(law, dict) or not isinstance(law.get("id"), str) or not law["id"]: raise LawValidationError(f"document={document} path={path}.id must be non-empty string")
        if law["id"] in ids: raise LawValidationError(f"document={document} law={law['id']} path=id duplicate law id")
        ids.add(law["id"]); _law(law, document)


def _law(law: dict[str, Any], document: str) -> None:
    law_id = law["id"]; mode = law.get("mode", "event"); bindings = law.get("bindings", {})
    if mode not in {"event", "state"}: raise LawValidationError(f"document={document} law={law_id} path=mode invalid mode")
    if not isinstance(law.get("priority", 0), int): raise LawValidationError(f"document={document} law={law_id} path=priority must be int")
    if not isinstance(bindings, dict): raise LawValidationError(f"document={document} law={law_id} path=bindings must be object")
    for name, spec in bindings.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or name == "event" or not isinstance(spec, dict) or spec.get("kind", "entity") not in {"entity", "relation"}: raise LawValidationError(f"document={document} law={law_id} path=bindings.{name} invalid binding")
        allowed = {"kind", "requires"} if spec.get("kind", "entity") == "entity" else {"kind", "type", "source", "target", "requires"}
        if set(spec) - allowed or not isinstance(spec.get("requires", []), list) or any(not isinstance(x, str) for x in spec.get("requires", [])) or len(spec.get("requires", [])) != len(set(spec.get("requires", []))): raise LawValidationError(f"document={document} law={law_id} path=bindings.{name} invalid requires/field")
        if spec.get("kind", "entity") == "relation":
            for field in ("source", "target"):
                ref = spec.get(field)
                if ref:
                    root = _root(ref)
                    if root not in bindings or root == name or bindings[root].get("kind", "entity") != "entity": raise ReferenceValidationError(f"document={document} law={law_id} path=bindings.{name}.{field} invalid entity binding '{ref}'")
    _condition(law.get("when") or {"all": []}, bindings, mode, document, law_id, "when")
    effects = law.get("effects")
    if not isinstance(effects, list): raise LawValidationError(f"document={document} law={law_id} path=effects must be list")
    for i, effect in enumerate(effects): _effect(effect, bindings, mode, document, law_id, f"effects[{i}]")


def _effect(effect: Any, bindings: dict[str, Any], mode: str, document: str, law_id: str, path: str) -> None:
    if not isinstance(effect, dict) or effect.get("op") not in OPS: raise LawValidationError(f"document={document} law={law_id} path={path}.op invalid operation")
    op = effect["op"]
    if op == "emit_event":
        if mode != "event": raise LawValidationError(f"document={document} law={law_id} path={path} state law cannot emit_event")
        event = effect.get("event")
        if not isinstance(event, dict) or not isinstance(event.get("type"), str) or not event["type"] or "id" in event: raise LawValidationError(f"document={document} law={law_id} path={path}.event requires type and forbids id")
        if set(event) - {"type", "time", "source", "target", "payload"}: raise LawValidationError(f"document={document} law={law_id} path={path}.event unknown field")
        _value(event, bindings, mode, document, law_id, f"{path}.event"); return
    if op == "schedule_event":
        if mode != "event": raise LawValidationError(f"document={document} law={law_id} path={path} state law cannot schedule_event")
        if set(effect) != {"op", "event"}: raise LawValidationError(f"document={document} law={law_id} path={path} schedule_event requires event only")
        event = effect.get("event")
        if not isinstance(event, dict) or not {"id", "type", "time"} <= set(event): raise LawValidationError(f"document={document} law={law_id} path={path}.event requires id, type, and time")
        if set(event) - {"id", "type", "time", "source", "target", "payload"}: raise LawValidationError(f"document={document} law={law_id} path={path}.event unknown field or author provenance")
        if isinstance(event.get("id"), str) and not event["id"] or isinstance(event.get("type"), str) and not event["type"]: raise LawValidationError(f"document={document} law={law_id} path={path}.event id/type cannot be empty")
        for key in ("id", "type"):
            if not isinstance(event[key], (str, dict)): raise LawValidationError(f"document={document} law={law_id} path={path}.event.{key} invalid static value")
        static_time = event["time"]
        if isinstance(static_time, str) and not static_time.startswith("$") or static_time is None or isinstance(static_time, bool) or isinstance(static_time, (list, tuple, set, bytes)):
            raise LawValidationError(f"document={document} law={law_id} path={path}.event.time invalid static value")
        for key in ("source", "target"):
            if key in event and event[key] is not None and not isinstance(event[key], (str, dict)):
                raise LawValidationError(f"document={document} law={law_id} path={path}.event.{key} invalid static value")
        if "payload" in event and not isinstance(event["payload"], dict) and not (isinstance(event["payload"], str) and event["payload"].startswith("$")):
            raise LawValidationError(f"document={document} law={law_id} path={path}.event.payload invalid static value")
        _value(event, bindings, mode, document, law_id, f"{path}.event"); return
    if op in {"cancel_scheduled", "reschedule_scheduled"}:
        if mode != "event": raise LawValidationError(f"document={document} law={law_id} path={path} state law cannot {op}")
        if set(effect) != {"op", "value"}: raise LawValidationError(f"document={document} law={law_id} path={path} {op} requires value only")
        _value(effect["value"], bindings, mode, document, law_id, f"{path}.value"); return
    if op in {"create_entity", "create_relation"}:
        if mode != "event": raise LawValidationError(f"document={document} law={law_id} path={path} state law cannot {op}")
        if "target" in effect or "value" not in effect: raise LawValidationError(f"document={document} law={law_id} path={path} requires value only")
        _value(effect["value"], bindings, mode, document, law_id, f"{path}.value"); return
    if op in {"delete_entity", "delete_relation"}:
        if "target" not in effect or "value" in effect: raise LawValidationError(f"document={document} law={law_id} path={path} requires target only")
        root = _root(effect["target"])
        if root not in bindings or bindings[root].get("kind", "entity") != op.removeprefix("delete_"): raise ReferenceValidationError(f"document={document} law={law_id} path={path}.target invalid binding")
        if effect["target"] != f"${root}": raise LawValidationError(f"document={document} law={law_id} path={path}.target must be binding only")
        return
    if "target" not in effect or "value" not in effect: raise LawValidationError(f"document={document} law={law_id} path={path} requires target and value")
    target = effect["target"]; root = _root(target)
    if root not in bindings: raise ReferenceValidationError(f"document={document} law={law_id} path={path}.target unknown binding '{target}'")
    suffix = target[len(root)+2:]
    if op in {"set", "delta"} and not suffix: raise LawValidationError(f"document={document} law={law_id} path={path}.target requires component path")
    if op in {"add_tag", "remove_tag"} and suffix: raise LawValidationError(f"document={document} law={law_id} path={path}.target must be binding only")
    _value(effect.get("value"), bindings, mode, document, law_id, f"{path}.value")


def _condition(expr: Any, bindings: dict[str, Any], mode: str, document: str, law_id: str, path: str) -> None:
    if not isinstance(expr, dict) or len(expr) != 1 and "ref" not in expr: raise LawValidationError(f"document={document} law={law_id} path={path} invalid condition")
    if "ref" in expr:
        if set(expr) - {"ref", "eq", "neq", "gt", "gte", "lt", "lte"}: raise LawValidationError(f"document={document} law={law_id} path={path} unknown comparator")
        comparators = set(expr) & {"eq", "neq", "gt", "gte", "lt", "lte"}
        if len(comparators) != 1: raise LawValidationError(f"document={document} law={law_id} path={path} requires exactly one comparator")
        _references(expr["ref"], bindings, mode, document, law_id, path); _value(expr[next(iter(comparators))], bindings, mode, document, law_id, path); return
    op, operand = next(iter(expr.items()))
    if op in {"all", "any"}:
        if not isinstance(operand, list): raise LawValidationError(f"document={document} law={law_id} path={path}.{op} must be list")
        for i, item in enumerate(operand): _condition(item, bindings, mode, document, law_id, f"{path}.{op}[{i}]")
    elif op == "not": _condition(operand, bindings, mode, document, law_id, f"{path}.not")
    elif op in {"has_tag", "has_component"}:
        if not isinstance(operand, list) or len(operand) != 2 or _root(operand[0]) not in bindings: raise ReferenceValidationError(f"document={document} law={law_id} path={path}.{op} invalid binding operand")
        _value(operand[1], bindings, mode, document, law_id, path)
    elif isinstance(operand, dict):
        _condition({"ref": f"${op}", **operand}, bindings, mode, document, law_id, path)
    else: raise LawValidationError(f"document={document} law={law_id} path={path} unknown condition operator '{op}'")


def _value(value: Any, bindings: dict[str, Any], mode: str, document: str, law_id: str, path: str) -> None:
    if isinstance(value, str): _references(value, bindings, mode, document, law_id, path); return
    if value is None or isinstance(value, (bool, int, float)):
        _literal_state_value(value, document, law_id, path); return
    if isinstance(value, list):
        for i, item in enumerate(value): _value(item, bindings, mode, document, law_id, f"{path}[{i}]")
    elif isinstance(value, dict):
        reserved = {"add", "sub", "mul", "div", "min", "max", "clamp"}
        if set(value) & reserved:
            if len(value) != 1: raise LawValidationError(f"document={document} law={law_id} path={path} malformed value expression")
            op, args = next(iter(value.items()))
            if not isinstance(args, list) or (op in {"sub", "div"} and len(args) != 2) or (op == "clamp" and len(args) != 3) or (op in {"add", "mul", "min", "max"} and len(args) < 1): raise LawValidationError(f"document={document} law={law_id} path={path}.{op} invalid arity")
            for i, item in enumerate(args): _value(item, bindings, mode, document, law_id, f"{path}.{op}[{i}]")
        else:
            for key, item in value.items():
                if not isinstance(key, str): raise LawValidationError(f"document={document} law={law_id} path={path} object literal keys must be strings")
                if key in {"ref", "all", "any", "not", "eq", "neq", "gt", "gte", "lt", "lte"}: raise LawValidationError(f"document={document} law={law_id} path={path}.{key} condition operator not valid value expression")
                _value(item, bindings, mode, document, law_id, f"{path}.{key}")
    else:
        _literal_state_value(value, document, law_id, path)


def _literal_state_value(value: Any, document: str, law_id: str, path: str) -> None:
    try:
        validate_state_value(value, path)
    except Exception as exc:
        raise LawValidationError(f"document={document} law={law_id} path={path} invalid state literal: {exc}") from exc


def _references(value: Any, bindings: dict[str, Any], mode: str, document: str, law_id: str, path: str) -> None:
    if isinstance(value, str) and value.startswith("$"):
        root = _root(value)
        if root == "event" and mode == "state": raise ReferenceValidationError(f"document={document} law={law_id} path={path} state law cannot reference $event")
        if root != "event" and root not in bindings: raise ReferenceValidationError(f"document={document} law={law_id} path={path} unknown binding '{value}'")
    elif isinstance(value, dict):
        for key, item in value.items():
            if key.startswith("event.") and mode == "state": raise ReferenceValidationError(f"document={document} law={law_id} path={path} state law cannot reference $event")
            _references(item, bindings, mode, document, law_id, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value): _references(item, bindings, mode, document, law_id, f"{path}[{i}]")


def _root(reference: str) -> str:
    return reference[1:].split(".")[0] if isinstance(reference, str) and reference.startswith("$") else ""
