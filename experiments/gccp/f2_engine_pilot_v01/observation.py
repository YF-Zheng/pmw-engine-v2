"""Allowlisted public observations for F2 belief updates."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import ActorObservationBuilder

from .engine_scenario import ACTOR_ID, AREA_ID, DIAGNOSTIC_MATERIAL, F2_COMPONENT, REPAIR_MATERIAL, F2Runtime


FORBIDDEN_KEYS = {"hidden_root", "hidden_interface", "damage"}


def public_observation(subject: F2Runtime) -> dict[str, Any]:
    base = ActorObservationBuilder().build(
        subject.session,
        subject.runtime.action_registry,
        ACTOR_ID,
    ).to_dict()
    private = subject.session.state.entities[AREA_ID].components[F2_COMPONENT]
    inventory = subject.session.state.entities[ACTOR_ID].components[
        "pmw_gameplay_material_inventory"
    ]["quantities"]
    fields = base["area"]["fields"]
    completed = base["clock"]["last_completed_step"]
    known_actions = []
    if inventory[REPAIR_MATERIAL] == 1 and private["repair_mode"] is None:
        known_actions.extend(("repair_water", "repair_resonance"))
    if completed < 3 and private["repair_mode"] is None:
        if not private["calibrated"]:
            known_actions.append("calibrate")
        if private["forged_probe"] is None and inventory[DIAGNOSTIC_MATERIAL] == 1:
            known_actions.extend(("forge_water", "forge_resonance"))
        if private["forged_probe"] is not None and not private["probe_used"]:
            known_actions.append("probe")
    document = {
        "protocol": "gccp-f2-public-observation-v0.1",
        "clock": {
            "world_tick": completed,
            "sim_time": base["clock"]["sim_time"],
            "next_step": base["clock"]["next_step"],
        },
        "water": fields["water"]["value"],
        "resonance": fields["resonance"]["value"],
        "stability": private["stability"],
        "calibrated_interface": private["measured_interface"] if private["calibrated"] else None,
        "forged_probe": private["forged_probe"],
        "probe_used": private["probe_used"],
        "probe_implemented": private["probe_implemented"] if private["probe_used"] else None,
        "repair_mode": private["repair_mode"],
        "resources": {
            "diagnostic_blanks": inventory[DIAGNOSTIC_MATERIAL],
            "repair_kits": inventory[REPAIR_MATERIAL],
        },
        "known_actions": sorted(known_actions),
    }
    assert not (FORBIDDEN_KEYS & set(document))
    return json.loads(json.dumps(document, sort_keys=True, allow_nan=False))


def observation_key(document: dict[str, Any]) -> str:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)


def observation_digest(document: dict[str, Any]) -> str:
    return hashlib.sha256(observation_key(document).encode("ascii")).hexdigest()
