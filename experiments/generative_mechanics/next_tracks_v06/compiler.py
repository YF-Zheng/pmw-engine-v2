"""Deterministic MechanismIR to PMW Law lowering for TODO1/v0.6."""

from __future__ import annotations

from typing import Any, Mapping

from pmw import parse_law

from .canonical import canonical_json
from .contracts import CompiledMechanism, MechanismIR, OperatorIR, SlotReservation, StateHandle
from .spec import (
    FieldObject, ObjectCatalog, ProcessObject, RelationObject, StockObject,
)
from .validator import validate_mechanism_batch


class MechanismCompileError(ValueError):
    pass


def compile_mechanisms(raw_documents, catalog: ObjectCatalog) -> tuple[CompiledMechanism, ...]:
    """Validate, jointly allocate, and compile a complete installation batch."""

    return tuple(compile_mechanism(ir, catalog) for ir in validate_mechanism_batch(raw_documents, catalog))


def compile_mechanism(ir: MechanismIR, catalog: ObjectCatalog) -> CompiledMechanism:
    """Lower validated immutable IR without executing any world effect."""

    objects = catalog.object_index
    slots = catalog.slot_index
    laws: list[dict[str, Any]] = []
    source_map: dict[str, str] = {}
    handle_templates: set[str] = set(ir.generated_handle_templates)
    event_types: set[str] = set(ir.generated_event_types)
    for operator in ir.operators:
        if operator.target_object_id not in objects:
            raise MechanismCompileError(f"unknown validated target {operator.target_object_id!r}")
        for instance_index in range(ir.max_instances):
            activation_id = _law_id(ir, operator, instance_index, "activate")
            expiry_type = _event_type(ir, operator, instance_index, "expire")
            event_types.update((f"gm.v06.mechanism.{ir.artifact_id}.activate", expiry_type))
            activation_effects = _activation_effects(ir, operator, instance_index, catalog)
            if operator.lifecycle.mode == "timed":
                template = _handle_template(ir, operator, instance_index)
                handle_templates.add(template)
                activation_effects.append({
                    "op": "schedule_event",
                    "event": {
                        "id": f"$event.payload.temporal_handles.{operator.operator_id}",
                        "type": expiry_type,
                        "time": {"add": ["$event.time", operator.lifecycle.steps]},
                        "source": "$event.source",
                        "target": "$event.target",
                        "payload": {
                            "artifact_id": ir.artifact_id,
                            "canonical_spec_hash": ir.canonical_spec_sha256,
                            "instance_index": instance_index,
                            "operator_id": operator.operator_id,
                            "temporal_handle": f"$event.payload.temporal_handles.{operator.operator_id}",
                        },
                    },
                })
            activation = {
                "id": activation_id,
                "mode": "event",
                "priority": 100,
                "bindings": _bindings_for(operator, catalog, activation=True, instance=instance_index),
                "when": {"all": _activation_conditions(ir, operator, instance_index, catalog)},
                "effects": activation_effects,
            }
            laws.append(activation)
            source_map[activation_id] = operator.source_pointer
            for persistent in _persistent_laws(ir, operator, instance_index, catalog):
                laws.append(persistent)
                source_map[persistent["id"]] = operator.source_pointer
            if operator.lifecycle.mode == "timed":
                expiry_id = _law_id(ir, operator, instance_index, "expire")
                expiry = {
                    "id": expiry_id,
                    "mode": "event",
                    "priority": 100,
                    "bindings": _bindings_for(operator, catalog, activation=False, instance=instance_index),
                    "when": {"all": [
                        {"event.type": {"eq": expiry_type}},
                        {"ref": "$event.payload.artifact_id", "eq": ir.artifact_id},
                        {"ref": "$event.payload.canonical_spec_hash", "eq": ir.canonical_spec_sha256},
                        {"ref": "$event.payload.instance_index", "eq": instance_index},
                        {"ref": "$event.payload.operator_id", "eq": operator.operator_id},
                        {"ref": "$event.id", "eq": "$event.payload.temporal_handle"},
                    ] + _expiry_target_conditions(ir, operator, instance_index, catalog)},
                    "effects": _expiry_effects(ir, operator, instance_index, catalog) + [
                        {"op": "cancel_scheduled", "value": "$event.payload.temporal_handle"},
                    ],
                }
                laws.append(expiry)
                source_map[expiry_id] = operator.source_pointer

    canonical_laws = tuple(sorted(laws, key=lambda row: row["id"]))
    try:
        for law in canonical_laws:
            parse_law(law)
    except Exception as exc:
        raise MechanismCompileError(f"PMW rejected compiled law bundle: {exc}") from exc
    # Force serialization now so unsupported values cannot escape compilation.
    canonical_json({"schema_version": "2.0", "laws": canonical_laws})
    return CompiledMechanism(
        protocol_version=ir.protocol,
        artifact_id=ir.artifact_id,
        canonical_spec_hash=ir.canonical_spec_sha256,
        max_instances=ir.max_instances,
        law_bundle=canonical_laws,
        required_world_objects=tuple(sorted(ir.required_objects)),
        required_capabilities=tuple(sorted(ir.required_capabilities)),
        generated_event_types=tuple(sorted(event_types)),
        generated_temporal_handles=tuple(sorted(handle_templates)),
        slot_allocations=tuple(sorted(
            ir.reservations,
            key=lambda item: (item.target_object_id, item.artifact_id, item.operator_id, item.instance_index, item.slot_id),
        )),
        source_map=dict(sorted(source_map.items())),
    )


def compiled_document(compiled: CompiledMechanism) -> dict[str, Any]:
    return {"schema_version": "2.0", "laws": [dict(item) for item in compiled.law_bundle]}


def _activation_conditions(ir: MechanismIR, operator: OperatorIR, instance: int, catalog: ObjectCatalog) -> list[dict[str, Any]]:
    conditions = [
        {"event.type": {"eq": f"gm.v06.mechanism.{ir.artifact_id}.activate"}},
        {"ref": "$event.payload.protocol", "eq": ir.protocol},
        {"ref": "$event.payload.artifact_id", "eq": ir.artifact_id},
        {"ref": "$event.payload.canonical_spec_hash", "eq": ir.canonical_spec_sha256},
        {"ref": "$event.payload.instance_index", "eq": instance},
    ]
    binding = _target_binding(operator)
    if _bindings_for(operator, catalog, activation=True, instance=instance):
        conditions.append({"ref": f"${binding}.id", "eq": _bound_runtime_id(ir, operator, catalog, instance)})
    reservation = next((item for item in operator.reservations if item.instance_index == instance), None)
    if reservation is not None:
        slot = catalog.slot_index[reservation.slot_id]
        conditions.append({"ref": "$target." + ".".join(slot.storage_ref.path) + ".active", "eq": False})
    target = catalog.object_index[operator.target_object_id]
    if operator.kind == "process_start" and isinstance(target, ProcessObject) and target.already_running == "reject":
        conditions.append({"ref": "$target." + ".".join(target.running_ref.path), "eq": target.stop_state})
    return conditions


def _bindings_for(operator: OperatorIR, catalog: ObjectCatalog, *, activation: bool, instance: int) -> dict[str, Any]:
    target = catalog.object_index[operator.target_object_id]
    reservations = [item for item in operator.reservations if item.instance_index == instance]
    handle = catalog.slot_index[reservations[0].slot_id].storage_ref if reservations else _primary_handle(target)
    if isinstance(target, RelationObject) and operator.kind == "relation_modifier":
        action = operator.parameters.get("action")
        if action == "create":
            return {"target": {"kind": "relation", "type": target.relation_type}} if not activation else {}
        if action == "delete":
            return {"target": {"kind": "relation", "type": target.relation_type}} if activation else {}
    if handle is None:
        if isinstance(target, RelationObject) and target.relation_id:
            return {"target": {"kind": "relation", "type": target.relation_type}}
        return {}
    return {_target_binding(operator): {"kind": handle.kind}}


def _activation_effects(ir: MechanismIR, operator: OperatorIR, instance: int, catalog: ObjectCatalog) -> list[dict[str, Any]]:
    target = catalog.object_index[operator.target_object_id]
    params = dict(operator.parameters)
    if operator.kind == "impulse":
        handle = _primary_handle(target)
        delta = _number(params, "delta", "amount", "value")
        if isinstance(target, FieldObject):
            value = {"clamp": [{"add": [_ref(handle), delta]}, target.minimum, target.maximum]}
        elif isinstance(target, StockObject):
            value = {"clamp": [{"add": [_ref(handle), delta]}, 0.0, target.capacity]}
        else:
            raise MechanismCompileError("impulse target must be field or stock")
        return [_write("set", handle, value)]
    if operator.kind in {"drive", "attractor_modifier", "dynamics_modifier", "process_modify"}:
        return _set_reserved_slots(operator, instance, catalog, active=True)
    if operator.kind == "process_start":
        if not isinstance(target, ProcessObject):
            raise MechanismCompileError("process_start target must be a process")
        return [_write("set", target.running_ref, target.start_state)]
    if operator.kind == "relation_modifier":
        if not isinstance(target, RelationObject):
            raise MechanismCompileError("relation_modifier target must be a relation")
        action = params.get("action")
        if action == "create":
            return [{"op": "create_relation", "value": _relation_value(target, catalog, _created_relation_id(ir, operator, instance))}]
        if action == "delete":
            return [{"op": "delete_relation", "target": "$target"}]
        if action in {"modify", "set_parameter"}:
            return _set_reserved_slots(operator, instance, catalog, active=True)
        raise MechanismCompileError(f"unsupported relation action {action!r}")
    raise MechanismCompileError(f"unsupported operator {operator.kind!r}")


def _expiry_effects(ir: MechanismIR, operator: OperatorIR, instance: int, catalog: ObjectCatalog) -> list[dict[str, Any]]:
    target = catalog.object_index[operator.target_object_id]
    if operator.kind in {"drive", "attractor_modifier", "dynamics_modifier", "process_modify"}:
        return _set_reserved_slots(operator, instance, catalog, active=False)
    if operator.kind == "process_start":
        assert isinstance(target, ProcessObject)
        return [_write("set", target.running_ref, target.stop_state)]
    if operator.kind == "relation_modifier":
        assert isinstance(target, RelationObject)
        action = operator.parameters.get("action")
        if action == "create":
            return [{"op": "delete_relation", "target": "$target"}]
        if action == "delete":
            return [{"op": "create_relation", "value": _relation_value(target, catalog)}]
        return _set_reserved_slots(operator, instance, catalog, active=False)
    return []


def _expiry_target_conditions(ir: MechanismIR, operator: OperatorIR, instance: int, catalog: ObjectCatalog) -> list[dict[str, Any]]:
    if "target" not in _bindings_for(operator, catalog, activation=False, instance=instance):
        return []
    return [{"ref": "$target.id", "eq": _bound_runtime_id(ir, operator, catalog, instance)}]


def _set_reserved_slots(operator: OperatorIR, instance: int, catalog: ObjectCatalog, *, active: bool) -> list[dict[str, Any]]:
    reservations = [item for item in operator.reservations if item.instance_index == instance]
    if not reservations:
        raise MechanismCompileError(f"{operator.kind} requires an allocated effect slot")
    effects = []
    for reservation in sorted(reservations, key=lambda item: item.slot_id):
        slot = catalog.slot_index[reservation.slot_id]
        value = _slot_value(reservation, operator.parameters) if active else _neutral_value(reservation.slot_kind)
        effects.append(_write("set", slot.storage_ref, value))
    return effects


def _persistent_laws(ir: MechanismIR, operator: OperatorIR, instance: int, catalog: ObjectCatalog) -> list[dict[str, Any]]:
    """Lower per-step stock source/sink/transfer semantics.

    Field drives are consumed by the normalized dynamics law bundle. Stock
    drives need an explicit world-step law so resource accounting remains in
    PMW and conserved transfers use one shared quantity expression.
    """

    target = catalog.object_index[operator.target_object_id]
    if operator.kind != "drive" or not isinstance(target, StockObject):
        return []
    reservation = next((item for item in operator.reservations if item.instance_index == instance), None)
    if reservation is None:
        raise MechanismCompileError("stock drive lacks its reserved contribution slot")
    slot = catalog.slot_index[reservation.slot_id]
    slot_ref = "$target." + ".".join(slot.storage_ref.path)
    amount = "$target." + ".".join(target.amount_ref.path)
    mode = operator.parameters["mode"]
    rate = f"{slot_ref}.drive"
    conditions: list[dict[str, Any]] = [
        {"event.type": {"eq": "gm.v06.world.step"}},
        {"ref": "$target.id", "eq": target.amount_ref.object_id},
        {"ref": f"{slot_ref}.active", "eq": True},
    ]
    bindings: dict[str, Any] = {"target": {"kind": "entity"}}
    if mode == "stock_source":
        quantity: Any = {"min": [rate, {"sub": [target.capacity, amount]}]}
        effects = [{"op": "delta", "target": amount, "value": quantity}]
    elif mode == "stock_sink":
        quantity = {"min": [rate, amount]}
        effects = [{"op": "delta", "target": amount, "value": {"sub": [0.0, quantity]}}]
    elif mode == "stock_transfer":
        destination = catalog.object_index[operator.parameters["destination"]]
        if not isinstance(destination, StockObject):
            raise MechanismCompileError("stock transfer destination is not a Stock")
        destination_amount = "$destination." + ".".join(destination.amount_ref.path)
        bindings["destination"] = {"kind": "entity"}
        conditions.append({"ref": "$destination.id", "eq": destination.amount_ref.object_id})
        quantity = {"min": [rate, amount, {"sub": [destination.capacity, destination_amount]}]}
        effects = [
            {"op": "delta", "target": amount, "value": {"sub": [0.0, quantity]}},
            {"op": "delta", "target": destination_amount, "value": quantity},
        ]
    else:
        return []
    return [{
        "id": _law_id(ir, operator, instance, "world_step"),
        "mode": "event",
        "priority": 100,
        "bindings": bindings,
        "when": {"all": conditions},
        "effects": effects,
    }]


def _slot_value(reservation: SlotReservation, params: Mapping[str, Any]) -> Any:
    kind = reservation.slot_kind
    owner = f"{reservation.artifact_id}:{reservation.operator_id}:{reservation.instance_index}"
    if kind == "attractor":
        return {"owner": owner, "active": True, "target": _number(params, "attractor"), "weight": _number(params, "weight")}
    if kind == "alpha":
        return {"owner": owner, "active": True, "delta": _number(params, "delta")}
    if kind == "drive":
        return {"owner": owner, "active": True, "drive": _number(params, "rate")}
    if kind in {"dynamics", "process_parameter", "relation_parameter"}:
        return {"owner": owner, "active": True, "delta": _number(params, "delta")}
    raise MechanismCompileError(f"unknown slot kind {kind!r}")


def _neutral_value(slot_kind: str) -> Any:
    if slot_kind == "attractor": return {"owner": None, "active": False, "target": 0.0, "weight": 0.0}
    if slot_kind == "drive": return {"owner": None, "active": False, "drive": 0.0}
    return {"owner": None, "active": False, "delta": 0.0}


def _write(op: str, handle: StateHandle | None, value: Any) -> dict[str, Any]:
    if handle is None:
        raise MechanismCompileError("operator target has no writable state handle")
    binding = "target"
    return {"op": op, "target": f"${binding}." + ".".join(handle.path), "value": value}


def _ref(handle: StateHandle | None) -> str:
    if handle is None: raise MechanismCompileError("missing state handle")
    return "$target." + ".".join(handle.path)


def _primary_handle(target: Any) -> StateHandle | None:
    if isinstance(target, FieldObject): return target.state_ref
    if isinstance(target, StockObject): return target.amount_ref
    if isinstance(target, ProcessObject): return target.running_ref
    if hasattr(target, "state_ref"): return target.state_ref
    return None


def _target_binding(operator: OperatorIR) -> str | None:
    return "target"


def _relation_value(target: RelationObject, catalog: ObjectCatalog, relation_id: str | None = None) -> dict[str, Any]:
    relation_id = relation_id or target.relation_id
    if not relation_id or len(target.source_objects) != 1 or len(target.target_objects) != 1:
        raise MechanismCompileError("relation lifecycle requires one id and one source/target")
    source = _runtime_object_id(catalog.object_index[target.source_objects[0]])
    destination = _runtime_object_id(catalog.object_index[target.target_objects[0]])
    return {"id": relation_id, "type": target.relation_type, "source": source, "target": destination}


def _runtime_object_id(target: Any) -> str:
    handle = _primary_handle(target)
    if handle is not None: return handle.object_id
    if isinstance(target, RelationObject) and target.relation_id: return target.relation_id
    if hasattr(target, "entity_id"): return target.entity_id
    raise MechanismCompileError("catalog object has no runtime object id")


def _number(params: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        value = params.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    raise MechanismCompileError(f"missing numeric parameter; expected one of {keys}")


def _law_id(ir: MechanismIR, operator: OperatorIR, instance: int, role: str) -> str:
    return f"gm.v06.law.{ir.canonical_spec_sha256[:12]}.{ir.artifact_id}.instance_{instance}.{operator.operator_id}.{role}"


def _event_type(ir: MechanismIR, operator: OperatorIR, instance: int, role: str) -> str:
    return f"{ir.event_namespace}.{operator.operator_id}.{role}"


def _handle_template(ir: MechanismIR, operator: OperatorIR, instance: int) -> str:
    expected = f"{ir.event_namespace}.instance.{instance}.{operator.operator_id}.expiry.{{activation_id}}"
    return expected


def _created_relation_id(ir: MechanismIR, operator: OperatorIR, instance: int) -> str:
    return f"gm:v06:relation:{ir.artifact_id}:{ir.canonical_spec_sha256[:12]}:{instance}:{operator.operator_id}"


def _bound_runtime_id(ir: MechanismIR, operator: OperatorIR, catalog: ObjectCatalog, instance: int) -> str:
    target = catalog.object_index[operator.target_object_id]
    if isinstance(target, RelationObject) and operator.parameters.get("action") == "create":
        return _created_relation_id(ir, operator, instance)
    return _runtime_object_id(target)
