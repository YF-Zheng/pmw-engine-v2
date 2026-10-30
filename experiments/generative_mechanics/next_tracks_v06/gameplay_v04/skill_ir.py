"""Versioned Skill IR validation and lowering to frozen v0.4 blueprints."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, NamedTuple

from .conditions import ConditionLimits
from .contracts import GameplayContractError
from .materials import MaterialAuthority
from .skills import SkillBlueprint, parse_skill_blueprint


PROTOCOL = "pmw-skill-ir-v1"
MAX_ENTRIES = 4
MAX_TAGS = 8
MAX_SUMMARY_LENGTH = 240
MAX_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 600
MAX_MODEL_LENGTH = 128
MAX_JSON_DEPTH = 128
MAX_JSON_VALUES = 65536
MAX_JSON_STRING = 4096
MAX_JSON_SAFE_INT = 2**53
SUPPORTED_EVENT = "damage_resolved"
RESERVED_TRIGGERS = frozenset({
    "on_tick", "on_expire", "transition", "condition_enter", "condition_exit",
})
RESERVED_EVENTS = frozenset({
    "action_started", "attack_applied", "status_changed", "weather_changed",
    "resource_harvested",
})
SELECTOR_KINDS = frozenset({
    "self", "target_actor", "current_area", "linked_object", "adjacent_area",
})
ORIGIN_SOURCES = frozenset({"reference", "generated", "authored"})
_ID = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")

OPERATOR_KINDS = {
    "impulse": frozenset({
        "damage", "heal", "shield", "add_resource", "modify_field",
        "apply_status", "grant_trait",
    }),
    "drive/source": frozenset({"drive_source"}),
    "attractor_modifier": frozenset({"modify_attractor"}),
    "dynamics_modifier": frozenset({"modify_rate", "dynamics_modifier"}),
    "process_start": frozenset({"process_start"}),
    "process_modify": frozenset({"process_modify"}),
    "relation_modifier": frozenset({
        "relation_modifier", "move_actor",
    }),
}
STATE_CLASS_KINDS = {
    "Field": frozenset({
        "modify_field", "modify_attractor", "modify_rate",
        "dynamics_modifier",
    }),
    "Stock": frozenset({
        "add_resource", "process_start", "process_modify", "drive_source",
    }),
    "Process": frozenset({"process_start", "process_modify"}),
    "Relation": frozenset({"relation_modifier", "move_actor"}),
    "Discrete": frozenset({"apply_status", "grant_trait"}),
    "Derived": frozenset(),
}


@dataclass(frozen=True, slots=True)
class SkillEntryIR:
    id: str
    trigger_kind: str
    event: str | None
    condition: dict[str, Any] | None
    effects: tuple[dict[str, Any], ...]
    max_firings_per_root: int


@dataclass(frozen=True, slots=True)
class SkillIR:
    id: str
    version: int
    name: str
    description: str
    origin_source: str
    origin_model: str | None
    context_hash: str | None
    material_ids: tuple[str, ...]
    traits: tuple[str, ...]
    selectors: tuple[str, ...]
    relation_types: tuple[str, ...]
    mana: float
    duration: int
    entries: tuple[SkillEntryIR, ...]
    status_duration: Mapping[str, Any] | None
    budget: float
    summary: str
    tags: tuple[str, ...]
    authority: MaterialAuthority
    statuses: Mapping[str, Any]
    canonical_hash: str
    canonical_json: str
    condition_nodes: int
    condition_limits: ConditionLimits


class SkillIRMetadata(NamedTuple):
    id: str
    version: int
    canonical_hash: str


@dataclass(frozen=True, slots=True)
class CompiledSkillIR:
    ir: SkillIR
    blueprints: tuple[SkillBlueprint, ...]
    canonical_hash: str
    metadata: tuple[SkillIRMetadata, ...]
    metadata_by_ir_hash: Mapping[str, tuple[SkillIRMetadata, ...]]
    operators: tuple[str, ...]
    state_classes: tuple[str, ...]
    preview: Mapping[str, Any]


def _validate_json_shape(raw: Any) -> None:
    """Reject non-JSON values and excessive input before recursive copying."""
    stack = [(raw, "$", 0)]
    value_count = 1
    if value_count > MAX_JSON_VALUES:
        raise GameplayContractError(
            f"$ exceeds JSON value limit {MAX_JSON_VALUES}"
        )
    while stack:
        value, path, depth = stack.pop()

        if value is None:
            continue
        if isinstance(value, dict):
            child_depth = depth + 1
            if child_depth > MAX_JSON_DEPTH:
                raise GameplayContractError(
                    f"{path} exceeds container depth limit {MAX_JSON_DEPTH}"
                )
            for key, child in value.items():
                if not isinstance(key, str):
                    raise GameplayContractError(
                        f"{path} keys must be strings"
                    )
                if len(key) > MAX_JSON_STRING:
                    raise GameplayContractError(
                        f"{path} key exceeds string limit {MAX_JSON_STRING}"
                    )
                if key.isidentifier():
                    child_path = f"{path}.{key}"
                else:
                    rendered_key = repr(key)
                    if len(rendered_key) > 80:
                        rendered_key = f"{rendered_key[:77]}..."
                    child_path = f"{path}[{rendered_key}]"
                value_count += 1
                if value_count > MAX_JSON_VALUES:
                    raise GameplayContractError(
                        f"{child_path} exceeds JSON value limit "
                        f"{MAX_JSON_VALUES}"
                    )
                stack.append((child, child_path, child_depth))
            continue
        if isinstance(value, (list, tuple)):
            child_depth = depth + 1
            if child_depth > MAX_JSON_DEPTH:
                raise GameplayContractError(
                    f"{path} exceeds container depth limit {MAX_JSON_DEPTH}"
                )
            for index in range(len(value) - 1, -1, -1):
                child_path = f"{path}[{index}]"
                value_count += 1
                if value_count > MAX_JSON_VALUES:
                    raise GameplayContractError(
                        f"{child_path} exceeds JSON value limit "
                        f"{MAX_JSON_VALUES}"
                    )
                stack.append((value[index], child_path, child_depth))
            continue
        if isinstance(value, str):
            if len(value) > MAX_JSON_STRING:
                raise GameplayContractError(
                    f"{path} exceeds string limit {MAX_JSON_STRING}"
                )
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            if abs(value) > MAX_JSON_SAFE_INT:
                raise GameplayContractError(
                    f"{path} exceeds JSON safe integer limit "
                    f"{MAX_JSON_SAFE_INT}"
                )
            continue
        if isinstance(value, float):
            if not math.isfinite(value):
                raise GameplayContractError(
                    f"{path} must be finite numeric; positive integer "
                    "fields also require a finite value"
                )
            continue
        raise GameplayContractError(
            f"{path} has unsupported JSON value type {type(value).__name__}"
        )


def parse_skill_ir(
    raw: Any,
    statuses: Mapping[str, Any],
    authority: MaterialAuthority,
    *,
    condition_limits: ConditionLimits | None = None,
) -> SkillIR:
    """Parse one strict, pure, versioned Skill IR document."""
    _validate_json_shape(raw)
    raw = deepcopy(raw)
    if condition_limits is None:
        condition_limits = ConditionLimits()
    elif not isinstance(condition_limits, ConditionLimits):
        raise GameplayContractError(
            "condition_limits must be a trusted ConditionLimits"
        )
    default_limits = ConditionLimits()
    if (
        condition_limits.max_depth > default_limits.max_depth
        or condition_limits.max_nodes > default_limits.max_nodes
        or condition_limits.max_children > default_limits.max_children
    ):
        raise GameplayContractError(
            "condition_limits is tighten-only relative to ConditionLimits() "
            f"defaults ({default_limits.max_depth}/{default_limits.max_nodes}/"
            f"{default_limits.max_children})"
        )
    if not isinstance(authority, MaterialAuthority):
        raise GameplayContractError(
            "authority must be a trusted MaterialAuthority"
        )
    if not isinstance(statuses, Mapping):
        raise GameplayContractError("statuses must be a trusted mapping")

    root = _strict(
        raw,
        {
            "protocol", "identity", "origin", "capability", "targeting",
            "costs", "entries", "lifecycle", "limits", "display",
        },
        "$",
    )
    if root["protocol"] != PROTOCOL:
        raise GameplayContractError("$.protocol must be pmw-skill-ir-v1")
    identity = _strict(
        root["identity"], {"id", "version", "name", "description"},
        "$.identity",
    )
    skill_id = _identifier(identity["id"], "$.identity.id")
    version = _positive_int(identity["version"], "$.identity.version")
    name = _display_text(
        identity["name"], "$.identity.name", MAX_NAME_LENGTH
    )
    description = _display_text(
        identity["description"], "$.identity.description",
        MAX_DESCRIPTION_LENGTH,
    )

    origin = _strict(
        root["origin"],
        {"source", "model", "context_hash", "material_ids"},
        "$.origin",
    )
    origin_source = origin["source"]
    if (
        not isinstance(origin_source, str)
        or origin_source not in ORIGIN_SOURCES
    ):
        raise GameplayContractError("$.origin.source is invalid")
    model = origin["model"]
    if model is not None and not isinstance(model, str):
        raise GameplayContractError("$.origin.model must be null or text")
    if model is not None and len(model) > MAX_MODEL_LENGTH:
        raise GameplayContractError(
            f"$.origin.model must be at most {MAX_MODEL_LENGTH} characters"
        )
    context_hash = origin["context_hash"]
    if context_hash is not None and (
        not isinstance(context_hash, str) or _HEX64.fullmatch(context_hash) is None
    ):
        raise GameplayContractError(
            "$.origin.context_hash must be null or 64 lowercase hex characters"
        )
    material_ids = _unique_identifiers(
        origin["material_ids"], "$.origin.material_ids", require_nonempty=True
    )
    if tuple(sorted(material_ids)) != authority.material_ids:
        raise GameplayContractError(
            "$.origin.material_ids does not match trusted material authority"
        )

    capability = _strict(root["capability"], {"traits"}, "$.capability")
    traits = _unique_strings(
        capability["traits"], "$.capability.traits", identifiers=True
    )
    targeting = _strict(
        root["targeting"], {"selectors", "relation_types"}, "$.targeting"
    )
    selectors = _unique_strings(
        targeting["selectors"], "$.targeting.selectors", require_nonempty=True
    )
    if any(item not in SELECTOR_KINDS for item in selectors):
        raise GameplayContractError("$.targeting.selectors contains an unknown selector")
    relation_types = _unique_strings(
        targeting["relation_types"], "$.targeting.relation_types",
        identifiers=True,
    )
    if any(item not in authority.selectors for item in selectors):
        raise GameplayContractError(
            "$.targeting.selectors exceeds material scope authorization"
        )
    if any(
        item == "linked_object" and not relation_types
        for item in selectors
    ):
        raise GameplayContractError(
            "$.targeting.linked_object requires an explicit relation type"
        )

    costs = _strict(root["costs"], {"mana", "duration"}, "$.costs")
    mana = _nonnegative_number(costs["mana"], "$.costs.mana")
    duration = _positive_int(costs["duration"], "$.costs.duration")

    raw_entries = root["entries"]
    if not isinstance(raw_entries, list) or not 1 <= len(raw_entries) <= MAX_ENTRIES:
        raise GameplayContractError("$.entries must contain 1..4 entries")
    entries = tuple(
        _parse_entry(item, index) for index, item in enumerate(raw_entries)
    )
    if len({item.id for item in entries}) != len(entries):
        raise GameplayContractError("$.entries contains duplicate IDs")
    if sum(item.trigger_kind == "on_use" for item in entries) > 1:
        raise GameplayContractError("$.entries permits at most one on_use entry")
    for entry in entries:
        lowered_id = f"{skill_id}__{entry.id}"
        _identifier(lowered_id, f"$.entries[{entry.id}].lowered_id")
        targets = tuple(
            _effect_target(
                item, f"$.entries[{entry.id}].effects[{index}]"
            )
            for index, item in enumerate(entry.effects)
        )
        if any(target["kind"] not in selectors for target in targets):
            raise GameplayContractError(
                f"$.entries[{entry.id}].effects exceeds targeting selectors"
            )
        if any(
            target.get("relation_type") is not None
            and target["relation_type"] not in relation_types
            for target in targets
        ):
            raise GameplayContractError(
                f"$.entries[{entry.id}].effects exceeds target relation types"
            )

    lifecycle = _strict(
        root["lifecycle"], {"status_duration"}, "$.lifecycle"
    )
    status_duration = _status_duration(
        lifecycle["status_duration"], "$.lifecycle.status_duration"
    )
    limits = _strict(root["limits"], {"budget"}, "$.limits")
    budget = _positive_number(limits["budget"], "$.limits.budget")
    if budget > authority.budget_points:
        raise GameplayContractError("$.limits.budget exceeds material authority")

    display = _strict(root["display"], {"summary", "tags"}, "$.display")
    summary = display["summary"]
    if not isinstance(summary, str) or len(summary) > MAX_SUMMARY_LENGTH:
        raise GameplayContractError(
            f"$.display.summary must be a string of at most {MAX_SUMMARY_LENGTH} characters"
        )
    tags = _unique_strings(display["tags"], "$.display.tags")
    if len(tags) > MAX_TAGS:
        raise GameplayContractError("$.display.tags permits at most 8 tags")

    condition_nodes = _document_condition_nodes(entries, condition_limits)
    if condition_nodes > condition_limits.max_nodes:
        raise GameplayContractError(
            "$.entries exceeds document condition max_nodes "
            f"{condition_limits.max_nodes}"
        )

    try:
        material_usage = _document_material_usage(
            skill_id, version, entries, statuses, authority, budget,
            duration, mana, relation_types,
        )
    except GameplayContractError:
        raise
    except (TypeError, KeyError, AttributeError) as error:
        raise GameplayContractError(
            "delegated parse_skill_blueprint failed: "
            f"{type(error).__name__}: {error}"
        ) from error
    if not (
        isinstance(material_usage, (int, float))
        and not isinstance(material_usage, bool)
    ):
        raise GameplayContractError(
            "delegated parse_skill_blueprint returned invalid material usage"
        )
    if material_usage > budget:
        raise GameplayContractError(
            "$.entries compound effects exceed the shared document budget"
        )

    canonical_json = json.dumps(
        raw, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    canonical_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return SkillIR(
        skill_id, version, name, description, origin_source, model,
        context_hash, material_ids, traits, selectors, relation_types, mana,
        duration, entries,
        None if status_duration is None else MappingProxyType(status_duration),
        budget, summary, tags, authority, MappingProxyType(dict(statuses)),
        canonical_hash, canonical_json, condition_nodes, condition_limits,
    )


def compile_skill_ir(ir: SkillIR) -> CompiledSkillIR:
    """Lower a validated IR into unchanged v0.4 SkillBlueprint values."""
    if not isinstance(ir, SkillIR):
        raise GameplayContractError("compile_skill_ir requires a trusted SkillIR")
    if not isinstance(ir.authority, MaterialAuthority):
        raise GameplayContractError(
            "SkillIR authority must be a trusted MaterialAuthority"
        )
    if not isinstance(ir.condition_limits, ConditionLimits):
        raise GameplayContractError(
            "SkillIR condition_limits must be a trusted ConditionLimits"
        )
    if not isinstance(ir.statuses, Mapping):
        raise GameplayContractError(
            "SkillIR statuses must be a trusted mapping"
        )
    if not isinstance(ir.canonical_json, str):
        raise GameplayContractError(
            "SkillIR canonical_json must be canonical JSON text"
        )
    try:
        fresh = parse_skill_ir(
            json.loads(ir.canonical_json),
            ir.statuses,
            ir.authority,
            condition_limits=ir.condition_limits,
        )
        if fresh.canonical_hash != ir.canonical_hash:
            raise GameplayContractError(
                "SkillIR canonical_hash does not match validated canonical_json"
            )
        blueprints = tuple(
            _lower_entry(fresh, entry)
            for entry in fresh.entries
        )
        metadata = tuple(
            SkillIRMetadata(item.id, item.version, item.canonical_hash)
            for item in blueprints
        )
        operators = _operators(blueprints)
        state_classes = _state_classes(fresh, blueprints)
        preview = _preview(
            fresh, blueprints, operators, state_classes
        )
    except GameplayContractError:
        raise
    except (
        json.JSONDecodeError, TypeError, KeyError, AttributeError, ValueError,
        RecursionError,
    ) as error:
        raise GameplayContractError(
            "delegated SkillIR lowering failed: "
            f"{type(error).__name__}: {error}"
        ) from error
    return CompiledSkillIR(
        fresh, blueprints, fresh.canonical_hash, metadata,
        MappingProxyType({fresh.canonical_hash: metadata}),
        operators, state_classes,
        MappingProxyType(preview),
    )


def _parse_entry(raw: Any, index: int) -> SkillEntryIR:
    path = f"$.entries[{index}]"
    data = _strict(
        raw,
        {"id", "trigger", "condition", "effects", "max_firings_per_root"},
        path,
    )
    entry_id = _identifier(data["id"], f"{path}.id")
    trigger = data["trigger"]
    trigger_kind, event = _trigger(trigger, f"{path}.trigger")
    condition = data["condition"]
    if condition is not None:
        _validate_condition_shape(condition, f"{path}.condition")
    raw_effects = data["effects"]
    if not isinstance(raw_effects, list) or not raw_effects:
        raise GameplayContractError(f"{path}.effects must be non-empty")
    effects = []
    for effect_index, effect in enumerate(raw_effects):
        if not isinstance(effect, dict):
            raise GameplayContractError(
                f"{path}.effects[{effect_index}] must be an object"
            )
        _validate_effect_scalars(
            effect, f"{path}.effects[{effect_index}]"
        )
        effects.append(dict(effect))
    effect_ids = []
    for index, effect in enumerate(effects):
        effect_id = effect.get("id")
        if not isinstance(effect_id, str) or not effect_id:
            raise GameplayContractError(
                f"{path}.effects[{index}].id must be a non-empty string"
            )
        effect_ids.append(effect_id)
    if len(set(effect_ids)) != len(effect_ids):
        raise GameplayContractError(f"{path}.effects contains duplicate IDs")
    firings = _bounded_int(
        data["max_firings_per_root"], f"{path}.max_firings_per_root", 1, 8
    )
    return SkillEntryIR(
        entry_id, trigger_kind, event,
        None if condition is None else dict(condition),
        tuple(effects), firings,
    )


def _trigger(raw: Any, path: str) -> tuple[str, str | None]:
    if not isinstance(raw, dict) or "kind" not in raw:
        raise GameplayContractError(f"{path} must be a trigger object")
    kind = raw.get("kind")
    if not isinstance(kind, str):
        raise GameplayContractError(f"{path}.kind must be text")
    if kind == "on_use":
        if set(raw) != {"kind"}:
            raise GameplayContractError(f"{path} on_use has unknown fields")
        return "on_use", None
    if kind == "on_event":
        if set(raw) != {"kind", "event"}:
            raise GameplayContractError(f"{path} on_event has unknown fields")
        event = raw.get("event")
        if not isinstance(event, str):
            raise GameplayContractError(f"{path}.event must be text")
        if event == SUPPORTED_EVENT:
            return "on_event", SUPPORTED_EVENT
        if event in RESERVED_EVENTS:
            raise GameplayContractError(
                f"language_gap:on_event:{event} is not executed by the accepted runtime"
            )
        raise GameplayContractError(f"{path}.event is unknown")
    if kind in RESERVED_TRIGGERS:
        raise GameplayContractError(
            f"language_gap:{kind} is not executed by the accepted runtime"
        )
    raise GameplayContractError(f"{path}.kind is unknown")


def _lower_entry(ir: SkillIR, entry: SkillEntryIR) -> SkillBlueprint:
    raw = _entry_raw(
        ir.id, ir.version, entry, ir.budget, ir.duration, ir.mana,
        ir.relation_types, ir.material_ids,
    )
    return parse_skill_blueprint(raw, ir.statuses, ir.authority)


def _document_condition_nodes(
    entries: tuple[SkillEntryIR, ...], limits: ConditionLimits,
) -> int:
    count = 0
    for entry in entries:
        count += _condition_nodes(
            entry.condition, f"$.entries[{entry.id}].condition",
            1, limits,
        )
        for index, effect in enumerate(entry.effects):
            count += _condition_nodes(
                effect.get("condition"),
                f"$.entries[{entry.id}].effects[{index}].condition",
                1, limits,
            )
    return count


def _condition_nodes(
    raw: Any, path: str, depth: int, limits: ConditionLimits,
) -> int:
    """Mirror parse_condition's shared traversal semantics without evaluation."""
    if depth > limits.max_depth:
        raise GameplayContractError(
            f"{path} exceeds condition max_depth {limits.max_depth}"
        )
    if raw is None:
        return 1
    if not isinstance(raw, dict) or len(raw) != 1:
        return 1
    kind, value = next(iter(raw.items()))
    if not isinstance(kind, str):
        raise GameplayContractError(f"{path} operator must be text")
    if kind in {"all", "any"}:
        if not isinstance(value, list) or not value:
            return 1
        if len(value) > limits.max_children:
            raise GameplayContractError(
                f"{path}.{kind} exceeds condition max_children "
                f"{limits.max_children}"
            )
        return 1 + sum(
            _condition_nodes(
                item, f"{path}.{kind}[{index}]", depth + 1, limits
            )
            for index, item in enumerate(value)
        )
    if kind == "not":
        return 1 + _condition_nodes(
            value, f"{path}.not", depth + 1, limits
        )
    return 1


def _validate_condition_shape(raw: Any, path: str) -> None:
    """Count every node with the existing parse_condition semantics."""
    if raw is None:
        return
    if not isinstance(raw, dict) or len(raw) != 1:
        raise GameplayContractError(
            f"{path} must contain exactly one condition operator"
        )
    kind, value = next(iter(raw.items()))
    if not isinstance(kind, str):
        raise GameplayContractError(f"{path} operator must be text")
    if kind in {"all", "any"}:
        if not isinstance(value, list) or not value:
            raise GameplayContractError(f"{path}.{kind} must be a non-empty list")
        for index, child in enumerate(value):
            _validate_condition_shape(child, f"{path}.{kind}[{index}]")
    elif kind == "not":
        _validate_condition_shape(value, f"{path}.not")


def _document_material_usage(
    skill_id: str,
    version: int,
    entries: tuple[SkillEntryIR, ...],
    statuses: Mapping[str, Any],
    authority: MaterialAuthority,
    budget: float,
    duration: int,
    mana: float,
    relation_types: tuple[str, ...],
) -> float:
    total = 0.0
    for entry in entries:
        raw = _entry_raw(
            skill_id, version, entry, budget, duration, mana,
            relation_types, authority.material_ids,
        )
        total += parse_skill_blueprint(raw, statuses, authority).budget_used
    return total


def _entry_raw(
    skill_id: str,
    version: int,
    entry: SkillEntryIR,
    budget: float,
    duration: int,
    mana: float,
    relation_types: tuple[str, ...],
    material_ids: tuple[str, ...],
) -> dict[str, Any]:
    passive = entry.trigger_kind == "on_event"
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "passive_blueprint" if passive else "skill_blueprint",
        "id": f"{skill_id}__{entry.id}",
        "version": version,
        "trigger": "damage_resolved" if passive else "on_use",
        "condition": entry.condition,
        "duration": None,
        "cost": (
            {"duration": 1, "mana": 0}
            if passive else {"duration": duration, "mana": mana}
        ),
        "scope": {
        "selectors": list(dict.fromkeys(
            _effect_target(
                item, f"$.entries[{skill_id}__{entry.id}].effect",
            )["kind"]
            for item in entry.effects
        )),
            "relation_types": list(relation_types),
        },
        "effects": list(entry.effects),
        "budget": {"limit": budget},
        "max_firings_per_root": entry.max_firings_per_root,
        "material_ids": list(material_ids),
    }


def _operators(blueprints: tuple[SkillBlueprint, ...]) -> tuple[str, ...]:
    found = set()
    for blueprint in blueprints:
        for effect in blueprint.effects:
            for operator, kinds in OPERATOR_KINDS.items():
                if effect.kind in kinds:
                    found.add(operator)
                    break
            else:
                raise GameplayContractError(
                    f"Effect kind {effect.kind!r} has no Operator classification"
                )
    return tuple(sorted(found))


def _state_classes(
    ir: SkillIR, blueprints: tuple[SkillBlueprint, ...],
) -> tuple[str, ...]:
    found = {
        state_class
        for blueprint in blueprints
        for effect in blueprint.effects
        for state_class, kinds in STATE_CLASS_KINDS.items()
        if effect.kind in kinds
    }
    if any(
        spec.kind == "derived"
        for blueprint in blueprints
        for condition in (
            blueprint.condition,
            *(effect.condition for effect in blueprint.effects),
        )
        for spec in _condition_specs(condition)
    ):
        found.add("Derived")
    return tuple(name for name in STATE_CLASS_KINDS if name in found)


def _condition_specs(spec: Any):
    yield spec
    for child in spec.children:
        yield from _condition_specs(child)


def _preview(
    ir: SkillIR,
    blueprints: tuple[SkillBlueprint, ...],
    operators: tuple[str, ...],
    state_classes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "skill_id": ir.id,
        "version": ir.version,
        "lowered_ids": tuple(item.id for item in blueprints),
        "triggers": tuple(
            item.trigger for item in blueprints
        ),
        "operators": operators,
        "state_classes": state_classes,
        "selectors": ir.selectors,
        "costs": {"mana": ir.mana, "duration": ir.duration},
        "effect_kinds": tuple(sorted({
            effect.kind for blueprint in blueprints for effect in blueprint.effects
        })),
        "condition_nodes": ir.condition_nodes,
        "budget": {
            "limit": ir.budget,
            "used": float(sum(item.budget_used for item in blueprints)),
        },
    }


def _status_duration(raw: Any, path: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    raise GameplayContractError(
        f"language_gap:lifecycle.status_duration is not consumed by "
        "the accepted runtime; use per-Effect durations"
    )


def _strict(raw: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise GameplayContractError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in raw):
        raise GameplayContractError(f"{path} fields must be text")
    if set(raw) != fields:
        missing = sorted(fields - set(raw))
        unknown = sorted(set(raw) - fields)
        detail = []
        if missing:
            detail.append(f"missing={missing}")
        if unknown:
            detail.append(f"unknown={unknown}")
        raise GameplayContractError(
            f"{path} has invalid fields ({', '.join(detail)})"
        )
    return raw


def _effect_target(raw: dict[str, Any], path: str) -> dict[str, Any]:
    target = raw.get("target")
    if not isinstance(target, dict) or not isinstance(target.get("kind"), str):
        raise GameplayContractError(f"{path}.target must be a selector object")
    relation_type = target.get("relation_type")
    if relation_type is not None and not isinstance(relation_type, str):
        raise GameplayContractError(
            f"{path}.target.relation_type must be text"
        )
    return target


def _validate_effect_scalars(raw: dict[str, Any], path: str) -> None:
    if not isinstance(raw.get("kind"), str):
        raise GameplayContractError(f"{path}.kind must be text")
    target = raw.get("target")
    if (
        not isinstance(target, dict)
        or not isinstance(target.get("kind"), str)
    ):
        raise GameplayContractError(
            f"{path}.target.kind must be text"
        )


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise GameplayContractError(f"{path} is invalid")
    return value


def _display_text(value: Any, path: str, maximum: int | None) -> str:
    if not isinstance(value, str):
        raise GameplayContractError(f"{path} must be text")
    if maximum is not None and len(value) > maximum:
        raise GameplayContractError(f"{path} must be at most {maximum} characters")
    return value


def _unique_identifiers(
    value: Any, path: str, *, require_nonempty: bool = False,
) -> tuple[str, ...]:
    items = _unique_strings(value, path, identifiers=True)
    if require_nonempty and not items:
        raise GameplayContractError(f"{path} must be non-empty")
    return items


def _unique_strings(
    value: Any, path: str, *, identifiers: bool = False,
    require_nonempty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GameplayContractError(f"{path} must be a list")
    if require_nonempty and not value:
        raise GameplayContractError(f"{path} must be non-empty")
    if any(not isinstance(item, str) or not item for item in value):
        raise GameplayContractError(f"{path} must contain non-empty strings")
    if identifiers:
        for item in value:
            _identifier(item, path)
    if len(set(value)) != len(value):
        raise GameplayContractError(f"{path} contains duplicates")
    return tuple(value)


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GameplayContractError(f"{path} must be a positive integer")
    return value


def _bounded_int(value: Any, path: str, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool) or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise GameplayContractError(
            f"{path} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _number(value: Any, path: str) -> float:
    if (
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise GameplayContractError(f"{path} must be finite numeric")
    return float(value)


def _nonnegative_number(value: Any, path: str) -> float:
    number = _number(value, path)
    if number < 0:
        raise GameplayContractError(f"{path} must be non-negative")
    return number


def _positive_number(value: Any, path: str) -> float:
    number = _number(value, path)
    if number <= 0:
        raise GameplayContractError(f"{path} must be positive")
    return number
