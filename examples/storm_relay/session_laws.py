"""Formal Storm Relay session events.

The Gameplay package deliberately does not prescribe a quest grammar.  These
small laws are the M0 grammar: exploration facts, finite stocks, and the relay
console are still written by ordinary PMW events, while combat, effects,
registry and time continue to use the public Gameplay adapters.
"""

from __future__ import annotations

from pmw import parse_law

from .content import AREA_COMPONENT, GUARD_ID, PLAYER_ID, SHALLOWS_ID, TOWER_ID
from .laws import WEATHER_CHANGED_EVENT


SESSION_EVENT = "pmw.m0.session.command"
COMBAT_EVENT = "pmw.m0.combat.resolve"
GUARD_EXPIRE_EVENT = "pmw.m0.combat.guard_expire"
RELAY_SHIELD_EVENT = "pmw.m0.session.relay_shield_grant"


def session_laws() -> tuple[dict, ...]:
    laws: list[dict] = []
    player = {"player": {"kind": "entity", "requires": ["pmw_gameplay_actor", "storm_relay_actor", "storm_relay_player"]}}
    common = [{"event.type": {"eq": SESSION_EVENT}}, {"ref": "$event.source", "eq": PLAYER_ID}]

    def command(name: str, effects: list[dict], extra: list[dict] = []) -> None:
        laws.append({"id": f"pmw.m0.session.{name}", "mode": "event", "priority": 80,
                     "bindings": player,
                     "when": {"all": [*common, {"ref": "$event.payload.action", "eq": name}, *extra]},
                     "effects": effects})

    command("investigate_inscription", [
        {"op": "set", "target": "$player.storm_relay_actor.known_recipes", "value": "$event.payload.recipes"},
        {"op": "set", "target": f"$player.storm_relay_actor.action_serial", "value": "$event.payload.serial"},
        {"op": "set", "target": f"$player.storm_relay_actor.last_message", "value": "ancient_inscription"},
    ], [{"ref": "$player.storm_relay_actor.current_area", "eq": SHALLOWS_ID}])
    command("investigate_storm_glass", [
        {"op": "set", "target": "$player.storm_relay_actor.known_recipes", "value": "$event.payload.recipes"},
        {"op": "set", "target": f"$player.storm_relay_actor.action_serial", "value": "$event.payload.serial"},
        {"op": "set", "target": f"$player.storm_relay_actor.last_message", "value": "broken_storm_glass"},
    ], [{"ref": "$player.storm_relay_actor.current_area", "eq": TOWER_ID}])
    command("travel_tower", [
        {"op": "set", "target": "$player.storm_relay_actor.current_area", "value": TOWER_ID},
        {"op": "set", "target": "$player.storm_relay_actor.action_serial", "value": "$event.payload.serial"},
    ], [{"ref": "$player.storm_relay_actor.current_area", "eq": SHALLOWS_ID}])
    command("travel_shallows", [
        {"op": "set", "target": "$player.storm_relay_actor.current_area", "value": SHALLOWS_ID},
        {"op": "set", "target": "$player.storm_relay_actor.action_serial", "value": "$event.payload.serial"},
    ], [{"ref": "$player.storm_relay_actor.current_area", "eq": TOWER_ID}])
    # One relation binding makes relocation robust under binding-dependent
    # pruning; the command supplies the current relation identity and the
    # deterministic replacement relation.
    laws.append({"id": "pmw.m0.session.relocate_relation", "mode": "event", "priority": 80,
                 "bindings": {"player": {"kind": "entity", "requires": ["storm_relay_player"]},
                              "location": {"kind": "relation", "type": "located_in", "source": "$player"}},
                 "when": {"all": [{"event.type": {"eq": "pmw.m0.session.relocate"}},
                                   {"ref": "$location.id", "eq": "$event.target"}]},
                 "effects": [{"op": "delete_relation", "target": "$location"},
                             {"op": "create_relation", "value": "$event.payload.replacement"}]})

    for material, area, stock in (("wet_moss", SHALLOWS_ID, "wet_moss"),
                                  ("thunder_crystal", SHALLOWS_ID, "thunder_crystal"),
                                  ("storm_glass", TOWER_ID, "storm_glass")):
        laws.append({"id": f"pmw.m0.session.harvest_{material}.player", "mode": "event", "priority": 80,
                     "bindings": {"player": {"kind": "entity", "requires": ["pmw_gameplay_actor", "storm_relay_actor", "storm_relay_player", "pmw_gameplay_material_inventory"]}},
                     "when": {"all": [*common, {"ref": "$event.payload.action", "eq": f"harvest_{material}"},
                                       {"ref": f"$player.pmw_gameplay_material_inventory.quantities.{material}", "eq": "$event.payload.before_material"}]},
                     "effects": [{"op": "set", "target": f"$player.pmw_gameplay_material_inventory.quantities.{material}", "value": "$event.payload.after_material"},
                                 {"op": "set", "target": "$player.storm_relay_actor.action_serial", "value": "$event.payload.serial"}]})
        laws.append({"id": f"pmw.m0.session.harvest_{material}.area", "mode": "event", "priority": 80,
                     "bindings": {"area": {"kind": "entity", "requires": [AREA_COMPONENT, f"storm_relay_stock_{material}"]}},
                     "when": {"all": [{"event.type": {"eq": SESSION_EVENT}}, {"ref": "$event.target", "eq": area},
                                       {"ref": "$event.payload.action", "eq": f"harvest_{material}"},
                                       {"ref": f"$area.{AREA_COMPONENT}.stock.{stock}", "eq": "$event.payload.before_stock"}]},
                     "effects": [{"op": "set", "target": f"$area.{AREA_COMPONENT}.stock.{stock}", "value": "$event.payload.after_stock"}]})

    command("craft", [
        {"op": "set", "target": "$player.pmw_gameplay_material_inventory.quantities", "value": "$event.payload.inventory"},
        {"op": "set", "target": "$player.storm_relay_actor.crafted_receipts", "value": "$event.payload.receipts"},
        {"op": "set", "target": "$player.storm_relay_actor.action_serial", "value": "$event.payload.serial"},
    ])
    command("start_core", [
        {"op": "set", "target": "$player.pmw_gameplay_actor.in_combat", "value": True},
        {"op": "set", "target": "$player.storm_relay_actor.action_serial", "value": "$event.payload.serial"},
    ], [{"ref": "$player.storm_relay_actor.current_area", "eq": TOWER_ID}])
    laws.append({"id": "pmw.m0.session.start_core.guard", "mode": "event", "priority": 80,
                 "bindings": {"guard": {"kind": "entity", "requires": ["storm_relay_actor"]}},
                 "when": {"all": [{"event.type": {"eq": SESSION_EVENT}}, {"ref": "$event.payload.action", "eq": "start_core"},
                                   {"ref": "$guard.id", "eq": GUARD_ID}]},
                 "effects": [{"op": "set", "target": "$guard.storm_relay_actor.encounter_active", "value": True},
                             {"op": "set", "target": "$guard.pmw_gameplay_actor.in_combat", "value": True}]})
    command("close_core", [
        {"op": "set", "target": "$player.storm_relay_actor.outcome", "value": "victory"},
        {"op": "set", "target": "$player.storm_relay_actor.action_serial", "value": "$event.payload.serial"},
    ], [{"ref": "$player.storm_relay_actor.current_area", "eq": TOWER_ID}])
    command("set_relay_equipped", [
        {"op": "set", "target": "$player.storm_relay_actor.relay_equipped", "value": "$event.payload.enabled"},
        {"op": "set", "target": "$player.storm_relay_actor.action_serial", "value": "$event.payload.serial"},
    ])
    command("terminal_defeat", [
        {"op": "set", "target": "$player.storm_relay_actor.outcome", "value": "defeat"},
        {"op": "set", "target": "$player.storm_relay_actor.action_serial", "value": "$event.payload.serial"},
    ])

    # The stock gameplay basic actions are cryptographically identity-pinned.
    # M0 therefore has its own small, data-only action protocol rather than
    # attempting to replace a frozen Gameplay builtin.  Both actors are
    # committed from one common resolver payload; these laws are the only
    # authority which writes the combat result into WorldState.
    for name, entity_id, payload_key in (("player", PLAYER_ID, "player"), ("guard", GUARD_ID, "guard")):
        laws.append({"id": f"pmw.m0.combat.100.commit_{name}", "mode": "event", "priority": 80,
                     "bindings": {name: {"kind": "entity", "requires": ["pmw_gameplay_actor", "pmw_gameplay_shields"]}},
                     "when": {"all": [{"event.type": {"eq": COMBAT_EVENT}}, {"ref": f"${name}.id", "eq": entity_id}]},
                     "effects": [
                         {"op": "set", "target": f"${name}.pmw_gameplay_actor.hp", "value": f"$event.payload.{payload_key}.hp"},
                         {"op": "set", "target": f"${name}.pmw_gameplay_actor.mana", "value": f"$event.payload.{payload_key}.mana"},
                         {"op": "set", "target": f"${name}.pmw_gameplay_actor.shield", "value": f"$event.payload.{payload_key}.shield"},
                         {"op": "set", "target": f"${name}.pmw_gameplay_shields", "value": f"$event.payload.{payload_key}.shields"},
                     ]})
    laws.append({"id": "pmw.m0.combat.110.expire_player_guard", "mode": "event", "priority": 80,
                 "bindings": {"player": {"kind": "entity", "requires": ["pmw_gameplay_actor", "pmw_gameplay_shields", "storm_relay_player"]}},
                 "when": {"all": [{"event.type": {"eq": GUARD_EXPIRE_EVENT}}, {"ref": "$event.target", "eq": "$player.id"}]},
                 "effects": [
                     {"op": "set", "target": "$player.pmw_gameplay_actor.shield", "value": "$event.payload.shield"},
                     {"op": "set", "target": "$player.pmw_gameplay_shields", "value": "$event.payload.shields"},
                 ]})

    # This is backend-side automatic dispatch.  It reacts to the formal
    # weather event while the passive is equipped; browser/routes never invoke
    # a named passive command.
    laws.append({"id": "pmw.m0.session.passive_weather_shield", "mode": "event", "priority": 70,
                 "bindings": {"player": {"kind": "entity", "requires": ["pmw_gameplay_actor", "storm_relay_actor", "storm_relay_player"]}},
                 "when": {"all": [{"event.type": {"eq": WEATHER_CHANGED_EVENT}},
                                   {"ref": "$player.storm_relay_actor.relay_equipped", "eq": True},
                                   {"ref": "$player.storm_relay_actor.current_area", "eq": "$event.target"}]},
                 "effects": []})
    laws.append({"id": "pmw.m0.session.commit_relay_shield", "mode": "event", "priority": 80,
                 "bindings": {"player": {"kind": "entity", "requires": ["pmw_gameplay_actor", "storm_relay_actor", "storm_relay_player", "pmw_gameplay_shields"]}},
                 "when": {"all": [{"event.type": {"eq": RELAY_SHIELD_EVENT}}, {"ref": "$event.target", "eq": "$player.id"}]},
                 "effects": [
                     {"op": "set", "target": "$player.pmw_gameplay_actor.shield", "value": "$event.payload.shield"},
                     {"op": "set", "target": "$player.pmw_gameplay_shields", "value": "$event.payload.shields"},
                     {"op": "set", "target": "$player.storm_relay_actor.relay_shield", "value": "$event.payload.amount"},
                     {"op": "set", "target": "$player.storm_relay_actor.relay_shield_ticks", "value": 3},
                 ]})
    laws.append({"id": "pmw.m0.session.passive_weather_shield_decay", "mode": "event", "priority": 70,
                 "bindings": {"player": {"kind": "entity", "requires": ["storm_relay_actor", "storm_relay_player"]}},
                 "when": {"all": [{"event.type": {"eq": "pmw.v04.world_tick"}},
                                   {"ref": "$player.storm_relay_actor.relay_shield_ticks", "gt": 0}]},
                 "effects": [{"op": "delta", "target": "$player.storm_relay_actor.relay_shield_ticks", "value": -1}]})
    laws.append({"id": "pmw.m0.session.passive_weather_shield_expire", "mode": "event", "priority": 80,
                 "bindings": {"player": {"kind": "entity", "requires": ["pmw_gameplay_actor", "storm_relay_player", "pmw_gameplay_shields"]}},
                 "when": {"all": [{"event.type": {"eq": "pmw.m0.session.relay_expire"}},
                                   {"ref": "$player.id", "eq": "$event.target"}]},
                 "effects": [{"op": "set", "target": "$player.pmw_gameplay_actor.shield", "value": "$event.payload.shield"},
                             {"op": "set", "target": "$player.pmw_gameplay_shields", "value": "$event.payload.shields"},
                             {"op": "set", "target": "$player.storm_relay_actor.relay_shield", "value": 0.0}]})
    result = tuple(sorted(laws, key=lambda law: law["id"]))
    for law in result:
        parse_law(law)
    return result
