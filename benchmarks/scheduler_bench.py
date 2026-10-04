"""Deterministic scheduler structural benchmarks. Run with PYTHONPATH=src python3 benchmarks/scheduler_bench.py."""

from time import perf_counter

from pmw import Engine, Entity, Event, WorldState, parse_law


def timed(call):
    started = perf_counter(); result = call(); return perf_counter() - started, result


def no_due():
    runtime = Engine([]).attach(WorldState(entities={f"e{i}": Entity(f"e{i}") for i in range(100_000)}))
    seconds, _ = timed(lambda: runtime.advance_to(100))
    print(f"NO_DUE        N=100000 time={seconds:.6f}s index_builds={runtime.stats.runtime_index_builds} views={runtime.stats.evaluation_views} dispatches={runtime.stats.scheduled_dispatches}")


def same_time():
    for size in (1_000, 5_000, 10_000, 50_000):
        runtime = Engine([], max_scheduler_dispatches_per_advance=size + 1).attach(WorldState())
        push, _ = timed(lambda: [runtime.schedule(Event(f"e{index:05d}", "noop", time=5)) for index in range(size, 0, -1)])
        dispatch, result = timed(lambda: runtime.advance_to(5))
        print(f"SAME_TIME_PUSH N={size} push_seconds={push:.6f}s queue_builds={runtime.stats.scheduler_queue_builds} pushes={runtime.stats.scheduled_pushes}")
        print(f"SAME_TIME_DISPATCH N={size} dispatch_seconds={dispatch:.6f}s dispatches={len(result.dispatches)} ordered={result.processed_event_ids == sorted(result.processed_event_ids)}")


def sparse():
    runtime = Engine([]).attach(WorldState())
    for index in range(10_000): runtime.schedule(Event(f"e{index:05d}", "noop", time=float(index)))
    seconds, result = timed(lambda: runtime.advance_to(10_000))
    print(f"SPARSE        N=10000 time={seconds:.6f}s dispatches={len(result.dispatches)} pops={runtime.stats.scheduled_pops}")


def future_chain():
    emit = parse_law({"id": "chain", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"event.type": {"eq": "chain"}}, {"ref": "$event.time", "lt": 1000}]}, "effects": [{"op": "emit_event", "event": {"type": "chain", "time": {"add": ["$event.time", 1]}}}]})
    runtime = Engine([emit], max_scheduler_dispatches_per_advance=2_000).attach(WorldState(entities={"x": Entity("x")})); runtime.schedule(Event("root", "chain", time=1))
    seconds, result = timed(lambda: runtime.advance_to(1000))
    print(f"FUTURE_CHAIN  N=1000 time={seconds:.6f}s dispatches={len(result.dispatches)} dynamic_queue=yes")


def large_pending():
    events = [Event(f"e{i:06d}", "noop", time=float(i)) for i in range(100_000)]
    runtime = Engine([]).attach(WorldState(scheduled_events=events))
    cold, next_time = timed(runtime.peek_next_time); step, _ = timed(runtime.step)
    print(f"LARGE_PENDING N=100000 cold={cold:.6f}s peek={next_time} step={step:.6f}s builds={runtime.stats.scheduler_queue_builds} pops={runtime.stats.scheduled_pops}")


def warm_single_push():
    for size in (10_000, 50_000, 100_000):
        runtime = Engine([]).attach(WorldState(scheduled_events=[Event(f"e{i:06d}", "noop", time=20) for i in range(size)])); runtime.peek_next_time()
        seconds, _ = timed(lambda: runtime.schedule(Event("new", "noop", time=21)))
        print(f"WARM_SINGLE_PUSH N={size} time={seconds:.6f}s queue_builds={runtime.stats.scheduler_queue_builds} membership_checks={runtime.stats.scheduler_membership_checks}")


def batch_future():
    for size in (10, 100, 1000):
        effects = [{"op": "emit_event", "event": {"type": "later", "time": 10}} for _ in range(size)]
        rule = parse_law({"id": "batch", "bindings": {"x": {"kind": "entity"}}, "when": {"event.type": {"eq": "root"}}, "effects": effects})
        pending = [Event(f"p{i:06d}", "noop", time=20) for i in range(100_000)]
        runtime = Engine([rule]).attach(WorldState(entities={"x": Entity("x")}, scheduled_events=pending)); runtime.peek_next_time(); before = runtime.stats.scheduler_membership_checks
        seconds, result = timed(lambda: runtime.run_event(Event("root", "root")))
        print(f"BATCH_FUTURE pending=100000 batch={size} time={seconds:.6f}s scheduled={len(result.scheduled_event_ids)} membership_checks={runtime.stats.scheduler_membership_checks - before}")


if __name__ == "__main__":
    no_due(); same_time(); sparse(); future_chain(); large_pending(); warm_single_push(); batch_future()
