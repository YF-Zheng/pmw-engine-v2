"""Bounded, data-driven Stock conversion Processes for Gameplay v0.4.

This module is a sidecar over the existing Gameplay runtime.  It does not
introduce a second clock or tick loop: conversion is lowered to event Laws on
``WORLD_TICK_EVENT`` and every authoritative write is committed by PMW.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from pmw import Entity, Event, parse_law

from .contracts import GameplayContractError
from .dynamics import CLOCK_COMPONENT, WORLD_TICK_EVENT
from .runtime import GameplaySession
from .transactions import publish_gameplay_session, stage_gameplay_session


STOCK_COMPONENT = "stock"
PROCESS_COMPONENT = "pmw_sandbox_process"
PROCESS_PROTOCOL = "pmw-sandbox-process-v0.1"
PROCESS_START_EVENT = "pmw.v04.sandbox.process.start"
PROCESS_MODIFY_EVENT = "pmw.v04.sandbox.process.modify"
PROCESS_PAUSE_EVENT = "pmw.v04.sandbox.process.pause"
PROCESS_RESUME_EVENT = "pmw.v04.sandbox.process.resume"
PROCESS_EXPIRE_EVENT = "pmw.v04.sandbox.process.expire"

MAX_RATE = 1_000_000.0
MAX_COEFFICIENT = 1_000_000.0
MAX_STOCK_VALUE = 1_000_000_000_000.0
MAX_DURATION_TICKS = 1_000_000
MAX_INSTANCES = 1024
_PROCESS_STATES = {"stopped", "running", "paused"}
_FAILURE_KINDS = {None, "insufficient_input"}

_PORT_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
_ENTITY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_UNIT = re.compile(r"[A-Za-z][A-Za-z0-9_.:/-]{0,31}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class StockRef:
    """A trusted reference to one entity's ``components.stock`` component."""

    entity_id: str

    def __post_init__(self) -> None:
        _entity_id(self.entity_id, "StockRef.entity_id")


@dataclass(frozen=True, slots=True)
class ConversionPort:
    """One typed coefficient in a Process template."""

    name: str
    coefficient: float
    unit: str

    def __post_init__(self) -> None:
        _port_name(self.name, "ConversionPort.name")
        _positive(self.coefficient, f"ConversionPort({self.name}).coefficient",
                  maximum=MAX_COEFFICIENT)
        _unit(self.unit, f"ConversionPort({self.name}).unit")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "coefficient": self.coefficient, "unit": self.unit}


@dataclass(frozen=True, slots=True)
class StockBinding:
    """Bind a template port name to one trusted Stock entity."""

    port: str
    stock: StockRef

    def __post_init__(self) -> None:
        _port_name(self.port, "StockBinding.port")
        if not isinstance(self.stock, StockRef):
            raise GameplayContractError("StockBinding.stock must be a StockRef")

    def to_dict(self) -> dict[str, Any]:
        return {"port": self.port, "stock": self.stock.entity_id}


@dataclass(frozen=True, slots=True)
class ProcessTemplate:
    """A preallocated trusted conversion recipe.

    The template is data only.  Coefficients, rate, and duration are validated
    here, and the compiler below never evaluates a template-supplied string.
    """

    id: str
    inputs: tuple[ConversionPort, ...]
    outputs: tuple[ConversionPort, ...]
    rate: float
    duration_ticks: int
    max_rate: float
    max_duration_ticks: int

    def __post_init__(self) -> None:
        _entity_id(self.id, "ProcessTemplate.id")
        _ports(self.inputs, "ProcessTemplate.inputs")
        _ports(self.outputs, "ProcessTemplate.outputs")
        names = [item.name for item in (*self.inputs, *self.outputs)]
        if len(names) != len(set(names)):
            raise GameplayContractError("Process port names must be unique across inputs and outputs")
        if not self.inputs or not self.outputs:
            raise GameplayContractError("Process templates require at least one input and output")
        _positive(self.rate, "ProcessTemplate.rate", maximum=MAX_RATE)
        _positive(self.max_rate, "ProcessTemplate.max_rate", maximum=MAX_RATE)
        if self.rate > self.max_rate:
            raise GameplayContractError("ProcessTemplate.rate exceeds max_rate")
        _duration(self.duration_ticks, "ProcessTemplate.duration_ticks",
                  maximum=MAX_DURATION_TICKS)
        _duration(self.max_duration_ticks, "ProcessTemplate.max_duration_ticks",
                  maximum=MAX_DURATION_TICKS)
        if self.duration_ticks > self.max_duration_ticks:
            raise GameplayContractError("ProcessTemplate.duration_ticks exceeds max_duration_ticks")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": PROCESS_PROTOCOL,
            "kind": "process_template",
            "id": self.id,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "rate": self.rate,
            "duration_ticks": self.duration_ticks,
            "max_rate": self.max_rate,
            "max_duration_ticks": self.max_duration_ticks,
        }


@dataclass(frozen=True, slots=True)
class ProcessProfile:
    """One instantiated, trusted binding of a Process template.

    Profiles are preallocated content in this increment.  Dynamic catalog edits
    are deliberately outside the bridge contract.
    """

    id: str
    template: ProcessTemplate
    process_entity_id: str
    owner: str
    inputs: tuple[StockBinding, ...]
    outputs: tuple[StockBinding, ...]
    rate: float | None = None
    duration_ticks: int | None = None
    profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        _entity_id(self.id, "ProcessProfile.id")
        if not isinstance(self.template, ProcessTemplate):
            raise GameplayContractError("ProcessProfile.template must be a ProcessTemplate")
        _entity_id(self.process_entity_id, "ProcessProfile.process_entity_id")
        _entity_id(self.owner, "ProcessProfile.owner")
        rate = self.template.rate if self.rate is None else self.rate
        duration = self.template.duration_ticks if self.duration_ticks is None else self.duration_ticks
        _positive(rate, "ProcessProfile.rate", maximum=self.template.max_rate)
        _duration(duration, "ProcessProfile.duration_ticks",
                  maximum=self.template.max_duration_ticks)
        _bindings(self.inputs, self.template.inputs, "ProcessProfile.inputs")
        _bindings(self.outputs, self.template.outputs, "ProcessProfile.outputs")
        refs = [item.stock.entity_id for item in (*self.inputs, *self.outputs)]
        if len(refs) != len(set(refs)):
            raise GameplayContractError("Process inputs and outputs cannot reuse or overlap a Stock entity")
        object.__setattr__(self, "rate", float(rate))
        object.__setattr__(self, "duration_ticks", duration)
        document = {
            "protocol": PROCESS_PROTOCOL,
            "kind": "process_profile",
            "id": self.id,
            "template": self.template.to_dict(),
            "process_entity_id": self.process_entity_id,
            "owner": self.owner,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "rate": self.rate,
            "duration_ticks": self.duration_ticks,
        }
        canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
        object.__setattr__(self, "profile_hash", hashlib.sha256(canonical.encode("utf-8")).hexdigest())

    @property
    def input_ports(self) -> tuple[tuple[ConversionPort, StockRef], ...]:
        by_name = {item.port: item.stock for item in self.inputs}
        return tuple((port, by_name[port.name]) for port in self.template.inputs)

    @property
    def output_ports(self) -> tuple[tuple[ConversionPort, StockRef], ...]:
        by_name = {item.port: item.stock for item in self.outputs}
        return tuple((port, by_name[port.name]) for port in self.template.outputs)

    @property
    def stock_ids(self) -> frozenset[str]:
        return frozenset(item.stock.entity_id for item in (*self.inputs, *self.outputs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": PROCESS_PROTOCOL,
            "kind": "process_profile",
            "id": self.id,
            "template_id": self.template.id,
            "profile_hash": self.profile_hash,
            "process_entity_id": self.process_entity_id,
            "owner": self.owner,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "rate": self.rate,
            "duration_ticks": self.duration_ticks,
        }


@dataclass(frozen=True, slots=True)
class ProcessLimits:
    """Independent bounds for registered instances and concurrently active ones."""

    max_instances: int = 16
    max_active: int = 8

    def __post_init__(self) -> None:
        _bounded_int(self.max_instances, "ProcessLimits.max_instances", 1, MAX_INSTANCES)
        _bounded_int(self.max_active, "ProcessLimits.max_active", 1, MAX_INSTANCES)
        if self.max_active > self.max_instances:
            raise GameplayContractError("ProcessLimits.max_active cannot exceed max_instances")


@dataclass(slots=True)
class ProcessController:
    """Trusted action boundary for a finite set of preallocated profiles."""

    profiles: tuple[ProcessProfile, ...]
    limits: ProcessLimits = field(default_factory=ProcessLimits)
    clock_id: str = "pmw:v04:clock"
    external_stock_writers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        profiles = tuple(self.profiles)
        if any(not isinstance(item, ProcessProfile) for item in profiles):
            raise GameplayContractError("ProcessController.profiles must contain ProcessProfile objects")
        if len(profiles) > self.limits.max_instances:
            raise GameplayContractError("registered Process instances exceed max_instances")
        ids = [item.id for item in profiles]
        entities = [item.process_entity_id for item in profiles]
        if len(ids) != len(set(ids)) or len(entities) != len(set(entities)):
            raise GameplayContractError("Process profile and entity IDs must be unique")
        _entity_id(self.clock_id, "ProcessController.clock_id")
        writers = dict(self.external_stock_writers)
        for stock_id, writer in writers.items():
            _entity_id(stock_id, "external_stock_writers.stock")
            _entity_id(writer, "external_stock_writers.writer")
        self.profiles = tuple(sorted(profiles, key=lambda item: item.id))
        self.external_stock_writers = writers

    @property
    def laws(self) -> tuple[dict[str, Any], ...]:
        return build_process_laws(self.profiles, clock_id=self.clock_id)

    def instantiate(self, process_id: str) -> Entity:
        return instantiate_process(self._profile(process_id))

    def prepare_start(
        self, session: GameplaySession, process_id: str, *, owner: str
    ) -> ProcessProfile:
        """Validate a start without changing controller, session, or scheduler state."""
        profile = self._profile(process_id)
        _preflight(self, session, profile, owner=owner, states={"stopped"}, require_inputs=True)
        _assert_active_limits(self, session, profile, activation=True)
        _assert_writer_exclusivity(self, session, profile)
        return profile

    def start(self, session: GameplaySession, process_id: str, *, owner: str) -> Any:
        return _start_process(self, session, process_id, owner=owner)

    def modify(
        self,
        session: GameplaySession,
        process_id: str,
        *,
        owner: str,
        rate: float | None = None,
        remaining_ticks: int | None = None,
    ) -> Any:
        return _modify_process(
            self, session, process_id, owner=owner, rate=rate, remaining_ticks=remaining_ticks
        )

    def pause(self, session: GameplaySession, process_id: str, *, owner: str) -> Any:
        return _pause_process(self, session, process_id, owner=owner)

    def resume(self, session: GameplaySession, process_id: str, *, owner: str) -> Any:
        return _resume_process(self, session, process_id, owner=owner)

    def _profile(self, process_id: str) -> ProcessProfile:
        if not isinstance(process_id, str):
            raise GameplayContractError("Process ID must be a string")
        matches = [item for item in self.profiles if item.id == process_id]
        if len(matches) != 1:
            raise GameplayContractError("unknown Process profile")
        return matches[0]


def stock_entity(
    entity_id: str, *, amount: float, capacity: float, unit: str
) -> Entity:
    """Create a detached Stock entity using the bridge's exact Stock shape."""
    _entity_id(entity_id, "stock_entity.entity_id")
    component = stock_component(amount=amount, capacity=capacity, unit=unit)
    return Entity(entity_id, "stock", components={STOCK_COMPONENT: component})


def stock_component(*, amount: float, capacity: float, unit: str) -> dict[str, Any]:
    amount = _non_negative(amount, "stock.amount")
    capacity = _non_negative(capacity, "stock.capacity")
    _unit(unit, "stock.unit")
    if amount > capacity:
        raise GameplayContractError("stock.amount cannot exceed stock.capacity")
    return {"amount": amount, "capacity": capacity, "unit": unit}


def instantiate_process(profile: ProcessProfile) -> Entity:
    """Create a detached stopped Process entity from a trusted profile."""
    if not isinstance(profile, ProcessProfile):
        raise GameplayContractError("instantiate_process requires a ProcessProfile")
    component = {
        "profile_id": profile.id,
        "profile_hash": profile.profile_hash,
        "template_id": profile.template.id,
        "owner": profile.owner,
        "state": "stopped",
        "rate": profile.rate,
        "max_rate": profile.template.max_rate,
        "duration_ticks": profile.duration_ticks,
        "remaining_ticks": profile.duration_ticks,
        "elapsed_ticks": 0,
        "progress": 0.0,
        "started_at": None,
        "hard_deadline": None,
        "expiry_handle": None,
        "last_step": -1,
        "last_failure": None,
    }
    return Entity(profile.process_entity_id, "pmw_sandbox_process",
                  components={PROCESS_COMPONENT: component})


def build_process_laws(
    profiles: Iterable[ProcessProfile], *, clock_id: str = "pmw:v04:clock"
) -> tuple[dict[str, Any], ...]:
    """Lower finite trusted profiles into validated PMW event Laws.

    All dynamic values are references to stock/process state or to a bounded
    trusted event payload.  Template or profile strings are never evaluated.
    """
    items = tuple(profiles)
    if any(not isinstance(item, ProcessProfile) for item in items):
        raise GameplayContractError("build_process_laws requires ProcessProfile objects")
    if len(items) > MAX_INSTANCES:
        raise GameplayContractError("Process law build exceeds the bounded instance limit")
    _entity_id(clock_id, "clock_id")
    if len({item.id for item in items}) != len(items):
        raise GameplayContractError("duplicate Process profile ID")
    if len({item.process_entity_id for item in items}) != len(items):
        raise GameplayContractError("duplicate Process entity ID")
    normalized = tuple(sorted(items, key=lambda item: item.id))
    conflicts: dict[str, tuple[ProcessProfile, ...]] = {}
    for profile in normalized:
        peers = tuple(
            other for other in normalized
            if other.id != profile.id and profile.stock_ids & other.stock_ids
        )
        if peers:
            conflicts[profile.id] = peers
    laws: list[dict[str, Any]] = []
    for profile in normalized:
        laws.extend(_profile_laws(profile, clock_id, conflicts.get(profile.id, ())))
    result = tuple(sorted(laws, key=lambda item: item["id"]))
    for law in result:
        parse_law(law)
    return result


def _profile_laws(
    profile: ProcessProfile,
    clock_id: str,
    conflicting_profiles: tuple[ProcessProfile, ...] = (),
) -> list[dict[str, Any]]:
    name = profile.id
    subject = f"$subject.{PROCESS_COMPONENT}"
    expiry_id = _expiry_id(name)
    base_bindings: dict[str, Any] = {
        "subject": {"kind": "entity", "requires": [PROCESS_COMPONENT]},
        "clock": {"kind": "entity", "requires": [CLOCK_COMPONENT]},
    }
    for index, (_, ref) in enumerate(profile.input_ports):
        base_bindings[f"input_{index}"] = {"kind": "entity", "requires": [STOCK_COMPONENT]}
    for index, (_, ref) in enumerate(profile.output_ports):
        base_bindings[f"output_{index}"] = {"kind": "entity", "requires": [STOCK_COMPONENT]}
    bindings = dict(base_bindings)
    for index, peer in enumerate(conflicting_profiles):
        bindings[f"conflict_{index}"] = {"kind": "entity", "requires": [PROCESS_COMPONENT]}

    identity = [
        {"ref": "$subject.id", "eq": profile.process_entity_id},
        {"ref": f"{subject}.profile_id", "eq": profile.id},
        {"ref": f"{subject}.profile_hash", "eq": profile.profile_hash},
        {"ref": f"{subject}.owner", "eq": profile.owner},
    ]
    stock_identity: list[dict[str, Any]] = []
    for index, (port, ref) in enumerate(profile.input_ports):
        stock_identity.extend([
            {"ref": f"$input_{index}.id", "eq": ref.entity_id},
            {"ref": f"$input_{index}.{STOCK_COMPONENT}.unit", "eq": port.unit},
        ])
    for index, (port, ref) in enumerate(profile.output_ports):
        stock_identity.extend([
            {"ref": f"$output_{index}.id", "eq": ref.entity_id},
            {"ref": f"$output_{index}.{STOCK_COMPONENT}.unit", "eq": port.unit},
        ])
    authority = [
        {"ref": "$event.source", "eq": profile.owner},
        {"ref": "$event.payload.profile_hash", "eq": profile.profile_hash},
        *identity,
        *stock_identity,
    ]
    # World Tick events carry neither a process target nor an owner payload.
    # Tick-time authority is therefore the bound trusted component identity,
    # the exact registered Stock endpoints, and the clock phase below.
    tick_authority = [*identity, *stock_identity]
    conflict_states: list[dict[str, Any]] = []
    for index, peer in enumerate(conflicting_profiles):
        peer_subject = f"$conflict_{index}.{PROCESS_COMPONENT}"
        conflict_states.extend([
            {"ref": f"$conflict_{index}.id", "eq": peer.process_entity_id},
            {"ref": f"{peer_subject}.profile_id", "eq": peer.id},
            {"ref": f"{peer_subject}.profile_hash", "eq": peer.profile_hash},
        ])
    tick_common = [
        {"event.type": {"eq": WORLD_TICK_EVENT}},
        {"ref": "$clock.id", "eq": clock_id},
        {"ref": "$event.payload.step", "eq": "$clock.pmw_gameplay_clock.next_step"},
        {"ref": "$event.time", "eq": "$clock.pmw_gameplay_clock.next_time"},
        {"ref": f"{subject}.state", "eq": "running"},
        {"ref": f"{subject}.last_step", "lt": "$event.payload.step"},
        *tick_authority,
        *conflict_states,
    ]
    valid_rate = [
        {"ref": f"{subject}.rate", "gt": 0},
        {"ref": f"{subject}.rate", "lte": profile.template.max_rate},
    ]
    valid_stock = _stock_domain_conditions(profile)

    laws: list[dict[str, Any]] = []
    start_payload = {
        "expiry_event": {
            "id": expiry_id,
            "type": PROCESS_EXPIRE_EVENT,
            "time": {"add": ["$event.time", profile.duration_ticks]},
            "source": profile.owner,
            "target": profile.process_entity_id,
            "payload": {"profile_id": profile.id, "profile_hash": profile.profile_hash},
        }
    }
    laws.append({
        "id": f"pmw.v04.sandbox.process.{name}.start",
        "mode": "event",
        "priority": 100,
        "bindings": base_bindings,
        "when": {"all": [
            {"event.type": {"eq": PROCESS_START_EVENT}},
            *authority,
            {"ref": "$subject.id", "eq": "$event.target"},
            {"ref": f"{subject}.state", "eq": "stopped"},
            {"ref": "$event.time", "eq": "$clock.pmw_gameplay_clock.last_completed_step"},
        ]},
        "effects": [
            {"op": "set", "target": f"{subject}.state", "value": "running"},
            {"op": "set", "target": f"{subject}.rate", "value": profile.rate},
            {"op": "set", "target": f"{subject}.duration_ticks", "value": profile.duration_ticks},
            {"op": "set", "target": f"{subject}.remaining_ticks", "value": profile.duration_ticks},
            {"op": "set", "target": f"{subject}.elapsed_ticks", "value": 0},
            {"op": "set", "target": f"{subject}.progress", "value": 0.0},
            {"op": "set", "target": f"{subject}.started_at", "value": "$event.time"},
            {"op": "set", "target": f"{subject}.hard_deadline", "value": {
                "add": ["$event.time", profile.template.max_duration_ticks]
            }},
            {"op": "set", "target": f"{subject}.expiry_handle", "value": expiry_id},
            {"op": "set", "target": f"{subject}.last_step", "value": "$clock.pmw_gameplay_clock.last_completed_step"},
            {"op": "set", "target": f"{subject}.last_failure", "value": None},
            {"op": "schedule_event", "event": start_payload["expiry_event"]},
        ],
    })

    quantity = _quantity_expression(profile, subject)
    conversion_conditions = [
        *tick_common,
        *valid_rate,
        *valid_stock,
        *[
            {"ref": f"$conflict_{index}.{PROCESS_COMPONENT}.state", "neq": "running"}
            for index in range(len(conflicting_profiles))
        ],
        {"ref": f"{subject}.remaining_ticks", "gt": 0},
        *[{"ref": f"$input_{i}.{STOCK_COMPONENT}.amount", "gt": 0}
          for i in range(len(profile.input_ports))],
        *[{
            "ref": f"$output_{i}.{STOCK_COMPONENT}.capacity",
            "gt": f"$output_{i}.{STOCK_COMPONENT}.amount",
        } for i in range(len(profile.output_ports))],
    ]
    conversion_effects: list[dict[str, Any]] = []
    for index, (port, _) in enumerate(profile.input_ports):
        path = f"$input_{index}.{STOCK_COMPONENT}.amount"
        conversion_effects.append({
            "op": "set",
            "target": path,
            "value": {"max": [0.0, {
                "sub": [path, {"mul": [quantity, port.coefficient]}]
            }]},
        })
    for index, (port, _) in enumerate(profile.output_ports):
        path = f"$output_{index}.{STOCK_COMPONENT}.amount"
        conversion_effects.append({
            "op": "set",
            "target": path,
            "value": {"min": [
                f"$output_{index}.{STOCK_COMPONENT}.capacity",
                {"add": [path, {"mul": [quantity, port.coefficient]}]},
            ]},
        })
    conversion_effects.extend(_advance_time_effects(subject))
    laws.append({
        "id": f"pmw.v04.sandbox.process.{name}.convert",
        "mode": "event",
        "priority": 100,
        "bindings": bindings,
        "when": {"all": conversion_conditions},
        "effects": conversion_effects,
    })

    shortage_conditions = [
        *tick_common,
        *valid_stock,
        {"any": [
            {"ref": f"$input_{i}.{STOCK_COMPONENT}.amount", "lte": 0}
            for i in range(len(profile.input_ports))
        ]},
        {"ref": f"{subject}.expiry_handle", "neq": None},
    ]
    laws.append({
        "id": f"pmw.v04.sandbox.process.{name}.insufficient_input",
        "mode": "event",
        "priority": 100,
        "bindings": bindings,
        "when": {"all": shortage_conditions},
        "effects": [
            {"op": "set", "target": f"{subject}.state", "value": "paused"},
            {"op": "set", "target": f"{subject}.last_failure", "value": "insufficient_input"},
            {"op": "set", "target": f"{subject}.last_step", "value": "$event.payload.step"},
            {"op": "set", "target": f"{subject}.expiry_handle", "value": None},
            {"op": "cancel_scheduled", "value": f"{subject}.expiry_handle"},
        ],
    })

    saturated_conditions = [
        *tick_common,
        *valid_rate,
        *valid_stock,
        {"ref": f"{subject}.remaining_ticks", "gt": 0},
        *[{"ref": f"$input_{i}.{STOCK_COMPONENT}.amount", "gt": 0}
          for i in range(len(profile.input_ports))],
        {"any": [{
            "ref": f"$output_{i}.{STOCK_COMPONENT}.capacity",
            "lte": f"$output_{i}.{STOCK_COMPONENT}.amount",
        } for i in range(len(profile.output_ports))]},
    ]
    laws.append({
        "id": f"pmw.v04.sandbox.process.{name}.saturated",
        "mode": "event",
        "priority": 100,
        "bindings": bindings,
        "when": {"all": saturated_conditions},
        # Saturation is not conversion success: mark the step to prevent a
        # duplicate execution, but do not advance progress without stock deltas.
        "effects": [
            {"op": "set", "target": f"{subject}.last_step", "value": "$event.payload.step"},
        ],
    })

    before = ["rate", "duration_ticks", "remaining_ticks"]
    modify_before = [
        {"ref": f"$event.payload.before_{key}", "eq": f"{subject}.{key}"}
        for key in before
    ]
    modify_common = [
        {"event.type": {"eq": PROCESS_MODIFY_EVENT}},
        *authority,
        {"ref": f"{subject}.state", "eq": "running"},
        {"ref": "$event.time", "eq": "$clock.pmw_gameplay_clock.last_completed_step"},
        {"ref": "$event.payload.expiry_handle", "eq": f"{subject}.expiry_handle"},
        *modify_before,
        {"ref": "$event.payload.after_rate", "gt": 0},
        {"ref": "$event.payload.after_rate", "lte": profile.template.max_rate},
        {"ref": "$event.payload.after_remaining", "gt": 0},
        {"ref": "$event.payload.after_duration", "lte": profile.template.max_duration_ticks},
        {"ref": "$event.payload.deadline", "gt": "$event.time"},
        {"ref": "$event.payload.deadline", "lte": f"{subject}.hard_deadline"},
    ]
    laws.append({
        "id": f"pmw.v04.sandbox.process.{name}.modify",
        "mode": "event",
        "priority": 100,
        "bindings": base_bindings,
        "when": {"all": modify_common},
        "effects": [
            {"op": "set", "target": f"{subject}.rate", "value": "$event.payload.after_rate"},
            {"op": "set", "target": f"{subject}.duration_ticks", "value": "$event.payload.after_duration"},
            {"op": "set", "target": f"{subject}.remaining_ticks", "value": "$event.payload.after_remaining"},
            {"op": "set", "target": f"{subject}.progress", "value": "$event.payload.after_progress"},
            {"op": "set", "target": f"{subject}.last_failure", "value": None},
            {"op": "reschedule_scheduled", "value": {
                "id": "$event.payload.expiry_handle", "time": "$event.payload.deadline"
            }},
        ],
    })

    pause_before = [
        {"ref": f"$event.payload.before_{key}", "eq": f"{subject}.{key}"}
        for key in before
    ]
    pause_common = [
        {"event.type": {"eq": PROCESS_PAUSE_EVENT}},
        *authority,
        {"ref": f"{subject}.state", "eq": "running"},
        {"ref": "$event.time", "eq": "$clock.pmw_gameplay_clock.last_completed_step"},
        {"ref": "$event.payload.expiry_handle", "eq": f"{subject}.expiry_handle"},
        *pause_before,
        {"ref": "$event.payload.after_remaining", "gt": 0},
        {"ref": "$event.payload.after_duration", "lte": profile.template.max_duration_ticks},
    ]
    laws.append({
        "id": f"pmw.v04.sandbox.process.{name}.pause",
        "mode": "event",
        "priority": 100,
        "bindings": base_bindings,
        "when": {"all": pause_common},
        "effects": [
            {"op": "set", "target": f"{subject}.state", "value": "paused"},
            {"op": "set", "target": f"{subject}.duration_ticks", "value": "$event.payload.after_duration"},
            {"op": "set", "target": f"{subject}.remaining_ticks", "value": "$event.payload.after_remaining"},
            {"op": "set", "target": f"{subject}.progress", "value": "$event.payload.after_progress"},
            {"op": "set", "target": f"{subject}.expiry_handle", "value": None},
            {"op": "set", "target": f"{subject}.last_failure", "value": None},
            {"op": "cancel_scheduled", "value": "$event.payload.expiry_handle"},
        ],
    })

    resume_common = [
        {"event.type": {"eq": PROCESS_RESUME_EVENT}},
        *authority,
        {"ref": f"{subject}.state", "eq": "paused"},
        {"ref": "$event.time", "eq": "$clock.pmw_gameplay_clock.last_completed_step"},
        {"ref": "$event.payload.before_remaining", "eq": f"{subject}.remaining_ticks"},
        {"ref": "$event.payload.before_duration", "eq": f"{subject}.duration_ticks"},
        {"ref": "$event.payload.after_remaining", "gt": 0},
        {"ref": "$event.payload.after_duration", "lte": profile.template.max_duration_ticks},
        {"ref": "$event.payload.deadline", "gt": "$event.time"},
        {"ref": "$event.payload.deadline", "lte": f"{subject}.hard_deadline"},
    ]
    laws.append({
        "id": f"pmw.v04.sandbox.process.{name}.resume",
        "mode": "event",
        "priority": 100,
        "bindings": base_bindings,
        "when": {"all": resume_common},
        "effects": [
            {"op": "set", "target": f"{subject}.state", "value": "running"},
            {"op": "set", "target": f"{subject}.duration_ticks", "value": "$event.payload.after_duration"},
            {"op": "set", "target": f"{subject}.remaining_ticks", "value": "$event.payload.after_remaining"},
            {"op": "set", "target": f"{subject}.progress", "value": "$event.payload.after_progress"},
            {"op": "set", "target": f"{subject}.expiry_handle", "value": expiry_id},
            {"op": "set", "target": f"{subject}.last_step", "value": "$clock.pmw_gameplay_clock.last_completed_step"},
            {"op": "set", "target": f"{subject}.last_failure", "value": None},
            {"op": "schedule_event", "event": {
                "id": expiry_id,
                "type": PROCESS_EXPIRE_EVENT,
                "time": "$event.payload.deadline",
                "source": profile.owner,
                "target": profile.process_entity_id,
                "payload": {"profile_id": profile.id, "profile_hash": profile.profile_hash},
            }},
        ],
    })

    # Expiry owns only the process component and its scheduled handle.  It
    # deliberately does not bind Stock entities: deleting or corrupting an
    # endpoint must not strand the process in a running state forever.
    expiry_bindings = {"subject": {"kind": "entity", "requires": [PROCESS_COMPONENT]}}
    laws.append({
        "id": f"pmw.v04.sandbox.process.{name}.expire",
        "mode": "event",
        "priority": 100,
        "bindings": expiry_bindings,
        "when": {"all": [
            {"event.type": {"eq": PROCESS_EXPIRE_EVENT}},
            {"ref": "$event.id", "eq": f"{subject}.expiry_handle"},
            {"ref": "$subject.id", "eq": profile.process_entity_id},
            {"ref": "$subject.id", "eq": "$event.target"},
            {"ref": f"{subject}.profile_id", "eq": profile.id},
            {"ref": f"{subject}.profile_hash", "eq": profile.profile_hash},
            {"ref": f"{subject}.owner", "eq": profile.owner},
            {"ref": "$event.source", "eq": profile.owner},
            {"ref": "$event.payload.profile_hash", "eq": profile.profile_hash},
            {"ref": f"{subject}.state", "eq": "running"},
        ]},
        "effects": [
            {"op": "set", "target": f"{subject}.state", "value": "stopped"},
            {"op": "set", "target": f"{subject}.remaining_ticks", "value": 0},
            {"op": "set", "target": f"{subject}.progress", "value": 1.0},
            {"op": "set", "target": f"{subject}.expiry_handle", "value": None},
            {"op": "set", "target": f"{subject}.last_failure", "value": None},
        ],
    })
    return laws


def _quantity_expression(profile: ProcessProfile, subject: str) -> dict[str, Any]:
    terms: list[Any] = [f"{subject}.rate"]
    for index, (port, _) in enumerate(profile.input_ports):
        terms.append({"div": [f"$input_{index}.{STOCK_COMPONENT}.amount", port.coefficient]})
    for index, (port, _) in enumerate(profile.output_ports):
        terms.append({"div": [_free_capacity(f"$output_{index}"), port.coefficient]})
    return {"min": terms}


def _stock_domain_conditions(profile: ProcessProfile) -> list[dict[str, Any]]:
    """Keep forged saved Stock out of arithmetic until it is in-domain."""
    result: list[dict[str, Any]] = []
    for index in range(len(profile.input_ports)):
        path = f"$input_{index}.{STOCK_COMPONENT}"
        result.extend([
            {"ref": f"{path}.amount", "gte": 0},
            {"ref": f"{path}.amount", "lte": MAX_STOCK_VALUE},
            {"ref": f"{path}.capacity", "gte": 0},
            {"ref": f"{path}.capacity", "lte": MAX_STOCK_VALUE},
            {"ref": f"{path}.capacity", "gte": f"{path}.amount"},
        ])
    for index in range(len(profile.output_ports)):
        path = f"$output_{index}.{STOCK_COMPONENT}"
        result.extend([
            {"ref": f"{path}.amount", "gte": 0},
            {"ref": f"{path}.amount", "lte": MAX_STOCK_VALUE},
            {"ref": f"{path}.capacity", "gte": 0},
            {"ref": f"{path}.capacity", "lte": MAX_STOCK_VALUE},
            {"ref": f"{path}.capacity", "gte": f"{path}.amount"},
        ])
    return result


def _finite_numeric_guard(path: str, maximum: float) -> list[dict[str, Any]]:
    """Reject booleans without applying tolerance to conversion arithmetic.

    The DSL compares like Python.  A compact value presence window is therefore
    used only as a type discriminator; exact conversion expectations and their
    test tolerance remain unchanged.
    """
    present = max(maximum * 1e-12, 5e-324)
    return [
        {"any": [
            {"ref": path, "gt": 0},
            {"ref": path, "eq": 0},
            {"ref": path, "lt": 0},
        ]},
        {"any": [
            {"ref": path, "gt": present},
            {"ref": path, "eq": 0},
            {"ref": path, "lt": -present},
        ]},
    ]


def _advance_time_effects(subject: str) -> list[dict[str, Any]]:
    return [
        {"op": "set", "target": f"{subject}.remaining_ticks", "value": {
            "sub": [f"{subject}.remaining_ticks", 1]
        }},
        {"op": "set", "target": f"{subject}.elapsed_ticks", "value": {
            "add": [f"{subject}.elapsed_ticks", 1]
        }},
        {"op": "set", "target": f"{subject}.progress", "value": {
            "min": [1.0, {"div": [
                {"add": [f"{subject}.elapsed_ticks", 1]},
                f"{subject}.duration_ticks",
            ]}]
        }},
        {"op": "set", "target": f"{subject}.last_step", "value": "$event.payload.step"},
    ]


def _start_process(
    controller: ProcessController, session: GameplaySession, process_id: str, *, owner: str
) -> Any:
    staged = stage_gameplay_session(session)
    profile = controller.prepare_start(staged, process_id, owner=owner)
    result = staged.runtime.run_event(Event(
        f"pmw:v04:sandbox.process.start:{profile.id}",
        PROCESS_START_EVENT,
        staged.state.sim_time,
        owner,
        profile.process_entity_id,
        {"profile_id": profile.id, "profile_hash": profile.profile_hash},
    ))
    if not result.changed:
        raise GameplayContractError("Process start did not match its trusted Law")
    publish_gameplay_session(session, staged)
    return result


def _modify_process(
    controller: ProcessController,
    session: GameplaySession,
    process_id: str,
    *,
    owner: str,
    rate: float | None,
    remaining_ticks: int | None,
) -> Any:
    profile = controller._profile(process_id)
    if rate is None and remaining_ticks is None:
        raise GameplayContractError("Process modification requires rate or remaining_ticks")
    staged = stage_gameplay_session(session)
    component = _preflight(
        controller, staged, profile, owner=owner, states={"running"}, require_inputs=True
    )
    _assert_writer_exclusivity(controller, staged, profile)
    now = _boundary_time(staged, controller.clock_id)
    hard_deadline = _deadline(component, "hard_deadline")
    after_rate = component["rate"] if rate is None else _positive(
        rate, "Process rate", maximum=profile.template.max_rate
    )
    current_remaining = component["remaining_ticks"]
    after_remaining = current_remaining if remaining_ticks is None else _duration(
        remaining_ticks, "Process remaining_ticks", maximum=profile.template.max_duration_ticks
    )
    deadline = now + after_remaining
    if deadline > hard_deadline:
        raise GameplayContractError("Process duration cannot extend the hard deadline")
    elapsed = component["elapsed_ticks"]
    after_duration = elapsed + after_remaining
    if after_duration > profile.template.max_duration_ticks:
        raise GameplayContractError("Process duration exceeds the trusted template maximum")
    if remaining_ticks is None:
        deadline = _scheduled_time(staged, component["expiry_handle"])
    after_progress = min(1.0, elapsed / after_duration)
    payload = {
        "profile_id": profile.id,
        "profile_hash": profile.profile_hash,
        "expiry_handle": component["expiry_handle"],
        "before_rate": component["rate"],
        "before_duration_ticks": component["duration_ticks"],
        "before_remaining_ticks": component["remaining_ticks"],
        "after_rate": after_rate,
        "after_duration": after_duration,
        "after_remaining": after_remaining,
        "after_progress": after_progress,
        "deadline": deadline,
    }
    result = staged.runtime.run_event(Event(
        _event_id(PROCESS_MODIFY_EVENT, profile.id, payload),
        PROCESS_MODIFY_EVENT,
        now,
        owner,
        profile.process_entity_id,
        payload,
    ))
    if not result.changed:
        raise GameplayContractError("Process modification did not match its trusted Law")
    publish_gameplay_session(session, staged)
    return result


def _pause_process(
    controller: ProcessController, session: GameplaySession, process_id: str, *, owner: str
) -> Any:
    profile = controller._profile(process_id)
    staged = stage_gameplay_session(session)
    component = _preflight(
        controller, staged, profile, owner=owner, states={"running"}, require_inputs=False
    )
    now = _boundary_time(staged, controller.clock_id)
    deadline = _scheduled_time(staged, component["expiry_handle"])
    available = int(deadline - now)
    if available < 1:
        raise GameplayContractError("Process has no remaining active duration")
    after_remaining = min(component["remaining_ticks"], available)
    after_duration = component["elapsed_ticks"] + after_remaining
    after_progress = min(1.0, component["elapsed_ticks"] / after_duration)
    payload = {
        "profile_id": profile.id,
        "profile_hash": profile.profile_hash,
        "expiry_handle": component["expiry_handle"],
        "before_rate": component["rate"],
        "before_duration_ticks": component["duration_ticks"],
        "before_remaining_ticks": component["remaining_ticks"],
        "after_duration": after_duration,
        "after_remaining": after_remaining,
        "after_progress": after_progress,
    }
    result = staged.runtime.run_event(Event(
        _event_id(PROCESS_PAUSE_EVENT, profile.id, payload),
        PROCESS_PAUSE_EVENT,
        now,
        owner,
        profile.process_entity_id,
        payload,
    ))
    if not result.changed:
        raise GameplayContractError("Process pause did not match its trusted Law")
    publish_gameplay_session(session, staged)
    return result


def _resume_process(
    controller: ProcessController, session: GameplaySession, process_id: str, *, owner: str
) -> Any:
    profile = controller._profile(process_id)
    staged = stage_gameplay_session(session)
    component = _preflight(
        controller, staged, profile, owner=owner, states={"paused"}, require_inputs=True
    )
    _assert_active_limits(controller, staged, profile, activation=True)
    _assert_writer_exclusivity(controller, staged, profile)
    now = _boundary_time(staged, controller.clock_id)
    hard_deadline = _deadline(component, "hard_deadline")
    available = int(hard_deadline - now)
    after_remaining = min(component["remaining_ticks"], available)
    if after_remaining < 1:
        raise GameplayContractError("Process hard deadline has passed")
    deadline = now + after_remaining
    after_duration = component["elapsed_ticks"] + after_remaining
    if after_duration > profile.template.max_duration_ticks:
        raise GameplayContractError("Process resume exceeds the trusted duration maximum")
    after_progress = min(1.0, component["elapsed_ticks"] / after_duration)
    payload = {
        "profile_id": profile.id,
        "profile_hash": profile.profile_hash,
        "before_remaining": component["remaining_ticks"],
        "before_duration": component["duration_ticks"],
        "after_remaining": after_remaining,
        "after_duration": after_duration,
        "after_progress": after_progress,
        "deadline": deadline,
    }
    result = staged.runtime.run_event(Event(
        _event_id(PROCESS_RESUME_EVENT, profile.id, payload),
        PROCESS_RESUME_EVENT,
        now,
        owner,
        profile.process_entity_id,
        payload,
    ))
    if not result.changed:
        raise GameplayContractError("Process resume did not match its trusted Law")
    publish_gameplay_session(session, staged)
    return result


def _preflight(
    controller: ProcessController,
    session: GameplaySession,
    profile: ProcessProfile,
    *,
    owner: str,
    states: set[str],
    require_inputs: bool,
) -> dict[str, Any]:
    if owner != profile.owner:
        raise GameplayContractError("Process source ownership does not match its trusted profile")
    entity = session.state.entities.get(profile.process_entity_id)
    if entity is None:
        raise GameplayContractError("Process target entity does not exist")
    component = _validate_process_component(entity, profile)
    if component["state"] not in states:
        raise GameplayContractError(
            f"Process state must be one of {', '.join(sorted(states))}"
        )
    now = _boundary_time(session, controller.clock_id)
    if component["started_at"] is not None:
        hard_deadline = _deadline(component, "hard_deadline")
        if now > hard_deadline:
            raise GameplayContractError("Process hard deadline has passed")
    for port, ref in (*profile.input_ports, *profile.output_ports):
        _validate_stock(session, ref, port)
    if require_inputs:
        for index, (_, ref) in enumerate(profile.input_ports):
            amount = session.state.entities[ref.entity_id].components[STOCK_COMPONENT]["amount"]
            if amount <= 0:
                raise GameplayContractError(f"Process input {index} is empty; production cannot start")
    return component


def _validate_process_component(entity: Entity, profile: ProcessProfile) -> dict[str, Any]:
    raw = entity.components.get(PROCESS_COMPONENT)
    required = {
        "profile_id", "profile_hash", "template_id", "owner", "state", "rate",
        "max_rate", "duration_ticks", "remaining_ticks", "elapsed_ticks",
        "progress", "started_at", "hard_deadline", "expiry_handle",
        "last_step", "last_failure",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise GameplayContractError("Process component shape is invalid")
    if (raw["profile_id"] != profile.id or raw["profile_hash"] != profile.profile_hash
            or raw["template_id"] != profile.template.id or raw["owner"] != profile.owner):
        raise GameplayContractError("Process component does not match its trusted profile")
    if raw["state"] not in _PROCESS_STATES:
        raise GameplayContractError("Process state is invalid")
    rate = _positive(raw["rate"], "Process rate", maximum=profile.template.max_rate)
    max_rate = _positive(raw["max_rate"], "Process max_rate", maximum=MAX_RATE)
    if max_rate != profile.template.max_rate:
        raise GameplayContractError("Process max_rate does not match its trusted template")
    duration = _duration(raw["duration_ticks"], "Process duration_ticks",
                         maximum=profile.template.max_duration_ticks)
    remaining = _duration(raw["remaining_ticks"], "Process remaining_ticks",
                          maximum=profile.template.max_duration_ticks, allow_zero=True)
    if duration != raw["duration_ticks"] or remaining != raw["remaining_ticks"]:
        raise GameplayContractError("Process duration fields must be integer ticks")
    elapsed = _non_negative_int(raw["elapsed_ticks"], "Process elapsed_ticks",
                                maximum=profile.template.max_duration_ticks)
    if elapsed > duration or remaining > duration - elapsed:
        raise GameplayContractError("Process elapsed/remaining duration is inconsistent")
    progress = _finite(raw["progress"], "Process progress")
    if not 0.0 <= progress <= 1.0:
        raise GameplayContractError("Process progress must be in [0, 1]")
    started = raw["started_at"]
    if started is not None:
        started = _finite(started, "Process started_at")
    deadline = raw["hard_deadline"]
    if deadline is not None:
        deadline = _finite(deadline, "Process hard_deadline")
    if (started is None) != (deadline is None):
        raise GameplayContractError("Process start/deadline fields must appear together")
    handle = raw["expiry_handle"]
    if handle is not None and (not isinstance(handle, str) or not handle or len(handle) > 160):
        raise GameplayContractError("Process expiry_handle is invalid")
    if raw["state"] == "running" and handle is None:
        raise GameplayContractError("running Process requires an expiry handle")
    if raw["state"] != "running" and handle is not None:
        raise GameplayContractError("non-running Process cannot retain an expiry handle")
    _integer(raw["last_step"], "Process last_step", minimum=-1)
    if raw["last_failure"] not in _FAILURE_KINDS:
        raise GameplayContractError("Process last_failure is invalid")
    return raw


def _validate_stock(session: GameplaySession, ref: StockRef, port: ConversionPort) -> None:
    entity = session.state.entities.get(ref.entity_id)
    if entity is None:
        raise GameplayContractError(f"Process Stock entity {ref.entity_id!r} does not exist")
    raw = entity.components.get(STOCK_COMPONENT)
    if not isinstance(raw, dict) or set(raw) != {"amount", "capacity", "unit"}:
        raise GameplayContractError(
            f"Process Stock {ref.entity_id!r} must expose exactly components.stock "
            "{amount,capacity,unit}"
        )
    amount = _non_negative(raw["amount"], f"stock.{ref.entity_id}.amount")
    capacity = _non_negative(raw["capacity"], f"stock.{ref.entity_id}.capacity")
    if amount > capacity:
        raise GameplayContractError(f"Process Stock {ref.entity_id!r} exceeds capacity")
    _unit(raw["unit"], f"stock.{ref.entity_id}.unit")
    if raw["unit"] != port.unit:
        raise GameplayContractError(
            f"Process Stock {ref.entity_id!r} unit {raw['unit']!r} "
            f"does not match declared unit {port.unit!r}"
        )


def _assert_active_limits(
    controller: ProcessController, session: GameplaySession, profile: ProcessProfile, *, activation: bool
) -> None:
    if not activation:
        return
    running = [
        entity for entity in session.state.entities.values()
        if isinstance(entity.components.get(PROCESS_COMPONENT), dict)
        and entity.components[PROCESS_COMPONENT].get("state") == "running"
    ]
    if len(running) >= controller.limits.max_active:
        raise GameplayContractError("active Process limit is exhausted")


def _assert_writer_exclusivity(
    controller: ProcessController, session: GameplaySession, profile: ProcessProfile
) -> None:
    configured = profile.stock_ids & frozenset(controller.external_stock_writers)
    if configured:
        stock_id = sorted(configured)[0]
        raise GameplayContractError(
            f"Process Stock {stock_id!r} already has configured world writer "
            f"{controller.external_stock_writers[stock_id]!r}"
        )
    known = {item.process_entity_id: item for item in controller.profiles}
    for entity in session.state.entities.values():
        raw = entity.components.get(PROCESS_COMPONENT)
        if not isinstance(raw, dict) or raw.get("state") != "running":
            continue
        other = known.get(entity.id)
        if other is None or other.profile_hash != raw.get("profile_hash"):
            raise GameplayContractError("unknown active Process writer prevents safe activation")
        if other.id != profile.id and profile.stock_ids & other.stock_ids:
            raise GameplayContractError(
                f"shared Stock is already owned by running Process {other.id!r}"
            )


def _boundary_time(session: GameplaySession, clock_id: str) -> float:
    entity = session.state.entities.get(clock_id)
    raw = entity.components.get(CLOCK_COMPONENT) if entity is not None else None
    if not isinstance(raw, dict):
        raise GameplayContractError("missing gameplay clock")
    completed = raw.get("last_completed_step")
    next_step = raw.get("next_step")
    if (not isinstance(completed, int) or isinstance(completed, bool) or completed < 0
            or next_step != completed + 1):
        raise GameplayContractError("gameplay clock is not at a completed Tick boundary")
    now = _finite(session.state.sim_time, "world.sim_time")
    if now != float(completed):
        raise GameplayContractError("Process controls require a completed Tick boundary")
    return now


def _scheduled_time(session: GameplaySession, handle: Any) -> float:
    if not isinstance(handle, str) or not handle:
        raise GameplayContractError("Process expiry handle is missing")
    matches = [event for event in session.state.scheduled_events if event.id == handle]
    if len(matches) != 1:
        raise GameplayContractError("Process expiry event is missing")
    value = _finite(matches[0].time, "Process expiry time")
    if value <= session.state.sim_time:
        raise GameplayContractError("Process expiry is not in the future")
    return value


def _deadline(component: Mapping[str, Any], key: str) -> float:
    value = component.get(key)
    if value is None:
        raise GameplayContractError(f"Process {key} is missing")
    return _finite(value, f"Process {key}")


def _free_capacity(prefix: str) -> dict[str, Any]:
    return {
        "sub": [
            f"{prefix}.{STOCK_COMPONENT}.capacity",
            f"{prefix}.{STOCK_COMPONENT}.amount",
        ]
    }


def _expiry_id(profile_id: str) -> str:
    return f"pmw:v04:sandbox.process.expiry:{profile_id}"


def _event_id(event_type: str, profile_id: str, payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{event_type}:{profile_id}:{digest}"


def _ports(items: Any, path: str) -> None:
    if not isinstance(items, tuple) or any(not isinstance(item, ConversionPort) for item in items):
        raise GameplayContractError(f"{path} must be a tuple of ConversionPort objects")


def _bindings(items: Any, ports: tuple[ConversionPort, ...], path: str) -> None:
    if not isinstance(items, tuple) or any(not isinstance(item, StockBinding) for item in items):
        raise GameplayContractError(f"{path} must be a tuple of StockBinding objects")
    expected = {item.name for item in ports}
    supplied = [item.port for item in items]
    if len(supplied) != len(set(supplied)) or set(supplied) != expected:
        raise GameplayContractError(f"{path} must bind every declared port exactly once")


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GameplayContractError(f"{path} must be a finite number")
    return float(value)


def _positive(value: Any, path: str, *, maximum: float) -> float:
    number = _finite(value, path)
    if number <= 0 or number > maximum:
        raise GameplayContractError(f"{path} must be in (0, {maximum}]")
    return number


def _non_negative(value: Any, path: str) -> float:
    number = _finite(value, path)
    if number < 0:
        raise GameplayContractError(f"{path} must be non-negative")
    return number


def _integer(value: Any, path: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GameplayContractError(f"{path} must be an integer >= {minimum}")
    return value


def _bounded_int(value: Any, path: str, minimum: int, maximum: int) -> int:
    result = _integer(value, path, minimum=minimum)
    if result > maximum:
        raise GameplayContractError(f"{path} must be <= {maximum}")
    return result


def _duration(value: Any, path: str, *, maximum: int, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    result = _bounded_int(value, path, minimum, maximum)
    return result


def _non_negative_int(value: Any, path: str, *, maximum: int) -> int:
    return _bounded_int(value, path, 0, maximum)


def _entity_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ENTITY_ID.fullmatch(value) is None:
        raise GameplayContractError(f"{path} is not a valid trusted entity ID")
    return value


def _port_name(value: Any, path: str) -> str:
    if not isinstance(value, str) or _PORT_NAME.fullmatch(value) is None:
        raise GameplayContractError(f"{path} is not a valid port name")
    return value


def _unit(value: Any, path: str) -> str:
    if not isinstance(value, str) or _UNIT.fullmatch(value) is None:
        raise GameplayContractError(f"{path} is not a valid resource unit")
    return value
