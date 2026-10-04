import random
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from pmw import (DuplicateScheduledEventError, Engine, Entity, Event,
                 MissingScheduledEventError, ProposalConflictError, Relation,
                 TemporalOrderError, WorldState, load_world, parse_law, save_world)
from pmw.validation import LawValidationError


def rule(identifier, event_type, effects, bindings=None):
    return parse_law({"id": identifier, "mode": "event", "bindings": bindings or {},
                      "when": {"event.type": {"eq": event_type}}, "effects": effects})


def pending(runtime):
    return [(event.id, event.type, event.time, event.source, event.target, event.payload,
             event.provenance) for event in sorted(runtime.state.scheduled_events,
                                                    key=lambda item: (item.time, item.id))]


class TemporalHandleTest(unittest.TestCase):
    def test_schedule_event_explicit_id_and_provenance(self):
        law = rule("schedule", "start", [{"op": "schedule_event", "event": {
            "id": "$event.payload.id", "type": "expire", "time": {"add": ["$event.time", 5]},
            "source": "$event.source", "payload": {"status": "s"}}}])
        runtime = Engine([law]).attach(WorldState(sim_time=2))
        result = runtime.run_event(Event("root", "start", time=2, source="hero", payload={"id": "expire:s"}))
        self.assertEqual(result.scheduled_event_ids, ["expire:s"])
        self.assertEqual(pending(runtime)[0][0:4], ("expire:s", "expire", 7, "hero"))
        self.assertEqual(runtime.state.scheduled_events[0].provenance, {"kind": "scheduled", "parent_event": "root"})

    def test_same_time_schedule_is_independent_root(self):
        schedule = rule("a", "start", [{"op": "schedule_event", "event": {"id": "later", "type": "hit", "time": "$event.time"}}])
        hit = rule("b", "hit", [{"op": "set", "target": "$x.state.hit", "value": True}], {"x": {"kind": "entity"}})
        runtime = Engine([schedule, hit]).attach(WorldState(sim_time=5, entities={"x": Entity("x", components={"state": {"hit": False}})}))
        result = runtime.run_event(Event("root", "start", time=5))
        self.assertEqual(result.processed_event_ids, ["root"]); self.assertFalse(runtime.state.entities["x"].components["state"]["hit"])
        runtime.advance_to(5); self.assertTrue(runtime.state.entities["x"].components["state"]["hit"])

    def test_cancel_direct_idempotence_and_revision(self):
        runtime = Engine([]).attach(WorldState(scheduled_events=[Event("a", "go", time=10)]))
        before_object = runtime.object_revision
        self.assertTrue(runtime.cancel_scheduled("a")); revision = runtime.revision
        self.assertFalse(runtime.cancel_scheduled("a")); self.assertEqual(runtime.revision, revision)
        self.assertEqual(runtime.object_revision, before_object)

    def test_reschedule_direct_contract_and_owned_event(self):
        runtime = Engine([]).attach(WorldState(scheduled_events=[Event("a", "go", time=10)]))
        old = runtime.state.scheduled_events[0]
        self.assertTrue(runtime.reschedule_scheduled("a", 20)); self.assertEqual((old.time, runtime.state.scheduled_events[0].time), (10, 20))
        revision = runtime.revision; self.assertFalse(runtime.reschedule_scheduled("a", 20)); self.assertEqual(runtime.revision, revision)
        with self.assertRaises(MissingScheduledEventError): runtime.reschedule_scheduled("missing", 30)

    def test_temporal_order_rejected(self):
        runtime = Engine([]).attach(WorldState(sim_time=5, scheduled_events=[Event("a", "go", time=10)]))
        with self.assertRaises(TemporalOrderError): runtime.reschedule_scheduled("a", 4)
        law = rule("past", "start", [{"op": "schedule_event", "event": {"id": "b", "type": "go", "time": 4}}])
        with self.assertRaises(TemporalOrderError): Engine([law]).attach(WorldState(sim_time=5)).run_event(Event("r", "start", time=5))

    def test_scheduler_effects_forbidden_in_state_laws(self):
        effects = [
            {"op": "schedule_event", "event": {"id": "a", "type": "x", "time": 1}},
            {"op": "cancel_scheduled", "value": "a"},
            {"op": "reschedule_scheduled", "value": {"id": "a", "time": 2}},
        ]
        for index, effect in enumerate(effects):
            with self.assertRaises(LawValidationError):
                parse_law({"id": f"bad{index}", "mode": "state", "effects": [effect]})

    def test_schedule_schema_rejections(self):
        invalid = [
            {"type": "x", "time": 1}, {"id": "", "type": "x", "time": 1},
            {"id": "x", "time": 1}, {"id": "x", "type": "x"},
            {"id": "x", "type": "x", "time": 1, "provenance": {}},
            {"id": "x", "type": "x", "time": 1, "extra": 1},
        ]
        for index, event in enumerate(invalid):
            with self.assertRaises(LawValidationError): rule(f"bad{index}", "go", [{"op": "schedule_event", "event": event}])

    def test_schedule_runtime_validation_rejections(self):
        cases = [
            {"id": "x", "type": "go", "time": float("nan")},
            {"id": "x", "type": "go", "time": 1, "payload": {"bad": float("nan")}},
            {"id": "x", "type": "go", "time": 1, "source": 9},
        ]
        for index, event in enumerate(cases):
            with self.assertRaises(Exception):
                law = rule(f"bad{index}", "root", [{"op": "schedule_event", "event": event}])
                Engine([law]).attach(WorldState()).run_event(Event("r", "root"))

    def test_schedule_rejects_non_json_static_values(self):
        for index, invalid in enumerate(({1}, (1,), b"bytes")):
            with self.assertRaises(LawValidationError):
                rule(f"non-json{index}", "root", [{"op": "schedule_event", "event": {"id": "x", "type": "go", "time": 1, "payload": {"bad": invalid}}}])

    def test_temporal_conflict_matrix(self):
        pairs = [
            ([{"op": "cancel_scheduled", "value": "a"}], [{"op": "reschedule_scheduled", "value": {"id": "a", "time": 3}}]),
            ([{"op": "schedule_event", "event": {"id": "a", "type": "x", "time": 3}}], [{"op": "cancel_scheduled", "value": "a"}]),
            ([{"op": "schedule_event", "event": {"id": "a", "type": "x", "time": 3}}], [{"op": "reschedule_scheduled", "value": {"id": "a", "time": 3}}]),
        ]
        for left, right in pairs:
            with self.assertRaises(ProposalConflictError):
                Engine([rule("a", "root", left), rule("b", "root", right)]).attach(WorldState(scheduled_events=[Event("a", "x", time=2)] if left[0]["op"] != "schedule_event" else [])).run_event(Event("r", "root"))

    def test_duplicate_cancel_and_same_reschedule_merge(self):
        cancel = Engine([rule("a", "root", [{"op": "cancel_scheduled", "value": "x"}]), rule("b", "root", [{"op": "cancel_scheduled", "value": "x"}])]).attach(WorldState(scheduled_events=[Event("x", "go", time=4)]))
        result = cancel.run_event(Event("r", "root")); self.assertEqual(result.cancelled_event_ids, ["x"])
        reschedule = Engine([rule("a", "root", [{"op": "reschedule_scheduled", "value": {"id": "x", "time": 8}}]), rule("b", "root", [{"op": "reschedule_scheduled", "value": {"id": "x", "time": 8}}])]).attach(WorldState(scheduled_events=[Event("x", "go", time=4)]))
        self.assertEqual(reschedule.run_event(Event("r", "root")).rescheduled_event_ids, ["x"])

    def test_different_reschedules_conflict(self):
        laws = [rule("a", "root", [{"op": "reschedule_scheduled", "value": {"id": "x", "time": 8}}]), rule("b", "root", [{"op": "reschedule_scheduled", "value": {"id": "x", "time": 9}}])]
        with self.assertRaises(ProposalConflictError): Engine(laws).attach(WorldState(scheduled_events=[Event("x", "go", time=4)])).run_event(Event("r", "root"))

    def test_duplicate_pending_schedule_is_atomic_with_cow(self):
        law = rule("both", "root", [{"op": "set", "target": "$x.state.v", "value": 1}, {"op": "schedule_event", "event": {"id": "taken", "type": "x", "time": 5}}], {"x": {"kind": "entity"}})
        state = WorldState(entities={"x": Entity("x", components={"state": {"v": 0}})}, scheduled_events=[Event("taken", "x", time=4)])
        runtime = Engine([law]).attach(state); old = state.entities["x"]
        with self.assertRaises(DuplicateScheduledEventError): runtime.run_event(Event("r", "root"))
        self.assertIs(state.entities["x"], old); self.assertEqual((state.entities["x"].components["state"]["v"], runtime.revision, runtime.object_revision), (0, 0, 0))

    def test_missing_reschedule_is_atomic_with_lifecycle(self):
        law = rule("both", "root", [{"op": "delete_relation", "target": "$r"}, {"op": "reschedule_scheduled", "value": {"id": "missing", "time": 5}}], {"r": {"kind": "relation", "type": "buff"}})
        state = WorldState(entities={"a": Entity("a"), "b": Entity("b")}, relations={"buff": Relation("buff", "buff", "a", "b")})
        runtime = Engine([law]).attach(state); runtime.get_index(); revision = runtime.revision
        with self.assertRaises(MissingScheduledEventError): runtime.run_event(Event("r", "root"))
        self.assertIn("buff", state.relations); self.assertEqual((runtime.revision, runtime.object_revision), (revision, 0)); self.assertIsNotNone(runtime._index)

    def test_snapshot_isolation_for_all_scheduler_mutations(self):
        runtime = Engine([]).attach(WorldState(scheduled_events=[Event("e", "x", time=10), Event("f", "x", time=11)])); snap = runtime.snapshot()
        runtime.reschedule_scheduled("e", 20); runtime.cancel_scheduled("f"); runtime.schedule(Event("g", "x", time=30))
        self.assertEqual([(e.id, e.time) for e in snap.scheduled_events], [("e", 10), ("f", 11)])
        self.assertEqual([(e.id, e.time) for e in sorted(runtime.state.scheduled_events, key=lambda e: e.id)], [("e", 20), ("g", 30)])

    def test_trace_and_semantic_projection_temporal_fields(self):
        law = rule("all", "root", [{"op": "cancel_scheduled", "value": "a"}, {"op": "reschedule_scheduled", "value": {"id": "b", "time": 9}}, {"op": "schedule_event", "event": {"id": "c", "type": "go", "time": 10}}])
        result = Engine([law]).attach(WorldState(scheduled_events=[Event("a", "go", time=5), Event("b", "go", time=6)])).run_event(Event("r", "root"))
        commit = result.trace.to_dict()["events"][0]["commits"][0]
        self.assertEqual((commit["scheduled_event_ids"], commit["cancelled_event_ids"], commit["rescheduled_events"]), (["c"], ["a"], [{"id": "b", "old_time": 6, "new_time": 9}]))
        self.assertEqual(result.trace.semantic_projection()["events"][0]["commits"][0]["cancelled_event_ids"], ["a"])

    def test_same_time_cancel_prevents_dispatch(self):
        cancel = rule("cancel", "a", [{"op": "cancel_scheduled", "value": "b"}])
        runtime = Engine([cancel]).attach(WorldState(scheduled_events=[Event("a", "a", time=5), Event("b", "b", time=5)]))
        self.assertEqual(runtime.advance_to(5).processed_event_ids, ["a"])

    def test_same_time_reschedule_later_and_earlier(self):
        later = rule("later", "a", [{"op": "reschedule_scheduled", "value": {"id": "b", "time": 10}}])
        runtime = Engine([later]).attach(WorldState(scheduled_events=[Event("a", "a", time=5), Event("b", "b", time=5)]))
        self.assertEqual(runtime.advance_to(5).processed_event_ids, ["a"]); self.assertEqual(runtime.peek_next_time(), 10)
        earlier = rule("earlier", "a", [{"op": "reschedule_scheduled", "value": {"id": "b", "time": 5}}])
        runtime = Engine([earlier]).attach(WorldState(scheduled_events=[Event("a", "a", time=4), Event("b", "b", time=10)]))
        self.assertEqual(runtime.advance_to(10).processed_event_ids, ["a", "b"])

    def test_current_root_cancel_is_noop(self):
        law = rule("self", "a", [{"op": "cancel_scheduled", "value": "$event.id"}])
        runtime = Engine([law]).attach(WorldState(scheduled_events=[Event("a", "a", time=1)]))
        dispatch = runtime.step(); self.assertEqual(dispatch.result.cancelled_event_ids, []); self.assertEqual(runtime.stats.scheduled_cancellations, 0)

    def test_event_id_reuse_ignores_stale_heap_entry(self):
        runtime = Engine([]).attach(WorldState()); runtime.schedule(Event("pulse", "old", time=1)); runtime.cancel_scheduled("pulse"); runtime.schedule(Event("pulse", "new", time=3))
        self.assertEqual(runtime.advance_to(2).dispatches, []); self.assertEqual(runtime.advance_to(3).processed_event_ids, ["pulse"])

    def test_heap_compaction_equivalence(self):
        base = [Event(f"e{i}", "go", time=i + 10) for i in range(20)]
        left = Engine([]).attach(WorldState(scheduled_events=deepcopy(base))); right = Engine([]).attach(WorldState(scheduled_events=deepcopy(base)))
        for i in range(1100): left.reschedule_scheduled("e0", 40 + (i % 2))
        self.assertGreater(left.stats.scheduler_heap_compactions, 0); right.reschedule_scheduled("e0", 40 + (1099 % 2)); right.get_scheduler().force_compact(right.state.scheduled_events, right.stats)
        self.assertEqual(pending(left), pending(right)); self.assertEqual(left.advance_to(100).processed_event_ids, right.advance_to(100).processed_event_ids)

    def test_structural_warm_queue_gate(self):
        runtime = Engine([]).attach(WorldState(scheduled_events=[Event(f"e{i}", "go", time=100 + i) for i in range(100000)])); queue = runtime.get_scheduler()
        builds = runtime.stats.scheduler_queue_builds; heap_size = len(queue.heap)
        runtime.cancel_scheduled("e50000"); self.assertEqual((runtime.stats.scheduler_queue_builds, len(queue.heap)), (builds, heap_size))
        runtime.reschedule_scheduled("e50001", 999999); self.assertEqual((runtime.stats.scheduler_queue_builds, len(queue.heap)), (builds, heap_size + 1))

    def test_save_reload_after_cancel_and_reschedule(self):
        runtime = Engine([]).attach(WorldState(scheduled_events=[Event("a", "go", time=10), Event("b", "go", time=20)])); runtime.reschedule_scheduled("a", 30); runtime.cancel_scheduled("b")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"; save_world(path, runtime.state); loaded = Engine([]).attach(load_world(path))
            self.assertEqual(pending(loaded), pending(runtime)); self.assertEqual(loaded.advance_to(30).processed_event_ids, ["a"])

    def test_insertion_history_independence(self):
        left = Engine([]).attach(WorldState()); right = Engine([]).attach(WorldState())
        left.schedule(Event("a", "go", time=9)); left.schedule(Event("b", "go", time=5)); left.reschedule_scheduled("a", 7)
        right.schedule(Event("z", "go", time=1)); right.cancel_scheduled("z"); right.schedule(Event("b", "go", time=5)); right.schedule(Event("a", "go", time=7))
        self.assertEqual(pending(left), pending(right)); self.assertEqual(left.advance_to(10).processed_event_ids, right.advance_to(10).processed_event_ids)

    def test_queue_differential_2000_operations(self):
        mutate = rule("count", "go", [{"op": "delta", "target": "$x.state.count", "value": 1}], {"x": {"kind": "entity"}})
        initial = WorldState(entities={"x": Entity("x", components={"state": {"count": 0}})})
        rng = random.Random(2700); fast = Engine([mutate], _scheduler_mode="versioned").attach(deepcopy(initial)); ref = Engine([mutate], _scheduler_mode="rebuild_each_operation").attach(deepcopy(initial))
        serial = 0
        for _ in range(2000):
            ids = [event.id for event in fast.state.scheduled_events]; op = rng.choice(["schedule", "cancel", "reschedule", "step", "advance"])
            if op == "schedule":
                serial += 1; event = Event(f"e{serial}", "go", time=fast.state.sim_time + rng.randint(0, 20), payload={"n": serial})
                fast.schedule(deepcopy(event)); ref.schedule(deepcopy(event))
            elif op == "cancel":
                event_id = rng.choice(ids) if ids and rng.random() < .8 else "missing"
                self.assertEqual(fast.cancel_scheduled(event_id), ref.cancel_scheduled(event_id))
            elif op == "reschedule" and ids:
                event_id = rng.choice(ids); time = fast.state.sim_time + rng.randint(0, 20)
                self.assertEqual(fast.reschedule_scheduled(event_id, time), ref.reschedule_scheduled(event_id, time))
            elif op == "step":
                a, b = fast.step(), ref.step(); self.assertEqual(None if a is None else (a.event_id, a.time), None if b is None else (b.event_id, b.time))
                if a is not None: self.assertEqual(a.result.trace.semantic_projection(), b.result.trace.semantic_projection())
            elif op == "advance":
                target = fast.state.sim_time + rng.randint(0, 10)
                a, b = fast.advance_to(target), ref.advance_to(target); self.assertEqual(a.processed_event_ids, b.processed_event_ids)
                self.assertEqual([item.result.trace.semantic_projection() for item in a.dispatches], [item.result.trace.semantic_projection() for item in b.dispatches])
            self.assertEqual((fast.state.sim_time, fast.state.tick, pending(fast)), (ref.state.sim_time, ref.state.tick, pending(ref)))
            self.assertEqual(fast.state.to_dict(), ref.state.to_dict())

    def test_duration_status_and_refresh(self):
        start = rule("start", "buff", [{"op": "create_relation", "value": {"id": "buff:1", "type": "buff", "source": "hero", "target": "hero", "components": {"duration": {"expiry_event_id": "expire:buff:1"}}}}, {"op": "schedule_event", "event": {"id": "expire:buff:1", "type": "expire", "time": 20, "payload": {"status_id": "buff:1"}}}])
        expire = parse_law({"id": "expire", "mode": "event", "bindings": {"status": {"kind": "relation", "type": "buff"}}, "when": {"all": [{"event.type": {"eq": "expire"}}, {"ref": "$status.id", "eq": "$event.payload.status_id"}]}, "effects": [{"op": "delete_relation", "target": "$status"}]})
        refresh = rule("refresh", "refresh", [{"op": "reschedule_scheduled", "value": {"id": "expire:buff:1", "time": 30}}])
        runtime = Engine([start, expire, refresh]).attach(WorldState(entities={"hero": Entity("hero")})); runtime.run_event(Event("s", "buff")); runtime.run_event(Event("r", "refresh"))
        runtime.advance_to(20); self.assertIn("buff:1", runtime.state.relations); runtime.advance_to(30); self.assertNotIn("buff:1", runtime.state.relations)

    def test_early_cancel_and_channel_pattern(self):
        stop = rule("stop", "interrupt", [{"op": "delete_relation", "target": "$channel"}, {"op": "cancel_scheduled", "value": "$channel.duration.completion_event_id"}], {"channel": {"kind": "relation", "type": "channel", "requires": ["duration"]}})
        complete = rule("complete", "complete", [{"op": "set", "target": "$hero.state.done", "value": True}], {"hero": {"kind": "entity"}})
        state = WorldState(entities={"hero": Entity("hero", components={"state": {"done": False}})}, relations={"channel": Relation("channel", "channel", "hero", "hero", components={"duration": {"completion_event_id": "complete:1"}})}, scheduled_events=[Event("complete:1", "complete", time=10)])
        runtime = Engine([stop, complete]).attach(state); result = runtime.run_event(Event("i", "interrupt")); self.assertEqual(result.cancelled_event_ids, ["complete:1"])
        runtime.advance_to(10); self.assertFalse(state.entities["hero"].components["state"]["done"]); self.assertNotIn("channel", state.relations)

    def test_early_cancel_status_pattern(self):
        dispel = rule("dispel", "dispel", [{"op": "delete_relation", "target": "$status"}, {"op": "cancel_scheduled", "value": "$status.duration.expiry_event_id"}], {"status": {"kind": "relation", "type": "buff", "requires": ["duration"]}})
        state = WorldState(entities={"hero": Entity("hero")}, relations={"buff:1": Relation("buff:1", "buff", "hero", "hero", components={"duration": {"expiry_event_id": "expire:buff:1"}})}, scheduled_events=[Event("expire:buff:1", "expire", time=20)])
        runtime = Engine([dispel]).attach(state)
        result = runtime.run_event(Event("root", "dispel"))
        self.assertNotIn("buff:1", state.relations)
        self.assertEqual(result.cancelled_event_ids, ["expire:buff:1"])
        self.assertEqual(runtime.advance_to(20).processed_event_ids, [])

    def test_temporal_only_transaction_is_not_counted_as_noop(self):
        runtime = Engine([rule("schedule", "root", [{"op": "schedule_event", "event": {"id": "future", "type": "go", "time": 1}}])]).attach(WorldState())
        runtime.run_event(Event("root", "root"))
        self.assertEqual((runtime.stats.transactions_committed, runtime.stats.noop_transactions), (1, 0))

    def test_recurring_handle_reuses_consumed_id(self):
        apply = rule("pulse.apply", "pulse", [{"op": "delta", "target": "$x.state.count", "value": 1}], {"x": {"kind": "entity"}})
        repeat = parse_law({"id": "pulse.repeat", "mode": "event", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"event.type": {"eq": "pulse"}}, {"ref": "$x.state.count", "lt": 9}]}, "effects": [{"op": "schedule_event", "event": {"id": "pulse", "type": "pulse", "time": {"add": ["$event.time", 1]}}}]})
        runtime = Engine([apply, repeat], max_scheduler_dispatches_per_advance=20).attach(WorldState(entities={"x": Entity("x", components={"state": {"count": 0}})}, scheduled_events=[Event("pulse", "pulse", time=1)]))
        result = runtime.advance_to(20); self.assertEqual(len(result.dispatches), 10); self.assertEqual(runtime.state.entities["x"].components["state"]["count"], 10); self.assertEqual(len(runtime.state.scheduled_events), 0)


if __name__ == "__main__":
    unittest.main()
