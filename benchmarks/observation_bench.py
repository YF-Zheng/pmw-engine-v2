"""PMW v2.8 observation projection benchmarks.

Run with: PYTHONPATH=src python3 benchmarks/observation_bench.py
"""

import json
from time import perf_counter

from pmw import Engine, Entity, Relation, WorldState, parse_observation_rule


def rule(identifier, subject, reveal=None, bindings=None):
    return parse_observation_rule({"id": identifier, "bindings": bindings or {},
        "when": {"all": []}, "subject": subject, "reveal": reveal or {}})


SELF = rule("self", "$observer", {"core": ["name"], "components": ["profile.label"]})
LOCAL = rule("local", "$subject", {"core": ["name"], "components": ["profile.label"]}, {
    "subject": {"kind": "entity"},
    "visibility": {"kind": "relation", "type": "visible_to", "source": "$observer", "target": "$subject"},
})


def measure(label, runtime, observer="e0", repeats=1, **fields):
    before_rows = runtime.stats.observation_candidate_rows
    before_builds = runtime.stats.runtime_index_builds
    before_paths = runtime.stats.observation_component_paths_copied
    start = perf_counter()
    observation = None
    for _ in range(repeats): observation = runtime.observe(observer)
    seconds = perf_counter() - start
    raw = observation.to_dict()
    values = " ".join(f"{key}={value}" for key, value in fields.items())
    print(
        f"{label} world={len(runtime.state.entities)} relations={len(runtime.state.relations)} "
        f"repeats={repeats} time={seconds:.6f}s matches={len(raw['entities']) + len(raw['relations'])} "
        f"candidate_rows={runtime.stats.observation_candidate_rows - before_rows} "
        f"component_paths={runtime.stats.observation_component_paths_copied - before_paths} "
        f"index_build_delta={runtime.stats.runtime_index_builds - before_builds} "
        f"output_bytes={len(json.dumps(raw, separators=(',', ':')))} {values}"
    )


def entities(count, *, profiles=False):
    return {f"e{i}": Entity(f"e{i}", name=f"Entity {i}", components={"profile": {"label": i}} if profiles else {}) for i in range(count)}


def self_only():
    for count in (100_000, 500_000):
        runtime = Engine([], observation_rules=[SELF]).attach(WorldState(entities=entities(count, profiles=True)))
        measure("SELF_ONLY", runtime, repeats=3)


def local_world(count, degree, noise_relations=0):
    world_entities = entities(count, profiles=True)
    relations = {f"visible:{i}": Relation(f"visible:{i}", "visible_to", "e0", f"e{i + 1}") for i in range(degree)}
    for i in range(noise_relations):
        source = f"e{1 + (i % (count - 1))}"
        target = f"e{1 + ((i + 1) % (count - 1))}"
        relations[f"noise:{i}"] = Relation(f"noise:{i}", "visible_to", source, target)
    runtime = Engine([], observation_rules=[LOCAL]).attach(WorldState(entities=world_entities, relations=relations))
    runtime.get_index()
    return runtime


def local_relation():
    for degree in (1, 10, 100, 1000):
        runtime = local_world(100_000, degree, noise_relations=100_000)
        measure("LOCAL_RELATION", runtime, degree=degree, repeats=3)


def field_redaction():
    hidden = {f"secret_{i}": "x" * 100 for i in range(10_000)}
    entity = Entity("e0", name="Observer", components={"profile": {"label": "public", "color": "red"}, "hidden": hidden, "health": {"hp": 8, "private": "diagnosis"}})
    disclosure = rule("tiny", "$observer", {"components": ["profile.label", "profile.color", "health.hp"]})
    runtime = Engine([], observation_rules=[disclosure]).attach(WorldState(entities={"e0": entity}))
    measure("FIELD_REDACTION", runtime, hidden_bytes=len(json.dumps(hidden)), repeats=100)


def many_observers():
    count, degree = 1000, 10
    world_entities = {f"o{i}": Entity(f"o{i}") for i in range(count)}
    world_entities.update({f"s{i}:{j}": Entity(f"s{i}:{j}", name=f"Subject {i}:{j}") for i in range(count) for j in range(degree)})
    relations = {f"v{i}:{j}": Relation(f"v{i}:{j}", "visible_to", f"o{i}", f"s{i}:{j}") for i in range(count) for j in range(degree)}
    runtime = Engine([], observation_rules=[LOCAL]).attach(WorldState(entities=world_entities, relations=relations)); runtime.get_index()
    start = perf_counter(); before = runtime.stats.observation_candidate_rows
    for i in range(count): runtime.observe(f"o{i}")
    print(f"MANY_OBSERVERS world={len(world_entities)} relations={len(relations)} observers={count} degree={degree} time={perf_counter()-start:.6f}s candidate_rows={runtime.stats.observation_candidate_rows-before} index_build_delta=0")


def fixed_degree_world_scale():
    for count in (1_000, 10_000, 100_000, 500_000):
        runtime = local_world(count, 10)
        measure("FIXED_DEGREE_WORLD_SCALE", runtime, degree=10, repeats=10)


if __name__ == "__main__":
    self_only()
    local_relation()
    field_redaction()
    many_observers()
    fixed_degree_world_scale()
