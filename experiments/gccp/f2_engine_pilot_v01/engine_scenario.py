"""Construct the four F2 hidden worlds on the real PMW Gameplay runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pmw import parse_law

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRegistry
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry_document
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_actor,
    instantiate_area,
    parse_actor_blueprint,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    CompiledGate3Content,
    Gate3Content,
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import change_loadout, skill_ref
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    MaterialDefinition,
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import MechanismRegistryRuntime
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import clock_entity
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import SkillBlueprint, parse_skill_blueprint
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import initialize_time_budget
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import build_gameplay_world


F2_COMPONENT = "gccp_f2_private"
ACTOR_ID = "f2_researcher"
AREA_ID = "f2_facility"
DIAGNOSTIC_MATERIAL = "diagnostic_blank"
REPAIR_MATERIAL = "repair_kit"
ROOTS = ("water", "resonance")
WORLD_PRIOR = {
    ("water", "water"): 0.325,
    ("water", "resonance"): 0.325,
    ("resonance", "water"): 0.175,
    ("resonance", "resonance"): 0.175,
}


@dataclass(slots=True)
class F2Runtime:
    runtime: MechanismRegistryRuntime
    compiled: CompiledGate3Content
    content: Gate3Content
    probe_blueprints: dict[str, SkillBlueprint]
    materials: dict[str, MaterialDefinition]

    @property
    def session(self):
        return self.runtime.session


def build_f2_runtime(hidden_root: str, hidden_interface: str, *, time_budget: int = 12) -> F2Runtime:
    if hidden_root not in ROOTS or hidden_interface not in ROOTS:
        raise ValueError("F2 hidden values must be water or resonance")
    actor = instantiate_actor(parse_actor_blueprint(_actor_document()), ACTOR_ID, controller="human")
    area = instantiate_area(parse_area_blueprint(_area_document()), AREA_ID)
    area.components[F2_COMPONENT] = {
        "hidden_root": hidden_root,
        "hidden_interface": hidden_interface,
        "damage": 1.0,
        "stability": 100.0,
        "calibrated": False,
        "measured_interface": None,
        "forged_probe": None,
        "probe_used": False,
        "probe_implemented": False,
        "repair_mode": None,
    }
    world = build_gameplay_world(
        "gccp_f2_engine_v01",
        areas=(area,),
        actors=(actor,),
        placements=((ACTOR_ID, AREA_ID),),
    )
    clock = clock_entity()
    world.entities[clock.id] = clock

    base_registry = ActionRegistry.parse(basic_registry_document(wait_mana=0.0))
    materials = {item.id: item for item in (_diagnostic_material(), _repair_material())}
    repairs = tuple(
        parse_skill_blueprint(
            _repair_blueprint(root),
            base_registry.statuses,
            material_authority((materials[REPAIR_MATERIAL],)),
        )
        for root in ROOTS
    )
    probes = {
        root: parse_skill_blueprint(
            _probe_blueprint(root),
            base_registry.statuses,
            material_authority((materials[DIAGNOSTIC_MATERIAL],)),
        )
        for root in ROOTS
    }
    content = make_content(
        base_registry,
        skills=repairs,
        material_ids=(DIAGNOSTIC_MATERIAL, REPAIR_MATERIAL),
    )
    initialized = initialize_content_world(world, content)
    inventory = initialized.entities[ACTOR_ID].components["pmw_gameplay_material_inventory"]["quantities"]
    inventory[DIAGNOSTIC_MATERIAL] = 1
    inventory[REPAIR_MATERIAL] = 1
    initialized = initialize_time_budget(initialized, time_budget)
    base_compiled = compile_content(content)
    laws = tuple(sorted((*base_compiled.laws, *f2_laws()), key=lambda row: row["id"]))
    for law in laws:
        parse_law(law)
    compiled = CompiledGate3Content(content, laws)
    session = build_content_session(initialized, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for slot, skill in enumerate(repairs):
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=ACTOR_ID,
            operation="equip_active",
            skill=skill_ref(skill),
            slot=slot,
        )
    return F2Runtime(runtime, compiled, content, probes, materials)


def f2_laws() -> tuple[dict[str, Any], ...]:
    laws: list[dict[str, Any]] = []
    identity = {"area": {"kind": "entity", "requires": [F2_COMPONENT, "pmw_gameplay_dynamics"]}}
    for root in ROOTS:
        drive = (
            {"max": [0.0, {"sub": [5.0, "$area.pmw_gameplay_dynamics.fields.water.value"]}]}
            if root == "water"
            else {"max": [0.0, {"sub": ["$area.pmw_gameplay_dynamics.fields.resonance.value", 5.0]}]}
        )
        next_damage = {"div": [{"add": [f"$area.{F2_COMPONENT}.damage", drive]}, 2.0]}
        laws.append({
            "id": f"gccp.f2.physics.{root}",
            "mode": "event",
            "priority": 200,
            "bindings": identity,
            "when": {"all": [
                {"event.type": {"eq": "pmw.v04.world_tick"}},
                {"ref": f"$area.{F2_COMPONENT}.hidden_root", "eq": root},
            ]},
            "effects": [
                {"op": "set", "target": f"$area.{F2_COMPONENT}.damage", "value": next_damage},
                {"op": "set", "target": f"$area.{F2_COMPONENT}.stability", "value": {
                    "sub": [
                        {"add": [f"$area.{F2_COMPONENT}.stability", 6.0]},
                        {"mul": [8.0, next_damage]},
                    ]
                }},
            ],
        })
        laws.append({
            "id": f"gccp.f2.calibrate.{root}", "mode": "event", "priority": 200,
            "bindings": identity,
            "when": {"all": [
                {"event.type": {"eq": "gccp.f2.calibrate"}},
                {"ref": f"$area.{F2_COMPONENT}.hidden_interface", "eq": root},
                {"ref": f"$area.{F2_COMPONENT}.calibrated", "eq": False},
            ]},
            "effects": [
                {"op": "set", "target": f"$area.{F2_COMPONENT}.calibrated", "value": True},
                {"op": "set", "target": f"$area.{F2_COMPONENT}.measured_interface", "value": root},
            ],
        })
        laws.extend(_probe_laws(root, identity))
        laws.append(_repair_law(root, identity))
    for root in ROOTS:
        laws.append({
            "id": f"gccp.f2.forge.{root}", "mode": "event", "priority": 200,
            "bindings": {
                **identity,
                "actor": {"kind": "entity", "requires": ["pmw_gameplay_material_inventory"]},
            },
            "when": {"all": [
                {"event.type": {"eq": "gccp.f2.forge"}},
                {"ref": "$event.payload.probe_kind", "eq": root},
                {"ref": "$actor.id", "eq": "$event.source"},
                {"ref": f"$area.{F2_COMPONENT}.forged_probe", "eq": None},
                {"ref": f"$actor.pmw_gameplay_material_inventory.quantities.{DIAGNOSTIC_MATERIAL}", "eq": 1},
            ]},
            "effects": [
                {"op": "set", "target": f"$actor.pmw_gameplay_material_inventory.quantities.{DIAGNOSTIC_MATERIAL}", "value": 0},
                {"op": "set", "target": f"$area.{F2_COMPONENT}.forged_probe", "value": root},
            ],
        })
    return tuple(laws)


def _probe_laws(root: str, identity: dict[str, Any]) -> list[dict[str, Any]]:
    laws = []
    field = "water" if root == "water" else "resonance"
    value = 6.0 if root == "water" else 4.0
    for interface in ROOTS:
        effects = [
            {"op": "set", "target": f"$area.{F2_COMPONENT}.probe_used", "value": True},
            {"op": "set", "target": f"$area.{F2_COMPONENT}.probe_implemented", "value": interface == root},
        ]
        if interface == root:
            effects.append({"op": "set", "target": f"$area.pmw_gameplay_dynamics.fields.{field}.value", "value": value})
        laws.append({
            "id": f"gccp.f2.probe.{root}.interface_{interface}", "mode": "event", "priority": 200,
            "bindings": identity,
            "when": {"all": [
                {"event.type": {"eq": "pmw.v04.action.resolve"}},
                {"ref": "$event.payload.action_id", "eq": f"f2_probe_{root}"},
                {"ref": f"$area.{F2_COMPONENT}.hidden_interface", "eq": interface},
                {"ref": f"$area.{F2_COMPONENT}.forged_probe", "eq": root},
                {"ref": f"$area.{F2_COMPONENT}.probe_used", "eq": False},
            ]},
            "effects": effects,
        })
    return laws


def _repair_law(root: str, identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"gccp.f2.repair_receipt.{root}", "mode": "event", "priority": 200,
        "bindings": {
            **identity,
            "actor": {"kind": "entity", "requires": ["pmw_gameplay_material_inventory"]},
        },
        "when": {"all": [
            {"event.type": {"eq": "pmw.v04.action.resolve"}},
            {"ref": "$event.payload.action_id", "eq": f"f2_repair_{root}"},
            {"ref": "$actor.id", "eq": "$event.source"},
            {"ref": f"$actor.pmw_gameplay_material_inventory.quantities.{REPAIR_MATERIAL}", "eq": 1},
            {"ref": f"$area.{F2_COMPONENT}.repair_mode", "eq": None},
        ]},
        "effects": [
            {"op": "set", "target": f"$actor.pmw_gameplay_material_inventory.quantities.{REPAIR_MATERIAL}", "value": 0},
            {"op": "set", "target": f"$area.{F2_COMPONENT}.repair_mode", "value": root},
        ],
    }


def _actor_document() -> dict[str, Any]:
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "actor_blueprint", "id": "f2_researcher_bp",
        "hp": {"max": 100, "initial": 100},
        "mana": {"max": 10, "initial": 10, "dynamics": None},
        "attributes": {"power": 0, "control": 0, "resilience": 0, "agility": 0},
        "traits": [],
    }


def _area_document() -> dict[str, Any]:
    def field(field_id: str, initial: float) -> dict[str, Any]:
        return {
            "id": field_id, "domain": {"min": 0, "max": 10}, "initial": initial,
            "target": initial, "rate": 1.0, "curve": "linear",
            "max_persistent_patches": 2, "max_temporary_modifiers": 4,
        }
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint", "id": "f2_facility_bp",
        "fields": [field("water", 4.0), field("resonance", 6.0)],
    }


def _diagnostic_material() -> MaterialDefinition:
    return parse_material({
        "id": DIAGNOSTIC_MATERIAL, "tier": "rare", "region_rarity": "unique",
        "traits": [{
            "id": "diagnostic_interface", "effect_kinds": ["add_resource"],
            "selectors": ["self"], "budget_points": 4,
        }],
    })


def _repair_material() -> MaterialDefinition:
    return parse_material({
        "id": REPAIR_MATERIAL, "tier": "rare", "region_rarity": "unique",
        "traits": [{
            "id": "facility_control", "effect_kinds": ["modify_field", "modify_attractor"],
            "selectors": ["current_area"], "budget_points": 8,
        }],
    })


def _probe_blueprint(root: str) -> dict[str, Any]:
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "skill_blueprint",
        "id": f"f2_probe_{root}", "version": 1, "trigger": "on_use", "condition": None,
        "duration": None, "cost": {"duration": 1, "mana": 0},
        "scope": {"selectors": ["self"], "relation_types": []},
        "effects": [{
            "id": "authorized_probe_request", "kind": "add_resource",
            "target": {"kind": "self"}, "commitment": "required", "resource": "mana", "amount": 0,
        }],
        "budget": {"limit": 4}, "max_firings_per_root": 1,
        "material_ids": [DIAGNOSTIC_MATERIAL],
    }


def _repair_blueprint(root: str) -> dict[str, Any]:
    field = "water" if root == "water" else "resonance"
    delta = 2.0 if root == "water" else -2.0
    attractor = 8.0 if root == "water" else 2.0
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "skill_blueprint",
        "id": f"f2_repair_{root}", "version": 1, "trigger": "on_use", "condition": None,
        "duration": None, "cost": {"duration": 1, "mana": 0},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": [
            {"id": "set_safe_now", "kind": "modify_field", "target": {"kind": "current_area"},
             "commitment": "required", "field_id": field, "amount": delta},
            {"id": "hold_safe", "kind": "modify_attractor", "target": {"kind": "current_area"},
             "commitment": "required", "field_id": field, "amount": attractor, "duration": 6},
        ],
        "budget": {"limit": 8}, "max_firings_per_root": 1,
        "material_ids": [REPAIR_MATERIAL],
    }
