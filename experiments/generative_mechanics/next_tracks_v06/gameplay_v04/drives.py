"""Bounded finite-Stock positive Field drives for Gameplay v0.4.

This module is a sidecar over the existing Gameplay runtime.  Trusted profile
data is lowered to PMW Event Laws; there is no second clock and no Python
per-tick mutator on an authoritative session.

Field definitions in this v0.4 bridge do not yet carry a universal unit
catalog.  Drive validation therefore checks the trusted Field domain exactly
and checks the Stock unit against the profile's explicitly declared unit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from pmw import Entity, Event, parse_law

from .contracts import FieldDefinition, GameplayContractError
from .dynamics import CLOCK_COMPONENT, DYNAMICS_COMPONENT, WORLD_TICK_EVENT
from .processes import (
    MAX_COEFFICIENT,
    MAX_DURATION_TICKS,
    MAX_RATE,
    MAX_STOCK_VALUE,
    STOCK_COMPONENT,
    StockRef,
)
from .runtime import GameplaySession
from .transactions import publish_gameplay_session, stage_gameplay_session


DRIVE_COMPONENT = "pmw_sandbox_drive"
DRIVE_PROTOCOL = "pmw-sandbox-drive-v0.1"
DRIVE_START_EVENT = "pmw.v04.sandbox.drive.start"
DRIVE_STEP_EVENT = "pmw.v04.sandbox.drive.step"
DRIVE_EXPIRE_EVENT = "pmw.v04.sandbox.drive.expire"

MAX_INSTANCES = 1024
_ENTITY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_UNIT = re.compile(r"[A-Za-z][A-Za-z0-9_.:/-]{0,31}\Z")
_DRIVE_FIELDS = {
    "profile_id",
    "profile_hash",
    "owner",
    "rate",
    "started_at",
    "expires_at",
    "expiry_handle",
    "last_step",
    "last_delta",
}


@dataclass(frozen=True, slots=True)
class DriveLimits:
    max_instances: int = 16
    max_active: int = 8

    def __post_init__(self) -> None:
        _bounded_int(self.max_instances, "DriveLimits.max_instances", 1, MAX_INSTANCES)
        _bounded_int(self.max_active, "DriveLimits.max_active", 1, MAX_INSTANCES)
        if self.max_active > self.max_instances:
            raise GameplayContractError("DriveLimits.max_active cannot exceed max_instances")


@dataclass(frozen=True, slots=True)
class DriveProfile:
    """One preallocated, trusted finite Stock source."""

    id: str
    drive_entity_id: str
    owner: str
    area_id: str
    field: FieldDefinition
    stock: StockRef
    stock_unit: str
    field_per_stock: float
    max_rate: float
    max_duration_ticks: int
    profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        _entity_id(self.id, "DriveProfile.id")
        _entity_id(self.drive_entity_id, "DriveProfile.drive_entity_id")
        _entity_id(self.owner, "DriveProfile.owner")
        _entity_id(self.area_id, "DriveProfile.area_id")
        if not isinstance(self.field, FieldDefinition):
            raise GameplayContractError("DriveProfile.field must be a FieldDefinition")
        if not isinstance(self.stock, StockRef):
            raise GameplayContractError("DriveProfile.stock must be a StockRef")
        _unit(self.stock_unit, "DriveProfile.stock_unit")
        _positive(self.field_per_stock, "DriveProfile.field_per_stock",
                  maximum=MAX_COEFFICIENT)
        _positive(self.max_rate, "DriveProfile.max_rate", maximum=MAX_RATE)
        _duration(self.max_duration_ticks, "DriveProfile.max_duration_ticks",
                  maximum=MAX_DURATION_TICKS)
        canonical = json.dumps(
            self._document(), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        object.__setattr__(
            self, "profile_hash", hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        )

    def _document(self) -> dict[str, Any]:
        return {
            "protocol": DRIVE_PROTOCOL,
            "kind": "drive_profile",
            "id": self.id,
            "drive_entity_id": self.drive_entity_id,
            "owner": self.owner,
            "area_id": self.area_id,
            "field": {
                "id": self.field.id,
                "minimum": self.field.minimum,
                "maximum": self.field.maximum,
                "initial": self.field.initial,
                "target": self.field.target,
                "rate": self.field.rate,
                "curve": self.field.curve,
                "max_persistent_patches": self.field.max_persistent_patches,
                "max_temporary_modifiers": self.field.max_temporary_modifiers,
            },
            "stock": self.stock.entity_id,
            "stock_unit": self.stock_unit,
            "field_per_stock": self.field_per_stock,
            "max_rate": self.max_rate,
            "max_duration_ticks": self.max_duration_ticks,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._document(), "profile_hash": self.profile_hash}


@dataclass(frozen=True, slots=True)
class DriveController:
    """Immutable action boundary over a finite set of trusted profiles."""

    profiles: tuple[DriveProfile, ...]
    limits: DriveLimits = field(default_factory=DriveLimits)
    clock_id: str = "pmw:v04:clock"

    def __post_init__(self) -> None:
        profiles = tuple(self.profiles)
        if any(not isinstance(item, DriveProfile) for item in profiles):
            raise GameplayContractError(
                "DriveController.profiles must contain DriveProfile objects"
            )
        if len(profiles) > self.limits.max_instances:
            raise GameplayContractError("registered Drive instances exceed max_instances")
        ids = [item.id for item in profiles]
        entities = [item.drive_entity_id for item in profiles]
        stocks = [item.stock.entity_id for item in profiles]
        if len(ids) != len(set(ids)):
            raise GameplayContractError("Drive profile IDs must be unique")
        if len(entities) != len(set(entities)):
            raise GameplayContractError("Drive entity IDs must be unique")
        if len(stocks) != len(set(stocks)):
            raise GameplayContractError("Drive profiles may not share an input Stock")
        _entity_id(self.clock_id, "DriveController.clock_id")
        object.__setattr__(self, "profiles", tuple(sorted(profiles, key=lambda item: item.id)))

    @property
    def laws(self) -> tuple[dict[str, Any], ...]:
        return build_drive_laws(self.profiles, clock_id=self.clock_id)

    def instantiate(self, profile_id: str) -> Entity:
        return instantiate_drive(self._profile(profile_id))

    def prepare_start(
        self,
        session: GameplaySession,
        profile_id: str,
        *,
        owner: str,
        rate: float,
        duration_ticks: int,
    ) -> dict[str, Any]:
        """Validate and prepare one activation without mutating the session."""
        profile = self._profile(profile_id)
        return _prepare_start(
            self,
            session,
            profile,
            owner=owner,
            rate=rate,
            duration_ticks=duration_ticks,
        )

    def start(
        self,
        session: GameplaySession,
        profile_id: str,
        *,
        owner: str,
        rate: float,
        duration_ticks: int,
    ) -> Any:
        """Stage a native activation through the same installed start Law."""
        profile = self._profile(profile_id)
        staged = stage_gameplay_session(session)
        prepared = _prepare_start(
            self,
            staged,
            profile,
            owner=owner,
            rate=rate,
            duration_ticks=duration_ticks,
        )
        result = staged.runtime.run_event(Event(
            _event_id(DRIVE_START_EVENT, profile.id, prepared),
            DRIVE_START_EVENT,
            staged.state.sim_time,
            owner,
            profile.drive_entity_id,
            _start_payload(prepared),
        ))
        expected = f"pmw.v04.sandbox.drive.{profile.id}.start"
        if expected not in result.triggered_law_ids:
            raise GameplayContractError("Drive start did not match its exact trusted Law")
        _assert_activated(staged, prepared)
        publish_gameplay_session(session, staged)
        return result

    def _profile(self, profile_id: str) -> DriveProfile:
        if not isinstance(profile_id, str):
            raise GameplayContractError("Drive profile ID must be a string")
        matches = [item for item in self.profiles if item.id == profile_id]
        if len(matches) != 1:
            raise GameplayContractError("unknown Drive profile")
        return matches[0]


def instantiate_drive(profile: DriveProfile) -> Entity:
    """Create a detached inactive Drive entity from a trusted profile."""
    if not isinstance(profile, DriveProfile):
        raise GameplayContractError("instantiate_drive requires a DriveProfile")
    return Entity(
        profile.drive_entity_id,
        "pmw_sandbox_drive",
        components={DRIVE_COMPONENT: {
            "profile_id": profile.id,
            "profile_hash": profile.profile_hash,
            "owner": profile.owner,
            "rate": 0.0,
            "started_at": None,
            "expires_at": None,
            "expiry_handle": None,
            "last_step": -1,
            "last_delta": 0.0,
        }},
    )


def build_drive_laws(
    profiles: Iterable[DriveProfile], *, clock_id: str = "pmw:v04:clock"
) -> tuple[dict[str, Any], ...]:
    """Lower trusted positive-source profiles into validated PMW Event Laws."""
    items = tuple(profiles)
    if any(not isinstance(item, DriveProfile) for item in items):
        raise GameplayContractError("build_drive_laws requires DriveProfile objects")
    if len(items) > MAX_INSTANCES:
        raise GameplayContractError("Drive law build exceeds the bounded instance limit")
    _entity_id(clock_id, "clock_id")
    normalized = tuple(sorted(items, key=lambda item: item.id))
    if len({item.id for item in normalized}) != len(normalized):
        raise GameplayContractError("duplicate Drive profile ID")
    if len({item.drive_entity_id for item in normalized}) != len(normalized):
        raise GameplayContractError("duplicate Drive entity ID")
    if len({item.stock.entity_id for item in normalized}) != len(normalized):
        raise GameplayContractError("Drive profiles may not share an input Stock")
    laws: list[dict[str, Any]] = []
    for profile in normalized:
        laws.extend(_profile_laws(profile, clock_id))
    result = tuple(sorted(laws, key=lambda item: item["id"]))
    for law in result:
        parse_law(law)
    return result


def _profile_laws(profile: DriveProfile, clock_id: str) -> list[dict[str, Any]]:
    drive = f"$drive.{DRIVE_COMPONENT}"
    field_root = f"$area.{DYNAMICS_COMPONENT}.fields.{profile.field.id}"
    stock_root = f"$stock.{STOCK_COMPONENT}"
    base_bindings: dict[str, Any] = {
        "drive": {"kind": "entity", "requires": [DRIVE_COMPONENT]},
        "stock": {"kind": "entity", "requires": [STOCK_COMPONENT]},
        "area": {"kind": "entity", "requires": [DYNAMICS_COMPONENT]},
        "actor": {"kind": "entity", "requires": ["pmw_gameplay_actor"]},
        "clock": {"kind": "entity", "requires": [CLOCK_COMPONENT]},
        "drive_location": {
            "kind": "relation", "type": "located_in",
            "source": "$drive", "target": "$area",
        },
        "stock_location": {
            "kind": "relation", "type": "located_in",
            "source": "$stock", "target": "$area",
        },
        "actor_location": {
            "kind": "relation", "type": "located_in",
            "source": "$actor", "target": "$area",
        },
    }
    target_identity = [
        {"ref": "$area.id", "eq": profile.area_id},
        {"ref": "$drive.id", "eq": profile.drive_entity_id},
        {"ref": "$stock.id", "eq": profile.stock.entity_id},
        {"ref": f"{drive}.profile_id", "eq": profile.id},
        {"ref": f"{drive}.profile_hash", "eq": profile.profile_hash},
        {"ref": f"{drive}.owner", "eq": profile.owner},
        {"ref": f"{field_root}.domain_min", "eq": profile.field.minimum},
        {"ref": f"{field_root}.domain_max", "eq": profile.field.maximum},
        {"ref": f"{stock_root}.unit", "eq": profile.stock_unit},
    ]
    domain = _stock_domain_conditions(stock_root)
    field_domain = [
        {"ref": f"{field_root}.value", "gte": profile.field.minimum},
        {"ref": f"{field_root}.value", "lte": profile.field.maximum},
    ]

    laws: list[dict[str, Any]] = []
    laws.append({
        "id": f"pmw.v04.sandbox.drive.{profile.id}.start",
        "mode": "event",
        "priority": 100,
        "bindings": base_bindings,
        "when": {"all": [
            {"event.type": {"eq": DRIVE_START_EVENT}},
            *target_identity,
            *domain,
            *field_domain,
            {"ref": "$actor.id", "eq": profile.owner},
            {"ref": "$event.source", "eq": profile.owner},
            {"ref": "$event.target", "eq": profile.drive_entity_id},
            {"ref": "$event.payload.profile_id", "eq": profile.id},
            {"ref": "$event.payload.profile_hash", "eq": profile.profile_hash},
            {"ref": "$event.payload.owner", "eq": profile.owner},
            {"ref": "$event.payload.drive_entity_id", "eq": profile.drive_entity_id},
            {"ref": "$event.payload.area_id", "eq": profile.area_id},
            {"ref": "$event.payload.field_id", "eq": profile.field.id},
            {"ref": "$event.payload.stock_id", "eq": profile.stock.entity_id},
            {"ref": "$event.payload.stock_unit", "eq": profile.stock_unit},
            {"ref": "$event.payload.field_per_stock", "eq": profile.field_per_stock},
            {"ref": "$event.payload.rate", "gt": 0},
            {"ref": "$event.payload.rate", "lte": profile.max_rate},
            {"ref": "$event.payload.duration_ticks", "gt": 0},
            {"ref": "$event.payload.duration_ticks", "lte": profile.max_duration_ticks},
            {"ref": "$event.payload.started_at", "eq": "$event.time"},
            {"ref": "$event.payload.expires_at", "eq": {
                "add": ["$event.time", "$event.payload.duration_ticks"]
            }},
            {"ref": "$event.time", "eq": "$clock.pmw_gameplay_clock.last_completed_step"},
            {"ref": f"{drive}.rate", "eq": 0},
            {"ref": f"{drive}.started_at", "eq": None},
            {"ref": f"{drive}.expires_at", "eq": None},
            {"ref": f"{drive}.expiry_handle", "eq": None},
            {"ref": f"{drive}.last_step", "eq": -1},
            {"ref": f"{drive}.last_delta", "eq": 0},
            {"ref": f"{stock_root}.amount", "gt": 0},
            {"ref": f"{field_root}.value", "lt": profile.field.maximum},
        ]},
        "effects": [
            {"op": "set", "target": f"{drive}.rate", "value": "$event.payload.rate"},
            {"op": "set", "target": f"{drive}.started_at", "value": "$event.payload.started_at"},
            {"op": "set", "target": f"{drive}.expires_at", "value": "$event.payload.expires_at"},
            {"op": "set", "target": f"{drive}.expiry_handle",
             "value": "$event.payload.expiry_handle"},
            {"op": "set", "target": f"{drive}.last_step", "value": -1},
            {"op": "set", "target": f"{drive}.last_delta", "value": 0.0},
            {"op": "schedule_event", "event": {
                "id": "$event.payload.expiry_handle",
                "type": DRIVE_EXPIRE_EVENT,
                "time": "$event.payload.expires_at",
                "source": profile.owner,
                "target": profile.drive_entity_id,
                "payload": {
                    "profile_id": profile.id,
                    "profile_hash": profile.profile_hash,
                    "expiry_handle": "$event.payload.expiry_handle",
                    "area_id": profile.area_id,
                    "field_id": profile.field.id,
                    "stock_id": profile.stock.entity_id,
                },
            }},
        ],
    })

    tick_conditions = [
        {"event.type": {"eq": WORLD_TICK_EVENT}},
        {"ref": "$clock.id", "eq": clock_id},
        {"ref": "$event.payload.step", "eq": "$clock.pmw_gameplay_clock.next_step"},
        {"ref": "$event.time", "eq": "$clock.pmw_gameplay_clock.next_time"},
        *target_identity,
        *domain,
        *field_domain,
        {"ref": f"{drive}.started_at", "neq": None},
        {"ref": f"{drive}.expires_at", "gt": "$event.time"},
        {"ref": f"{drive}.started_at", "lt": "$event.time"},
        {"ref": f"{drive}.expiry_handle", "neq": None},
        {"ref": f"{drive}.rate", "gt": 0},
        {"ref": f"{drive}.rate", "lte": profile.max_rate},
        {"ref": f"{drive}.last_step", "lt": "$event.payload.step"},
    ]
    laws.append({
        "id": f"pmw.v04.sandbox.drive.{profile.id}.step_trigger",
        "mode": "event",
        "priority": 100,
        "bindings": {
            key: value for key, value in base_bindings.items()
            if key != "actor" and key != "actor_location"
        },
        "when": {"all": tick_conditions},
        "effects": [{
            "op": "emit_event",
            "event": {
                "type": DRIVE_STEP_EVENT,
                "time": "$event.time",
                "source": profile.owner,
                "target": profile.drive_entity_id,
                "payload": {
                    "profile_id": profile.id,
                    "profile_hash": profile.profile_hash,
                    "owner": profile.owner,
                    "drive_entity_id": profile.drive_entity_id,
                    "area_id": profile.area_id,
                    "field_id": profile.field.id,
                    "stock_id": profile.stock.entity_id,
                    "stock_unit": profile.stock_unit,
                    "field_per_stock": profile.field_per_stock,
                    "rate": f"{drive}.rate",
                    "expiry_handle": f"{drive}.expiry_handle",
                    "step": "$event.payload.step",
                },
            },
        }],
    })

    available = {"sub": [f"{field_root}.domain_max", f"{field_root}.value"]}
    fuel_limited = {"mul": [f"{stock_root}.amount", profile.field_per_stock]}
    candidate = {"min": [f"{drive}.rate", fuel_limited, available]}
    # Publish only representable paired changes.  The Field after-value first
    # fixes the accepted Field delta; the Stock after-value is then derived
    # from that actual delta, and the step is gated unless both stored values
    # differ from their exact before-values.
    new_field = {
        "clamp": [
            {"add": [f"{field_root}.value", candidate]},
            profile.field.minimum,
            profile.field.maximum,
        ]
    }
    actual_field_delta = {"sub": [new_field, f"{field_root}.value"]}
    new_stock = {
        "max": [
            0.0,
            {
                "sub": [
                    f"{stock_root}.amount",
                    {"div": [actual_field_delta, profile.field_per_stock]},
                ]
            },
        ]
    }
    representable = {"all": [
        {"ref": f"{stock_root}.amount", "gt": new_stock},
        {"ref": f"{field_root}.value", "lt": new_field},
    ]}
    step_common = [
        {"event.type": {"eq": DRIVE_STEP_EVENT}},
        *target_identity,
        *domain,
        *field_domain,
        {"ref": "$event.source", "eq": profile.owner},
        {"ref": "$event.target", "eq": profile.drive_entity_id},
        {"ref": "$event.payload.profile_id", "eq": profile.id},
        {"ref": "$event.payload.profile_hash", "eq": profile.profile_hash},
        {"ref": "$event.payload.owner", "eq": profile.owner},
        {"ref": "$event.payload.area_id", "eq": profile.area_id},
        {"ref": "$event.payload.field_id", "eq": profile.field.id},
        {"ref": "$event.payload.stock_id", "eq": profile.stock.entity_id},
        {"ref": "$event.payload.stock_unit", "eq": profile.stock_unit},
        {"ref": "$event.payload.field_per_stock", "eq": profile.field_per_stock},
        {"ref": "$event.payload.rate", "eq": f"{drive}.rate"},
        {"ref": "$event.payload.expiry_handle", "eq": f"{drive}.expiry_handle"},
        {"ref": "$event.payload.step", "eq": "$clock.pmw_gameplay_clock.last_completed_step"},
        {"ref": f"{drive}.started_at", "neq": None},
        {"ref": f"{drive}.expires_at", "gt": "$event.time"},
        {"ref": f"{drive}.rate", "gt": 0},
        {"ref": f"{drive}.last_step", "lt": "$event.payload.step"},
        {"ref": f"{stock_root}.amount", "gt": 0},
        {"ref": f"{field_root}.value", "lt": profile.field.maximum},
    ]
    step_bindings = {
        key: value for key, value in base_bindings.items()
        if key != "actor" and key != "actor_location"
    }
    laws.append({
        "id": f"pmw.v04.sandbox.drive.{profile.id}.step",
        "mode": "event",
        "priority": 100,
        "bindings": step_bindings,
        "when": {"all": [*step_common, representable]},
        "effects": [
            {"op": "set", "target": f"{field_root}.value", "value": new_field},
            {"op": "set", "target": f"{stock_root}.amount", "value": new_stock},
            {"op": "set", "target": f"{drive}.last_step", "value": "$event.payload.step"},
            {"op": "set", "target": f"{drive}.last_delta", "value": actual_field_delta},
        ],
    })
    laws.append({
        "id": f"pmw.v04.sandbox.drive.{profile.id}.step_unrepresentable",
        "mode": "event",
        "priority": 100,
        "bindings": step_bindings,
        "when": {"all": [*step_common, {"not": representable}]},
        "effects": [
            {"op": "set", "target": f"{drive}.last_step", "value": "$event.payload.step"},
            {"op": "set", "target": f"{drive}.last_delta", "value": 0.0},
        ],
    })

    laws.append({
        "id": f"pmw.v04.sandbox.drive.{profile.id}.expire",
        "mode": "event",
        "priority": 100,
        "bindings": {"drive": {"kind": "entity", "requires": [DRIVE_COMPONENT]}},
        "when": {"all": [
            {"event.type": {"eq": DRIVE_EXPIRE_EVENT}},
            {"ref": "$event.id", "eq": f"{drive}.expiry_handle"},
            {"ref": "$event.target", "eq": profile.drive_entity_id},
            {"ref": "$event.source", "eq": profile.owner},
            {"ref": "$event.payload.profile_id", "eq": profile.id},
            {"ref": "$event.payload.profile_hash", "eq": profile.profile_hash},
            {"ref": "$event.payload.expiry_handle", "eq": f"{drive}.expiry_handle"},
            {"ref": "$drive.id", "eq": profile.drive_entity_id},
            {"ref": f"{drive}.profile_id", "eq": profile.id},
            {"ref": f"{drive}.profile_hash", "eq": profile.profile_hash},
            {"ref": f"{drive}.owner", "eq": profile.owner},
            {"ref": f"{drive}.started_at", "neq": None},
        ]},
        "effects": [
            {"op": "set", "target": f"{drive}.rate", "value": 0.0},
            {"op": "set", "target": f"{drive}.started_at", "value": None},
            {"op": "set", "target": f"{drive}.expires_at", "value": None},
            {"op": "set", "target": f"{drive}.expiry_handle", "value": None},
            {"op": "set", "target": f"{drive}.last_step", "value": -1},
            {"op": "set", "target": f"{drive}.last_delta", "value": 0.0},
            {"op": "cancel_scheduled", "value": f"{drive}.expiry_handle"},
        ],
    })
    return laws


def _prepare_start(
    controller: DriveController,
    session: GameplaySession,
    profile: DriveProfile,
    *,
    owner: str,
    rate: float,
    duration_ticks: int,
) -> dict[str, Any]:
    if owner != profile.owner:
        raise GameplayContractError("Drive source ownership does not match its trusted profile")
    activation_rate = _positive(rate, "Drive rate", maximum=profile.max_rate)
    duration = _duration(
        duration_ticks, "Drive duration_ticks", maximum=profile.max_duration_ticks
    )
    now = _boundary_time(session, controller.clock_id)
    area = session.state.entities.get(profile.area_id)
    drive = session.state.entities.get(profile.drive_entity_id)
    stock = session.state.entities.get(profile.stock.entity_id)
    actor = session.state.entities.get(profile.owner)
    if area is None or "pmw_gameplay_area" not in area.components:
        raise GameplayContractError("Drive target Area does not exist")
    if drive is None:
        raise GameplayContractError("Drive entity does not exist")
    if stock is None:
        raise GameplayContractError("Drive input Stock does not exist")
    if actor is None or "pmw_gameplay_actor" not in actor.components:
        raise GameplayContractError("Drive owner is not an Actor")
    component = _validate_drive_component(drive, profile, now=now)
    if component["started_at"] is not None:
        raise GameplayContractError("Drive profile is already active")
    _validate_field(session, profile, area)
    _validate_stock(session, profile)
    for entity_id in (profile.owner, profile.drive_entity_id, profile.stock.entity_id):
        if _located_area(session, entity_id) != profile.area_id:
            raise GameplayContractError(
                "Drive owner, source, and Drive entity must be local to the profile Area"
            )
    active = _active_profiles(controller, session)
    if len(active) >= controller.limits.max_active:
        raise GameplayContractError("active Drive limit is exhausted")
    field = _field_state(session, profile)
    if float(stock.components[STOCK_COMPONENT]["amount"]) <= 0:
        raise GameplayContractError("Drive input Stock is empty")
    if float(field["value"]) >= profile.field.maximum:
        raise GameplayContractError("Drive target Field is full")
    expires_at = now + duration
    expiry_handle = _expiry_id(
        profile, owner=owner, started_at=now, rate=activation_rate, duration=duration
    )
    return {
        "profile_id": profile.id,
        "profile_hash": profile.profile_hash,
        "owner": owner,
        "drive_entity_id": profile.drive_entity_id,
        "area_id": profile.area_id,
        "field_id": profile.field.id,
        "stock_id": profile.stock.entity_id,
        "stock_unit": profile.stock_unit,
        "field_per_stock": profile.field_per_stock,
        "rate": activation_rate,
        "duration_ticks": duration,
        "started_at": now,
        "expires_at": expires_at,
        "expiry_handle": expiry_handle,
    }


def _validate_drive_component(
    entity: Entity, profile: DriveProfile, *, now: float
) -> dict[str, Any]:
    raw = entity.components.get(DRIVE_COMPONENT)
    if not isinstance(raw, dict) or set(raw) != _DRIVE_FIELDS:
        raise GameplayContractError("Drive component shape is invalid")
    if (
        raw["profile_id"] != profile.id
        or raw["profile_hash"] != profile.profile_hash
        or raw["owner"] != profile.owner
    ):
        raise GameplayContractError("Drive component does not match its trusted profile")
    rate = _finite(raw["rate"], "Drive rate")
    if not 0.0 <= rate <= profile.max_rate:
        raise GameplayContractError("Drive rate is outside its trusted profile bound")
    started = raw["started_at"]
    expires = raw["expires_at"]
    handle = raw["expiry_handle"]
    active_values = (started is not None, expires is not None, handle is not None)
    if not all(active_values) and any(active_values):
        raise GameplayContractError("Drive lifecycle fields must appear together")
    if rate == 0.0 and any(active_values):
        raise GameplayContractError("active Drive requires a positive rate")
    if rate > 0.0 and not all(active_values):
        raise GameplayContractError("inactive Drive cannot retain an active rate")
    if started is not None:
        started_value = _finite(started, "Drive started_at")
        expires_value = _finite(expires, "Drive expires_at")
        if expires_value <= started_value or expires_value - started_value > profile.max_duration_ticks:
            raise GameplayContractError("Drive duration is invalid")
        if now > expires_value:
            raise GameplayContractError("Drive expiry has already passed")
        if not isinstance(handle, str) or not handle or len(handle) > 192:
            raise GameplayContractError("Drive expiry_handle is invalid")
    _integer(raw["last_step"], "Drive last_step", minimum=-1)
    _finite(raw["last_delta"], "Drive last_delta")
    return raw


def _validate_field(session: GameplaySession, profile: DriveProfile, area: Entity) -> None:
    field = _field_state(session, profile)
    if field.get("domain_min") != profile.field.minimum or field.get("domain_max") != profile.field.maximum:
        raise GameplayContractError("Drive Field domain does not match its trusted profile")
    value = _finite(field.get("value"), "Drive Field value")
    if not profile.field.minimum <= value <= profile.field.maximum:
        raise GameplayContractError("Drive Field value is outside its trusted domain")


def _field_state(session: GameplaySession, profile: DriveProfile) -> dict[str, Any]:
    area = session.state.entities.get(profile.area_id)
    dynamics = area.components.get(DYNAMICS_COMPONENT) if area is not None else None
    fields = dynamics.get("fields") if isinstance(dynamics, dict) else None
    field = fields.get(profile.field.id) if isinstance(fields, dict) else None
    if not isinstance(field, dict):
        raise GameplayContractError("Drive target Area Field does not exist")
    return field


def _validate_stock(session: GameplaySession, profile: DriveProfile) -> None:
    entity = session.state.entities.get(profile.stock.entity_id)
    raw = entity.components.get(STOCK_COMPONENT) if entity is not None else None
    if not isinstance(raw, dict) or set(raw) != {"amount", "capacity", "unit"}:
        raise GameplayContractError(
            "Drive Stock must expose exactly components.stock {amount,capacity,unit}"
        )
    amount = _non_negative(raw["amount"], "Drive Stock amount")
    capacity = _non_negative(raw["capacity"], "Drive Stock capacity")
    if amount > MAX_STOCK_VALUE or capacity > MAX_STOCK_VALUE or amount > capacity:
        raise GameplayContractError("Drive Stock amount/capacity is outside its trusted bound")
    _unit(raw["unit"], "Drive Stock unit")
    if raw["unit"] != profile.stock_unit:
        raise GameplayContractError("Drive Stock unit does not match its trusted profile")


def _active_profiles(
    controller: DriveController, session: GameplaySession
) -> tuple[DriveProfile, ...]:
    active = []
    for profile in controller.profiles:
        entity = session.state.entities.get(profile.drive_entity_id)
        raw = entity.components.get(DRIVE_COMPONENT) if entity is not None else None
        if not isinstance(raw, dict):
            continue
        if raw.get("started_at") is not None:
            _validate_drive_component(
                entity, profile, now=_finite(session.state.sim_time, "world.sim_time")
            )
            active.append(profile)
    return tuple(active)


def _located_area(session: GameplaySession, entity_id: str) -> str | None:
    entities = session.state.entities
    areas = sorted(
        relation.target
        for relation in session.state.relations.values()
        if relation.type == "located_in" and relation.source == entity_id
    )
    if len(areas) != 1:
        return None
    area = entities.get(areas[0])
    if area is None or "pmw_gameplay_area" not in area.components:
        return None
    return area.id


def _assert_activated(session: GameplaySession, prepared: Mapping[str, Any]) -> None:
    entity = session.state.entities.get(prepared["drive_entity_id"])
    raw = entity.components.get(DRIVE_COMPONENT) if entity is not None else None
    if not isinstance(raw, dict) or raw != {
        "profile_id": prepared["profile_id"],
        "profile_hash": prepared["profile_hash"],
        "owner": prepared["owner"],
        "rate": prepared["rate"],
        "started_at": prepared["started_at"],
        "expires_at": prepared["expires_at"],
        "expiry_handle": prepared["expiry_handle"],
        "last_step": -1,
        "last_delta": 0.0,
    }:
        raise GameplayContractError("Drive activation state is not the exact prepared state")
    scheduled = [
        event for event in session.state.scheduled_events
        if event.id == prepared["expiry_handle"]
    ]
    if (
        len(scheduled) != 1
        or scheduled[0].type != DRIVE_EXPIRE_EVENT
        or scheduled[0].time != prepared["expires_at"]
        or scheduled[0].target != prepared["drive_entity_id"]
    ):
        raise GameplayContractError("Drive activation schedule is not exact")


def _start_payload(prepared: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: prepared[key]
        for key in (
            "profile_id",
            "profile_hash",
            "owner",
            "drive_entity_id",
            "area_id",
            "field_id",
            "stock_id",
            "stock_unit",
            "field_per_stock",
            "rate",
            "duration_ticks",
            "started_at",
            "expires_at",
            "expiry_handle",
        )
    }


def _stock_domain_conditions(path: str) -> list[dict[str, Any]]:
    return [
        {"ref": f"{path}.amount", "gte": 0},
        {"ref": f"{path}.amount", "lte": MAX_STOCK_VALUE},
        {"ref": f"{path}.capacity", "gte": 0},
        {"ref": f"{path}.capacity", "lte": MAX_STOCK_VALUE},
        {"ref": f"{path}.capacity", "gte": f"{path}.amount"},
    ]


def _boundary_time(session: GameplaySession, clock_id: str) -> float:
    entity = session.state.entities.get(clock_id)
    raw = entity.components.get(CLOCK_COMPONENT) if entity is not None else None
    if not isinstance(raw, dict):
        raise GameplayContractError("missing gameplay clock")
    completed = raw.get("last_completed_step")
    next_step = raw.get("next_step")
    if (
        isinstance(completed, bool)
        or not isinstance(completed, int)
        or completed < 0
        or next_step != completed + 1
    ):
        raise GameplayContractError("gameplay clock is not at a completed Tick boundary")
    now = _finite(session.state.sim_time, "world.sim_time")
    if now != float(completed):
        raise GameplayContractError("Drive controls require a completed Tick boundary")
    return now


def _expiry_id(
    profile: DriveProfile, *, owner: str, started_at: float, rate: float, duration: int
) -> str:
    document = {
        "profile_id": profile.id,
        "profile_hash": profile.profile_hash,
        "owner": owner,
        "started_at": started_at,
        "rate": rate,
        "duration_ticks": duration,
    }
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"pmw:v04:sandbox.drive.expiry:{profile.id}:{digest}"


def _event_id(event_type: str, profile_id: str, payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{event_type}:{profile_id}:{digest}"


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GameplayContractError(f"{path} must be finite numeric")
    return float(value)


def _positive(value: Any, path: str, *, maximum: float) -> float:
    result = _finite(value, path)
    if result <= 0 or result > maximum:
        raise GameplayContractError(f"{path} must be in (0, {maximum}]")
    return result


def _non_negative(value: Any, path: str) -> float:
    result = _finite(value, path)
    if result < 0:
        raise GameplayContractError(f"{path} must be non-negative")
    return result


def _integer(value: Any, path: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GameplayContractError(f"{path} must be an integer >= {minimum}")
    return value


def _bounded_int(value: Any, path: str, minimum: int, maximum: int) -> int:
    result = _integer(value, path, minimum=minimum)
    if result > maximum:
        raise GameplayContractError(f"{path} must be <= {maximum}")
    return result


def _duration(value: Any, path: str, *, maximum: int) -> int:
    return _bounded_int(value, path, 1, maximum)


def _entity_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ENTITY_ID.fullmatch(value) is None:
        raise GameplayContractError(f"{path} is not a valid trusted entity ID")
    return value


def _unit(value: Any, path: str) -> str:
    if not isinstance(value, str) or _UNIT.fullmatch(value) is None:
        raise GameplayContractError(f"{path} is not a valid resource unit")
    return value
