"""Electric/network world where a real Relation gates charging."""

from __future__ import annotations

from pmw import Entity, WorldState

from ..dynamics import DynamicsLawProfile, build_dynamics_laws
from .common import catalog, clock, dynamic_entity, neutral_slot


def build_electric_world():
    cat = catalog("electric_network")
    bus = dynamic_entity(
        "power_bus", 0.2, 0.2, 0.10,
        attractor_slots=("voltage_attractor_0", "voltage_attractor_1"),
        alpha_slots=("voltage_alpha_0", "voltage_alpha_1"),
        drive_slots=("voltage_drive_0", "voltage_drive_1"),
    )
    battery = Entity("battery", "stock", components={
        "stock": {"amount": 0.3, "capacity": 1.0, "unit": "charge"},
        "slots": {"drive_0": neutral_slot("drive"), "drive_1": neutral_slot("drive")},
    })
    charger = Entity("charger", "process", components={
        "process": {"state": "stopped", "base_rate": 0.10},
        "gm_v06_process": {"modifier_slots": {
            "charger_rate_0": neutral_slot("process_parameter"),
            "charger_rate_1": neutral_slot("process_parameter"),
        }},
    })
    switch = Entity("switch", "discrete", components={"control": {"mode": "off"}})
    state = WorldState("gm_v06_electric", entities={item.id: item for item in (
        clock(), bus, battery, charger, switch,
    )})
    laws = list(build_dynamics_laws([
        DynamicsLawProfile("power_bus", ("voltage_attractor_0", "voltage_attractor_1"), ("voltage_alpha_0", "voltage_alpha_1"), ("voltage_drive_0", "voltage_drive_1")),
    ]))
    rate = {"clamp": [{"add": [
        "$charger.process.base_rate",
        "$charger.gm_v06_process.modifier_slots.charger_rate_0.delta",
        "$charger.gm_v06_process.modifier_slots.charger_rate_1.delta",
    ]}, 0.0, 0.25]}
    quantity = {"min": [rate, {"sub": ["$battery.stock.capacity", "$battery.stock.amount"]}, "$bus.gm_v06_dynamics.value"]}
    laws.extend([
        {
            "id": "gm.v06.world.electric.switch_on", "mode": "state", "priority": 100,
            "bindings": {"charger": {"kind": "entity", "requires": ["process"]}, "switch": {"kind": "entity", "requires": ["control"]}},
            "when": {"all": [
                {"ref": "$charger.id", "eq": "charger"}, {"ref": "$switch.id", "eq": "switch"},
                {"ref": "$charger.process.state", "eq": "running"}, {"ref": "$switch.control.mode", "eq": "off"},
            ]},
            "effects": [{"op": "set", "target": "$switch.control.mode", "value": "on"}],
        },
        {
            "id": "gm.v06.world.electric.transfer", "mode": "event", "priority": 100,
            "bindings": {
                "bus": {"kind": "entity", "requires": ["gm_v06_dynamics"]},
                "battery": {"kind": "entity", "requires": ["stock"]},
                "charger": {"kind": "entity", "requires": ["process", "gm_v06_process"]},
                "switch": {"kind": "entity", "requires": ["control"]},
                "link": {"kind": "relation", "type": "supplies_power", "source": "$bus", "target": "$battery"},
            },
            "when": {"all": [
                {"event.type": {"eq": "gm.v06.world.step"}},
                {"ref": "$bus.id", "eq": "power_bus"}, {"ref": "$battery.id", "eq": "battery"},
                {"ref": "$charger.id", "eq": "charger"}, {"ref": "$switch.id", "eq": "switch"},
                {"ref": "$charger.process.state", "eq": "running"}, {"ref": "$switch.control.mode", "eq": "on"},
                {"ref": "$battery.stock.amount", "lt": "$battery.stock.capacity"},
            ]},
            "effects": [
                {"op": "delta", "target": "$battery.stock.amount", "value": quantity},
                {"op": "delta", "target": "$bus.gm_v06_dynamics.value", "value": {"sub": [0.0, quantity]}},
            ],
        },
    ])
    return state, tuple(laws), cat
