"""Bounded 6+6/6 skill loadouts changed only by traced PMW events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pmw import Event, parse_law

from .actions import ACTOR_COMPONENT
from .contracts import GameplayContractError
from .skills import MechanismRegistryManifest, SkillBlueprint


LOADOUT_EVENT = "pmw.v04.loadout.change"


@dataclass(frozen=True, slots=True)
class SkillRef:
    id: str
    version: int
    canonical_hash: str
    kind: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "version": self.version, "canonical_hash": self.canonical_hash, "kind": self.kind}


def skill_ref(skill: SkillBlueprint) -> SkillRef:
    return SkillRef(skill.id, skill.version, skill.canonical_hash, skill.kind)


def build_loadout_laws() -> tuple[dict, ...]:
    law = {
        "id": "pmw.v04.loadout.change", "mode": "event", "priority": 100,
        "bindings": {"actor": {"kind": "entity", "requires": [ACTOR_COMPONENT]}},
        "when": {"all": [
            {"event.type": {"eq": LOADOUT_EVENT}},
            {"ref": "$actor.id", "eq": "$event.source"},
            {"ref": f"$actor.{ACTOR_COMPONENT}.active_equipped", "eq": "$event.payload.before.active_equipped"},
            {"ref": f"$actor.{ACTOR_COMPONENT}.active_stowed", "eq": "$event.payload.before.active_stowed"},
            {"ref": f"$actor.{ACTOR_COMPONENT}.passive_equipped", "eq": "$event.payload.before.passive_equipped"},
        ]},
        "effects": [
            {"op": "set", "target": f"$actor.{ACTOR_COMPONENT}.active_equipped", "value": "$event.payload.after.active_equipped"},
            {"op": "set", "target": f"$actor.{ACTOR_COMPONENT}.active_stowed", "value": "$event.payload.after.active_stowed"},
            {"op": "set", "target": f"$actor.{ACTOR_COMPONENT}.passive_equipped", "value": "$event.payload.after.passive_equipped"},
        ],
    }
    parse_law(law)
    return (law,)


def change_loadout(session, manifest: MechanismRegistryManifest, *, actor_id: str, operation: str,
                   skill: SkillRef | None = None, slot: int | None = None, other_slot: int | None = None):
    actor_entity = session.state.entities.get(actor_id)
    if actor_entity is None or ACTOR_COMPONENT not in actor_entity.components:
        raise GameplayContractError("loadout owner is not an Actor")
    actor = actor_entity.components[ACTOR_COMPONENT]
    if actor.get("in_combat", False):
        raise GameplayContractError("loadout is locked during combat")
    before = _snapshot(actor)
    after = {key: list(value) for key, value in before.items()}
    if skill is not None:
        _validate_ref(skill, manifest)
    if operation in {"equip_active", "stow_active", "equip_passive"}:
        if skill is None or slot is None:
            raise GameplayContractError("install operation requires skill and slot")
        key = {"equip_active": "active_equipped", "stow_active": "active_stowed", "equip_passive": "passive_equipped"}[operation]
        expected_kind = "passive_blueprint" if key == "passive_equipped" else "skill_blueprint"
        if skill.kind != expected_kind:
            raise GameplayContractError("skill kind does not match loadout container")
        _slot(slot, key)
        if after[key][slot] is not None:
            raise GameplayContractError("loadout slot is occupied")
        if any(_same_ref(skill, row) for rows in after.values() for row in rows if row is not None):
            raise GameplayContractError("skill version is already present in this loadout")
        after[key][slot] = skill.to_dict()
    elif operation in {"move_active", "unstow_active"}:
        if slot is None or other_slot is None:
            raise GameplayContractError(f"{operation} requires two slots")
        _slot(slot, "active_equipped"); _slot(other_slot, "active_stowed")
        source_key, destination_key = (("active_equipped", "active_stowed")
                                       if operation == "move_active"
                                       else ("active_stowed", "active_equipped"))
        source_slot, destination_slot = ((slot, other_slot)
                                         if operation == "move_active"
                                         else (other_slot, slot))
        if after[source_key][source_slot] is None:
            raise GameplayContractError("source slot is empty")
        if after[destination_key][destination_slot] is not None:
            raise GameplayContractError("destination slot is occupied")
        after[destination_key][destination_slot] = after[source_key][source_slot]
        after[source_key][source_slot] = None
    elif operation in {"unload_active", "unload_stowed", "unload_passive"}:
        if slot is None:
            raise GameplayContractError("unload requires slot")
        key = {"unload_active": "active_equipped", "unload_stowed": "active_stowed", "unload_passive": "passive_equipped"}[operation]
        _slot(slot, key)
        if after[key][slot] is None:
            raise GameplayContractError("cannot unload an empty slot")
        after[key][slot] = None
    else:
        raise GameplayContractError("unknown loadout operation")
    result = session.runtime.run_event(Event(
        f"pmw:v04:loadout:{actor_id}:{session.state.tick}:{operation}", LOADOUT_EVENT,
        session.state.sim_time, actor_id, actor_id,
        {"operation": operation, "before": before, "after": after},
    ))
    if not result.changed:
        raise GameplayContractError("loadout transaction did not commit")
    return result


def _snapshot(actor: dict) -> dict[str, list]:
    result = {}
    for key in ("active_equipped", "active_stowed", "passive_equipped"):
        rows = actor.get(key)
        if not isinstance(rows, list) or len(rows) != 6:
            raise GameplayContractError("Actor loadout shape is invalid")
        result[key] = [dict(row) if isinstance(row, dict) else row for row in rows]
    return result


def _validate_ref(ref: SkillRef, manifest: MechanismRegistryManifest) -> None:
    matches = [item for item in manifest.entries if item.skill_id == ref.id and item.version == ref.version]
    if len(matches) != 1 or not matches[0].enabled or matches[0].canonical_hash != ref.canonical_hash or matches[0].kind != ref.kind:
        raise GameplayContractError("skill reference is not enabled in the trusted manifest")


def _same_ref(ref: SkillRef, row: dict) -> bool:
    return row.get("id") == ref.id and row.get("version") == ref.version


def _slot(index: int, name: str) -> None:
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < 6:
        raise GameplayContractError(f"{name} slot must be in [0, 5]")
