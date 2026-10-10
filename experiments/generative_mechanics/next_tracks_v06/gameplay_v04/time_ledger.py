"""Finite world-time budget for exploration and offline progression."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pmw import Event, WorldState, parse_law

from .contracts import GameplayContractError, TickResult
from .dynamics import CLOCK_COMPONENT
from .runtime import GameplaySession, advance_world_tick


TIME_BUDGET_COMPONENT = "pmw_gameplay_time_budget"
TIME_SPEND_EVENT = "pmw.v04.time.spend"
TIME_REASONS = ("exploration", "harvest", "move", "rest", "offline")


@dataclass(frozen=True, slots=True)
class TimeSpendResult:
    reason: str
    duration: int
    before_remaining: int
    after_remaining: int
    event_result: Any
    ticks: tuple[TickResult, ...]


def initialize_time_budget(world: WorldState, total_ticks: int) -> WorldState:
    """Attach a budget to a detached time-zero world before building its runtime."""
    if isinstance(total_ticks, bool) or not isinstance(total_ticks, int) or total_ticks < 1:
        raise GameplayContractError("world time budget must be a positive integer")
    if world.tick != 0 or world.sim_time != 0 or world.scheduled_events:
        raise GameplayContractError("time budget initialization requires a detached time-zero WorldState")
    result = deepcopy(world)
    clocks = [entity for entity in result.entities.values() if CLOCK_COMPONENT in entity.components]
    if len(clocks) != 1:
        raise GameplayContractError("time budget requires exactly one gameplay clock")
    clocks[0].components[TIME_BUDGET_COMPONENT] = {
        "total_ticks": total_ticks,
        "spent_ticks": 0,
        "remaining_ticks": total_ticks,
        "last_reason": None,
    }
    return result


def build_time_budget_laws() -> tuple[dict, ...]:
    law = {
        "id": "pmw.v04.time.spend", "mode": "event", "priority": 100,
        "bindings": {"clock": {"kind": "entity", "requires": [CLOCK_COMPONENT, TIME_BUDGET_COMPONENT]}},
        "when": {"all": [
            {"event.type": {"eq": TIME_SPEND_EVENT}},
            {"ref": "$clock.id", "eq": "$event.source"},
            {"ref": "$clock.id", "eq": "$event.target"},
            {"ref": f"$clock.{TIME_BUDGET_COMPONENT}.remaining_ticks", "eq": "$event.payload.before_remaining"},
            {"ref": f"$clock.{TIME_BUDGET_COMPONENT}.spent_ticks", "eq": "$event.payload.before_spent"},
        ]},
        "effects": [
            {"op": "set", "target": f"$clock.{TIME_BUDGET_COMPONENT}.remaining_ticks",
             "value": "$event.payload.after_remaining"},
            {"op": "set", "target": f"$clock.{TIME_BUDGET_COMPONENT}.spent_ticks",
             "value": "$event.payload.after_spent"},
            {"op": "set", "target": f"$clock.{TIME_BUDGET_COMPONENT}.last_reason",
             "value": "$event.payload.reason"},
        ],
    }
    parse_law(law)
    return (law,)


def spend_world_time(session: GameplaySession, duration: int, *, reason: str) -> TimeSpendResult:
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 1:
        raise GameplayContractError("time spend duration must be a positive integer")
    if reason not in TIME_REASONS:
        raise GameplayContractError("unknown world time spend reason")
    clock_id, budget = _budget(session)
    remaining = budget["remaining_ticks"]
    spent = budget["spent_ticks"]
    if duration > remaining:
        raise GameplayContractError("world time budget is exhausted")
    payload = {
        "reason": reason, "duration": duration,
        "before_remaining": remaining, "after_remaining": remaining - duration,
        "before_spent": spent, "after_spent": spent + duration,
    }
    event_result = session.runtime.run_event(Event(
        f"pmw:v04:time:{spent:08d}:{reason}", TIME_SPEND_EVENT,
        session.state.sim_time, clock_id, clock_id, payload,
    ))
    if not event_result.changed:
        raise GameplayContractError("world time spend did not commit")
    ticks = tuple(advance_world_tick(session, clock_id=clock_id) for _ in range(duration))
    return TimeSpendResult(reason, duration, remaining, remaining - duration, event_result, ticks)


def _budget(session: GameplaySession) -> tuple[str, dict[str, Any]]:
    matches = [
        (entity.id, entity.components[TIME_BUDGET_COMPONENT])
        for entity in session.state.entities.values()
        if CLOCK_COMPONENT in entity.components and TIME_BUDGET_COMPONENT in entity.components
    ]
    if len(matches) != 1:
        raise GameplayContractError("session must contain one clock-owned world time budget")
    clock_id, budget = matches[0]
    if (
        not isinstance(budget, dict)
        or set(budget) != {"total_ticks", "spent_ticks", "remaining_ticks", "last_reason"}
        or any(isinstance(budget[key], bool) or not isinstance(budget[key], int)
               for key in ("total_ticks", "spent_ticks", "remaining_ticks"))
        or budget["total_ticks"] < 1
        or budget["spent_ticks"] < 0
        or budget["remaining_ticks"] < 0
        or budget["spent_ticks"] + budget["remaining_ticks"] != budget["total_ticks"]
        or (budget["last_reason"] is not None and budget["last_reason"] not in TIME_REASONS)
    ):
        raise GameplayContractError("world time budget state is invalid")
    return clock_id, budget
