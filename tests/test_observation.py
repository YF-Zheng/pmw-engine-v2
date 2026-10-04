import json
import random
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from pmw import (Engine, Entity, Event, MissingObserverError, Observation,
                 ObserverView, Relation, WorldState, load_observation_rules,
                 parse_law, parse_observation_rule)
from pmw.matching.matcher import match_law_reference
from pmw.validation import ObservationValidationError, validate_observation_rules


def observation_rule(identifier, subject, reveal=None, bindings=None, when=None):
    return parse_observation_rule({
        "id": identifier,
        "bindings": bindings or {},
        "when": when or {"all": []},
        "subject": subject,
        "reveal": reveal or {},
    })


def visible_rules():
    return [
        observation_rule("self", "$observer", {"core": ["name"], "components": ["profile.public"]}),
        observation_rule(
            "visible-entity", "$subject",
            {"core": ["archetype", "name"], "tags": ["public", "wounded"],
             "components": ["appearance.color", "health.visible_state"]},
            {"subject": {"kind": "entity"},
             "visibility": {"kind": "relation", "type": "visible_to",
                            "source": "$observer", "target": "$subject"}},
        ),
    ]


class ObservationContractTest(unittest.TestCase):
    def test_default_deny_including_self(self):
        runtime = Engine([]).attach(WorldState("secret", tick=9, sim_time=3, rng_state={"seed": 7},
            entities={"alice": Entity("alice", "npc", "Alice", {"admin"}, {"hp": 5})},
            scheduled_events=[Event("hidden", "pulse", time=4)]))
        self.assertEqual(runtime.observe("alice").to_dict(), {"observer_id": "alice", "entities": [], "relations": []})
        self.assertEqual(runtime.stats.runtime_index_builds, 0)

    def test_self_grant_uses_seed_without_index(self):
        rule = observation_rule("self", "$observer", {"core": ["archetype", "name"], "tags": ["wounded"], "components": ["health.hp"]})
        runtime = Engine([], observation_rules=[rule]).attach(WorldState(entities={"a": Entity("a", "npc", "A", {"wounded", "secret"}, {"health": {"hp": 4, "max": 8}})}))
        self.assertEqual(runtime.observe("a").to_dict()["entities"], [{"id": "a", "archetype": "npc", "name": "A", "tags": ["wounded"], "components": {"health": {"hp": 4}}}])
        self.assertEqual((runtime.stats.observation_candidate_rows, runtime.stats.runtime_index_builds), (0, 0))

    def test_missing_observer_and_relation_observer_rejected(self):
        runtime = Engine([]).attach(WorldState(entities={"a": Entity("a")}, relations={"r": Relation("r", "x", "a", "a")}))
        for value in ("", "missing", "r", None):
            with self.assertRaises(MissingObserverError): runtime.observe(value)

    def test_observer_view_is_narrow_facade(self):
        view = Engine([]).attach(WorldState(entities={"a": Entity("a")})).observer("a")
        self.assertIsInstance(view, ObserverView); self.assertEqual(view.observer_id, "a")
        self.assertIsInstance(view.observe(), Observation)
        for name in ("state", "snapshot", "get_index", "run_event", "schedule", "trace"):
            self.assertFalse(hasattr(view, name))

    def test_core_tag_and_component_redaction(self):
        entity = Entity("a", "agent", "Alice", {"public", "secret_trait", "admin_only"}, {
            "appearance": {"color": "red", "biometric": "secret"},
            "health": {"visible_state": "injured", "hp": 2},
            "secret_ai_plan": {"target": "vault"}, "inventory": ["key"],
        })
        rule = observation_rule("self", "$observer", {"core": ["name"], "tags": ["public"], "components": ["appearance.color", "health.visible_state"]})
        raw = Engine([], observation_rules=[rule]).attach(WorldState(entities={"a": entity})).observe("a").to_dict()
        encoded = json.dumps(raw, sort_keys=True)
        self.assertEqual(raw["entities"][0], {"id": "a", "name": "Alice", "tags": ["public"], "components": {"appearance": {"color": "red"}, "health": {"visible_state": "injured"}}})
        for hidden in ("secret_trait", "admin_only", "biometric", "secret_ai_plan", "inventory", '"hp"'):
            self.assertNotIn(hidden, encoded)

    def test_whole_component_is_deep_copied(self):
        entity = Entity("a", components={"appearance": {"layers": [{"color": "red"}]}})
        rule = observation_rule("self", "$observer", {"components": ["appearance"]})
        observation = Engine([], observation_rules=[rule]).attach(WorldState(entities={"a": entity})).observe("a")
        entity.components["appearance"]["layers"][0]["color"] = "blue"
        self.assertEqual(observation.to_dict()["entities"][0]["components"]["appearance"]["layers"][0]["color"], "red")

    def test_whole_component_dict_is_canonicalized(self):
        entity = Entity("a", components={"data": {"z": 1, "a": {"y": 2, "b": 3}}})
        rule = observation_rule("self", "$observer", {"components": ["data"]})
        data = Engine([], observation_rules=[rule]).attach(WorldState(entities={"a": entity})).observe("a").to_dict()["entities"][0]["components"]["data"]
        self.assertEqual(list(data), ["a", "z"]); self.assertEqual(list(data["a"]), ["b", "y"])

    def test_missing_and_list_traversal_paths_are_omitted(self):
        rule = observation_rule("self", "$observer", {"components": ["missing.path", "items.0.name"]})
        raw = Engine([], observation_rules=[rule]).attach(WorldState(entities={"a": Entity("a", components={"items": [{"name": "hidden"}]})})).observe("a").to_dict()
        self.assertEqual(raw["entities"], [{"id": "a"}])

    def test_output_mutation_does_not_mutate_world_or_future_observation(self):
        rule = observation_rule("self", "$observer", {"components": ["health.hp"]})
        runtime = Engine([], observation_rules=[rule]).attach(WorldState(entities={"a": Entity("a", components={"health": {"hp": 5}})}))
        raw = runtime.observe("a").to_dict(); raw["entities"][0]["components"]["health"]["hp"] = 999
        self.assertEqual(runtime.state.entities["a"].components["health"]["hp"], 5)
        self.assertEqual(runtime.observe("a").to_dict()["entities"][0]["components"]["health"]["hp"], 5)

    def test_old_observation_stability(self):
        rule = observation_rule("self", "$observer", {"core": ["name"], "components": ["state.value"]})
        runtime = Engine([], observation_rules=[rule]).attach(WorldState(entities={"a": Entity("a", name="before", components={"state": {"value": [1]}})}))
        old = runtime.observe("a"); expected = old.to_dict()
        runtime.state.entities["a"].name = "after"; runtime.state.entities["a"].components["state"]["value"].append(2)
        self.assertEqual(old.to_dict(), expected)

    def test_relation_endpoint_identity_protection(self):
        world = WorldState(entities={"alice": Entity("alice"), "secret": Entity("secret"), "public": Entity("public")},
            relations={"noise": Relation("noise", "heard_noise", "secret", "public")})
        rules = [
            observation_rule("public", "$p", {}, {"p": {"kind": "entity"}}, {"ref": "$p.id", "eq": "public"}),
            observation_rule("noise", "$r", {"core": ["type", "source", "target"]}, {"r": {"kind": "relation", "type": "heard_noise"}}),
        ]
        raw = Engine([], observation_rules=rules).attach(world).observe("alice").to_dict()
        self.assertEqual(raw["relations"], [{"id": "noise", "target": "public", "type": "heard_noise"}])
        self.assertNotIn("secret", json.dumps(raw))

    def test_relation_core_and_components(self):
        world = WorldState(entities={"a": Entity("a"), "b": Entity("b")}, relations={"r": Relation("r", "knows", "a", "b", {"public", "secret"}, {"strength": {"shown": 2, "raw": 9}})})
        rules = [observation_rule("ids", "$x", {}, {"x": {"kind": "entity"}}), observation_rule("rel", "$r", {"core": ["type", "source", "target"], "tags": ["public"], "components": ["strength.shown"]}, {"r": {"kind": "relation"}})]
        relation = Engine([], observation_rules=rules).attach(world).observe("a").to_dict()["relations"][0]
        self.assertEqual(relation, {"id": "r", "source": "a", "target": "b", "type": "knows", "tags": ["public"], "components": {"strength": {"shown": 2}}})

    def test_multiple_grants_are_monotonic_union(self):
        world = WorldState(entities={"a": Entity("a", "npc", "Alice", components={"health": {"hp": 3}})})
        rules = [observation_rule("name", "$observer", {"core": ["name"]}), observation_rule("hp", "$observer", {"components": ["health.hp"]})]
        self.assertEqual(Engine([], observation_rules=rules).attach(world).observe("a").to_dict()["entities"], [{"id": "a", "name": "Alice", "components": {"health": {"hp": 3}}}])

    def test_duplicate_match_paths_are_deduplicated(self):
        world = WorldState(entities={"a": Entity("a"), "b": Entity("b")}, relations={"v1": Relation("v1", "visible_to", "a", "b"), "v2": Relation("v2", "visible_to", "a", "b")})
        rule = observation_rule("visible", "$subject", {}, {"subject": {"kind": "entity"}, "v": {"kind": "relation", "type": "visible_to", "source": "$observer", "target": "$subject"}})
        runtime = Engine([], observation_rules=[rule]).attach(world); raw = runtime.observe("a").to_dict()
        self.assertEqual(raw["entities"], [{"id": "b"}]); self.assertEqual(runtime.stats.observation_deduplicated_grants, 1)

    def test_rule_order_invariance_500_permutations(self):
        rng = random.Random(82801)
        world = WorldState(entities={"a": Entity("a", name="Alice", components={"x": {"a": 1, "b": 2}})})
        rules = [observation_rule("name", "$observer", {"core": ["name"]}), observation_rule("a", "$observer", {"components": ["x.a"]}), observation_rule("b", "$observer", {"components": ["x.b"]})]
        expected = Engine([], observation_rules=rules).attach(deepcopy(world)).observe("a").to_dict()
        for _ in range(500):
            shuffled = list(rules); rng.shuffle(shuffled)
            self.assertEqual(Engine([], observation_rules=shuffled).attach(deepcopy(world)).observe("a").to_dict(), expected)

    def test_observer_specific_isolation(self):
        world = WorldState(entities={name: Entity(name, name="Secret " + name) for name in ("alice", "bob", "x", "y")}, relations={"ax": Relation("ax", "visible_to", "alice", "x"), "by": Relation("by", "visible_to", "bob", "y")})
        runtime = Engine([], observation_rules=visible_rules()).attach(world)
        alice, bob = runtime.observe("alice").to_dict(), runtime.observe("bob").to_dict()
        self.assertNotEqual(alice, bob); self.assertIn("x", json.dumps(alice)); self.assertNotIn('"y"', json.dumps(alice)); self.assertIn("y", json.dumps(bob)); self.assertNotIn('"x"', json.dumps(bob))

    def test_observe_has_no_runtime_semantic_side_effect(self):
        runtime = Engine([], observation_rules=[observation_rule("self", "$observer")]).attach(WorldState(tick=4, sim_time=7, entities={"a": Entity("a")}, scheduled_events=[Event("s", "x", time=8)]))
        runtime.state_closure_known = True; before = (runtime.revision, runtime.object_revision, runtime.state.tick, runtime.state.sim_time, runtime.state_closure_known, [e.to_dict() for e in runtime.state.scheduled_events])
        runtime.observe("a")
        after = (runtime.revision, runtime.object_revision, runtime.state.tick, runtime.state.sim_time, runtime.state_closure_known, [e.to_dict() for e in runtime.state.scheduled_events])
        self.assertEqual(after, before)

    def test_no_runtime_metadata_in_output(self):
        runtime = Engine([], observation_rules=[observation_rule("self", "$observer")]).attach(WorldState("classified-world", tick=99, sim_time=12, rng_state={"secret": 1}, entities={"a": Entity("a")}, scheduled_events=[Event("secret-event", "x", time=13)]))
        raw = runtime.observe("a").to_dict(); encoded = json.dumps(raw)
        for hidden in ("classified-world", "tick", "sim_time", "revision", "rng", "scheduled", "secret-event", "stats", "trace"):
            self.assertNotIn(hidden, encoded)

    def test_hidden_temporal_changes_do_not_leak(self):
        runtime = Engine([], observation_rules=[observation_rule("self", "$observer", {"core": ["name"]})]).attach(WorldState(entities={"a": Entity("a", name="Alice")}))
        expected = runtime.observe("a").to_dict(); runtime.schedule(Event("hidden", "pulse", time=3)); runtime.reschedule_scheduled("hidden", 4); runtime.advance_to(4)
        self.assertEqual(runtime.observe("a").to_dict(), expected); self.assertGreater(runtime.revision, 0); self.assertGreater(runtime.state.tick, 0)

    def test_new_field_safety(self):
        rule = observation_rule("self", "$observer", {"components": ["health.visible_state"]})
        runtime = Engine([], observation_rules=[rule]).attach(WorldState(entities={"a": Entity("a", components={"health": {"visible_state": "well"}})}))
        before = runtime.observe("a").to_dict(); runtime.state.entities["a"].components["health"]["internal_bleeding"] = True
        self.assertEqual(runtime.observe("a").to_dict(), before)

    def test_stats_contract(self):
        runtime = Engine([], observation_rules=[observation_rule("self", "$observer", {"components": ["x.y"]})]).attach(WorldState(entities={"a": Entity("a", components={"x": {"y": 1}})}))
        runtime.observe("a"); stats = runtime.stats
        self.assertEqual((stats.observation_calls, stats.observation_rules_evaluated, stats.observation_matches, stats.observation_raw_grants, stats.observation_entities_returned, stats.observation_component_paths_copied), (1, 1, 1, 1, 1, 1))

    def test_lifecycle_visibility_create_and_delete(self):
        create_hidden = parse_law({"id": "create-hidden", "mode": "event", "when": {"event.type": {"eq": "hidden"}}, "effects": [{"op": "create_entity", "value": {"id": "hidden", "name": "Hidden"}}]})
        create_visible = parse_law({"id": "create-visible", "mode": "event", "when": {"event.type": {"eq": "visible"}}, "effects": [
            {"op": "create_entity", "value": {"id": "shown", "name": "Shown"}},
            {"op": "create_relation", "value": {"id": "visibility", "type": "visible_to", "source": "observer", "target": "shown"}},
        ]})
        delete = parse_law({"id": "delete", "mode": "event", "bindings": {"shown": {"kind": "entity"}, "v": {"kind": "relation", "type": "visible_to", "source": "$observer_entity", "target": "$shown"}, "observer_entity": {"kind": "entity"}}, "when": {"all": [{"ref": "$shown.id", "eq": "shown"}, {"ref": "$observer_entity.id", "eq": "observer"}, {"event.type": {"eq": "delete"}}]}, "effects": [{"op": "delete_relation", "target": "$v"}, {"op": "delete_entity", "target": "$shown"}]})
        runtime = Engine([create_hidden, create_visible, delete], observation_rules=visible_rules()).attach(WorldState(entities={"observer": Entity("observer", name="O", components={"profile": {"public": "O"}})}))
        initial = runtime.observe("observer").to_dict(); runtime.run_event(Event("h", "hidden"))
        self.assertEqual(runtime.observe("observer").to_dict(), initial)
        runtime.run_event(Event("v", "visible")); self.assertIn("shown", {item["id"] for item in runtime.observe("observer").to_dict()["entities"]})
        runtime.run_event(Event("d", "delete")); self.assertEqual(runtime.observe("observer").to_dict(), initial)

    def test_duration_relation_disappears_after_expiry(self):
        expire = parse_law({"id": "expire", "mode": "event", "bindings": {"status": {"kind": "relation", "type": "status"}}, "when": {"all": [{"event.type": {"eq": "expire"}}, {"ref": "$status.id", "eq": "$event.target"}]}, "effects": [{"op": "delete_relation", "target": "$status"}]})
        rule = observation_rule("status", "$status", {"core": ["type"]}, {"status": {"kind": "relation", "type": "status", "source": "$observer", "target": "$subject"}, "subject": {"kind": "entity"}})
        world = WorldState(entities={"a": Entity("a"), "b": Entity("b")}, relations={"burn": Relation("burn", "status", "a", "b")}, scheduled_events=[Event("expiry", "expire", time=5, target="burn")])
        runtime = Engine([expire], observation_rules=[rule]).attach(world)
        self.assertEqual(runtime.observe("a").to_dict()["relations"], [{"id": "burn", "type": "status"}])
        runtime.advance_to(5); self.assertEqual(runtime.observe("a").to_dict()["relations"], [])

    def test_loader_and_canonical_rule(self):
        raw = {"schema_version": "2.0", "observation_rules": [{"id": "self", "bindings": {}, "when": {"all": []}, "subject": "$observer", "reveal": {"core": ["name"]}}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observation.json"; path.write_text(json.dumps(raw), encoding="utf-8")
            rules = load_observation_rules(path)
        self.assertEqual(rules[0].to_dict(), raw["observation_rules"][0] | {"reveal": {"core": ["name"], "tags": [], "components": []}})


class ObservationValidationTest(unittest.TestCase):
    def assert_invalid(self, rule):
        with self.assertRaises(ObservationValidationError):
            validate_observation_rules({"schema_version": "2.0", "observation_rules": [rule]}, "test")

    def test_duplicate_ids(self):
        rule = {"id": "x", "bindings": {}, "when": {"all": []}, "subject": "$observer", "reveal": {}}
        with self.assertRaises(ObservationValidationError): validate_observation_rules({"schema_version": "2.0", "observation_rules": [rule, rule]}, "test")

    def test_reserved_observer_binding(self):
        self.assert_invalid({"id": "x", "bindings": {"observer": {"kind": "entity"}}, "subject": "$observer", "reveal": {}})

    def test_invalid_binding_kind_and_condition(self):
        for rule in (
            {"id": "x", "bindings": {"x": {"kind": "object"}}, "subject": "$x", "reveal": {}},
            {"id": "x", "bindings": {}, "when": {"mystery": []}, "subject": "$observer", "reveal": {}},
        ): self.assert_invalid(rule)

    def test_event_is_forbidden_everywhere(self):
        cases = [
            {"id": "x", "bindings": {}, "when": {"ref": "$event.type", "eq": "x"}, "subject": "$observer", "reveal": {}},
            {"id": "x", "bindings": {"r": {"kind": "relation", "source": "$event"}}, "subject": "$r", "reveal": {}},
            {"id": "x", "bindings": {}, "subject": "$event", "reveal": {}},
        ]
        for rule in cases: self.assert_invalid(rule)

    def test_invalid_subject_references(self):
        for subject in ("$missing", "$observer.name", "observer", "", 3):
            self.assert_invalid({"id": "x", "bindings": {}, "subject": subject, "reveal": {}})

    def test_invalid_core_by_subject_kind(self):
        self.assert_invalid({"id": "x", "bindings": {}, "subject": "$observer", "reveal": {"core": ["type"]}})
        self.assert_invalid({"id": "x", "bindings": {"r": {"kind": "relation"}}, "subject": "$r", "reveal": {"core": ["name"]}})

    def test_invalid_component_paths_and_duplicates(self):
        for paths in (["*"], ["x.*"], [".x"], ["x."], ["x", "x"]):
            self.assert_invalid({"id": "x", "bindings": {}, "subject": "$observer", "reveal": {"components": paths}})

    def test_duplicate_reveal_fields_and_unknown_schema_fields(self):
        self.assert_invalid({"id": "x", "bindings": {}, "subject": "$observer", "reveal": {"tags": ["a", "a"]}})
        self.assert_invalid({"id": "x", "bindings": {}, "subject": "$observer", "reveal": {}, "priority": 1})
        with self.assertRaises(ObservationValidationError): validate_observation_rules({"schema_version": "2.0", "observation_rules": [], "extra": True}, "test")


class ObservationPropertyTest(unittest.TestCase):
    def test_hidden_perturbation_noninterference_1000(self):
        rng = random.Random(82802)
        rule = observation_rule("self", "$observer", {"core": ["name"], "tags": ["public"], "components": ["profile.public"]})
        expected = None
        for case in range(1000):
            hidden_entities = {f"h{case}:{i}": Entity(f"h{case}:{i}", tags={f"secret-{rng.randrange(100)}"}, components={"secret": rng.randrange(100000)}) for i in range(rng.randrange(4))}
            entities = {"alice": Entity("alice", "npc", "Alice", {"public", f"hidden-{case}"}, {"profile": {"public": "hello", "private": rng.randrange(100000)}}), **hidden_entities}
            hidden_ids = list(hidden_entities)
            relations = {}
            if hidden_ids: relations["hidden-r"] = Relation("hidden-r", "secret", "alice", hidden_ids[0], components={"secret": case})
            world = WorldState(f"world-{case}", tick=rng.randrange(10000), sim_time=rng.random() * 100, rng_state={"hidden": rng.randrange(100000)}, entities=entities, relations=relations, scheduled_events=[Event(f"hidden-e-{case}", "secret", time=1000 + case)])
            actual = Engine([], observation_rules=[rule]).attach(world).observe("alice").to_dict()
            expected = expected or actual
            self.assertEqual(actual, expected)

    def test_indexed_reference_observation_differential_1000(self):
        rng = random.Random(82803)
        rules = [
            observation_rule("self", "$observer", {"core": ["name"], "components": ["profile.public"]}),
            observation_rule("visible", "$subject", {"core": ["name"], "tags": ["marked"], "components": ["health.hp"]},
                {"subject": {"kind": "entity", "requires": ["health"]}, "v": {"kind": "relation", "type": "visible_to", "source": "$observer", "target": "$subject", "requires": ["signal"]}},
                {"all": [{"has_component": ["$subject", "health"]}, {"any": [{"has_tag": ["$subject", "marked"]}, {"not": {"ref": "$subject.health.hp", "lt": 2}}]}]}),
            observation_rule("relations", "$v", {"core": ["type", "source", "target"], "components": ["signal.level"]},
                {"subject": {"kind": "entity"}, "v": {"kind": "relation", "type": "visible_to", "source": "$observer", "target": "$subject", "requires": ["signal"]}},
                {"ref": "$v.signal.level", "gte": 0}),
        ]
        for case in range(1000):
            count = 1 + rng.randrange(5)
            entities = {"o": Entity("o", name="Observer", components={"profile": {"public": case % 7}})}
            for i in range(count): entities[f"e{i}"] = Entity(f"e{i}", name=f"E{i}", tags={"marked"} if rng.randrange(2) else set(), components={"health": {"hp": rng.randrange(6)}} if rng.randrange(5) else {})
            relations = {}
            for i in range(count):
                if rng.randrange(2): relations[f"v{i}"] = Relation(f"v{i}", "visible_to", "o", f"e{i}", components={"signal": {"level": rng.randrange(3)}})
            world = WorldState(entities=entities, relations=relations)
            indexed = Engine([], observation_rules=rules).attach(deepcopy(world)).observe("o").to_dict()
            reference = Engine([], observation_rules=rules, _observation_matcher_backend=match_law_reference).attach(deepcopy(world)).observe("o").to_dict()
            self.assertEqual(indexed, reference, case)

    def test_persistent_rebuild_mutation_equivalence_1000(self):
        create = parse_law({"id": "create", "mode": "event", "when": {"event.type": {"eq": "create"}}, "effects": [
            {"op": "create_entity", "value": {"id": "$event.payload.entity", "name": "$event.payload.entity", "components": {"health": {"hp": 1}}}},
            {"op": "create_relation", "value": {"id": "$event.payload.relation", "type": "visible_to", "source": "observer", "target": "$event.payload.entity"}},
        ]})
        delete = parse_law({"id": "delete", "mode": "event", "bindings": {"subject": {"kind": "entity"}, "v": {"kind": "relation", "type": "visible_to", "source": "$observer_entity", "target": "$subject"}, "observer_entity": {"kind": "entity"}},
            "when": {"all": [{"ref": "$subject.id", "eq": "$event.payload.entity"}, {"ref": "$observer_entity.id", "eq": "observer"}]},
            "effects": [{"op": "delete_relation", "target": "$v"}, {"op": "delete_entity", "target": "$subject"}]})
        rules = visible_rules(); base = WorldState(entities={"observer": Entity("observer", name="O", components={"profile": {"public": "O"}})})
        persistent = Engine([create, delete], observation_rules=rules, _runtime_index_mode="persistent").attach(deepcopy(base))
        rebuild = Engine([create, delete], observation_rules=rules, _runtime_index_mode="rebuild_each_view").attach(deepcopy(base))
        for step in range(1000):
            cycle = step // 2; event_type = "create" if step % 2 == 0 else "delete"
            event = Event(f"{event_type}:{cycle}", event_type, payload={"entity": f"e{cycle}", "relation": f"v{cycle}"})
            persistent.run_event(deepcopy(event)); rebuild.run_event(deepcopy(event))
            self.assertEqual(persistent.observe("observer").to_dict(), rebuild.observe("observer").to_dict(), step)


if __name__ == "__main__":
    unittest.main()
