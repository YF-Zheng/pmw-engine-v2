"""Profile 100 status expirations in a 100k-entity world."""

import cProfile
import pstats

from pmw import Engine, Entity, Event, Relation, WorldState, parse_law


def main():
    count = 100
    entities = {f"entity:{index}": Entity(f"entity:{index}") for index in range(100_000)}
    entities["hero"] = Entity("hero")
    relations = {f"status:{index}": Relation(f"status:{index}", "status", "hero", "hero") for index in range(count)}
    events = [Event(f"expire:{index}", "expire", time=10, payload={"status_id": f"status:{index}"}) for index in range(count)]
    expire = parse_law({
        "id": "expire",
        "bindings": {"status": {"kind": "relation", "type": "status"}},
        "when": {"all": [
            {"event.type": {"eq": "expire"}},
            {"ref": "$status.id", "eq": "$event.payload.status_id"},
        ]},
        "effects": [{"op": "delete_relation", "target": "$status"}],
    })
    runtime = Engine([expire]).attach(WorldState(entities=entities, relations=relations, scheduled_events=events))

    profiler = cProfile.Profile()
    profiler.enable()
    runtime.advance_to(10)
    profiler.disable()
    pstats.Stats(profiler).strip_dirs().sort_stats("cumulative").print_stats(20)
    print(
        "STRUCTURE",
        f"membership={runtime.stats.lifecycle_id_membership_checks}",
        f"endpoints={runtime.stats.lifecycle_endpoint_checks}",
        f"incident={runtime.stats.lifecycle_incident_relation_checks}",
        f"global_scans={runtime.stats.lifecycle_global_scans}",
        f"index_builds={runtime.stats.runtime_index_builds}",
    )


if __name__ == "__main__":
    main()
