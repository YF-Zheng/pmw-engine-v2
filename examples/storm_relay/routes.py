"""Reproducible public-command route runners for Storm Relay."""

from __future__ import annotations

from typing import Any

from .session import StormRelaySession


def run_commands(commands: list[dict[str, Any]], *, time_budget: int = 23) -> dict[str, Any]:
    """Execute a route exclusively through the browser command surface."""
    session = StormRelaySession.new_game(time_budget=time_budget)
    transcript: list[dict[str, Any]] = []
    for command in commands:
        session.perform(command["action"], target=command.get("target"), slot=command.get("slot"))
        state = session.public_state()
        transcript.append({"command": dict(command), "remaining": state["time"]["remaining"],
                           "outcome": state["outcome"]})
        if state["outcome"] != "playing":
            break
    return {"transcript": transcript, "state": session.public_state()}


def direct_assault_route() -> dict[str, Any]:
    commands = [{"action": "travel_tower"}, {"action": "start_core"}] + [{"action": "attack"}] * 7 + [{"action": "close_core"}]
    return run_commands(commands)


def storm_build_route() -> dict[str, Any]:
    commands = [
        {"action": "investigate_inscription"}, {"action": "harvest_wet_moss"},
        {"action": "harvest_thunder_crystal"}, {"action": "craft_lightning_seed"},
        {"action": "travel_tower"}, {"action": "equip_active", "target": "lightning_seed", "slot": 0},
        {"action": "cast_lightning_seed"}, {"action": "investigate_storm_glass"},
        {"action": "harvest_storm_glass"}, {"action": "craft_storm_glass_relay"},
        {"action": "equip_passive", "target": "storm_glass_relay", "slot": 0}, {"action": "start_core"},
    ] + [{"action": "attack"}] * 4 + [{"action": "close_core"}]
    return run_commands(commands)


def fog_build_route() -> dict[str, Any]:
    commands = [
        {"action": "investigate_inscription"}, {"action": "harvest_wet_moss"},
        {"action": "harvest_wet_moss"}, {"action": "harvest_thunder_crystal"},
        {"action": "craft_mist_echo"},
        {"action": "travel_tower"}, {"action": "equip_active", "target": "fog_echo", "slot": 0},
        {"action": "cast_mist_echo"}, {"action": "investigate_storm_glass"},
        {"action": "harvest_storm_glass"}, {"action": "craft_storm_glass_relay"},
        {"action": "equip_passive", "target": "storm_glass_relay", "slot": 0}, {"action": "start_core"},
    ] + [{"action": "attack"}] * 7 + [{"action": "close_core"}]
    return run_commands(commands)
