"""Deterministically generate checked-in lab JSON assets."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHANNELS = ("temperature", "wetness", "electric_field", "fire_intensity", "sound_level", "ground_stability", "water_level", "visibility")


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def world(name: str, values: tuple[float, ...], material: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "2.0", "world_id": f"gm_{name}",
        "time": {"tick": 0, "sim_time": 0.0}, "rng": {"seed": 20261004},
        "entities": [
            {"id": "actor:researcher", "archetype": "actor", "tags": [], "components": {"resource": {"energy": 100.0}}},
            {"id": f"zone:{name}", "archetype": "zone", "tags": [name], "components": {
                "zone": {"kind": name}, "fields": dict(zip(CHANNELS, values)), "process": {"steam": 0.0, "alert": 0.0},
                "material": material, "outcome": {"discharges": 0.0, "charged_ore": 0.0},
            }},
            {"id": "skill:equipped", "archetype": "skill_instance", "tags": [], "components": {
                "skill": {"spec_id": "static_grave", "owner": "actor:researcher", "charges": 99}
            }},
        ], "relations": [], "scheduled_events": [],
    }


ENVIRONMENTS = {
    "mine": ((0.30, 0.20, 0.05, 0.05, 0.10, 0.85, 0.05, 0.45), {"fuel": 0.65, "exposed_iron": 1.0, "fragility": 0.25}),
    "wetland": ((0.45, 0.90, 0.05, 0.00, 0.20, 0.35, 0.90, 0.65), {"fuel": 0.35, "exposed_iron": 0.10, "fragility": 0.15}),
    "industrial_yard": ((0.50, 0.25, 0.40, 0.10, 0.45, 0.90, 0.10, 0.80), {"fuel": 0.80, "exposed_iron": 0.90, "fragility": 0.10}),
    "fragile_bridge": ((0.35, 0.40, 0.05, 0.00, 0.15, 0.40, 0.30, 0.90), {"fuel": 0.55, "exposed_iron": 0.50, "fragility": 0.95}),
}


def clause(field: str, op: str, value: float) -> dict[str, object]:
    return {"ref": f"$zone.fields.{field}", op: value}


def law(number: int, name: str, conditions: list[dict[str, object]], effects: list[dict[str, object]]) -> dict[str, object]:
    return {
        "id": f"gm.world.{number:02d}.{name}", "mode": "event", "priority": 0,
        "bindings": {"zone": {"kind": "entity", "requires": ["fields", "zone", "process", "material", "outcome"]}},
        "when": {"all": [{"event.type": {"eq": "lab.step"}}, *conditions]}, "effects": effects,
    }


def delta(path: str, value: float) -> dict[str, object]:
    return {"op": "delta", "target": f"$zone.{path}", "value": value}


LAWS = [
    law(1, "rain_wets", [clause("water_level", "gt", .6)], [delta("fields.wetness", .10)]),
    law(2, "water_saturates", [clause("water_level", "gt", .8)], [delta("fields.wetness", .08)]),
    law(3, "wet_discharge", [clause("wetness", "gt", .55), clause("electric_field", "gt", .45)], [delta("outcome.discharges", 1), delta("fields.electric_field", -.20), delta("fields.sound_level", .12)]),
    law(4, "heat_makes_steam", [clause("temperature", "gt", .60), clause("wetness", "gt", .45)], [delta("process.steam", .20), delta("fields.wetness", -.08)]),
    law(5, "steam_obscures", [{"ref": "$zone.process.steam", "gt": .10}], [delta("fields.visibility", -.16)]),
    law(6, "fire_heats", [clause("fire_intensity", "gt", .10)], [delta("fields.temperature", .12)]),
    law(7, "fire_consumes_fuel", [clause("fire_intensity", "gt", .10), {"ref": "$zone.material.fuel", "gt": .05}], [delta("material.fuel", -.08)]),
    law(8, "low_fuel_dims_fire", [{"ref": "$zone.material.fuel", "lt": .15}, clause("fire_intensity", "gt", .05)], [delta("fields.fire_intensity", -.12)]),
    law(9, "water_weakens_ground", [clause("water_level", "gt", .55)], [delta("fields.ground_stability", -.10)]),
    law(10, "wetness_weakens_fragile", [clause("wetness", "gt", .55), {"ref": "$zone.material.fragility", "gt": .70}], [delta("fields.ground_stability", -.14)]),
    law(11, "sound_alerts", [clause("sound_level", "gt", .45)], [delta("process.alert", .20)]),
    law(12, "silence_settles_alert", [clause("sound_level", "lt", .20), {"ref": "$zone.process.alert", "gt": 0}], [delta("process.alert", -.08)]),
    law(13, "iron_charges", [clause("electric_field", "gt", .50), {"ref": "$zone.material.exposed_iron", "gt": .50}], [delta("outcome.charged_ore", .25)]),
    law(14, "charged_ore_hums", [{"ref": "$zone.outcome.charged_ore", "gt": .20}], [delta("fields.sound_level", .08)]),
    law(15, "fire_dries", [clause("fire_intensity", "gt", .30), clause("wetness", "gt", .10)], [delta("fields.wetness", -.10)]),
    law(16, "water_suppresses_fire", [clause("water_level", "gt", .60), clause("fire_intensity", "gt", .05)], [delta("fields.fire_intensity", -.16)]),
    law(17, "electric_ignites_fuel", [clause("electric_field", "gt", .70), {"ref": "$zone.material.fuel", "gt": .60}], [delta("fields.fire_intensity", .14)]),
    law(18, "unstable_ground_rumbles", [clause("ground_stability", "lt", .35)], [delta("fields.sound_level", .10)]),
    law(19, "fire_glow", [clause("fire_intensity", "gt", .25), clause("visibility", "lt", .90)], [delta("fields.visibility", .08)]),
    law(20, "rain_cools", [clause("water_level", "gt", .65), clause("temperature", "gt", .20)], [delta("fields.temperature", -.08)]),
    law(21, "steam_condenses", [{"ref": "$zone.process.steam", "gt": .35}, clause("temperature", "lt", .45)], [delta("process.steam", -.12), delta("fields.wetness", .06)]),
    law(22, "yard_resonance", [{"ref": "$zone.zone.kind", "eq": "industrial_yard"}, clause("electric_field", "gt", .55)], [delta("fields.sound_level", .12)]),
    law(23, "mine_echo", [{"ref": "$zone.zone.kind", "eq": "mine"}, clause("sound_level", "gt", .20)], [delta("process.alert", .12)]),
    law(24, "bridge_strain", [{"ref": "$zone.zone.kind", "eq": "fragile_bridge"}, clause("ground_stability", "lt", .50)], [delta("fields.sound_level", .15)]),
]


CATEGORIES = ("Starter", "Setup", "Payoff", "Converter", "Amplifier", "Control", "Utility", "Engine", "Consumable")
SKILL_BLUEPRINTS = (
    ("static_grave", "Static Grave", "electric_field", .60), ("kindling_arc", "Kindling Arc", "fire_intensity", .35),
    ("monsoon_seed", "Monsoon Seed", "water_level", .45), ("thermal_lance", "Thermal Lance", "temperature", .50),
    ("muffling_fold", "Muffling Fold", "sound_level", -.40), ("bedrock_memory", "Bedrock Memory", "ground_stability", .45),
    ("whiteout_veil", "Whiteout Veil", "visibility", -.45), ("dew_circuit", "Dew Circuit", "wetness", .50),
    ("ember_pulse", "Ember Pulse", "fire_intensity", .22), ("cold_sink", "Cold Sink", "temperature", -.40),
    ("storm_coil", "Storm Coil", "electric_field", .38), ("floodgate", "Floodgate", "water_level", .55),
    ("clear_sky", "Clear Sky", "visibility", .40), ("quiet_geometry", "Quiet Geometry", "sound_level", -.30),
    ("fault_whisper", "Fault Whisper", "ground_stability", -.35), ("drying_wind", "Drying Wind", "wetness", -.45),
    ("flare_mark", "Flare Mark", "visibility", .25), ("boiler_field", "Boiler Field", "temperature", .30),
    ("spark_tax", "Spark Tax", "electric_field", -.30), ("ash_bloom", "Ash Bloom", "fire_intensity", .48),
    ("reservoir_echo", "Reservoir Echo", "water_level", .30), ("mud_anchor", "Mud Anchor", "ground_stability", .28),
    ("signal_bell", "Signal Bell", "sound_level", .55), ("fog_lattice", "Fog Lattice", "visibility", -.30),
    ("static_engine", "Static Engine", "electric_field", .18), ("heat_engine", "Heat Engine", "temperature", .16),
    ("rain_engine", "Rain Engine", "wetness", .18), ("quake_engine", "Quake Engine", "ground_stability", -.14),
    ("flash_flood", "Flash Flood", "water_level", .70), ("flash_fire", "Flash Fire", "fire_intensity", .65),
    ("thunderclap", "Thunderclap", "sound_level", .80), ("blackout", "Blackout", "visibility", -.70),
    ("grounding_rod", "Grounding Rod", "electric_field", -.55), ("firebreak", "Firebreak", "fire_intensity", -.55),
    ("drainage_cut", "Drainage Cut", "water_level", -.50), ("stability_charge", "Stability Charge", "ground_stability", .65),
)


def skill(index: int, blueprint: tuple[str, str, str, float]) -> dict[str, object]:
    skill_id, name, field, amount = blueprint
    category = CATEGORIES[index % len(CATEGORIES)]
    periodic = {"interval": 2.0, "repeats": 3} if category == "Engine" else None
    duration = 6.0 if category in {"Control", "Amplifier"} else 0.0
    return {
        "id": skill_id, "name": name, "target_scope": "zone", "effects": [{"field": field, "delta": amount}],
        "duration": duration, "periodic": periodic, "trigger_conditions": [],
        "resource_cost": float(6 + index % 9), "charges": 1 if category == "Consumable" else 3,
        "slot_cost": 2 if category in {"Engine", "Amplifier"} else 1,
        "category": category,
    }


def main() -> None:
    for name, (values, material) in ENVIRONMENTS.items():
        write(ROOT / "environments" / f"{name}.json", world(name, values, material))
    write(ROOT / "substrate" / "world_laws.json", {"schema_version": "2.0", "laws": LAWS})
    manifest = []
    for index, blueprint in enumerate(SKILL_BLUEPRINTS):
        raw = skill(index, blueprint)
        category = raw.pop("category")
        path = ROOT / "skills" / f"{raw['id']}.json"
        write(path, raw)
        manifest.append({"id": raw["id"], "category": category, "path": f"skills/{raw['id']}.json"})
    write(ROOT / "skills" / "manifest.json", {"skills": manifest})


if __name__ == "__main__":
    main()
