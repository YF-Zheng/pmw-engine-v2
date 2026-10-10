"""Strict catalog and MechanismSpec validation for v0.6.

No function in this module repairs untrusted input.  Successful mechanism
validation returns the immutable, fully resolved compiler-facing IR.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .canonical import canonical_sha256
from .contracts import (
    CATALOG_PROTOCOL_ID,
    LIFECYCLE_MODES,
    OBJECT_KINDS,
    OPERATOR_KINDS,
    PROTOCOL_ID,
    LifecycleIR,
    MechanismIR,
    OperatorIR,
    SlotReservation,
    StateHandle,
)
from .spec import (
    CapabilitySpec,
    CatalogLimits,
    DerivedObject,
    DiscreteObject,
    EffectSlotSpec,
    FieldObject,
    MechanismSpec,
    ObjectCatalog,
    OperatorSpec,
    ParameterSpec,
    ProcessObject,
    RelationObject,
    StockObject,
)


ID_RE = re.compile(r"[a-z][a-z0-9_]{1,47}\Z")
RESERVED_PREFIXES = ("gm_", "pmw_", "lab_")
OWNERSHIPS = frozenset({"world", "artifact"})
SCOPES = frozenset({"local", "linked"})
PRIVILEGES = frozenset({
    "nonconserved_source", "nonconserved_sink", "permanent_modifier",
    "delete_world_relation", "modify_world_owned_process",
})
SLOT_KINDS = frozenset({
    "attractor", "alpha", "drive", "dynamics",
    "process_parameter", "relation_parameter",
})


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    path: str
    message: str


class MechanismValidationError(ValueError):
    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues = tuple(sorted(issues, key=lambda item: (item.path, item.code)))
        if not self.issues:
            raise ValueError("MechanismValidationError requires at least one issue")
        super().__init__("; ".join(
            f"{item.code} at {item.path}: {item.message}" for item in self.issues
        ))


def _fail(code: str, path: str, message: str) -> None:
    raise MechanismValidationError((ValidationIssue(code, path, message),))


def _strict(raw: Any, required: set[str], optional: set[str], path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        _fail("SCHEMA_TYPE", path, "must be an object")
    unknown = set(raw) - required - optional
    missing = required - set(raw)
    if unknown:
        _fail("UNKNOWN_FIELD", path, f"unknown fields: {sorted(unknown)}")
    if missing:
        _fail("MISSING_FIELD", path, f"missing fields: {sorted(missing)}")
    return raw


def _identifier(value: Any, path: str, *, allow_reserved: bool = False) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        _fail("INVALID_ID", path, "must match [a-z][a-z0-9_]{1,47}")
    if not allow_reserved and value.startswith(RESERVED_PREFIXES):
        _fail("RESERVED_NAMESPACE", path, "uses a reserved namespace")
    return value


def _string(value: Any, path: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or nonempty and not value.strip():
        _fail("SCHEMA_TYPE", path, "must be a non-empty string")
    return value


def _number(value: Any, path: str, *, low: float | None = None, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail("NON_FINITE" if isinstance(value, float) else "SCHEMA_TYPE", path, "must be a finite number")
    result = float(value)
    if low is not None and result < low or high is not None and result > high:
        _fail("OUT_OF_RANGE", path, f"must be in [{low}, {high}]")
    return result


def _integer(value: Any, path: str, *, low: int = 0, high: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("SCHEMA_TYPE", path, "must be an integer")
    if value < low or high is not None and value > high:
        _fail("OUT_OF_RANGE", path, f"must be in [{low}, {high}]")
    return value


def _string_list(value: Any, path: str, *, identifiers: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        _fail("SCHEMA_TYPE", path, "must be a list")
    result = tuple(
        _identifier(item, f"{path}[{index}]", allow_reserved=True)
        if identifiers else _string(item, f"{path}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        _fail("DUPLICATE_ID", path, "must not contain duplicates")
    return result


def _state_ref(raw: Any, path: str, *, default_type: str = "number") -> StateHandle:
    data = _strict(raw, {"kind", "object_id", "path"}, {"value_type"}, path)
    if data["kind"] not in {"entity", "relation"}:
        _fail("SCHEMA_TYPE", f"{path}.kind", "must be entity or relation")
    object_id = _string(data["object_id"], f"{path}.object_id")
    parts = _string_list(data["path"], f"{path}.path")
    if not parts:
        _fail("SCHEMA_TYPE", f"{path}.path", "must not be empty")
    value_type = data.get("value_type", default_type)
    if value_type not in {"number", "boolean", "string", "object"}:
        _fail("SCHEMA_TYPE", f"{path}.value_type", "unsupported state value type")
    return StateHandle(data["kind"], object_id, parts, value_type)


def _operator_names(value: Any, path: str, kind: str) -> tuple[str, ...]:
    result = _string_list(value, path)
    legal = {
        "field": {"impulse", "drive", "attractor_modifier", "dynamics_modifier"},
        "stock": {"impulse", "drive"},
        "process": {"process_start", "process_modify"},
        "relation": {"relation_modifier", "dynamics_modifier"},
        "discrete": set(),
        "derived": set(),
    }[kind]
    bad = set(result) - legal
    if bad:
        _fail("OPERATOR_NOT_ALLOWED", path, f"not legal for {kind}: {sorted(bad)}")
    return tuple(sorted(result))


def _parameter(raw: Any, path: str) -> ParameterSpec:
    data = _strict(
        raw, {"id", "state_ref", "domain", "combination", "modifier_slots"},
        {"dynamics_parameter"}, path,
    )
    domain = _strict(data["domain"], {"min", "max"}, set(), f"{path}.domain")
    low = _number(domain["min"], f"{path}.domain.min")
    high = _number(domain["max"], f"{path}.domain.max")
    if low >= high:
        _fail("OUT_OF_RANGE", f"{path}.domain", "min must be less than max")
    if data["combination"] != "base_plus_additive_slots":
        _fail("SCHEMA_TYPE", f"{path}.combination", "unsupported combination")
    dynamic = data.get("dynamics_parameter", False)
    if not isinstance(dynamic, bool):
        _fail("SCHEMA_TYPE", f"{path}.dynamics_parameter", "must be boolean")
    return ParameterSpec(
        _identifier(data["id"], f"{path}.id", allow_reserved=True),
        _state_ref(data["state_ref"], f"{path}.state_ref"), low, high,
        data["combination"], _string_list(data["modifier_slots"], f"{path}.modifier_slots", identifiers=True),
        dynamic,
    )


def _parameters(value: Any, path: str) -> tuple[ParameterSpec, ...]:
    if not isinstance(value, list):
        _fail("SCHEMA_TYPE", path, "must be a list")
    result = tuple(_parameter(item, f"{path}[{index}]") for index, item in enumerate(value))
    _unique((item.id for item in result), path)
    return result


def _unique(values: Iterable[str], path: str) -> None:
    items = tuple(values)
    if len(items) != len(set(items)):
        _fail("DUPLICATE_ID", path, "contains duplicate ids")


def _parse_object(raw: Any, path: str):
    if not isinstance(raw, dict) or raw.get("kind") not in OBJECT_KINDS:
        _fail("SCHEMA_TYPE", f"{path}.kind", "unknown object kind")
    kind = raw["kind"]
    common = {"id", "kind", "ownership", "allowed_operators"}
    required = {
        "field": {"state_ref", "domain", "initial", "normalization", "writable", "dynamics"},
        "stock": {"amount_ref", "capacity", "initial", "boundary_policy", "transfer_unit", "source_policy", "sink_policy"},
        "process": {"entity_id", "running_ref", "lifecycle", "source_objects", "target_objects", "parameters"},
        "relation": {"relation_type", "lifecycle", "source_objects", "target_objects", "parameters"},
        "discrete": {"state_ref", "initial", "values", "transitions"},
        "derived": {"state_ref", "value_type", "source_objects", "derivation_law_ids", "writable"},
    }[kind]
    optional = {"relation_id"} if kind == "relation" else set()
    data = _strict(raw, common | required, optional, path)
    item_id = _identifier(data["id"], f"{path}.id", allow_reserved=True)
    if data["ownership"] not in OWNERSHIPS:
        _fail("SCHEMA_TYPE", f"{path}.ownership", "must be world or artifact")
    allowed = _operator_names(data["allowed_operators"], f"{path}.allowed_operators", kind)
    if kind == "field":
        domain = _strict(data["domain"], {"min", "max"}, set(), f"{path}.domain")
        low = _number(domain["min"], f"{path}.domain.min")
        high = _number(domain["max"], f"{path}.domain.max")
        initial = _number(data["initial"], f"{path}.initial", low=low, high=high)
        if low >= high:
            _fail("OUT_OF_RANGE", f"{path}.domain", "min must be less than max")
        if data["normalization"] != "clamp" or not isinstance(data["writable"], bool):
            _fail("SCHEMA_TYPE", path, "invalid normalization or writable flag")
        dynamics = None
        if data["dynamics"] is not None:
            dyn = _strict(data["dynamics"], {"base_attractor_ref", "base_alpha_ref", "base_weight", "attractor_slots", "alpha_slots", "drive_slots"}, set(), f"{path}.dynamics")
            weight = _number(dyn["base_weight"], f"{path}.dynamics.base_weight", low=0.0)
            if weight <= 0:
                _fail("OUT_OF_RANGE", f"{path}.dynamics.base_weight", "must be positive")
            dynamics = MappingProxyType({
                "base_attractor_ref": _state_ref(dyn["base_attractor_ref"], f"{path}.dynamics.base_attractor_ref"),
                "base_alpha_ref": _state_ref(dyn["base_alpha_ref"], f"{path}.dynamics.base_alpha_ref"),
                "base_weight": weight,
                "attractor_slots": _string_list(dyn["attractor_slots"], f"{path}.dynamics.attractor_slots", identifiers=True),
                "alpha_slots": _string_list(dyn["alpha_slots"], f"{path}.dynamics.alpha_slots", identifiers=True),
                "drive_slots": _string_list(dyn["drive_slots"], f"{path}.dynamics.drive_slots", identifiers=True),
            })
        return FieldObject(item_id, data["ownership"], _state_ref(data["state_ref"], f"{path}.state_ref"), low, high, initial, data["normalization"], data["writable"], allowed, dynamics)
    if kind == "stock":
        capacity = _number(data["capacity"], f"{path}.capacity", low=0.0)
        if capacity <= 0:
            _fail("OUT_OF_RANGE", f"{path}.capacity", "must be positive")
        initial = _number(data["initial"], f"{path}.initial", low=0.0, high=capacity)
        if data["boundary_policy"] != "bounded_flow" or data["source_policy"] != "capability_required" or data["sink_policy"] != "capability_required":
            _fail("CONSERVATION_REQUIRED", path, "stock must use bounded flow and explicit source/sink capabilities")
        return StockObject(item_id, data["ownership"], _state_ref(data["amount_ref"], f"{path}.amount_ref"), capacity, initial, data["boundary_policy"], _string(data["transfer_unit"], f"{path}.transfer_unit"), allowed, data["source_policy"], data["sink_policy"])
    if kind == "process":
        lifecycle = _strict(data["lifecycle"], {"start_state", "stop_state", "already_running"}, set(), f"{path}.lifecycle")
        if lifecycle["already_running"] not in {"reject", "idempotent"}:
            _fail("SCHEMA_TYPE", f"{path}.lifecycle.already_running", "must be reject or idempotent")
        return ProcessObject(item_id, data["ownership"], _string(data["entity_id"], f"{path}.entity_id"), _state_ref(data["running_ref"], f"{path}.running_ref", default_type="string"), _string(lifecycle["start_state"], f"{path}.lifecycle.start_state"), _string(lifecycle["stop_state"], f"{path}.lifecycle.stop_state"), lifecycle["already_running"], _string_list(data["source_objects"], f"{path}.source_objects", identifiers=True), _string_list(data["target_objects"], f"{path}.target_objects", identifiers=True), _parameters(data["parameters"], f"{path}.parameters"), allowed)
    if kind == "relation":
        if data["lifecycle"] not in {"existing", "template"}:
            _fail("SCHEMA_TYPE", f"{path}.lifecycle", "must be existing or template")
        relation_id = data.get("relation_id")
        if data["lifecycle"] == "existing" and not isinstance(relation_id, str):
            _fail("MISSING_FIELD", f"{path}.relation_id", "existing relation requires relation_id")
        if data["lifecycle"] == "template" and relation_id is not None:
            _fail("UNKNOWN_FIELD", f"{path}.relation_id", "template must not fix a relation id")
        return RelationObject(item_id, data["ownership"], _string(data["relation_type"], f"{path}.relation_type"), data["lifecycle"], relation_id, _string_list(data["source_objects"], f"{path}.source_objects", identifiers=True), _string_list(data["target_objects"], f"{path}.target_objects", identifiers=True), _parameters(data["parameters"], f"{path}.parameters"), allowed)
    if kind == "discrete":
        values = _string_list(data["values"], f"{path}.values")
        if not values or data["initial"] not in values:
            _fail("ILLEGAL_TRANSITION", f"{path}.initial", "must be a declared value")
        if not isinstance(data["transitions"], list):
            _fail("SCHEMA_TYPE", f"{path}.transitions", "must be a list")
        transitions = []
        for index, raw_transition in enumerate(data["transitions"]):
            trans = _strict(raw_transition, {"from", "to"}, set(), f"{path}.transitions[{index}]")
            if trans["from"] not in values or trans["to"] not in values:
                _fail("ILLEGAL_TRANSITION", f"{path}.transitions[{index}]", "uses undeclared state")
            transitions.append((trans["from"], trans["to"]))
        return DiscreteObject(item_id, data["ownership"], _state_ref(data["state_ref"], f"{path}.state_ref", default_type="string"), data["initial"], values, tuple(transitions), allowed)
    if data["value_type"] not in {"number", "boolean", "string"} or data["writable"] is not False or allowed:
        _fail("DERIVED_READ_ONLY", path, "derived objects must be read-only and expose no operators")
    return DerivedObject(item_id, data["ownership"], _state_ref(data["state_ref"], f"{path}.state_ref", default_type=data["value_type"]), data["value_type"], _string_list(data["source_objects"], f"{path}.source_objects", identifiers=True), _string_list(data["derivation_law_ids"], f"{path}.derivation_law_ids"), False, allowed)


def _capability(raw: Any, path: str) -> CapabilitySpec:
    data = _strict(raw, {"id", "operator_kind", "targets", "scopes", "actions", "lifecycles", "numeric_limits", "privileges"}, set(), path)
    if data["operator_kind"] not in OPERATOR_KINDS:
        _fail("UNKNOWN_OPERATOR", f"{path}.operator_kind", "unknown operator")
    scopes = _string_list(data["scopes"], f"{path}.scopes")
    if not scopes or set(scopes) - SCOPES:
        _fail("SCHEMA_TYPE", f"{path}.scopes", "contains unsupported scope")
    lifecycles = _string_list(data["lifecycles"], f"{path}.lifecycles")
    if not lifecycles or set(lifecycles) - set(LIFECYCLE_MODES):
        _fail("INVALID_LIFECYCLE", f"{path}.lifecycles", "contains unsupported lifecycle")
    if not isinstance(data["numeric_limits"], dict):
        _fail("SCHEMA_TYPE", f"{path}.numeric_limits", "must be an object")
    if set(data["numeric_limits"]) - {"max_abs_value", "max_weight"}:
        _fail("UNKNOWN_FIELD", f"{path}.numeric_limits", "contains unsupported numeric limit")
    limits = {key: _number(value, f"{path}.numeric_limits.{key}", low=0.0) for key, value in data["numeric_limits"].items() if isinstance(key, str)}
    if len(limits) != len(data["numeric_limits"]):
        _fail("SCHEMA_TYPE", f"{path}.numeric_limits", "keys must be strings")
    privileges = _string_list(data["privileges"], f"{path}.privileges")
    if set(privileges) - PRIVILEGES:
        _fail("SCHEMA_TYPE", f"{path}.privileges", "contains unknown privilege")
    actions = _string_list(data["actions"], f"{path}.actions")
    allowed_actions = {"create", "delete", "modify"} if data["operator_kind"] == "relation_modifier" else {"start"} if data["operator_kind"] == "process_start" else {"modify"}
    if not actions or set(actions) - allowed_actions:
        _fail("SCHEMA_TYPE", f"{path}.actions", "contains unsupported action")
    return CapabilitySpec(_identifier(data["id"], f"{path}.id", allow_reserved=True), data["operator_kind"], _string_list(data["targets"], f"{path}.targets", identifiers=True), tuple(sorted(scopes)), tuple(sorted(actions)), tuple(sorted(lifecycles)), MappingProxyType(dict(sorted(limits.items()))), tuple(sorted(privileges)))


def _slot(raw: Any, path: str) -> EffectSlotSpec:
    data = _strict(raw, {"id", "slot_kind", "target", "storage_ref"}, set(), path)
    if data["slot_kind"] not in SLOT_KINDS:
        _fail("SCHEMA_TYPE", f"{path}.slot_kind", "unknown slot kind")
    return EffectSlotSpec(_identifier(data["id"], f"{path}.id", allow_reserved=True), data["slot_kind"], _identifier(data["target"], f"{path}.target", allow_reserved=True), _state_ref(data["storage_ref"], f"{path}.storage_ref", default_type="object"))


def validate_catalog(raw: Any) -> ObjectCatalog:
    data = _strict(raw, {"protocol", "catalog_id", "limits", "objects", "capabilities", "effect_slots"}, set(), "$")
    if data["protocol"] != CATALOG_PROTOCOL_ID:
        _fail("SCHEMA_TYPE", "$.protocol", f"must be {CATALOG_PROTOCOL_ID}")
    limits_raw = _strict(data["limits"], {"max_operators", "max_instances", "max_targets", "max_duration_steps", "max_total_effect_slots", "max_scheduled_handles"}, set(), "$.limits")
    limits = CatalogLimits(*(_integer(limits_raw[name], f"$.limits.{name}", low=1) for name in ("max_operators", "max_instances", "max_targets", "max_duration_steps", "max_total_effect_slots", "max_scheduled_handles")))
    for key in ("objects", "capabilities", "effect_slots"):
        if not isinstance(data[key], list):
            _fail("SCHEMA_TYPE", f"$.{key}", "must be a list")
    objects = tuple(_parse_object(item, f"$.objects[{index}]") for index, item in enumerate(data["objects"]))
    capabilities = tuple(_capability(item, f"$.capabilities[{index}]") for index, item in enumerate(data["capabilities"]))
    slots = tuple(_slot(item, f"$.effect_slots[{index}]") for index, item in enumerate(data["effect_slots"]))
    _unique((item.id for item in objects), "$.objects")
    _unique((item.id for item in capabilities), "$.capabilities")
    _unique((item.id for item in slots), "$.effect_slots")
    object_ids = {item.id for item in objects}
    slot_ids = {item.id for item in slots}
    slot_index = {item.id: item for item in slots}
    for slot in slots:
        if slot.target_object_id not in object_ids:
            _fail("UNKNOWN_OBJECT", f"$.effect_slots.{slot.id}.target", "references unknown object")
    storage_addresses = [(item.storage_ref.kind, item.storage_ref.object_id, item.storage_ref.path) for item in slots]
    if len(storage_addresses) != len(set(storage_addresses)):
        _fail("SLOT_OWNER_CONFLICT", "$.effect_slots", "multiple slot IDs alias one storage address")
    for item in objects:
        refs: tuple[str, ...] = ()
        if isinstance(item, (ProcessObject, RelationObject)):
            refs = item.source_objects + item.target_objects
            for parameter in item.parameters:
                if set(parameter.modifier_slots) - slot_ids:
                    _fail("UNKNOWN_OBJECT", f"$.objects.{item.id}.parameters.{parameter.id}.modifier_slots", "references unknown slot")
                allowed_slot_kinds = {"process_parameter"} if isinstance(item, ProcessObject) else {"dynamics", "relation_parameter"}
                for slot_id in parameter.modifier_slots:
                    slot = slot_index[slot_id]
                    if slot.target_object_id != item.id or slot.slot_kind not in allowed_slot_kinds:
                        _fail("SLOT_OWNER_CONFLICT", f"$.objects.{item.id}.parameters.{parameter.id}.modifier_slots", "slot kind/target mismatch")
        elif isinstance(item, DerivedObject):
            refs = item.source_objects
        if set(refs) - object_ids:
            _fail("UNKNOWN_OBJECT", f"$.objects.{item.id}", f"unknown object refs: {sorted(set(refs)-object_ids)}")
        if isinstance(item, FieldObject) and item.dynamics:
            declared = set(item.dynamics["attractor_slots"] + item.dynamics["alpha_slots"] + item.dynamics["drive_slots"])
            if declared - slot_ids:
                _fail("UNKNOWN_OBJECT", f"$.objects.{item.id}.dynamics", f"unknown slots: {sorted(declared-slot_ids)}")
            for slot_id in item.dynamics["attractor_slots"]:
                if slot_index[slot_id].slot_kind != "attractor" or slot_index[slot_id].target_object_id != item.id:
                    _fail("SLOT_OWNER_CONFLICT", f"$.objects.{item.id}.dynamics.attractor_slots", "slot kind/target mismatch")
            for slot_id in item.dynamics["alpha_slots"]:
                if slot_index[slot_id].slot_kind != "alpha" or slot_index[slot_id].target_object_id != item.id:
                    _fail("SLOT_OWNER_CONFLICT", f"$.objects.{item.id}.dynamics.alpha_slots", "slot kind/target mismatch")
            for slot_id in item.dynamics["drive_slots"]:
                if slot_index[slot_id].slot_kind != "drive" or slot_index[slot_id].target_object_id != item.id:
                    _fail("SLOT_OWNER_CONFLICT", f"$.objects.{item.id}.dynamics.drive_slots", "slot kind/target mismatch")
    for cap in capabilities:
        if set(cap.targets) - object_ids:
            _fail("UNKNOWN_OBJECT", f"$.capabilities.{cap.id}.targets", "references unknown object")
    process_stock_objects = {
        object_id
        for item in objects if isinstance(item, ProcessObject)
        for object_id in item.source_objects + item.target_objects
        if isinstance(next(candidate for candidate in objects if candidate.id == object_id), StockObject)
    }
    for cap in capabilities:
        if cap.operator_kind == "drive" and set(cap.targets) & process_stock_objects:
            _fail("CONSERVATION_REQUIRED", f"$.capabilities.{cap.id}.targets", "generated Stock flow cannot share a Stock with a world Process writer")
    for slot in slots:
        if slot.target_object_id not in object_ids:
            _fail("UNKNOWN_OBJECT", f"$.effect_slots.{slot.id}.target", "references unknown object")
        target = next(item for item in objects if item.id == slot.target_object_id)
        runtime_id = (
            target.state_ref.object_id if isinstance(target, (FieldObject, DiscreteObject, DerivedObject))
            else target.amount_ref.object_id if isinstance(target, StockObject)
            else target.entity_id if isinstance(target, ProcessObject)
            else target.relation_id if isinstance(target, RelationObject) else None
        )
        if runtime_id is None or slot.storage_ref.object_id != runtime_id:
            _fail("SLOT_OWNER_CONFLICT", f"$.effect_slots.{slot.id}.storage_ref", "storage object disagrees with target runtime object")
    return ObjectCatalog(CATALOG_PROTOCOL_ID, _identifier(data["catalog_id"], "$.catalog_id", allow_reserved=True), limits, tuple(sorted(objects, key=lambda item: item.id)), tuple(sorted(capabilities, key=lambda item: item.id)), tuple(sorted(slots, key=lambda item: item.id)))


def load_catalog(path: str | Path) -> ObjectCatalog:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("SCHEMA_TYPE", "$", f"cannot load catalog: {exc}")
    return validate_catalog(raw)


def _lifecycle(raw: Any, path: str, max_steps: int) -> tuple[str, int | None]:
    data = _strict(raw, {"mode"}, {"steps"}, path)
    mode = data["mode"]
    if mode not in LIFECYCLE_MODES:
        _fail("INVALID_LIFECYCLE", f"{path}.mode", "unknown lifecycle")
    if mode == "timed":
        if "steps" not in data:
            _fail("MISSING_FIELD", path, "timed lifecycle requires steps")
        return mode, _integer(data["steps"], f"{path}.steps", low=1, high=max_steps)
    if "steps" in data:
        _fail("UNKNOWN_FIELD", f"{path}.steps", "only timed lifecycle accepts steps")
    return mode, None


def _operator(raw: Any, path: str, max_steps: int) -> OperatorSpec:
    data = _strict(raw, {"id", "kind", "capability_id", "scope", "target", "parameters", "lifecycle"}, set(), path)
    if data["kind"] not in OPERATOR_KINDS:
        _fail("UNKNOWN_OPERATOR", f"{path}.kind", "unknown operator")
    if data["scope"] not in SCOPES:
        _fail("SCHEMA_TYPE", f"{path}.scope", "must be local or linked")
    target = _strict(data["target"], {"object"}, set(), f"{path}.target")
    if not isinstance(data["parameters"], dict):
        _fail("SCHEMA_TYPE", f"{path}.parameters", "must be an object")
    mode, steps = _lifecycle(data["lifecycle"], f"{path}.lifecycle", max_steps)
    return OperatorSpec(_identifier(data["id"], f"{path}.id", allow_reserved=True), data["kind"], _identifier(data["capability_id"], f"{path}.capability_id", allow_reserved=True), data["scope"], _identifier(target["object"], f"{path}.target.object", allow_reserved=True), MappingProxyType(dict(data["parameters"])), mode, steps, path)


def _validate_parameters(op: OperatorSpec, target: Any, objects: Mapping[str, Any], cap: CapabilitySpec) -> tuple[Mapping[str, Any], tuple[str, ...], str | None]:
    path = f"{op.source_pointer}.parameters"
    raw = dict(op.parameters)
    extra_targets: tuple[str, ...] = ()
    slot_kind: str | None = None
    if op.kind == "impulse":
        data = _strict(raw, {"delta"}, set(), path)
        if not isinstance(target, (FieldObject, StockObject)):
            _fail("TARGET_KIND_MISMATCH", op.source_pointer, "impulse requires Field or Stock")
        params = {"delta": _number(data["delta"], f"{path}.delta")}
    elif op.kind == "drive":
        data = _strict(raw, {"mode", "rate"}, {"destination"}, path)
        mode = data["mode"]
        if mode not in {"field", "stock_source", "stock_sink", "stock_transfer"}:
            _fail("SCHEMA_TYPE", f"{path}.mode", "unknown drive mode")
        rate = _number(data["rate"], f"{path}.rate")
        if mode == "field" and not isinstance(target, FieldObject) or mode != "field" and not isinstance(target, StockObject):
            _fail("TARGET_KIND_MISMATCH", op.source_pointer, "drive mode and target kind disagree")
        if mode == "field" and rate == 0:
            _fail("OUT_OF_RANGE", f"{path}.rate", "field drive must be non-zero")
        if mode != "field" and rate <= 0:
            _fail("OUT_OF_RANGE", f"{path}.rate", "Stock flow rate must be positive")
        destination = data.get("destination")
        if mode == "stock_transfer":
            if not isinstance(destination, str) or destination not in objects or not isinstance(objects[destination], StockObject):
                _fail("UNKNOWN_OBJECT", f"{path}.destination", "must name a Stock")
            if objects[destination].transfer_unit != target.transfer_unit:
                _fail("CONSERVATION_REQUIRED", f"{path}.destination", "transfer units differ")
            extra_targets = (destination,)
        elif destination is not None:
            _fail("UNKNOWN_FIELD", f"{path}.destination", "only stock_transfer accepts destination")
        privilege = {"stock_source": "nonconserved_source", "stock_sink": "nonconserved_sink"}.get(mode)
        if privilege and privilege not in cap.privileges:
            _fail("CONSERVATION_REQUIRED", path, f"{mode} requires {privilege}")
        params = {"mode": mode, "rate": rate, **({"destination": destination} if destination else {})}
        slot_kind = "drive"
    elif op.kind == "attractor_modifier":
        data = _strict(raw, {"attractor", "weight"}, set(), path)
        if not isinstance(target, FieldObject) or target.dynamics is None:
            _fail("TARGET_KIND_MISMATCH", op.source_pointer, "requires a dynamic Field")
        weight = _number(data["weight"], f"{path}.weight", low=0.0)
        params = {"attractor": _number(data["attractor"], f"{path}.attractor", low=target.minimum, high=target.maximum), "weight": weight}
        slot_kind = "attractor"
    elif op.kind == "dynamics_modifier":
        data = _strict(raw, {"parameter", "delta"}, set(), path)
        parameter = _string(data["parameter"], f"{path}.parameter")
        if isinstance(target, FieldObject):
            if target.dynamics is None or parameter != "alpha":
                _fail("PARAMETER_NOT_ALLOWED", f"{path}.parameter", "Field only exposes alpha")
            slot_kind = "alpha"
        elif isinstance(target, RelationObject):
            match = next((item for item in target.parameters if item.id == parameter and item.dynamics_parameter), None)
            if match is None:
                _fail("PARAMETER_NOT_ALLOWED", f"{path}.parameter", "not a dynamics parameter")
            slot_kind = "dynamics"
        else:
            _fail("TARGET_KIND_MISMATCH", op.source_pointer, "requires dynamic Field or Relation")
        params = {"parameter": parameter, "delta": _number(data["delta"], f"{path}.delta")}
    elif op.kind == "process_start":
        _strict(raw, set(), set(), path)
        if not isinstance(target, ProcessObject):
            _fail("TARGET_KIND_MISMATCH", op.source_pointer, "requires Process")
        params = {}
    elif op.kind == "process_modify":
        data = _strict(raw, {"parameter", "delta"}, set(), path)
        if not isinstance(target, ProcessObject):
            _fail("TARGET_KIND_MISMATCH", op.source_pointer, "requires Process")
        parameter = _string(data["parameter"], f"{path}.parameter")
        if not any(item.id == parameter for item in target.parameters):
            _fail("PARAMETER_NOT_ALLOWED", f"{path}.parameter", "unknown Process parameter")
        params = {"parameter": parameter, "delta": _number(data["delta"], f"{path}.delta")}
        slot_kind = "process_parameter"
    else:
        data = _strict(raw, {"action"}, {"parameter", "delta"}, path)
        if not isinstance(target, RelationObject):
            _fail("TARGET_KIND_MISMATCH", op.source_pointer, "requires Relation")
        action = data["action"]
        if action not in {"create", "delete", "modify"}:
            _fail("SCHEMA_TYPE", f"{path}.action", "unknown relation action")
        if action == "create" and target.lifecycle != "template":
            _fail("OPERATOR_NOT_ALLOWED", path, "create requires relation template")
        if action in {"delete", "modify"} and target.lifecycle != "existing":
            _fail("OPERATOR_NOT_ALLOWED", path, f"{action} requires existing relation")
        if action == "delete" and target.ownership == "world" and "delete_world_relation" not in cap.privileges:
            _fail("OWNERSHIP_DENIED", path, "cannot delete world-owned relation")
        if action == "delete" and op.lifecycle_mode == "timed":
            _fail("INVALID_LIFECYCLE", path, "temporary deletion cannot restore an unspecified runtime relation snapshot")
        params = {"action": action}
        if action == "modify":
            if set(data) != {"action", "parameter", "delta"}:
                _fail("MISSING_FIELD", path, "modify requires parameter and delta")
            parameter = _string(data["parameter"], f"{path}.parameter")
            if not any(item.id == parameter for item in target.parameters):
                _fail("PARAMETER_NOT_ALLOWED", f"{path}.parameter", "unknown Relation parameter")
            params.update(parameter=parameter, delta=_number(data["delta"], f"{path}.delta"))
            slot_kind = "relation_parameter"
        elif set(data) != {"action"}:
            _fail("UNKNOWN_FIELD", path, "create/delete accept only action")
    maximum = cap.numeric_limits.get("max_abs_value")
    if maximum is not None:
        for key in ("delta", "rate"):
            if key in params and abs(params[key]) > maximum:
                _fail("OUT_OF_RANGE", f"{path}.{key}", "exceeds capability numeric limit")
    if "weight" in params and "max_weight" in cap.numeric_limits and params["weight"] > cap.numeric_limits["max_weight"]:
        _fail("OUT_OF_RANGE", f"{path}.weight", "exceeds capability weight limit")
    return MappingProxyType(params), extra_targets, slot_kind


def validate_mechanism(raw: Any, catalog: ObjectCatalog) -> MechanismIR:
    data = _strict(raw, {"protocol", "id", "name", "scope", "artifact_policy", "capability_ids", "max_instances", "operators"}, set(), "$")
    if data["protocol"] != PROTOCOL_ID:
        _fail("SCHEMA_TYPE", "$.protocol", f"must be {PROTOCOL_ID}")
    artifact_id = _identifier(data["id"], "$.id")
    name = _string(data["name"], "$.name").strip()
    if len(name) > 80:
        _fail("OUT_OF_RANGE", "$.name", "must be at most 80 characters")
    scope = _strict(data["scope"], {"kind", "anchor"}, set(), "$.scope")
    if scope["kind"] not in SCOPES:
        _fail("SCHEMA_TYPE", "$.scope.kind", "must be local or linked")
    policy = _strict(data["artifact_policy"], {"owner", "event_namespace", "temporal_handles"}, set(), "$.artifact_policy")
    if policy != {"owner": "activation_source", "event_namespace": "derived", "temporal_handles": "per_instance"}:
        _fail("OWNERSHIP_DENIED", "$.artifact_policy", "must use the frozen derived ownership policy")
    objects = catalog.object_index
    anchor = _identifier(scope["anchor"], "$.scope.anchor", allow_reserved=True)
    if anchor not in objects:
        _fail("UNKNOWN_OBJECT", "$.scope.anchor", "unknown catalog object")
    capability_ids = _string_list(data["capability_ids"], "$.capability_ids", identifiers=True)
    capabilities = catalog.capability_index
    unknown_caps = set(capability_ids) - set(capabilities)
    if unknown_caps:
        _fail("UNKNOWN_CAPABILITY", "$.capability_ids", f"unknown: {sorted(unknown_caps)}")
    max_instances = _integer(data["max_instances"], "$.max_instances", low=1, high=catalog.limits.max_instances)
    if not isinstance(data["operators"], list) or not data["operators"]:
        _fail("SCHEMA_TYPE", "$.operators", "must be a non-empty list")
    if len(data["operators"]) > catalog.limits.max_operators:
        _fail("LIMIT_MAX_OPERATORS", "$.operators", "exceeds catalog limit")
    specs = tuple(_operator(item, f"$.operators[{index}]", catalog.limits.max_duration_steps) for index, item in enumerate(data["operators"]))
    _unique((item.id for item in specs), "$.operators")
    slots = tuple(sorted(catalog.effect_slots, key=lambda item: item.id))
    claimed: set[str] = set()
    operator_irs: list[OperatorIR] = []
    all_reservations: list[SlotReservation] = []
    required_objects: set[str] = {anchor}
    required_caps: set[str] = set()
    event_types: set[str] = set()
    handles: set[str] = set()
    source_map: dict[str, str] = {}
    stock_flow_targets: set[str] = set()
    impulse_targets: set[str] = set()
    process_start_targets: set[str] = set()
    destructive_relation_targets: set[str] = set()
    for op in sorted(specs, key=lambda item: item.id):
        if op.capability_id not in capability_ids:
            _fail("UNKNOWN_CAPABILITY", f"{op.source_pointer}.capability_id", "capability not declared by mechanism")
        cap = capabilities[op.capability_id]
        if cap.operator_kind != op.kind:
            _fail("CAPABILITY_KIND_MISMATCH", f"{op.source_pointer}.capability_id", "capability is for another operator")
        if op.target_object_id not in objects:
            _fail("UNKNOWN_OBJECT", f"{op.source_pointer}.target.object", "unknown catalog object")
        target = objects[op.target_object_id]
        if isinstance(target, DerivedObject):
            _fail("DERIVED_READ_ONLY", f"{op.source_pointer}.target", "Derived objects are read-only")
        if op.kind not in target.allowed_operators:
            _fail("OPERATOR_NOT_ALLOWED", op.source_pointer, "operator is not exposed by target")
        if op.target_object_id not in cap.targets:
            _fail("CAPABILITY_TARGET_DENIED", f"{op.source_pointer}.target", "capability does not grant this target")
        if op.scope not in cap.scopes or op.scope != scope["kind"]:
            _fail("CAPABILITY_SCOPE_DENIED", f"{op.source_pointer}.scope", "scope is not granted or disagrees with mechanism")
        if op.lifecycle_mode not in cap.lifecycles:
            _fail("CAPABILITY_LIFETIME_DENIED", f"{op.source_pointer}.lifecycle", "lifecycle is not granted")
        if op.lifecycle_mode == "permanent" and "permanent_modifier" not in cap.privileges:
            _fail("CAPABILITY_LIFETIME_DENIED", f"{op.source_pointer}.lifecycle", "permanent effects require permanent_modifier")
        if op.kind == "impulse" and op.lifecycle_mode != "instant":
            _fail("INVALID_LIFECYCLE", f"{op.source_pointer}.lifecycle", "impulse must be instant")
        if op.kind != "impulse" and op.lifecycle_mode == "instant":
            _fail("INVALID_LIFECYCLE", f"{op.source_pointer}.lifecycle", "persistent operator cannot be instant")
        params, extra_targets, slot_kind = _validate_parameters(op, target, objects, cap)
        requested_action = params.get("action", "start" if op.kind == "process_start" else "modify")
        if requested_action not in cap.actions:
            _fail("CAPABILITY_TARGET_DENIED", op.source_pointer, f"capability does not grant action {requested_action!r}")
        if isinstance(target, ProcessObject) and target.ownership == "world" and "modify_world_owned_process" not in cap.privileges:
            _fail("OWNERSHIP_DENIED", op.source_pointer, "world-owned Process requires modify_world_owned_process")
        if op.kind == "impulse":
            if op.target_object_id in impulse_targets:
                _fail("OPERATOR_CONFLICT", op.source_pointer, "duplicate impulse target would create competing set effects")
            impulse_targets.add(op.target_object_id)
        if op.kind == "process_start":
            if op.target_object_id in process_start_targets:
                _fail("OPERATOR_CONFLICT", op.source_pointer, "duplicate process lifecycle owner")
            process_start_targets.add(op.target_object_id)
        if op.kind == "relation_modifier" and params.get("action") == "delete":
            if op.target_object_id in destructive_relation_targets:
                _fail("OPERATOR_CONFLICT", op.source_pointer, "duplicate destructive Relation writer")
            destructive_relation_targets.add(op.target_object_id)
        if op.kind == "drive" and isinstance(target, StockObject):
            participants = {op.target_object_id, *extra_targets}
            process_stocks = {
                object_id
                for process in objects.values() if isinstance(process, ProcessObject)
                for object_id in process.source_objects + process.target_objects
                if isinstance(objects[object_id], StockObject)
            }
            if max_instances != 1:
                _fail("OPERATOR_CONFLICT", op.source_pointer, "Stock flows require max_instances=1")
            if participants & process_stocks:
                _fail("OPERATOR_CONFLICT", op.source_pointer, "generated Stock flow cannot share a Process Stock")
            if participants & stock_flow_targets:
                _fail("OPERATOR_CONFLICT", op.source_pointer, "Stock flows may not share source or destination")
            stock_flow_targets.update(participants)
        required_objects.add(op.target_object_id)
        required_objects.update(extra_targets)
        required_caps.add(op.capability_id)
        reservations: list[SlotReservation] = []
        if slot_kind:
            eligible = [item for item in slots if item.slot_kind == slot_kind and item.target_object_id == op.target_object_id and item.id not in claimed]
            for instance in range(max_instances):
                if not eligible:
                    _fail("SLOT_EXHAUSTED", op.source_pointer, f"no {slot_kind} slot for instance {instance}")
                selected = eligible.pop(0)
                claimed.add(selected.id)
                reservations.append(SlotReservation(selected.id, slot_kind, op.target_object_id, artifact_id, op.id, instance))
        namespace = f"gm.v06.artifact.{artifact_id}"
        if op.lifecycle_mode == "timed":
            event_types.add(f"{namespace}.{op.id}.expire")
            for instance in range(max_instances):
                handles.add(f"{namespace}.instance.{instance}.{op.id}.expiry.{{activation_id}}")
        source_map[op.id] = op.source_pointer
        operator_ir = OperatorIR(op.id, op.kind, op.capability_id, op.scope, op.target_object_id, params, LifecycleIR(op.lifecycle_mode, op.lifecycle_steps), tuple(reservations), op.source_pointer)
        operator_irs.append(operator_ir)
        all_reservations.extend(reservations)
    if len(required_objects) > catalog.limits.max_targets:
        _fail("LIMIT_MAX_TARGETS", "$.operators", "resolved targets exceed catalog limit")
    if len(all_reservations) > catalog.limits.max_total_effect_slots:
        _fail("LIMIT_MAX_EFFECT_SLOTS", "$.operators", "slot reservations exceed catalog limit")
    if len(handles) > catalog.limits.max_scheduled_handles:
        _fail("LIMIT_MAX_HANDLES", "$.operators", "temporal handles exceed catalog limit")
    return MechanismIR(
        PROTOCOL_ID, artifact_id, name, canonical_sha256(raw), scope["kind"], anchor,
        max_instances, f"gm.v06.artifact.{artifact_id}", tuple(operator_irs),
        tuple(sorted(required_objects)), tuple(sorted(required_caps)),
        tuple(all_reservations), tuple(sorted(event_types)), tuple(sorted(handles)),
        MappingProxyType(dict(sorted(source_map.items()))),
    )


def validate_mechanism_batch(raw_documents: Iterable[Any], catalog: ObjectCatalog) -> tuple[MechanismIR, ...]:
    """Validate and jointly allocate slots for an immutable installation batch."""

    validated = [validate_mechanism(raw, catalog) for raw in raw_documents]
    ids = [item.artifact_id for item in validated]
    if len(ids) != len(set(ids)):
        _fail("DUPLICATE_ID", "$", "installation batch contains duplicate artifact ids")
    available = tuple(sorted(catalog.effect_slots, key=lambda item: item.id))
    claimed: set[str] = set()
    stock_flow_targets: set[str] = set()
    process_start_targets: set[str] = set()
    rebuilt: list[MechanismIR] = []
    for ir in sorted(validated, key=lambda item: item.artifact_id):
        operators: list[OperatorIR] = []
        reservations: list[SlotReservation] = []
        for operator_ir in sorted(ir.operators, key=lambda item: item.operator_id):
            target = catalog.object_index[operator_ir.target_object_id]
            if operator_ir.kind == "drive" and isinstance(target, StockObject):
                participants = {operator_ir.target_object_id}
                destination = operator_ir.parameters.get("destination")
                if destination:
                    participants.add(destination)
                if participants & stock_flow_targets:
                    _fail("OPERATOR_CONFLICT", operator_ir.source_pointer, "installation batch has overlapping Stock flows")
                stock_flow_targets.update(participants)
            if operator_ir.kind == "process_start":
                if operator_ir.target_object_id in process_start_targets:
                    _fail("OPERATOR_CONFLICT", operator_ir.source_pointer, "installation batch has multiple Process lifecycle owners")
                process_start_targets.add(operator_ir.target_object_id)
            if operator_ir.reservations:
                slot_kind = operator_ir.reservations[0].slot_kind
                allocated = []
                for instance in range(ir.max_instances):
                    eligible = [
                        item for item in available
                        if item.slot_kind == slot_kind
                        and item.target_object_id == operator_ir.target_object_id
                        and item.id not in claimed
                    ]
                    if not eligible:
                        _fail("SLOT_EXHAUSTED", operator_ir.source_pointer, "installation batch exhausted compatible slots")
                    selected = eligible[0]
                    claimed.add(selected.id)
                    allocated.append(SlotReservation(
                        selected.id, slot_kind, operator_ir.target_object_id,
                        ir.artifact_id, operator_ir.operator_id, instance,
                    ))
                operator_ir = replace(operator_ir, reservations=tuple(allocated))
                reservations.extend(allocated)
            operators.append(operator_ir)
        rebuilt.append(replace(ir, operators=tuple(operators), reservations=tuple(reservations)))
    return tuple(rebuilt)
