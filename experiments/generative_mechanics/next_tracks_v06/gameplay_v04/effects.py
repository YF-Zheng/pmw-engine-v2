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
                "modify_attractor", "modify_rate", "grant_trait", "process_start",
                "process_modify")


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
    process_template_id: str | None = None
    process_rate: float | None = None
    process_remaining_ticks: int | None = None


def parse_effect(raw: Any, statuses: Mapping[str, StatusSpec], path: str = "$.effect") -> EffectSpec:
    common = {"id", "kind", "target", "commitment"}
    optional = {"condition", "attribute_terms", "targeting"}
    process_modify_optional = {"process_rate", "process_remaining_ticks"}
    if not isinstance(raw, dict) or not common <= set(raw): raise GameplayContractError(f"{path} is missing common fields")
    kind = raw["kind"]
    fields = {
        "damage": {"amount"}, "heal": {"amount"}, "shield": {"amount"},
        "add_resource": {"resource", "amount"}, "apply_status": {"status_id"},
        "modify_field": {"field_id", "amount"}, "modify_attractor": {"field_id", "amount", "duration"},
        "modify_rate": {"field_id", "amount", "duration"}, "grant_trait": {"trait_id", "duration"},
        "process_start": {"process_template_id"},
        "process_modify": {"process_template_id"} | process_modify_optional,
    }
    if kind not in fields: raise GameplayContractError(f"{path}.kind is invalid")
    allowed = common | optional | fields[kind]
    required_fields = fields[kind]
    if kind == "process_modify":
        required_fields = required_fields - process_modify_optional
    required = common | required_fields
    missing_required = not required <= set(raw)
    if kind == "process_modify" and not any(
            raw.get(key) is not None for key in process_modify_optional):
        missing_required = True
    if missing_required or set(raw) - allowed:
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
    process_template_id = raw.get("process_template_id")
    if kind in {"process_start", "process_modify"}:
        if target.kind != "current_area":
            raise GameplayContractError(f"{path}.target must be current_area for {kind}")
        if raw["commitment"] != "required":
            raise GameplayContractError(f"{path}.commitment must be required for {kind}")
        if terms:
            raise GameplayContractError(f"{path}.attribute_terms are not allowed for {kind}")
        if targeting != {"sensing": "none", "evadable": False}:
            raise GameplayContractError(f"{path}.targeting is not allowed for {kind}")
        if (not isinstance(process_template_id, str) or not process_template_id
                or len(process_template_id) > 128):
            raise GameplayContractError(f"{path}.process_template_id is invalid")
    process_rate = None
    process_remaining_ticks = None
    if kind == "process_modify":
        has_rate = raw.get("process_rate") is not None
        has_remaining = raw.get("process_remaining_ticks") is not None
        if not has_rate and not has_remaining:
            raise GameplayContractError(
                f"{path}.process_modify requires process_rate or process_remaining_ticks"
            )
        if "process_rate" in raw:
            process_rate = raw["process_rate"]
            if (isinstance(process_rate, bool)
                    or not isinstance(process_rate, (int, float))
                    or not math.isfinite(process_rate)
                    or process_rate <= 0):
                raise GameplayContractError(f"{path}.process_rate must be finite positive")
            process_rate = float(process_rate)
        if "process_remaining_ticks" in raw:
            process_remaining_ticks = raw["process_remaining_ticks"]
            if (isinstance(process_remaining_ticks, bool)
                    or not isinstance(process_remaining_ticks, int)
                    or process_remaining_ticks < 1):
                raise GameplayContractError(
                    f"{path}.process_remaining_ticks must be a positive integer"
                )
    amount = raw.get("amount")
    if kind in {"process_start", "process_modify"}:
        amount = None
    elif amount is not None:
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
                      trait, status_id, duration, terms, targeting["sensing"], targeting["evadable"],
                      process_template_id, process_rate, process_remaining_ticks)
