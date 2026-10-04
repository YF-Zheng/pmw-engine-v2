from copy import deepcopy
from time import perf_counter

from pmw import Engine, Entity, Event, WorldState
from pmw.matching import WorldIndex
from pmw.validation import validate_runtime_world


def elapsed(fn):
    start = perf_counter(); fn(); return perf_counter() - start


def main():
    for size in (1000, 5000, 10000):
        world = WorldState(entities={f"e{i}": Entity(f"e{i}") for i in range(size)})
        validation = elapsed(lambda: validate_runtime_world(world))
        snapshot = elapsed(lambda: deepcopy(world))
        index = elapsed(lambda: WorldIndex(world))
        empty_engine = elapsed(lambda: Engine([]).run_event(world, Event("noop", "noop")))
        print(f"N={size} validation={validation:.6f}s snapshot_deepcopy={snapshot:.6f}s index={index:.6f}s empty_run={empty_engine:.6f}s matching=0 resolve_commit=0 trace=baseline")


if __name__ == "__main__":
    main()
