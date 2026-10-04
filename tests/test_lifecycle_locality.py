import unittest

from pmw import DanglingRelationError, EffectProposal, Engine, Entity, Event, Relation, WorldState, parse_law
from pmw.types import StateAddress


def delete_status_law():
    return parse_law({
        "id": "expire",
        "bindings": {"status": {"kind": "relation", "type": "status"}},
        "when": {"all": [
            {"event.type": {"eq": "expire"}},
            {"ref": "$status.id", "eq": "$event.target"},
        ]},
        "effects": [{"op": "delete_relation", "target": "$status"}],
    })


def unrelated_entities(count):
    return {f"e{i}": Entity(f"e{i}") for i in range(count)}


class LifecycleLocalityTest(unittest.TestCase):
    def test_single_relation_delete_is_world_size_local(self):
        entities = unrelated_entities(100_000)
        runtime = Engine([delete_status_law()]).attach(WorldState(
            entities=entities,
            relations={"status": Relation("status", "status", "e0", "e1")},
        ))
        before_builds = runtime.stats.runtime_index_builds
        runtime.run_event(Event("expire", "expire", target="status"))
        self.assertNotIn("status", runtime.state.relations)
        self.assertEqual(runtime.stats.runtime_index_builds - before_builds, 0)
        self.assertEqual((runtime.stats.lifecycle_id_membership_checks,
                          runtime.stats.lifecycle_endpoint_checks,
                          runtime.stats.lifecycle_incident_relation_checks,
                          runtime.stats.lifecycle_global_scans), (0, 0, 0, 0))

    def test_single_entity_create_work_is_constant_across_world_sizes(self):
        law = parse_law({"id": "create", "bindings": {}, "when": {"event.type": {"eq": "create"}}, "effects": [{"op": "create_entity", "value": {"id": "new"}}]})
        observed = []
        for size in (1_000, 100_000):
            runtime = Engine([law]).attach(WorldState(entities=unrelated_entities(size)))
            runtime.run_event(Event(f"create:{size}", "create"))
            observed.append((runtime.stats.lifecycle_id_membership_checks,
                             runtime.stats.lifecycle_endpoint_checks,
                             runtime.stats.lifecycle_global_scans))
        self.assertEqual(observed, [(2, 0, 0), (2, 0, 0)])

    def test_single_relation_create_work_is_constant_across_world_sizes(self):
        law = parse_law({"id": "create", "bindings": {}, "when": {"event.type": {"eq": "create"}}, "effects": [{"op": "create_relation", "value": {"id": "new-r", "type": "link", "source": "e0", "target": "e1"}}]})
        observed = []
        for size in (1_000, 100_000):
            runtime = Engine([law]).attach(WorldState(entities=unrelated_entities(size)))
            runtime.get_index(); before_builds = runtime.stats.runtime_index_builds
            runtime.run_event(Event(f"create:{size}", "create"))
            observed.append((runtime.stats.lifecycle_id_membership_checks,
                             runtime.stats.lifecycle_endpoint_checks,
                             runtime.stats.lifecycle_global_scans,
                             runtime.stats.runtime_index_builds - before_builds))
        self.assertEqual(observed, [(2, 2, 0, 0), (2, 2, 0, 0)])

    def test_entity_delete_work_is_incident_degree_local(self):
        entities = unrelated_entities(100_000)
        entities["x"] = Entity("x")
        relations = {f"u{i}": Relation(f"u{i}", "unrelated", "e0", "e1") for i in range(100_000)}
        relations.update({f"incident{i}": Relation(f"incident{i}", "link", "x", f"e{i}") for i in range(4)})
        runtime = Engine([]).attach(WorldState(entities=entities, relations=relations))
        runtime.get_index(); before_builds = runtime.stats.runtime_index_builds
        proposals = [EffectProposal(f"p{i}", "test", 0, "delete_relation", StateAddress("relation", f"incident{i}")) for i in range(4)]
        proposals.append(EffectProposal("px", "test", 0, "delete_entity", StateAddress("entity", "x")))
        runtime.engine._commit(runtime, runtime.engine._resolve(proposals).accepted)
        self.assertNotIn("x", runtime.state.entities)
        self.assertEqual(runtime.stats.lifecycle_incident_relation_checks, 4)
        self.assertEqual(runtime.stats.runtime_index_builds - before_builds, 0)
        self.assertEqual(runtime.stats.lifecycle_global_scans, 0)

    def test_many_small_relation_deletes_have_zero_global_work(self):
        count = 1000
        entities = unrelated_entities(100_000)
        relations = {f"status:{i}": Relation(f"status:{i}", "status", "e0", "e1") for i in range(count)}
        runtime = Engine([delete_status_law()]).attach(WorldState(entities=entities, relations=relations))
        for i in range(count):
            runtime.run_event(Event(f"expire:{i}", "expire", target=f"status:{i}"))
        self.assertEqual(len(runtime.state.relations), 0)
        self.assertEqual((runtime.stats.lifecycle_id_membership_checks,
                          runtime.stats.lifecycle_endpoint_checks,
                          runtime.stats.lifecycle_incident_relation_checks,
                          runtime.stats.lifecycle_global_scans,
                          runtime.stats.runtime_index_builds), (0, 0, 0, 0, 0))

    def test_one_batch_relation_deletes_have_zero_global_work(self):
        count = 1000
        runtime = Engine([]).attach(WorldState(
            entities=unrelated_entities(100_000),
            relations={f"status:{i}": Relation(f"status:{i}", "status", "e0", "e1") for i in range(count)},
        ))
        proposals = [EffectProposal(f"p{i}", "test", 0, "delete_relation", StateAddress("relation", f"status:{i}")) for i in range(count)]
        runtime.engine._commit(runtime, runtime.engine._resolve(proposals).accepted)
        self.assertEqual(len(runtime.state.relations), 0)
        self.assertEqual((runtime.stats.lifecycle_id_membership_checks,
                          runtime.stats.lifecycle_endpoint_checks,
                          runtime.stats.lifecycle_incident_relation_checks,
                          runtime.stats.lifecycle_global_scans,
                          runtime.stats.runtime_index_builds), (0, 0, 0, 0, 0))

    def test_duration_expiry_roots_do_not_scan_unrelated_entities(self):
        count = 100
        runtime = Engine([delete_status_law()]).attach(WorldState(
            entities=unrelated_entities(100_000),
            relations={f"status:{i}": Relation(f"status:{i}", "status", "e0", "e1") for i in range(count)},
            scheduled_events=[Event(f"expire:{i}", "expire", time=10, target=f"status:{i}") for i in range(count)],
        ))
        runtime.advance_to(10)
        self.assertEqual(len(runtime.state.relations), 0)
        self.assertEqual((runtime.stats.lifecycle_id_membership_checks,
                          runtime.stats.lifecycle_endpoint_checks,
                          runtime.stats.lifecycle_incident_relation_checks,
                          runtime.stats.lifecycle_global_scans,
                          runtime.stats.runtime_index_builds), (0, 0, 0, 0, 0))

    def test_created_relation_cannot_target_deleted_entity(self):
        law = parse_law({"id": "invalid", "bindings": {"x": {"kind": "entity"}}, "when": {"ref": "$x.id", "eq": "x"}, "effects": [
            {"op": "delete_entity", "target": "$x"},
            {"op": "create_relation", "value": {"id": "r", "type": "link", "source": "a", "target": "x"}},
        ]})
        runtime = Engine([law]).attach(WorldState(entities={"a": Entity("a"), "x": Entity("x")}))
        with self.assertRaises(DanglingRelationError): runtime.run_event(Event("root", "go"))
        self.assertIn("x", runtime.state.entities)
        self.assertEqual((runtime.stats.lifecycle_id_membership_checks,
                          runtime.stats.lifecycle_endpoint_checks,
                          runtime.stats.lifecycle_global_scans), (2, 2, 0))

    def test_created_entity_is_visible_to_created_relation_endpoint_check(self):
        law = parse_law({"id": "valid", "bindings": {}, "effects": [
            {"op": "create_entity", "value": {"id": "b"}},
            {"op": "create_relation", "value": {"id": "r", "type": "link", "source": "a", "target": "b"}},
        ]})
        runtime = Engine([law]).attach(WorldState(entities={"a": Entity("a")}))
        runtime.run_event(Event("root", "go"))
        self.assertIn("r", runtime.state.relations)
        self.assertEqual((runtime.stats.lifecycle_id_membership_checks,
                          runtime.stats.lifecycle_endpoint_checks,
                          runtime.stats.lifecycle_global_scans), (4, 2, 0))


if __name__ == "__main__":
    unittest.main()
