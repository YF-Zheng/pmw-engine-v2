"""Mechanical world with coupling, recovery, and a Derived status."""

from __future__ import annotations

from pmw import Relation, WorldState

from ..dynamics import CouplingLawProfile, DynamicsLawProfile, build_dynamics_laws
from .common import catalog, clock, dynamic_entity, neutral_slot


def build_structural_world():
    cat = catalog("mechanical_structural")
    frame = dynamic_entity(
        "frame", 0.35, 0.75, 0.12,
        attractor_slots=("stability_attractor_0", "stability_attractor_1"),
        alpha_slots=("stability_alpha_0", "stability_alpha_1"),
        drive_slots=("stability_drive_0", "stability_drive_1"),
    )
    frame.components["derived"] = {"operational": False}
    support = dynamic_entity("support", 0.9, 0.9, 0.05)
    link = Relation("frame_support", "supports", "frame", "support", components={
        "gm_v06_coupling": {"base_conductivity": 0.04, "modifier_slots": {
            name: neutral_slot("dynamics") for name in (
                "stiffness_dynamic_0", "stiffness_dynamic_1", "stiffness_param_0", "stiffness_param_1"
            )
        }},
    })
    state = WorldState("gm_v06_structural", entities={item.id: item for item in (
        clock(), frame, support,
    )}, relations={link.id: link})
    laws = list(build_dynamics_laws(
        [
            DynamicsLawProfile("frame", ("stability_attractor_0", "stability_attractor_1"), ("stability_alpha_0", "stability_alpha_1"), ("stability_drive_0", "stability_drive_1")),
            DynamicsLawProfile("support"),
        ],
        [CouplingLawProfile("frame_support", "supports", "frame", "support", ("stiffness_dynamic_0", "stiffness_dynamic_1", "stiffness_param_0", "stiffness_param_1"))],
    ))
    laws.extend([
        {
            "id": "gm.v06.world.structural.operational_true", "mode": "state", "priority": 100,
            "bindings": {"frame": {"kind": "entity", "requires": ["gm_v06_dynamics", "derived"]}},
            "when": {"all": [{"ref": "$frame.id", "eq": "frame"}, {"ref": "$frame.gm_v06_dynamics.value", "gte": 0.55}, {"ref": "$frame.derived.operational", "eq": False}]},
            "effects": [{"op": "set", "target": "$frame.derived.operational", "value": True}],
        },
        {
            "id": "gm.v06.world.structural.operational_false", "mode": "state", "priority": 100,
            "bindings": {"frame": {"kind": "entity", "requires": ["gm_v06_dynamics", "derived"]}},
            "when": {"all": [{"ref": "$frame.id", "eq": "frame"}, {"ref": "$frame.gm_v06_dynamics.value", "lt": 0.55}, {"ref": "$frame.derived.operational", "eq": True}]},
            "effects": [{"op": "set", "target": "$frame.derived.operational", "value": False}],
        },
    ])
    return state, tuple(laws), cat
