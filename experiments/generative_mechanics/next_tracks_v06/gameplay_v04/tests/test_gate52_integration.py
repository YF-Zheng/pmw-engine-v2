from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRequest,
    resolve_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import (
    run_combat_round,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import (
    build_gate3_demo,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.harvest import (
    HarvestRequest,
    resolve_harvest,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    run_phase_event,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.shields import (
    SHIELD_COMPONENT,
    validate_status_shield_ownership,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.status import (
    STATUS_COMPONENT,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    spend_world_time,
)


def _aegis_skills(statuses):
    material = parse_material({
        "id": "aegis_ore",
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "layered_guard",
            "effect_kinds": ["shield", "apply_status"],
            "selectors": ["self"],
            "budget_points": 10,
        }],
    })
    authority = material_authority((material,))
    result = []
    for skill_id, amount in (("aegis_a", 11), ("aegis_b", 17)):
        result.append(parse_skill_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "skill_blueprint",
            "id": skill_id,
            "version": 1,
            "trigger": "on_use",
            "condition": None,
            "duration": None,
            "cost": {"duration": 1, "mana": 0},
            "scope": {"selectors": ["self"], "relation_types": []},
            "effects": [
                {
                    "id": "layer",
                    "kind": "shield",
                    "target": {"kind": "self"},
                    "commitment": "required",
                    "amount": amount,
                },
                {
                    "id": "lifetime",
                    "kind": "apply_status",
                    "target": {"kind": "self"},
                    "commitment": "required",
                    "status_id": "basic_guarding",
                },
            ],
            "budget": {"limit": 10},
            "max_firings_per_root": 1,
            "material_ids": ["aegis_ore"],
        }, statuses, authority))
    return tuple(result)


def _build_integrated_runtime():
    original_session, original, _, harvest = build_gate3_demo(time_budget_ticks=6)
    skills = _aegis_skills(original.action_registry.statuses)
    content = make_content(
        original.action_registry,
        skills=skills,
        weather_by_area=original.weather_by_area,
        ecology_by_area=original.ecology_by_area,
        harvest_by_area=original.harvest_by_area,
        stock_amounts_by_area=original.stock_amounts_by_area,
        material_ids=(*original.material_ids, "aegis_ore"),
    )
    world = initialize_content_world(original_session.state, content)
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    return MechanismRegistryRuntime.from_compiled_content(session, compiled), compiled, skills, harvest


class Gate52FinalIntegration(unittest.TestCase):
    def test_full_authoritative_limited_world_chain(self):
        runtime, compiled, skills, harvest = _build_integrated_runtime()

        explored = spend_world_time(runtime.session, 1, reason="exploration")
        self.assertEqual((explored.duration, len(explored.ticks)), (1, 1))

        gathered = resolve_harvest(
            runtime.session,
            runtime.action_registry,
            harvest,
            HarvestRequest("gate52_harvest", "hero_actor", harvest.id, True),
            permissions=("lucky_harvest",),
        )
        self.assertEqual((gathered.duration, len(gathered.time_result.ticks)), (1, 1))

        for slot, skill in enumerate(skills):
            change_loadout(
                runtime.session,
                runtime.manifest,
                actor_id="hero_actor",
                operation="equip_active",
                skill=skill_ref(skill),
                slot=slot,
            )
            outcome = resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"gate52_{skill.id}", "hero_actor", skill.id),
            )
            self.assertTrue(outcome.event_result.trace.events)

        hero = runtime.session.state.entities["hero_actor"]
        self.assertEqual(hero.components["pmw_gameplay_actor"]["shield"], 28)
        validate_status_shield_ownership(
            hero.components[STATUS_COMPONENT], hero.components[SHIELD_COMPONENT]
        )
        owners = {
            row["status_instance_id"]
            for row in hero.components[SHIELD_COMPONENT]["slots"].values()
            if row["active"] and row["status_instance_id"] is not None
        }
        self.assertEqual(owners, {"gate52_aegis_a:lifetime", "gate52_aegis_b:lifetime"})

        combat = run_combat_round(
            runtime.session,
            runtime.action_registry,
            round_index=1,
            actor_order=("plain_actor",),
            requests={
                "plain_actor": ActionRequest(
                    "gate52_enemy_attack", "plain_actor", "basic_attack", "hero_actor"
                )
            },
        )
        self.assertEqual(combat.time_spend_result.duration, 1)
        self.assertEqual(
            runtime.session.state.entities["hero_actor"].components["pmw_gameplay_actor"]["shield"],
            18,
        )

        expiry = run_phase_event(runtime.session, "owner_turn", actor_id="hero_actor")
        self.assertTrue(expiry.changed)
        hero = runtime.session.state.entities["hero_actor"]
        self.assertEqual(hero.components["pmw_gameplay_actor"]["shield"], 0)
        validate_status_shield_ownership(
            hero.components[STATUS_COMPONENT], hero.components[SHIELD_COMPONENT]
        )

        rested = spend_world_time(runtime.session, 1, reason="rest")
        self.assertEqual(rested.after_remaining, 2)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate52-checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)

        self.assertEqual(restored.session.state.to_dict(), runtime.session.state.to_dict())
        exhausted = spend_world_time(restored.session, 2, reason="offline")
        self.assertEqual(exhausted.after_remaining, 0)
        budget = restored.session.state.entities["pmw:v04:clock"].components[
            TIME_BUDGET_COMPONENT
        ]
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (6, 0))

        before = deepcopy(restored.session.state.to_dict())
        with self.assertRaises(GameplayContractError):
            spend_world_time(restored.session, 1, reason="move")
        self.assertEqual(restored.session.state.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
