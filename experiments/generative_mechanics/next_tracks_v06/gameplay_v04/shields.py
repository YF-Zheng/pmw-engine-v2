"""Bounded, source-owned shield layers with a public aggregate value."""

from __future__ import annotations

import math
from typing import Any

from .contracts import GameplayContractError


SHIELD_COMPONENT = "pmw_gameplay_shields"
SHIELD_SLOTS = 8
LEGACY_SOURCE = "pmw.v04.shield.legacy"


def neutral_shield_layer() -> dict[str, Any]:
    return {
        "active": False, "layer_id": None, "source_id": None,
        "owner_id": None, "granted": 0.0, "remaining": 0.0,
        "sequence": -1, "status_instance_id": None,
    }


def shield_component(slot_count: int = SHIELD_SLOTS) -> dict[str, Any]:
    return {"slots": {f"slot_{index}": neutral_shield_layer()
                      for index in range(slot_count)}}


def reconcile_shields(actor: dict[str, Any], component: dict[str, Any]) -> None:
    """Reconcile legacy scalar edits into layers, then publish their exact sum."""
    slots = component.get("slots")
    if not isinstance(slots, dict) or not slots:
        raise GameplayContractError("shield component slots are invalid")
    public = actor.get("shield", 0.0)
    if isinstance(public, bool) or not isinstance(public, (int, float)) or not math.isfinite(public) or public < 0:
        raise GameplayContractError("Actor shield is invalid")
    total = sum(float(layer.get("remaining", 0.0)) for layer in slots.values()
                if layer.get("active"))
    delta = float(public) - total
    if delta > 1e-12:
        legacy = next((layer for layer in slots.values()
                       if layer.get("active") and layer.get("source_id") == LEGACY_SOURCE), None)
        if legacy is None:
            name = next((name for name, layer in sorted(slots.items())
                         if not layer.get("active")), None)
            if name is None:
                raise GameplayContractError("shield layer capacity exhausted")
            legacy = slots[name] = {
                "active": True, "layer_id": name, "source_id": LEGACY_SOURCE,
                "owner_id": None, "granted": 0.0, "remaining": 0.0,
                "sequence": 0, "status_instance_id": None,
            }
        legacy["granted"] += delta
        legacy["remaining"] += delta
    elif delta < -1e-12:
        _consume(slots, -delta)
    actor["shield"] = _total(slots)


def grant_shield(actor: dict[str, Any], component: dict[str, Any], *,
                 source_id: str, owner_id: str, amount: float) -> str:
    reconcile_shields(actor, component)
    slots = component["slots"]
    match = next(((name, layer) for name, layer in sorted(slots.items())
                  if (layer["active"] and layer["source_id"] == source_id and
                      layer["owner_id"] == owner_id)), None)
    if match is None:
        name = next((name for name, layer in sorted(slots.items()) if not layer["active"]), None)
        if name is None:
            raise GameplayContractError("shield layer capacity exhausted")
        sequence = max((layer["sequence"] for layer in slots.values() if layer["active"]), default=0) + 1
        slots[name] = {
            "active": True, "layer_id": name, "source_id": source_id,
            "owner_id": owner_id, "granted": float(amount),
            "remaining": float(amount), "sequence": sequence,
            "status_instance_id": None,
        }
    else:
        name, layer = match
        # Refresh changes lifetime/ownership only. Consumed capacity is never restored.
        layer["granted"] = max(layer["granted"], float(amount))
        layer["owner_id"] = owner_id
    actor["shield"] = _total(slots)
    return name


def bind_layer_to_status(component: dict[str, Any], slot: str,
                         status_instance_id: str) -> None:
    layer = component["slots"].get(slot)
    if not layer or not layer.get("active"):
        raise GameplayContractError("shield ownership layer is missing")
    layer["status_instance_id"] = status_instance_id


def release_status_layer(actor: dict[str, Any], component: dict[str, Any],
                         status: dict[str, Any]) -> None:
    """Release exactly the remaining layer owned by one replaced status."""
    layer_slot = status.get("shield_layer_slot")
    if layer_slot is None:
        return
    layer = component.get("slots", {}).get(layer_slot)
    if (not isinstance(layer, dict) or not layer.get("active") or
            layer.get("status_instance_id") != status.get("instance_id")):
        raise GameplayContractError("replaced status shield ownership is invalid")
    layer.clear()
    layer.update(neutral_shield_layer())
    actor["shield"] = _total(component["slots"])


def validate_status_shield_ownership(status_component: dict[str, Any],
                                     component: dict[str, Any]) -> None:
    """Require every temporary shield layer and status pointer to agree."""
    statuses = status_component.get("slots")
    layers = component.get("slots")
    if not isinstance(statuses, dict) or not isinstance(layers, dict):
        raise GameplayContractError("status/shield ownership components are invalid")
    active_statuses: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for status_slot, status in statuses.items():
        if status.get("active") and status.get("instance_id") is not None:
            active_statuses.setdefault(status["instance_id"], []).append((status_slot, status))
    for layer_slot, layer in layers.items():
        instance_id = layer.get("status_instance_id") if layer.get("active") else None
        if instance_id is None:
            continue
        matches = active_statuses.get(instance_id, [])
        if (len(matches) != 1 or matches[0][1].get("shield_layer_slot") != layer_slot or
                not _layer_matches_status_source(layer, matches[0][1])):
            raise GameplayContractError("temporary shield layer has no unique status owner")
    for matches in active_statuses.values():
        for _, status in matches:
            layer_slot = status.get("shield_layer_slot")
            if layer_slot is None:
                continue
            layer = layers.get(layer_slot)
            if (not isinstance(layer, dict) or not layer.get("active") or
                    layer.get("status_instance_id") != status.get("instance_id") or
                    not _layer_matches_status_source(layer, status)):
                raise GameplayContractError("status shield owner does not resolve to its layer")


def migrate_status_shield_ownership(actor: dict[str, Any], status_component: dict[str, Any],
                                    component: dict[str, Any]) -> None:
    """Idempotently discard temporary layers orphaned by pre-Gate-5.2 refresh."""
    reconcile_shields(actor, component)
    statuses = status_component.get("slots", {})
    layers = component.get("slots", {})
    by_instance: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for status_slot, status in statuses.items():
        if status.get("active") and status.get("instance_id") is not None:
            by_instance.setdefault(status["instance_id"], []).append((status_slot, status))

    valid_layers: set[str] = set()
    for instance_matches in by_instance.values():
        for _, status in instance_matches:
            layer_slot = status.get("shield_layer_slot")
            layer = layers.get(layer_slot) if layer_slot is not None else None
            if (len(instance_matches) == 1 and isinstance(layer, dict) and
                    layer.get("active") and
                    layer.get("status_instance_id") == status.get("instance_id") and
                    _layer_matches_status_source(layer, status)):
                valid_layers.add(layer_slot)
            elif layer_slot is not None:
                status["shield_layer_slot"] = None

    for layer_slot, layer in layers.items():
        if (layer.get("active") and layer.get("status_instance_id") is not None and
                layer_slot not in valid_layers):
            layer.clear()
            layer.update(neutral_shield_layer())
    actor["shield"] = _total(layers)
    validate_status_shield_ownership(status_component, component)


def _layer_matches_status_source(layer: dict[str, Any], status: dict[str, Any]) -> bool:
    """Match caster ownership and the action-to-effect source lineage."""
    status_source = status.get("source_id")
    layer_source = layer.get("source_id")
    return bool(
        layer.get("owner_id") == status.get("owner_id")
        and isinstance(status_source, str)
        and isinstance(layer_source, str)
        and layer_source.startswith(f"{status_source}:")
    )


def absorb_damage(actor: dict[str, Any], component: dict[str, Any], amount: float) -> float:
    reconcile_shields(actor, component)
    absorbed = _consume(component["slots"], amount)
    actor["shield"] = _total(component["slots"])
    return absorbed


def _consume(slots: dict[str, dict[str, Any]], amount: float) -> float:
    left = float(amount)
    for _, layer in sorted(slots.items(), key=lambda item: (
            item[1].get("sequence", -1), item[0])):
        if left <= 0 or not layer.get("active"):
            continue
        consumed = min(float(layer["remaining"]), left)
        layer["remaining"] -= consumed
        left -= consumed
        if layer["remaining"] <= 1e-12 and layer.get("status_instance_id") is None:
            layer.clear()
            layer.update(neutral_shield_layer())
    return float(amount) - left


def _total(slots: dict[str, dict[str, Any]]) -> float:
    return sum(float(layer["remaining"]) for layer in slots.values() if layer.get("active"))
