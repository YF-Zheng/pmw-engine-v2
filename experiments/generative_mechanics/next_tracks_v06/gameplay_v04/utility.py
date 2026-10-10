"""Bounded, explainable utility over actor-safe observations."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .contracts import GameplayContractError
from .observation import ActorObservation


@dataclass(frozen=True, slots=True)
class UtilityConfig:
    self_hp: float = 40.0
    opponent_hp: float = 45.0
    shield: float = 8.0
    mana: float = 6.0
    status: float = 4.0
    terminal: float = 100.0
    future_potential: float = 5.0
    discount: float = 0.85

    def __post_init__(self):
        values = (self.self_hp, self.opponent_hp, self.shield, self.mana,
                  self.status, self.terminal, self.future_potential, self.discount)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
            raise GameplayContractError("utility weights must be finite numbers")
        if not 0.0 < self.discount < 1.0:
            raise GameplayContractError("utility discount must be in (0, 1)")


@dataclass(frozen=True, slots=True)
class UtilityTerm:
    name: str
    value: float
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UtilityScore:
    total: float
    terms: tuple[UtilityTerm, ...]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "terms": [
                {"name": item.name, "value": item.value, "evidence": list(item.evidence)}
                for item in self.terms
            ],
        }


class UtilityEvaluator:
    def __init__(self, config: UtilityConfig | None = None):
        self.config = config or UtilityConfig()

    def evaluate(
        self,
        before: ActorObservation,
        after: ActorObservation,
        *,
        perspective_actor_id: str,
        future_potential_delta: float = 0.0,
        depth: int = 0,
    ) -> UtilityScore:
        left, right = before.to_dict(), after.to_dict()
        if perspective_actor_id not in left["actors"] or perspective_actor_id not in right["actors"]:
            raise GameplayContractError("utility perspective is not observed")
        own_before, own_after = left["actors"][perspective_actor_id], right["actors"][perspective_actor_id]
        opponents = tuple(sorted(set(left["actors"]) & set(right["actors"]) - {perspective_actor_id}))
        terms = (
            UtilityTerm("self_hp", self.config.self_hp * (_ratio(own_after, "hp", "max_hp") - _ratio(own_before, "hp", "max_hp")),
                        (f"actor:{perspective_actor_id}:hp",)),
            UtilityTerm("opponent_hp", self.config.opponent_hp * sum(
                _ratio(left["actors"][key], "hp", "max_hp") - _ratio(right["actors"][key], "hp", "max_hp")
                for key in opponents
            ), tuple(f"actor:{key}:hp" for key in opponents)),
            UtilityTerm("shield", self.config.shield * (
                _bounded(own_after["shield"], own_after["max_hp"]) - _bounded(own_before["shield"], own_before["max_hp"])
            ), (f"actor:{perspective_actor_id}:shield",)),
            UtilityTerm("mana", self.config.mana * (_ratio(own_after, "mana", "max_mana") - _ratio(own_before, "mana", "max_mana")),
                        (f"actor:{perspective_actor_id}:mana",)),
            UtilityTerm("status", self.config.status * (
                _status_value(right, perspective_actor_id) - _status_value(left, perspective_actor_id)
            ), (f"actor:{perspective_actor_id}:statuses",)),
            UtilityTerm("opponent_status", self.config.status * sum(
                _status_value(left, key) - _status_value(right, key)
                for key in opponents
            ), tuple(f"actor:{key}:statuses" for key in opponents)),
            UtilityTerm("terminal", self.config.terminal * (
                (1.0 if own_after["hp"] > 0 and any(right["actors"][key]["hp"] <= 0 for key in opponents) else 0.0)
                - (1.0 if own_after["hp"] <= 0 else 0.0)
            ), ("terminal_state",)),
            UtilityTerm("future_potential", self.config.future_potential * max(-1.0, min(1.0, future_potential_delta)),
                        ("build_graph",)),
        )
        discount = self.config.discount ** depth
        discounted = tuple(UtilityTerm(term.name, term.value * discount, term.evidence) for term in terms)
        return UtilityScore(sum(item.value for item in discounted), discounted)


def _ratio(actor: dict, key: str, maximum: str) -> float:
    return _bounded(actor[key], actor[maximum])


def _bounded(value: float, maximum: float) -> float:
    return 0.0 if maximum <= 0 else max(0.0, min(1.0, float(value) / float(maximum)))


def _status_value(document: dict, actor_id: str) -> float:
    value = 0.0
    polarities = document.get("status_polarities", {})
    for row in document["actors"][actor_id]["statuses"]:
        polarity = polarities.get(row["spec_id"], "neutral")
        value += (1.0 if polarity == "buff" else -1.0 if polarity == "debuff" else 0.0) * min(1.0, row["stacks"])
    return value
