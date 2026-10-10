"""Immutable Gate 1 gameplay contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


PROTOCOL_ID = "pmw-gameplay-v0.4"
CURVES = ("linear", "distance_squared")
SELECTOR_KINDS = (
    "self", "target_actor", "current_area", "linked_object", "adjacent_area",
)
LAYERS = ("persistent", "temporary")
ATTRIBUTES = ("power", "control", "resilience", "agility")


class GameplayContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    id: str
    minimum: float
    maximum: float
    initial: float
    target: float
    rate: float
    curve: str
    max_persistent_patches: int = 4
    max_temporary_modifiers: int = 4

    @property
    def width(self) -> float:
        return self.maximum - self.minimum

    @property
    def stable_rate_limit(self) -> float:
        return 1.0 if self.curve == "linear" else 1.0 / self.width


@dataclass(frozen=True, slots=True)
class AreaBlueprint:
    id: str
    fields: tuple[FieldDefinition, ...]
    ecology_state: str = "stable"


@dataclass(frozen=True, slots=True)
class ActorBlueprint:
    id: str
    max_hp: float
    initial_hp: float
    max_mana: float
    initial_mana: float
    attributes: Mapping[str, float]
    traits: tuple[str, ...]
    mana_dynamics: FieldDefinition | None = None


@dataclass(frozen=True, slots=True)
class ScopedSelector:
    kind: str
    relation_type: str | None = None


@dataclass(frozen=True, slots=True)
class ScopeCapability:
    id: str
    selectors: tuple[str, ...]
    relation_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectorContext:
    actor_id: str
    target_actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class DynamicsSource:
    source_id: str
    owner: str
    target: float | None = None
    target_weight: float = 0.0
    rate_add: float = 0.0
    rate_multiplier: float = 1.0
    curve: str | None = None
    curve_priority: int | None = None
    duration_ticks: int | None = None


@dataclass(frozen=True, slots=True)
class FieldProfile:
    entity_id: str
    field: FieldDefinition
    mirror_path: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class TickResult:
    step: int
    time: float
    event_result: object
    snapshot: object
