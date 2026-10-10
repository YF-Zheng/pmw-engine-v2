"""Independent Role-D adversarial verification for the v0.4 gameplay gates."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from pmw import parse_law

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import build_action_session
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    resolve_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ai_demo import ai_demo_session
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
    basic_registry_document,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_actor,
    instantiate_area,
    parse_actor_blueprint,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import run_combat_round
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import compile_content
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    DynamicsSource,
    FieldDefinition,
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.dynamics import evaluate_field
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import build_gate3_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import change_loadout, skill_ref
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import MaterialAuthority
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import (
    ActorObservationBuilder,
    ObservationDisclosure,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.planner import BoundedPlanner, PlannerConfig
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import MechanismRegistryRuntime
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    clock_entity,
    discover_profiles,
    run_phase_event,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import build_gameplay_world


def _actor_document() -> dict:
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": "qa_actor",
        "hp": {"max": 100, "initial": 100},
        "mana": {"max": 50, "initial": 20, "dynamics": None},
        "attributes": {"power": 8, "control": 7, "resilience": 6, "agility": 5},
        "traits": [],
    }


def _area_document() -> dict:
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": "qa_area",
        "fields": [{
            "id": "mist",
            "domain": {"min": 0, "max": 1},
            "initial": 0.2,
            "target": 0.2,
            "rate": 0.1,
            "curve": "linear",
            "max_persistent_patches": 2,
            "max_temporary_modifiers": 2,
        }],
    }


def _action_session(registry: ActionRegistry, actor_count: int = 2):
    actor_blueprint = parse_actor_blueprint(_actor_document())
    actors = [
        instantiate_actor(actor_blueprint, f"qa_actor_{index}", controller="ai")
        for index in range(actor_count)
    ]
    area = instantiate_area(parse_area_blueprint(_area_document()), "qa_arena")
    world = build_gameplay_world(
        "independent_qa",
        areas=[area],
        actors=actors,
        placements=[(actor.id, area.id) for actor in actors],
    )
    clock = clock_entity()
    world.entities[clock.id] = clock
    return build_action_session(world, discover_profiles(world), registry)


def _registry_runtime():
    session, content, _, _ = build_gate3_demo()
    compiled = compile_content(content)
    return MechanismRegistryRuntime.from_compiled_content(session, compiled), compiled


def _timed_skill_document() -> dict:
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": "qa_slow_mist",
        "version": 1,
        "trigger": "on_use",
        "condition": None,
        "duration": None,
        "cost": {"duration": 1, "mana": 0},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": [{
            "id": "qa_slow_recovery",
            "kind": "modify_rate",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "mist",
            "amount": -0.02,
            "duration": 2,
        }],
        "budget": {"limit": 6},
        "max_firings_per_root": 1,
        "material_ids": ["mist_crystal"],
    }


TIMED_AUTHORITY = MaterialAuthority(
    ("mist_crystal",), ("modify_rate",), ("current_area",), 8.0,
)


class IndependentAtomicityTests(unittest.TestCase):
    def test_true_conditional_before_failed_required_effect_is_fully_atomic(self):
        document = basic_registry_document()
        document["actions"].append({
            "id": "qa_composite",
            "version": 1,
            "action_type": "skill",
            "builtin": False,
            "cost": {"duration": 2, "mana": 3},
            "scope": {"selectors": ["self", "target_actor", "current_area"], "relation_types": []},
            "effects": [
                {
                    "id": "conditional_field_write",
                    "kind": "modify_field",
                    "target": {"kind": "current_area"},
                    "commitment": "conditional",
                    "condition": {"field": {
                        "subject": "current_area", "key": "mist",
                        "comparator": "gte", "value": 0,
                    }},
                    "field_id": "mist",
                    "amount": 0.5,
                },
                {
                    "id": "required_impossible_damage",
                    "kind": "damage",
                    "target": {"kind": "target_actor"},
                    "commitment": "required",
                    "condition": {"resource": {
                        "subject": "target_actor", "key": "hp",
                        "comparator": "lt", "value": 0,
                    }},
                    "amount": 9,
                },
                {
                    "id": "unreached_conditional_heal",
                    "kind": "heal",
                    "target": {"kind": "self"},
                    "commitment": "conditional",
                    "amount": 1,
                },
            ],
        })
        registry = ActionRegistry.parse(document)
        session = _action_session(registry)
        before = deepcopy(session.state.to_dict())

        with self.assertRaisesRegex(GameplayContractError, "required effect"):
            resolve_action(
                session,
                registry,
                ActionRequest("qa_atomic", "qa_actor_0", "qa_composite", "qa_actor_1"),
            )

        self.assertEqual(session.state.to_dict(), before)
        self.assertEqual(session.state.scheduled_events, [])


class IndependentDynamicsOracleTests(unittest.TestCase):
    def test_linear_and_distance_squared_match_closed_form_oracles(self):
        source = DynamicsSource(
            "qa_patch", "qa_owner", target=2.0, target_weight=3.0,
            rate_add=0.05, rate_multiplier=0.5,
        )
        expected_target = (1.0 + 3.0 * 2.0) / 4.0
        expected_rate = (0.2 + 0.05) * 0.5
        difference = expected_target - (-1.0)

        linear = evaluate_field(
            FieldDefinition("qa_field", -2.0, 2.0, -1.0, 1.0, 0.2, "linear", 1, 1),
            -1.0,
            persistent=(source,),
        )
        squared = evaluate_field(
            FieldDefinition("qa_field", -2.0, 2.0, -1.0, 1.0, 0.2, "distance_squared", 1, 1),
            -1.0,
            persistent=(source,),
        )

        self.assertAlmostEqual(linear.effective_target, 1.75, delta=1e-12)
        self.assertAlmostEqual(linear.effective_rate, 0.125, delta=1e-12)
        self.assertAlmostEqual(linear.value, -1.0 + expected_rate * difference, delta=1e-12)
        self.assertAlmostEqual(
            squared.value,
            -1.0 + expected_rate * difference * abs(difference),
            delta=1e-12,
        )


class IndependentLifecycleTests(unittest.TestCase):
    def test_status_expiry_after_registry_checkpoint_matches_manual_oracle(self):
        runtime, compiled = _registry_runtime()
        resolve_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_guard", "hero_actor", "basic_guard"),
        )
        actor = runtime.session.state.entities["hero_actor"].components["pmw_gameplay_actor"]
        slots = runtime.session.state.entities["hero_actor"].components["pmw_gameplay_statuses"]["slots"]
        # Gate-3 demo Actor resilience is 3; basic guard is 2 + 1*resilience.
        self.assertEqual(actor["shield"], 5.0)
        self.assertEqual(slots["slot_0"]["remaining"], 1)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)

        left = run_phase_event(runtime.session, "owner_turn", actor_id="hero_actor")
        right = run_phase_event(restored.session, "owner_turn", actor_id="hero_actor")
        for candidate in (runtime, restored):
            entity = candidate.session.state.entities["hero_actor"]
            self.assertEqual(entity.components["pmw_gameplay_actor"]["shield"], 0.0)
            self.assertFalse(entity.components["pmw_gameplay_statuses"]["slots"]["slot_0"]["active"])
        self.assertEqual(left.trace.to_dict(), right.trace.to_dict())
        self.assertEqual(runtime.session.state.to_dict(), restored.session.state.to_dict())

    def test_scheduler_restores_pending_expiry_at_exact_time(self):
        runtime, compiled = _registry_runtime()
        runtime.install(_timed_skill_document(), TIMED_AUTHORITY)
        skill = runtime.blueprints[("qa_slow_mist", 1)]
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id="hero_actor",
            operation="equip_active",
            skill=skill_ref(skill),
            slot=0,
        )
        resolve_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_timed", "hero_actor", "qa_slow_mist"),
        )
        expected_id = "pmw:v04:action-expiry:qa_timed:qa_slow_recovery"
        self.assertEqual(
            [(event.id, event.time) for event in runtime.session.state.scheduled_events],
            [(expected_id, 2.0)],
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheduler_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)

        for candidate in (runtime, restored):
            early = candidate.session.runtime.advance_to(1.999)
            self.assertEqual(early.processed_event_ids, [])
            self.assertEqual(candidate.session.state.scheduled_events[0].id, expected_id)
            due = candidate.session.runtime.advance_to(2.0)
            self.assertEqual(due.processed_event_ids, [expected_id])
            self.assertEqual(candidate.session.state.scheduled_events, [])
            slot = candidate.session.state.entities["mist_forest"].components[
                "pmw_gameplay_dynamics"
            ]["fields"]["mist"]["temporary_modifiers"]["slot_0"]
            self.assertFalse(slot["active"])
        self.assertEqual(runtime.session.state.to_dict(), restored.session.state.to_dict())


class IndependentCombatOrderTests(unittest.TestCase):
    def test_lethal_earlier_commit_prevents_later_actor_action_in_same_round(self):
        registry = basic_registry()
        first = _action_session(registry)
        first.state.entities["qa_actor_1"].components["pmw_gameplay_actor"]["hp"] = 1.0
        result = run_combat_round(
            first,
            registry,
            round_index=1,
            actor_order=("qa_actor_0", "qa_actor_1"),
            requests={
                "qa_actor_0": ActionRequest("qa_first_kill", "qa_actor_0", "basic_attack", "qa_actor_1"),
                "qa_actor_1": ActionRequest("qa_dead_reply", "qa_actor_1", "basic_attack", "qa_actor_0"),
            },
        )
        self.assertEqual(result.skipped, ("qa_actor_1",))
        self.assertEqual([row.request.request_id for row in result.outcomes], ["qa_first_kill"])
        self.assertEqual(first.state.entities["qa_actor_0"].components["pmw_gameplay_actor"]["hp"], 100.0)
        self.assertEqual(result.world_tick_result.step, 1)

        reversed_session = _action_session(registry)
        reversed_session.state.entities["qa_actor_1"].components["pmw_gameplay_actor"]["hp"] = 1.0
        reversed_result = run_combat_round(
            reversed_session,
            registry,
            round_index=1,
            actor_order=("qa_actor_1", "qa_actor_0"),
            requests={
                "qa_actor_0": ActionRequest("qa_late_kill", "qa_actor_0", "basic_attack", "qa_actor_1"),
                "qa_actor_1": ActionRequest("qa_live_reply", "qa_actor_1", "basic_attack", "qa_actor_0"),
            },
        )
        self.assertEqual(reversed_result.skipped, ())
        self.assertEqual(
            [row.request.request_id for row in reversed_result.outcomes],
            ["qa_live_reply", "qa_late_kill"],
        )
        self.assertEqual(
            reversed_session.state.entities["qa_actor_0"].components["pmw_gameplay_actor"]["hp"],
            86.0,
        )


class IndependentAIInformationBoundaryTests(unittest.TestCase):
    def test_hidden_ability_and_hidden_law_cannot_change_observation_or_plan(self):
        left, registry = ai_demo_session()
        right, _ = ai_demo_session()

        hidden_document = basic_registry_document()
        hidden = deepcopy(hidden_document["actions"][0])
        hidden["id"] = "qa_hidden_annihilation"
        hidden["builtin"] = False
        hidden["effects"][0]["amount"] = 9999
        hidden_document["actions"] = [hidden]
        hidden_document["statuses"] = []
        hidden_action = ActionRegistry.parse(hidden_document).actions["qa_hidden_annihilation"]
        augmented = ActionRegistry(
            (*registry.actions.values(), hidden_action),
            registry.statuses.values(),
            registry.hooks.values(),
        )
        right.state.entities["ai_hero"].components["qa_hidden_ability"] = {
            "action_id": "qa_hidden_annihilation", "damage": 9999,
        }
        right.runtime.engine.laws.append(parse_law({
            "id": "qa.hidden.catastrophic_rule",
            "mode": "event",
            "priority": 1,
            "bindings": {
                "victim": {"kind": "entity", "requires": ["pmw_gameplay_actor"]},
            },
            "when": {"all": [
                {"event.type": {"eq": "qa.hidden.trigger"}},
                {"ref": "$victim.id", "eq": "ai_monster"},
            ]},
            "effects": [{
                "op": "set", "target": "$victim.pmw_gameplay_actor.hp", "value": 0,
            }],
        }))

        disclosure = ObservationDisclosure.create(hostile_actor_ids=("ai_hero",))
        builder = ActorObservationBuilder()
        left_observation = builder.build(left, registry, "ai_monster", disclosure)
        right_observation = builder.build(right, augmented, "ai_monster", disclosure)
        self.assertEqual(left_observation.document_json, right_observation.document_json)
        self.assertNotIn("qa_hidden", right_observation.document_json)

        config = PlannerConfig(deadline_ms=None)
        left_plan = BoundedPlanner(registry, config=config).choose(left_observation)
        right_plan = BoundedPlanner(augmented, config=config).choose(right_observation)
        self.assertEqual(left_plan.selected.canonical_key, right_plan.selected.canonical_key)
        self.assertEqual(left_plan.decision_log.document_json, right_plan.decision_log.document_json)


if __name__ == "__main__":
    unittest.main()
