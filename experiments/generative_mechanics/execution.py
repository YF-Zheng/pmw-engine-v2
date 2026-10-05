"""Trusted event construction for compiled skill mechanics."""

from __future__ import annotations

from typing import Any

from pmw import Event

from .spec import SkillSpec


class ExperimentExecutionError(ValueError):
    """Raised before PMW execution when an experiment command is incomplete."""


def required_handle_fields(spec: SkillSpec) -> tuple[str, ...]:
    if spec.duration > 0:
        return ("expiry_event_id",)
    if spec.periodic:
        return tuple(f"pulse_{index:02d}_event_id" for index in range(1, spec.periodic.repeats + 1))
    return ()


def activation_payload(spec: SkillSpec, skill_instance_id: str, activation_id: str) -> dict[str, Any]:
    if not all(isinstance(value, str) and value for value in (skill_instance_id, activation_id)):
        raise ExperimentExecutionError("skill_instance_id and activation_id must be non-empty strings")
    payload: dict[str, Any] = {"skill_id": spec.id, "skill_instance_id": skill_instance_id}
    for field in required_handle_fields(spec):
        payload[field] = f"gm.handle.{activation_id}.{field}"
    return payload


def activation_event(
    spec: SkillSpec, *, activation_id: str, skill_instance_id: str,
    actor_id: str, zone_id: str, time: float,
) -> Event:
    if not all(isinstance(value, str) and value for value in (actor_id, zone_id)):
        raise ExperimentExecutionError("actor_id and zone_id must be non-empty strings")
    return Event(
        id=activation_id, type="lab.skill.activate", time=float(time),
        source=actor_id, target=zone_id,
        payload=activation_payload(spec, skill_instance_id, activation_id),
    )


def validate_activation_payload(spec: SkillSpec, payload: Any) -> None:
    required = {"skill_id", "skill_instance_id", *required_handle_fields(spec)}
    if not isinstance(payload, dict):
        raise ExperimentExecutionError("activation payload must be an object")
    missing = required - set(payload)
    if missing:
        raise ExperimentExecutionError(f"activation payload missing required fields: {sorted(missing)}")
    for key in required:
        if not isinstance(payload[key], str) or not payload[key]:
            raise ExperimentExecutionError(f"activation payload field {key!r} must be a non-empty string")
