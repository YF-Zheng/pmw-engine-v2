"""Bounded status definitions and runtime slot values."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

from .contracts import GameplayContractError


CLOCK_UNITS = ("world_tick", "combat_round", "owner_turn")
STACK_POLICIES = ("reject", "refresh", "replace", "add_stacks")
STATUS_COMPONENT = "pmw_gameplay_statuses"
STATUS_CANCEL_EVENT = "pmw.v04.status.cancel"


@dataclass(frozen=True, slots=True)
class DurationSpec:
    unit: str
    amount: int


@dataclass(frozen=True, slots=True)
class StatusSpec:
    id: str
    version: int
    polarity: str
    max_stacks: int
    stack_policy: str
    duration: DurationSpec
    granted_traits: tuple[str, ...] = ()
    periodic_resource: tuple[str, float] | None = None
    on_expire_resource: tuple[str, float] | None = None
    canonical_hash: str = ""


def parse_status_spec(raw: Any, path: str = "$.status") -> StatusSpec:
    required = {"id", "version", "polarity", "max_stacks", "stack_policy", "duration", "granted_traits"}
    optional = {"periodic_resource", "on_expire_resource"}
    if not isinstance(raw, dict) or set(raw) - required - optional or not required <= set(raw):
        raise GameplayContractError(f"{path} has missing or unknown fields")
    if not isinstance(raw["id"], str) or not raw["id"]: raise GameplayContractError(f"{path}.id is invalid")
    if isinstance(raw["version"], bool) or not isinstance(raw["version"], int) or raw["version"] < 1: raise GameplayContractError(f"{path}.version is invalid")
    if raw["polarity"] not in {"buff", "debuff", "neutral"}: raise GameplayContractError(f"{path}.polarity is invalid")
    if isinstance(raw["max_stacks"], bool) or not isinstance(raw["max_stacks"], int) or not 1 <= raw["max_stacks"] <= 99: raise GameplayContractError(f"{path}.max_stacks is invalid")
    if raw["stack_policy"] not in STACK_POLICIES: raise GameplayContractError(f"{path}.stack_policy is invalid")
    duration = raw["duration"]
    if not isinstance(duration, dict) or set(duration) != {"unit", "amount"} or duration["unit"] not in CLOCK_UNITS:
        raise GameplayContractError(f"{path}.duration is invalid")
    if isinstance(duration["amount"], bool) or not isinstance(duration["amount"], int) or duration["amount"] < 1:
        raise GameplayContractError(f"{path}.duration.amount must be positive")
    traits = raw["granted_traits"]
    if not isinstance(traits, list) or any(not isinstance(x, str) or not x for x in traits) or len(set(traits)) != len(traits):
        raise GameplayContractError(f"{path}.granted_traits is invalid")
    periodic = raw.get("periodic_resource")
    if periodic is not None:
        if not isinstance(periodic, dict) or set(periodic) != {"resource", "delta"} or periodic["resource"] not in {"hp", "mana", "shield"}:
            raise GameplayContractError(f"{path}.periodic_resource is invalid")
        delta = periodic["delta"]
        if isinstance(delta, bool) or not isinstance(delta, (int, float)) or not math.isfinite(delta):
            raise GameplayContractError(f"{path}.periodic_resource.delta is invalid")
        periodic = (periodic["resource"], float(delta))
    on_expire = raw.get("on_expire_resource")
    if on_expire is not None:
        if not isinstance(on_expire, dict) or set(on_expire) != {"resource", "value"} or on_expire["resource"] not in {"hp", "mana", "shield"}:
            raise GameplayContractError(f"{path}.on_expire_resource is invalid")
        value = on_expire["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise GameplayContractError(f"{path}.on_expire_resource.value is invalid")
        on_expire = (on_expire["resource"], float(value))
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return StatusSpec(raw["id"], raw["version"], raw["polarity"], raw["max_stacks"], raw["stack_policy"],
                      DurationSpec(duration["unit"], duration["amount"]), tuple(traits), periodic, on_expire,
                      hashlib.sha256(canonical).hexdigest())


def neutral_status_slot() -> dict[str, Any]:
    return {"active": False, "instance_id": None, "spec_id": None, "spec_hash": None, "source_id": None,
            "owner_id": None, "stacks": 0, "remaining": 0, "clock_unit": None,
            "granted_traits": [], "expiry_handle": None}


def active_status_slot(spec: StatusSpec, *, instance_id: str, source_id: str, owner_id: str,
                       stacks: int = 1, expiry_handle: str | None = None) -> dict[str, Any]:
    return {"active": True, "instance_id": instance_id, "spec_id": spec.id, "spec_hash": spec.canonical_hash,
            "source_id": source_id, "owner_id": owner_id, "stacks": stacks,
            "remaining": spec.duration.amount, "clock_unit": spec.duration.unit,
            "granted_traits": list(spec.granted_traits), "expiry_handle": expiry_handle}


def cancel_status(session, registry, *, owner_id: str, instance_id: str, requester_id: str):
    from pmw import Event
    entity = session.state.entities.get(owner_id)
    slots = entity.components.get(STATUS_COMPONENT, {}).get("slots", {}) if entity else {}
    matches = [(slot, value) for slot, value in slots.items() if value.get("active") and value.get("instance_id") == instance_id]
    if len(matches) != 1: raise GameplayContractError("status instance ownership is not unique")
    slot, value = matches[0]
    spec = registry.statuses.get(value["spec_id"])
    if spec is None or value["owner_id"] != requester_id: raise GameplayContractError("status cancellation owner mismatch")
    return session.runtime.run_event(Event(
        f"pmw:v04:status-cancel:{instance_id}", STATUS_CANCEL_EVENT, session.state.sim_time,
        requester_id, owner_id, {"slot": slot, "instance_id": instance_id, "spec_id": spec.id,
                                 "spec_hash": spec.canonical_hash, "owner_id": owner_id}
    ))
