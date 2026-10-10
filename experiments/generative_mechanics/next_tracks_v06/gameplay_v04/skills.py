"""Skill and passive blueprints lowered through the frozen Gate 2 contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping

from .actions import ActionDefinition, parse_action_definition
from .conditions import ConditionSpec, parse_condition
from .contracts import GameplayContractError
from .effects import EffectSpec, parse_effect
from .hooks import HookSpec
from .materials import MaterialAuthority
from .status import DurationSpec, StatusSpec


_ID = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")
_EFFECT_COST = {
    "damage": 2.0, "heal": 2.0, "shield": 2.0, "add_resource": 2.0,
    "apply_status": 3.0, "modify_field": 2.0, "modify_attractor": 3.0,
    "modify_rate": 3.0, "grant_trait": 3.0,
}


@dataclass(frozen=True, slots=True)
class SkillBlueprint:
    id: str
    version: int
    kind: str
    trigger: str
    condition: ConditionSpec
    duration: DurationSpec | None
    effects: tuple[EffectSpec, ...]
    budget_limit: float
    budget_used: float
    max_firings_per_root: int
    action: ActionDefinition
    canonical_hash: str
    material_ids: tuple[str, ...]
    canonical_document_json: str
    material_authority: MaterialAuthority


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    skill_id: str
    version: int
    canonical_hash: str
    kind: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class MechanismRegistryManifest:
    epoch: int
    entries: tuple[RegistryEntry, ...]


def parse_skill_blueprint(raw: Any, statuses: Mapping[str, StatusSpec], authority: MaterialAuthority,
                          path: str = "$.skill") -> SkillBlueprint:
    required = {"protocol", "kind", "id", "version", "trigger", "condition", "duration",
                "cost", "scope", "effects", "budget", "max_firings_per_root", "material_ids"}
    if not isinstance(raw, dict) or set(raw) != required or raw.get("protocol") != "pmw-gameplay-v0.4":
        raise GameplayContractError(f"{path} has missing/unknown fields or invalid protocol")
    kind = raw["kind"]
    if kind not in {"skill_blueprint", "passive_blueprint"}:
        raise GameplayContractError(f"{path}.kind is invalid")
    skill_id = _identifier(raw["id"], f"{path}.id")
    version = raw["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise GameplayContractError(f"{path}.version is invalid")
    trigger = raw["trigger"]
    allowed_triggers = {"on_use"} if kind == "skill_blueprint" else {
        "action_started", "attack_applied", "damage_resolved", "status_changed",
        "weather_changed", "resource_harvested",
    }
    if trigger not in allowed_triggers:
        raise GameplayContractError(f"{path}.trigger is invalid for {kind}")
    condition = parse_condition(raw["condition"], f"{path}.condition")
    duration = _duration(raw["duration"], f"{path}.duration")
    if not isinstance(raw["effects"], list) or not raw["effects"]:
        raise GameplayContractError(f"{path}.effects must be non-empty")
    effects = tuple(parse_effect(item, statuses, f"{path}.effects[{i}]") for i, item in enumerate(raw["effects"]))
    if len({item.id for item in effects}) != len(effects):
        raise GameplayContractError(f"{path}.effects contains duplicate IDs")
    if any(item.kind not in authority.effect_kinds for item in effects):
        raise GameplayContractError(f"{path}.effects exceeds material effect authorization")
    if any(item.target.kind not in authority.selectors for item in effects):
        raise GameplayContractError(f"{path}.effects exceeds material scope authorization")
    material_ids = raw["material_ids"]
    if not isinstance(material_ids, list) or tuple(sorted(material_ids)) != authority.material_ids:
        raise GameplayContractError(f"{path}.material_ids does not match the trusted material authority")
    budget = raw["budget"]
    if not isinstance(budget, dict) or set(budget) != {"limit"}:
        raise GameplayContractError(f"{path}.budget is invalid")
    limit = _number(budget["limit"], f"{path}.budget.limit")
    if limit <= 0 or limit > authority.budget_points:
        raise GameplayContractError(f"{path}.budget.limit exceeds material authority")
    firings = raw["max_firings_per_root"]
    if isinstance(firings, bool) or not isinstance(firings, int) or not 1 <= firings <= 8:
        raise GameplayContractError(f"{path}.max_firings_per_root must be in [1, 8]")
    used = sum(_effect_cost(item) for item in effects) + (0.5 if kind == "passive_blueprint" else 0.0)
    if used > limit:
        raise GameplayContractError(f"{path} compound effects exceed the shared budget")
    action_raw = {
        "id": skill_id, "version": version, "action_type": "skill", "cost": raw["cost"],
        "scope": raw["scope"], "effects": raw["effects"],
    }
    action = parse_action_definition(action_raw, statuses, f"{path}.action")
    if kind == "passive_blueprint" and (action.cost.mana != 0 or action.cost.duration != 1):
        raise GameplayContractError(f"{path} passive hook action must use the neutral 1/0 cost")
    canonical_text = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
    canonical = canonical_text.encode()
    return SkillBlueprint(skill_id, version, kind, trigger, condition, duration, effects, limit, used,
                          firings, action, hashlib.sha256(canonical).hexdigest(), authority.material_ids,
                          canonical_text, authority)


def passive_hook(blueprint: SkillBlueprint) -> HookSpec:
    if blueprint.kind != "passive_blueprint":
        raise GameplayContractError("only PassiveBlueprint creates a Hook")
    return HookSpec(f"passive_{blueprint.id}_v{blueprint.version}", blueprint.trigger, blueprint.condition,
                    tuple(item.id for item in blueprint.effects), blueprint.id,
                    blueprint.max_firings_per_root, 0)


def registry_manifest(skills: tuple[SkillBlueprint, ...], *, epoch: int = 0) -> MechanismRegistryManifest:
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
        raise GameplayContractError("registry epoch must be a non-negative integer")
    keys = [(item.id, item.version) for item in skills]
    if len(keys) != len(set(keys)):
        raise GameplayContractError("duplicate skill version in registry manifest")
    latest: dict[str, int] = {}
    for item in skills:
        latest[item.id] = max(latest.get(item.id, 0), item.version)
    entries = tuple(RegistryEntry(item.id, item.version, item.canonical_hash, item.kind, True)
                    for item in sorted(skills, key=lambda row: (row.id, row.version)))
    return MechanismRegistryManifest(epoch, entries)


def _duration(raw: Any, path: str) -> DurationSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"unit", "amount"} or raw["unit"] not in {"world_tick", "combat_round", "owner_turn"}:
        raise GameplayContractError(f"{path} is invalid")
    amount = raw["amount"]
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
        raise GameplayContractError(f"{path}.amount must be positive")
    return DurationSpec(raw["unit"], amount)


def _effect_cost(effect: EffectSpec) -> float:
    cost = _EFFECT_COST[effect.kind] + 0.25 * len(effect.terms)
    if effect.duration is not None:
        cost += min(effect.duration, 20) * 0.1
    if effect.sensing != "none" or effect.evadable:
        cost += 0.25
    return cost


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GameplayContractError(f"{path} must be finite numeric")
    return float(value)


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise GameplayContractError(f"{path} is invalid")
    return value
