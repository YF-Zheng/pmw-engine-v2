import json
import tempfile
import unittest
import random
from copy import deepcopy
from pathlib import Path

from pmw import EffectProposal, Engine, Entity, Event, NonConvergentWorldError, ProposalConflictError, Relation, WorldState, load_laws, load_world, parse_law, save_world
from pmw.types import StateAddress
from pmw.dsl import DSLConditionTypeError, DSLResolutionError, evaluate
from pmw.validation import EventValidationError, LawValidationError, ReferenceValidationError, WorldValidationError
from pmw.matching import MatchStats, match_law as indexed_match, match_law_reference
from pmw.matching.matcher import MatchContext
from pmw.matching.plan import compile_match_plan, expression_dependencies
from pmw.matching.state_dependency import compile_state_dependency_plan


def law(law_id, *, mode="event", when=None, effects=None, priority=0, bindings=None):
    return parse_law({"id": law_id, "mode": mode, "priority": priority, "bindings": bindings or {"x": {"kind": "entity"}}, "when": when or {"event.type": {"eq": "root"}}, "effects": effects or []})


def world(**components):
    return WorldState(entities={"x": Entity("x", components=components)})


class EngineTest(unittest.TestCase):
    def test_state_laws_reach_fixed_point(self):
        event_law = law("event.make_a", effects=[{"op": "set", "target": "$x.state.a", "value": 1}])
        b_law = law("state.a_to_b", mode="state", when={"ref": "$x.state.a", "eq": 1}, effects=[{"op": "set", "target": "$x.state.b", "value": 1}])
        c_law = law("state.b_to_c", mode="state", when={"ref": "$x.state.b", "eq": 1}, effects=[{"op": "set", "target": "$x.state.c", "value": 1}])
        subject = world(state={"a": 0, "b": 0, "c": 0})
        Engine([event_law, b_law, c_law]).run_event(subject, Event("root", "root"))
        self.assertEqual(subject.entities["x"].components["state"], {"a": 1, "b": 1, "c": 1})

    def test_event_law_only_fires_once_while_state_settles(self):
        impact = law("event.impact", when={"event.type": {"eq": "impact"}}, effects=[{"op": "delta", "target": "$x.state.value", "value": 1}, {"op": "set", "target": "$x.state.a", "value": 1}])
        settle = law("state.settle", mode="state", when={"ref": "$x.state.a", "eq": 1}, effects=[{"op": "set", "target": "$x.state.b", "value": 1}])
        subject = world(state={"value": 0, "a": 0, "b": 0})
        Engine([impact, settle]).run_event(subject, Event("impact", "impact"))
        self.assertEqual(subject.entities["x"].components["state"]["value"], 1)

    def test_deltas_aggregate_independently_of_law_order(self):
        plus = law("delta.plus", effects=[{"op": "delta", "target": "$x.state.value", "value": 10}])
        minus = law("delta.minus", effects=[{"op": "delta", "target": "$x.state.value", "value": -3}])
        for laws in ([plus, minus], [minus, plus]):
            subject = world(state={"value": 0})
            Engine(laws).run_event(subject, Event("root", "root"))
            self.assertEqual(subject.entities["x"].components["state"]["value"], 7)

    def test_delta_trace_and_result_keep_all_source_laws(self):
        plus = law("a.plus", effects=[{"op": "delta", "target": "$x.state.value", "value": 10}])
        minus = law("b.minus", effects=[{"op": "delta", "target": "$x.state.value", "value": -3}])
        result = Engine([plus, minus]).run_event(world(state={"value": 0}), Event("root", "root"))
        self.assertEqual(result.state_delta[0].law_ids, ("a.plus", "b.minus"))
        self.assertEqual(result.triggered_law_ids, ["a.plus", "b.minus"])

    def test_set_conflict_is_deterministic(self):
        low = law("z.low", priority=1, effects=[{"op": "set", "target": "$x.state.value", "value": 1}])
        high = law("a.high", priority=1, effects=[{"op": "set", "target": "$x.state.value", "value": 2}])
        for laws in ([low, high], [high, low]):
            subject = world(state={"value": 0})
            result = Engine(laws).run_event(subject, Event("root", "root"))
            self.assertEqual(subject.entities["x"].components["state"]["value"], 2)
            self.assertEqual(len(result.conflicts), 1)

    def test_set_delta_is_a_hard_conflict(self):
        set_law = law("set", effects=[{"op": "set", "target": "$x.state.value", "value": 1}])
        delta_law = law("delta", effects=[{"op": "delta", "target": "$x.state.value", "value": 1}])
        with self.assertRaises(ProposalConflictError):
            Engine([set_law, delta_law]).run_event(world(state={"value": 0}), Event("root", "root"))

    def test_add_remove_tag_conflict_is_deterministic(self):
        add = law("z.add", priority=1, effects=[{"op": "add_tag", "target": "$x", "value": "marked"}])
        remove = law("a.remove", priority=1, effects=[{"op": "remove_tag", "target": "$x", "value": "marked"}])
        for laws in ([add, remove], [remove, add]):
            subject = world(state={})
            subject.entities["x"].tags.add("marked")
            result = Engine(laws).run_event(subject, Event("root", "root"))
            self.assertNotIn("marked", subject.entities["x"].tags)
            self.assertEqual(len(result.conflicts), 1)

    def test_higher_priority_set_wins(self):
        low = law("a.low", priority=1, effects=[{"op": "set", "target": "$x.state.value", "value": 1}])
        high = law("z.high", priority=2, effects=[{"op": "set", "target": "$x.state.value", "value": 2}])
        subject = world(state={"value": 0})
        Engine([high, low]).run_event(subject, Event("root", "root"))
        self.assertEqual(subject.entities["x"].components["state"]["value"], 2)

    def test_run_event_does_not_advance_simulation_time(self):
        subject = world(state={"value": 0})
        subject.tick, subject.sim_time = 7, 12.5
        Engine([law("change", effects=[{"op": "set", "target": "$x.state.value", "value": 1}])]).run_event(subject, Event("root", "root", time=99.0))
        self.assertEqual((subject.tick, subject.sim_time), (7, 12.5))

    def test_derived_events_and_proposal_ids_are_unique(self):
        emit = law("emit.each", when={"event.type": {"eq": "root"}}, effects=[{"op": "emit_event", "event": {"type": "leaf", "source": "$x.id"}}])
        subject = WorldState(entities={"a": Entity("a"), "b": Entity("b")})
        result = Engine([emit]).run_event(subject, Event("root", "root"))
        ids = [event["event"]["id"] for event in result.trace.to_dict()["events"]]
        proposal_ids = [proposal.proposal_id for proposal in result.trace.proposals]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(proposal_ids), len(set(proposal_ids)))
        self.assertEqual(ids[1:], ["derived:root:000001", "derived:root:000002"])

    def test_proposal_trace_links_derived_event(self):
        result = Engine([law("emit", effects=[{"op": "emit_event", "event": {"type": "leaf"}}])]).run_event(world(state={}), Event("root", "root"))
        proposal = result.trace.to_dict()["proposals"][0]
        self.assertEqual(proposal["emitted_event_id"], "derived:root:000001")
        self.assertEqual(proposal["cause_event_id"], "root")

    def test_multilevel_derived_events_keep_parent_causality(self):
        a = law("emit.a", when={"event.type": {"eq": "root"}}, effects=[{"op": "emit_event", "event": {"type": "a"}}])
        b = law("emit.b", when={"event.type": {"eq": "a"}}, effects=[{"op": "emit_event", "event": {"type": "b"}}])
        result = Engine([a, b]).run_event(world(state={}), Event("root", "root"))
        events = result.trace.to_dict()["events"]
        self.assertEqual([item["event"]["type"] for item in events], ["root", "a", "b"])
        self.assertEqual(events[1]["event"]["provenance"]["parent_event"], "root")
        self.assertEqual(events[2]["event"]["provenance"]["parent_event"], "derived:root:000001")

    def test_trace_records_real_state_delta(self):
        result = Engine([law("set", effects=[{"op": "set", "target": "$x.state.value", "value": 3}])]).run_event(world(state={"value": 1}), Event("root", "root"))
        delta = result.trace.to_dict()["events"][0]["commits"][0]["state_deltas"][0]
        self.assertEqual(delta["address"], "entity:x/state/value")
        self.assertEqual((delta["old"], delta["new"]), (1, 3))

    def test_noop_state_set_converges(self):
        noop = law("noop", mode="state", when={"ref": "$x.state.value", "eq": 1}, effects=[{"op": "set", "target": "$x.state.value", "value": 1}])
        Engine([noop], max_settle_iterations=2).run_event(world(state={"value": 1}), Event("root", "root"))

    def test_nonconvergent_state_rule_is_detected(self):
        up = law("up", mode="state", when={"ref": "$x.state.flag", "eq": 0}, effects=[{"op": "set", "target": "$x.state.flag", "value": 1}])
        down = law("down", mode="state", when={"ref": "$x.state.flag", "eq": 1}, effects=[{"op": "set", "target": "$x.state.flag", "value": 0}])
        with self.assertRaises(NonConvergentWorldError) as caught:
            Engine([up, down], max_settle_iterations=3).run_event(world(state={"flag": 0}), Event("root", "root"))
        self.assertEqual(caught.exception.law_ids, ["down", "up"])
        self.assertTrue(caught.exception.trace.events[0].commits)

    def test_same_law_conflicting_binding_sets_fail(self):
        conflict = law("bad", bindings={"a": {"kind": "entity"}, "b": {"kind": "entity"}}, effects=[{"op": "set", "target": "$a.state.value", "value": "$b.state.value"}])
        subject = WorldState(entities={"a": Entity("a", components={"state": {"value": 0}}), "b": Entity("b", components={"state": {"value": 1}})})
        with self.assertRaises(ProposalConflictError): Engine([conflict]).run_event(subject, Event("root", "root"))

    def test_same_law_add_remove_authoring_conflict_fails(self):
        conflict = law("bad", effects=[{"op": "add_tag", "target": "$x", "value": "x"}, {"op": "remove_tag", "target": "$x", "value": "x"}])
        subject = world(state={})
        with self.assertRaises(ProposalConflictError): Engine([conflict]).run_event(subject, Event("root", "root"))

    def test_load_validation_rejects_duplicate_and_dangling_world_ids(self):
        for relations, entities in (
            ([], [{"id": "x"}, {"id": "x"}]),
            ([{"id": "r", "type": "link", "source": "x", "target": "missing"}], [{"id": "x"}]),
            ([{"id": "x", "type": "link", "source": "x", "target": "b"}], [{"id": "x"}, {"id": "b"}]),
        ):
            with self.assertRaises(WorldValidationError): self._load_world({"schema_version": "2.0", "world_id": "w", "entities": entities, "relations": relations, "scheduled_events": []})

    def test_load_validation_rejects_duplicate_law_and_invalid_references(self):
        duplicate = {"schema_version": "2.0", "laws": [{"id": "x", "effects": []}, {"id": "x", "effects": []}]}
        unknown = {"schema_version": "2.0", "laws": [{"id": "x", "bindings": {"a": {"kind": "entity"}}, "when": {"ref": "$missing.value", "eq": 1}, "effects": []}]}
        with self.assertRaises(LawValidationError): self._load_laws(duplicate)
        with self.assertRaises(ReferenceValidationError): self._load_laws(unknown)

    def test_state_law_event_and_emit_are_rejected_at_load(self):
        event_ref = {"schema_version": "2.0", "laws": [{"id": "x", "mode": "state", "when": {"event.type": {"eq": "x"}}, "effects": []}]}
        emit = {"schema_version": "2.0", "laws": [{"id": "x", "mode": "state", "effects": [{"op": "emit_event", "event": {"type": "x"}}]}]}
        with self.assertRaises(ReferenceValidationError): self._load_laws(event_ref)
        with self.assertRaises(LawValidationError): self._load_laws(emit)

    def test_relation_binding_and_invalid_effect_target_are_rejected_at_load(self):
        relation = {"schema_version": "2.0", "laws": [{"id": "x", "bindings": {"r": {"kind": "relation", "source": "$missing"}}, "effects": []}]}
        target = {"schema_version": "2.0", "laws": [{"id": "x", "bindings": {"a": {"kind": "entity"}}, "effects": [{"op": "set", "target": "$a", "value": 1}]}]}
        with self.assertRaises(ReferenceValidationError): self._load_laws(relation)
        with self.assertRaises(LawValidationError): self._load_laws(target)

    def test_binding_key_order_has_identical_trace_semantics(self):
        common = {"id": "ordered", "when": {"event.type": {"eq": "root"}}, "effects": [{"op": "set", "target": "$a.state.value", "value": "$b.state.value"}]}
        first = parse_law({**common, "bindings": {"a": {"kind": "entity"}, "b": {"kind": "entity"}}})
        second = parse_law({**common, "bindings": {"b": {"kind": "entity"}, "a": {"kind": "entity"}}})
        subject = world(state={"value": 1})
        one = Engine([first]).run_event(subject, Event("root", "root")).trace.to_dict()
        two = Engine([second]).run_event(world(state={"value": 1}), Event("root", "root")).trace.to_dict()
        self.assertEqual(one, two)

    def test_world_roundtrip_preserves_semantics(self):
        subject = WorldState(world_id="roundtrip", tick=3, sim_time=1.5, entities={"x": Entity("x", tags={"tag"}, components={"state": {"value": 1}})}, scheduled_events=[Event("later", "future", time=2.0)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"; save_world(path, subject)
            self.assertEqual(load_world(path).to_dict(), subject.to_dict())

    def test_missing_when_is_canonical_true_and_executes(self):
        rule = parse_law({"id": "always", "bindings": {"x": {"kind": "entity"}}, "effects": [{"op": "set", "target": "$x.state.value", "value": 2}]})
        subject = world(state={"value": 0}); Engine([rule]).run_event(subject, Event("root", "root"))
        self.assertEqual(rule.when, {"all": []}); self.assertEqual(subject.entities["x"].components["state"]["value"], 2)

    def test_condition_ast_and_value_arity_fail_at_parse_boundary(self):
        for when in ({"foo": "bar"}, {"ref": "$x.state.value", "wat": 1}, {"ref": "$x.state.value", "gt": 1, "lt": 5}, {"all": "bad"}, {"has_tag": ["$x"]}):
            with self.assertRaises((LawValidationError, ReferenceValidationError)): parse_law({"id": "bad", "bindings": {"x": {"kind": "entity"}}, "when": when, "effects": []})
        with self.assertRaises(LawValidationError): parse_law({"id": "bad-value", "bindings": {"x": {"kind": "entity"}}, "effects": [{"op": "set", "target": "$x.state.value", "value": {"div": [1]}}]})

    def test_missing_runtime_path_is_explicit(self):
        rule = law("missing", when={"ref": "$x.state.missing", "eq": 1}, effects=[])
        with self.assertRaises(DSLResolutionError): Engine([rule]).run_event(world(state={}), Event("root", "root"))

    def test_event_validation_and_engine_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"; path.write_text('{"id":"x","type":"t","time":NaN}')
            from pmw import load_event
            with self.assertRaises(EventValidationError): load_event(path)
        with self.assertRaises(EventValidationError): Engine([]).run_event(world(state={}), Event("", "root"))

    def test_emit_event_unknown_field_and_invalid_dynamic_value_fail(self):
        with self.assertRaises(LawValidationError): parse_law({"id": "bad", "effects": [{"op": "emit_event", "event": {"type": "x", "extra": 1}}]})
        rule = law("dynamic", effects=[{"op": "emit_event", "event": {"type": "leaf", "source": "$x.state.number"}}])
        with self.assertRaises(EventValidationError): Engine([rule]).run_event(world(state={"number": 3}), Event("root", "root"))

    def test_canonical_serialization_ignores_insertion_order(self):
        first = WorldState(entities={"b": Entity("b"), "a": Entity("a")}, scheduled_events=[Event("z", "t", time=2), Event("a", "t", time=1)])
        second = WorldState(entities={"a": Entity("a"), "b": Entity("b")}, scheduled_events=[Event("a", "t", time=1), Event("z", "t", time=2)])
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_indexed_relation_join_matches_reference_and_is_linearish(self):
        count = 100
        subject = WorldState(entities={f"e{i}": Entity(f"e{i}") for i in range(count)}, relations={f"r{i}": __import__("pmw").Relation(f"r{i}", "link", f"e{i}", f"e{(i + 1) % count}") for i in range(count)})
        rule = parse_law({"id": "join", "bindings": {"a": {"kind": "entity"}, "b": {"kind": "entity"}, "r": {"kind": "relation", "type": "link", "source": "$a", "target": "$b"}}, "effects": []})
        event = Event("root", "root"); stats = MatchStats()
        fast = indexed_match(rule, subject, event, stats=stats); slow = match_law_reference(rule, subject, event)
        self.assertEqual([{key: item.id for key, item in row.items()} for row in fast], [{key: item.id for key, item in row.items()} for row in slow])
        self.assertEqual(len(fast), count); self.assertLess(stats.candidate_rows_examined, 20 * count)

    def test_early_pruning_avoids_independent_cartesian_product(self):
        count = 1000
        subject = WorldState(entities={f"e{i}": Entity(f"e{i}", components={"state": {"active": i == 0}}) for i in range(count)})
        rule = parse_law({"id": "prune", "bindings": {"a": {"kind": "entity"}, "b": {"kind": "entity"}}, "when": {"all": [{"ref": "$a.state.active", "eq": True}]}, "effects": []})
        stats = MatchStats(); matches = indexed_match(rule, subject, Event("root", "root"), stats=stats)
        self.assertEqual(len(matches), count); self.assertLessEqual(stats.complete_bindings, count); self.assertGreater(stats.early_predicate_prunes, count - 2)

    def test_match_plan_dependencies_do_not_parse_literal_references(self):
        bindings, event = expression_dependencies({"all": [{"ref": "$x.state.v", "eq": "hello $fake"}, {"event.type": {"eq": "go"}}]})
        self.assertEqual(bindings, {"x"}); self.assertTrue(event)

    def test_lazy_context_builds_one_index_or_zero_for_event_only_laws(self):
        subject = world(state={"value": 1}); event = Event("root", "root")
        context = MatchContext(subject, event); first = law("one", effects=[])
        indexed_match(first, subject, event, context=context, plan=compile_match_plan(first))
        indexed_match(law("two", effects=[]), subject, event, context=context, plan=compile_match_plan(law("two", effects=[])))
        self.assertEqual(context.index_builds, 1)
        event_law = parse_law({"id": "guard", "when": {"all": [{"event.type": {"eq": "other"}}]}, "bindings": {"x": {"kind": "entity"}}, "effects": []})
        context = MatchContext(subject, event); self.assertEqual(indexed_match(event_law, subject, event, context=context, plan=compile_match_plan(event_law)), [])
        self.assertEqual(context.index_builds, 0)

    def test_differential_property_suite_500_cases(self):
        rng = random.Random(20261001)
        for case in range(500):
            size = rng.randrange(1, 5)
            entities = {f"e{i}": Entity(f"e{i}", tags={"tag"} if i % 2 else set(), components={"state": {"n": i}}) for i in range(size)}
            relations = {f"r{i}": __import__("pmw").Relation(f"r{i}", "link", f"e{i}", f"e{(i + 1) % size}", components={"contact": {}} if i % 2 else {}) for i in range(size)}
            subject = WorldState(entities=entities, relations=relations)
            bindings = {"a": {"kind": "entity"}, "b": {"kind": "entity"}, "r": {"kind": "relation", "type": "link", "source": "$a", "target": "$b"}}
            when = {"all": [{"event.type": {"eq": "go"}}, {"any": [{"has_tag": ["$a", "tag"]}, {"not": {"has_component": ["$r", "missing"]}}]}]}
            rule = parse_law({"id": f"p{case}", "bindings": bindings, "when": when, "effects": []})
            fast = indexed_match(rule, subject, Event("go", "go")); slow = match_law_reference(rule, subject, Event("go", "go"))
            self.assertEqual([[row[key].id for key in sorted(row)] for row in fast], [[row[key].id for key in sorted(row)] for row in slow])

    def test_engine_trace_equivalence_with_reference_backend(self):
        rules = [law("event.delta", effects=[{"op": "delta", "target": "$x.state.v", "value": 1}, {"op": "emit_event", "event": {"type": "derived"}}]), law("state.tag", mode="state", when={"ref": "$x.state.v", "eq": 1}, effects=[{"op": "add_tag", "target": "$x", "value": "done"}])]
        left = world(state={"v": 0}); right = world(state={"v": 0})
        indexed = Engine(rules).run_event(left, Event("root", "root"))
        reference = Engine(rules, _matcher_backend=match_law_reference).run_event(right, Event("root", "root"))
        self.assertEqual(left.to_dict(), right.to_dict()); self.assertEqual(indexed.trace.to_dict(), reference.trace.to_dict())

    def test_scheduled_event_requires_full_contract(self):
        raw = {"schema_version": "2.0", "world_id": "w", "entities": [], "relations": [], "scheduled_events": [{"id": "s", "type": "", "payload": {}}]}
        with self.assertRaises(EventValidationError): self._load_world(raw)

    def test_relation_component_requires_is_indexed(self):
        count = 1000; subject = WorldState(entities={f"e{i}": Entity(f"e{i}") for i in range(count)}, relations={f"r{i}": __import__("pmw").Relation(f"r{i}", "link", f"e{i}", f"e{i}", components={"rare": {}} if i < 10 else {}) for i in range(count)})
        rule = parse_law({"id": "rare", "bindings": {"r": {"kind": "relation", "requires": ["rare"]}}, "effects": []}); stats = MatchStats()
        self.assertEqual(len(indexed_match(rule, subject, Event("x", "x"), stats=stats)), 10); self.assertLess(stats.candidate_rows_examined, 20)

    def test_zero_binding_event_law_needs_no_index(self):
        rule = parse_law({"id": "event", "when": {"all": [{"event.type": {"eq": "go"}}]}, "effects": []}); subject = world(state={}); context = MatchContext(subject, Event("go", "go"))
        self.assertEqual(indexed_match(rule, subject, Event("go", "go"), context=context, plan=compile_match_plan(rule)), [{}]); self.assertEqual(context.index_builds, 0)

    def test_exact_entity_id_literal_uses_snapshot_map_without_index(self):
        subject = WorldState(entities={f"e{i}": Entity(f"e{i}", components={"state": {}} if i == 77777 else {}) for i in range(100000)})
        rule = parse_law({"id": "exact", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"all": [{"ref": "$x.id", "eq": "e77777"}]}, "effects": []})
        stats = MatchStats(); matches = indexed_match(rule, subject, Event("go", "go"), stats=stats)
        self.assertEqual([row["x"].id for row in matches], ["e77777"])
        self.assertLessEqual(stats.candidate_rows_examined, 1); self.assertEqual(stats.exact_constraint_lookups, 1); self.assertEqual(stats.index_builds, 0)

    def test_exact_entity_event_target_and_invalid_rhs_prune_without_index(self):
        subject = WorldState(entities={"e0": Entity("e0"), "e1": Entity("e1")})
        target_rule = parse_law({"id": "target", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": []})
        stats = MatchStats(); matches = indexed_match(target_rule, subject, Event("go", "go", target="e1"), stats=stats)
        self.assertEqual([row["x"].id for row in matches], ["e1"]); self.assertEqual((stats.candidate_rows_examined, stats.index_builds, stats.exact_constraint_lookups), (1, 0, 1))
        for event in (Event("none", "go", target=None), Event("wrong", "go", payload={"target": 3})):
            rule = target_rule if event.target is None else parse_law({"id": "wrong", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.payload.target"}]}, "effects": []})
            stats = MatchStats(); self.assertEqual(indexed_match(rule, subject, event, stats=stats), []); self.assertEqual(stats.index_builds, 0); self.assertEqual(stats.exact_constraint_prunes, 1)

    def test_exact_entity_source_and_multiple_constraint_compatibility(self):
        subject = WorldState(entities={"e0": Entity("e0"), "e1": Entity("e1")})
        compatible = parse_law({"id": "compatible", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "e0"}, {"ref": "$x.id", "eq": "$event.source"}]}, "effects": []})
        stats = MatchStats(); self.assertEqual([row["x"].id for row in indexed_match(compatible, subject, Event("go", "go", source="e0"), stats=stats)], ["e0"]); self.assertEqual(stats.constraint_pushdowns, 2)
        stats = MatchStats(); self.assertEqual(indexed_match(compatible, subject, Event("go", "go", source="e1"), stats=stats), []); self.assertEqual(stats.exact_constraint_prunes, 1); self.assertEqual(stats.index_builds, 0)

    def test_exact_relation_id_uses_snapshot_map_without_index(self):
        subject = WorldState(entities={"a": Entity("a"), "b": Entity("b")}, relations={"r0": Relation("r0", "link", "a", "b", components={"needed": {}}), "r1": Relation("r1", "link", "b", "a")})
        rule = parse_law({"id": "relation", "bindings": {"r": {"kind": "relation", "requires": ["needed"]}}, "when": {"all": [{"ref": "$r.id", "eq": "r0"}]}, "effects": []})
        stats = MatchStats(); self.assertEqual([row["r"].id for row in indexed_match(rule, subject, Event("go", "go"), stats=stats)], ["r0"]); self.assertEqual((stats.candidate_rows_examined, stats.index_builds, stats.exact_constraint_lookups), (1, 0, 1))

    def test_relation_source_target_type_constraints_use_indexed_query(self):
        entities = {f"e{i}": Entity(f"e{i}") for i in range(50)}
        relations = {f"r{i}": Relation(f"r{i}", "contact" if i == 7 else "other", "e1" if i == 7 else "e2", "e3" if i == 7 else "e4") for i in range(50)}
        subject = WorldState(entities=entities, relations=relations)
        rule = parse_law({"id": "relation-key", "bindings": {"r": {"kind": "relation"}}, "when": {"all": [{"ref": "$r.source", "eq": "$event.source"}, {"ref": "$r.target", "eq": "$event.target"}, {"ref": "$r.type", "eq": "contact"}]}, "effects": []})
        stats = MatchStats(); self.assertEqual([row["r"].id for row in indexed_match(rule, subject, Event("go", "go", source="e1", target="e3"), stats=stats)], ["r7"]); self.assertEqual(stats.constraint_pushdowns, 3); self.assertEqual(stats.index_builds, 1); self.assertLessEqual(stats.candidate_rows_examined, 1)

    def test_exact_constraint_pushdown_differential_200_cases(self):
        rng = random.Random(241)
        for case in range(200):
            size = rng.randrange(1, 6); entities = {f"e{i}": Entity(f"e{i}", components={"needed": {}} if i % 2 else {}) for i in range(size)}
            relations = {f"r{i}": Relation(f"r{i}", "contact" if i % 2 else "other", f"e{i}", f"e{(i + 1) % size}") for i in range(size)}
            subject = WorldState(entities=entities, relations=relations); event = Event(f"event{case}", "go", source=f"e{rng.randrange(size)}", target=f"e{rng.randrange(size)}", payload={"id": f"e{rng.randrange(size)}"})
            variant = case % 6
            if variant == 0: bindings, clause = {"x": {"kind": "entity"}}, {"ref": "$x.id", "eq": f"e{rng.randrange(size)}"}
            elif variant == 1: bindings, clause = {"x": {"kind": "entity"}}, {"ref": "$x.id", "eq": "$event.source"}
            elif variant == 2: bindings, clause = {"x": {"kind": "entity", "requires": ["needed"]}}, {"ref": "$x.id", "eq": "$event.payload.id"}
            elif variant == 3: bindings, clause = {"r": {"kind": "relation"}}, {"ref": "$r.id", "eq": f"r{rng.randrange(size)}"}
            elif variant == 4: bindings, clause = {"r": {"kind": "relation"}}, {"ref": "$r.source", "eq": "$event.source"}
            else: bindings, clause = {"r": {"kind": "relation"}}, {"ref": "$r.type", "eq": "contact"}
            rule = parse_law({"id": f"exact{case}", "bindings": bindings, "when": {"all": [{"event.type": {"eq": "go"}}, clause]}, "effects": []})
            fast, slow = indexed_match(rule, subject, event), match_law_reference(rule, subject, event)
            self.assertEqual([[row[key].id for key in sorted(row)] for row in fast], [[row[key].id for key in sorted(row)] for row in slow])

    def test_targeted_event_trace_equivalence_with_exact_binding(self):
        rule = parse_law({"id": "targeted", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"all": [{"event.type": {"eq": "impact"}}, {"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "delta", "target": "$x.state.v", "value": 1}, {"op": "emit_event", "event": {"type": "after"}}]})
        left = WorldState(entities={"e0": Entity("e0", components={"state": {"v": 0}}), "e1": Entity("e1", components={"state": {"v": 0}})})
        right = deepcopy(left); event = Event("impact", "impact", target="e1")
        indexed = Engine([rule]).run_event(left, event); reference = Engine([rule], _matcher_backend=match_law_reference).run_event(right, event)
        self.assertEqual(left.to_dict(), right.to_dict()); self.assertEqual(indexed.trace.to_dict(), reference.trace.to_dict())

    def test_ten_exact_id_laws_examine_ten_candidates(self):
        subject = WorldState(entities={f"e{i}": Entity(f"e{i}") for i in range(1000)})
        totals = MatchStats()
        for i in range(10):
            rule = parse_law({"id": f"ten{i}", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": f"e{i}"}]}, "effects": []})
            stats = MatchStats(); indexed_match(rule, subject, Event("go", "go"), stats=stats)
            totals.candidate_rows_examined += stats.candidate_rows_examined; totals.exact_constraint_lookups += stats.exact_constraint_lookups; totals.index_builds += stats.index_builds
        self.assertEqual((totals.candidate_rows_examined, totals.exact_constraint_lookups, totals.index_builds), (10, 10, 0))

    def test_state_dependency_plan_extracts_paths_tags_and_requires(self):
        rule = parse_law({"id": "dependencies", "mode": "state", "bindings": {"x": {"kind": "entity", "requires": ["thermal"]}, "y": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.thermal.temperature", "gt": "$y.state.value"}, {"has_tag": ["$x", "burning"]}, {"has_component": ["$y", "state"]}]}, "effects": []})
        reads = {(item.binding, item.path) for item in compile_state_dependency_plan(rule).reads}
        self.assertTrue({("x", ("thermal",)), ("x", ("thermal", "temperature")), ("y", ("state", "value")), ("x", ("tags", "burning")), ("y", ("state",))} <= reads)

    def test_runtime_settle_and_revalidate_track_closure_knowledge(self):
        settle = law("state.set", mode="state", when={"ref": "$x.state.a", "eq": 1}, effects=[{"op": "set", "target": "$x.state.b", "value": 1}])
        runtime = Engine([settle]).attach(world(state={"a": 1, "b": 0}))
        self.assertFalse(runtime.state_closure_known); runtime.settle(); self.assertTrue(runtime.state_closure_known); self.assertEqual(runtime.state.entities["x"].components["state"]["b"], 1)
        runtime.revalidate(); self.assertFalse(runtime.state_closure_known)

    def test_incremental_local_chain_uses_constant_seeded_candidates(self):
        entities = {"e0": Entity("e0", components={"state": {"a": 0, "b": 0, "c": 0}})}
        entities.update({f"e{i}": Entity(f"e{i}") for i in range(1, 100000)})
        event = parse_law({"id": "event.start", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.a", "value": 1}]})
        first = law("state.first", mode="state", bindings={"x": {"kind": "entity", "requires": ["state"]}}, when={"ref": "$x.state.a", "eq": 1}, effects=[{"op": "set", "target": "$x.state.b", "value": 1}])
        second = law("state.second", mode="state", bindings={"x": {"kind": "entity", "requires": ["state"]}}, when={"ref": "$x.state.b", "eq": 1}, effects=[{"op": "set", "target": "$x.state.c", "value": 1}])
        runtime = Engine([event, first, second]).attach(WorldState(entities=entities)); runtime.settle()
        before_full, before_rows = runtime.stats.state_full_scans, runtime.stats.seeded_candidate_rows
        runtime.run_event(Event("impact", "impact", target="e0"))
        self.assertEqual(runtime.state.entities["e0"].components["state"], {"a": 1, "b": 1, "c": 1})
        self.assertEqual(runtime.stats.state_full_scans, before_full); self.assertLessEqual(runtime.stats.seeded_candidate_rows - before_rows, 3); self.assertGreaterEqual(runtime.stats.state_incremental_rounds, 2)

    def test_incremental_relation_neighborhood_reuses_seeded_matcher(self):
        subject = WorldState(entities={"x": Entity("x", components={"thermal": {"t": 0}}), "y": Entity("y", components={"state": {"hit": 0}}), "other": Entity("other", components={"state": {"hit": 0}})}, relations={"r": Relation("r", "contact", "x", "y")})
        event = parse_law({"id": "event.heat", "bindings": {"x": {"kind": "entity", "requires": ["thermal"]}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.thermal.t", "value": 1}]})
        contact = parse_law({"id": "state.contact", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}, "r": {"kind": "relation", "type": "contact", "source": "$x", "target": "$y"}}, "when": {"ref": "$x.thermal.t", "eq": 1}, "effects": [{"op": "set", "target": "$y.state.hit", "value": 1}]})
        runtime = Engine([event, contact]).attach(subject); runtime.settle(); runtime.run_event(Event("heat", "heat", target="x"))
        self.assertEqual(subject.entities["y"].components["state"]["hit"], 1); self.assertEqual(subject.entities["other"].components["state"]["hit"], 0); self.assertGreater(runtime.stats.seeded_match_calls, 0)

    def test_incremental_multi_binding_seeds_both_roles(self):
        subject = WorldState(entities={"e0": Entity("e0", components={"state": {"v": 1, "hit": 0}}), "e1": Entity("e1", components={"state": {"v": 2, "hit": 0}})})
        event = parse_law({"id": "event.bump", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "delta", "target": "$x.state.v", "value": 1}]})
        pair = parse_law({"id": "state.pair", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.state.v", "eq": "$y.state.v"}, {"ref": "$x.id", "neq": "$y.id"}]}, "effects": [{"op": "set", "target": "$x.state.hit", "value": 1}]})
        runtime = Engine([event, pair]).attach(subject); runtime.settle(); runtime.run_event(Event("bump", "bump", target="e0"))
        self.assertEqual([subject.entities[key].components["state"]["hit"] for key in ("e0", "e1")], [1, 1]); self.assertGreaterEqual(runtime.stats.seeded_match_calls, 2)

    def test_global_state_law_falls_back_to_full_match(self):
        subject = world(state={"flag": 1, "trigger": 0, "mark": 1})
        event = parse_law({"id": "event.reset", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.trigger", "value": 1}]})
        global_rule = law("state.global", mode="state", when={"all": []}, effects=[])
        runtime = Engine([event, global_rule]).attach(subject); runtime.settle(); before = runtime.stats.global_fallback_matches
        runtime.run_event(Event("root", "root", target="x"))
        self.assertEqual(subject.entities["x"].components["state"]["mark"], 1); self.assertGreater(runtime.stats.global_fallback_matches, before)

    def test_incremental_closure_differential_1000_cases(self):
        rng = random.Random(242)
        for case in range(1000):
            size = rng.randrange(1, 5); target = f"e{rng.randrange(size)}"
            entities = {f"e{i}": Entity(f"e{i}", components={"state": {"a": 0, "b": 0, "c": 0}}) for i in range(size)}
            event = parse_law({"id": "event", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.a", "value": 1}]})
            first = law("state.a", mode="state", bindings={"x": {"kind": "entity", "requires": ["state"]}}, when={"ref": "$x.state.a", "eq": 1}, effects=[{"op": "set", "target": "$x.state.b", "value": 1}])
            second = law("state.b", mode="state", bindings={"x": {"kind": "entity", "requires": ["state"]}}, when={"ref": "$x.state.b", "eq": 1}, effects=[{"op": "set", "target": "$x.state.c", "value": 1}])
            fast = Engine([event, first, second]).attach(WorldState(entities=deepcopy(entities))); slow = Engine([event, first, second], _state_closure_backend="full").attach(WorldState(entities=deepcopy(entities)))
            fast.settle(); slow.settle(); fast_result = fast.run_event(Event(f"e{case}", "go", target=target)); slow_result = slow.run_event(Event(f"e{case}", "go", target=target))
            self.assertEqual(fast.state.to_dict(), slow.state.to_dict()); self.assertEqual(fast_result.trace.to_dict(), slow_result.trace.to_dict())

    def test_tag_delta_activates_matching_state_law(self):
        event = parse_law({"id": "event.tag", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "add_tag", "target": "$x", "value": "burning"}]})
        state = law("state.tag", mode="state", when={"has_tag": ["$x", "burning"]}, effects=[{"op": "set", "target": "$x.state.hit", "value": 1}])
        subject = world(state={"hit": 0}); runtime = Engine([event, state]).attach(subject); runtime.settle(); runtime.run_event(Event("tag", "go", target="x"))
        self.assertEqual(subject.entities["x"].components["state"]["hit"], 1); self.assertGreater(runtime.stats.seeded_match_calls, 0)

    def test_relation_delta_seeds_relation_binding(self):
        subject = WorldState(entities={"a": Entity("a"), "b": Entity("b")}, relations={"r": Relation("r", "contact", "a", "b", components={"state": {"strength": 0, "active": 0}})})
        event = parse_law({"id": "event.relation", "bindings": {"r": {"kind": "relation"}}, "when": {"all": [{"ref": "$r.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$r.state.strength", "value": 1}]})
        state = parse_law({"id": "state.relation", "mode": "state", "bindings": {"r": {"kind": "relation"}}, "when": {"ref": "$r.state.strength", "eq": 1}, "effects": [{"op": "set", "target": "$r.state.active", "value": 1}]})
        runtime = Engine([event, state]).attach(subject); runtime.settle(); runtime.run_event(Event("relation", "go", target="r"))
        self.assertEqual(subject.relations["r"].components["state"]["active"], 1); self.assertGreater(runtime.stats.seeded_match_calls, 0)

    def test_parent_path_delta_overlaps_child_read_dependency(self):
        event = parse_law({"id": "event.parent", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state", "value": {"a": 1, "b": 0}}]})
        state = law("state.child", mode="state", when={"ref": "$x.state.a", "eq": 1}, effects=[{"op": "set", "target": "$x.state.b", "value": 1}])
        subject = world(state={"a": 0, "b": 0}); runtime = Engine([event, state]).attach(subject); runtime.settle(); runtime.run_event(Event("parent", "go", target="x"))
        self.assertEqual(subject.entities["x"].components["state"]["b"], 1)

    def test_incremental_relation_trace_matches_full_backend(self):
        event = parse_law({"id": "event.heat", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.thermal.t", "value": 1}]})
        state = parse_law({"id": "state.contact", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}, "r": {"kind": "relation", "type": "contact", "source": "$x", "target": "$y"}}, "when": {"ref": "$x.thermal.t", "eq": 1}, "effects": [{"op": "set", "target": "$y.state.hit", "value": 1}]})
        base = WorldState(entities={"x": Entity("x", components={"thermal": {"t": 0}}), "y": Entity("y", components={"state": {"hit": 0}})}, relations={"r": Relation("r", "contact", "x", "y")})
        fast = Engine([event, state]).attach(deepcopy(base)); slow = Engine([event, state], _state_closure_backend="full").attach(deepcopy(base)); fast.settle(); slow.settle()
        fast_result = fast.run_event(Event("heat", "go", target="x")); slow_result = slow.run_event(Event("heat", "go", target="x"))
        self.assertEqual(fast.state.to_dict(), slow.state.to_dict()); self.assertEqual(fast_result.trace.to_dict(), slow_result.trace.to_dict())

    def test_incremental_nonconvergence_matches_full_backend(self):
        event = parse_law({"id": "event.enable", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.enabled", "value": 1}]})
        up = law("state.up", mode="state", when={"all": [{"ref": "$x.state.enabled", "eq": 1}, {"ref": "$x.state.flag", "eq": 0}]}, effects=[{"op": "set", "target": "$x.state.flag", "value": 1}])
        down = law("state.down", mode="state", when={"all": [{"ref": "$x.state.enabled", "eq": 1}, {"ref": "$x.state.flag", "eq": 1}]}, effects=[{"op": "set", "target": "$x.state.flag", "value": 0}])
        base = world(state={"enabled": 0, "flag": 0}); fast = Engine([event, up, down], max_settle_iterations=3).attach(deepcopy(base)); slow = Engine([event, up, down], max_settle_iterations=3, _state_closure_backend="full").attach(deepcopy(base)); fast.settle(); slow.settle()
        with self.assertRaises(NonConvergentWorldError) as fast_error: fast.run_event(Event("enable", "go", target="x"))
        with self.assertRaises(NonConvergentWorldError) as slow_error: slow.run_event(Event("enable", "go", target="x"))
        self.assertEqual(fast.state.to_dict(), slow.state.to_dict()); self.assertEqual(fast_error.exception.trace.to_dict(), slow_error.exception.trace.to_dict())

    def test_dependency_plan_includes_effect_value_and_target(self):
        rule = parse_law({"id": "reactive", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"ref": "$x.state.trigger", "eq": 1}, "effects": [{"op": "set", "target": "$x.state.out", "value": {"add": ["$y.state.source", 1]}}]})
        reads = {(item.binding, item.path, item.reason) for item in compile_state_dependency_plan(rule).reads}
        self.assertTrue({("x", ("state", "trigger"), "condition"), ("x", ("state", "out"), "effect_target"), ("y", ("state", "source"), "effect_value")} <= reads)

    def test_dependency_plan_tracks_static_and_dynamic_tag_effects(self):
        static = parse_law({"id": "tag.static", "mode": "state", "bindings": {"x": {"kind": "entity"}}, "when": {"all": []}, "effects": [{"op": "add_tag", "target": "$x", "value": "burning"}]})
        dynamic = parse_law({"id": "tag.dynamic", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": []}, "effects": [{"op": "remove_tag", "target": "$x", "value": "$y.state.tag_name"}]})
        static_reads = {(item.binding, item.path) for item in compile_state_dependency_plan(static).reads}
        dynamic_reads = {(item.binding, item.path) for item in compile_state_dependency_plan(dynamic).reads}
        self.assertIn(("x", ("tags", "burning")), static_reads); self.assertTrue({("x", ("tags",)), ("y", ("state", "tag_name"))} <= dynamic_reads)

    def test_effect_value_propagation_matches_full_backend(self):
        event = parse_law({"id": "event.source", "bindings": {"y": {"kind": "entity"}}, "when": {"all": [{"ref": "$y.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$y.state.source", "value": 1}]})
        state = parse_law({"id": "state.copy", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.state.trigger", "eq": 1}, {"ref": "$x.id", "eq": "x"}, {"ref": "$y.id", "eq": "y"}]}, "effects": [{"op": "set", "target": "$x.state.out", "value": "$y.state.source"}]})
        base = WorldState(entities={"x": Entity("x", components={"state": {"trigger": 1, "out": 0}}), "y": Entity("y", components={"state": {"source": 0}})})
        fast = Engine([event, state]).attach(deepcopy(base)); slow = Engine([event, state], _state_closure_backend="full").attach(deepcopy(base)); fast.settle(); slow.settle()
        left, right = fast.run_event(Event("source", "go", target="y")), slow.run_event(Event("source", "go", target="y"))
        self.assertEqual(fast.state.entities["x"].components["state"]["out"], 1); self.assertEqual(fast.state.to_dict(), slow.state.to_dict()); self.assertEqual(left.trace.to_dict(), right.trace.to_dict())

    def test_effect_target_restoration_matches_full_backend(self):
        event = parse_law({"id": "event.break", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.out", "value": 0}]})
        state = law("state.restore", mode="state", when={"ref": "$x.state.enabled", "eq": 1}, effects=[{"op": "set", "target": "$x.state.out", "value": 1}])
        base = world(state={"enabled": 1, "out": 1}); fast = Engine([event, state]).attach(deepcopy(base)); slow = Engine([event, state], _state_closure_backend="full").attach(deepcopy(base)); fast.settle(); slow.settle()
        left, right = fast.run_event(Event("break", "go", target="x")), slow.run_event(Event("break", "go", target="x"))
        self.assertEqual(fast.state.entities["x"].components["state"]["out"], 1); self.assertEqual(fast.state.to_dict(), slow.state.to_dict()); self.assertEqual(left.trace.to_dict(), right.trace.to_dict())

    def test_tag_restoration_matches_full_backend(self):
        event = parse_law({"id": "event.remove", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "remove_tag", "target": "$x", "value": "burning"}]})
        state = law("state.restore-tag", mode="state", when={"ref": "$x.state.enabled", "eq": 1}, effects=[{"op": "add_tag", "target": "$x", "value": "burning"}])
        base = world(state={"enabled": 1}); base.entities["x"].tags.add("burning"); fast = Engine([event, state]).attach(deepcopy(base)); slow = Engine([event, state], _state_closure_backend="full").attach(deepcopy(base)); fast.settle(); slow.settle()
        left, right = fast.run_event(Event("remove", "go", target="x")), slow.run_event(Event("remove", "go", target="x"))
        self.assertIn("burning", fast.state.entities["x"].tags); self.assertEqual(fast.state.to_dict(), slow.state.to_dict()); self.assertEqual(left.trace.to_dict(), right.trace.to_dict())

    def test_relation_effect_dependencies_match_full_backend(self):
        event = parse_law({"id": "event.power", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.power", "value": 2}]})
        state = parse_law({"id": "state.relation-copy", "mode": "state", "bindings": {"r": {"kind": "relation"}, "x": {"kind": "entity"}}, "when": {"all": [{"ref": "$r.state.enabled", "eq": 1}, {"ref": "$r.id", "eq": "r"}, {"ref": "$x.id", "eq": "x"}]}, "effects": [{"op": "set", "target": "$r.state.strength", "value": "$x.state.power"}]})
        base = WorldState(entities={"x": Entity("x", components={"state": {"power": 1}})}, relations={"r": Relation("r", "contact", "x", "x", components={"state": {"enabled": 1, "strength": 1}})})
        fast = Engine([event, state]).attach(deepcopy(base)); slow = Engine([event, state], _state_closure_backend="full").attach(deepcopy(base)); fast.settle(); slow.settle()
        left, right = fast.run_event(Event("power", "go", target="x")), slow.run_event(Event("power", "go", target="x"))
        self.assertEqual(fast.state.relations["r"].components["state"]["strength"], 2); self.assertEqual(fast.state.to_dict(), slow.state.to_dict()); self.assertEqual(left.trace.to_dict(), right.trace.to_dict())

    def test_effect_target_parent_child_overlap_is_reactive(self):
        event = parse_law({"id": "event.child", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.a", "value": 0}]})
        state = law("state.parent", mode="state", when={"ref": "$x.state.enabled", "eq": 1}, effects=[{"op": "set", "target": "$x.state", "value": {"a": 1, "enabled": 1}}])
        runtime = Engine([event, state]).attach(world(state={"a": 1, "enabled": 1})); runtime.settle(); runtime.run_event(Event("child", "go", target="x"))
        self.assertEqual(runtime.state.entities["x"].components["state"]["a"], 1)

    def test_effect_value_literal_text_is_not_false_dependency(self):
        rule = parse_law({"id": "literal", "mode": "state", "bindings": {"x": {"kind": "entity"}}, "when": {"all": []}, "effects": [{"op": "set", "target": "$x.state.note", "value": "literal $y text"}]})
        reads = compile_state_dependency_plan(rule).reads
        self.assertFalse(any(item.binding == "y" for item in reads))

    def test_effect_dependencies_do_not_force_global_fallback(self):
        rule = parse_law({"id": "copy", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": []}, "effects": [{"op": "set", "target": "$x.state.out", "value": "$y.state.source"}]})
        self.assertFalse(compile_state_dependency_plan(rule).global_state_law)

    def test_dependency_plan_tracks_relation_effect_target(self):
        rule = parse_law({"id": "relation", "mode": "state", "bindings": {"r": {"kind": "relation"}}, "when": {"all": []}, "effects": [{"op": "delta", "target": "$r.state.strength", "value": 1}]})
        self.assertIn(("r", ("state", "strength"), "effect_target"), {(item.binding, item.path, item.reason) for item in compile_state_dependency_plan(rule).reads})

    def test_dependency_plan_walks_recursive_value_expression(self):
        rule = parse_law({"id": "nested", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": []}, "effects": [{"op": "set", "target": "$x.state.out", "value": {"clamp": [{"mul": ["$y.state.power", 2]}, 0, 10]}}]})
        self.assertIn(("y", ("state", "power"), "effect_value"), {(item.binding, item.path, item.reason) for item in compile_state_dependency_plan(rule).reads})

    def test_dynamic_tag_value_change_reactivates_law(self):
        event = parse_law({"id": "event.name", "bindings": {"y": {"kind": "entity"}}, "when": {"all": [{"ref": "$y.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$y.state.tag_name", "value": "hot"}]})
        state = parse_law({"id": "state.dynamic-tag", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "x"}, {"ref": "$y.id", "eq": "y"}]}, "effects": [{"op": "add_tag", "target": "$x", "value": "$y.state.tag_name"}]})
        base = WorldState(entities={"x": Entity("x"), "y": Entity("y", components={"state": {"tag_name": "cold"}})})
        runtime = Engine([event, state]).attach(base); runtime.settle(); runtime.run_event(Event("name", "go", target="y"))
        self.assertIn("hot", runtime.state.entities["x"].tags)

    def test_dynamic_has_tag_uses_value_dsl(self):
        subject = WorldState(entities={"x": Entity("x", tags={"burning"}), "y": Entity("y", components={"state": {"tag_name": "burning"}})})
        self.assertTrue(evaluate({"has_tag": ["$x", "$y.state.tag_name"]}, subject, Event("e", "go"), {"x": subject.entities["x"], "y": subject.entities["y"]}))

    def test_dynamic_has_component_uses_value_dsl(self):
        subject = WorldState(entities={"x": Entity("x", components={"thermal": {}}), "y": Entity("y", components={"state": {"component_name": "thermal"}})})
        self.assertTrue(evaluate({"has_component": ["$x", "$y.state.component_name"]}, subject, Event("e", "go"), {"x": subject.entities["x"], "y": subject.entities["y"]}))

    def test_arithmetic_comparator_rhs_uses_value_dsl(self):
        subject = WorldState(entities={"x": Entity("x", components={"state": {"v": 4}}), "y": Entity("y", components={"state": {"threshold": 2}})})
        self.assertTrue(evaluate({"ref": "$x.state.v", "gt": {"add": ["$y.state.threshold", 1]}}, subject, Event("e", "go"), {"x": subject.entities["x"], "y": subject.entities["y"]}))

    def test_membership_non_string_operand_is_false(self):
        subject = world(state={}); subject.entities["x"].tags.add("hot")
        bindings = {"x": subject.entities["x"]}
        self.assertFalse(evaluate({"has_tag": ["$x", ["hot"]]}, subject, Event("e", "go"), bindings)); self.assertFalse(evaluate({"has_component": ["$x", {"bad": 1}]}, subject, Event("e", "go"), bindings))

    def test_ordered_comparator_type_error_is_explicit(self):
        subject = world(state={"v": 1}); bindings = {"x": subject.entities["x"]}
        with self.assertRaises(DSLConditionTypeError): evaluate({"ref": "$x.state.v", "gt": "text"}, subject, Event("e", "go"), bindings)

    def test_dynamic_predicate_operand_dependency_plan(self):
        rule = parse_law({"id": "predicate", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": [{"has_tag": ["$x", "$y.state.tag_name"]}, {"has_component": ["$x", "$y.state.component_name"]}]}, "effects": []})
        reads = {(item.binding, item.path) for item in compile_state_dependency_plan(rule).reads}
        self.assertTrue({("x", ("tags",)), ("x", ()), ("y", ("state", "tag_name")), ("y", ("state", "component_name"))} <= reads)

    def test_dynamic_predicate_change_matches_full_semantics(self):
        event = parse_law({"id": "event.name", "bindings": {"y": {"kind": "entity"}}, "when": {"all": [{"ref": "$y.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$y.state.tag_name", "value": "hot"}]})
        state = parse_law({"id": "state.predicate", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": [{"has_tag": ["$x", "$y.state.tag_name"]}, {"ref": "$x.id", "eq": "x"}, {"ref": "$y.id", "eq": "y"}]}, "effects": [{"op": "set", "target": "$x.state.hit", "value": 1}]})
        base = WorldState(entities={"x": Entity("x", tags={"hot"}, components={"state": {"hit": 0}}), "y": Entity("y", components={"state": {"tag_name": "cold"}})})
        fast = Engine([event, state]).attach(deepcopy(base)); slow = Engine([event, state], _state_closure_backend="full").attach(deepcopy(base)); fast.settle(); slow.settle(); left, right = fast.run_event(Event("name", "go", target="y")), slow.run_event(Event("name", "go", target="y"))
        self.assertEqual(fast.state.to_dict(), slow.state.to_dict()); self.assertEqual(left.trace.semantic_projection(), right.trace.semantic_projection())

    def test_long_chain_frontier_activation_is_linearish(self):
        for length in (10, 100, 500):
            entities = {f"e{i}": Entity(f"e{i}", components={"state": {"active": 0}}) for i in range(length + 1)}
            relations = {f"r{i}": Relation(f"r{i}", "link", f"e{i}", f"e{i + 1}") for i in range(length)}
            event = parse_law({"id": "event.start", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.active", "value": 1}]})
            spread = parse_law({"id": "state.spread", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}, "r": {"kind": "relation", "type": "link", "source": "$x", "target": "$y"}}, "when": {"all": [{"ref": "$x.state.active", "eq": 1}, {"ref": "$y.state.active", "eq": 0}]}, "effects": [{"op": "set", "target": "$y.state.active", "value": 1}]})
            runtime = Engine([event, spread], max_settle_iterations=length + 5).attach(WorldState(entities=entities, relations=relations)); runtime.settle(); before = runtime.stats.seeded_match_calls
            runtime.run_event(Event("start", "go", target="e0"))
            self.assertTrue(all(item.components["state"]["active"] == 1 for item in runtime.state.entities.values())); self.assertLessEqual(runtime.stats.seeded_match_calls - before, 3 * length + 3)

    def test_semantic_projection_excludes_noop_execution(self):
        law_a = law("event.set", effects=[{"op": "set", "target": "$x.state.a", "value": 1}])
        settle = law("state.noop", mode="state", when={"ref": "$x.state.a", "eq": 1}, effects=[{"op": "set", "target": "$x.state.a", "value": 1}])
        result = Engine([law_a, settle]).run_event(world(state={"a": 0}), Event("root", "root"))
        self.assertLess(len(result.trace.semantic_projection()["events"][0]["commits"]), len(result.trace.to_dict()["events"][0]["commits"]))

    def test_raw_execution_trace_is_deterministic_per_backend(self):
        laws = [law("event.set", effects=[{"op": "set", "target": "$x.state.a", "value": 1}]), law("state.set", mode="state", when={"ref": "$x.state.a", "eq": 1}, effects=[{"op": "set", "target": "$x.state.b", "value": 1}])]
        first = Engine(laws).run_event(world(state={"a": 0, "b": 0}), Event("root", "root")); second = Engine(laws).run_event(world(state={"a": 0, "b": 0}), Event("root", "root"))
        self.assertEqual(first.trace.to_dict(), second.trace.to_dict())

    def test_dynamic_component_predicate_change_matches_full_semantics(self):
        event = parse_law({"id": "event.component", "bindings": {"y": {"kind": "entity"}}, "when": {"all": [{"ref": "$y.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$y.state.component_name", "value": "thermal"}]})
        state = parse_law({"id": "state.component", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": [{"has_component": ["$x", "$y.state.component_name"]}, {"ref": "$x.id", "eq": "x"}, {"ref": "$y.id", "eq": "y"}]}, "effects": [{"op": "set", "target": "$x.state.hit", "value": 1}]})
        base = WorldState(entities={"x": Entity("x", components={"thermal": {}, "state": {"hit": 0}}), "y": Entity("y", components={"state": {"component_name": "other"}})})
        fast = Engine([event, state]).attach(deepcopy(base)); slow = Engine([event, state], _state_closure_backend="full").attach(deepcopy(base)); fast.settle(); slow.settle(); left, right = fast.run_event(Event("component", "go", target="y")), slow.run_event(Event("component", "go", target="y"))
        self.assertEqual(fast.state.to_dict(), slow.state.to_dict()); self.assertEqual(left.trace.semantic_projection(), right.trace.semantic_projection())

    def test_comparator_rhs_reference_preserves_literal_behavior(self):
        subject = WorldState(entities={"x": Entity("x", components={"state": {"name": "same"}}), "y": Entity("y", components={"state": {"expected": "same"}})})
        self.assertTrue(evaluate({"ref": "$x.state.name", "eq": "$y.state.expected"}, subject, Event("e", "go"), subject.entities))

    def test_full_incremental_nonconvergence_semantic_projection(self):
        event = parse_law({"id": "event.enable", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.enabled", "value": 1}]})
        up = law("state.up", mode="state", when={"all": [{"ref": "$x.state.enabled", "eq": 1}, {"ref": "$x.state.flag", "eq": 0}]}, effects=[{"op": "set", "target": "$x.state.flag", "value": 1}]); down = law("state.down", mode="state", when={"all": [{"ref": "$x.state.enabled", "eq": 1}, {"ref": "$x.state.flag", "eq": 1}]}, effects=[{"op": "set", "target": "$x.state.flag", "value": 0}])
        fast = Engine([event, up, down], max_settle_iterations=3).attach(world(state={"enabled": 0, "flag": 0})); slow = Engine([event, up, down], max_settle_iterations=3, _state_closure_backend="full").attach(world(state={"enabled": 0, "flag": 0})); fast.settle(); slow.settle()
        with self.assertRaises(NonConvergentWorldError) as left: fast.run_event(Event("enable", "go", target="x"))
        with self.assertRaises(NonConvergentWorldError) as right: slow.run_event(Event("enable", "go", target="x"))
        self.assertEqual(left.exception.trace.semantic_projection(), right.exception.trace.semantic_projection())

    def test_frontier_activation_is_not_cumulative(self):
        event = law("event", effects=[{"op": "set", "target": "$x.state.a", "value": 1}])
        one = law("state.one", mode="state", when={"ref": "$x.state.a", "eq": 1}, effects=[{"op": "set", "target": "$x.state.b", "value": 1}]); two = law("state.two", mode="state", when={"ref": "$x.state.b", "eq": 1}, effects=[{"op": "set", "target": "$x.state.c", "value": 1}])
        runtime = Engine([event, one, two]).attach(world(state={"a": 0, "b": 0, "c": 0})); runtime.settle(); before = runtime.stats.seeded_match_calls; runtime.run_event(Event("root", "root"))
        self.assertLessEqual(runtime.stats.seeded_match_calls - before, 6)

    def test_generated_state_program_differential_1000_cases(self):
        rng = random.Random(2423)
        for case in range(1000):
            count = rng.randrange(1, 5); entities = {f"e{i}": Entity(f"e{i}", tags={"hot"} if rng.randrange(2) else set(), components={"state": {"v": rng.randrange(3), "source": rng.randrange(3), "enabled": 1, "out0": 0, "out1": 0, "out2": 0, "out3": 0}}) for i in range(count)}
            relations = {f"r{i}": Relation(f"r{i}", "link", f"e{i}", f"e{(i + 1) % count}", components={"state": {"enabled": 1, "out": 0}}) for i in range(min(rng.randrange(4), count))}
            target = f"e{rng.randrange(count)}"
            event = parse_law({"id": "event", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.v", "value": rng.randrange(3)}, {"op": "set", "target": "$x.state.source", "value": rng.randrange(3)}]})
            laws = [event]
            for law_number in range(rng.randrange(1, 5)):
                owner = f"e{rng.randrange(count)}"; kind = rng.randrange(5); field = f"out{law_number}"
                if kind == 0:
                    laws.append(parse_law({"id": f"state.{law_number}", "mode": "state", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": owner}, {"ref": "$x.state.enabled", "eq": 1}, {"ref": "$x.state.v", "gte": 0}]}, "effects": [{"op": "set", "target": f"$x.state.{field}", "value": rng.randrange(3)}]}))
                elif kind == 1:
                    source = f"e{rng.randrange(count)}"
                    laws.append(parse_law({
                        "id": f"state.{law_number}", "mode": "state",
                        "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}},
                        "when": {"all": [
                            {"ref": "$x.id", "eq": owner},
                            {"ref": "$y.id", "eq": source},
                            {"any": [{"ref": "$y.state.v", "gte": 0}, {"not": {"has_tag": ["$y", "never"]}}]},
                        ]},
                        "effects": [{"op": "set", "target": f"$x.state.{field}", "value": {"add": ["$y.state.source", 1]}}],
                    }))
                elif kind == 2:
                    laws.append(parse_law({"id": f"state.{law_number}", "mode": "state", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": owner}, {"has_component": ["$x", "state"]}]}, "effects": [{"op": "add_tag", "target": "$x", "value": "marked"}]}))
                elif kind == 3:
                    laws.append(parse_law({"id": f"state.{law_number}", "mode": "state", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": owner}, {"has_tag": ["$x", "hot"]}]}, "effects": [{"op": "remove_tag", "target": "$x", "value": "hot"}]}))
                elif relations:
                    laws.append(parse_law({"id": f"state.{law_number}", "mode": "state", "bindings": {"r": {"kind": "relation"}}, "when": {"all": [{"ref": "$r.id", "eq": "r0"}, {"ref": "$r.state.enabled", "eq": 1}]}, "effects": [{"op": "set", "target": "$r.state.out", "value": 1}]}))
            fast = Engine(laws, max_settle_iterations=20).attach(WorldState(entities=deepcopy(entities), relations=deepcopy(relations))); slow = Engine(laws, max_settle_iterations=20, _state_closure_backend="full").attach(WorldState(entities=deepcopy(entities), relations=deepcopy(relations)))
            fast.settle(); slow.settle(); left, right = fast.run_event(Event(f"event{case}", "go", target=target)), slow.run_event(Event(f"event{case}", "go", target=target))
            left_deltas = [(str(delta.address), delta.old_value, delta.new_value, delta.law_ids) for delta in left.state_delta]
            right_deltas = [(str(delta.address), delta.old_value, delta.new_value, delta.law_ids) for delta in right.state_delta]
            self.assertEqual(fast.state.to_dict(), slow.state.to_dict()); self.assertEqual(left.changed, right.changed); self.assertEqual(left_deltas, right_deltas); self.assertEqual(left.trace.semantic_projection(), right.trace.semantic_projection())

    def test_randomized_reactive_closure_differential_1000_cases(self):
        rng = random.Random(2421)
        for case in range(1000):
            variant, size = rng.randrange(4), rng.randrange(2, 5); target = f"e{rng.randrange(size)}"
            entities = {f"e{i}": Entity(f"e{i}", components={"state": {"enabled": 1, "source": i, "out": i, "a": 0}}) for i in range(size)}
            if variant == 0:
                target = "e0"; event = parse_law({"id": "event", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.out", "value": 0}]}); state = law("state", mode="state", when={"all": [{"ref": "$x.state.enabled", "eq": 1}, {"ref": "$x.id", "eq": "e0"}]}, effects=[{"op": "set", "target": "$x.state.out", "value": 1}])
            elif variant == 1:
                entities["e0"].components["state"]["out"] = entities["e1"].components["state"]["source"]
                event = parse_law({"id": "event", "bindings": {"y": {"kind": "entity"}}, "when": {"all": [{"ref": "$y.id", "eq": "$event.target"}]}, "effects": [{"op": "delta", "target": "$y.state.source", "value": 1}]}); state = parse_law({"id": "state", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "e0"}, {"ref": "$y.id", "eq": "e1"}]}, "effects": [{"op": "set", "target": "$x.state.out", "value": "$y.state.source"}]}); target = "e1"
            elif variant == 2:
                target = "e0"; entities[target].tags.add("burning")
                event = parse_law({"id": "event", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "remove_tag", "target": "$x", "value": "burning"}]}); state = law("state", mode="state", when={"all": [{"ref": "$x.state.enabled", "eq": 1}, {"ref": "$x.id", "eq": "e0"}]}, effects=[{"op": "add_tag", "target": "$x", "value": "burning"}])
            else:
                target = "e0"; event = parse_law({"id": "event", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state", "value": {"enabled": 1, "a": 0, "out": 0, "source": 0}}]}); state = law("state", mode="state", when={"all": [{"ref": "$x.state.enabled", "eq": 1}, {"ref": "$x.id", "eq": "e0"}]}, effects=[{"op": "set", "target": "$x.state.a", "value": 1}, {"op": "set", "target": "$x.state.out", "value": 1}])
            fast = Engine([event, state]).attach(WorldState(entities=deepcopy(entities))); slow = Engine([event, state], _state_closure_backend="full").attach(WorldState(entities=deepcopy(entities))); fast.settle(); slow.settle()
            left, right = fast.run_event(Event(f"event{case}", "go", target=target)), slow.run_event(Event(f"event{case}", "go", target=target))
            self.assertEqual(fast.state.to_dict(), slow.state.to_dict()); self.assertEqual(left.trace.to_dict(), right.trace.to_dict())

    def test_match_plan_is_cached_by_engine(self):
        rule = law("cached", effects=[]); engine = Engine([rule]); self.assertIs(engine.match_plans["cached"].law, rule)

    def test_runtime_snapshot_isolation_and_structural_sharing(self):
        rule = law("set", bindings={"x": {"kind": "entity", "requires": ["state"]}}, effects=[{"op": "set", "target": "$x.state.value", "value": 2}])
        subject = WorldState(entities={"x": Entity("x", components={"state": {"value": 1}}), "untouched": Entity("untouched")})
        runtime = Engine([rule]).attach(subject); snapshot = runtime.snapshot(); old_x = snapshot.entities["x"]; old_other = subject.entities["untouched"]
        runtime.run_event(Event("root", "root"))
        self.assertEqual(snapshot.entities["x"].components["state"]["value"], 1); self.assertEqual(subject.entities["x"].components["state"]["value"], 2)
        self.assertIs(snapshot.entities["x"], old_x); self.assertIsNot(subject.entities["x"], old_x); self.assertIs(subject.entities["untouched"], old_other)

    def test_runtime_clones_once_and_noop_clones_zero(self):
        many = law("many", effects=[{"op": "set", "target": "$x.state.a", "value": 1}, {"op": "set", "target": "$x.state.b", "value": 2}])
        runtime = Engine([many]).attach(world(state={"a": 0, "b": 0})); runtime.run_event(Event("root", "root")); self.assertEqual(runtime.stats.objects_cloned, 1)
        idle = Engine([]).attach(world(state={"a": 0})); idle.run_event(Event("root", "root")); self.assertEqual(idle.stats.objects_cloned, 0); self.assertEqual(idle.stats.full_world_deepcopies, 0)

    def test_runtime_prepare_failure_is_atomic_and_revision_tracks_delta(self):
        bad = law("bad", effects=[{"op": "set", "target": "$x.state.value", "value": 2}, {"op": "delta", "target": "$x.state.missing", "value": 1}])
        subject = world(state={"value": 1}); runtime = Engine([bad]).attach(subject)
        with self.assertRaises(ValueError): runtime.run_event(Event("root", "root"))
        self.assertEqual(subject.entities["x"].components["state"]["value"], 1); self.assertEqual(runtime.revision, 0)
        runtime.revalidate(); self.assertEqual(runtime.revision, 1)

    def test_runtime_noop_proposals_preserve_identity(self):
        for effect in ([{"op": "set", "target": "$x.state.value", "value": 1}], [{"op": "add_tag", "target": "$x", "value": "present"}], [{"op": "delta", "target": "$x.state.value", "value": 0}]):
            subject = world(state={"value": 1}); subject.entities["x"].tags.add("present"); old = subject.entities["x"]
            runtime = Engine([law("noop", effects=effect)]).attach(subject); runtime.run_event(Event("root", "root"))
            self.assertIs(subject.entities["x"], old); self.assertEqual(runtime.stats.objects_cloned, 0); self.assertEqual(runtime.stats.objects_swapped, 0); self.assertEqual(runtime.revision, 0)

    def test_runtime_rejects_invalid_generated_component_value_atomically(self):
        bad = parse_law({"id": "bad", "bindings": {"x": {"kind": "entity"}}, "when": {"event.type": {"eq": "root"}}, "effects": [{"op": "set", "target": "$x.state.value", "value": float("nan")}]}, validate=False)
        subject = world(state={"value": 1}); runtime = Engine([bad], validate=False).attach(subject)
        with self.assertRaises(WorldValidationError): runtime.run_event(Event("root", "root"))
        self.assertEqual(subject.entities["x"].components["state"]["value"], 1)

    def test_world_boundaries_reject_non_json_component_values(self):
        for invalid in (float("inf"), {1}, {1: "bad"}):
            subject = world(state={"value": invalid})
            with self.assertRaises(WorldValidationError): Engine([]).attach(subject)
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(WorldValidationError): save_world(Path(directory) / "invalid.json", subject)

    def test_empty_runtime_avoids_snapshots_and_repeated_validation(self):
        runtime = Engine([]).attach(world(state={"value": 1})); runtime.run_event(Event("root", "root")); runtime.run_event(Event("root2", "root"))
        self.assertEqual(runtime.stats.snapshot_count, 0); self.assertEqual(runtime.stats.full_world_validations, 1); self.assertEqual(runtime.stats.full_world_deepcopies, 0)

    def test_cow_commit_differential_500_transactions(self):
        rng = random.Random(24)
        for _ in range(500):
            value = rng.randrange(-5, 6); delta = rng.randrange(-2, 3)
            subject = world(state={"value": value}); rule = law("tx", effects=[{"op": "delta", "target": "$x.state.value", "value": delta}])
            result = Engine([rule]).run_event(subject, Event("root", "root"))
            self.assertEqual(subject.entities["x"].components["state"]["value"], value + delta)
            self.assertEqual(bool(result.state_delta), delta != 0)

    def test_value_contract_rejects_set(self):
        with self.assertRaises(WorldValidationError): Engine([parse_law({"id":"x","bindings":{"x":{"kind":"entity"}},"effects":[{"op":"set","target":"$x.state.v","value":{1}}]},validate=False)], validate=False).attach(world(state={"v":0})).run_event(Event("r","r"))
    def test_value_contract_rejects_tuple(self):
        with self.assertRaises(WorldValidationError): Engine([parse_law({"id":"x","bindings":{"x":{"kind":"entity"}},"effects":[{"op":"set","target":"$x.state.v","value":(1,)}]},validate=False)], validate=False).attach(world(state={"v":0})).run_event(Event("r","r"))
    def test_value_contract_rejects_bytes(self):
        with self.assertRaises(WorldValidationError): Engine([parse_law({"id":"x","bindings":{"x":{"kind":"entity"}},"effects":[{"op":"set","target":"$x.state.v","value":b"x"}]},validate=False)], validate=False).attach(world(state={"v":0})).run_event(Event("r","r"))
    def test_runtime_stats_counts_event_validation(self):
        runtime=Engine([]).attach(world(state={})); runtime.run_event(Event("r","r")); self.assertEqual(runtime.stats.event_validations,1)
    def test_runtime_stats_counts_transaction(self):
        runtime=Engine([law("x",effects=[{"op":"set","target":"$x.state.v","value":1}])]).attach(world(state={"v":0})); runtime.run_event(Event("root","root")); self.assertEqual(runtime.stats.transactions_committed,1)
    def test_no_state_laws_uses_one_evaluation_view_not_snapshot(self):
        runtime=Engine([law("x",effects=[])]).attach(world(state={})); runtime.run_event(Event("r","r")); self.assertEqual(runtime.stats.evaluation_views,1); self.assertEqual(runtime.stats.snapshot_count,0)
    def test_noop_transaction_counter(self):
        runtime=Engine([law("x",effects=[{"op":"set","target":"$x.state.v","value":0}])]).attach(world(state={"v":0})); runtime.run_event(Event("r","r")); self.assertGreaterEqual(runtime.stats.noop_transactions,1)
    def test_snapshot_revision_is_captured(self):
        runtime=Engine([]).attach(world(state={})); snapshot=runtime.snapshot(); self.assertEqual(snapshot.revision,0)

    def test_runtime_index_exact_id_only_workload_builds_nothing(self):
        rule = parse_law({"id": "exact", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": []})
        runtime = Engine([rule]).attach(WorldState(entities={f"e{i}": Entity(f"e{i}") for i in range(100)}))
        runtime.run_event(Event("root", "root", target="e42"))
        self.assertEqual(runtime.stats.runtime_index_builds, 0)

    def test_runtime_index_is_lazy_then_reused_between_events(self):
        rule = law("indexed", bindings={"x": {"kind": "entity", "requires": ["state"]}}, effects=[])
        runtime = Engine([rule]).attach(WorldState(entities={"x": Entity("x", components={"state": {}})}))
        runtime.run_event(Event("one", "root")); self.assertEqual(runtime.stats.runtime_index_builds, 1)
        runtime.run_event(Event("two", "root")); self.assertEqual(runtime.stats.runtime_index_builds, 1); self.assertGreaterEqual(runtime.stats.runtime_index_reuses, 1)

    def test_entity_component_creation_patches_persistent_index(self):
        create = parse_law({"id": "create", "bindings": {"x": {"kind": "entity"}}, "when": {"event.type": {"eq": "create"}}, "effects": [{"op": "set", "target": "$x.thermal.value", "value": 1}]})
        observe = parse_law({"id": "observe", "bindings": {"x": {"kind": "entity", "requires": ["thermal"]}}, "when": {"event.type": {"eq": "observe"}}, "effects": [{"op": "set", "target": "$x.state.seen", "value": 1}]})
        runtime = Engine([create, observe]).attach(world(state={"seen": 0})); runtime.get_index(); runtime.run_event(Event("create", "create")); runtime.run_event(Event("observe", "observe"))
        self.assertEqual(runtime.state.entities["x"].components["state"]["seen"], 1); self.assertEqual(runtime.stats.entity_component_posting_adds, 1); self.assertEqual(runtime.stats.runtime_index_builds, 1)

    def test_relation_component_creation_patches_persistent_index(self):
        create = parse_law({"id": "create", "bindings": {"r": {"kind": "relation"}}, "when": {"event.type": {"eq": "create"}}, "effects": [{"op": "set", "target": "$r.thermal.value", "value": 1}]})
        observe = parse_law({"id": "observe", "bindings": {"r": {"kind": "relation", "requires": ["thermal"]}}, "when": {"event.type": {"eq": "observe"}}, "effects": [{"op": "set", "target": "$r.state.seen", "value": 1}]})
        runtime = Engine([create, observe]).attach(WorldState(entities={"a": Entity("a"), "b": Entity("b")}, relations={"r": Relation("r", "link", "a", "b", components={"state": {"seen": 0}})})); runtime.get_index(); runtime.run_event(Event("create", "create")); runtime.run_event(Event("observe", "observe"))
        self.assertEqual(runtime.state.relations["r"].components["state"]["seen"], 1); self.assertEqual(runtime.stats.relation_component_posting_adds, 1); self.assertEqual(runtime.stats.runtime_index_builds, 1)

    def test_component_field_mutation_patches_without_posting_change(self):
        runtime = Engine([law("change", effects=[{"op": "set", "target": "$x.state.value", "value": 1}])]).attach(world(state={"value": 0}))
        runtime.get_index(); runtime.run_event(Event("root", "root"))
        self.assertEqual(runtime.stats.runtime_index_patches, 1); self.assertEqual(runtime.stats.entity_component_posting_adds, 0); self.assertEqual(runtime.stats.entity_component_posting_removes, 0)

    def test_noop_commit_does_not_patch_or_advance_runtime_index(self):
        runtime = Engine([law("noop", effects=[{"op": "set", "target": "$x.state.value", "value": 0}])]).attach(world(state={"value": 0}))
        runtime.get_index(); runtime.run_event(Event("root", "root"))
        self.assertEqual(runtime.revision, 0); self.assertEqual(runtime.stats.runtime_index_patches, 0); self.assertEqual(runtime._index_revision, 0)

    def test_revalidate_invalidates_index_and_rebuilds_from_live_state(self):
        rule = law("thermal", bindings={"x": {"kind": "entity", "requires": ["thermal"]}}, effects=[{"op": "set", "target": "$x.state.hit", "value": 1}])
        runtime = Engine([rule]).attach(world(state={"hit": 0})); runtime.get_index(); runtime.state.entities["x"].components["thermal"] = {"value": 1}; runtime.revalidate(); runtime.run_event(Event("root", "root"))
        self.assertEqual(runtime.state.entities["x"].components["state"]["hit"], 1); self.assertEqual(runtime.stats.runtime_index_invalidations, 1); self.assertEqual(runtime.stats.runtime_index_builds, 2)

    def test_public_snapshot_isolated_while_evaluation_view_is_zero_copy(self):
        runtime = Engine([]).attach(world(state={"value": 0})); snapshot = runtime.snapshot(); view = runtime._read_view()
        self.assertIs(view.entities, runtime.state.entities); self.assertIsNot(snapshot.entities, runtime.state.entities); self.assertEqual(runtime.stats.public_snapshots, 1); self.assertEqual(runtime.stats.evaluation_views, 1)

    def test_persistent_index_survives_incremental_relation_chain(self):
        count = 250
        entities = {f"e{i}": Entity(f"e{i}", components={"state": {"active": 0}}) for i in range(count + 1)}
        relations = {f"r{i}": Relation(f"r{i}", "link", f"e{i}", f"e{i + 1}") for i in range(count)}
        event = parse_law({"id": "start", "bindings": {"x": {"kind": "entity"}}, "when": {"ref": "$x.id", "eq": "$event.target"}, "effects": [{"op": "set", "target": "$x.state.active", "value": 1}]})
        spread = parse_law({"id": "spread", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}, "r": {"kind": "relation", "type": "link", "source": "$x", "target": "$y"}}, "when": {"all": [{"ref": "$x.state.active", "eq": 1}, {"ref": "$y.state.active", "eq": 0}]}, "effects": [{"op": "set", "target": "$y.state.active", "value": 1}]})
        runtime = Engine([event, spread], max_settle_iterations=count + 5).attach(WorldState(entities=entities, relations=relations)); runtime.settle(); before = runtime.stats.runtime_index_builds; runtime.run_event(Event("go", "go", target="e0"))
        self.assertEqual(runtime.state.entities[f"e{count}"].components["state"]["active"], 1); self.assertEqual(runtime.stats.runtime_index_builds, before)

    def test_fixed_100k_world_chain_keeps_warm_index_builds_constant(self):
        length, size = 10, 100_000
        entities = {f"e{i}": Entity(f"e{i}", components={"state": {"active": 0}}) for i in range(size)}
        relations = {f"r{i}": Relation(f"r{i}", "link", f"e{i}", f"e{i + 1}") for i in range(length)}
        event = parse_law({"id": "start", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.active", "value": 1}]})
        spread = parse_law({"id": "spread", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}, "r": {"kind": "relation", "type": "link", "source": "$x", "target": "$y"}}, "when": {"all": [{"ref": "$x.state.active", "eq": 1}, {"ref": "$y.state.active", "eq": 0}]}, "effects": [{"op": "set", "target": "$y.state.active", "value": 1}]})
        runtime = Engine([event, spread], max_settle_iterations=20).attach(WorldState(entities=entities, relations=relations)); runtime.settle(); before = runtime.stats.runtime_index_builds; runtime.run_event(Event("go", "go", target="e0"))
        self.assertEqual(runtime.state.entities[f"e{length}"].components["state"]["active"], 1); self.assertEqual(runtime.stats.runtime_index_builds, before)

    def test_persistent_and_rebuild_each_view_match_for_1000_seeded_cases(self):
        rng = random.Random(2444)
        for case in range(1000):
            variant, size, target = case % 6, rng.randrange(2, 5), rng.randrange(2)
            entities = {f"e{i}": Entity(f"e{i}", components={"state": {"value": 0, "seen": 0, "source": 0, "out": 0, "tag_name": "hot"}}) for i in range(size)}
            relations = {"r": Relation("r", "link", "e0", "e1", components={"state": {"mark": 0}})}
            if variant == 0:
                event = parse_law({"id": "event", "bindings": {"x": {"kind": "entity"}, "r": {"kind": "relation", "type": "link", "source": "$x", "target": "$y"}, "y": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}, {"any": [{"ref": "$r.state.mark", "eq": 0}, {"not": {"ref": "$y.id", "eq": "missing"}}]}]}, "effects": [{"op": "set", "target": "$x.state.value", "value": 1}, {"op": "set", "target": "$r.state.mark", "value": 1}]})
                state = parse_law({"id": "state", "mode": "state", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"all": [{"ref": "$x.state.value", "eq": 1}, {"has_component": ["$x", "state"]}]}, "effects": [{"op": "set", "target": "$x.state.seen", "value": 1}]})
            elif variant == 1:
                target = 0; event = parse_law({"id": "event", "bindings": {"x": {"kind": "entity"}}, "when": {"ref": "$x.id", "eq": "$event.target"}, "effects": [{"op": "set", "target": "$x.thermal.temperature", "value": 100}]})
                state = parse_law({"id": "state", "mode": "state", "bindings": {"x": {"kind": "entity", "requires": ["thermal"]}}, "when": {"ref": "$x.thermal.temperature", "eq": 100}, "effects": [{"op": "set", "target": "$x.state.seen", "value": 1}]})
            elif variant == 2:
                event = parse_law({"id": "event", "bindings": {"r": {"kind": "relation"}}, "when": {"ref": "$r.id", "eq": "r"}, "effects": [{"op": "set", "target": "$r.thermal.temperature", "value": 100}]})
                state = parse_law({"id": "state", "mode": "state", "bindings": {"r": {"kind": "relation", "requires": ["thermal"]}}, "when": {"ref": "$r.thermal.temperature", "eq": 100}, "effects": [{"op": "set", "target": "$r.state.mark", "value": 1}]})
            elif variant == 3:
                target = 0; event = parse_law({"id": "event", "bindings": {"x": {"kind": "entity"}}, "when": {"ref": "$x.id", "eq": "$event.target"}, "effects": [{"op": "add_tag", "target": "$x", "value": "hot"}]})
                state = parse_law({"id": "state", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "e0"}, {"ref": "$y.id", "eq": "e1"}, {"has_tag": ["$x", "$y.state.tag_name"]}]}, "effects": [{"op": "set", "target": "$x.state.seen", "value": 1}]})
            elif variant == 4:
                target = 1; event = parse_law({"id": "event", "bindings": {"y": {"kind": "entity"}}, "when": {"ref": "$y.id", "eq": "$event.target"}, "effects": [{"op": "set", "target": "$y.state.source", "value": 7}]})
                state = parse_law({"id": "state", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "e0"}, {"ref": "$y.id", "eq": "e1"}]}, "effects": [{"op": "set", "target": "$x.state.out", "value": "$y.state.source"}]})
            else:
                target = 0; event = parse_law({"id": "event", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}, "r": {"kind": "relation", "type": "link", "source": "$x", "target": "$y"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}, {"ref": "$y.id", "eq": "e1"}]}, "effects": [{"op": "set", "target": "$y.state.value", "value": 1}]})
                state = parse_law({"id": "state", "mode": "state", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"ref": "$x.state.value", "eq": 1}, "effects": [{"op": "set", "target": "$x.state.seen", "value": 1}]})
            persistent = Engine([event, state]).attach(WorldState(entities=deepcopy(entities), relations=deepcopy(relations)))
            rebuild = Engine([event, state], _runtime_index_mode="rebuild_each_view").attach(WorldState(entities=deepcopy(entities), relations=deepcopy(relations)))
            left, right = persistent.run_event(Event(f"case{case}", "go", target=f"e{target}")), rebuild.run_event(Event(f"case{case}", "go", target=f"e{target}"))
            self.assertEqual(persistent.state.to_dict(), rebuild.state.to_dict()); self.assertEqual(left.trace.to_dict(), right.trace.to_dict())

    def test_rebuild_each_view_backend_rebuilds_without_persistent_cache(self):
        runtime = Engine([law("indexed", bindings={"x": {"kind": "entity", "requires": ["state"]}}, effects=[])], _runtime_index_mode="rebuild_each_view").attach(world(state={}))
        runtime.run_event(Event("one", "root")); runtime.run_event(Event("two", "root"))
        self.assertGreaterEqual(runtime.stats.runtime_index_builds, 2); self.assertIsNone(runtime._index)

    def test_index_patch_failure_invalidates_cache_after_world_commit(self):
        runtime = Engine([law("create", effects=[{"op": "set", "target": "$x.thermal.value", "value": 1}])]).attach(world(state={}))
        runtime.get_index(); runtime._index.entities_by_component = None
        runtime.run_event(Event("root", "root"))
        self.assertEqual(runtime.state.entities["x"].components["thermal"]["value"], 1); self.assertIsNone(runtime._index); self.assertEqual(runtime.stats.runtime_index_invalidations, 1)

    def test_static_law_literals_must_be_finite_json_values(self):
        for invalid in ({1}, (1,), b"bytes", float("nan"), {"nested": {1}}):
            with self.assertRaises(LawValidationError):
                parse_law({"id": "invalid", "bindings": {"x": {"kind": "entity"}}, "effects": [{"op": "set", "target": "$x.state.value", "value": invalid}]})

    def test_prepare_validates_all_clones_before_any_swap(self):
        subject = WorldState(entities={"a": Entity("a", components={"state": {"v": 0}}), "b": Entity("b", components={"state": {"v": 0}})})
        runtime = Engine([]).attach(subject)
        original_a, original_b = subject.entities["a"], subject.entities["b"]
        proposals = [
            EffectProposal("a", "test", 0, "set", StateAddress("entity", "a", ("state", "v")), 1),
            EffectProposal("b", "test", 0, "set", StateAddress("entity", "b", ("state", "v")), float("nan")),
        ]
        with self.assertRaises(WorldValidationError): runtime.engine._commit(runtime, proposals)
        self.assertIs(subject.entities["a"], original_a); self.assertIs(subject.entities["b"], original_b)
        self.assertEqual(subject.entities["a"].components["state"]["v"], 0); self.assertEqual(subject.entities["b"].components["state"]["v"], 0)

    def test_cow_commit_matches_full_copy_reference_for_500_transactions(self):
        rng = random.Random(2401)
        for case in range(500):
            state = {"v": rng.randrange(-5, 6), "nested": {"v": rng.randrange(-5, 6)}}
            original = WorldState(entities={"x": Entity("x", tags={"old"}, components=deepcopy(state)), "y": Entity("y", components={"state": {"v": 0}})}, relations={"r": Relation("r", "link", "x", "y", components={"state": {"v": 0}})})
            cow_runtime = Engine([]).attach(deepcopy(original))
            reference_runtime = Engine([]).attach(deepcopy(original))
            proposals = []
            for serial in range(rng.randrange(1, 6)):
                choice = rng.randrange(6)
                if choice == 0: target, op, value = StateAddress("entity", "x", ("state", "v")), "set", rng.randrange(-5, 6)
                elif choice == 1: target, op, value = StateAddress("entity", "x", ("state", "v")), "delta", rng.randrange(-2, 3)
                elif choice == 2: target, op, value = StateAddress("entity", "x", ("state", "nested", "v")), "set", rng.randrange(-5, 6)
                elif choice == 3: target, op, value = StateAddress("entity", "x"), "add_tag", "new"
                elif choice == 4: target, op, value = StateAddress("entity", "x"), "remove_tag", "old"
                else: target, op, value = StateAddress("relation", "r", ("state", "v")), "delta", rng.randrange(-2, 3)
                proposals.append(EffectProposal(f"p{case}:{serial}", "reference", 0, op, target, value))
            if case % 17 == 0:
                proposals.append(EffectProposal(f"bad{case}", "reference", 0, "delta", StateAddress("entity", "y", ("state", "missing")), 1))
            try:
                derived, deltas = cow_runtime.engine._commit(cow_runtime, proposals)
            except ValueError:
                with self.assertRaises(ValueError): self._full_copy_commit(reference_runtime, proposals)
                self.assertEqual(cow_runtime.state.to_dict(), original.to_dict())
            else:
                reference_derived, reference_deltas = self._full_copy_commit(reference_runtime, proposals)
                self.assertEqual([item.to_dict() for item in derived], [item.to_dict() for item in reference_derived])
                self.assertEqual([item.to_dict() for item in deltas], [item.to_dict() for item in reference_deltas])
                self.assertEqual(cow_runtime.state.to_dict(), reference_runtime.state.to_dict())

    def test_engine_cow_matches_full_copy_commit_trace_and_nonconvergence(self):
        only_x = {"x": {"kind": "entity", "requires": ["state"]}}
        rules = [
            parse_law({"id": "event.relation", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}, "r": {"kind": "relation", "type": "link", "source": "$x", "target": "$y"}}, "when": {"event.type": {"eq": "root"}}, "effects": [{"op": "delta", "target": "$x.state.v", "value": 1}, {"op": "emit_event", "event": {"type": "derived"}}]}),
            law("event.aggregate", bindings=only_x, effects=[{"op": "delta", "target": "$x.state.v", "value": 2}]),
            law("state.first", mode="state", bindings=only_x, when={"ref": "$x.state.v", "eq": 3}, effects=[{"op": "set", "target": "$x.state.a", "value": 1}]),
            law("state.second", mode="state", bindings=only_x, when={"ref": "$x.state.a", "eq": 1}, effects=[{"op": "set", "target": "$x.state.b", "value": 1}]),
            law("state.third", mode="state", bindings=only_x, when={"ref": "$x.state.b", "eq": 1}, effects=[{"op": "add_tag", "target": "$x", "value": "done"}]),
            law("state.noop", mode="state", bindings=only_x, when={"ref": "$x.state.b", "eq": 1}, effects=[{"op": "set", "target": "$x.state.b", "value": 1}]),
            law("derived.hit", bindings=only_x, when={"event.type": {"eq": "derived"}}, effects=[{"op": "set", "target": "$x.state.derived", "value": True}]),
        ]
        subject = WorldState(entities={"x": Entity("x", components={"state": {"v": 0, "a": 0, "b": 0, "derived": False}}), "y": Entity("y")}, relations={"r": Relation("r", "link", "x", "y")})
        cow = Engine(rules).attach(deepcopy(subject))
        reference = Engine(rules).attach(deepcopy(subject))
        self._install_full_copy_commit(reference)
        cow_result = cow.run_event(Event("root", "root")); reference_result = reference.run_event(Event("root", "root"))
        self.assertEqual(cow.state.to_dict(), reference.state.to_dict())
        self.assertEqual(cow_result.trace.to_dict(), reference_result.trace.to_dict())

        conflict_rules = [law("conflict.left", effects=[{"op": "set", "target": "$x.state.v", "value": 1}]), law("conflict.right", effects=[{"op": "delta", "target": "$x.state.v", "value": 1}])]
        cow_conflict = Engine(conflict_rules).attach(world(state={"v": 0}))
        reference_conflict = Engine(conflict_rules).attach(world(state={"v": 0})); self._install_full_copy_commit(reference_conflict)
        with self.assertRaises(ProposalConflictError): cow_conflict.run_event(Event("root", "root"))
        with self.assertRaises(ProposalConflictError): reference_conflict.run_event(Event("root", "root"))
        self.assertEqual(cow_conflict.state.to_dict(), reference_conflict.state.to_dict())

        oscillating = [law("up", mode="state", when={"ref": "$x.state.flag", "eq": 0}, effects=[{"op": "set", "target": "$x.state.flag", "value": 1}]), law("down", mode="state", when={"ref": "$x.state.flag", "eq": 1}, effects=[{"op": "set", "target": "$x.state.flag", "value": 0}])]
        cow = Engine(oscillating, max_settle_iterations=3).attach(world(state={"flag": 0}))
        reference = Engine(oscillating, max_settle_iterations=3).attach(world(state={"flag": 0})); self._install_full_copy_commit(reference)
        with self.assertRaises(NonConvergentWorldError) as cow_error:
            cow.run_event(Event("root", "root"))
        with self.assertRaises(NonConvergentWorldError) as reference_error:
            reference.run_event(Event("root", "root"))
        self.assertEqual(cow.state.to_dict(), reference.state.to_dict())
        self.assertEqual(cow_error.exception.trace.to_dict(), reference_error.exception.trace.to_dict())

    def test_production_commit_has_no_full_world_deepcopy(self):
        source = (Path(__file__).parents[1] / "src" / "pmw" / "engine.py").read_text()
        self.assertNotIn("deepcopy(world)", source)
        self.assertNotIn("deepcopy(runtime.state)", source)

    def test_ten_touch_clones_at_most_ten_objects(self):
        entities = {f"e{i}": Entity(f"e{i}", components={"state": {"v": 0}}) for i in range(10)}
        rules = [law(f"touch.{i}", bindings={"x": {"kind": "entity"}}, when={"all": [{"event.type": {"eq": "root"}}, {"ref": "$x.id", "eq": f"e{i}"}]}, effects=[{"op": "delta", "target": "$x.state.v", "value": 1}]) for i in range(10)]
        runtime = Engine(rules).attach(WorldState(entities=entities)); runtime.run_event(Event("root", "root"))
        self.assertLessEqual(runtime.stats.objects_cloned, 10); self.assertLessEqual(runtime.stats.objects_swapped, 10)

    def _load_world(self, raw):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"; path.write_text(json.dumps(raw))
            return load_world(path)

    def _load_laws(self, raw):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "laws.json"; path.write_text(json.dumps(raw))
            return load_laws(path)

    @staticmethod
    def _full_copy_commit(runtime, proposals):
        candidate = deepcopy(runtime.state)
        candidate_runtime = runtime.engine.attach(candidate, validate=False)
        derived, deltas = Engine._commit(runtime.engine, candidate_runtime, proposals)
        runtime.state = candidate
        runtime.revision += bool(deltas); runtime.object_revision += bool(deltas)
        if deltas: runtime.invalidate_index()
        return derived, deltas

    def _install_full_copy_commit(self, runtime):
        runtime.engine._commit = lambda active_runtime, proposals: self._full_copy_commit(active_runtime, proposals)


    def test_scheduler_step_dispatches_one_root(self):
        runtime = Engine([]).attach(WorldState()); runtime.schedule(Event("a", "go", time=2)); dispatch = runtime.step()
        self.assertEqual((dispatch.event_id, dispatch.time, dispatch.tick), ("a", 2, 1)); self.assertEqual((runtime.state.sim_time, runtime.state.tick), (2, 1))

    def test_scheduler_rejects_past_event(self):
        from pmw.runtime import TemporalOrderError
        runtime = Engine([]).attach(WorldState(sim_time=2));
        with self.assertRaises(TemporalOrderError): runtime.schedule(Event("past", "go", time=1))

    def test_scheduler_rejects_duplicate_pending_id(self):
        from pmw.runtime import DuplicateScheduledEventError
        runtime = Engine([]).attach(WorldState()); runtime.schedule(Event("same", "go", time=1))
        with self.assertRaises(DuplicateScheduledEventError): runtime.schedule(Event("same", "other", time=2))

    def test_scheduler_same_time_order_is_time_then_id(self):
        runtime = Engine([]).attach(WorldState())
        for event_id in ("e3", "e1", "e2"): runtime.schedule(Event(event_id, "go", time=5))
        self.assertEqual(runtime.advance_to(5).processed_event_ids, ["e1", "e2", "e3"])

    def test_scheduler_advance_to_is_inclusive(self):
        runtime = Engine([]).attach(WorldState()); runtime.schedule(Event("at", "go", time=3)); result = runtime.advance_to(3)
        self.assertEqual(result.processed_event_ids, ["at"]); self.assertEqual(runtime.state.sim_time, 3)

    def test_scheduler_advance_by(self):
        runtime = Engine([]).attach(WorldState(sim_time=2)); runtime.schedule(Event("at", "go", time=4)); result = runtime.advance_by(2)
        self.assertEqual((result.end_time, result.processed_event_ids), (4, ["at"]))

    def test_scheduler_time_only_advance_does_not_evaluate_world(self):
        runtime = Engine([]).attach(WorldState(entities={f"e{i}": Entity(f"e{i}") for i in range(100)})); runtime.advance_to(7)
        self.assertEqual((runtime.stats.evaluation_views, runtime.stats.runtime_index_builds, runtime.stats.scheduled_dispatches), (0, 0, 0)); self.assertEqual(runtime.state.sim_time, 7)

    def test_scheduler_future_derived_event_is_persisted_then_dispatched(self):
        emit = parse_law({"id": "emit", "bindings": {"x": {"kind": "entity"}}, "when": {"event.type": {"eq": "a"}}, "effects": [{"op": "emit_event", "event": {"type": "b", "time": 5}}]})
        hit = law("hit", when={"event.type": {"eq": "b"}}, effects=[{"op": "set", "target": "$x.state.hit", "value": 1}])
        runtime = Engine([emit, hit]).attach(world(state={"hit": 0})); runtime.schedule(Event("A", "a", time=1)); first = runtime.advance_to(1)
        self.assertEqual((first.dispatches[0].result.processed_event_ids, first.dispatches[0].result.scheduled_event_ids), (["A"], ["derived:A:000001"])); self.assertEqual(runtime.state.entities["x"].components["state"]["hit"], 0)
        runtime.advance_to(5); self.assertEqual(runtime.state.entities["x"].components["state"]["hit"], 1)

    def test_scheduler_same_time_derived_stays_in_causal_chain(self):
        emit = parse_law({"id": "emit", "bindings": {"x": {"kind": "entity"}}, "when": {"event.type": {"eq": "a"}}, "effects": [{"op": "emit_event", "event": {"type": "b", "time": 5}}]})
        runtime = Engine([emit]).attach(world(state={})); runtime.schedule(Event("C", "c", time=5)); runtime.schedule(Event("A", "a", time=5)); result = runtime.advance_to(5)
        self.assertEqual(result.processed_event_ids, ["A", "C"]); self.assertEqual(result.dispatches[0].result.processed_event_ids, ["A", "derived:A:000001"])

    def test_scheduler_dynamic_future_event_due_in_same_advance(self):
        emit = parse_law({"id": "emit", "bindings": {"x": {"kind": "entity"}}, "when": {"event.type": {"eq": "a"}}, "effects": [{"op": "emit_event", "event": {"type": "b", "time": 3}}]})
        runtime = Engine([emit]).attach(world(state={})); runtime.schedule(Event("A", "a", time=1)); self.assertEqual(runtime.advance_to(5).processed_event_ids, ["A", "derived:A:000001"])

    def test_scheduler_limit_leaves_next_event_pending(self):
        from pmw.runtime import SchedulerLimitError
        runtime = Engine([], max_scheduler_dispatches_per_advance=1).attach(WorldState()); runtime.schedule(Event("a", "go", time=1)); runtime.schedule(Event("b", "go", time=2))
        with self.assertRaises(SchedulerLimitError): runtime.advance_to(3)
        self.assertEqual(runtime.peek_next_time(), 2); self.assertEqual(runtime.state.tick, 1)

    def test_scheduler_consumes_root_when_root_execution_fails(self):
        bad = law("bad", effects=[{"op": "delta", "target": "$x.state.missing", "value": 1}]); runtime = Engine([bad]).attach(world(state={"ok": 0})); runtime.schedule(Event("bad", "go", time=1))
        runtime.state.scheduled_events[0].type = "root"
        with self.assertRaises(ValueError): runtime.step()
        self.assertEqual((runtime.state.scheduled_events, runtime.state.tick), ([], 1))

    def test_scheduler_save_reload_replay(self):
        left = Engine([]).attach(WorldState(scheduled_events=[Event("a", "go", time=2), Event("b", "go", time=5)])); direct = left.advance_to(10)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"; right = Engine([]).attach(WorldState(scheduled_events=[Event("a", "go", time=2), Event("b", "go", time=5)])); first = right.advance_to(3); save_world(path, right.state); resumed = Engine([]).attach(load_world(path)); second = resumed.advance_to(10)
        self.assertEqual(direct.processed_event_ids, first.processed_event_ids + second.processed_event_ids); self.assertEqual(left.state.to_dict(), resumed.state.to_dict())

    def test_scheduler_staged_advance_equivalence(self):
        events = [Event("a", "go", time=2), Event("b", "go", time=5)]
        one = Engine([]).attach(WorldState(scheduled_events=deepcopy(events))); staged = Engine([]).attach(WorldState(scheduled_events=deepcopy(events)))
        self.assertEqual(one.advance_to(10).processed_event_ids, staged.advance_to(2).processed_event_ids + staged.advance_to(5).processed_event_ids + staged.advance_to(10).processed_event_ids); self.assertEqual(one.state.to_dict(), staged.state.to_dict())

    def test_scheduler_keeps_runtime_index_across_time_mutations(self):
        rule = law("indexed", bindings={"x": {"kind": "entity", "requires": ["state"]}}, effects=[]); runtime = Engine([rule]).attach(world(state={}))
        runtime.run_event(Event("r", "root")); before = runtime.stats.runtime_index_builds
        for index in range(3): runtime.schedule(Event(f"e{index}", "none", time=index + 1))
        runtime.advance_to(3); runtime.run_event(Event("r2", "root")); self.assertEqual(runtime.stats.runtime_index_builds, before)

    def test_revalidate_invalidates_scheduler_cache(self):
        runtime = Engine([]).attach(WorldState()); runtime.peek_next_time(); self.assertIsNotNone(runtime._scheduler); runtime.revalidate(); self.assertIsNone(runtime._scheduler)

    def test_scheduler_payload_must_be_finite_json(self):
        from pmw.validation import EventValidationError
        runtime = Engine([]).attach(WorldState())
        with self.assertRaises(EventValidationError): runtime.schedule(Event("bad", "go", time=1, payload={"bad": float("nan")}))

    def test_immediate_run_event_does_not_change_scheduler_clock(self):
        runtime = Engine([]).attach(WorldState(sim_time=4, tick=3)); runtime.run_event(Event("now", "go", time=99)); self.assertEqual((runtime.state.sim_time, runtime.state.tick), (4, 3))

    def test_scheduled_events_canonicalize_in_public_snapshot(self):
        runtime = Engine([]).attach(WorldState(scheduled_events=[Event("z", "go", time=2), Event("a", "go", time=1)])); self.assertEqual([event.id for event in runtime.snapshot().scheduled_events], ["a", "z"])

    def test_scheduler_external_provenance_becomes_scheduled(self):
        source = Event("a", "go", time=1); runtime = Engine([]).attach(WorldState()); runtime.schedule(source)
        self.assertEqual(source.provenance["kind"], "external"); self.assertEqual(runtime.state.scheduled_events[0].provenance["kind"], "scheduled")

    def test_scheduler_pending_world_cannot_contain_past_event(self):
        with self.assertRaises(WorldValidationError): Engine([]).attach(WorldState(sim_time=2, scheduled_events=[Event("old", "go", time=1)]))

    def test_scheduler_queue_is_lazy(self):
        runtime = Engine([]).attach(WorldState()); self.assertEqual(runtime.stats.scheduler_queue_builds, 0); runtime.schedule(Event("a", "go", time=1)); self.assertEqual(runtime.stats.scheduler_queue_builds, 1)

    def test_scheduler_peek_returns_none_when_empty(self):
        self.assertIsNone(Engine([]).attach(WorldState()).peek_next_time())

    def test_lifecycle_create_entity_and_exact_lookup(self):
        rule=parse_law({"id":"c","bindings":{},"when":{"event.type":{"eq":"go"}},"effects":[{"op":"create_entity","value":{"id":"y","components":{"state":{"v":1}}}}]}); runtime=Engine([rule]).attach(WorldState()); runtime.run_event(Event("go","go")); self.assertEqual(runtime.state.entities["y"].components["state"]["v"],1)

    def test_lifecycle_create_relation_requires_existing_endpoints(self):
        rule=parse_law({"id":"c","bindings":{},"when":{"event.type":{"eq":"go"}},"effects":[{"op":"create_relation","value":{"id":"r","type":"link","source":"a","target":"b"}}]}); runtime=Engine([rule]).attach(WorldState(entities={"a":Entity("a")}));
        with self.assertRaises(ValueError): runtime.run_event(Event("go","go"))
        self.assertNotIn("r",runtime.state.relations)

    def test_lifecycle_create_entities_then_relation_same_transaction(self):
        rule=parse_law({"id":"c","bindings":{},"when":{"event.type":{"eq":"go"}},"effects":[{"op":"create_entity","value":{"id":"a"}},{"op":"create_entity","value":{"id":"b"}},{"op":"create_relation","value":{"id":"r","type":"link","source":"a","target":"b"}}]}); runtime=Engine([rule]).attach(WorldState()); runtime.run_event(Event("go","go")); self.assertIn("r",runtime.state.relations)

    def test_lifecycle_delete_entity_requires_explicit_relation_delete(self):
        delete=parse_law({"id":"d","bindings":{"x":{"kind":"entity"}},"when":{"ref":"$x.id","eq":"x"},"effects":[{"op":"delete_entity","target":"$x"}]}); runtime=Engine([delete]).attach(WorldState(entities={"x":Entity("x"),"a":Entity("a")},relations={"r":Relation("r","link","a","x")}));
        with self.assertRaises(ValueError): runtime.run_event(Event("go","go"))
        self.assertIn("x",runtime.state.entities)

    def test_lifecycle_state_create_is_rejected(self):
        with self.assertRaises(LawValidationError): parse_law({"id":"bad","mode":"state","effects":[{"op":"create_entity","value":{"id":"x"}}]})

    def test_lifecycle_snapshot_isolation(self):
        rule=parse_law({"id":"c","bindings":{"x":{"kind":"entity"}},"when":{"ref":"$x.id","eq":"x"},"effects":[{"op":"delete_entity","target":"$x"},{"op":"create_entity","value":{"id":"y"}}]}); runtime=Engine([rule]).attach(WorldState(entities={"x":Entity("x")})); snapshot=runtime.snapshot(); runtime.run_event(Event("go","go")); self.assertIn("x",snapshot.entities); self.assertNotIn("y",snapshot.entities); self.assertIn("y",runtime.state.entities)

    def test_lifecycle_relation_topology_index_patches_without_rebuild(self):
        rule=parse_law({"id":"c","bindings":{},"when":{"event.type":{"eq":"go"}},"effects":[{"op":"create_relation","value":{"id":"r","type":"link","source":"a","target":"b"}}]}); runtime=Engine([rule]).attach(WorldState(entities={"a":Entity("a"),"b":Entity("b")})); index=runtime.get_index(); before=runtime.stats.runtime_index_builds; runtime.run_event(Event("go","go")); self.assertIn("r",index.relations_by_type["link"]); self.assertEqual(runtime.stats.runtime_index_builds,before)

    def test_lifecycle_delete_relation_then_entity_is_atomic(self):
        rule=parse_law({"id":"d","bindings":{"x":{"kind":"entity"},"r":{"kind":"relation"}},"when":{"all":[{"ref":"$x.id","eq":"x"},{"ref":"$r.id","eq":"r"}]},"effects":[{"op":"delete_relation","target":"$r"},{"op":"delete_entity","target":"$x"}]}); runtime=Engine([rule]).attach(WorldState(entities={"x":Entity("x"),"a":Entity("a")},relations={"r":Relation("r","link","a","x")})); runtime.run_event(Event("go","go")); self.assertNotIn("x",runtime.state.entities); self.assertNotIn("r",runtime.state.relations)

    def test_lifecycle_namespace_collision_rejected(self):
        rule=parse_law({"id":"c","bindings":{},"when":{"event.type":{"eq":"go"}},"effects":[{"op":"create_relation","value":{"id":"x","type":"link","source":"a","target":"b"}}]}); runtime=Engine([rule]).attach(WorldState(entities={"x":Entity("x"),"a":Entity("a"),"b":Entity("b")}));
        with self.assertRaises(ProposalConflictError): runtime.run_event(Event("go","go"))

    def test_lifecycle_state_law_can_delete_bound_entity(self):
        state=parse_law({"id":"d","mode":"state","bindings":{"x":{"kind":"entity","requires":["state"]}},"when":{"ref":"$x.state.dead","eq":True},"effects":[{"op":"delete_entity","target":"$x"}]}); runtime=Engine([state]).attach(WorldState(entities={"x":Entity("x",components={"state":{"dead":True}})})); runtime.settle(); self.assertNotIn("x",runtime.state.entities)

    def test_lifecycle_immediate_derived_observes_created_entity(self):
        create=parse_law({"id":"a","bindings":{},"when":{"event.type":{"eq":"a"}},"effects":[{"op":"create_entity","value":{"id":"y","components":{"state":{"v":0}}}},{"op":"emit_event","event":{"type":"b"}}]}); hit=parse_law({"id":"b","bindings":{"x":{"kind":"entity"}},"when":{"all":[{"event.type":{"eq":"b"}},{"ref":"$x.id","eq":"y"}]},"effects":[{"op":"set","target":"$x.state.v","value":1}]}); runtime=Engine([create,hit]).attach(WorldState()); runtime.run_event(Event("A","a")); self.assertEqual(runtime.state.entities["y"].components["state"]["v"],1)

    def test_future_duplicate_rejects_before_cow_state_publish(self):
        from pmw.runtime import DuplicateScheduledEventError
        rule = parse_law({"id": "future", "bindings": {"x": {"kind": "entity"}}, "when": {"event.type": {"eq": "a"}}, "effects": [{"op": "set", "target": "$x.state.v", "value": 1}, {"op": "emit_event", "event": {"type": "later", "time": 10}}]})
        runtime = Engine([rule]).attach(world(state={"v": 0})); runtime.schedule(Event("derived:A:000001", "later", time=20)); old = runtime.state.entities["x"]; revision, object_revision, pending = runtime.revision, runtime.object_revision, list(runtime.state.scheduled_events)
        with self.assertRaises(DuplicateScheduledEventError): runtime.run_event(Event("A", "a", time=1))
        self.assertEqual(runtime.state.entities["x"].components["state"]["v"], 0); self.assertIs(runtime.state.entities["x"], old); self.assertEqual((runtime.revision, runtime.object_revision), (revision, object_revision)); self.assertEqual(runtime.state.scheduled_events, pending)

    def test_failed_future_component_creation_preserves_index_coherence(self):
        from pmw.runtime import DuplicateScheduledEventError
        rule = parse_law({"id": "future", "bindings": {"x": {"kind": "entity"}}, "when": {"event.type": {"eq": "a"}}, "effects": [{"op": "set", "target": "$x.thermal.temperature", "value": 100}, {"op": "emit_event", "event": {"type": "later", "time": 10}}]})
        runtime = Engine([rule]).attach(world(state={})); index = runtime.get_index(); runtime.schedule(Event("derived:A:000001", "later", time=20))
        with self.assertRaises(DuplicateScheduledEventError): runtime.run_event(Event("A", "a", time=1))
        self.assertNotIn("thermal", runtime.state.entities["x"].components); self.assertNotIn("x", index.entities_by_component["thermal"]); self.assertEqual(runtime._index_revision, runtime.object_revision); self.assertIs(runtime.get_index(), index)

    def test_failed_direct_schedule_is_atomic_and_queue_remains_usable(self):
        from pmw.runtime import DuplicateScheduledEventError
        runtime = Engine([]).attach(WorldState()); runtime.schedule(Event("a", "go", time=1)); before, revision = list(runtime.state.scheduled_events), runtime.revision
        with self.assertRaises(DuplicateScheduledEventError): runtime.schedule(Event("a", "go", time=2))
        self.assertEqual((runtime.state.scheduled_events, runtime.revision, runtime.peek_next_time()), (before, revision, 1))

    def test_warm_schedule_uses_single_queue_membership_check(self):
        runtime = Engine([]).attach(WorldState(scheduled_events=[Event(f"e{i}", "go", time=10) for i in range(1000)])); runtime.peek_next_time(); before_builds, before_checks = runtime.stats.scheduler_queue_builds, runtime.stats.scheduler_membership_checks
        runtime.schedule(Event("new", "go", time=11))
        self.assertEqual((runtime.stats.scheduler_queue_builds, runtime.stats.scheduler_membership_checks - before_checks), (before_builds, 1))

    def test_batch_preflight_detects_internal_duplicate_without_world_mutation(self):
        from pmw.runtime import DuplicateScheduledEventError
        runtime = Engine([]).attach(WorldState()); before = runtime.revision
        with self.assertRaises(DuplicateScheduledEventError): runtime.prepare_schedule_batch([Event("same", "go", time=1), Event("same", "go", time=2)])
        self.assertEqual((runtime.state.scheduled_events, runtime.revision), ([], before))

    def test_future_batch_preflight_checks_only_batch_membership(self):
        runtime = Engine([]).attach(WorldState(scheduled_events=[Event(f"e{i}", "go", time=20) for i in range(1000)])); runtime.peek_next_time(); before = runtime.stats.scheduler_membership_checks
        batch = runtime.prepare_schedule_batch([Event("x", "go", time=10), Event("y", "go", time=11)])
        self.assertEqual(runtime.stats.scheduler_membership_checks - before, 2); runtime.commit_schedule_batch(batch); self.assertEqual(len(runtime.state.scheduled_events), 1002)

    def test_failed_future_preflight_keeps_scheduler_positions_consistent(self):
        from pmw.runtime import DuplicateScheduledEventError
        runtime = Engine([]).attach(WorldState(scheduled_events=[Event("taken", "go", time=2)])); runtime.peek_next_time()
        with self.assertRaises(DuplicateScheduledEventError): runtime.prepare_schedule_batch([Event("taken", "go", time=3)])
        self.assertTrue(runtime._scheduler.contains("taken")); self.assertEqual(runtime.step().event_id, "taken")


if __name__ == "__main__":
    unittest.main()
