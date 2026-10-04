"""PMW v2.6 lifecycle structural benchmarks.

Run with: PYTHONPATH=src python3 benchmarks/lifecycle_bench.py
"""

from time import perf_counter

from pmw import EffectProposal, Engine, Entity, Event, Relation, WorldState, parse_law
from pmw.types import StateAddress


WORLD_SIZE = 100_000


def elapsed(call):
    start = perf_counter()
    call()
    return perf_counter() - start


def metric(name, runtime, seconds, **fields):
    values = " ".join(f"{key}={value}" for key, value in fields.items())
    print(
        f"{name} world={len(runtime.state.entities)} time={seconds:.6f}s {values} "
        f"builds={runtime.stats.runtime_index_builds} "
        f"patches={runtime.stats.topology_index_patches} "
        f"topology_adds={runtime.stats.relation_topology_posting_adds} "
        f"topology_removes={runtime.stats.relation_topology_posting_removes}"
    )


def entities():
    return {f"e{i}": Entity(f"e{i}") for i in range(WORLD_SIZE)}


def create_rule(kind, count):
    if kind == "entity":
        effects = [{"op": "create_entity", "value": {"id": f"new{i}", "components": {"state": {"v": i}}}} for i in range(count)]
    else:
        effects = [{"op": "create_relation", "value": {"id": f"new-r{i}", "type": "link", "source": "e0", "target": "e1", "components": {"state": {"v": i}}}} for i in range(count)]
    return parse_law({"id": f"create-{kind}", "bindings": {}, "when": {"event.type": {"eq": "go"}}, "effects": effects})


def create_entity_cases():
    for count in (1, 10, 1000):
        runtime = Engine([create_rule("entity", count)]).attach(WorldState(entities=entities()))
        runtime.get_index()
        builds = runtime.stats.runtime_index_builds
        seconds = elapsed(lambda: runtime.run_event(Event("root", "go")))
        metric("CREATE_ENTITY", runtime, seconds, count=count, warm_build_delta=runtime.stats.runtime_index_builds - builds, component_adds=runtime.stats.entity_component_posting_adds)


def create_relation_cases():
    for count in (1, 10, 1000):
        runtime = Engine([create_rule("relation", count)]).attach(WorldState(entities=entities()))
        runtime.get_index()
        builds = runtime.stats.runtime_index_builds
        seconds = elapsed(lambda: runtime.run_event(Event("root", "go")))
        metric("CREATE_RELATION", runtime, seconds, count=count, warm_build_delta=runtime.stats.runtime_index_builds - builds)


def delete_relation_cases():
    for count in (1, 10, 1000):
        relations = {f"r{i}": Relation(f"r{i}", "link", "e0", "e1") for i in range(count)}
        rule = parse_law({"id": "delete", "bindings": {"r": {"kind": "relation", "type": "link"}}, "when": {"event.type": {"eq": "go"}}, "effects": [{"op": "delete_relation", "target": "$r"}]})
        runtime = Engine([rule]).attach(WorldState(entities=entities(), relations=relations))
        runtime.get_index()
        builds = runtime.stats.runtime_index_builds
        seconds = elapsed(lambda: runtime.run_event(Event("root", "go")))
        metric("DELETE_RELATION", runtime, seconds, count=count, warm_build_delta=runtime.stats.runtime_index_builds - builds)


def delete_isolated_cases():
    rule = parse_law({"id": "delete", "bindings": {"x": {"kind": "entity"}}, "when": {"all": [{"event.type": {"eq": "go"}}, {"ref": "$x.id", "eq": "$event.target"}]}, "effects": [{"op": "delete_entity", "target": "$x"}]})
    for temperature in ("cold", "warm"):
        runtime = Engine([rule]).attach(WorldState(entities=entities()))
        if temperature == "warm": runtime.get_index()
        builds = runtime.stats.runtime_index_builds
        seconds = elapsed(lambda: runtime.run_event(Event("root", "go", target="e99999")))
        metric("DELETE_ENTITY_ISOLATED", runtime, seconds, cache=temperature, build_delta=runtime.stats.runtime_index_builds - builds)


def lifecycle_proposal(serial, op, kind, object_id, value=None):
    return EffectProposal(f"p{serial:06d}", "bench", 0, op, StateAddress(kind, object_id), value)


def delete_incident_cases():
    for degree in (1, 4, 16):
        relations = {f"r{i}": Relation(f"r{i}", "link", "e0", f"e{i + 1}") for i in range(degree)}
        runtime = Engine([]).attach(WorldState(entities=entities(), relations=relations))
        runtime.get_index()
        proposals = [lifecycle_proposal(i, "delete_relation", "relation", f"r{i}") for i in range(degree)]
        proposals.append(lifecycle_proposal(degree, "delete_entity", "entity", "e0"))
        accepted = runtime.engine._resolve(proposals).accepted
        builds = runtime.stats.runtime_index_builds
        seconds = elapsed(lambda: runtime.engine._commit(runtime, accepted))
        metric("DELETE_ENTITY_WITH_RELATIONS", runtime, seconds, degree=degree, build_delta=runtime.stats.runtime_index_builds - builds)


def topology_churn():
    count = 10_000
    runtime = Engine([]).attach(WorldState(entities=entities()))
    runtime.get_index()
    builds = runtime.stats.runtime_index_builds
    creates = [lifecycle_proposal(i, "create_relation", "relation", f"r{i}", {"id": f"r{i}", "type": "link", "source": "e0", "target": "e1"}) for i in range(count)]
    deletes = [lifecycle_proposal(count + i, "delete_relation", "relation", f"r{i}") for i in range(count)]
    seconds = elapsed(lambda: runtime.engine._commit(runtime, runtime.engine._resolve(creates).accepted))
    seconds += elapsed(lambda: runtime.engine._commit(runtime, runtime.engine._resolve(deletes).accepted))
    metric("TOPOLOGY_CHURN", runtime, seconds, relations=count, mutations=count * 2, build_delta=runtime.stats.runtime_index_builds - builds)


if __name__ == "__main__":
    create_entity_cases()
    create_relation_cases()
    delete_relation_cases()
    delete_isolated_cases()
    delete_incident_cases()
    topology_churn()
