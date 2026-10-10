"""Deterministic lowering of normalized dynamics into PMW event laws."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable

from pmw import parse_law


DYNAMICS_COMPONENT = "gm_v06_dynamics"
COUPLING_COMPONENT = "gm_v06_coupling"
CLOCK_COMPONENT = "gm_v06_clock"
TICK_EVENT = "gm.v06.dynamics.tick"
ACCUMULATE_EVENT = "gm.v06.dynamics.accumulate"
COMMIT_EVENT = "gm.v06.dynamics.commit"
WORLD_STEP_EVENT = "gm.v06.world.step"

_SLOT_RE = re.compile(r"[a-z][a-z0-9_]{0,47}")


@dataclass(frozen=True, slots=True)
class DynamicsLawProfile:
    object_id: str
    attractor_slots: tuple[str, ...] = ()
    alpha_slots: tuple[str, ...] = ()
    drive_slots: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CouplingLawProfile:
    relation_id: str
    relation_type: str
    source_object_id: str
    target_object_id: str
    conductivity_slots: tuple[str, ...] = ()


def _token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _require_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _slots(values: Iterable[str], name: str) -> tuple[str, ...]:
    result = tuple(sorted(values))
    if len(result) != len(set(result)):
        raise ValueError(f"{name} contains duplicate slot IDs")
    if any(not isinstance(item, str) or not _SLOT_RE.fullmatch(item) for item in result):
        raise ValueError(f"{name} slot IDs must match {_SLOT_RE.pattern}")
    return result


def _field_conditions(event_type: str, object_id: str, clock_id: str) -> list[dict]:
    return [
        {"event.type": {"eq": event_type}},
        {"ref": "$field.id", "eq": object_id},
        {"ref": "$clock.id", "eq": clock_id},
        {"ref": "$event.payload.step", "eq": "$clock.gm_v06_clock.next_step"},
        {"ref": "$event.time", "eq": "$clock.gm_v06_clock.next_time"},
    ]


def _clock_conditions(event_type: str, clock_id: str) -> list[dict]:
    return [
        {"event.type": {"eq": event_type}},
        {"ref": "$clock.id", "eq": clock_id},
        {"ref": "$event.payload.step", "eq": "$clock.gm_v06_clock.next_step"},
        {"ref": "$event.time", "eq": "$clock.gm_v06_clock.next_time"},
    ]


def _add(values: list[object]) -> object:
    return values[0] if len(values) == 1 else {"add": values}


def _effective_attractor(profile: DynamicsLawProfile) -> object:
    base = "$field.gm_v06_dynamics"
    numerator: list[object] = [{"mul": [f"{base}.base_weight", f"{base}.base_attractor"]}]
    denominator: list[object] = [f"{base}.base_weight"]
    for slot in profile.attractor_slots:
        numerator.append({"mul": [f"{base}.attractor_slots.{slot}.weight", f"{base}.attractor_slots.{slot}.target"]})
        denominator.append(f"{base}.attractor_slots.{slot}.weight")
    return {"div": [_add(numerator), _add(denominator)]}


def _effective_alpha(profile: DynamicsLawProfile) -> object:
    base = "$field.gm_v06_dynamics"
    values: list[object] = [f"{base}.base_alpha"]
    values.extend(f"{base}.alpha_slots.{slot}.delta" for slot in profile.alpha_slots)
    return {"clamp": [_add(values), 0.0, 1.0]}


def _effective_drive(profile: DynamicsLawProfile) -> object:
    base = "$field.gm_v06_dynamics"
    values: list[object] = [0.0]
    values.extend(f"{base}.drive_slots.{slot}.drive" for slot in profile.drive_slots)
    return {"clamp": [_add(values), {"sub": [0.0, f"{base}.drive_limit"]}, f"{base}.drive_limit"]}


def _conductivity(profile: CouplingLawProfile) -> object:
    base = "$link.gm_v06_coupling"
    values: list[object] = [f"{base}.base_conductivity"]
    values.extend(f"{base}.modifier_slots.{slot}.delta" for slot in profile.conductivity_slots)
    return {"clamp": [_add(values), 0.0, 1.0]}


def build_dynamics_laws(
    profiles: Iterable[DynamicsLawProfile],
    couplings: Iterable[CouplingLawProfile] = (),
    *,
    clock_id: str = "gm:v06:clock",
    namespace: str = "gm.v06.dynamics",
) -> tuple[dict, ...]:
    """Build and validate the complete three-phase tick law bundle."""

    clock_id = _require_id(clock_id, "clock_id")
    namespace = _require_id(namespace, "namespace")
    normalized_profiles = []
    object_ids: set[str] = set()
    for item in sorted(profiles, key=lambda item: item.object_id):
        object_id = _require_id(item.object_id, "profile.object_id")
        if object_id in object_ids:
            raise ValueError(f"duplicate dynamics profile for {object_id!r}")
        object_ids.add(object_id)
        normalized_profiles.append(DynamicsLawProfile(
            object_id,
            _slots(item.attractor_slots, "attractor_slots"),
            _slots(item.alpha_slots, "alpha_slots"),
            _slots(item.drive_slots, "drive_slots"),
        ))
    if not normalized_profiles:
        raise ValueError("at least one dynamics profile is required")

    normalized_couplings = []
    relation_ids: set[str] = set()
    for item in sorted(couplings, key=lambda item: item.relation_id):
        relation_id = _require_id(item.relation_id, "coupling.relation_id")
        if relation_id in relation_ids:
            raise ValueError(f"duplicate coupling profile for {relation_id!r}")
        relation_ids.add(relation_id)
        source = _require_id(item.source_object_id, "coupling.source_object_id")
        target = _require_id(item.target_object_id, "coupling.target_object_id")
        if source not in object_ids or target not in object_ids:
            raise ValueError(f"coupling {relation_id!r} endpoint lacks a dynamics profile")
        normalized_couplings.append(CouplingLawProfile(
            relation_id,
            _require_id(item.relation_type, "coupling.relation_type"),
            source,
            target,
            _slots(item.conductivity_slots, "conductivity_slots"),
        ))

    clock_binding = {"clock": {"kind": "entity", "requires": [CLOCK_COMPONENT]}}
    field_bindings = {
        "clock": {"kind": "entity", "requires": [CLOCK_COMPONENT]},
        "field": {"kind": "entity", "requires": [DYNAMICS_COMPONENT]},
    }
    laws: list[dict] = []
    for profile in normalized_profiles:
        tag = _token(profile.object_id)
        laws.append({
            "id": f"{namespace}.000.prepare.{tag}", "mode": "event", "priority": 100,
            "bindings": field_bindings,
            "when": {"all": _field_conditions(TICK_EVENT, profile.object_id, clock_id)},
            "effects": [
                {"op": "set", "target": "$field.gm_v06_dynamics.scratch.intrinsic", "value": 0.0},
                {"op": "set", "target": "$field.gm_v06_dynamics.scratch.coupling", "value": 0.0},
            ],
        })
    laws.append({
        "id": f"{namespace}.010.emit_accumulate", "mode": "event", "priority": 100,
        "bindings": clock_binding,
        "when": {"all": _clock_conditions(TICK_EVENT, clock_id)},
        "effects": [{"op": "emit_event", "event": {
            "type": ACCUMULATE_EVENT, "time": "$event.time", "source": clock_id,
            "payload": {"step": "$event.payload.step"},
        }}],
    })

    for profile in normalized_profiles:
        tag = _token(profile.object_id)
        attractor = _effective_attractor(profile)
        alpha = _effective_alpha(profile)
        drive = _effective_drive(profile)
        intrinsic = {"add": [
            {"mul": [alpha, {"sub": [attractor, "$field.gm_v06_dynamics.value"]}]},
            drive,
        ]}
        laws.append({
            "id": f"{namespace}.100.intrinsic.{tag}", "mode": "event", "priority": 100,
            "bindings": field_bindings,
            "when": {"all": _field_conditions(ACCUMULATE_EVENT, profile.object_id, clock_id)},
            "effects": [{"op": "delta", "target": "$field.gm_v06_dynamics.scratch.intrinsic", "value": intrinsic}],
        })

    for profile in normalized_couplings:
        tag = _token(profile.relation_id)
        bindings = {
            "clock": {"kind": "entity", "requires": [CLOCK_COMPONENT]},
            "left": {"kind": "entity", "requires": [DYNAMICS_COMPONENT]},
            "right": {"kind": "entity", "requires": [DYNAMICS_COMPONENT]},
            "link": {
                "kind": "relation", "type": profile.relation_type,
                "source": "$left", "target": "$right", "requires": [COUPLING_COMPONENT],
            },
        }
        conditions = _clock_conditions(ACCUMULATE_EVENT, clock_id) + [
            {"ref": "$left.id", "eq": profile.source_object_id},
            {"ref": "$right.id", "eq": profile.target_object_id},
            {"ref": "$link.id", "eq": profile.relation_id},
        ]
        conductivity = _conductivity(profile)
        transfer = {"mul": [conductivity, {"sub": [
            "$right.gm_v06_dynamics.value", "$left.gm_v06_dynamics.value",
        ]}]}
        laws.append({
            "id": f"{namespace}.110.coupling.{tag}", "mode": "event", "priority": 100,
            "bindings": bindings, "when": {"all": conditions},
            "effects": [
                {"op": "delta", "target": "$left.gm_v06_dynamics.scratch.coupling", "value": transfer},
                {"op": "delta", "target": "$right.gm_v06_dynamics.scratch.coupling", "value": {"sub": [0.0, transfer]}},
            ],
        })
    laws.append({
        "id": f"{namespace}.190.emit_commit", "mode": "event", "priority": 100,
        "bindings": clock_binding,
        "when": {"all": _clock_conditions(ACCUMULATE_EVENT, clock_id)},
        "effects": [{"op": "emit_event", "event": {
            "type": COMMIT_EVENT, "time": "$event.time", "source": clock_id,
            "payload": {"step": "$event.payload.step"},
        }}],
    })

    for profile in normalized_profiles:
        tag = _token(profile.object_id)
        attractor = _effective_attractor(profile)
        alpha = _effective_alpha(profile)
        drive = _effective_drive(profile)
        raw = {"add": [
            "$field.gm_v06_dynamics.value",
            "$field.gm_v06_dynamics.scratch.intrinsic",
            "$field.gm_v06_dynamics.scratch.coupling",
        ]}
        bounded = {"clamp": [raw, 0.0, 1.0]}
        laws.append({
            "id": f"{namespace}.200.commit.{tag}", "mode": "event", "priority": 100,
            "bindings": field_bindings,
            "when": {"all": _field_conditions(COMMIT_EVENT, profile.object_id, clock_id)},
            "effects": [
                {"op": "set", "target": "$field.gm_v06_dynamics.diagnostics.effective_attractor", "value": attractor},
                {"op": "set", "target": "$field.gm_v06_dynamics.diagnostics.effective_alpha", "value": alpha},
                {"op": "set", "target": "$field.gm_v06_dynamics.diagnostics.effective_drive", "value": drive},
                {"op": "set", "target": "$field.gm_v06_dynamics.diagnostics.intrinsic", "value": "$field.gm_v06_dynamics.scratch.intrinsic"},
                {"op": "set", "target": "$field.gm_v06_dynamics.diagnostics.coupling", "value": "$field.gm_v06_dynamics.scratch.coupling"},
                {"op": "set", "target": "$field.gm_v06_dynamics.diagnostics.unclamped", "value": raw},
                {"op": "set", "target": "$field.gm_v06_dynamics.diagnostics.clamp_loss", "value": {"sub": [bounded, raw]}},
                {"op": "set", "target": "$field.gm_v06_dynamics.value", "value": bounded},
            ],
        })
    laws.append({
        "id": f"{namespace}.290.complete", "mode": "event", "priority": 100,
        "bindings": clock_binding,
        "when": {"all": _clock_conditions(COMMIT_EVENT, clock_id)},
        "effects": [
            {"op": "set", "target": "$clock.gm_v06_clock.last_completed_step", "value": "$event.payload.step"},
            {"op": "delta", "target": "$clock.gm_v06_clock.next_step", "value": 1},
            {"op": "delta", "target": "$clock.gm_v06_clock.next_time", "value": 1.0},
        ],
    })

    result = tuple(sorted(laws, key=lambda law: law["id"]))
    for law in result:
        parse_law(law)
    return result
