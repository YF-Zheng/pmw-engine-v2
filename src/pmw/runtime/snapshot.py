from dataclasses import dataclass
from types import MappingProxyType

from ..types import WorldState


@dataclass(frozen=True, slots=True)
class WorldSnapshot:
    world_id: str
    tick: int
    sim_time: float
    entities: object
    relations: object
    scheduled_events: tuple
    rng_state: object
    revision: int

    @classmethod
    def from_runtime(cls, runtime):
        runtime.stats.snapshot_count += 1
        runtime.stats.public_snapshots += 1
        runtime.stats.snapshot_mapping_copies += 2
        state = runtime.state
        return cls(state.world_id, state.tick, state.sim_time, MappingProxyType(dict(state.entities)), MappingProxyType(dict(state.relations)), tuple(sorted(state.scheduled_events, key=lambda item: (item.time, item.id))), MappingProxyType(dict(state.rng_state)), runtime.revision)

    def get_object(self, kind, object_id):
        return (self.entities if kind == "entity" else self.relations if kind == "relation" else {}).get(object_id)


@dataclass(frozen=True, slots=True)
class WorldReadView:
    """Internal, phase-local live mapping view. It is not a persistent snapshot."""
    world_id: str
    tick: int
    sim_time: float
    entities: object
    relations: object
    scheduled_events: object
    rng_state: object
    revision: int

    @classmethod
    def from_runtime(cls, runtime):
        runtime.stats.evaluation_views += 1
        state = runtime.state
        return cls(state.world_id, state.tick, state.sim_time, state.entities, state.relations, state.scheduled_events, state.rng_state, runtime.revision)

    def get_object(self, kind, object_id):
        return (self.entities if kind == "entity" else self.relations if kind == "relation" else {}).get(object_id)
