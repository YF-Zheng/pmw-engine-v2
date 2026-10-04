from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Entity:
    id: str
    archetype: str = ""
    name: str | None = None
    tags: set[str] = field(default_factory=set)
    components: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"id": self.id, "tags": sorted(self.tags), "components": self.components}
        if self.archetype:
            result["archetype"] = self.archetype
        if self.name:
            result["name"] = self.name
        return result


@dataclass(slots=True)
class Relation:
    id: str
    type: str
    source: str
    target: str
    tags: set[str] = field(default_factory=set)
    components: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "source": self.source, "target": self.target, "tags": sorted(self.tags), "components": self.components}


@dataclass(slots=True)
class Event:
    id: str
    type: str
    time: float = 0.0
    source: str | None = None
    target: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=lambda: {"kind": "external", "parent_event": None})

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "time": self.time, "source": self.source, "target": self.target, "payload": self.payload, "provenance": self.provenance}


@dataclass(frozen=True, slots=True)
class StateAddress:
    kind: str
    object_id: str
    path: tuple[str, ...] = ()

    def __str__(self) -> str:
        suffix = "/".join(self.path)
        return f"{self.kind}:{self.object_id}" + (f"/{suffix}" if suffix else "")


@dataclass(slots=True)
class EffectProposal:
    proposal_id: str
    law_id: str
    priority: int
    op: str
    target: StateAddress | None = None
    value: Any = None
    event: Event | None = None
    source_proposal_ids: tuple[str, ...] = ()
    source_law_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def causes(self) -> tuple[str, ...]:
        return self.source_proposal_ids or (self.proposal_id,)

    @property
    def source_laws(self) -> tuple[str, ...]:
        return self.source_law_ids or (self.law_id,)


@dataclass(slots=True)
class StateDelta:
    address: StateAddress
    old_value: Any
    new_value: Any
    proposal_ids: tuple[str, ...]
    law_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"address": str(self.address), "old": self.old_value, "new": self.new_value, "proposal_ids": list(self.proposal_ids), "law_ids": list(self.law_ids)}


@dataclass(slots=True)
class LawMatchTrace:
    law_id: str
    mode: str
    bindings: dict[str, str]
    proposal_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"law_id": self.law_id, "mode": self.mode, "bindings": self.bindings, "proposal_ids": self.proposal_ids}


@dataclass(slots=True)
class ProposalTrace:
    proposal_id: str
    law_id: str
    op: str
    target: str | None
    status: str = "pending"
    reason: str | None = None
    value: Any = None
    cause_event_id: str | None = None
    source_proposal_ids: tuple[str, ...] = ()
    source_law_ids: tuple[str, ...] = ()
    emitted_event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"proposal_id": self.proposal_id, "law_id": self.law_id, "op": self.op, "target": self.target, "status": self.status, "reason": self.reason, "value": self.value, "cause_event_id": self.cause_event_id, "source_proposal_ids": list(self.source_proposal_ids), "source_law_ids": list(self.source_law_ids), "emitted_event_id": self.emitted_event_id}


@dataclass(slots=True)
class CommitTrace:
    microstep: int
    phase: str
    accepted_proposal_ids: list[str]
    rejected_proposal_ids: list[str]
    state_deltas: list[StateDelta]
    derived_event_ids: list[str]
    scheduled_event_ids: list[str] = field(default_factory=list)
    cancelled_event_ids: list[str] = field(default_factory=list)
    rescheduled_events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"microstep": self.microstep, "phase": self.phase, "accepted_proposal_ids": self.accepted_proposal_ids, "rejected_proposal_ids": self.rejected_proposal_ids, "state_deltas": [delta.to_dict() for delta in self.state_deltas], "derived_event_ids": self.derived_event_ids, "scheduled_event_ids": sorted(self.scheduled_event_ids), "cancelled_event_ids": sorted(self.cancelled_event_ids), "rescheduled_events": sorted(self.rescheduled_events, key=lambda item: item["id"])}


@dataclass(slots=True)
class EventTrace:
    event: Event
    event_law_matches: list[LawMatchTrace] = field(default_factory=list)
    state_law_matches: list[LawMatchTrace] = field(default_factory=list)
    commits: list[CommitTrace] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"event": self.event.to_dict(), "event_law_matches": [item.to_dict() for item in self.event_law_matches], "state_law_matches": [item.to_dict() for item in self.state_law_matches], "commits": [item.to_dict() for item in self.commits]}


@dataclass(slots=True)
class CausalTrace:
    root_event: Event
    events: list[EventTrace] = field(default_factory=list)
    proposals: list[ProposalTrace] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"root_event": self.root_event.to_dict(), "events": [item.to_dict() for item in self.events], "proposals": [item.to_dict() for item in self.proposals], "conflicts": self.conflicts}

    def semantic_projection(self) -> dict[str, Any]:
        """Backend-independent causal effects, excluding redundant no-op matches."""
        events = []
        for event in self.events:
            commits = []
            for commit in event.commits:
                if not (commit.state_deltas or commit.derived_event_ids or commit.scheduled_event_ids or commit.cancelled_event_ids or commit.rescheduled_events or commit.rejected_proposal_ids): continue
                deltas = [{"address": str(delta.address), "old": delta.old_value, "new": delta.new_value, "law_ids": list(delta.law_ids)} for delta in commit.state_deltas]
                commits.append({"state_deltas": deltas, "derived_event_ids": commit.derived_event_ids, "scheduled_event_ids": sorted(commit.scheduled_event_ids), "cancelled_event_ids": sorted(commit.cancelled_event_ids), "rescheduled_events": sorted(commit.rescheduled_events, key=lambda item: item["id"]), "conflict": bool(commit.rejected_proposal_ids)})
            if commits: events.append({"event": event.event.to_dict(), "commits": commits})
        return {"root_event": self.root_event.to_dict(), "events": events, "conflicts": self.conflicts}


@dataclass(slots=True)
class WorldState:
    world_id: str = "world"
    tick: int = 0
    sim_time: float = 0.0
    entities: dict[str, Entity] = field(default_factory=dict)
    relations: dict[str, Relation] = field(default_factory=dict)
    scheduled_events: list[Event] = field(default_factory=list)
    rng_state: dict[str, Any] = field(default_factory=dict)

    def get_object(self, kind: str, object_id: str) -> Entity | Relation | None:
        return (self.entities if kind == "entity" else self.relations if kind == "relation" else {}).get(object_id)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": "2.0", "world_id": self.world_id, "time": {"tick": self.tick, "sim_time": self.sim_time}, "rng": self.rng_state, "entities": [self.entities[key].to_dict() for key in sorted(self.entities)], "relations": [self.relations[key].to_dict() for key in sorted(self.relations)], "scheduled_events": [event.to_dict() for event in sorted(self.scheduled_events, key=lambda item: (item.time, item.id))]}
