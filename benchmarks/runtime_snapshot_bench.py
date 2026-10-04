"""COW runtime benchmark. Run with: PYTHONPATH=src python3 benchmarks/runtime_snapshot_bench.py"""

from time import perf_counter

from pmw import Engine, Entity, Event, WorldState, parse_law
from pmw.matching import MatchStats, match_law


SIZES = (1_000, 5_000, 10_000, 50_000)


def timed(fn):
    start = perf_counter()
    fn()
    return perf_counter() - start


def base_world(size):
    return WorldState(entities={f"e{i}": Entity(f"e{i}", components={"state": {"v": 0, "a": 0, "b": 0}}) for i in range(size)})


def entity_rule(law_id, entity_id, effects, *, mode="event", when=None):
    return parse_law({
        "id": law_id,
        "mode": mode,
        "bindings": {"x": {"kind": "entity", "requires": ["state"]}},
        "when": when or {"all": [{"event.type": {"eq": "go"}}, {"ref": "$x.id", "eq": entity_id}]},
        "effects": effects,
    })


def report(label, size, engine, event=None, probe_laws=()):
    runtime = engine.attach(base_world(size))
    initial_revision = runtime.revision
    event = event or Event(f"{label}:{size}", "go")
    match_stats = MatchStats()
    for probe in probe_laws:
        stats = MatchStats(); match_law(probe, runtime.state, event, stats=stats)
        match_stats.candidate_rows_examined += stats.candidate_rows_examined
        match_stats.index_builds += stats.index_builds
        match_stats.exact_constraint_lookups += stats.exact_constraint_lookups
    seconds = timed(lambda: runtime.run_event(event))
    stats = runtime.stats
    print(
        f"{label:14} N={size:6} time={seconds:.6f}s "
        f"snapshots={stats.snapshot_count} map_copies={stats.snapshot_mapping_copies} "
        f"clones={stats.objects_cloned} swaps={stats.objects_swapped} "
        f"prepared={stats.transactions_prepared} committed={stats.transactions_committed} "
        f"noop={stats.noop_transactions} local_validated={stats.local_objects_validated} "
        f"revision_delta={runtime.revision - initial_revision} full_copy={stats.full_world_deepcopies} "
        f"full_validation={stats.full_world_validations} match_rows={match_stats.candidate_rows_examined} "
        f"match_indexes={match_stats.index_builds} exact_lookups={match_stats.exact_constraint_lookups}"
    )


def main():
    for size in SIZES:
        safe_world = base_world(size)
        safe_seconds = timed(lambda: Engine([]).run_event(safe_world, Event(f"safe:{size}", "go")))
        hot_runtime = Engine([]).attach(base_world(size))
        hot_seconds = timed(lambda: hot_runtime.run_event(Event(f"hot:{size}", "go")))
        print(f"NOOP_COMPARE   N={size:6} safe={safe_seconds:.6f}s hot={hot_seconds:.6f}s hot_snapshots={hot_runtime.stats.snapshot_count} hot_clones={hot_runtime.stats.objects_cloned} hot_swaps={hot_runtime.stats.objects_swapped}")
        report("NOOP", size, Engine([]))
        one = entity_rule("one.touch", "e0", [{"op": "delta", "target": "$x.state.v", "value": 1}])
        report("ONE_TOUCH", size, Engine([one]), probe_laws=[one])
        ten = [entity_rule(f"ten.touch.{i}", f"e{i}", [{"op": "delta", "target": "$x.state.v", "value": 1}]) for i in range(10)]
        report("TEN_TOUCH", size, Engine(ten), probe_laws=ten)
        noop = entity_rule("noop.proposal", "e0", [{"op": "set", "target": "$x.state.v", "value": 0}])
        report("NOOP_PROPOSAL", size, Engine([noop]), probe_laws=[noop])
        event = entity_rule("settle.event", "e0", [{"op": "set", "target": "$x.state.a", "value": 1}])
        first = entity_rule("settle.first", "e0", [{"op": "set", "target": "$x.state.b", "value": 1}], mode="state", when={"ref": "$x.state.a", "eq": 1})
        second = entity_rule("settle.second", "e0", [{"op": "set", "target": "$x.state.v", "value": 1}], mode="state", when={"ref": "$x.state.b", "eq": 1})
        report("STATE_SETTLE", size, Engine([event, first, second]), probe_laws=[event])
        targeted = parse_law({"id": "targeted.event", "bindings": {"x": {"kind": "entity", "requires": ["state"]}}, "when": {"all": [{"event.type": {"eq": "impact"}}, {"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "delta", "target": "$x.state.v", "value": 1}]})
        target_event = Event(f"targeted:{size}", "impact", target="e0")
        report("TARGETED_EVENT", size, Engine([targeted]), target_event, [targeted])


if __name__ == "__main__":
    main()
