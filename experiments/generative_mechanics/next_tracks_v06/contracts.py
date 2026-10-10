"""Shared immutable IR contracts frozen before role implementations begin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


PROTOCOL_ID = "gm-mechanism-v0.6"
CATALOG_PROTOCOL_ID = "gm-object-catalog-v0.6"
OBJECT_KINDS = ("field", "stock", "process", "relation", "discrete", "derived")
OPERATOR_KINDS = (
    "impulse",
    "drive",
    "attractor_modifier",
    "dynamics_modifier",
    "process_start",
    "process_modify",
    "relation_modifier",
)
LIFECYCLE_MODES = ("instant", "timed", "permanent")


@dataclass(frozen=True, slots=True)
class StateHandle:
    kind: str
    object_id: str
    path: tuple[str, ...]
    value_type: str = "number"


@dataclass(frozen=True, slots=True)
class LifecycleIR:
    mode: str
    steps: int | None = None


@dataclass(frozen=True, slots=True)
class SlotReservation:
    slot_id: str
    slot_kind: str
    target_object_id: str
    artifact_id: str
    operator_id: str
    instance_index: int


@dataclass(frozen=True, slots=True)
class OperatorIR:
    operator_id: str
    kind: str
    capability_id: str
    scope: str
    target_object_id: str
    parameters: Mapping[str, Any]
    lifecycle: LifecycleIR
    reservations: tuple[SlotReservation, ...]
    source_pointer: str


@dataclass(frozen=True, slots=True)
class MechanismIR:
    protocol: str
    artifact_id: str
    name: str
    canonical_spec_sha256: str
    scope_kind: str
    scope_anchor: str
    max_instances: int
    event_namespace: str
    operators: tuple[OperatorIR, ...]
    required_objects: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    reservations: tuple[SlotReservation, ...]
    generated_event_types: tuple[str, ...]
    generated_handle_templates: tuple[str, ...]
    source_map: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class CompiledMechanism:
    protocol_version: str
    artifact_id: str
    canonical_spec_hash: str
    max_instances: int
    law_bundle: tuple[Mapping[str, Any], ...]
    required_world_objects: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    generated_event_types: tuple[str, ...]
    generated_temporal_handles: tuple[str, ...]
    slot_allocations: tuple[SlotReservation, ...]
    source_map: Mapping[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "artifact_id": self.artifact_id,
            "canonical_spec_hash": self.canonical_spec_hash,
            "max_instances": self.max_instances,
            "law_bundle": [dict(law) for law in self.law_bundle],
            "required_world_objects": list(self.required_world_objects),
            "required_capabilities": list(self.required_capabilities),
            "generated_event_types": list(self.generated_event_types),
            "generated_temporal_handles": list(self.generated_temporal_handles),
            "slot_allocations": [
                {
                    "slot_id": item.slot_id,
                    "slot_kind": item.slot_kind,
                    "target_object_id": item.target_object_id,
                    "artifact_id": item.artifact_id,
                    "operator_id": item.operator_id,
                    "instance_index": item.instance_index,
                }
                for item in self.slot_allocations
            ],
            "source_map": dict(sorted(self.source_map.items())),
        }
