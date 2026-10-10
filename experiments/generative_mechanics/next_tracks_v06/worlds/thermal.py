"""Thermal/fluid world with stock depletion and a real cooling process."""

from __future__ import annotations

from pmw import Entity, Relation, WorldState

from ..dynamics import CouplingLawProfile, DynamicsLawProfile, build_dynamics_laws
from .common import catalog, clock, dynamic_entity, neutral_slot


def build_thermal_world():
    cat = catalog("thermal_fluid")
    reactor = dynamic_entity(
        "reactor", 0.8, 0.8, 0.20,
        attractor_slots=("temp_attractor_0", "temp_attractor_1"),
        alpha_slots=("temp_alpha_0", "temp_alpha_1"),
        drive_slots=("temp_drive_0", "temp_drive_1"),
    )
    reactor.components["derived"] = {"operational": True}
    ambient = dynamic_entity("ambient", 0.2, 0.2, 0.05)
    coolant = Entity("coolant_tank", "stock", components={
        "stock": {"amount": 0.8, "capacity": 1.0, "unit": "coolant"},
        "slots": {"drive_0": neutral_slot("drive"), "drive_1": neutral_slot("drive")},
    })
    reserve = Entity("reserve_tank", "stock", components={
        "stock": {"amount": 0.4, "capacity": 1.0, "unit": "coolant"},
        "slots": {"drive_0": neutral_slot("drive"), "drive_1": neutral_slot("drive")},
    })
    waste = Entity("waste_tank", "stock", components={"stock": {
        "amount": 0.0, "capacity": 1.0, "unit": "coolant",
    }})
    pump = Entity("pump_01", "process", components={
        "process": {"state": "stopped", "base_flow_rate": 0.10},
        "gm_v06_process": {"modifier_slots": {
            "pump_flow_0": neutral_slot("process_parameter"),
            "pump_flow_1": neutral_slot("process_parameter"),
        }},
    })
    link = Relation("thermal_link_ab", "conducts_heat", "reactor", "ambient", components={
        "gm_v06_coupling": {"base_conductivity": 0.05, "modifier_slots": {
            name: neutral_slot("dynamics") for name in (
                "link_dynamic_0", "link_dynamic_1", "link_param_0", "link_param_1"
            )
        }},
    })
    state = WorldState("gm_v06_thermal", entities={item.id: item for item in (
        clock(), reactor, ambient, coolant, reserve, waste, pump,
    )}, relations={link.id: link})
    laws = list(build_dynamics_laws(
        [
            DynamicsLawProfile("reactor", ("temp_attractor_0", "temp_attractor_1"), ("temp_alpha_0", "temp_alpha_1"), ("temp_drive_0", "temp_drive_1")),
            DynamicsLawProfile("ambient"),
        ],
        [CouplingLawProfile("thermal_link_ab", "conducts_heat", "reactor", "ambient", ("link_dynamic_0", "link_dynamic_1", "link_param_0", "link_param_1"))],
    ))
    flow = {"clamp": [{"add": [
        "$pump.process.base_flow_rate",
        "$pump.gm_v06_process.modifier_slots.pump_flow_0.delta",
        "$pump.gm_v06_process.modifier_slots.pump_flow_1.delta",
    ]}, 0.0, 1.0]}
    quantity = {"min": [flow, "$tank.stock.amount"]}
    laws.extend([
        {
            "id": "gm.v06.world.thermal.pump", "mode": "event", "priority": 100,
            "bindings": {
                "reactor": {"kind": "entity", "requires": ["gm_v06_dynamics"]},
                "tank": {"kind": "entity", "requires": ["stock"]},
                "pump": {"kind": "entity", "requires": ["process", "gm_v06_process"]},
            },
            "when": {"all": [
                {"event.type": {"eq": "gm.v06.world.step"}},
                {"ref": "$reactor.id", "eq": "reactor"},
                {"ref": "$tank.id", "eq": "coolant_tank"},
                {"ref": "$pump.id", "eq": "pump_01"},
                {"ref": "$pump.process.state", "eq": "running"},
                {"ref": "$tank.stock.amount", "gt": 0.0},
            ]},
            "effects": [
                {"op": "set", "target": "$reactor.gm_v06_dynamics.value", "value": {"clamp": [{"sub": ["$reactor.gm_v06_dynamics.value", {"mul": [0.5, quantity]}]}, 0.0, 1.0]}},
                {"op": "delta", "target": "$tank.stock.amount", "value": {"sub": [0.0, quantity]}},
            ],
        },
        {
            "id": "gm.v06.world.thermal.stop_empty", "mode": "state", "priority": 100,
            "bindings": {"tank": {"kind": "entity", "requires": ["stock"]}, "pump": {"kind": "entity", "requires": ["process"]}},
            "when": {"all": [
                {"ref": "$tank.id", "eq": "coolant_tank"}, {"ref": "$pump.id", "eq": "pump_01"},
                {"ref": "$tank.stock.amount", "lte": 0.0}, {"ref": "$pump.process.state", "eq": "running"},
            ]},
            "effects": [{"op": "set", "target": "$pump.process.state", "value": "stopped"}],
        },
        {
            "id": "gm.v06.world.thermal.operational_false", "mode": "state", "priority": 100,
            "bindings": {"reactor": {"kind": "entity", "requires": ["gm_v06_dynamics", "derived"]}},
            "when": {"all": [{"ref": "$reactor.id", "eq": "reactor"}, {"ref": "$reactor.gm_v06_dynamics.value", "gt": 0.9}, {"ref": "$reactor.derived.operational", "eq": True}]},
            "effects": [{"op": "set", "target": "$reactor.derived.operational", "value": False}],
        },
        {
            "id": "gm.v06.world.thermal.operational_true", "mode": "state", "priority": 100,
            "bindings": {"reactor": {"kind": "entity", "requires": ["gm_v06_dynamics", "derived"]}},
            "when": {"all": [{"ref": "$reactor.id", "eq": "reactor"}, {"ref": "$reactor.gm_v06_dynamics.value", "lte": 0.9}, {"ref": "$reactor.derived.operational", "eq": False}]},
            "effects": [{"op": "set", "target": "$reactor.derived.operational", "value": True}],
        },
    ])
    return state, tuple(laws), cat
