from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import heapq


class TemporalOrderError(ValueError):
    pass


class DuplicateScheduledEventError(ValueError):
    pass


class MissingScheduledEventError(ValueError):
    pass


class SchedulerLimitError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedSchedulerMutation:
    additions: tuple[object, ...] = ()
    cancellations: tuple[str, ...] = ()
    reschedules: tuple[tuple[str, object, float, float], ...] = ()

    @property
    def changed(self):
        return bool(self.additions or self.cancellations or self.reschedules)

    @property
    def events(self):
        return self.additions


# Backward-compatible name used by the v2.5 API.
PreparedScheduleBatch = PreparedSchedulerMutation


@dataclass(slots=True)
class SchedulerDispatchResult:
    event_id: str
    time: float
    tick: int
    result: object


@dataclass(slots=True)
class AdvanceResult:
    start_time: float
    end_time: float
    start_tick: int
    end_tick: int
    dispatches: list[SchedulerDispatchResult] = field(default_factory=list)

    @property
    def processed_event_ids(self):
        return [item.event_id for item in self.dispatches]


class RuntimeScheduleQueue:
    """Versioned lazy heap over the persisted scheduled_events list."""

    COMPACTION_SLACK = 1024

    def __init__(self, events, *, mode="versioned"):
        self.mode = mode
        self.positions = {event.id: index for index, event in enumerate(events)}
        if len(self.positions) != len(events):
            raise DuplicateScheduledEventError("duplicate pending scheduled event id")
        self.versions = {event.id: 1 for event in events}
        self.heap = [(event.time, event.id, 1) for event in events]
        heapq.heapify(self.heap)

    def _live(self, entry):
        _, event_id, version = entry
        return event_id in self.positions and self.versions.get(event_id) == version

    def _prune(self, stats=None):
        while self.heap and not self._live(self.heap[0]):
            heapq.heappop(self.heap)
            if stats is not None:
                stats.scheduler_stale_entries_skipped += 1

    def _compact_if_needed(self, events, stats=None, *, force=False):
        live = len(self.positions)
        if force or self.mode == "rebuild_each_operation" or len(self.heap) > 2 * live + self.COMPACTION_SLACK:
            self.heap = [(event.time, event.id, self.versions[event.id]) for event in events]
            heapq.heapify(self.heap)
            if stats is not None:
                stats.scheduler_heap_compactions += 1
            return True
        return False

    def peek_time(self, stats=None):
        self._prune(stats)
        return self.heap[0][0] if self.heap else None

    def contains(self, event_id):
        return event_id in self.positions

    def get(self, event_id, events):
        index = self.positions.get(event_id)
        return None if index is None else events[index]

    def push(self, event, events, stats=None):
        if event.id in self.positions:
            raise DuplicateScheduledEventError(f"duplicate pending scheduled event id '{event.id}'")
        version = self.versions.get(event.id, 0) + 1
        self.versions[event.id] = version
        self.positions[event.id] = len(events)
        events.append(event)
        heapq.heappush(self.heap, (event.time, event.id, version))
        self._compact_if_needed(events, stats)

    def _remove_at(self, event_id, events):
        index = self.positions.pop(event_id)
        event = events[index]
        last = events.pop()
        if index < len(events):
            events[index] = last
            self.positions[last.id] = index
        return event

    def remove(self, event_id, events, stats=None):
        if event_id not in self.positions:
            return None
        event = self._remove_at(event_id, events)
        self.versions[event_id] = self.versions.get(event_id, 0) + 1
        self._compact_if_needed(events, stats)
        return event

    def replace(self, event_id, replacement, events, stats=None):
        index = self.positions[event_id]
        events[index] = replacement
        version = self.versions.get(event_id, 0) + 1
        self.versions[event_id] = version
        heapq.heappush(self.heap, (replacement.time, event_id, version))
        self._compact_if_needed(events, stats)

    def pop(self, events, stats=None):
        self._prune(stats)
        _, event_id, _ = heapq.heappop(self.heap)
        return self._remove_at(event_id, events)

    @property
    def stale_count(self):
        return max(0, len(self.heap) - len(self.positions))

    def force_compact(self, events, stats=None):
        self._compact_if_needed(events, stats, force=True)


def owned_scheduled_event(event):
    copied = deepcopy(event)
    if copied.provenance == {"kind": "external", "parent_event": None}:
        copied.provenance = {"kind": "scheduled", "parent_event": None}
    return copied
