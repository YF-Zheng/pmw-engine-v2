"""Bounded temporary modification of trusted existing gameplay Relations.

Profiles are static authority.  The trusted helper only creates detached
Relations; all authoritative component mutation remains Law-driven.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from pmw import Event, Relation, parse_law

from .contracts import GameplayContractError
from .runtime import GameplaySession


RELATION_COMPONENT = "pmw_gameplay_link"
RELATION_MODIFY_EVENT = "pmw.v04.sandbox.relation.modify"
RELATION_EXPIRE_EVENT = "pmw.v04.sandbox.relation.expire"
RELATION_PROTOCOL = "pmw-sandbox-relation-v0.1"

MAX_INSTANCES = 1024
_ENTITY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")

__all__ = [
    "RELATION_COMPONENT",
    "RELATION_MODIFY_EVENT",
    "RELATION_EXPIRE_EVENT",
    "RelationLimits",
    "RelationProfile",
    "RelationController",
    "instantiate_relation",
]


@dataclass(frozen=True, slots=True)
class RelationLimits:
    max_instances: int = 16
    max_active: int = 8

    def __post_init__(self) -> None:
        _bounded_int(self.max_instances, "RelationLimits.max_instances", 1, MAX_INSTANCES)
        _bounded_int(self.max_active, "RelationLimits.max_active", 1, MAX_INSTANCES)
        if self.max_active > self.max_instances:
            raise GameplayContractError("RelationLimits.max_active cannot exceed max_instances")


@dataclass(frozen=True, slots=True)
class RelationProfile:
    """One preallocated existing Relation and its immutable authority."""

    id: str
    relation_id: str
    relation_type: str
    source_entity_id: str
    target_entity_id: str
    owner: str
    area_id: str
    source_components: tuple[str, ...]
    target_components: tuple[str, ...]
    max_duration_ticks: int
    profile_hash: str = field(init=False)

    def __post_init__(self) -> None:
        _entity_id(self.id, "RelationProfile.id")
        _entity_id(self.relation_id, "RelationProfile.relation_id")
        _entity_id(self.relation_type, "RelationProfile.relation_type")
        _entity_id(self.source_entity_id, "RelationProfile.source_entity_id")
        _entity_id(self.target_entity_id, "RelationProfile.target_entity_id")
        _entity_id(self.owner, "RelationProfile.owner")
        _entity_id(self.area_id, "RelationProfile.area_id")
        source = _markers(self.source_components, "RelationProfile.source_components")
        target = _markers(self.target_components, "RelationProfile.target_components")
        _duration(self.max_duration_ticks, "RelationProfile.max_duration_ticks")
        object.__setattr__(self, "source_components", source)
        object.__setattr__(self, "target_components", target)
        canonical = json.dumps(
            self._document(), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        object.__setattr__(
            self, "profile_hash", hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        )

    def _document(self) -> dict[str, Any]:
        return {
            "protocol": RELATION_PROTOCOL,
            "kind": "relation_profile",
            "id": self.id,
            "relation_id": self.relation_id,
            "relation_type": self.relation_type,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "owner": self.owner,
            "area_id": self.area_id,
            "source_components": list(self.source_components),
            "target_components": list(self.target_components),
            "max_duration_ticks": self.max_duration_ticks,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._document(), "profile_hash": self.profile_hash}


@dataclass(frozen=True, slots=True)
class RelationController:
    """Immutable action boundary over trusted preallocated Relations."""

    profiles: tuple[RelationProfile, ...]
    limits: RelationLimits = field(default_factory=RelationLimits)
    clock_id: str = "pmw:v04:clock"

    def __post_init__(self) -> None:
        profiles = tuple(self.profiles)
        if any(not isinstance(item, RelationProfile) for item in profiles):
            raise GameplayContractError(
                "RelationController.profiles must contain RelationProfile objects"
            )
        if len(profiles) > self.limits.max_instances:
            raise GameplayContractError("registered Relation instances exceed max_instances")
        ids = [item.id for item in profiles]
        relation_ids = [item.relation_id for item in profiles]
        if len(ids) != len(set(ids)):
            raise GameplayContractError("Relation profile IDs must be unique")
        if len(relation_ids) != len(set(relation_ids)):
            raise GameplayContractError("Relation profiles may not share a Relation slot")
        _entity_id(self.clock_id, "RelationController.clock_id")
        object.__setattr__(self, "profiles", tuple(sorted(profiles, key=lambda item: item.id)))

    @property
    def laws(self) -> tuple[dict[str, Any], ...]:
        return build_relation_laws(self.profiles, clock_id=self.clock_id)

    def instantiate(self, profile_id: str) -> Relation:
        return instantiate_relation(self._profile(profile_id))

    def prepare_modify(
        self,
        session: GameplaySession,
        profile_id: str,
        *,
        owner: str,
        enabled: bool,
        duration_ticks: int,
    ) -> dict[str, Any]:
        """Validate and prepare one activation without mutating the session."""
        profile = self._profile(profile_id)
        _entity_id(owner, "RelationController.owner")
        if not isinstance(enabled, bool):
            raise GameplayContractError("relation_enabled must be a strict boolean")
        _duration(duration_ticks, "relation duration_ticks")
        if duration_ticks > profile.max_duration_ticks:
            raise GameplayContractError("relation duration exceeds the trusted maximum")
        _preflight(self, session, profile, owner=owner)
        _assert_active_limit(self, session, profile)
        component = session.state.relations[profile.relation_id].components[RELATION_COMPONENT]
        started_at = float(session.state.sim_time)
        expires_at = float(session.state.sim_time + duration_ticks)
        handle = _expiry_handle(
            profile, owner, component, enabled, duration_ticks, started_at, expires_at
        )
        if any(event.id == handle for event in session.state.scheduled_events):
            raise GameplayContractError("Relation expiry handle is already scheduled")
        prepared = {
            "profile_id": profile.id,
            "profile_hash": profile.profile_hash,
            "relation_id": profile.relation_id,
            "relation_type": profile.relation_type,
            "source_entity_id": profile.source_entity_id,
            "target_entity_id": profile.target_entity_id,
            "owner": profile.owner,
            "area_id": profile.area_id,
            "enabled": enabled,
            "started_at": started_at,
            "expires_at": expires_at,
            "expiry_handle": handle,
            "base_enabled": component["base_enabled"],
        }
        return prepared

    def modify(
        self,
        session: GameplaySession,
        profile_id: str,
        *,
        owner: str,
        enabled: bool,
        duration_ticks: int,
    ) -> Any:
        """Run the same installed exact Law used by the formal Action path."""
        from .transactions import publish_gameplay_session, stage_gameplay_session

        staged = stage_gameplay_session(session)
        prepared = self.prepare_modify(
            staged,
            profile_id,
            owner=owner,
            enabled=enabled,
            duration_ticks=duration_ticks,
        )
        result = staged.runtime.run_event(Event(
            _event_id(prepared),
            RELATION_MODIFY_EVENT,
            staged.state.sim_time,
            prepared["owner"],
            prepared["relation_id"],
            prepared,
        ))
        expected = (
            f"pmw.v04.sandbox.relation.{prepared['profile_id']}.modify."
            f"{'on' if prepared['enabled'] else 'off'}"
        )
        if expected not in result.triggered_law_ids:
            raise GameplayContractError("Relation modify did not match its exact trusted Law")
        _assert_modified(staged, prepared)
        publish_gameplay_session(session, staged)
        return result

    def _profile(self, profile_id: str) -> RelationProfile:
        if not isinstance(profile_id, str):
            raise GameplayContractError("Relation profile ID must be a string")
        matches = [item for item in self.profiles if item.id == profile_id]
        if len(matches) != 1:
            raise GameplayContractError("unknown Relation profile")
        return matches[0]


def instantiate_relation(profile: RelationProfile, *, base_enabled: bool = True) -> Relation:
    """Create a detached real Relation with an inactive modifier slot."""
    if not isinstance(profile, RelationProfile):
        raise GameplayContractError("instantiate_relation requires a RelationProfile")
    if not isinstance(base_enabled, bool):
        raise GameplayContractError("base_enabled must be a strict boolean")
    return Relation(
        profile.relation_id,
        profile.relation_type,
        profile.source_entity_id,
        profile.target_entity_id,
        components={
            RELATION_COMPONENT: {
                "profile_id": profile.id,
                "profile_hash": profile.profile_hash,
                "owner": profile.owner,
                "base_enabled": base_enabled,
                "effective_enabled": base_enabled,
                "active": False,
                "enabled": None,
                "started_at": None,
                "expires_at": None,
                "expiry_handle": None,
            }
        },
    )


def build_relation_laws(
    profiles: Iterable[RelationProfile], *, clock_id: str = "pmw:v04:clock"
) -> tuple[dict[str, Any], ...]:
    items = tuple(profiles)
    if any(not isinstance(item, RelationProfile) for item in items):
        raise GameplayContractError("build_relation_laws requires RelationProfile objects")
    if len(items) > MAX_INSTANCES:
        raise GameplayContractError("Relation law build exceeds the bounded instance limit")
    _entity_id(clock_id, "clock_id")
    normalized = tuple(sorted(items, key=lambda item: item.id))
    if len({item.id for item in normalized}) != len(normalized):
        raise GameplayContractError("duplicate Relation profile ID")
    if len({item.relation_id for item in normalized}) != len(normalized):
        raise GameplayContractError("duplicate Relation slot")
    laws: list[dict[str, Any]] = []
    for profile in normalized:
        laws.extend(_profile_laws(profile, clock_id))
    result = tuple(sorted(laws, key=lambda item: item["id"]))
    for law in result:
        parse_law(law)
    return result


def _profile_laws(profile: RelationProfile, clock_id: str) -> list[dict[str, Any]]:
    root = f"$link.{RELATION_COMPONENT}"
    source_markers = list(profile.source_components)
    target_markers = list(profile.target_components)
    bindings = {
        "link": {
            "kind": "relation",
            "type": profile.relation_type,
            "source": "$source",
            "target": "$target",
            "requires": [RELATION_COMPONENT],
        },
        "source": {"kind": "entity", "requires": source_markers},
        "target": {"kind": "entity", "requires": target_markers},
        "area": {"kind": "entity", "requires": ["pmw_gameplay_area"]},
        "actor": {"kind": "entity", "requires": ["pmw_gameplay_actor"]},
        "clock": {"kind": "entity", "requires": ["pmw_gameplay_clock"]},
        "actor_location": {
            "kind": "relation", "type": "located_in",
            "source": "$actor", "target": "$area",
        },
    }
    identity = [
        {"ref": "$link.id", "eq": profile.relation_id},
        {"ref": "$link.type", "eq": profile.relation_type},
        {"ref": "$link.source", "eq": profile.source_entity_id},
        {"ref": "$link.target", "eq": profile.target_entity_id},
        {"ref": "$source.id", "eq": profile.source_entity_id},
        {"ref": "$target.id", "eq": profile.target_entity_id},
        {"ref": "$area.id", "eq": profile.area_id},
        {"ref": f"{root}.profile_id", "eq": profile.id},
        {"ref": f"{root}.profile_hash", "eq": profile.profile_hash},
        {"ref": f"{root}.owner", "eq": profile.owner},
    ]
    state_identity = [item for item in identity if item["ref"] != "$link.type"]
    modify_conditions = [
        {"event.type": {"eq": RELATION_MODIFY_EVENT}},
        {"ref": "$clock.id", "eq": clock_id},
        {"ref": "$clock.pmw_gameplay_clock.last_completed_step", "eq": "$event.time"},
        *identity,
        {"ref": "$actor.id", "eq": profile.owner},
        {"ref": "$event.source", "eq": profile.owner},
        {"ref": "$event.target", "eq": profile.relation_id},
        {"ref": "$event.payload.profile_id", "eq": profile.id},
        {"ref": "$event.payload.profile_hash", "eq": profile.profile_hash},
        {"ref": "$event.payload.relation_id", "eq": profile.relation_id},
        {"ref": "$event.payload.relation_type", "eq": profile.relation_type},
        {"ref": "$event.payload.source_entity_id", "eq": profile.source_entity_id},
        {"ref": "$event.payload.target_entity_id", "eq": profile.target_entity_id},
        {"ref": "$event.payload.owner", "eq": profile.owner},
        {"ref": "$event.payload.area_id", "eq": profile.area_id},
        {"ref": "$event.payload.base_enabled", "eq": f"{root}.base_enabled"},
        {"ref": "$event.payload.enabled", "eq": True},
        {"ref": "$event.payload.enabled", "neq": False},
        {"ref": "$event.payload.started_at", "eq": "$event.time"},
        {"ref": "$event.payload.expires_at", "gt": "$event.time"},
        {"ref": "$event.payload.expires_at", "lte": {
            "add": ["$event.time", profile.max_duration_ticks]
        }},
        {"ref": f"{root}.active", "eq": False},
        {"ref": f"{root}.enabled", "eq": None},
        {"ref": f"{root}.started_at", "eq": None},
        {"ref": f"{root}.expires_at", "eq": None},
        {"ref": f"{root}.expiry_handle", "eq": None},
        {"ref": f"{root}.effective_enabled", "eq": f"{root}.base_enabled"},
    ]
    modify_conditions_off = [
        {"event.type": {"eq": RELATION_MODIFY_EVENT}},
        {"ref": "$clock.id", "eq": clock_id},
        {"ref": "$clock.pmw_gameplay_clock.last_completed_step", "eq": "$event.time"},
        *identity,
        {"ref": "$actor.id", "eq": profile.owner},
        {"ref": "$event.source", "eq": profile.owner},
        {"ref": "$event.target", "eq": profile.relation_id},
        {"ref": "$event.payload.profile_id", "eq": profile.id},
        {"ref": "$event.payload.profile_hash", "eq": profile.profile_hash},
        {"ref": "$event.payload.relation_id", "eq": profile.relation_id},
        {"ref": "$event.payload.relation_type", "eq": profile.relation_type},
        {"ref": "$event.payload.source_entity_id", "eq": profile.source_entity_id},
        {"ref": "$event.payload.target_entity_id", "eq": profile.target_entity_id},
        {"ref": "$event.payload.owner", "eq": profile.owner},
        {"ref": "$event.payload.area_id", "eq": profile.area_id},
        {"ref": "$event.payload.base_enabled", "eq": f"{root}.base_enabled"},
        {"ref": "$event.payload.enabled", "eq": False},
        {"ref": "$event.payload.started_at", "eq": "$event.time"},
        {"ref": "$event.payload.expires_at", "gt": "$event.time"},
        {"ref": "$event.payload.expires_at", "lte": {
            "add": ["$event.time", profile.max_duration_ticks]
        }},
        {"ref": f"{root}.active", "eq": False},
        {"ref": f"{root}.enabled", "eq": None},
        {"ref": f"{root}.started_at", "eq": None},
        {"ref": f"{root}.expires_at", "eq": None},
        {"ref": f"{root}.expiry_handle", "eq": None},
        {"ref": f"{root}.effective_enabled", "eq": f"{root}.base_enabled"},
    ]

    def modification_law(condition, suffix):
        return {
            "id": f"pmw.v04.sandbox.relation.{profile.id}.modify.{suffix}",
            "mode": "event",
            "priority": 100,
            "bindings": bindings,
            "when": {"all": condition},
            "effects": [
                {"op": "set", "target": f"{root}.active", "value": True},
                {"op": "set", "target": f"{root}.enabled",
                 "value": "$event.payload.enabled"},
                {"op": "set", "target": f"{root}.started_at",
                 "value": "$event.payload.started_at"},
                {"op": "set", "target": f"{root}.expires_at",
                 "value": "$event.payload.expires_at"},
                {"op": "set", "target": f"{root}.expiry_handle",
                 "value": "$event.payload.expiry_handle"},
                {"op": "set", "target": f"{root}.effective_enabled",
                 "value": "$event.payload.enabled"},
                {"op": "schedule_event", "event": {
                    "id": "$event.payload.expiry_handle",
                    "type": RELATION_EXPIRE_EVENT,
                    "time": "$event.payload.expires_at",
                    "source": profile.owner,
                    "target": profile.relation_id,
                    "payload": {
                        "profile_id": profile.id,
                        "profile_hash": profile.profile_hash,
                        "relation_id": profile.relation_id,
                        "owner": profile.owner,
                        "expiry_handle": "$event.payload.expiry_handle",
                    },
                }},
            ],
        }

    laws = [
        modification_law(modify_conditions, "on"),
        modification_law(modify_conditions_off, "off"),
    ]
    expire_conditions = [
        {"event.type": {"eq": RELATION_EXPIRE_EVENT}},
        {"ref": "$link.id", "eq": profile.relation_id},
        {"ref": f"{root}.profile_id", "eq": profile.id},
        {"ref": f"{root}.profile_hash", "eq": profile.profile_hash},
        {"ref": "$event.id", "eq": f"{root}.expiry_handle"},
        {"ref": "$event.target", "eq": profile.relation_id},
        {"ref": "$event.source", "eq": profile.owner},
        {"ref": "$event.payload.profile_id", "eq": profile.id},
        {"ref": "$event.payload.profile_hash", "eq": profile.profile_hash},
        {"ref": "$event.payload.relation_id", "eq": profile.relation_id},
        {"ref": "$event.payload.expiry_handle", "eq": "$event.id"},
        {"ref": "$event.time", "eq": f"{root}.expires_at"},
        {"ref": f"{root}.active", "eq": True},
        {"ref": f"{root}.owner", "eq": profile.owner},
        {"ref": f"{root}.expiry_handle", "eq": "$event.id"},
    ]
    # An owned expiry must remain reachable after legitimate World changes to
    # endpoint markers, Relation type, or Actor location.  The component's
    # profile hash, owner, and current expiry handle are the authority.
    expire_bindings = {
        "link": {
            "kind": "relation",
            "requires": [RELATION_COMPONENT],
        },
    }
    laws.append({
        "id": f"pmw.v04.sandbox.relation.{profile.id}.expire",
        "mode": "event",
        "priority": 100,
        "bindings": expire_bindings,
        "when": {"all": expire_conditions},
        "effects": [
            {"op": "set", "target": f"{root}.active", "value": False},
            {"op": "set", "target": f"{root}.enabled", "value": None},
            {"op": "set", "target": f"{root}.started_at", "value": None},
            {"op": "set", "target": f"{root}.expires_at", "value": None},
            {"op": "set", "target": f"{root}.expiry_handle", "value": None},
            {"op": "cancel_scheduled", "value": "$event.id"},
        ],
    })
    derive_bindings = {
        "link": {
            "kind": "relation",
            "requires": [RELATION_COMPONENT],
        },
    }
    derive_identity = [
        {"ref": "$link.id", "eq": profile.relation_id},
        {"ref": f"{root}.profile_id", "eq": profile.id},
        {"ref": f"{root}.profile_hash", "eq": profile.profile_hash},
        {"ref": f"{root}.owner", "eq": profile.owner},
    ]
    derive_cases = (
        ("active.on", [{"ref": f"{root}.active", "eq": True},
                       {"ref": f"{root}.enabled", "eq": True},
                       {"ref": f"{root}.effective_enabled", "eq": False}], True),
        ("active.off", [{"ref": f"{root}.active", "eq": True},
                        {"ref": f"{root}.enabled", "eq": False},
                        {"ref": f"{root}.effective_enabled", "eq": True}], False),
        ("base.on", [{"ref": f"{root}.active", "eq": False},
                     {"ref": f"{root}.enabled", "eq": None},
                     {"ref": f"{root}.base_enabled", "eq": True},
                     {"ref": f"{root}.effective_enabled", "eq": False}], True),
        ("base.off", [{"ref": f"{root}.active", "eq": False},
                      {"ref": f"{root}.enabled", "eq": None},
                      {"ref": f"{root}.base_enabled", "eq": False},
                      {"ref": f"{root}.effective_enabled", "eq": True}], False),
    )
    for suffix, mismatch, value in derive_cases:
        laws.append({
            "id": f"pmw.v04.sandbox.relation.{profile.id}.derive.{suffix}",
            "mode": "state",
            "priority": 100,
            "bindings": derive_bindings,
            "when": {"all": [*derive_identity, *mismatch]},
            "effects": [{
                "op": "set",
                "target": f"{root}.effective_enabled",
                "value": value,
            }],
        })
    return laws


def _preflight(
    controller: RelationController,
    session: GameplaySession,
    profile: RelationProfile,
    *,
    owner: str,
) -> None:
    if owner != profile.owner:
        raise GameplayContractError("Relation owner does not match the trusted profile")
    relation = session.state.relations.get(profile.relation_id)
    if relation is None:
        raise GameplayContractError("trusted Relation is unavailable")
    if (
        relation.type != profile.relation_type
        or relation.source != profile.source_entity_id
        or relation.target != profile.target_entity_id
    ):
        raise GameplayContractError("trusted Relation endpoints/type changed")
    source = session.state.entities.get(profile.source_entity_id)
    target = session.state.entities.get(profile.target_entity_id)
    if source is None or target is None:
        raise GameplayContractError("trusted Relation endpoint is unavailable")
    if not all(marker in source.components for marker in profile.source_components):
        raise GameplayContractError("trusted Relation source markers changed")
    if not all(marker in target.components for marker in profile.target_components):
        raise GameplayContractError("trusted Relation target markers changed")
    component = relation.components.get(RELATION_COMPONENT)
    if not isinstance(component, Mapping) or set(component) != {
        "profile_id", "profile_hash", "owner", "base_enabled", "effective_enabled",
        "active", "enabled", "started_at", "expires_at", "expiry_handle",
    }:
        raise GameplayContractError("trusted Relation component shape is invalid")
    if (
        component.get("profile_id") != profile.id
        or component.get("profile_hash") != profile.profile_hash
        or component.get("owner") != profile.owner
        or not isinstance(component.get("base_enabled"), bool)
        or not isinstance(component.get("effective_enabled"), bool)
        or not isinstance(component.get("active"), bool)
        or (component.get("enabled") is not None
            and not isinstance(component.get("enabled"), bool))
    ):
        raise GameplayContractError("trusted Relation component identity/markers changed")
    if component["active"]:
        raise GameplayContractError("trusted Relation modifier slot is already active")
    if not (
        component.get("enabled") is None
        and component.get("started_at") is None
        and component.get("expires_at") is None
        and component.get("expiry_handle") is None
    ):
        raise GameplayContractError("trusted Relation modifier slot is not empty")
    if component["effective_enabled"] != component["base_enabled"]:
        raise GameplayContractError("trusted Relation effective state is not closed")
    if _endpoint_area(session, relation.source) != profile.area_id:
        raise GameplayContractError("Relation source is remote for the trusted Area")
    if _endpoint_area(session, relation.target) != profile.area_id:
        raise GameplayContractError("Relation target is remote for the trusted Area")
    if not isinstance(relation.source, str) or not isinstance(relation.target, str):
        raise GameplayContractError("trusted Relation endpoints are invalid")
    actor = session.state.entities.get(profile.owner)
    if actor is None or "pmw_gameplay_actor" not in actor.components:
        raise GameplayContractError("trusted Relation owner is not an Actor")
    if _endpoint_area(session, profile.owner) != profile.area_id:
        raise GameplayContractError(
            "trusted Relation owner is missing, remote, or ambiguous for this Area"
        )
    clock = session.state.entities.get(controller.clock_id)
    clock_component = (
        clock.components.get("pmw_gameplay_clock")
        if clock is not None else None
    )
    if not isinstance(clock_component, Mapping):
        raise GameplayContractError("Relation modify requires a complete World Tick boundary")
    completed = clock_component.get("last_completed_step")
    if (
        isinstance(completed, bool)
        or not isinstance(completed, int)
        or session.state.sim_time != completed
        or clock_component.get("next_step") != completed + 1
        or clock_component.get("next_time") != completed + 1
    ):
        raise GameplayContractError("Relation modify requires a complete World Tick boundary")


def _assert_modified(session: GameplaySession, prepared: Mapping[str, Any]) -> None:
    relation = session.state.relations.get(prepared["relation_id"])
    component = (
        relation.components.get(RELATION_COMPONENT)
        if relation is not None else None
    )
    scheduled = [
        event for event in session.state.scheduled_events
        if event.id == prepared["expiry_handle"]
    ]
    if (
        not isinstance(component, Mapping)
        or component.get("profile_hash") != prepared["profile_hash"]
        or component.get("active") is not True
        or component.get("enabled") is not prepared["enabled"]
        or component.get("started_at") != prepared["started_at"]
        or component.get("expires_at") != prepared["expires_at"]
        or component.get("expiry_handle") != prepared["expiry_handle"]
        or component.get("effective_enabled") is not prepared["enabled"]
        or len(scheduled) != 1
        or scheduled[0].type != RELATION_EXPIRE_EVENT
        or scheduled[0].time != prepared["expires_at"]
        or scheduled[0].target != prepared["relation_id"]
    ):
        raise GameplayContractError("Relation modify did not activate the trusted slot")


def _assert_active_limit(
    controller: RelationController,
    session: GameplaySession,
    profile: RelationProfile,
) -> None:
    active = 0
    for row in controller.profiles:
        relation = session.state.relations.get(row.relation_id)
        component = (
            relation.components.get(RELATION_COMPONENT)
            if relation is not None else None
        )
        if (
            isinstance(component, Mapping)
            and component.get("profile_id") == row.id
            and component.get("profile_hash") == row.profile_hash
            and component.get("active") is True
        ):
            active += 1
    if active >= controller.limits.max_active:
        raise GameplayContractError("active Relation modifiers exceed max_active")


def _expiry_handle(
    profile: RelationProfile,
    owner: str,
    component: Mapping[str, Any],
    enabled: bool | None,
    duration_ticks: int,
    started_at: float,
    expires_at: float,
) -> str:
    payload = {
        "profile": profile.id,
        "relation": profile.relation_id,
        "owner": owner,
        "base": component["base_enabled"],
        "enabled": enabled,
        "duration": duration_ticks,
        "started": started_at,
        "expiry": expires_at,
    }
    token = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()[:24]
    return f"pmw:v04:relation-expiry:{profile.id}:{token}"


def _event_id(prepared: Mapping[str, Any]) -> str:
    token = hashlib.sha256(
        json.dumps(prepared, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()[:24]
    return f"pmw:v04:relation-modify:{prepared['profile_id']}:{token}"


def _endpoint_area(session: GameplaySession, entity_id: str) -> str | None:
    entity = session.state.entities.get(entity_id)
    if entity is None:
        return None
    areas = sorted(
        relation.target for relation in session.state.relations.values()
        if relation.type == "located_in" and relation.source == entity_id
    )
    if len(areas) != 1:
        return None
    area = session.state.entities.get(areas[0])
    if area is None or "pmw_gameplay_area" not in area.components:
        return None
    return area.id


def _markers(value: Iterable[str], name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (tuple, list)):
        raise GameplayContractError(f"{name} must be a sequence of marker names")
    items = tuple(value)
    if (
        not items
        or any(not isinstance(item, str) or not _ENTITY_ID.fullmatch(item) for item in items)
        or len(items) != len(set(items))
    ):
        raise GameplayContractError(f"{name} must be a unique non-empty marker tuple")
    return tuple(items)


def _bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise GameplayContractError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _duration(value: Any, name: str) -> int:
    return _bounded_int(value, name, 1, 10_000)


def _entity_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or _ENTITY_ID.fullmatch(value) is None:
        raise GameplayContractError(f"{name} is invalid")
    return value
