"""Incremental state-closure benchmarks. Run with PYTHONPATH=src python3 benchmarks/state_closure_bench.py."""

from time import perf_counter

from pmw import Engine, Entity, Event, Relation, WorldState, parse_law


SIZE = 100_000


def timed(call):
    started = perf_counter(); call(); return perf_counter() - started


def state_rule(law_id, when, effects, bindings=None):
    return parse_law({"id": law_id, "mode": "state", "bindings": bindings or {"x": {"kind": "entity", "requires": ["state"]}}, "when": when, "effects": effects})


def print_result(label, seconds, runtime, before, size=SIZE):
    stats = runtime.stats
    print(
        f"{label:15} N={size} time={seconds:.6f}s "
        f"full_scans={stats.state_full_scans - before[0]} incremental_rounds={stats.state_incremental_rounds - before[1]} "
        f"activations={stats.state_activations - before[2]} dirty={stats.dirty_deltas_processed - before[3]} "
        f"seeded_calls={stats.seeded_match_calls - before[4]} seeded_rows={stats.seeded_candidate_rows - before[5]} "
        f"global_matches={stats.global_fallback_matches - before[6]} index_builds={stats.runtime_index_builds - before[7]} "
        f"index_reuses={stats.runtime_index_reuses - before[8]} index_patches={stats.runtime_index_patches - before[9]}"
    )


def baseline(runtime):
    s = runtime.stats
    return (s.state_full_scans, s.state_incremental_rounds, s.state_activations, s.dirty_deltas_processed, s.seeded_match_calls, s.seeded_candidate_rows, s.global_fallback_matches, s.runtime_index_builds, s.runtime_index_reuses, s.runtime_index_patches)


def local_chain():
    entities = {"e0": Entity("e0", components={"state": {"a": 0, "b": 0, "c": 0, "d": 0}})}
    entities.update({f"e{i}": Entity(f"e{i}") for i in range(1, SIZE)})
    event = parse_law({"id": "event.local", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.a", "value": 1}]})
    laws = [event, state_rule("state.a", {"ref": "$x.state.a", "eq": 1}, [{"op": "set", "target": "$x.state.b", "value": 1}]), state_rule("state.b", {"ref": "$x.state.b", "eq": 1}, [{"op": "set", "target": "$x.state.c", "value": 1}]), state_rule("state.c", {"ref": "$x.state.c", "eq": 1}, [{"op": "set", "target": "$x.state.d", "value": 1}])]
    runtime = Engine(laws).attach(WorldState(entities=entities)); runtime.settle(); before = baseline(runtime)
    print_result("LOCAL_CHAIN", timed(lambda: runtime.run_event(Event("local", "go", target="e0"))), runtime, before)


def local_relation():
    entities = {"e0": Entity("e0", components={"thermal": {"t": 0}})}
    entities.update({f"e{i}": Entity(f"e{i}", components={"state": {"hit": 0}}) for i in range(1, SIZE)})
    relations = {f"r{i}": Relation(f"r{i}", "contact", "e0", f"e{i}") for i in range(1, 5)}
    event = parse_law({"id": "event.heat", "bindings": {"x": {"kind": "entity", "requires": ["thermal"]}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.thermal.t", "value": 1}]})
    contact = state_rule("state.contact", {"ref": "$x.thermal.t", "eq": 1}, [{"op": "set", "target": "$y.state.hit", "value": 1}], {"x": {"kind": "entity"}, "y": {"kind": "entity"}, "r": {"kind": "relation", "type": "contact", "source": "$x", "target": "$y"}})
    runtime = Engine([event, contact]).attach(WorldState(entities=entities, relations=relations)); runtime.settle(); before = baseline(runtime)
    print_result("LOCAL_RELATION", timed(lambda: runtime.run_event(Event("heat", "go", target="e0"))), runtime, before)


def ten_dirty():
    entities = {f"e{i}": Entity(f"e{i}", components={"state": {"a": 0, "b": 0}}) for i in range(SIZE)}
    events = [parse_law({"id": f"event.{i}", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"all": [{"ref": "$x.id", "eq": f"e{i}"}]}, "effects": [{"op": "set", "target": "$x.state.a", "value": 1}]}) for i in range(10)]
    settle = state_rule("state.ten", {"ref": "$x.state.a", "eq": 1}, [{"op": "set", "target": "$x.state.b", "value": 1}])
    runtime = Engine(events + [settle]).attach(WorldState(entities=entities)); runtime.settle(); before = baseline(runtime)
    print_result("TEN_DIRTY", timed(lambda: runtime.run_event(Event("ten", "go"))), runtime, before)


def global_fallback():
    size = 10_000
    entities = {f"e{i}": Entity(f"e{i}", components={"state": {"trigger": 0, "mark": 1}}) for i in range(size)}
    event = parse_law({"id": "event.reset", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.trigger", "value": 1}]})
    global_rule = state_rule("state.global", {"all": []}, [], {"x": {"kind": "entity"}})
    runtime = Engine([event, global_rule]).attach(WorldState(entities=entities)); runtime.settle(); before = baseline(runtime)
    print_result("GLOBAL_FALLBACK", timed(lambda: runtime.run_event(Event("global", "go", target="e0"))), runtime, before, size)


def value_dependency():
    entities = {"x": Entity("x", components={"state": {"trigger": 1, "out": 0}}), "y": Entity("y", components={"state": {"source": 0}})}
    entities.update({f"e{i}": Entity(f"e{i}") for i in range(2, SIZE)})
    event = parse_law({"id": "event.value", "bindings": {"y": {"kind": "entity"}}, "when": {"all": [{"ref": "$y.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$y.state.source", "value": 1}]})
    state = parse_law({"id": "state.value", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.state.trigger", "eq": 1}, {"ref": "$x.id", "eq": "x"}, {"ref": "$y.id", "eq": "y"}]}, "effects": [{"op": "set", "target": "$x.state.out", "value": "$y.state.source"}]})
    runtime = Engine([event, state]).attach(WorldState(entities=entities)); runtime.settle(); before = baseline(runtime)
    print_result("VALUE_DEPENDENCY", timed(lambda: runtime.run_event(Event("value", "go", target="y"))), runtime, before)


def target_restoration():
    entities = {"e0": Entity("e0", components={"state": {"enabled": 1, "out": 1}})}
    entities.update({f"e{i}": Entity(f"e{i}") for i in range(1, SIZE)})
    event = parse_law({"id": "event.break", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.out", "value": 0}]})
    state = state_rule("state.restore", {"all": [{"ref": "$x.state.enabled", "eq": 1}, {"ref": "$x.id", "eq": "e0"}]}, [{"op": "set", "target": "$x.state.out", "value": 1}], {"x": {"kind": "entity"}})
    runtime = Engine([event, state]).attach(WorldState(entities=entities)); runtime.settle(); before = baseline(runtime)
    print_result("TARGET_RESTORATION", timed(lambda: runtime.run_event(Event("break", "go", target="e0"))), runtime, before)


def long_chain():
    for length in (100, 500, 1000):
        entities = {f"e{i}": Entity(f"e{i}", components={"state": {"active": 0}}) for i in range(length + 1)}
        relations = {f"r{i}": Relation(f"r{i}", "link", f"e{i}", f"e{i + 1}") for i in range(length)}
        event = parse_law({"id": "event.start", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.active", "value": 1}]})
        spread = parse_law({"id": "state.spread", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}, "r": {"kind": "relation", "type": "link", "source": "$x", "target": "$y"}}, "when": {"all": [{"ref": "$x.state.active", "eq": 1}, {"ref": "$y.state.active", "eq": 0}]}, "effects": [{"op": "set", "target": "$y.state.active", "value": 1}]})
        runtime = Engine([event, spread], max_settle_iterations=length + 5).attach(WorldState(entities=entities, relations=relations)); runtime.settle(); before = baseline(runtime)
        results = []; seconds = timed(lambda: results.append(runtime.run_event(Event("start", "go", target="e0"))))
        result = results[0]
        stats = runtime.stats
        print(f"LONG_CHAIN      L={length} time={seconds:.6f}s rounds={stats.state_incremental_rounds - before[1]} activations={stats.state_activations - before[2]} seeded_calls={stats.seeded_match_calls - before[4]} seeded_rows={stats.seeded_candidate_rows - before[5]} proposals={len(result.trace.proposals)} index_builds={stats.runtime_index_builds - before[7]} index_reuses={stats.runtime_index_reuses - before[8]}")


def fixed_world_long_chain():
    for length in (10, 100, 500, 1000):
        entities = {f"e{i}": Entity(f"e{i}", components={"state": {"active": 0}}) for i in range(SIZE)}
        relations = {f"r{i}": Relation(f"r{i}", "link", f"e{i}", f"e{i + 1}") for i in range(length)}
        event = parse_law({"id": "event.start", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$x.state.active", "value": 1}]})
        spread = parse_law({"id": "state.spread", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}, "r": {"kind": "relation", "type": "link", "source": "$x", "target": "$y"}}, "when": {"all": [{"ref": "$x.state.active", "eq": 1}, {"ref": "$y.state.active", "eq": 0}]}, "effects": [{"op": "set", "target": "$y.state.active", "value": 1}]})
        runtime = Engine([event, spread], max_settle_iterations=length + 5).attach(WorldState(entities=entities, relations=relations)); runtime.settle(); before = baseline(runtime)
        seconds = timed(lambda: runtime.run_event(Event("start", "go", target="e0"))); stats = runtime.stats
        print(f"LONG_CHAIN_FIXED_WORLD N={SIZE} L={length} time={seconds:.6f}s rounds={stats.state_incremental_rounds - before[1]} index_builds={stats.runtime_index_builds - before[7]} index_reuses={stats.runtime_index_reuses - before[8]}")


def index_lifetime():
    entities = {f"e{i}": Entity(f"e{i}", components={"state": {}}) for i in range(SIZE)}
    rule = parse_law({"id": "indexed", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"event.type": {"eq": "probe"}}, "effects": []})
    runtime = Engine([rule]).attach(WorldState(entities=entities)); before = baseline(runtime)
    cold = timed(lambda: runtime.run_event(Event("cold", "probe"))); mid = baseline(runtime)
    warm = timed(lambda: runtime.run_event(Event("warm", "probe"))); stats = runtime.stats
    print(f"INDEX_COLD      N={SIZE} time={cold:.6f}s index_builds={mid[7] - before[7]} index_reuses={mid[8] - before[8]}")
    print(f"INDEX_WARM      N={SIZE} time={warm:.6f}s index_builds={stats.runtime_index_builds - mid[7]} index_reuses={stats.runtime_index_reuses - mid[8]}")


def dynamic_predicate():
    entities = {"x": Entity("x", tags={"hot"}, components={"state": {"hit": 0}}), "y": Entity("y", components={"state": {"tag_name": "cold"}})}
    entities.update({f"e{i}": Entity(f"e{i}") for i in range(2, SIZE)})
    event = parse_law({"id": "event.name", "bindings": {"y": {"kind": "entity"}}, "when": {"all": [{"ref": "$y.id", "eq": "$event.target"}]}, "effects": [{"op": "set", "target": "$y.state.tag_name", "value": "hot"}]})
    state = parse_law({"id": "state.predicate", "mode": "state", "bindings": {"x": {"kind": "entity"}, "y": {"kind": "entity"}}, "when": {"all": [{"has_tag": ["$x", "$y.state.tag_name"]}, {"ref": "$x.id", "eq": "x"}, {"ref": "$y.id", "eq": "y"}]}, "effects": [{"op": "set", "target": "$x.state.hit", "value": 1}]})
    runtime = Engine([event, state]).attach(WorldState(entities=entities)); runtime.settle(); before = baseline(runtime)
    print_result("DYNAMIC_PREDICATE", timed(lambda: runtime.run_event(Event("name", "go", target="y"))), runtime, before)


if __name__ == "__main__":
    local_chain(); local_relation(); ten_dirty(); global_fallback(); value_dependency(); target_restoration(); long_chain(); fixed_world_long_chain(); dynamic_predicate(); index_lifetime()
