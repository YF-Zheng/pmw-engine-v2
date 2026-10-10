"""Closed high-level Effect template schemas."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .attributes import AttributeTerm, parse_attribute_term
from .conditions import ConditionSpec, parse_condition
from .contracts import GameplayContractError, ScopedSelector
from .selectors import parse_selector
from .status import StatusSpec


EFFECT_KINDS = ("damage", "heal", "shield", "add_resource", "apply_status", "modify_field",
                "modify_attractor", "modify_rate", "grant_trait")


@dataclass(frozen=True, slots=True)
class EffectSpec:
    id: str
    kind: str
    target: ScopedSelector
    commitment: str
    condition: ConditionSpec
    amount: float | None = None
    resource: str | None = None
    field_id: str | None = None
    trait_id: str | None = None
    status_id: str | None = None
    duration: int | None = None
    terms: tuple[AttributeTerm, ...] = ()
    sensing: str = "none"
    evadable: bool = False


def parse_effect(raw: Any, statuses: Mapping[str, StatusSpec], path: str = "$.effect") -> EffectSpec:
    common = {"id", "kind", "target", "commitment"}
    optional = {"condition", "attribute_terms", "targeting"}
    if not isinstance(raw, dict) or not common <= set(raw): raise GameplayContractError(f"{path} is missing common fields")
    kind = raw["kind"]
    fields = {
        "damage": {"amount"}, "heal": {"amount"}, "shield": {"amount"},
        "add_resource": {"resource", "amount"}, "apply_status": {"status_id"},
        "modify_field": {"field_id", "amount"}, "modify_attractor": {"field_id", "amount", "duration"},
        "modify_rate": {"field_id", "amount", "duration"}, "grant_trait": {"trait_id", "duration"},
    }
    if kind not in fields: raise GameplayContractError(f"{path}.kind is invalid")
    allowed = common | optional | fields[kind]
    if set(raw) != (common | fields[kind] | (set(raw) & optional)) or set(raw) - allowed:
        raise GameplayContractError(f"{path} has missing or unknown fields")
    if not isinstance(raw["id"], str) or not raw["id"]: raise GameplayContractError(f"{path}.id is invalid")
    if raw["commitment"] not in {"required", "conditional"}: raise GameplayContractError(f"{path}.commitment is invalid")
    target = parse_selector(raw["target"])
    condition = parse_condition(raw.get("condition"), f"{path}.condition")
    terms_raw = raw.get("attribute_terms", [])
    if not isinstance(terms_raw, list): raise GameplayContractError(f"{path}.attribute_terms must be a list")
    terms = tuple(parse_attribute_term(item, f"{path}.attribute_terms[{i}]") for i, item in enumerate(terms_raw))
    targeting = raw.get("targeting", {"sensing": "none", "evadable": False})
    if not isinstance(targeting, dict) or set(targeting) != {"sensing", "evadable"} or targeting["sensing"] not in {"none", "visual", "mana"} or not isinstance(targeting["evadable"], bool):
        raise GameplayContractError(f"{path}.targeting is invalid")
    if targeting["evadable"] and not any(term.kind == "check" for term in terms):
        raise GameplayContractError(f"{path}.targeting.evadable requires an explicit check term")
    amount = raw.get("amount")
    if amount is not None:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount): raise GameplayContractError(f"{path}.amount is invalid")
        amount = float(amount)
    if kind in {"damage", "heal", "shield"} and amount is not None and amount < 0: raise GameplayContractError(f"{path}.amount must be non-negative")
    resource = raw.get("resource")
    if resource is not None and resource not in {"hp", "mana", "shield"}: raise GameplayContractError(f"{path}.resource is invalid")
    status_id = raw.get("status_id")
    if status_id is not None and status_id not in statuses: raise GameplayContractError(f"{path}.status_id is unknown")
    field_id = raw.get("field_id")
    if field_id is not None and (not isinstance(field_id, str) or not field_id): raise GameplayContractError(f"{path}.field_id is invalid")
    trait = raw.get("trait_id")
    if trait is not None and (not isinstance(trait, str) or not trait): raise GameplayContractError(f"{path}.trait_id is invalid")
    duration = raw.get("duration")
    if duration is not None and (isinstance(duration, bool) or not isinstance(duration, int) or duration < 1): raise GameplayContractError(f"{path}.duration is invalid")
    return EffectSpec(raw["id"], kind, target, raw["commitment"], condition, amount, resource, field_id,
                      trait, status_id, duration, terms, targeting["sensing"], targeting["evadable"])
