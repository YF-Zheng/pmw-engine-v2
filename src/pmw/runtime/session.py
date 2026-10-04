from dataclasses import dataclass
from copy import deepcopy

import math

from ..validation import validate_event, validate_runtime_world
from .scheduler import AdvanceResult, DuplicateScheduledEventError, MissingScheduledEventError, PreparedSchedulerMutation, RuntimeScheduleQueue, SchedulerDispatchResult, SchedulerLimitError, TemporalOrderError, owned_scheduled_event
from .snapshot import WorldReadView, WorldSnapshot


@dataclass(slots=True)
class RuntimeStats:
    snapshot_count: int = 0
    snapshot_mapping_copies: int = 0
    objects_cloned: int = 0
    objects_swapped: int = 0
    full_world_deepcopies: int = 0
    full_world_validations: int = 0
    event_validations: int = 0
    transactions_prepared: int = 0
    transactions_committed: int = 0
    noop_transactions: int = 0
    local_objects_validated: int = 0
    state_full_scans: int = 0
    state_incremental_rounds: int = 0
    state_activations: int = 0
    state_activation_dedups: int = 0
    dirty_deltas_processed: int = 0
    seeded_match_calls: int = 0
    seeded_candidate_rows: int = 0
    global_fallback_matches: int = 0
    runtime_index_builds: int = 0
    runtime_index_reuses: int = 0
    runtime_index_patches: int = 0
    runtime_index_invalidations: int = 0
    entity_component_posting_adds: int = 0
    entity_component_posting_removes: int = 0
    relation_component_posting_adds: int = 0
    relation_component_posting_removes: int = 0
    evaluation_views: int = 0
    public_snapshots: int = 0
    scheduler_queue_builds: int = 0
    scheduler_queue_reuses: int = 0
    scheduled_pushes: int = 0
    scheduled_pops: int = 0
    scheduled_cancellations: int = 0
    scheduled_reschedules: int = 0
    scheduler_stale_entries_skipped: int = 0
    scheduler_heap_compactions: int = 0
    scheduler_cancel_membership_checks: int = 0
    scheduler_reschedule_membership_checks: int = 0
    scheduled_dispatches: int = 0
    scheduler_steps: int = 0
    time_advances: int = 0
    future_derived_scheduled: int = 0
    same_time_derived_immediate: int = 0
    scheduler_limit_failures: int = 0
    scheduler_membership_checks: int = 0
    scheduler_batch_preflights: int = 0
    entities_created: int = 0
    entities_deleted: int = 0
    relations_created: int = 0
    relations_deleted: int = 0
    lifecycle_transactions: int = 0
    lifecycle_preflight_failures: int = 0
    lifecycle_id_membership_checks: int = 0
    lifecycle_endpoint_checks: int = 0
    lifecycle_incident_relation_checks: int = 0
    lifecycle_global_scans: int = 0
    topology_index_patches: int = 0
    relation_topology_posting_adds: int = 0
    relation_topology_posting_removes: int = 0
    observation_calls: int = 0
    observation_rules_evaluated: int = 0
    observation_matches: int = 0
    observation_raw_grants: int = 0
    observation_deduplicated_grants: int = 0
    observation_entities_returned: int = 0
    observation_relations_returned: int = 0
    observation_component_paths_copied: int = 0
    observation_candidate_rows: int = 0


class WorldRuntime:
    def __init__(self, engine, state, validate=True):
        self.engine = engine; self.state = state; self.revision = 0; self.object_revision = 0; self.validated = True; self.stats = RuntimeStats(); self.state_closure_known = False; self._index = None; self._index_revision = None; self._scheduler = None; self._last_commit_scheduled_ids = []; self._last_commit_cancelled_ids = []; self._last_commit_reschedules = []; self._last_commit_future_derived_ids = []
        if validate: validate_runtime_world(state); self.stats.full_world_validations += 1

    def snapshot(self): return WorldSnapshot.from_runtime(self)

    def _read_view(self): return WorldReadView.from_runtime(self)

    def get_index(self):
        from ..matching.index import WorldIndex
        if self.engine._runtime_index_mode == "rebuild_each_view":
            self.stats.runtime_index_builds += 1
            return WorldIndex(self.state)
        if self._index is None or self._index_revision != self.object_revision:
            self._index = WorldIndex(self.state); self._index_revision = self.object_revision; self.stats.runtime_index_builds += 1
        else:
            self.stats.runtime_index_reuses += 1
        return self._index

    def invalidate_index(self):
        self._index = None; self._index_revision = None; self.stats.runtime_index_invalidations += 1

    def apply_index_patch(self, changes):
        if self._index is None: return
        # A cache that missed a revision is never patched forward speculatively.
        if self._index_revision != self.object_revision - 1:
            self.invalidate_index()
            return
        try:
            for kind, object_id, old_roots, new_roots in changes:
                postings = self._index.entities_by_component if kind == "entity" else self._index.relations_by_component
                for component in old_roots - new_roots:
                    postings[component].discard(object_id)
                    if kind == "entity": self.stats.entity_component_posting_removes += 1
                    else: self.stats.relation_component_posting_removes += 1
                for component in new_roots - old_roots:
                    postings[component].add(object_id)
                    if kind == "entity": self.stats.entity_component_posting_adds += 1
                    else: self.stats.relation_component_posting_adds += 1
            self._index_revision = self.object_revision; self.stats.runtime_index_patches += 1
        except Exception:
            self.invalidate_index()

    def revalidate(self):
        validate_runtime_world(self.state); self.stats.full_world_validations += 1; self.validated = True; self.revision += 1; self.object_revision += 1; self.state_closure_known = False; self.invalidate_index(); self.invalidate_scheduler()

    def run_event(self, event):
        return self.engine._run_runtime(self, event)

    def settle(self, force_full=False):
        return self.engine._settle_runtime(self, force_full=force_full)

    def observe(self, observer_id):
        from ..observation import observe_runtime
        return observe_runtime(self.engine, self, observer_id)

    def observer(self, observer_id):
        from ..observation import ObserverView
        # Validate eagerly so an invalid capability is never handed out.
        if not isinstance(observer_id, str) or not observer_id or observer_id not in self.state.entities:
            from ..observation import MissingObserverError
            raise MissingObserverError(f"missing observer entity '{observer_id}'")
        return ObserverView(self, observer_id)

    def get_scheduler(self):
        if self._scheduler is None:
            self._scheduler = RuntimeScheduleQueue(self.state.scheduled_events, mode=self.engine._scheduler_mode); self.stats.scheduler_queue_builds += 1
        else:
            self.stats.scheduler_queue_reuses += 1
        return self._scheduler

    def invalidate_scheduler(self):
        self._scheduler = None

    def prepare_scheduler_mutation(self, events=(), cancellations=(), reschedules=()):
        owned = tuple(owned_scheduled_event(event) for event in events)
        cancellations = tuple(sorted(set(cancellations)))
        requested = tuple(reschedules)
        if not owned and not cancellations and not requested: return PreparedSchedulerMutation()
        queue = self.get_scheduler(); self.stats.scheduler_batch_preflights += 1
        additions = set()
        for event in owned:
            validate_event(event.to_dict(), "Scheduler.schedule")
            if event.time < self.state.sim_time: raise TemporalOrderError("cannot schedule an event in logical time's past")
            self.stats.scheduler_membership_checks += 1
            if queue.contains(event.id) or event.id in additions: raise DuplicateScheduledEventError(f"duplicate pending scheduled event id '{event.id}'")
            additions.add(event.id)
        replacements = []
        for event_id, new_time in requested:
            self.stats.scheduler_reschedule_membership_checks += 1
            if not isinstance(new_time, (int, float)) or isinstance(new_time, bool) or not math.isfinite(new_time): raise TemporalOrderError("new_time must be finite")
            existing = queue.get(event_id, self.state.scheduled_events)
            if existing is None: raise MissingScheduledEventError(f"missing pending scheduled event id '{event_id}'")
            if existing.time == new_time: continue
            replacement = deepcopy(existing); replacement.time = new_time
            validate_event(replacement.to_dict(), "Scheduler.reschedule")
            if new_time < self.state.sim_time: raise TemporalOrderError("cannot reschedule an event in logical time's past")
            replacements.append((event_id, replacement, existing.time, new_time))
        effective_cancellations = []
        for event_id in cancellations:
            self.stats.scheduler_cancel_membership_checks += 1
            if queue.contains(event_id): effective_cancellations.append(event_id)
        return PreparedSchedulerMutation(owned, tuple(effective_cancellations), tuple(replacements))

    def prepare_schedule_batch(self, events):
        return self.prepare_scheduler_mutation(events=events)

    def commit_scheduler_mutation(self, batch, *, future=False):
        if not batch.changed: return False
        queue = self.get_scheduler()
        for event_id in batch.cancellations:
            queue.remove(event_id, self.state.scheduled_events, self.stats)
            self.stats.scheduled_cancellations += 1
        for event_id, replacement, _, _ in batch.reschedules:
            queue.replace(event_id, replacement, self.state.scheduled_events, self.stats)
            self.stats.scheduled_reschedules += 1
        for event in batch.additions:
            queue.push(event, self.state.scheduled_events, self.stats)
            self.stats.scheduled_pushes += 1
            if future is True or future and event.id in future: self.stats.future_derived_scheduled += 1
        self.revision += 1
        return True

    def commit_schedule_batch(self, batch, *, future=False):
        return self.commit_scheduler_mutation(batch, future=future)

    def schedule(self, event):
        self.commit_schedule_batch(self.prepare_schedule_batch([event]))

    def cancel_scheduled(self, event_id):
        if not isinstance(event_id, str) or not event_id: raise ValueError("event_id must be a non-empty string")
        prepared = self.prepare_scheduler_mutation(cancellations=(event_id,))
        return self.commit_scheduler_mutation(prepared)

    def reschedule_scheduled(self, event_id, new_time):
        if not isinstance(event_id, str) or not event_id: raise ValueError("event_id must be a non-empty string")
        if not isinstance(new_time, (int, float)) or isinstance(new_time, bool) or not math.isfinite(new_time): raise TemporalOrderError("new_time must be finite")
        prepared = self.prepare_scheduler_mutation(reschedules=((event_id, new_time),))
        return self.commit_scheduler_mutation(prepared)

    def peek_next_time(self):
        return self.get_scheduler().peek_time(self.stats)

    def step(self):
        queue = self.get_scheduler(); self.stats.scheduler_steps += 1
        if queue.peek_time(self.stats) is None: return None
        event = queue.pop(self.state.scheduled_events, self.stats); self.stats.scheduled_pops += 1
        self.state.sim_time = event.time; self.state.tick += 1; self.revision += 1; self.stats.scheduled_dispatches += 1
        result = self.engine._run_runtime(self, event)
        return SchedulerDispatchResult(event.id, event.time, self.state.tick, result)

    def advance_to(self, target_time):
        if not isinstance(target_time, (int, float)) or not math.isfinite(target_time): raise TemporalOrderError("target_time must be finite")
        if target_time < self.state.sim_time: raise TemporalOrderError("cannot move logical time backward")
        start_time, start_tick = self.state.sim_time, self.state.tick; result = AdvanceResult(start_time, float(target_time), start_tick, start_tick)
        while (next_time := self.peek_next_time()) is not None and next_time <= target_time:
            if len(result.dispatches) >= self.engine.max_scheduler_dispatches_per_advance:
                self.stats.scheduler_limit_failures += 1; raise SchedulerLimitError("scheduler dispatch limit exceeded")
            result.dispatches.append(self.step())
        if self.state.sim_time != float(target_time): self.state.sim_time = float(target_time); self.revision += 1; self.stats.time_advances += 1
        result.end_tick = self.state.tick
        return result

    def advance_by(self, delta):
        if not isinstance(delta, (int, float)) or not math.isfinite(delta) or delta < 0: raise TemporalOrderError("delta must be finite and non-negative")
        return self.advance_to(self.state.sim_time + delta)
