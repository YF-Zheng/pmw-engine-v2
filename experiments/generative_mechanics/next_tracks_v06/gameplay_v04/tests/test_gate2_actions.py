from __future__ import annotations

from copy import deepcopy
import math
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import build_action_session
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRegistry, ActionRequest, parse_action_request, resolve_action
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.audit import explain_action
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry, basic_registry_document
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import instantiate_actor, instantiate_area, parse_actor_blueprint, parse_area_blueprint
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import clock_entity, discover_profiles
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import build_gameplay_world


def actor_raw():
    return {"protocol": "pmw-gameplay-v0.4", "kind": "actor_blueprint", "id": "test_actor",
            "hp": {"max": 100, "initial": 100}, "mana": {"max": 50, "initial": 20, "dynamics": None},
            "attributes": {"power": 8, "control": 7, "resilience": 6, "agility": 5}, "traits": []}


def area_raw():
    return {"protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint", "id": "test_area",
            "fields": [{"id": "mist", "domain": {"min": 0, "max": 1}, "initial": .2, "target": .2,
                        "rate": .1, "curve": "linear", "max_persistent_patches": 2, "max_temporary_modifiers": 2}]}


def make_session(registry=None, actors=2):
    ab, area = parse_actor_blueprint(actor_raw()), parse_area_blueprint(area_raw())
    units = [instantiate_actor(ab, f"actor_{i}", controller="human" if i == 0 else "ai") for i in range(actors)]
    zone = instantiate_area(area, "arena_area")
    world = build_gameplay_world("g2", areas=[zone], actors=units,
        placements=[(x.id, zone.id) for x in units])
    clock = clock_entity(); world.entities[clock.id] = clock
    registry = registry or basic_registry()
    return build_action_session(world, discover_profiles(world), registry), registry


class RequestAndBasicActionTests(unittest.TestCase):
    def test_controller_request_cannot_inject_cost_or_effects(self):
        with self.assertRaises(GameplayContractError):
            parse_action_request({"request_id": "request_1", "actor_id": "actor_0", "action_id": "basic_wait", "effects": []})

    def test_attack_explicit_power_scaling_and_shield_absorption(self):
        session, registry = make_session()
        target = session.state.entities["actor_1"].components["pmw_gameplay_actor"]
        target["shield"] = 10
        outcome = resolve_action(session, registry, ActionRequest("request_1", "actor_0", "basic_attack", "actor_1"))
        target = session.state.entities["actor_1"].components["pmw_gameplay_actor"]
        self.assertEqual(target["shield"], 0)
        self.assertEqual(target["hp"], 96)
        self.assertTrue(outcome.event_result.trace.events)

    def test_guard_is_bounded_refresh_not_additive(self):
        session, registry = make_session(actors=1)
        resolve_action(session, registry, ActionRequest("request_1", "actor_0", "basic_guard"))
        first = session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"]
        resolve_action(session, registry, ActionRequest("request_2", "actor_0", "basic_guard"))
        self.assertEqual(session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"], first)

    def test_wait_has_explicit_mana_value_and_does_not_use_agility(self):
        session, registry = make_session(actors=1)
        resolve_action(session, registry, ActionRequest("request_1", "actor_0", "basic_wait"))
        self.assertEqual(session.state.entities["actor_0"].components["pmw_gameplay_actor"]["mana"], 25)

    def test_mana_cost_is_reserved_before_self_mana_effect(self):
        doc = basic_registry_document(wait_mana=5)
        doc["actions"][2]["cost"]["mana"] = 7
        registry = ActionRegistry.parse(doc); session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest("request_1", "actor_0", "basic_wait"))
        self.assertEqual(session.state.entities["actor_0"].components["pmw_gameplay_actor"]["mana"], 18)

    def test_action_cost_modifiers_are_explicit_and_keep_positive_time(self):
        doc = basic_registry_document(); wait = doc["actions"][2]
        wait["cost_modifiers"] = [{"id": "resting_trait", "condition": {"attribute": {
            "subject": "self", "key": "control", "comparator": "gte", "value": 1}},
            "duration_add": -99, "mana_add": 2}]
        registry = ActionRegistry.parse(doc); session, _ = make_session(registry, actors=1)
        outcome = resolve_action(session, registry, ActionRequest("request_1", "actor_0", "basic_wait"))
        self.assertEqual(outcome.cost.duration, 1)
        self.assertEqual(outcome.cost.mana, 2)
        self.assertEqual(session.state.entities["actor_0"].components["pmw_gameplay_actor"]["mana"], 23)
        root_event = outcome.event_result.trace.events[0].event
        self.assertEqual(root_event.payload["writes"]["actor_0"]["mana"], 23)

    def test_mana_action_updates_dynamics_mirror(self):
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate1_blueprints import actor_raw as dynamic_actor_raw
        ab, area = parse_actor_blueprint(dynamic_actor_raw()), parse_area_blueprint(area_raw())
        unit, zone = instantiate_actor(ab, "actor_0", controller="human"), instantiate_area(area, "arena_area")
        world = build_gameplay_world("mirror", areas=[zone], actors=[unit], placements=[("actor_0", "arena_area")])
        clock = clock_entity(); world.entities[clock.id] = clock
        registry = basic_registry(); session = build_action_session(world, discover_profiles(world), registry)
        resolve_action(session, registry, ActionRequest("request_1", "actor_0", "basic_wait"))
        entity = session.state.entities["actor_0"]
        self.assertEqual(entity.components["pmw_gameplay_actor"]["mana"], 75)
        self.assertEqual(entity.components["pmw_gameplay_dynamics"]["fields"]["mana"]["value"], 75)

    def test_insufficient_mana_is_atomic(self):
        doc = basic_registry_document(); doc["actions"][0]["cost"]["mana"] = 30
        registry = ActionRegistry.parse(doc); session, _ = make_session(registry)
        before = deepcopy(session.state.to_dict())
        with self.assertRaises(GameplayContractError): resolve_action(session, registry, ActionRequest("request_1", "actor_0", "basic_attack", "actor_1"))
        self.assertEqual(session.state.to_dict(), before)

    def test_audit_is_backed_by_causal_trace(self):
        session, registry = make_session()
        report = explain_action(resolve_action(session, registry, ActionRequest("request_1", "actor_0", "basic_attack", "actor_1")))
        self.assertEqual(report["effects"][0]["kind"], "damage")
        self.assertTrue(report["causal_trace"]["events"])


class SchemaTests(unittest.TestCase):
    def test_positive_duration_and_finite_numbers(self):
        for value in (0, True):
            doc = basic_registry_document(); doc["actions"][0]["cost"]["duration"] = value
            with self.assertRaises(GameplayContractError): ActionRegistry.parse(doc)
        for value in (math.nan, math.inf, True):
            doc = basic_registry_document(); doc["actions"][0]["cost"]["mana"] = value
            with self.assertRaises(GameplayContractError): ActionRegistry.parse(doc)

    def test_duplicate_effect_id_and_write_conflict_rejected(self):
        doc = basic_registry_document(); duplicate = deepcopy(doc["actions"][0]["effects"][0]); doc["actions"][0]["effects"].append(duplicate)
        with self.assertRaises(GameplayContractError): ActionRegistry.parse(doc)

    def test_recursive_unknown_field_rejected(self):
        doc = basic_registry_document(); doc["actions"][0]["effects"][0]["target"]["path"] = "secret"
        with self.assertRaises(GameplayContractError): ActionRegistry.parse(doc)

    def test_targeting_and_evasion_are_opt_in(self):
        doc = basic_registry_document(); effect = doc["actions"][0]["effects"][0]
        registry = ActionRegistry.parse(doc)
        self.assertEqual(registry.actions["basic_attack"].effects[0].sensing, "none")
        effect["targeting"] = {"sensing": "visual", "evadable": True}
        with self.assertRaises(GameplayContractError): ActionRegistry.parse(doc)
        effect["attribute_terms"].append({"kind": "check", "attribute": "control", "comparator": "gte", "threshold": 1})
        parsed = ActionRegistry.parse(doc).actions["basic_attack"].effects[0]
        self.assertTrue(parsed.evadable); self.assertEqual(parsed.sensing, "visual")

    def test_periodic_status_rejects_nonfinite(self):
        doc = basic_registry_document(); doc["statuses"][0]["periodic_resource"] = {"resource": "mana", "delta": math.nan}
        with self.assertRaises(GameplayContractError): ActionRegistry.parse(doc)
