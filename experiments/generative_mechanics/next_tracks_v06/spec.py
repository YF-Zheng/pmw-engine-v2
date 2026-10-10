"""Trusted catalog and untrusted authoring data types for v0.6."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import StateHandle


@dataclass(frozen=True, slots=True)
class CatalogLimits:
    max_operators: int
    max_instances: int
    max_targets: int
    max_duration_steps: int
    max_total_effect_slots: int
    max_scheduled_handles: int


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    id: str
    state_ref: StateHandle
    minimum: float
    maximum: float
    combination: str
    modifier_slots: tuple[str, ...]
    dynamics_parameter: bool = False


@dataclass(frozen=True, slots=True)
class FieldObject:
    id: str
    ownership: str
    state_ref: StateHandle
    minimum: float
    maximum: float
    initial: float
    normalization: str
    writable: bool
    allowed_operators: tuple[str, ...]
    dynamics: Mapping[str, Any] | None
    kind: str = "field"


@dataclass(frozen=True, slots=True)
class StockObject:
    id: str
    ownership: str
    amount_ref: StateHandle
    capacity: float
    initial: float
    boundary_policy: str
    transfer_unit: str
    allowed_operators: tuple[str, ...]
    source_policy: str
    sink_policy: str
    kind: str = "stock"


@dataclass(frozen=True, slots=True)
class ProcessObject:
    id: str
    ownership: str
    entity_id: str
    running_ref: StateHandle
    start_state: str
    stop_state: str
    already_running: str
    source_objects: tuple[str, ...]
    target_objects: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]
    allowed_operators: tuple[str, ...]
    kind: str = "process"


@dataclass(frozen=True, slots=True)
class RelationObject:
    id: str
    ownership: str
    relation_type: str
    lifecycle: str
    relation_id: str | None
    source_objects: tuple[str, ...]
    target_objects: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]
    allowed_operators: tuple[str, ...]
    kind: str = "relation"


@dataclass(frozen=True, slots=True)
class DiscreteObject:
    id: str
    ownership: str
    state_ref: StateHandle
    initial: str
    values: tuple[str, ...]
    transitions: tuple[tuple[str, str], ...]
    allowed_operators: tuple[str, ...]
    kind: str = "discrete"


@dataclass(frozen=True, slots=True)
class DerivedObject:
    id: str
    ownership: str
    state_ref: StateHandle
    value_type: str
    source_objects: tuple[str, ...]
    derivation_law_ids: tuple[str, ...]
    writable: bool
    allowed_operators: tuple[str, ...]
    kind: str = "derived"


CatalogObject = (
    FieldObject | StockObject | ProcessObject | RelationObject
    | DiscreteObject | DerivedObject
)


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    id: str
    operator_kind: str
    targets: tuple[str, ...]
    scopes: tuple[str, ...]
    actions: tuple[str, ...]
    lifecycles: tuple[str, ...]
    numeric_limits: Mapping[str, float]
    privileges: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EffectSlotSpec:
    id: str
    slot_kind: str
    target_object_id: str
    storage_ref: StateHandle


@dataclass(frozen=True, slots=True)
class ObjectCatalog:
    protocol: str
    catalog_id: str
    limits: CatalogLimits
    objects: tuple[CatalogObject, ...]
    capabilities: tuple[CapabilitySpec, ...]
    effect_slots: tuple[EffectSlotSpec, ...]

    @property
    def object_index(self) -> Mapping[str, CatalogObject]:
        return MappingProxyType({item.id: item for item in self.objects})

    @property
    def capability_index(self) -> Mapping[str, CapabilitySpec]:
        return MappingProxyType({item.id: item for item in self.capabilities})

    @property
    def slot_index(self) -> Mapping[str, EffectSlotSpec]:
        return MappingProxyType({item.id: item for item in self.effect_slots})


@dataclass(frozen=True, slots=True)
class OperatorSpec:
    id: str
    kind: str
    capability_id: str
    scope: str
    target_object_id: str
    parameters: Mapping[str, Any]
    lifecycle_mode: str
    lifecycle_steps: int | None
    source_pointer: str


@dataclass(frozen=True, slots=True)
class MechanismSpec:
    protocol: str
    id: str
    name: str
    scope_kind: str
    scope_anchor: str
    capability_ids: tuple[str, ...]
    max_instances: int
    operators: tuple[OperatorSpec, ...]
