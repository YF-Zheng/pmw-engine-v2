from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .dsl import Law, match_law, value
from .types import CausalTrace, CommitTrace, EffectProposal, Entity, Event, EventTrace, LawMatchTrace, ProposalTrace, Relation, StateAddress, StateDelta, WorldState
from .validation import validate_derived_event, validate_event, validate_laws, validate_runtime_entity, validate_runtime_relation, validate_runtime_world
from .matching.matcher import MatchContext, MatchStats, match_law as indexed_match
from .matching.plan import compile_match_plan
from .matching.state_dependency import StateDependencyIndex, compile_state_dependency_plan
from .observation import ObservationRule, parse_observation_rule
from .validation import validate_observation_rules


class ProposalConflictError(RuntimeError):
    """Raised when a transaction contains an intentionally unsupported conflict."""


class ObjectInUseError(ValueError):
    """Raised when deleting an entity would leave an incident relation."""


class DanglingRelationError(ValueError):
    """Raised when a relation endpoint is absent from the final transaction state."""


class NonConvergentWorldError(RuntimeError):
    def __init__(self, iterations: int, law_ids: list[str], addresses: list[str], trace: CausalTrace) -> None:
        super().__init__(f"State settling did not converge after {iterations} iterations; laws={law_ids}, targets={addresses}")
        self.iterations = iterations
        self.law_ids = law_ids
        self.addresses = addresses
        self.trace = trace


@dataclass(slots=True)
class EventResult:
    changed: bool = False
    triggered_law_ids: list[str] = field(default_factory=list)
    state_delta: list[StateDelta] = field(default_factory=list)
    processed_event_ids: list[str] = field(default_factory=list)
    scheduled_event_ids: list[str] = field(default_factory=list)
    cancelled_event_ids: list[str] = field(default_factory=list)
    rescheduled_event_ids: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    trace: CausalTrace | None = None


@dataclass(slots=True)
class _Resolution:
    accepted: list[EffectProposal]
    accepted_ids: list[str]
    rejected: dict[str, str]
    conflicts: list[str]


@dataclass(slots=True)
class PreparedWorldMutation:
    """A fully validated transaction ready for non-semantic publication."""

    replacements: dict[tuple[str, str], Any]
    created_entities: dict[str, Entity]
    created_relations: dict[str, Relation]
    deleted_objects: list[tuple[str, Any]]
    index_changes: list[tuple[str, str, set[str], set[str]]]
    prepared_schedule: Any
    immediate_events: list[Event]
    future_events: list[Event]
    deltas: list[StateDelta]
    lifecycle_action_count: int
    cancelled_event_ids: list[str]
    rescheduled_events: list[dict[str, Any]]
    future_derived_event_ids: list[str]


def _materialize_entity(raw: Any) -> Entity:
    if not isinstance(raw, dict) or set(raw) - {"id", "archetype", "name", "tags", "components"}:
        raise ValueError("create_entity value must be an entity object")
    tags = raw.get("tags", [])
    if not isinstance(raw.get("id"), str) or not raw["id"] or not isinstance(raw.get("archetype", ""), str) or raw.get("name") is not None and not isinstance(raw.get("name"), str):
        raise ValueError("invalid create_entity identity fields")
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags) or len(tags) != len(set(tags)):
        raise ValueError("create_entity tags must be unique strings")
    if not isinstance(raw.get("components", {}), dict): raise ValueError("create_entity components must be object")
    entity = Entity(raw["id"], raw.get("archetype", ""), raw.get("name"), set(tags), deepcopy(raw.get("components", {})))
    validate_runtime_entity(entity)
    return entity


def _materialize_relation(raw: Any) -> Relation:
    if not isinstance(raw, dict) or set(raw) - {"id", "type", "source", "target", "tags", "components"}:
        raise ValueError("create_relation value must be a relation object")
    tags = raw.get("tags", [])
    if any(not isinstance(raw.get(field), str) or not raw[field] for field in ("id", "type", "source", "target")):
        raise ValueError("invalid create_relation identity fields")
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags) or len(tags) != len(set(tags)):
        raise ValueError("create_relation tags must be unique strings")
    if not isinstance(raw.get("components", {}), dict): raise ValueError("create_relation components must be object")
    relation = Relation(raw["id"], raw["type"], raw["source"], raw["target"], set(tags), deepcopy(raw.get("components", {})))
    validate_runtime_relation(relation)
    return relation


class Engine:
    def __init__(self, laws: list[Law], max_cascade_events: int = 1000, max_settle_iterations: int = 100, max_scheduler_dispatches_per_advance: int = 10000, *, observation_rules: list[ObservationRule] | None = None, validate: bool = True, _matcher_backend=None, _observation_matcher_backend=None, _state_closure_backend="incremental", _runtime_index_mode="persistent", _scheduler_mode="versioned") -> None:
        if validate:
            validate_laws({"schema_version": "2.0", "laws": [{"id": law.law_id, "mode": law.mode, "priority": law.priority, "bindings": law.bindings, "when": law.when, "effects": list(law.effects)} for law in laws]}, "Engine")
        self.laws = sorted(laws, key=lambda law: law.law_id)
        self.event_laws = [law for law in self.laws if law.mode == "event"]
        self.state_laws = [law for law in self.laws if law.mode == "state"]
        self.match_plans = {law.law_id: compile_match_plan(law) for law in self.laws}
        observation_documents = [rule.to_dict() for rule in observation_rules or []]
        if validate:
            validate_observation_rules(
                {"schema_version": "2.0", "observation_rules": observation_documents},
                "Engine",
            )
        self.observation_rules = sorted(
            (parse_observation_rule(raw, validate=False) for raw in observation_documents),
            key=lambda rule: rule.rule_id,
        )
        self.observation_plans = {rule.rule_id: compile_match_plan(rule) for rule in self.observation_rules}
        self.state_dependency_index = StateDependencyIndex([compile_state_dependency_plan(law) for law in self.state_laws])
        self._matcher = _matcher_backend or indexed_match
        self._observation_matcher = _observation_matcher_backend or indexed_match
        self._state_closure_backend = _state_closure_backend
        self._runtime_index_mode = _runtime_index_mode
        self._scheduler_mode = _scheduler_mode
        self.max_cascade_events = max_cascade_events
        self.max_settle_iterations = max_settle_iterations
        self.max_scheduler_dispatches_per_advance = max_scheduler_dispatches_per_advance

    def attach(self, world: WorldState, *, validate: bool = True):
        from .runtime import WorldRuntime
        return WorldRuntime(self, world, validate=validate)

    def run_event(self, world: WorldState, event: Event) -> EventResult:
        return self.attach(world, validate=True).run_event(event)

    def _run_runtime(self, runtime, event: Event) -> EventResult:
        world = runtime.state
        validate_event(event.to_dict(), "Engine.run_event")
        runtime.stats.event_validations += 1
        trace = CausalTrace(root_event=deepcopy(event))
        result = EventResult(trace=trace)
        queue = [event]
        proposal_serial = 0
        event_serial = 0
        microstep = 0

        while queue:
            if len(result.processed_event_ids) >= self.max_cascade_events:
                raise RuntimeError("Event cascade exceeded max_cascade_events")
            current = queue.pop(0)
            result.processed_event_ids.append(current.id)
            event_trace = EventTrace(event=deepcopy(current))
            trace.events.append(event_trace)

            proposals, proposal_serial, event_serial = self._collect(
                "event", runtime, current, event.id, proposal_serial, event_serial, event_trace, trace,
            )
            resolution = self._resolve(proposals)
            microstep += 1
            runtime._last_commit_scheduled_ids = []
            runtime._last_commit_cancelled_ids = []
            runtime._last_commit_reschedules = []
            derived, deltas = self._commit(runtime, resolution.accepted)
            future_derived_ids = [item.event.id for item in resolution.accepted if item.op == "emit_event" and item.event.id in runtime._last_commit_scheduled_ids]
            self._record_commit(trace, event_trace, resolution, deltas, derived, runtime._last_commit_scheduled_ids, runtime._last_commit_cancelled_ids, runtime._last_commit_reschedules, future_derived_ids, microstep, "event")
            result.scheduled_event_ids.extend(runtime._last_commit_scheduled_ids)
            result.cancelled_event_ids.extend(runtime._last_commit_cancelled_ids)
            result.rescheduled_event_ids.extend(item["id"] for item in runtime._last_commit_reschedules)
            self._merge_result(result, resolution, deltas)
            result.changed = result.changed or bool(runtime._last_commit_scheduled_ids or runtime._last_commit_cancelled_ids or runtime._last_commit_reschedules)
            queue_after_settling: list[Event] = list(derived)
            if not self.state_laws:
                runtime.state_closure_known = True
                queue.extend(queue_after_settling)
                continue
            proposal_serial, event_serial, microstep, settled_events = self._settle_state(
                runtime, current, event.id, proposal_serial, event_serial, microstep, event_trace, trace, result, deltas,
            )
            queue_after_settling.extend(settled_events)
            queue.extend(queue_after_settling)

        # run_event intentionally does not advance simulation tick or sim_time.
        return result

    def _settle_runtime(self, runtime, force_full=False):
        event = Event("runtime:settle", "settle")
        trace = CausalTrace(root_event=deepcopy(event)); event_trace = EventTrace(event=deepcopy(event)); trace.events.append(event_trace)
        result = EventResult(trace=trace)
        if not self.state_laws:
            runtime.state_closure_known = True; return result
        if runtime.state_closure_known and not force_full: return result
        self._settle_state(runtime, event, event.id, 0, 0, 0, event_trace, trace, result, [], force_full=True)
        return result

    def _settle_state(self, runtime, event, root_id, proposal_serial, event_serial, microstep, event_trace, trace, result, frontier, force_full=False):
        full = force_full or self._state_closure_backend == "full" or not runtime.state_closure_known
        settling_law_ids, settling_addresses, derived_events = set(), set(), []
        for iteration in range(1, self.max_settle_iterations + 1):
            if full:
                runtime.stats.state_full_scans += 1
                proposals, proposal_serial, event_serial = self._collect("state", runtime, event, root_id, proposal_serial, event_serial, event_trace, trace)
            else:
                if not frontier: runtime.state_closure_known = True; return proposal_serial, event_serial, microstep, derived_events
                runtime.stats.state_incremental_rounds += 1; runtime.stats.dirty_deltas_processed += len(frontier)
                activated = self.state_dependency_index.activations(frontier, runtime.state)
                runtime.stats.state_activations += len(activated)
                proposals, proposal_serial, event_serial = self._collect_state_activations(runtime, event, root_id, proposal_serial, event_serial, event_trace, trace, activated)
            resolution = self._resolve(proposals)
            microstep += 1
            runtime._last_commit_scheduled_ids = []
            runtime._last_commit_cancelled_ids = []
            runtime._last_commit_reschedules = []
            derived, deltas = self._commit(runtime, resolution.accepted)
            future_derived_ids = [item.event.id for item in resolution.accepted if item.op == "emit_event" and item.event.id in runtime._last_commit_scheduled_ids]
            self._record_commit(trace, event_trace, resolution, deltas, derived, runtime._last_commit_scheduled_ids, runtime._last_commit_cancelled_ids, runtime._last_commit_reschedules, future_derived_ids, microstep, f"state:{iteration}")
            result.scheduled_event_ids.extend(runtime._last_commit_scheduled_ids)
            self._merge_result(result, resolution, deltas)
            settling_law_ids.update(proposal.law_id for proposal in resolution.accepted)
            settling_addresses.update(str(proposal.target) for proposal in resolution.accepted if proposal.target)
            derived_events.extend(derived)
            if not deltas:
                runtime.state_closure_known = True
                return proposal_serial, event_serial, microstep, derived_events
            frontier = deltas
        raise NonConvergentWorldError(self.max_settle_iterations, sorted(settling_law_ids), sorted(settling_addresses), trace)

    def _collect(
        self, mode: str, runtime, event: Event, root_id: str, proposal_serial: int,
        event_serial: int, event_trace: EventTrace, trace: CausalTrace,
    ) -> tuple[list[EffectProposal], int, int]:
        laws = self.event_laws if mode == "event" else self.state_laws
        if not laws: return [], proposal_serial, event_serial
        snapshot = runtime._read_view()
        context = MatchContext(snapshot, event, index_provider=runtime.get_index)
        proposals: list[EffectProposal] = []
        match_traces = event_trace.event_law_matches if mode == "event" else event_trace.state_law_matches
        for law in laws:
            for bindings in self._matcher(law, snapshot, event, context=context, plan=self.match_plans[law.law_id]):
                produced: list[EffectProposal] = []
                for effect in law.effects:
                    proposal_serial += 1
                    proposal_id = f"proposal:{root_id}:{proposal_serial:06d}"
                    if effect["op"] == "emit_event":
                        event_serial += 1
                    produced.append(self._propose(law, snapshot, event, bindings, effect, proposal_id, root_id, event_serial))
                proposals.extend(produced)
                match_traces.append(LawMatchTrace(law.law_id, mode, {name: item.id for name, item in sorted(bindings.items())}, [item.proposal_id for item in produced]))
                trace.proposals.extend(ProposalTrace(item.proposal_id, item.law_id, item.op, str(item.target) if item.target else None, value=item.value, cause_event_id=event.id, source_proposal_ids=item.causes, source_law_ids=item.source_laws, emitted_event_id=item.event.id if item.event else None) for item in produced)
        return proposals, proposal_serial, event_serial

    def _collect_state_activations(self, runtime, event, root_id, proposal_serial, event_serial, event_trace, trace, activations):
        if not activations: return [], proposal_serial, event_serial
        snapshot = runtime._read_view(); context = MatchContext(snapshot, event, index_provider=runtime.get_index)
        proposals, seen_matches = [], set()
        for law, binding_name, item in activations:
            seeds = None if binding_name is None else {binding_name: item}
            stats = MatchStats()
            if seeds is not None: runtime.stats.seeded_match_calls += 1
            for bindings in self._matcher(law, snapshot, event, context=context, plan=self.match_plans[law.law_id], seed_bindings=seeds, stats=stats):
                match_key = (law.law_id, tuple((name, bindings[name].id) for name in sorted(bindings)))
                if match_key in seen_matches:
                    runtime.stats.state_activation_dedups += 1; continue
                seen_matches.add(match_key)
                produced = []
                for effect in law.effects:
                    proposal_serial += 1; proposal_id = f"proposal:{root_id}:{proposal_serial:06d}"
                    produced.append(self._propose(law, snapshot, event, bindings, effect, proposal_id, root_id, event_serial))
                proposals.extend(produced)
                event_trace.state_law_matches.append(LawMatchTrace(law.law_id, "state", {name: item.id for name, item in sorted(bindings.items())}, [item.proposal_id for item in produced]))
                trace.proposals.extend(ProposalTrace(item.proposal_id, item.law_id, item.op, str(item.target) if item.target else None, value=item.value, cause_event_id=event.id, source_proposal_ids=item.causes, source_law_ids=item.source_laws, emitted_event_id=None) for item in produced)
            runtime.stats.seeded_candidate_rows += stats.candidate_rows_examined
            if binding_name is None: runtime.stats.global_fallback_matches += stats.matches_returned
        return proposals, proposal_serial, event_serial

    def _propose(self, law: Law, world: WorldState, event: Event, bindings: dict[str, Any], effect: dict[str, Any], proposal_id: str, root_id: str, event_serial: int) -> EffectProposal:
        op = effect["op"]
        metadata = {"cause_event": event.id}
        if op == "emit_event":
            raw = value(effect["event"], world, event, bindings)
            raw["id"] = f"derived:{root_id}:{event_serial:06d}"
            raw.setdefault("time", event.time)
            raw["provenance"] = {"kind": "derived", "parent_event": event.id}
            validate_derived_event(raw, f"law={law.law_id}")
            return EffectProposal(proposal_id, law.law_id, law.priority, op, event=Event(**raw), source_proposal_ids=(proposal_id,), source_law_ids=(law.law_id,), metadata=metadata)
        if op == "schedule_event":
            raw = value(effect["event"], world, event, bindings)
            if not isinstance(raw, dict): raise ValueError("schedule_event requires resolved event object")
            raw.setdefault("source", None); raw.setdefault("target", None); raw.setdefault("payload", {})
            raw["provenance"] = {"kind": "scheduled", "parent_event": event.id}
            validate_event(raw, f"law={law.law_id}")
            scheduled = Event(**raw)
            return EffectProposal(proposal_id, law.law_id, law.priority, op, StateAddress("scheduled", scheduled.id), event=scheduled, source_proposal_ids=(proposal_id,), source_law_ids=(law.law_id,), metadata=metadata)
        if op == "cancel_scheduled":
            event_id = value(effect["value"], world, event, bindings)
            if not isinstance(event_id, str) or not event_id: raise ValueError("cancel_scheduled requires a non-empty string event id")
            return EffectProposal(proposal_id, law.law_id, law.priority, op, StateAddress("scheduled", event_id), event_id, source_proposal_ids=(proposal_id,), source_law_ids=(law.law_id,), metadata=metadata)
        if op == "reschedule_scheduled":
            raw = value(effect["value"], world, event, bindings)
            if not isinstance(raw, dict) or set(raw) != {"id", "time"} or not isinstance(raw["id"], str) or not raw["id"]:
                raise ValueError("reschedule_scheduled requires {id, time}")
            return EffectProposal(proposal_id, law.law_id, law.priority, op, StateAddress("scheduled", raw["id"]), raw, source_proposal_ids=(proposal_id,), source_law_ids=(law.law_id,), metadata=metadata)
        if op in {"create_entity", "create_relation"}:
            raw = value(effect["value"], world, event, bindings)
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str): raise ValueError(f"{op} requires resolved object with id")
            return EffectProposal(proposal_id, law.law_id, law.priority, op, StateAddress(op.removeprefix("create_"), raw["id"]), raw, source_proposal_ids=(proposal_id,), source_law_ids=(law.law_id,), metadata=metadata)
        if op in {"delete_entity", "delete_relation"}:
            target_object = value(effect["target"], world, event, bindings)
            return EffectProposal(proposal_id, law.law_id, law.priority, op, StateAddress(op.removeprefix("delete_"), target_object.id), source_proposal_ids=(proposal_id,), source_law_ids=(law.law_id,), metadata=metadata)
        target_ref = effect["target"]
        object_ref, *path = target_ref.split(".")
        target_object = value(object_ref, world, event, bindings)
        kind = law.bindings[object_ref[1:]]["kind"]
        return EffectProposal(proposal_id, law.law_id, law.priority, op, StateAddress(kind, target_object.id, tuple(path)), value(effect.get("value"), world, event, bindings), source_proposal_ids=(proposal_id,), source_law_ids=(law.law_id,), metadata=metadata)

    def _resolve(self, proposals: list[EffectProposal]) -> _Resolution:
        accepted: list[EffectProposal] = []
        accepted_ids: list[str] = []
        rejected: dict[str, str] = {}
        conflicts: list[str] = []
        lifecycle_ops = {"create_entity", "create_relation", "delete_entity", "delete_relation"}
        temporal_ops = {"schedule_event", "cancel_scheduled", "reschedule_scheduled"}
        lifecycle = sorted((item for item in proposals if item.op in lifecycle_ops), key=lambda item: item.proposal_id)
        lifecycle_by_id: dict[str, EffectProposal] = {}
        for item in lifecycle:
            key = (item.target.object_id if item.target else "")
            previous = lifecycle_by_id.get(key)
            if previous is not None and (previous.op.startswith("create") or item.op.startswith("create") or previous.op != item.op):
                raise ProposalConflictError(f"lifecycle conflict at object id '{key}'")
            if previous is None:
                lifecycle_by_id[key] = deepcopy(item)
            else:
                canonical = lifecycle_by_id[key]
                canonical.source_proposal_ids = canonical.causes + item.causes
                canonical.source_law_ids = tuple(sorted(set(canonical.source_laws + item.source_laws)))
        lifecycle_targets = set(lifecycle_by_id)
        for item in proposals:
            if item.op not in lifecycle_ops | temporal_ops | {"emit_event"} and item.target and item.target.object_id in lifecycle_targets:
                raise ProposalConflictError(f"lifecycle/value conflict at {item.target}")
        accepted.extend(lifecycle_by_id.values()); accepted_ids.extend(proposal_id for item in lifecycle_by_id.values() for proposal_id in item.causes)
        emit = sorted((item for item in proposals if item.op == "emit_event"), key=lambda item: item.proposal_id)
        accepted.extend(emit)
        accepted_ids.extend(item.proposal_id for item in emit)
        temporal_by_id: dict[str, list[EffectProposal]] = {}
        for item in sorted((p for p in proposals if p.op in temporal_ops), key=lambda p: p.proposal_id):
            temporal_by_id.setdefault(item.target.object_id, []).append(item)
        for event_id, group in sorted(temporal_by_id.items()):
            ops = {item.op for item in group}
            if len(ops) != 1 or "schedule_event" in ops and len(group) > 1:
                raise ProposalConflictError(f"scheduler conflict at scheduled:{event_id}")
            canonical = deepcopy(group[0])
            if ops == {"reschedule_scheduled"} and len({item.value["time"] for item in group}) > 1:
                raise ProposalConflictError(f"scheduler reschedule conflict at scheduled:{event_id}")
            canonical.source_proposal_ids = tuple(item.proposal_id for item in group)
            canonical.source_law_ids = tuple(sorted({law for item in group for law in item.source_laws}))
            accepted.append(canonical); accepted_ids.extend(canonical.source_proposal_ids)
        groups: dict[StateAddress, list[EffectProposal]] = {}
        for proposal in proposals:
            if proposal.op == "emit_event" or proposal.op in lifecycle_ops | temporal_ops:
                continue
            groups.setdefault(self._conflict_address(proposal), []).append(proposal)

        for address in sorted(groups, key=str):
            group = sorted(groups[address], key=lambda item: item.proposal_id)
            ops = {item.op for item in group}
            if "set" in ops and "delta" in ops:
                raise ProposalConflictError(f"set/delta conflict at {address}: {[item.proposal_id for item in group]}")
            if ops <= {"delta"}:
                ids = tuple(item.proposal_id for item in group)
                canonical = deepcopy(group[0])
                canonical.value = sum(item.value for item in group)
                canonical.source_proposal_ids = ids
                canonical.source_law_ids = tuple(sorted({law_id for item in group for law_id in item.source_laws}))
                accepted.append(canonical)
                accepted_ids.extend(ids)
                continue
            if ops <= {"set"}:
                chosen = self._winner(group)
                canonical = deepcopy(chosen)
                if len({repr(item.value) for item in group}) > 1 and len({item.law_id for item in group}) == 1:
                    raise ProposalConflictError(f"authoring conflict: law {chosen.law_id} produced conflicting set proposals at {address}")
                if len({repr(item.value) for item in group}) == 1:
                    canonical.source_proposal_ids = tuple(item.proposal_id for item in group)
                    canonical.source_law_ids = tuple(sorted({law_id for item in group for law_id in item.source_laws}))
                else:
                    canonical.source_proposal_ids = (chosen.proposal_id,)
                    canonical.source_law_ids = chosen.source_laws
                accepted.append(canonical)
                accepted_ids.extend(canonical.source_proposal_ids)
                if len(canonical.source_proposal_ids) == 1:
                    self._reject_losers(group, chosen, address, rejected, conflicts)
                continue
            if ops <= {"add_tag", "remove_tag"}:
                if len(ops) == 1:
                    canonical = deepcopy(group[0])
                    canonical.source_proposal_ids = tuple(item.proposal_id for item in group)
                    canonical.source_law_ids = tuple(sorted({law_id for item in group for law_id in item.source_laws}))
                    accepted.append(canonical)
                    accepted_ids.extend(canonical.source_proposal_ids)
                else:
                    chosen = self._winner(group)
                    if len({item.law_id for item in group}) == 1:
                        raise ProposalConflictError(f"authoring conflict: law {chosen.law_id} produced add/remove conflict at {address}")
                    canonical = deepcopy(chosen)
                    canonical.source_proposal_ids = (chosen.proposal_id,)
                    canonical.source_law_ids = chosen.source_laws
                    accepted.append(canonical)
                    accepted_ids.append(chosen.proposal_id)
                    self._reject_losers(group, chosen, address, rejected, conflicts)
                continue
            raise ProposalConflictError(f"Unsupported proposal combination at {address}: {sorted(ops)}")
        return _Resolution(accepted, sorted(accepted_ids), rejected, conflicts)

    @staticmethod
    def _conflict_address(proposal: EffectProposal) -> StateAddress:
        if proposal.op in {"add_tag", "remove_tag"}:
            return StateAddress(proposal.target.kind, proposal.target.object_id, ("tags", str(proposal.value)))  # type: ignore[union-attr]
        return proposal.target  # type: ignore[return-value]

    @staticmethod
    def _winner(group: list[EffectProposal]) -> EffectProposal:
        return min(group, key=lambda item: (-item.priority, item.law_id, item.proposal_id))

    @staticmethod
    def _reject_losers(group: list[EffectProposal], chosen: EffectProposal, address: StateAddress, rejected: dict[str, str], conflicts: list[str]) -> None:
        for item in group:
            if item.proposal_id == chosen.proposal_id:
                continue
            reason = f"conflict at {address}; selected {chosen.law_id}"
            rejected[item.proposal_id] = reason
            conflicts.append(f"{reason} over {item.law_id}")

    def _commit(self, runtime, proposals: list[EffectProposal]) -> tuple[list[Event], list[StateDelta]]:
        prepared = self._prepare_world_mutation(runtime, proposals)
        self._publish_world_mutation(runtime, prepared)
        return prepared.immediate_events, prepared.deltas

    def _prepare_world_mutation(self, runtime, proposals: list[EffectProposal]) -> PreparedWorldMutation:
        world = runtime.state
        runtime.stats.transactions_prepared += 1
        derived = [item.event for item in sorted(proposals, key=lambda item: item.proposal_id) if item.op == "emit_event"]
        explicit_scheduled = [item.event for item in sorted(proposals, key=lambda item: item.proposal_id) if item.op == "schedule_event"]
        cancellations = [item.target.object_id for item in proposals if item.op == "cancel_scheduled"]
        reschedules = [(item.target.object_id, item.value["time"]) for item in proposals if item.op == "reschedule_scheduled"]
        deltas: list[StateDelta] = []
        clones: dict[tuple[str, str], Any] = {}
        def object_for(target):
            key = (target.kind, target.object_id)
            return clones.get(key) or world.get_object(*key)
        def ensure_clone(target):
            key = (target.kind, target.object_id)
            if key not in clones:
                original = world.get_object(*key)
                if original is None: raise ValueError(f"Unknown proposal target: {target}")
                clones[key] = deepcopy(original); runtime.stats.objects_cloned += 1
            return clones[key]
        for proposal in sorted((item for item in proposals if item.op not in {"emit_event", "schedule_event", "cancel_scheduled", "reschedule_scheduled", "create_entity", "create_relation", "delete_entity", "delete_relation"}), key=lambda item: str(self._conflict_address(item))):
            target = proposal.target
            obj = object_for(target)
            if obj is None: raise ValueError(f"Unknown proposal target: {target}")
            if proposal.op in {"add_tag", "remove_tag"}:
                tag = str(proposal.value)
                old = tag in obj.tags
                new = proposal.op == "add_tag"
                if old != new:
                    obj = ensure_clone(target)
                    (obj.tags.add(tag) if new else obj.tags.remove(tag))
                    deltas.append(StateDelta(self._conflict_address(proposal), old, new, proposal.causes, proposal.source_laws))
                continue
            if not target.path:
                raise ValueError(f"{proposal.op} requires a component path: {target}")
            container: Any = obj.components
            missing_parent = False
            for key in target.path[:-1]:
                if not isinstance(container, dict) or key not in container:
                    missing_parent = True; break
                container = container[key]
            key = target.path[-1]
            old = None if missing_parent else container.get(key)
            if proposal.op == "set":
                new = proposal.value
            elif proposal.op == "delta":
                if old is None:
                    raise ValueError(f"delta requires an existing numeric value: {target}")
                new = old + proposal.value
            else:
                raise ValueError(f"Unsupported effect operation: {proposal.op}")
            if old != new:
                obj = ensure_clone(target)
                container = obj.components
                for key_part in target.path[:-1]: container = container.setdefault(key_part, {})
                container[key] = new
                deltas.append(StateDelta(target, old, new, proposal.causes, proposal.source_laws))
        # Validate the complete write set before publishing any replacement.
        for (kind, _), obj in clones.items():
            if kind == "entity": validate_runtime_entity(obj)
            else: validate_runtime_relation(obj)
            runtime.stats.local_objects_validated += 1
        lifecycle = [item for item in proposals if item.op in {"create_entity", "create_relation", "delete_entity", "delete_relation"}]
        created_entities, created_relations, deleted = {}, {}, set()
        lifecycle_sources = {}
        for item in lifecycle:
            kind, object_id = item.target.kind, item.target.object_id
            lifecycle_sources[(kind, object_id)] = (item.causes, item.source_laws)
            if item.op.startswith("delete"):
                if world.get_object(kind, object_id) is None: continue
                deleted.add((kind, object_id)); continue
            raw = item.value
            try:
                if kind == "entity":
                    obj = _materialize_entity(raw); created_entities[object_id] = obj
                else:
                    obj = _materialize_relation(raw); created_relations[object_id] = obj
            except Exception as exc:
                runtime.stats.lifecycle_preflight_failures += 1
                raise ValueError(f"invalid lifecycle creation {object_id}") from exc
        created_entity_ids = set(created_entities)
        created_relation_ids = set(created_relations)
        deleted_entity_ids = {object_id for kind, object_id in deleted if kind == "entity"}
        deleted_relation_ids = {object_id for kind, object_id in deleted if kind == "relation"}
        if created_entity_ids & created_relation_ids:
            runtime.stats.lifecycle_preflight_failures += 1
            raise ProposalConflictError("lifecycle object id collision")

        for object_id in created_entity_ids | created_relation_ids:
            exists_as_entity = object_id in world.entities
            exists_as_relation = object_id in world.relations
            runtime.stats.lifecycle_id_membership_checks += 2
            if exists_as_entity or exists_as_relation:
                runtime.stats.lifecycle_preflight_failures += 1
                raise ProposalConflictError("lifecycle object id collision")

        def entity_exists_final(entity_id: str) -> bool:
            if entity_id in created_entities:
                return True
            if entity_id in deleted_entity_ids:
                return False
            return entity_id in world.entities

        for relation in created_relations.values():
            source_exists = entity_exists_final(relation.source)
            target_exists = entity_exists_final(relation.target)
            runtime.stats.lifecycle_endpoint_checks += 2
            if not source_exists or not target_exists:
                runtime.stats.lifecycle_preflight_failures += 1
                raise DanglingRelationError("dangling created relation after lifecycle transaction")

        if deleted_entity_ids:
            index = runtime.get_index()
            for entity_id in deleted_entity_ids:
                incident = index.relations_by_source[entity_id] | index.relations_by_target[entity_id]
                runtime.stats.lifecycle_incident_relation_checks += len(incident)
                surviving_incident = incident - deleted_relation_ids
                if surviving_incident:
                    runtime.stats.lifecycle_preflight_failures += 1
                    raise ObjectInUseError(f"entity '{entity_id}' is referenced by relations {sorted(surviving_incident)}")
        deleted_objects: list[tuple[str, Any]] = []
        for kind, object_id in sorted(deleted, key=lambda item: (item[0] != "relation", item[1])):
            original = world.get_object(kind, object_id)
            if original is not None:
                causes, laws = lifecycle_sources[(kind, object_id)]
                deleted_objects.append((kind, original)); deltas.append(StateDelta(StateAddress(kind, object_id), deepcopy(original.to_dict()), None, causes, laws))
        for object_id, obj in created_entities.items():
            causes, laws = lifecycle_sources[("entity", object_id)]; deltas.append(StateDelta(StateAddress("entity", object_id), None, deepcopy(obj.to_dict()), causes, laws))
        for object_id, obj in created_relations.items():
            causes, laws = lifecycle_sources[("relation", object_id)]; deltas.append(StateDelta(StateAddress("relation", object_id), None, deepcopy(obj.to_dict()), causes, laws))
        future = [item for item in derived if item.time > world.sim_time]
        immediate = [item for item in derived if item.time <= world.sim_time]
        # This and every semantic check must complete before publication.
        prepared_schedule = runtime.prepare_scheduler_mutation(future + explicit_scheduled, cancellations, reschedules)
        index_changes = []
        for (kind, object_id), obj in clones.items():
            original = world.get_object(kind, object_id)
            index_changes.append((kind, object_id, set(original.components) if original is not None else set(), set(obj.components)))
        return PreparedWorldMutation(
            clones, created_entities, created_relations, deleted_objects, index_changes,
            prepared_schedule, immediate, future + explicit_scheduled, deltas, len(lifecycle),
            list(prepared_schedule.cancellations),
            [{"id": event_id, "old_time": old, "new_time": new} for event_id, _, old, new in prepared_schedule.reschedules],
            [item.id for item in future],
        )

    @staticmethod
    def _publish_world_mutation(runtime, prepared: PreparedWorldMutation) -> None:
        world = runtime.state
        deleted_relations = sorted((obj for kind, obj in prepared.deleted_objects if kind == "relation"), key=lambda obj: obj.id)
        deleted_entities = sorted((obj for kind, obj in prepared.deleted_objects if kind == "entity"), key=lambda obj: obj.id)

        # All expected failures have occurred; publication only changes owned containers.
        for obj in deleted_relations: world.relations.pop(obj.id)
        for obj in deleted_entities: world.entities.pop(obj.id)
        world.entities.update(prepared.created_entities)
        world.relations.update(prepared.created_relations)
        for (kind, object_id), obj in sorted(prepared.replacements.items()):
            (world.entities if kind == "entity" else world.relations)[object_id] = obj
            runtime.stats.objects_swapped += 1

        if prepared.deltas:
            runtime.revision += 1
            runtime.object_revision += 1
            runtime.apply_index_patch(prepared.index_changes)
            if prepared.lifecycle_action_count and runtime._index is not None:
                try:
                    for obj in deleted_relations:
                        runtime._index.remove_relation(obj)
                        runtime.stats.relation_component_posting_removes += len(obj.components)
                        runtime.stats.relation_topology_posting_removes += 7
                    for obj in deleted_entities:
                        runtime._index.remove_entity(obj)
                        runtime.stats.entity_component_posting_removes += len(obj.components)
                    for obj in prepared.created_entities.values():
                        runtime._index.add_entity(obj)
                        runtime.stats.entity_component_posting_adds += len(obj.components)
                    for obj in prepared.created_relations.values():
                        runtime._index.add_relation(obj)
                        runtime.stats.relation_component_posting_adds += len(obj.components)
                        runtime.stats.relation_topology_posting_adds += 7
                    runtime._index_revision = runtime.object_revision
                    runtime.stats.topology_index_patches += prepared.lifecycle_action_count
                except Exception:
                    runtime.invalidate_index()
            if prepared.lifecycle_action_count:
                runtime.stats.lifecycle_transactions += 1
                runtime.stats.entities_created += len(prepared.created_entities)
                runtime.stats.relations_created += len(prepared.created_relations)
                runtime.stats.entities_deleted += len(deleted_entities)
                runtime.stats.relations_deleted += len(deleted_relations)

        runtime._last_commit_scheduled_ids = [item.id for item in prepared.future_events]
        runtime._last_commit_cancelled_ids = prepared.cancelled_event_ids
        runtime._last_commit_reschedules = prepared.rescheduled_events
        runtime._last_commit_future_derived_ids = prepared.future_derived_event_ids
        temporal_changed = prepared.prepared_schedule.changed
        runtime.commit_scheduler_mutation(prepared.prepared_schedule, future=set(prepared.future_derived_event_ids))
        if prepared.deltas or temporal_changed: runtime.stats.transactions_committed += 1
        else: runtime.stats.noop_transactions += 1

    def _record_commit(self, trace: CausalTrace, event_trace: EventTrace, resolution: _Resolution, deltas: list[StateDelta], derived: list[Event], scheduled_event_ids: list[str], cancelled_event_ids: list[str], rescheduled_events: list[dict[str, Any]], future_derived_event_ids: list[str], microstep: int, phase: str) -> None:
        for item in trace.proposals:
            if item.proposal_id in resolution.accepted_ids:
                item.status = "accepted"
            elif item.proposal_id in resolution.rejected:
                item.status = "rejected"
                item.reason = resolution.rejected[item.proposal_id]
        trace.conflicts.extend(resolution.conflicts)
        event_trace.commits.append(CommitTrace(microstep, phase, resolution.accepted_ids, sorted(resolution.rejected), deltas, [item.id for item in derived] + future_derived_event_ids, scheduled_event_ids, cancelled_event_ids, rescheduled_events))

    @staticmethod
    def _merge_result(result: EventResult, resolution: _Resolution, deltas: list[StateDelta]) -> None:
        result.changed = result.changed or bool(deltas)
        result.state_delta.extend(deltas)
        result.conflicts.extend(resolution.conflicts)
        for law_id in sorted({law_id for item in resolution.accepted for law_id in item.source_laws}):
            if law_id not in result.triggered_law_ids:
                result.triggered_law_ids.append(law_id)
