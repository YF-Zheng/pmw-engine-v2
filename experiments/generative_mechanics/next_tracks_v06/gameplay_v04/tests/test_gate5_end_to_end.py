from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRequest, resolve_action
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_area, parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint, save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import run_combat_round
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import build_content_session, compile_content
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import DynamicsSource, GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.explanations import ExplanationSource, explain_result
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import build_gate3_demo, run_gate3_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate5_demo import run_gate5_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.harvest import HarvestRequest, resolve_harvest
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import change_loadout, skill_ref
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import MaterialAuthority
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import MechanismRegistryRuntime
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick, apply_source, build_runtime, clock_entity, discover_profiles,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate2_actions import make_session
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT, initialize_time_budget, spend_world_time,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import build_gameplay_world


TIMED_AUTHORITY = MaterialAuthority(
    ("mist_crystal",), ("modify_rate",), ("current_area",), 8.0,
)


def _timed_skill() -> dict:
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "skill_blueprint",
        "id": "e2e_slow_mist", "version": 1, "trigger": "on_use",
        "condition": None, "duration": None,
        "cost": {"duration": 1, "mana": 0},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": [{
            "id": "slow_recovery", "kind": "modify_rate",
            "target": {"kind": "current_area"}, "commitment": "required",
            "field_id": "mist", "amount": -0.02, "duration": 2,
        }],
        "budget": {"limit": 6}, "max_firings_per_root": 1,
        "material_ids": ["mist_crystal"],
    }


class EndToEndScenarios(unittest.TestCase):
    def test_integrated_demo_is_deterministic(self):
        self.assertEqual(run_gate5_demo(), run_gate5_demo())

    def test_one_blueprint_two_area_instances_remain_independent(self):
        blueprint = parse_area_blueprint({
            "protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint", "id": "shared_area",
            "fields": [{
                "id": "heat", "domain": {"min": 0, "max": 1}, "initial": 0.2,
                "target": 0.8, "rate": 0.25, "curve": "linear",
                "max_persistent_patches": 2, "max_temporary_modifiers": 2,
            }],
        })
        left = instantiate_area(blueprint, "left_area")
        right = instantiate_area(blueprint, "right_area")
        world = build_gameplay_world("two_area_e2e", areas=[left, right])
        clock = clock_entity(); world.entities[clock.id] = clock
        session = build_runtime(world, discover_profiles(world))
        apply_source(session, entity_id="left_area", field_id="heat", layer="persistent",
                     source=DynamicsSource("left_weather", "left_area", target=1.0, target_weight=1.0))
        advance_world_tick(session)
        left_value = session.state.entities["left_area"].components["pmw_gameplay_dynamics"]["fields"]["heat"]["value"]
        right_value = session.state.entities["right_area"].components["pmw_gameplay_dynamics"]["fields"]["heat"]["value"]
        self.assertNotEqual(left_value, right_value)
        self.assertAlmostEqual(right_value, 0.35)

    def test_weather_trait_and_combat_share_the_same_world(self):
        session, content, _, _ = build_gate3_demo()
        advance_world_tick(session)
        hero = session.state.entities["hero_actor"].components["pmw_gameplay_actor"]
        plain = session.state.entities["plain_actor"].components["pmw_gameplay_actor"]
        self.assertEqual((hero["mana"], plain["mana"]), (11.0, 10.0))
        result = run_combat_round(
            session, content.action_registry, round_index=1,
            actor_order=("hero_actor", "plain_actor"),
            requests={
                "hero_actor": ActionRequest("e2e_guard", "hero_actor", "basic_guard"),
                "plain_actor": ActionRequest("e2e_attack", "plain_actor", "basic_attack", "hero_actor"),
            },
        )
        self.assertEqual(result.world_tick_result.step, 2)
        self.assertEqual(hero["hp"], hero["max_hp"])
        self.assertEqual(hero["shield"], 0.0)
        self.assertEqual([item.definition.id for item in result.outcomes], ["basic_guard", "basic_attack"])
        self.assertEqual(session.state.entities["mist_forest"].components["pmw_gameplay_weather"]["states"]["living_mist"]["active"], True)

    def test_harvest_time_yield_consumption_and_ecology_are_separate(self):
        session, content, _, harvest = build_gate3_demo()
        lucky = resolve_harvest(
            session, content.action_registry, harvest,
            HarvestRequest("e2e_lucky", "hero_actor", harvest.id, True),
            permissions=("lucky_harvest",),
        )
        ordinary = resolve_harvest(
            session, content.action_registry, harvest,
            HarvestRequest("e2e_ordinary", "hero_actor", harvest.id),
        )
        self.assertEqual((lucky.duration, ordinary.duration), (1, 2))
        self.assertEqual((lucky.yield_amount, ordinary.yield_amount), (2.0, 1.0))
        self.assertEqual((lucky.consumption, ordinary.consumption), (0.2, 0.2))
        area = session.state.entities["mist_forest"]
        self.assertAlmostEqual(area.components["pmw_gameplay_dynamics"]["fields"]["herbs"]["value"], 0.3)
        self.assertAlmostEqual(area.components["pmw_gameplay_dynamics"]["fields"]["herbs"]["baseline"]["target"], 0.6)
        resolve_harvest(session, content.action_registry, harvest,
                        HarvestRequest("e2e_last", "hero_actor", harvest.id))
        with self.assertRaises(GameplayContractError):
            resolve_harvest(session, content.action_registry, harvest,
                            HarvestRequest("e2e_exhausted", "hero_actor", harvest.id))

    def test_forest_sustained_threshold_changes_ecology_and_attractor(self):
        result = run_gate3_demo()
        self.assertEqual(result["ecology"]["current"], "depleted")
        self.assertEqual(result["ecology"]["baseline"], {
            "target": 0.2, "target_weight": 1.0, "rate": 0.02, "curve": "linear",
        })
        self.assertTrue(result["trace_present"])

    def test_runtime_registration_disable_and_checkpoint_continuation(self):
        session, content, _, _ = build_gate3_demo()
        compiled = compile_content(content)
        runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
        runtime.install(_timed_skill(), TIMED_AUTHORITY)
        skill = runtime.blueprints[("e2e_slow_mist", 1)]
        change_loadout(runtime.session, runtime.manifest, actor_id="hero_actor",
                       operation="equip_active", skill=skill_ref(skill), slot=0)
        resolve_action(runtime.session, runtime.action_registry,
                       ActionRequest("e2e_cast", "hero_actor", skill.id))
        advance_world_tick(runtime.session)
        change_loadout(runtime.session, runtime.manifest, actor_id="hero_actor",
                       operation="unload_active", slot=0)
        runtime.disable(skill.id)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
        self.assertNotIn(skill.id, restored.action_registry.actions)
        left = runtime.session.runtime.advance_to(2.0)
        right = restored.session.runtime.advance_to(2.0)
        self.assertEqual(left.processed_event_ids, right.processed_event_ids)
        self.assertEqual(runtime.session.state.to_dict(), restored.session.state.to_dict())


class TimeAndTraceLedger(unittest.TestCase):
    def test_combat_round_costs_one_world_tick_regardless_of_actor_count(self):
        one, registry_one = make_session(actors=1)
        many, registry_many = make_session(actors=6)
        run_combat_round(one, registry_one, round_index=1, actor_order=("actor_0",), requests={})
        run_combat_round(many, registry_many, round_index=1,
                         actor_order=tuple(f"actor_{i}" for i in range(6)), requests={})
        self.assertEqual(one.state.tick, many.state.tick)
        self.assertEqual(one.state.sim_time, many.state.sim_time)

    def test_zero_time_or_infinite_harvest_is_impossible(self):
        session, content, _, harvest = build_gate3_demo()
        durations = []
        for index in range(10):
            try:
                outcome = resolve_harvest(
                    session, content.action_registry, harvest,
                    HarvestRequest(f"ledger_{index}", "hero_actor", harvest.id, True),
                    permissions=("lucky_harvest",),
                )
            except GameplayContractError:
                break
            durations.append(outcome.duration)
        self.assertEqual(durations, [1, 1, 1])
        self.assertGreaterEqual(sum(durations), len(durations))

    def test_exploration_and_offline_time_use_the_same_finite_world_ticks(self):
        original, content, _, harvest = build_gate3_demo()
        world = initialize_time_budget(original.state, 4)
        session = build_content_session(world, compile_content(content))
        gathered = resolve_harvest(
            session, content.action_registry, harvest,
            HarvestRequest("timed_harvest", "hero_actor", harvest.id, True),
            permissions=("lucky_harvest",),
        )
        exploration = spend_world_time(session, gathered.duration, reason="harvest")
        offline = spend_world_time(session, 2, reason="offline")
        budget = session.state.entities["pmw:v04:clock"].components[TIME_BUDGET_COMPONENT]
        self.assertEqual((exploration.duration, len(exploration.ticks)), (1, 1))
        self.assertEqual((offline.duration, len(offline.ticks)), (2, 2))
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (3, 1))
        before = session.state.to_dict()
        with self.assertRaises(GameplayContractError):
            spend_world_time(session, 2, reason="exploration")
        self.assertEqual(session.state.to_dict(), before)

    def test_deterministic_formal_replay_and_readable_causal_sources(self):
        def execute():
            session, content, skill, harvest = build_gate3_demo()
            change_loadout(session, content.manifest, actor_id="hero_actor",
                           operation="equip_active", skill=skill_ref(skill), slot=0)
            tick = advance_world_tick(session)
            gathered = resolve_harvest(
                session, content.action_registry, harvest,
                HarvestRequest("replay_harvest", "hero_actor", harvest.id),
            )
            cast = resolve_action(
                session, content.action_registry,
                ActionRequest("replay_cast", "hero_actor", skill.id, "plain_actor"),
            )
            explanation = explain_result(
                cast.event_result, event="Mist Bolt",
                sources=(ExplanationSource("skill", skill.id, "Mist Bolt", "damage and mist"),),
                values={"enemy_hp": session.state.entities["plain_actor"].components["pmw_gameplay_actor"]["hp"]},
            )
            return {
                "world": session.state.to_dict(),
                "traces": [tick.event_result.trace.to_dict(), gathered.event_result.trace.to_dict(),
                           cast.event_result.trace.to_dict()],
                "explanation": explanation,
            }
        left, right = execute(), execute()
        self.assertEqual(left, right)
        self.assertEqual(left["explanation"]["sources"][0]["id"], "mist_bolt")
        self.assertTrue(left["explanation"]["causal_trace"]["events"])


if __name__ == "__main__":
    unittest.main()
