import random
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from pmw import (
    DanglingRelationError,
    EffectProposal,
    Engine,
    Entity,
    Event,
    ObjectInUseError,
    ProposalConflictError,
    Relation,
    WorldState,
    load_world,
    parse_law,
    save_world,
)
from pmw.runtime import DuplicateScheduledEventError
from pmw.types import StateAddress, StateDelta
from pmw.validation import LawValidationError, validate_runtime_world


LIFECYCLE_OPS = {"create_entity", "delete_entity", "create_relation", "delete_relation"}


def event_law(law_id, effects, *, bindings=None, event_type="go", where=()):
    conditions = [{"event.type": {"eq": event_type}}, *where]
    return parse_law({
        "id": law_id,
        "bindings": bindings or {},
        "when": {"all": conditions},
        "effects": effects,
    })


def semantic_result(result):
    return {
        "changed": result.changed,
        "triggered_law_ids": result.triggered_law_ids,
        "state_delta": [delta.to_dict() for delta in result.state_delta],
        "processed_event_ids": result.processed_event_ids,
        "scheduled_event_ids": result.scheduled_event_ids,
        "conflicts": result.conflicts,
        "trace": result.trace.semantic_projection(),
    }


def materialize_entity(raw):
    return Entity(
        raw["id"], raw.get("archetype", ""), raw.get("name"),
        set(raw.get("tags", [])), deepcopy(raw.get("components", {})),
    )


def materialize_relation(raw):
    return Relation(
        raw["id"], raw["type"], raw["source"], raw["target"],
        set(raw.get("tags", [])), deepcopy(raw.get("components", {})),
    )


def reference_full_copy_commit(runtime, proposals):
    """Test-only whole-world transaction oracle, independent of production prepare/publish."""
    original = runtime.state
    candidate = deepcopy(original)
    derived = [item.event for item in sorted(proposals, key=lambda item: item.proposal_id) if item.op == "emit_event"]
    deltas = []

    for proposal in sorted(
        (item for item in proposals if item.op not in LIFECYCLE_OPS | {"emit_event"}),
        key=lambda item: str(runtime.engine._conflict_address(item)),
    ):
        target = proposal.target
        obj = candidate.get_object(target.kind, target.object_id)
        if obj is None:
            raise ValueError(f"Unknown proposal target: {target}")
        if proposal.op in {"add_tag", "remove_tag"}:
            tag = str(proposal.value)
            old = tag in obj.tags
            new = proposal.op == "add_tag"
            if old != new:
                (obj.tags.add(tag) if new else obj.tags.remove(tag))
                deltas.append(StateDelta(runtime.engine._conflict_address(proposal), old, new, proposal.causes, proposal.source_laws))
            continue
        container = obj.components
        missing_parent = False
        for key in target.path[:-1]:
            if not isinstance(container, dict) or key not in container:
                missing_parent = True
                break
            container = container[key]
        key = target.path[-1]
        old = None if missing_parent else container.get(key)
        if proposal.op == "set":
            new = deepcopy(proposal.value)
        elif proposal.op == "delta":
            if old is None:
                raise ValueError(f"delta requires an existing numeric value: {target}")
            new = old + proposal.value
        else:
            raise ValueError(proposal.op)
        if old != new:
            container = obj.components
            for part in target.path[:-1]:
                container = container.setdefault(part, {})
            container[key] = new
            deltas.append(StateDelta(target, old, new, proposal.causes, proposal.source_laws))

    creates = [item for item in proposals if item.op.startswith("create_")]
    deletes = [item for item in proposals if item.op.startswith("delete_")]
    existing_ids = set(candidate.entities) | set(candidate.relations)
    create_ids = [item.target.object_id for item in creates]
    if len(create_ids) != len(set(create_ids)) or existing_ids & set(create_ids):
        raise ProposalConflictError("lifecycle object id collision")

    deleted_entity_ids = {item.target.object_id for item in deletes if item.target.kind == "entity"}
    for proposal in sorted(deletes, key=lambda item: (item.target.kind != "relation", item.target.object_id)):
        target = proposal.target
        mapping = candidate.entities if target.kind == "entity" else candidate.relations
        old = mapping.pop(target.object_id, None)
        if old is not None:
            deltas.append(StateDelta(target, deepcopy(old.to_dict()), None, proposal.causes, proposal.source_laws))
    for proposal in creates:
        target = proposal.target
        obj = materialize_entity(proposal.value) if target.kind == "entity" else materialize_relation(proposal.value)
        (candidate.entities if target.kind == "entity" else candidate.relations)[target.object_id] = obj
        deltas.append(StateDelta(target, None, deepcopy(obj.to_dict()), proposal.causes, proposal.source_laws))

    dangling = [relation for relation in candidate.relations.values() if relation.source not in candidate.entities or relation.target not in candidate.entities]
    if dangling:
        if any(relation.source in deleted_entity_ids or relation.target in deleted_entity_ids for relation in dangling):
            raise ObjectInUseError("entity remains referenced")
        raise DanglingRelationError("dangling created relation")
    validate_runtime_world(candidate)
    future = [item for item in derived if item.time > original.sim_time]
    immediate = [item for item in derived if item.time <= original.sim_time]
    prepared_schedule = runtime.prepare_schedule_batch(future)
    runtime.state = candidate
    if deltas:
        runtime.revision += 1
        runtime.object_revision += 1
        runtime.invalidate_index()
        runtime.stats.transactions_committed += 1
    else:
        runtime.stats.noop_transactions += 1
    runtime._last_commit_scheduled_ids = [item.id for item in future]
    runtime.commit_schedule_batch(prepared_schedule, future=True)
    return immediate, deltas


class LifecycleTest(unittest.TestCase):
    def test_creation_fields_resolve_through_existing_value_dsl(self):
        rule = event_law("dynamic", [
            {"op": "create_entity", "value": {"id": "$event.payload.id", "archetype": "projectile", "name": None, "tags": ["temporary"], "components": {"motion": {"vx": "$event.payload.vx"}}}},
            {"op": "create_relation", "value": {"id": "$event.payload.relation", "type": "attached_to", "source": "anchor", "target": "$event.payload.id"}},
        ])
        runtime = Engine([rule]).attach(WorldState(entities={"anchor": Entity("anchor")}))
        runtime.run_event(Event("root", "go", payload={"id": "shot:1", "relation": "attachment:1", "vx": 4}))
        self.assertEqual(runtime.state.entities["shot:1"].components, {"motion": {"vx": 4}})
        self.assertEqual(runtime.state.relations["attachment:1"].target, "shot:1")

    def test_creation_spec_contract_and_state_mode_restriction(self):
        invalid_values = [
            {}, {"id": ""}, {"id": "x", "archetype": None}, {"id": "x", "name": 1},
            {"id": "x", "tags": ["a", "a"]}, {"id": "x", "components": {"v": float("nan")}},
        ]
        for serial, value in enumerate(invalid_values):
            try:
                rule = event_law(f"bad{serial}", [{"op": "create_entity", "value": value}])
            except LawValidationError:
                continue
            runtime = Engine([rule]).attach(WorldState())
            with self.assertRaises(ValueError): runtime.run_event(Event(f"e{serial}", "go"))
            self.assertEqual(runtime.state.to_dict(), WorldState().to_dict())
        with self.assertRaises(LawValidationError):
            parse_law({"id": "bad", "mode": "state", "effects": [{"op": "create_relation", "value": {"id": "r"}}]})

    def test_duplicate_create_and_create_delete_are_hard_conflicts(self):
        engine = Engine([])
        create = lambda pid, kind="entity": EffectProposal(pid, pid, 0, f"create_{kind}", StateAddress(kind, "x"), {"id": "x"})
        delete = EffectProposal("d", "d", 0, "delete_entity", StateAddress("entity", "x"))
        for proposals in ([create("a"), create("b")], [create("a"), delete], [create("a"), create("r", "relation")]):
            with self.assertRaises(ProposalConflictError):
                engine._resolve(proposals)

    def test_duplicate_delete_merges_provenance(self):
        engine = Engine([])
        proposals = [
            EffectProposal("a", "law.a", 0, "delete_entity", StateAddress("entity", "x"), source_proposal_ids=("a",), source_law_ids=("law.a",)),
            EffectProposal("b", "law.b", 0, "delete_entity", StateAddress("entity", "x"), source_proposal_ids=("b",), source_law_ids=("law.b",)),
        ]
        resolved = engine._resolve(proposals)
        self.assertEqual(len(resolved.accepted), 1)
        self.assertEqual(resolved.accepted[0].causes, ("a", "b"))
        self.assertEqual(resolved.accepted[0].source_laws, ("law.a", "law.b"))

    def test_delete_and_value_mutations_are_hard_conflicts(self):
        engine = Engine([])
        delete = EffectProposal("d", "d", 0, "delete_entity", StateAddress("entity", "x"))
        for serial, op in enumerate(("set", "delta", "add_tag", "remove_tag")):
            path = () if "tag" in op else ("state", "v")
            mutation = EffectProposal(f"m{serial}", "m", 0, op, StateAddress("entity", "x", path), 1)
            with self.assertRaises(ProposalConflictError):
                engine._resolve([delete, mutation])

    def test_lifecycle_delta_trace_is_deepcopied_and_has_provenance(self):
        rule = event_law("create", [{"op": "create_entity", "value": {"id": "x", "components": {"state": {"v": 1}}}}])
        runtime = Engine([rule]).attach(WorldState())
        result = runtime.run_event(Event("root", "go"))
        delta = result.state_delta[0]
        runtime.state.entities["x"].components["state"]["v"] = 9
        self.assertEqual(delta.new_value["components"]["state"]["v"], 1)
        self.assertEqual(delta.law_ids, ("create",))
        self.assertEqual(delta.proposal_ids, ("proposal:root:000001",))

    def test_delete_incident_batch_emits_three_explicit_deltas(self):
        bindings = {"x": {"kind": "entity"}, "r1": {"kind": "relation"}, "r2": {"kind": "relation"}}
        effects = [{"op": "delete_relation", "target": "$r1"}, {"op": "delete_relation", "target": "$r2"}, {"op": "delete_entity", "target": "$x"}]
        rule = event_law("delete", effects, bindings=bindings, where=({"ref": "$x.id", "eq": "x"}, {"ref": "$r1.id", "eq": "r1"}, {"ref": "$r2.id", "eq": "r2"}))
        subject = WorldState(
            entities={key: Entity(key) for key in ("a", "x", "b")},
            relations={"r1": Relation("r1", "link", "a", "x"), "r2": Relation("r2", "link", "x", "b")},
        )
        result = Engine([rule]).run_event(subject, Event("root", "go"))
        self.assertEqual({str(delta.address) for delta in result.state_delta}, {"entity:x", "relation:r1", "relation:r2"})
        self.assertNotIn("x", subject.entities)

    def test_immediate_derived_event_cannot_observe_deleted_entity(self):
        delete = event_law("a.delete", [{"op": "delete_entity", "target": "$x"}, {"op": "emit_event", "event": {"type": "observe"}}], bindings={"x": {"kind": "entity"}}, event_type="delete")
        observe = event_law("b.observe", [{"op": "set", "target": "$x.state.seen", "value": True}], bindings={"x": {"kind": "entity"}}, event_type="observe")
        runtime = Engine([delete, observe]).attach(WorldState(entities={"x": Entity("x", components={"state": {"seen": False}})}))
        result = runtime.run_event(Event("root", "delete"))
        self.assertNotIn("x", runtime.state.entities)
        self.assertNotIn("b.observe", result.triggered_law_ids)

    def test_future_event_and_lifecycle_commit_or_fail_atomically(self):
        rule = event_law("create", [
            {"op": "create_entity", "value": {"id": "x"}},
            {"op": "emit_event", "event": {"type": "later", "time": 10, "target": "x"}},
        ])
        success = Engine([rule]).attach(WorldState())
        success.run_event(Event("A", "go"))
        self.assertIn("x", success.state.entities)
        self.assertEqual(success.state.scheduled_events[0].target, "x")

        failed = Engine([rule]).attach(WorldState(scheduled_events=[Event("derived:A:000001", "occupied", time=20)]))
        before = failed.state.to_dict()
        with self.assertRaises(DuplicateScheduledEventError):
            failed.run_event(Event("A", "go"))
        self.assertEqual(failed.state.to_dict(), before)
        self.assertEqual((failed.revision, failed.object_revision), (0, 0))

    def test_deletion_does_not_rewrite_stale_scheduled_references(self):
        rule = event_law("delete", [{"op": "delete_entity", "target": "$x"}], bindings={"x": {"kind": "entity"}})
        pending = Event("future", "later", time=10, source="x", target="x", payload={"object_id": "x"})
        runtime = Engine([rule]).attach(WorldState(entities={"x": Entity("x")}, scheduled_events=[pending]))
        runtime.run_event(Event("root", "go"))
        self.assertEqual(runtime.state.scheduled_events[0].to_dict(), pending.to_dict())

    def test_dynamic_lifecycle_save_reload_is_exact(self):
        rule = event_law("mutate", [
            {"op": "delete_relation", "target": "$r"}, {"op": "delete_entity", "target": "$old"},
            {"op": "create_entity", "value": {"id": "new", "tags": ["fresh"]}},
            {"op": "create_relation", "value": {"id": "new-r", "type": "link", "source": "anchor", "target": "new"}},
            {"op": "emit_event", "event": {"type": "later", "time": 7, "target": "new"}},
        ], bindings={"old": {"kind": "entity"}, "r": {"kind": "relation"}}, where=({"ref": "$old.id", "eq": "old"}, {"ref": "$r.id", "eq": "r"}))
        subject = WorldState(entities={"anchor": Entity("anchor"), "old": Entity("old")}, relations={"r": Relation("r", "link", "anchor", "old")}, sim_time=2, tick=3)
        runtime = Engine([rule]).attach(subject)
        runtime.run_event(Event("root", "go", time=2))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            save_world(path, runtime.state)
            restored = load_world(path)
        self.assertEqual(restored.to_dict(), runtime.state.to_dict())

    def test_lifecycle_closure_incremental_and_full_are_equivalent(self):
        cases = [
            (
                event_law("create", [{"op": "create_entity", "value": {"id": "new", "components": {"state": {"ready": True, "initialized": False}}}}]),
                parse_law({"id": "state", "mode": "state", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"ref": "$x.state.ready", "eq": True}, "effects": [{"op": "set", "target": "$x.state.initialized", "value": True}]}),
                WorldState(),
            ),
            (
                event_law("create", [{"op": "create_relation", "value": {"id": "r", "type": "contact", "source": "a", "target": "b"}}]),
                parse_law({"id": "state", "mode": "state", "bindings": {"a": {"kind": "entity"}, "b": {"kind": "entity"}, "r": {"kind": "relation", "type": "contact", "source": "$a", "target": "$b"}}, "effects": [{"op": "set", "target": "$b.state.hit", "value": True}]}),
                WorldState(entities={"a": Entity("a"), "b": Entity("b", components={"state": {"hit": False}})}),
            ),
            (
                event_law("mark", [{"op": "set", "target": "$x.state.dead", "value": True}], bindings={"x": {"kind": "entity"}}),
                parse_law({"id": "state", "mode": "state", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"ref": "$x.state.dead", "eq": True}, "effects": [{"op": "delete_entity", "target": "$x"}]}),
                WorldState(entities={"x": Entity("x", components={"state": {"dead": False}})}),
            ),
        ]
        for create, state, initial in cases:
            incremental = Engine([create, state]).attach(deepcopy(initial))
            full = Engine([create, state], _state_closure_backend="full").attach(deepcopy(initial))
            incremental.settle()
            full.settle()
            left = incremental.run_event(Event("root", "go"))
            right = full.run_event(Event("root", "go"))
            self.assertEqual(incremental.state.to_dict(), full.state.to_dict())
            self.assertEqual(left.trace.semantic_projection(), right.trace.semantic_projection())

    def test_exact_id_and_dynamic_topology_patch_without_rebuild(self):
        create = event_law("create", [
            {"op": "create_entity", "value": {"id": "new", "components": {"state": {"seen": False}}}},
            {"op": "create_relation", "value": {"id": "r", "type": "link", "source": "a", "target": "new", "components": {"meta": {}}}},
        ], event_type="create")
        observe = parse_law({"id": "observe", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"event.type": {"eq": "observe"}}, {"ref": "$x.id", "eq": "new"}]}, "effects": [{"op": "set", "target": "$x.state.seen", "value": True}]})
        runtime = Engine([create, observe]).attach(WorldState(entities={"a": Entity("a")}))
        index = runtime.get_index()
        builds = runtime.stats.runtime_index_builds
        runtime.run_event(Event("create", "create"))
        self.assertIn("r", index.relations_by_key[("link", "a", "new")])
        self.assertEqual(runtime.stats.runtime_index_builds, builds)
        self.assertEqual(runtime.stats.relation_topology_posting_adds, 7)
        runtime.run_event(Event("observe", "observe"))
        self.assertTrue(runtime.state.entities["new"].components["state"]["seen"])

    def test_deleted_exact_id_immediately_has_zero_candidates_without_index(self):
        delete = event_law("delete", [{"op": "delete_relation", "target": "$r"}, {"op": "emit_event", "event": {"type": "observe"}}], bindings={"r": {"kind": "relation"}}, event_type="delete", where=({"ref": "$r.id", "eq": "r"},))
        observe = parse_law({"id": "observe", "bindings": {"r": {"kind": "relation"}}, "when": {"all": [{"event.type": {"eq": "observe"}}, {"ref": "$r.id", "eq": "r"}]}, "effects": []})
        runtime = Engine([delete, observe]).attach(WorldState(entities={"a": Entity("a")}, relations={"r": Relation("r", "loop", "a", "a")}))
        runtime.run_event(Event("root", "delete"))
        self.assertEqual(runtime.stats.runtime_index_builds, 0)
        self.assertNotIn("r", runtime.state.relations)

    def test_relation_delete_updates_all_topology_postings(self):
        rule = event_law("delete", [{"op": "delete_relation", "target": "$r"}], bindings={"r": {"kind": "relation"}})
        runtime = Engine([rule]).attach(WorldState(entities={"a": Entity("a"), "b": Entity("b")}, relations={"r": Relation("r", "link", "a", "b", components={"meta": {}})}))
        index = runtime.get_index()
        builds = runtime.stats.runtime_index_builds
        runtime.run_event(Event("root", "go"))
        self.assertNotIn("r", index.relations_by_type["link"])
        self.assertNotIn("r", index.relations_by_source["a"])
        self.assertNotIn("r", index.relations_by_target["b"])
        self.assertEqual(runtime.stats.runtime_index_builds, builds)
        self.assertEqual((runtime.stats.relation_topology_posting_removes, runtime.stats.relation_component_posting_removes), (7, 1))

    def test_lifecycle_full_copy_differential_500_transactions(self):
        rng = random.Random(2600)
        for case in range(500):
            variant = case % 10
            entities = {"a": Entity("a", components={"state": {"v": rng.randrange(5)}}), "b": Entity("b"), "x": Entity("x", components={"state": {"v": 0}})}
            relations = {"r": Relation("r", "link", "a", "x")}
            effects = []
            if variant == 0: effects = [{"op": "create_entity", "value": {"id": f"n{case}", "components": {"state": {"v": rng.randrange(10)}}}}]
            elif variant == 1: effects = [{"op": "create_entity", "value": {"id": f"n{case}"}}, {"op": "create_relation", "value": {"id": f"nr{case}", "type": "link", "source": "a", "target": f"n{case}"}}]
            elif variant == 2: effects = [{"op": "delete_entity", "target": "$b"}]
            elif variant == 3: effects = [{"op": "delete_relation", "target": "$r"}]
            elif variant == 4: effects = [{"op": "delete_relation", "target": "$r"}, {"op": "delete_entity", "target": "$x"}]
            elif variant == 5: effects = [{"op": "set", "target": "$a.state.v", "value": rng.randrange(10)}, {"op": "create_entity", "value": {"id": f"n{case}"}}]
            elif variant == 6: effects = [{"op": "create_entity", "value": {"id": "a"}}]
            elif variant == 7: effects = [{"op": "create_relation", "value": {"id": f"nr{case}", "type": "link", "source": "a", "target": "missing"}}]
            elif variant == 8: effects = [{"op": "delete_entity", "target": "$x"}]
            else: effects = [{"op": "create_entity", "value": {"id": f"n{case}"}}, {"op": "emit_event", "event": {"type": "later", "time": 5, "target": f"n{case}"}}]
            bindings = {"a": {"kind": "entity"}, "b": {"kind": "entity"}, "x": {"kind": "entity"}, "r": {"kind": "relation"}}
            rule = event_law("transaction", effects, bindings=bindings, where=({"ref": "$a.id", "eq": "a"}, {"ref": "$b.id", "eq": "b"}, {"ref": "$x.id", "eq": "x"}, {"ref": "$r.id", "eq": "r"}))
            initial = WorldState(entities=entities, relations=relations)
            production = Engine([rule]).attach(deepcopy(initial))
            reference = Engine([rule]).attach(deepcopy(initial))
            reference.engine._commit = lambda active, proposals: reference_full_copy_commit(active, proposals)
            try:
                left = production.run_event(Event(f"case{case}", "go"))
            except Exception as left_error:
                with self.assertRaises(type(left_error)):
                    reference.run_event(Event(f"case{case}", "go"))
                self.assertEqual(production.state.to_dict(), initial.to_dict())
                self.assertEqual(reference.state.to_dict(), initial.to_dict())
            else:
                right = reference.run_event(Event(f"case{case}", "go"))
                self.assertEqual(production.state.to_dict(), reference.state.to_dict())
                self.assertEqual(semantic_result(left), semantic_result(right))

    def test_persistent_rebuild_topology_differential_1000_cases(self):
        rng = random.Random(2610)
        variants = [case % 6 for case in range(1000)]
        rng.shuffle(variants)
        for case, variant in enumerate(variants):
            initial = WorldState(
                entities={"a": Entity("a", components={"state": {"hit": False, "ready": False, "seen": False}}), "b": Entity("b", components={"state": {"hit": False, "ready": False, "seen": False}}), "x": Entity("x", components={"state": {"hit": False, "ready": False, "seen": False}})},
                relations={"old": Relation("old", "link", "a", "b")},
            )
            if variant == 0:
                action = event_law("action", [{"op": "create_relation", "value": {"id": f"r{case}", "type": "contact", "source": "a", "target": "b"}}])
                state = parse_law({"id": "state", "mode": "state", "bindings": {"a": {"kind": "entity"}, "b": {"kind": "entity"}, "r": {"kind": "relation", "type": "contact", "source": "$a", "target": "$b"}}, "effects": [{"op": "set", "target": "$b.state.hit", "value": True}]})
            elif variant == 1:
                action = event_law("action", [{"op": "delete_relation", "target": "$r"}, {"op": "emit_event", "event": {"type": "after"}}], bindings={"r": {"kind": "relation"}})
                state = event_law("state", [{"op": "set", "target": "$b.state.hit", "value": True}], bindings={"a": {"kind": "entity"}, "b": {"kind": "entity"}, "r": {"kind": "relation", "type": "link", "source": "$a", "target": "$b"}}, event_type="after")
            elif variant == 2:
                action = event_law("action", [{"op": "create_entity", "value": {"id": f"n{case}", "components": {"state": {"ready": True, "seen": False}}}}])
                state = parse_law({"id": "state", "mode": "state", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"ref": "$x.state.ready", "eq": True}, "effects": [{"op": "set", "target": "$x.state.seen", "value": True}]})
            elif variant == 3:
                action = event_law("action", [{"op": "delete_relation", "target": "$r"}, {"op": "delete_entity", "target": "$b"}], bindings={"r": {"kind": "relation"}, "b": {"kind": "entity"}}, where=({"ref": "$r.id", "eq": "old"}, {"ref": "$b.id", "eq": "b"}))
                state = parse_law({"id": "state", "mode": "state", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "effects": [{"op": "set", "target": "$x.state.seen", "value": "$x.state.seen"}]})
            elif variant == 4:
                action = event_law("action", [{"op": "create_entity", "value": {"id": f"n{case}", "components": {"extra": {"v": rng.randrange(5)}}}}])
                state = event_law("state", [], bindings={"x": {"kind": "entity", "requires": ["extra"]}}, event_type="none")
            else:
                action = event_law("action", [{"op": "delete_relation", "target": "$r"}], bindings={"r": {"kind": "relation", "requires": []}})
                state = event_law("state", [], bindings={"r": {"kind": "relation", "type": "link"}}, event_type="none")
            persistent = Engine([action, state]).attach(deepcopy(initial))
            rebuild = Engine([action, state], _runtime_index_mode="rebuild_each_view").attach(deepcopy(initial))
            persistent.get_index()
            left = persistent.run_event(Event(f"case{case}", "go"))
            right = rebuild.run_event(Event(f"case{case}", "go"))
            self.assertEqual(persistent.state.to_dict(), rebuild.state.to_dict())
            self.assertEqual(left.trace.to_dict(), right.trace.to_dict())
            self.assertEqual(left.trace.semantic_projection(), right.trace.semantic_projection())


if __name__ == "__main__":
    unittest.main()
