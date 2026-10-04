import math
from typing import Any

from .errors import WorldValidationError


def validate_world(raw: Any, document: str) -> None:
    if not isinstance(raw, dict) or raw.get("schema_version") != "2.0":
        raise WorldValidationError(f"document={document} path=schema_version expected '2.0'")
    _finite_values(raw, document)
    if not isinstance(raw.get("world_id"), str) or not raw["world_id"]:
        raise WorldValidationError(f"document={document} path=world_id must be non-empty string")
    for name in ("entities", "relations", "scheduled_events"):
        if not isinstance(raw.get(name), list):
            raise WorldValidationError(f"document={document} path={name} must be list")
    time = raw.get("time", {})
    if not isinstance(time.get("tick", 0), int) or time.get("tick", 0) < 0:
        raise WorldValidationError(f"document={document} path=time.tick must be non-negative int")
    if not isinstance(time.get("sim_time", 0), (int, float)) or not math.isfinite(time.get("sim_time", 0)):
        raise WorldValidationError(f"document={document} path=time.sim_time must be finite number")
    ids: set[str] = set()
    entity_ids: set[str] = set()
    for index, item in enumerate(raw["entities"]):
        _object(item, f"entities[{index}]", document, ids, entity_ids, entity=True)
    for index, item in enumerate(raw["relations"]):
        _object(item, f"relations[{index}]", document, ids, entity_ids, entity=False)
    scheduled: set[str] = set()
    for index, item in enumerate(raw["scheduled_events"]):
        from .event import validate_event
        validate_event(item, f"document={document} scheduled_events[{index}]")
        if item.get("time", 0.0) < time.get("sim_time", 0.0):
            raise WorldValidationError(f"document={document} path=scheduled_events[{index}].time cannot be before sim_time")
        event_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(event_id, str) or not event_id:
            raise WorldValidationError(f"document={document} path=scheduled_events[{index}].id must be non-empty string")
        if event_id in scheduled:
            raise WorldValidationError(f"document={document} path=scheduled_events[{index}].id duplicate id '{event_id}'")
        scheduled.add(event_id)


def validate_runtime_world(world: Any) -> None:
    if not hasattr(world, "to_dict"):
        raise WorldValidationError("document=runtime path=world expected WorldState")
    validate_world(world.to_dict(), "runtime")


def validate_state_value(value: Any, path: str = "value") -> None:
    if value is None or isinstance(value, (bool, str, int)): return
    if isinstance(value, float):
        if math.isfinite(value): return
        raise WorldValidationError(f"path={path} invalid non-finite number")
    if isinstance(value, list):
        for index, item in enumerate(value): validate_state_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str): raise WorldValidationError(f"path={path} invalid non-string dict key")
            validate_state_value(item, f"{path}.{key}")
        return
    raise WorldValidationError(f"path={path} invalid non-JSON state value")


def validate_runtime_entity(entity: Any) -> None:
    _validate_runtime_object(entity, "entity")


def validate_runtime_relation(relation: Any) -> None:
    _validate_runtime_object(relation, "relation")
    if not all(isinstance(getattr(relation, field, None), str) and getattr(relation, field) for field in ("type", "source", "target")):
        raise WorldValidationError(f"invalid runtime relation={relation.id}")


def _validate_runtime_object(item: Any, kind: str) -> None:
    if not isinstance(getattr(item, "id", None), str) or not item.id or not isinstance(getattr(item, "tags", None), set) or any(not isinstance(tag, str) for tag in item.tags) or not isinstance(getattr(item, "components", None), dict):
        raise WorldValidationError(f"invalid runtime {kind}")
    validate_state_value(item.components, f"{kind}={item.id}.components")
    if kind == "entity" and (not isinstance(getattr(item, "archetype", None), str) or getattr(item, "name", None) is not None and not isinstance(getattr(item, "name"), str)):
        raise WorldValidationError(f"invalid runtime entity={item.id}")


def _finite_values(value: Any, document: str, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise WorldValidationError(f"document={document} path={path} must be finite number")
    if isinstance(value, dict):
        for key, item in value.items(): _finite_values(item, document, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value): _finite_values(item, document, f"{path}[{index}]")


def _object(item: Any, path: str, document: str, ids: set[str], entity_ids: set[str], entity: bool) -> None:
    if not isinstance(item, dict): raise WorldValidationError(f"document={document} path={path} must be object")
    object_id = item.get("id")
    if not isinstance(object_id, str) or not object_id: raise WorldValidationError(f"document={document} path={path}.id must be non-empty string")
    if object_id in ids: raise WorldValidationError(f"document={document} path={path}.id duplicate object id '{object_id}'")
    ids.add(object_id)
    if entity: entity_ids.add(object_id)
    if entity and (not isinstance(item.get("archetype", ""), str) or item.get("name") is not None and not isinstance(item.get("name"), str)):
        raise WorldValidationError(f"document={document} path={path}.archetype/name invalid")
    if not entity:
        for key in ("type", "source", "target"):
            if not isinstance(item.get(key), str) or not item[key]: raise WorldValidationError(f"document={document} path={path}.{key} must be non-empty string")
        for key in ("source", "target"):
            if item[key] not in entity_ids: raise WorldValidationError(f"document={document} path={path}.{key} dangling entity '{item[key]}'")
    tags = item.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags) or len(tags) != len(set(tags)):
        raise WorldValidationError(f"document={document} path={path}.tags must be unique strings")
    components = item.get("components", {})
    if not isinstance(components, dict): raise WorldValidationError(f"document={document} path={path}.components must be object")
    try:
        validate_state_value(components, f"{path}.components")
    except WorldValidationError as exc:
        raise WorldValidationError(f"document={document} {exc}") from exc
