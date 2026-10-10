"""Cold/warm locality evidence for fixed v0.6 participants."""

from __future__ import annotations

from dataclasses import asdict
from time import perf_counter
from typing import Iterable

from pmw import Engine, Entity, parse_law
from pmw.matching.matcher import MatchStats, match_law

from ..dynamics.tick_protocol import advance_dynamics_step
from ..worlds import build_thermal_world


class MatcherProbe:
    def __init__(self):
        self.stats = MatchStats()

    def __call__(self, law, world, event, **kwargs):
        supplied = kwargs.pop("stats", None)
        local = supplied or MatchStats()
        before = asdict(local)
        result = match_law(law, world, event, stats=local, **kwargs)
        after = asdict(local)
        for key in after:
            setattr(self.stats, key, getattr(self.stats, key) + after[key] - before[key])
        return result


def measure(size: int) -> dict:
    world, laws, _ = build_thermal_world()
    world.entities.update({
        f"unrelated_{index:06d}": Entity(f"unrelated_{index:06d}", "noise", components={"unrelated": {"value": index}})
        for index in range(size)
    })
    probe = MatcherProbe()
    engine = Engine([parse_law(item) for item in laws], _matcher_backend=probe)
    started = perf_counter()
    runtime = engine.attach(world)
    runtime.get_index()
    cold_seconds = perf_counter() - started
    probe.stats = MatchStats()
    runtime.stats.runtime_index_builds = 0
    runtime.stats.state_full_scans = 0
    runtime.stats.lifecycle_global_scans = 0
    started = perf_counter()
    advance_dynamics_step(runtime)
    warm_seconds = perf_counter() - started
    return {
        "unrelated_objects": size,
        "cold_seconds": cold_seconds,
        "warm_tick_seconds": warm_seconds,
        "candidate_rows": probe.stats.candidate_rows_examined,
        "partial_bindings": probe.stats.partial_bindings_created,
        "complete_bindings": probe.stats.complete_bindings,
        "index_builds": runtime.stats.runtime_index_builds,
        "state_full_scans": runtime.stats.state_full_scans,
        "lifecycle_global_scans": runtime.stats.lifecycle_global_scans,
    }


def run(sizes: Iterable[int] = (1_000, 10_000, 100_000)) -> list[dict]:
    return [measure(size) for size in sizes]


if __name__ == "__main__":
    import json
    print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
