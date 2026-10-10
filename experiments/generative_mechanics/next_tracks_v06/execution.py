"""Trusted PMW runtime harness for v0.6 compiled mechanisms.

The helpers in this module construct commands and orchestrate PMW.  They never
apply mechanism or physics state changes directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from pmw import Engine, Event, WorldState, load_world, parse_law, save_world

from .contracts import CompiledMechanism
from .dynamics.tick_protocol import TickResult, advance_dynamics_step


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ExecutionContractError(ValueError):
    """Raised before PMW execution when a trusted command is malformed."""


def build_runtime(
    world: WorldState,
    world_laws: Iterable[Mapping[str, Any]],
    mechanisms: Iterable[CompiledMechanism] = (),
):
    """Build one immutable-law Engine and attach an existing formal state."""

    raw_laws = [dict(item) for item in world_laws]
    for mechanism in mechanisms:
        raw_laws.extend(dict(item) for item in mechanism.law_bundle)
    laws = [parse_law(item) for item in sorted(raw_laws, key=lambda row: row["id"])]
    return Engine(laws).attach(world)


def activation_event(
    mechanism: CompiledMechanism,
    *,
    activation_id: str,
    instance_index: int,
    time: int | float,
    source: str | None = None,
    target: str | None = None,
) -> Event:
    """Construct the only supported external activation command.

    Temporal handle IDs are compiler-owned.  An activation-specific suffix
    prevents two live activations from sharing a pending Scheduler handle.
    """

    _require_identifier(activation_id, "activation_id")
    if isinstance(instance_index, bool) or not isinstance(instance_index, int) or not 0 <= instance_index < mechanism.max_instances:
        raise ExecutionContractError("instance_index is outside the compiled mechanism range")
    handles = _instance_handles(mechanism, instance_index, activation_id)
    payload = {
        "protocol": mechanism.protocol_version,
        "artifact_id": mechanism.artifact_id,
        "canonical_spec_hash": mechanism.canonical_spec_hash,
        "instance_index": instance_index,
        "activation_id": activation_id,
        "temporal_handles": handles,
    }
    event = Event(
        id=f"gm.v06.activation.{mechanism.artifact_id}.{instance_index}.{activation_id}",
        type=f"gm.v06.mechanism.{mechanism.artifact_id}.activate",
        time=float(time),
        source=source,
        target=target,
        payload=payload,
    )
    validate_activation_event(mechanism, event)
    return event


def validate_activation_event(mechanism: CompiledMechanism, event: Event) -> None:
    expected = {
        "protocol", "artifact_id", "canonical_spec_hash", "instance_index",
        "activation_id", "temporal_handles",
    }
    payload = event.payload
    if set(payload) != expected:
        raise ExecutionContractError("activation payload has missing or unexpected fields")
    if event.type != f"gm.v06.mechanism.{mechanism.artifact_id}.activate":
        raise ExecutionContractError("activation event type is outside the mechanism namespace")
    if payload["protocol"] != mechanism.protocol_version:
        raise ExecutionContractError("activation protocol mismatch")
    if payload["artifact_id"] != mechanism.artifact_id:
        raise ExecutionContractError("activation artifact mismatch")
    if payload["canonical_spec_hash"] != mechanism.canonical_spec_hash:
        raise ExecutionContractError("activation spec hash mismatch")
    _require_identifier(payload["activation_id"], "payload.activation_id")
    index = payload["instance_index"]
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < mechanism.max_instances:
        raise ExecutionContractError("activation instance_index is invalid")
    handles = payload["temporal_handles"]
    if not isinstance(handles, dict):
        raise ExecutionContractError("temporal_handles must be an object")
    expected_handles = _instance_handles(mechanism, index, payload["activation_id"])
    if handles != expected_handles:
        raise ExecutionContractError("activation temporal handle set mismatch")
    if len(set(handles.values())) != len(handles):
        raise ExecutionContractError("activation temporal handles must be unique")


def activate(runtime, mechanism: CompiledMechanism, event: Event):
    validate_activation_event(mechanism, event)
    if event.time != runtime.state.sim_time:
        raise ExecutionContractError("activation time must equal the current simulation time")
    pending_ids = {item.id for item in runtime.state.scheduled_events}
    prefixes = _instance_handle_prefixes(mechanism, event.payload["instance_index"])
    if any(any(handle.startswith(prefix) for prefix in prefixes) for handle in pending_ids):
        raise ExecutionContractError(
            "mechanism instance still has a live timed activation"
        )
    return runtime.run_event(event)


def cancel_activation(runtime, mechanism: CompiledMechanism, *, activation_id: str, instance_index: int):
    """Expire every timed operator for one activation and cancel its handles."""

    _require_identifier(activation_id, "activation_id")
    if isinstance(instance_index, bool) or not isinstance(instance_index, int) or not 0 <= instance_index < mechanism.max_instances:
        raise ExecutionContractError("instance_index is outside the compiled mechanism range")
    handles = _instance_handles(mechanism, instance_index, activation_id)
    pending_ids = {item.id for item in runtime.state.scheduled_events}
    pending_handles = {
        operator_id: handle for operator_id, handle in handles.items()
        if handle in pending_ids
    }
    if not pending_handles:
        raise ExecutionContractError("activation has no matching pending handles")
    results = []
    for operator_id, handle in pending_handles.items():
        event_type = next((
            item for item in mechanism.generated_event_types
            if item.endswith(f".{operator_id}.expire")
        ), None)
        if event_type is None:
            raise ExecutionContractError(f"missing expiry event type for {operator_id}")
        results.append(runtime.run_event(Event(
            id=handle,
            type=event_type,
            time=runtime.state.sim_time,
            payload={
                "artifact_id": mechanism.artifact_id,
                "canonical_spec_hash": mechanism.canonical_spec_hash,
                "instance_index": instance_index,
                "operator_id": operator_id,
                "temporal_handle": handle,
            },
        )))
    return tuple(results)


def run_step(runtime, step: int | None = None, *, clock_id: str = "gm:v06:clock") -> TickResult:
    """Delegate one complete PREPARE -> ACCUMULATE -> COMMIT protocol step."""

    result = advance_dynamics_step(runtime, clock_id=clock_id)
    if step is not None and result.step != step:
        raise ExecutionContractError(f"clock produced step {result.step}, expected {step}")
    return result


def run_steps(runtime, count: int, *, clock_id: str = "gm:v06:clock") -> tuple[TickResult, ...]:
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ExecutionContractError("count must be a non-negative integer")
    return tuple(run_step(runtime, clock_id=clock_id) for _ in range(count))


def save_checkpoint(path: str | Path, runtime) -> None:
    if runtime.state.sim_time != int(runtime.state.sim_time):
        raise ExecutionContractError("checkpoints require an integer step boundary")
    save_world(path, runtime.state)


def load_checkpoint(
    path: str | Path,
    world_laws: Iterable[Mapping[str, Any]],
    mechanisms: Iterable[CompiledMechanism] = (),
):
    return build_runtime(load_world(path), world_laws, mechanisms)


def _require_identifier(value: Any, name: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ExecutionContractError(f"{name} must match {_IDENTIFIER.pattern}")


def _instance_handles(mechanism: CompiledMechanism, instance: int, activation_id: str) -> dict[str, str]:
    marker = f".instance.{instance}."
    result: dict[str, str] = {}
    for template in mechanism.generated_temporal_handles:
        if marker not in template:
            continue
        tail = template.split(marker, 1)[1]
        operator_id = tail.split(".expiry.", 1)[0]
        if not operator_id or operator_id in result:
            raise ExecutionContractError("ambiguous temporal handle template")
        result[operator_id] = template.format(activation_id=activation_id)
    return dict(sorted(result.items()))


def _instance_handle_prefixes(mechanism: CompiledMechanism, instance: int) -> tuple[str, ...]:
    marker = f".instance.{instance}."
    prefixes = {
        template.split("{activation_id}", 1)[0]
        for template in mechanism.generated_temporal_handles
        if marker in template and "{activation_id}" in template
    }
    return tuple(sorted(prefixes))
