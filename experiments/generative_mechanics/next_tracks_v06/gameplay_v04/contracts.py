"""Immutable Gate 1 gameplay contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import math


PROTOCOL_ID = "pmw-gameplay-v0.4"
CURVES = ("linear", "distance_squared", "none")
SELECTOR_KINDS = (
    "self", "target_actor", "current_area", "linked_object", "adjacent_area",
)
LAYERS = ("persistent", "temporary")
ATTRIBUTES = ("power", "control", "resilience", "agility")


class GameplayContractError(ValueError):
    pass


def validate_curve_policy(curve: str, rate: float) -> None:
    if curve not in CURVES:
        raise GameplayContractError(f"unknown dynamics curve {curve!r}")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate):
        raise GameplayContractError("base rate must be finite")
    if rate < 0.0:
        raise GameplayContractError("base rate must be non-negative")
    if curve == "none" and rate != 0.0:
        raise GameplayContractError("curve none requires a zero base rate")


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
        if self.curve == "linear":
            return 1.0
        if self.curve == "distance_squared":
            return 1.0 / self.width
        if self.curve == "none":
            return 0.0
        raise GameplayContractError(f"unknown dynamics curve {self.curve!r}")


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
