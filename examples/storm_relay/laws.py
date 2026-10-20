"""M0-only PMW Laws for exclusive local weather and storm damage.

The weather evaluator is deliberately a derived event.  Gameplay field laws
commit first for a ``pmw.v04.world_tick``; only then does this module inspect
the evolved fields.  Thus every transition and pulse is causally visible and
uses the exact Tick-order contract rather than a Python-side postprocessor.
"""

from __future__ import annotations

from typing import Any

from pmw import parse_law


AREA_COMPONENT = "storm_relay_area"
DYNAMICS_COMPONENT = "pmw_gameplay_dynamics"
ACTOR_COMPONENT = "pmw_gameplay_actor"
WORLD_TICK_EVENT = "pmw.v04.world_tick"
WEATHER_EVALUATE_EVENT = "pmw.m0.weather.evaluate"
WEATHER_CHANGED_EVENT = "pmw.m0.weather_changed"
WEATHER_PULSE_EVENT = "pmw.m0.weather.pulse"
STORM_DAMAGE_EVENT = "pmw.m0.storm.damage"


def m0_laws() -> tuple[dict[str, Any], ...]:
    """Return parsed-valid Law documents, reusable by the M0 Session factory."""
    laws = [_weather_evaluator_emitter()]
    for area_id in ("storm_shallows", "storm_tower"):
        laws.extend(_weather_transition_laws(area_id))
    laws.append(_storm_damage_law())
    result = tuple(sorted(laws, key=lambda law: law["id"]))
    for law in result:
        parse_law(law)
    return result


def _weather_evaluator_emitter() -> dict[str, Any]:
    return {
        "id": "pmw.m0.weather.010.schedule_evaluation", "mode": "event", "priority": 10,
        "bindings": {"area": {"kind": "entity", "requires": [AREA_COMPONENT, DYNAMICS_COMPONENT]}},
        "when": {"all": [{"event.type": {"eq": WORLD_TICK_EVENT}}]},
        "effects": [{"op": "emit_event", "event": {
            "type": WEATHER_EVALUATE_EVENT, "time": "$event.time", "source": "m0_weather",
            "target": "$area.id", "payload": {"area_id": "$area.id", "tick": "$event.payload.step"},
        }}],
    }


def _weather_transition_laws(area_id: str) -> list[dict[str, Any]]:
    prefix = f"pmw.m0.weather.100.{area_id}"
    b = {"area": {"kind": "entity", "requires": [AREA_COMPONENT, DYNAMICS_COMPONENT]}}
    state = f"$area.{AREA_COMPONENT}.weather"
    h = f"$area.{DYNAMICS_COMPONENT}.fields.humidity.value"
    c = f"$area.{DYNAMICS_COMPONENT}.fields.charge.value"
    common = [{"event.type": {"eq": WEATHER_EVALUATE_EVENT}}, {"ref": "$area.id", "eq": area_id},
              {"ref": "$event.target", "eq": "$area.id"}, {"ref": "$event.payload.area_id", "eq": "$area.id"}]
    rules: list[tuple[str, list[dict], str, bool]] = [
        ("clear_to_storm", [{"ref": state, "eq": "clear"}, {"ref": h, "gte": .60}, {"ref": c, "gte": .70}], "storm", True),
        ("clear_to_fog", [{"ref": state, "eq": "clear"}, {"ref": h, "gte": .70}, {"ref": c, "lt": .60}], "fog", False),
        ("storm_keep", [{"ref": state, "eq": "storm"}, {"ref": h, "gte": .45}, {"ref": c, "gte": .50}], "storm", True),
        # When storm cannot keep, its fog alternative is exactly the ordinary
        # fog enter condition combined with not(storm_keep).
        ("storm_to_fog", [{"ref": state, "eq": "storm"}, {"ref": h, "gte": .70}, {"ref": c, "lt": .50}], "fog", False),
        ("storm_to_clear", [{"ref": state, "eq": "storm"}, {"any": [{"ref": h, "lt": .45}, {"ref": c, "lt": .50}]},
                            {"not": {"all": [{"ref": h, "gte": .70}, {"ref": c, "lt": .50}]}}], "clear", False),
        ("fog_keep", [{"ref": state, "eq": "fog"}, {"ref": h, "gte": .55}, {"ref": c, "lt": .70}], "fog", False),
        ("fog_to_storm", [{"ref": state, "eq": "fog"}, {"any": [{"ref": h, "lt": .55}, {"ref": c, "gte": .70}]},
                           {"ref": h, "gte": .60}, {"ref": c, "gte": .70}], "storm", True),
        ("fog_to_clear", [{"ref": state, "eq": "fog"}, {"any": [{"ref": h, "lt": .55}, {"ref": c, "gte": .70}]},
                            {"not": {"all": [{"ref": h, "gte": .60}, {"ref": c, "gte": .70}]}}], "clear", False),
    ]
    laws: list[dict[str, Any]] = []
    for name, conditions, new_state, pulse in rules:
        changed = name not in {"storm_keep", "fog_keep"}
        effects: list[dict[str, Any]] = []
        if changed:
            effects.extend([
                {"op": "set", "target": state, "value": new_state},
                {"op": "delta", "target": f"$area.{AREA_COMPONENT}.weather_transitions", "value": 1},
                {"op": "emit_event", "event": {
                    "type": WEATHER_CHANGED_EVENT, "time": "$event.time", "source": "m0_weather",
                    "target": "$area.id", "payload": {"area_id": "$area.id", "old": state,
                        "new": new_state, "source": "m0_weather", "tick": "$event.payload.tick"},
                }},
            ])
        if pulse:
            effects.append({"op": "emit_event", "event": {
                "type": WEATHER_PULSE_EVENT, "time": "$event.time", "source": "m0_weather",
                "target": "$area.id", "payload": {"area_id": "$area.id", "weather": "storm", "tick": "$event.payload.tick"},
            }})
        laws.append({"id": f"{prefix}.{name}", "mode": "event", "priority": 10, "bindings": b,
                     "when": {"all": [*common, *conditions]}, "effects": effects})
    return laws


def _storm_damage_law() -> dict[str, Any]:
    return {
        "id": "pmw.m0.weather.200.storm_conductive_damage", "mode": "event", "priority": 10,
        "bindings": {
            "area": {"kind": "entity", "requires": [AREA_COMPONENT]},
            "actor": {"kind": "entity", "requires": [ACTOR_COMPONENT, "storm_relay_actor"]},
            "location": {"kind": "relation", "type": "located_in", "source": "$actor", "target": "$area"},
        },
        "when": {"all": [
            {"event.type": {"eq": WEATHER_PULSE_EVENT}}, {"ref": "$event.target", "eq": "$area.id"},
            {"ref": "$event.payload.weather", "eq": "storm"}, {"has_tag": ["$actor", "conductive"]},
            {"ref": "$actor.storm_relay_actor.encounter_active", "eq": True},
            {"ref": "$actor.pmw_gameplay_actor.hp", "gt": 0},
        ]},
        "effects": [
            {"op": "delta", "target": "$actor.pmw_gameplay_actor.hp", "value": -5},
            {"op": "emit_event", "event": {
                "type": STORM_DAMAGE_EVENT, "time": "$event.time", "source": "$area.id", "target": "$actor.id",
                "payload": {"area_id": "$area.id", "actor_id": "$actor.id", "damage": 5,
                            "tick": "$event.payload.tick"},
            }},
        ],
    }
