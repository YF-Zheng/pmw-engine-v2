"""PMW v2.7 temporal-handle structural benchmarks."""

from copy import deepcopy
import gc
from random import Random
from time import perf_counter

from pmw import Engine, Entity, Event, Relation, WorldState, parse_law


PENDING = 100_000


def make_runtime():
    events = [Event(f"event:{index}", "noop", time=1000 + index) for index in range(PENDING)]
    runtime = Engine([]).attach(WorldState(scheduled_events=events))
    runtime.get_scheduler()
    return runtime


def cancel_warm(count):
    runtime = make_runtime(); rng = Random(27); ids = rng.sample(range(PENDING), count)
    start = perf_counter()
    for index in ids: runtime.cancel_scheduled(f"event:{index}")
    elapsed = perf_counter() - start; queue = runtime.get_scheduler()
    print(f"CANCEL_WARM pending={PENDING} ops={count} seconds={elapsed:.6f} stale={queue.stale_count} compactions={runtime.stats.scheduler_heap_compactions}")


def reschedule_warm(count):
    runtime = make_runtime(); rng = Random(28); ids = rng.sample(range(PENDING), count)
    start = perf_counter()
    for offset, index in enumerate(ids): runtime.reschedule_scheduled(f"event:{index}", 1_000_000 + offset)
    elapsed = perf_counter() - start; queue = runtime.get_scheduler()
    print(f"RESCHEDULE_WARM pending={PENDING} ops={count} seconds={elapsed:.6f} stale={queue.stale_count} compactions={runtime.stats.scheduler_heap_compactions}")


def churn(count=20_000):
    runtime = Engine([]).attach(WorldState()); start = perf_counter()
    runtime.schedule(Event("pulse", "pulse", time=1))
    for index in range(count): runtime.reschedule_scheduled("pulse", index + 2)
    runtime.cancel_scheduled("pulse"); runtime.schedule(Event("pulse", "reused", time=count + 3))
    elapsed = perf_counter() - start
    dispatch = runtime.advance_to(count + 3).processed_event_ids
    print(f"CHURN ops={count} seconds={elapsed:.6f} dispatch={dispatch} compactions={runtime.stats.scheduler_heap_compactions}")


def heap_compaction():
    runtime = Engine([]).attach(WorldState(scheduled_events=[Event("x", "noop", time=1)])); start = perf_counter()
    for index in range(10_000): runtime.reschedule_scheduled("x", 2 + index)
    elapsed = perf_counter() - start
    print(f"HEAP_COMPACTION ops=10000 seconds={elapsed:.6f} heap={len(runtime.get_scheduler().heap)} live=1 compactions={runtime.stats.scheduler_heap_compactions}")


def lifecycle_stats(runtime):
    return (
        f"membership={runtime.stats.lifecycle_id_membership_checks} "
        f"endpoints={runtime.stats.lifecycle_endpoint_checks} "
        f"incident={runtime.stats.lifecycle_incident_relation_checks} "
        f"global_scans={runtime.stats.lifecycle_global_scans} "
        f"index_builds={runtime.stats.runtime_index_builds}"
    )


def duration_status(count, entity_count=PENDING, label="DURATION_STATUS"):
    entities = {f"entity:{index}": Entity(f"entity:{index}") for index in range(entity_count)}
    entities["hero"] = Entity("hero")
    relations = {f"status:{index}": Relation(f"status:{index}", "status", "hero", "hero") for index in range(count)}
    events = [Event(f"expire:{index}", "expire", time=10, payload={"status_id": f"status:{index}"}) for index in range(count)]
    expire = parse_law({"id": "expire", "mode": "event", "bindings": {"s": {"kind": "relation", "type": "status"}}, "when": {"all": [{"event.type": {"eq": "expire"}}, {"ref": "$s.id", "eq": "$event.payload.status_id"}]}, "effects": [{"op": "delete_relation", "target": "$s"}]})
    runtime = Engine([expire]).attach(WorldState(entities=entities, relations=relations, scheduled_events=events)); start = perf_counter(); runtime.advance_to(10); elapsed = perf_counter() - start
    print(f"{label} unrelated={entity_count} active={count} seconds={elapsed:.6f} remaining={len(runtime.state.relations)} {lifecycle_stats(runtime)}")


def fixed_status_world_scale():
    for entity_count in (1_000, 10_000, 100_000, 500_000):
        duration_status(100, entity_count, "FIXED_STATUS_COUNT")
        gc.collect()


def many_small_vs_one_batch(count=1000):
    entities = {f"entity:{index}": Entity(f"entity:{index}") for index in range(PENDING)}
    entities["hero"] = Entity("hero")
    relations = {f"status:{index}": Relation(f"status:{index}", "status", "hero", "hero") for index in range(count)}
    events = [Event(f"expire:{index}", "expire", time=10, payload={"status_id": f"status:{index}"}) for index in range(count)]
    expire = parse_law({"id": "expire", "bindings": {"s": {"kind": "relation", "type": "status"}}, "when": {"all": [{"event.type": {"eq": "expire"}}, {"ref": "$s.id", "eq": "$event.payload.status_id"}]}, "effects": [{"op": "delete_relation", "target": "$s"}]})
    many = Engine([expire]).attach(WorldState(entities=deepcopy(entities), relations=deepcopy(relations), scheduled_events=events))
    start = perf_counter(); many.advance_to(10); elapsed = perf_counter() - start
    print(f"MANY_SMALL roots={count} seconds={elapsed:.6f} {lifecycle_stats(many)}")

    laws = [parse_law({"id": f"delete:{index}", "bindings": {"s": {"kind": "relation"}}, "when": {"all": [{"event.type": {"eq": "batch"}}, {"ref": "$s.id", "eq": f"status:{index}"}]}, "effects": [{"op": "delete_relation", "target": "$s"}]}) for index in range(count)]
    batch = Engine(laws).attach(WorldState(entities=entities, relations=relations))
    start = perf_counter(); batch.run_event(Event("batch", "batch")); elapsed = perf_counter() - start
    print(f"ONE_BATCH relations={count} seconds={elapsed:.6f} {lifecycle_stats(batch)}")


def recurring(count):
    apply = parse_law({"id": "apply", "mode": "event", "bindings": {"x": {"kind": "entity"}}, "when": {"event.type": {"eq": "pulse"}}, "effects": [{"op": "delta", "target": "$x.state.count", "value": 1}, {"op": "schedule_event", "event": {"id": "pulse", "type": "pulse", "time": {"add": ["$event.time", 1]}}}]})
    runtime = Engine([apply], max_scheduler_dispatches_per_advance=count + 1).attach(WorldState(entities={"x": Entity("x", components={"state": {"count": 0}})}, scheduled_events=[Event("pulse", "pulse", time=1)])); start = perf_counter(); runtime.advance_to(count); elapsed = perf_counter() - start
    print(f"RECURRING pulses={count} seconds={elapsed:.6f} queue={len(runtime.state.scheduled_events)} heap={len(runtime.get_scheduler().heap)}")


if __name__ == "__main__":
    for size in (1, 100, 10_000): cancel_warm(size)
    for size in (1, 100, 10_000): reschedule_warm(size)
    churn(); heap_compaction()
    for size in (1, 100, 1000, 5000): duration_status(size)
    fixed_status_world_scale()
    many_small_vs_one_batch()
    for size in (100, 1000, 10_000): recurring(size)
