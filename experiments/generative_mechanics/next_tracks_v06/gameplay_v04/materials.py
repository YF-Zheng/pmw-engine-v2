"""Strict material provenance and capability budgets for generated skills."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Iterable

from .contracts import GameplayContractError
from .effects import EFFECT_KINDS


MATERIAL_TIERS = ("common", "fine", "rare", "epic", "legendary")
REGION_RARITIES = ("abundant", "uncommon", "scarce", "unique")
_ID = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")


@dataclass(frozen=True, slots=True)
class MaterialTrait:
    id: str
    effect_kinds: tuple[str, ...]
    selectors: tuple[str, ...]
    budget_points: float


@dataclass(frozen=True, slots=True)
class MaterialDefinition:
    id: str
    tier: str
    region_rarity: str
    traits: tuple[MaterialTrait, ...]


@dataclass(frozen=True, slots=True)
class MaterialAuthority:
    material_ids: tuple[str, ...]
    effect_kinds: tuple[str, ...]
    selectors: tuple[str, ...]
    budget_points: float


def parse_material(raw: Any, path: str = "$.material") -> MaterialDefinition:
    data = _strict(raw, {"id", "tier", "region_rarity", "traits"}, path)
    material_id = _identifier(data["id"], f"{path}.id")
    if data["tier"] not in MATERIAL_TIERS:
        raise GameplayContractError(f"{path}.tier is invalid")
    if data["region_rarity"] not in REGION_RARITIES:
        raise GameplayContractError(f"{path}.region_rarity is invalid")
    if not isinstance(data["traits"], list) or not data["traits"]:
        raise GameplayContractError(f"{path}.traits must be a non-empty list")
    traits = tuple(_parse_trait(item, f"{path}.traits[{index}]") for index, item in enumerate(data["traits"]))
    if len({item.id for item in traits}) != len(traits):
        raise GameplayContractError(f"{path}.traits contains duplicates")
    return MaterialDefinition(material_id, data["tier"], data["region_rarity"], traits)


def material_authority(materials: Iterable[MaterialDefinition]) -> MaterialAuthority:
    items = tuple(materials)
    if not items or len({item.id for item in items}) != len(items):
        raise GameplayContractError("skill materials must be a non-empty unique set")
    kinds = sorted({kind for item in items for trait in item.traits for kind in trait.effect_kinds})
    selectors = sorted({scope for item in items for trait in item.traits for scope in trait.selectors})
    budget = sum(trait.budget_points for item in items for trait in item.traits)
    return MaterialAuthority(tuple(sorted(item.id for item in items)), tuple(kinds), tuple(selectors), budget)


def _parse_trait(raw: Any, path: str) -> MaterialTrait:
    data = _strict(raw, {"id", "effect_kinds", "selectors", "budget_points"}, path)
    kinds = _string_set(data["effect_kinds"], f"{path}.effect_kinds")
    if any(item not in EFFECT_KINDS for item in kinds):
        raise GameplayContractError(f"{path}.effect_kinds contains an unknown Effect")
    selectors = _string_set(data["selectors"], f"{path}.selectors")
    allowed = {"self", "target_actor", "current_area", "linked_object", "adjacent_area"}
    if any(item not in allowed for item in selectors):
        raise GameplayContractError(f"{path}.selectors contains an unknown scope")
    budget = data["budget_points"]
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget <= 0:
        raise GameplayContractError(f"{path}.budget_points must be positive finite")
    return MaterialTrait(_identifier(data["id"], f"{path}.id"), kinds, selectors, float(budget))


def _strict(raw: Any, fields: set[str], path: str) -> dict:
    if not isinstance(raw, dict) or set(raw) != fields:
        raise GameplayContractError(f"{path} has missing or unknown fields")
    return raw


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise GameplayContractError(f"{path} is invalid")
    return value


def _string_set(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise GameplayContractError(f"{path} must be a non-empty string list")
    if len(set(value)) != len(value):
        raise GameplayContractError(f"{path} contains duplicates")
    return tuple(value)
