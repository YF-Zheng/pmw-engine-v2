"""Formal integer-time protocol for v0.6 dynamics ticks."""

from __future__ import annotations

from dataclasses import dataclass
import math

from pmw import Event

from .law_builder import CLOCK_COMPONENT, TICK_EVENT, WORLD_STEP_EVENT


class TickProtocolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TickResult:
    step: int
    time: float
    advance_result: object
    dynamics_result: object
    world_step_result: object
    snapshot: object


def _clock(runtime, clock_id: str) -> dict:
    entity = runtime.state.entities.get(clock_id)
    if entity is None or CLOCK_COMPONENT not in entity.components:
        raise TickProtocolError(f"missing dynamics clock {clock_id!r}")
    value = entity.components[CLOCK_COMPONENT]
    if not isinstance(value, dict):
        raise TickProtocolError("dynamics clock component must be an object")
    return value


def advance_dynamics_step(runtime, *, clock_id: str = "gm:v06:clock") -> TickResult:
    """Advance due schedules, run one dynamics tick and one world-step event."""

    before = _clock(runtime, clock_id)
    step = before.get("next_step")
    target_time = before.get("next_time")
    if isinstance(step, bool) or not isinstance(step, int) or step < 0:
        raise TickProtocolError("clock.next_step must be a non-negative integer")
    if isinstance(target_time, bool) or not isinstance(target_time, (int, float)) or not math.isfinite(target_time):
        raise TickProtocolError("clock.next_time must be finite")
    if float(target_time) != float(step):
        raise TickProtocolError("v0.6 integer protocol requires next_time == next_step")
    advance_result = runtime.advance_to(float(target_time))
    after_dispatch = _clock(runtime, clock_id)
    if after_dispatch.get("next_step") != step or float(after_dispatch.get("next_time", math.nan)) != float(target_time):
        raise TickProtocolError("a due event changed the dynamics clock")

    payload = {"step": step}
    dynamics_result = runtime.run_event(Event(
        id=f"gm:v06:tick:{step:08d}", type=TICK_EVENT, time=float(target_time),
        source=clock_id, payload=payload,
    ))
    completed = _clock(runtime, clock_id)
    if completed.get("last_completed_step") != step or completed.get("next_step") != step + 1:
        raise TickProtocolError("dynamics tick did not complete exactly once")
    world_step_result = runtime.run_event(Event(
        id=f"gm:v06:world-step:{step:08d}", type=WORLD_STEP_EVENT,
        time=float(target_time), source=clock_id, payload=payload,
    ))
    return TickResult(
        step, float(target_time), advance_result, dynamics_result,
        world_step_result, runtime.snapshot(),
    )
