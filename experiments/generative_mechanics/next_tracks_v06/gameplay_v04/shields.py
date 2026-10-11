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
