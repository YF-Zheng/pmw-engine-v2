"""Bounded event hooks with deterministic lineage and source deduplication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .conditions import ConditionSpec, parse_condition
from .contracts import GameplayContractError


TRIGGERS = ("action_started", "attack_applied", "damage_resolved", "status_changed",
            "weather_changed", "resource_harvested")


@dataclass(frozen=True, slots=True)
class HookSpec:
    id: str
    trigger: str
    condition: ConditionSpec
    effect_ids: tuple[str, ...]
    action_id: str
    max_firings_per_root: int
    cooldown: int = 0


@dataclass(frozen=True, slots=True)
class HookLineage:
    root_event_id: str
    parent_event_id: str | None
    depth: int
    remaining_budget: int
    fired_sources: tuple[str, ...] = ()

    def fire(self, source_key: str, *, max_depth: int = 16) -> "HookLineage":
        if self.depth >= max_depth or self.remaining_budget <= 0:
            raise GameplayContractError("hook cascade budget exhausted")
        if source_key in self.fired_sources:
            raise GameplayContractError("hook source already fired in this root lineage")
        return HookLineage(self.root_event_id, self.parent_event_id, self.depth + 1,
                           self.remaining_budget - 1, (*self.fired_sources, source_key))


def parse_hook(raw: Any, path: str = "$.hook") -> HookSpec:
    required = {"id", "trigger", "condition", "effect_ids", "action_id", "max_firings_per_root"}
    optional = {"cooldown"}
    if not isinstance(raw, dict) or set(raw) - required - optional or not required <= set(raw):
        raise GameplayContractError(f"{path} has missing or unknown fields")
    if not isinstance(raw["id"], str) or not raw["id"]: raise GameplayContractError(f"{path}.id is invalid")
    if raw["trigger"] not in TRIGGERS: raise GameplayContractError(f"{path}.trigger is invalid")
    effect_ids = raw["effect_ids"]
    if not isinstance(effect_ids, list) or not effect_ids or any(not isinstance(x, str) or not x for x in effect_ids) or len(set(effect_ids)) != len(effect_ids):
        raise GameplayContractError(f"{path}.effect_ids is invalid")
    budget = raw["max_firings_per_root"]
    cooldown = raw.get("cooldown", 0)
    for value, name, low in ((budget, "max_firings_per_root", 1), (cooldown, "cooldown", 0)):
        if isinstance(value, bool) or not isinstance(value, int) or value < low:
            raise GameplayContractError(f"{path}.{name} is invalid")
    if not isinstance(raw["action_id"], str) or not raw["action_id"]: raise GameplayContractError(f"{path}.action_id is invalid")
    return HookSpec(raw["id"], raw["trigger"], parse_condition(raw["condition"], f"{path}.condition"),
                    tuple(effect_ids), raw["action_id"], budget, cooldown)


def execute_hook(session, registry, hook: HookSpec, lineage: HookLineage, *, actor_id: str,
                 target_actor_id: str | None, trigger: str):
    """Execute a trusted hook action through the same PMW Effect pipeline."""
    from .actions import ActionRequest, _actor_view, _condition_context, resolve_action
    from .conditions import evaluate_condition
    if trigger != hook.trigger: raise GameplayContractError("hook trigger mismatch")
    if registry.hooks.get(hook.id) != hook: raise GameplayContractError("hook is not installed in the trusted registry")
    action = registry.actions.get(hook.action_id)
    if action is None or tuple(effect.id for effect in action.effects) != hook.effect_ids:
        raise GameplayContractError("hook effect bundle does not match its trusted action")
    request = ActionRequest(f"hook_{lineage.depth}_{hook.id}", actor_id, hook.action_id, target_actor_id)
    actor = session.state.entities.get(actor_id)
    target = session.state.entities.get(target_actor_id) if target_actor_id else None
    shadow = {actor_id: _actor_view(actor)}
    if target is not None: shadow[target_actor_id] = _actor_view(target)
    if not evaluate_condition(hook.condition, _condition_context(session, request, shadow)):
        return None, lineage
    cooldowns = actor.components.get("pmw_gameplay_hooks", {}).get("cooldowns", {})
    if float(cooldowns.get(hook.id, -1.0)) > session.state.sim_time:
        raise GameplayContractError("hook is on cooldown")
    next_lineage = lineage.fire(f"hook:{hook.id}")
    context = {"hook_id": hook.id, "cooldown_until": session.state.sim_time + hook.cooldown}
    return resolve_action(session, registry, request, execution_kind="hook", hook_context=context), next_lineage
