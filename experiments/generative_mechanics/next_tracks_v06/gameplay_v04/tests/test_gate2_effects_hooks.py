from __future__ import annotations

from copy import deepcopy
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRegistry, ActionRequest, resolve_action
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.attributes import evaluate_terms, parse_attribute_term
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry_document
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import effective_traits
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.hooks import HookLineage, execute_hook, parse_hook
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import advance_world_tick, run_phase_event
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.status import cancel_status
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate2_actions import make_session


def registry_with(action, statuses=(), hooks=()):
    doc = basic_registry_document(); doc["actions"].append(action); doc["statuses"].extend(statuses); doc["hooks"] = list(hooks)
    return ActionRegistry.parse(doc)


def action(action_id, effects, *, mana=0):
    return {"id": action_id, "version": 1, "action_type": "skill", "cost": {"duration": 1, "mana": mana},
            "scope": {"selectors": sorted({e["target"]["kind"] for e in effects}), "relation_types": []}, "effects": effects}


class AttributeAndConditionTests(unittest.TestCase):
    def test_four_explicit_term_types_have_stable_order(self):
        terms = tuple(parse_attribute_term(raw) for raw in [
            {"kind": "threshold", "attribute": "control", "comparator": "gte", "threshold": 5},
            {"kind": "check", "attribute": "agility", "comparator": "gt", "threshold": 1},
            {"kind": "scaling", "attribute": "power", "coefficient": 2},
            {"kind": "modifier", "attribute": "resilience", "operation": "add", "value": .5},
            {"kind": "modifier", "attribute": "control", "operation": "multiply", "value": .1},
        ])
        passed, value, trace = evaluate_terms(10, terms, {"power": 3, "control": 5, "resilience": 4, "agility": 2})
        self.assertTrue(passed); self.assertEqual(value, 27); self.assertEqual(trace[0]["kind"], "threshold")

    def test_attribute_check_failure_is_atomic_for_required_effect(self):
        effect = {"id": "strict_hit", "kind": "damage", "target": {"kind": "target_actor"}, "commitment": "required", "amount": 5,
                  "attribute_terms": [{"kind": "threshold", "attribute": "power", "comparator": "gt", "threshold": 999}]}
        registry = registry_with(action("strict_skill", [effect], mana=3)); session, _ = make_session(registry)
        before = deepcopy(session.state.to_dict())
        with self.assertRaises(GameplayContractError): resolve_action(session, registry, ActionRequest("request_1", "actor_0", "strict_skill", "actor_1"))
        self.assertEqual(session.state.to_dict(), before)

    def test_conditional_effect_skips_but_action_costs_mana(self):
        effect = {"id": "optional_hit", "kind": "damage", "target": {"kind": "target_actor"}, "commitment": "conditional", "amount": 5,
                  "condition": {"attribute": {"subject": "self", "key": "power", "comparator": "gt", "value": 999}}}
        registry = registry_with(action("optional_skill", [effect], mana=3)); session, _ = make_session(registry)
        outcome = resolve_action(session, registry, ActionRequest("request_1", "actor_0", "optional_skill", "actor_1"))
        self.assertEqual(session.state.entities["actor_0"].components["pmw_gameplay_actor"]["mana"], 17)
        self.assertEqual(session.state.entities["actor_1"].components["pmw_gameplay_actor"]["hp"], 100)
        self.assertEqual(outcome.effect_outcomes[0]["status"], "skipped")


class EffectTemplateTests(unittest.TestCase):
    def test_heal_and_resource_clamp(self):
        effects = [{"id": "heal", "kind": "heal", "target": {"kind": "self"}, "commitment": "required", "amount": 50},
                   {"id": "mana", "kind": "add_resource", "target": {"kind": "target_actor"}, "commitment": "required", "resource": "mana", "amount": 100}]
        registry = registry_with(action("restore_skill", effects)); session, _ = make_session(registry)
        session.state.entities["actor_0"].components["pmw_gameplay_actor"]["hp"] = 60
        resolve_action(session, registry, ActionRequest("request_1", "actor_0", "restore_skill", "actor_1"))
        self.assertEqual(session.state.entities["actor_0"].components["pmw_gameplay_actor"]["hp"], 100)
        self.assertEqual(session.state.entities["actor_1"].components["pmw_gameplay_actor"]["mana"], 50)

    def test_modify_field_is_a_pmw_traced_write(self):
        effect = {"id": "mist", "kind": "modify_field", "target": {"kind": "current_area"}, "commitment": "required", "field_id": "mist", "amount": .6}
        registry = registry_with(action("mist_skill", [effect])); session, _ = make_session(registry, actors=1)
        outcome = resolve_action(session, registry, ActionRequest("request_1", "actor_0", "mist_skill"))
        field = session.state.entities["arena_area"].components["pmw_gameplay_dynamics"]["fields"]["mist"]
        self.assertAlmostEqual(field["value"], .8)
        self.assertIn("pmw_gameplay_dynamics/fields/mist/value", str(outcome.event_result.trace.to_dict()))

    def test_temporary_attractor_and_rate_use_owned_slots_and_expire(self):
        for kind, amount in (("modify_attractor", .8), ("modify_rate", .05)):
            with self.subTest(kind=kind):
                effect = {"id": "dynamic", "kind": kind, "target": {"kind": "current_area"}, "commitment": "required",
                          "field_id": "mist", "amount": amount, "duration": 2}
                registry = registry_with(action(f"{kind}_skill", [effect])); session, _ = make_session(registry, actors=1)
                resolve_action(session, registry, ActionRequest("request_1", "actor_0", f"{kind}_skill"))
                slots = session.state.entities["arena_area"].components["pmw_gameplay_dynamics"]["fields"]["mist"]["temporary_modifiers"]
                self.assertTrue(slots["slot_0"]["active"]); self.assertEqual(len(session.state.scheduled_events), 1)
                advance_world_tick(session); advance_world_tick(session)
                slots = session.state.entities["arena_area"].components["pmw_gameplay_dynamics"]["fields"]["mist"]["temporary_modifiers"]
                self.assertFalse(slots["slot_0"]["active"]); self.assertEqual(session.state.scheduled_events, [])

    def test_apply_status_periodic_and_cancel_exact_owner(self):
        status = {"id": "renewing", "version": 1, "polarity": "buff", "max_stacks": 2, "stack_policy": "add_stacks",
                  "duration": {"unit": "world_tick", "amount": 2}, "granted_traits": ["renewing"],
                  "periodic_resource": {"resource": "mana", "delta": 2}}
        effect = {"id": "renew", "kind": "apply_status", "target": {"kind": "self"}, "commitment": "required", "status_id": "renewing"}
        registry = registry_with(action("renew_skill", [effect]), [status]); session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest("request_1", "actor_0", "renew_skill"))
        actor = session.state.entities["actor_0"]
        self.assertIn("renewing", effective_traits({**actor.components["pmw_gameplay_actor"], "status_slots": actor.components["pmw_gameplay_statuses"]["slots"]}))
        advance_world_tick(session); actor = session.state.entities["actor_0"]
        self.assertGreater(actor.components["pmw_gameplay_actor"]["mana"], 20)
        with self.assertRaises(GameplayContractError): cancel_status(session, registry, owner_id="actor_0", instance_id="request_1:renew", requester_id="actor_1")
        result = cancel_status(session, registry, owner_id="actor_0", instance_id="request_1:renew", requester_id="actor_0")
        self.assertTrue(result.changed)

    def test_status_add_stacks_is_bounded_and_refreshes_duration(self):
        status = {"id": "charge", "version": 1, "polarity": "buff", "max_stacks": 2, "stack_policy": "add_stacks",
                  "duration": {"unit": "combat_round", "amount": 2}, "granted_traits": []}
        effect = {"id": "charge", "kind": "apply_status", "target": {"kind": "self"}, "commitment": "required", "status_id": "charge"}
        registry = registry_with(action("charge_skill", [effect]), [status]); session, _ = make_session(registry, actors=1)
        for index in range(3): resolve_action(session, registry, ActionRequest(f"request_{index}", "actor_0", "charge_skill"))
        slot = session.state.entities["actor_0"].components["pmw_gameplay_statuses"]["slots"]["slot_0"]
        self.assertEqual(slot["stacks"], 2); self.assertEqual(slot["remaining"], 2)
        run_phase_event(session, "combat_round")
        slot = session.state.entities["actor_0"].components["pmw_gameplay_statuses"]["slots"]["slot_0"]
        self.assertEqual(slot["remaining"], 1)

    def test_duplicate_temporal_handle_failure_is_atomic(self):
        effect = {"id": "dynamic", "kind": "modify_rate", "target": {"kind": "current_area"},
                  "commitment": "required", "field_id": "mist", "amount": .01, "duration": 2}
        registry = registry_with(action("rate_skill", [effect], mana=2)); session, _ = make_session(registry, actors=1)
        request = ActionRequest("request_same", "actor_0", "rate_skill")
        resolve_action(session, registry, request); before = deepcopy(session.state.to_dict())
        with self.assertRaises(Exception): resolve_action(session, registry, request)
        self.assertEqual(session.state.to_dict(), before)

    def test_grant_trait_expires_by_owner_turn(self):
        effect = {"id": "focus", "kind": "grant_trait", "target": {"kind": "self"}, "commitment": "required", "trait_id": "focused", "duration": 1}
        registry = registry_with(action("focus_skill", [effect])); session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest("request_1", "actor_0", "focus_skill"))
        actor = session.state.entities["actor_0"]
        slots = actor.components["pmw_gameplay_statuses"]["slots"]
        self.assertIn("focused", effective_traits({**actor.components["pmw_gameplay_actor"], "status_slots": slots}))
        run_phase_event(session, "owner_turn", actor_id="actor_0")
        actor = session.state.entities["actor_0"]; slots = actor.components["pmw_gameplay_statuses"]["slots"]
        self.assertNotIn("focused", effective_traits({**actor.components["pmw_gameplay_actor"], "status_slots": slots}))


class HookContractTests(unittest.TestCase):
    def test_hook_schema_and_cycle_budget(self):
        hook = parse_hook({"id": "on_damage", "trigger": "damage_resolved", "condition": None,
                           "effect_ids": ["counter"], "action_id": "counter_skill", "max_firings_per_root": 2})
        self.assertEqual(hook.trigger, "damage_resolved")
        lineage = HookLineage("root", None, 0, 2).fire("status:on_damage")
        with self.assertRaises(GameplayContractError): lineage.fire("status:on_damage")
        lineage = lineage.fire("trait:counter")
        with self.assertRaises(GameplayContractError): lineage.fire("third")

    def test_hook_effect_executes_through_pmw_without_main_action_cost(self):
        effect = {"id": "counter", "kind": "damage", "target": {"kind": "target_actor"}, "commitment": "required", "amount": 3}
        hook_raw = {"id": "on_damage", "trigger": "damage_resolved", "condition": None,
                    "effect_ids": ["counter"], "action_id": "counter_skill", "max_firings_per_root": 1, "cooldown": 2}
        registry = registry_with(action("counter_skill", [effect], mana=9), hooks=[hook_raw]); session, _ = make_session(registry)
        hook = registry.hooks["on_damage"]
        outcome, lineage = execute_hook(session, registry, hook, HookLineage("root", None, 0, 1),
                                        actor_id="actor_0", target_actor_id="actor_1", trigger="damage_resolved")
        self.assertEqual(session.state.entities["actor_0"].components["pmw_gameplay_actor"]["mana"], 20)
        self.assertEqual(session.state.entities["actor_1"].components["pmw_gameplay_actor"]["hp"], 97)
        self.assertTrue(outcome.event_result.trace.events); self.assertEqual(lineage.remaining_budget, 0)
        self.assertEqual(session.state.entities["actor_0"].components["pmw_gameplay_hooks"]["cooldowns"]["on_damage"], 2)
        with self.assertRaises(GameplayContractError):
            execute_hook(session, registry, hook, HookLineage("other", None, 0, 1),
                         actor_id="actor_0", target_actor_id="actor_1", trigger="damage_resolved")
