from __future__ import annotations

from copy import deepcopy
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRequest, resolve_action
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import AIController, HumanController, run_combat_round, run_gate2_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import run_phase_event
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate2_actions import make_session


class StatusLifecycleTests(unittest.TestCase):
    def test_guard_expires_at_next_owner_turn_and_clears_own_slot(self):
        session, registry = make_session(actors=1)
        resolve_action(session, registry, ActionRequest("request_1", "actor_0", "basic_guard"))
        result = run_phase_event(session, "owner_turn", actor_id="actor_0")
        actor = session.state.entities["actor_0"]
        self.assertTrue(result.changed)
        self.assertEqual(actor.components["pmw_gameplay_actor"]["shield"], 0)
        self.assertFalse(actor.components["pmw_gameplay_statuses"]["slots"]["slot_0"]["active"])

    def test_other_owner_turn_does_not_expire_status(self):
        session, registry = make_session()
        resolve_action(session, registry, ActionRequest("request_1", "actor_0", "basic_guard"))
        run_phase_event(session, "owner_turn", actor_id="actor_1")
        self.assertEqual(session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"], 8)

    def test_status_capacity_failure_does_not_charge_or_shield(self):
        session, registry = make_session(actors=1)
        entity = session.state.entities["actor_0"]
        entity.components["pmw_gameplay_statuses"] = {"slots": {f"slot_{i}": {"active": True, "spec_id": f"occupied_{i}"} for i in range(8)}}
        before = deepcopy(session.state.to_dict())
        with self.assertRaises(GameplayContractError): resolve_action(session, registry, ActionRequest("request_1", "actor_0", "basic_guard"))
        self.assertEqual(session.state.to_dict(), before)


class CombatTests(unittest.TestCase):
    def test_human_and_ai_controllers_produce_same_request_type(self):
        request = ActionRequest("request_1", "actor_0", "basic_wait")
        self.assertEqual(HumanController().request(request), AIController().request(request))

    def test_sequential_commit_changes_later_damage_resolution(self):
        session, registry = make_session()
        result = run_combat_round(session, registry, round_index=1, actor_order=("actor_0", "actor_1"), requests={
            "actor_0": ActionRequest("request_1", "actor_0", "basic_guard"),
            "actor_1": ActionRequest("request_2", "actor_1", "basic_attack", "actor_0"),
        })
        actor = session.state.entities["actor_0"].components["pmw_gameplay_actor"]
        self.assertEqual(actor["shield"], 0)
        self.assertEqual(actor["hp"], 94)
        self.assertEqual(result.world_tick_result.step, 1)

    def test_actor_count_does_not_accelerate_world_tick(self):
        one, registry = make_session(actors=1); many, registry_many = make_session(actors=4)
        run_combat_round(one, registry, round_index=1, actor_order=("actor_0",), requests={})
        run_combat_round(many, registry_many, round_index=1, actor_order=tuple(f"actor_{i}" for i in range(4)), requests={})
        self.assertEqual(one.state.entities["pmw:v04:clock"].components["pmw_gameplay_clock"]["last_completed_step"], 1)
        self.assertEqual(many.state.entities["pmw:v04:clock"].components["pmw_gameplay_clock"]["last_completed_step"], 1)

    def test_duplicate_actor_order_rejected(self):
        session, registry = make_session()
        with self.assertRaises(GameplayContractError): run_combat_round(session, registry, round_index=1, actor_order=("actor_0", "actor_0"), requests={})

    def test_demo_is_deterministic_and_advances_one_tick_per_round(self):
        left, right = run_gate2_demo(), run_gate2_demo()
        self.assertEqual(left, right)
        self.assertEqual(left["world_tick"], 2)
