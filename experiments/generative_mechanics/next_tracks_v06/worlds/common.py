"""Shared data constructors; no function here mutates an attached runtime."""

from __future__ import annotations

from pathlib import Path

from pmw import Entity

from ..spec import FieldObject, ObjectCatalog
from ..validator import load_catalog


ROOT = Path(__file__).resolve().parents[1]


def catalog(name: str) -> ObjectCatalog:
    return load_catalog(ROOT / "substrate" / f"{name}.json")


def neutral_slot(kind: str) -> dict:
    if kind == "attractor":
        return {"owner": None, "active": False, "target": 0.0, "weight": 0.0}
    if kind == "drive":
        return {"owner": None, "active": False, "drive": 0.0}
    return {"owner": None, "active": False, "delta": 0.0}


def dynamic_entity(
    entity_id: str,
    value: float,
    attractor: float,
    alpha: float,
    *,
    attractor_slots: tuple[str, ...] = (),
    alpha_slots: tuple[str, ...] = (),
    drive_slots: tuple[str, ...] = (),
) -> Entity:
    return Entity(entity_id, "gm_v06_field", components={"gm_v06_dynamics": {
        "value": value,
        "base_attractor": attractor,
        "base_weight": 1.0,
        "base_alpha": alpha,
        "drive_limit": 0.25,
        "attractor_slots": {item: neutral_slot("attractor") for item in attractor_slots},
        "alpha_slots": {item: neutral_slot("alpha") for item in alpha_slots},
        "drive_slots": {item: neutral_slot("drive") for item in drive_slots},
        "scratch": {"intrinsic": 0.0, "coupling": 0.0},
        "diagnostics": {
            "effective_attractor": attractor,
            "effective_alpha": alpha,
            "effective_drive": 0.0,
            "intrinsic": 0.0,
            "coupling": 0.0,
            "unclamped": value,
            "clamp_loss": 0.0,
        },
    }})


def catalog_field_entity(item: FieldObject) -> Entity:
    dynamics = item.dynamics or {}
    return dynamic_entity(
        item.state_ref.object_id,
        item.initial,
        float(dynamics.get("base_attractor", item.initial)),
        float(dynamics.get("base_alpha", 0.15)),
        attractor_slots=tuple(dynamics.get("attractor_slots", ())),
        alpha_slots=tuple(dynamics.get("alpha_slots", ())),
        drive_slots=tuple(dynamics.get("drive_slots", ())),
    )


def clock() -> Entity:
    return Entity("gm:v06:clock", "gm_v06_clock", components={"gm_v06_clock": {
        "next_step": 1, "next_time": 1.0, "last_completed_step": 0,
    }})
