"""Strict sequential combat rounds over the unified Actor action API."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Mapping

from .actions import (
    ACTOR_COMPONENT,
    ActionOutcome,
    ActionRegistry,
    ActionRequest,
    authorize_primary_action,
    submit_primary_action,
)
from .contracts import GameplayContractError
from .runtime import GameplaySession, advance_world_tick, run_phase_event
from .time_ledger import (
    TIME_BUDGET_COMPONENT,
    TimeSpendResult,
    preflight_world_time,
    spend_world_time,
)


@dataclass(frozen=True, slots=True)
class CombatRoundResult:
    round_index: int
    actor_order: tuple[str, ...]
    outcomes: tuple[ActionOutcome, ...]
    skipped: tuple[str, ...]
    combat_phase_result: object
    world_tick_result: object
    time_spend_result: TimeSpendResult | None = None


def run_combat_round(session, registry: ActionRegistry, *, round_index: int,
                     actor_order: tuple[str, ...], requests: Mapping[str, ActionRequest],
                     time_policy: str = "finite") -> CombatRoundResult:
    if isinstance(round_index, bool) or not isinstance(round_index, int) or round_index < 1:
        raise GameplayContractError("round_index must be positive")
    if len(actor_order) != len(set(actor_order)): raise GameplayContractError("actor_order contains duplicates")
    if set(requests) - set(actor_order): raise GameplayContractError("request actor is outside encounter order")
    if time_policy not in {"finite", "unbudgeted_fixture"}:
        raise GameplayContractError("unknown combat time policy")
    has_budget = any(TIME_BUDGET_COMPONENT in entity.components for entity in session.state.entities.values())
    if time_policy == "finite":
        preflight_world_time(session, 1, reason="combat")
    elif has_budget:
        raise GameplayContractError("unbudgeted fixture mode cannot bypass a formal time budget")

    # Reject controller-level identity and equipment violations before owner_turn
    # can expire Statuses or otherwise mutate the encounter.
    for actor_id in actor_order:
        entity = session.state.entities.get(actor_id)
        if entity is None or ACTOR_COMPONENT not in entity.components:
            raise GameplayContractError("encounter contains non-Actor")
        request = requests.get(actor_id)
        if request is not None and request.actor_id != actor_id:
            raise GameplayContractError("controller request actor mismatch")
        if request is not None and entity.components[ACTOR_COMPONENT]["hp"] > 0:
            authorize_primary_action(session, registry, request)

    # A finite combat round is one gameplay transaction.  The attached Engine
    # and formal WorldState are cloned so any late execution or Tick failure
    # leaves the caller's live session unchanged.
    working = session
    if time_policy == "finite":
        staged_runtime = session.runtime.engine.attach(deepcopy(session.state))
        staged_runtime.stats = deepcopy(session.runtime.stats)
        staged_runtime.revision = session.runtime.revision
        staged_runtime.object_revision = session.runtime.object_revision
        staged_runtime.state_closure_known = session.runtime.state_closure_known
        working = GameplaySession(staged_runtime, session.profiles)
    outcomes, skipped = [], []
    for actor_id in actor_order:
        entity = working.state.entities[actor_id]
        if entity.components[ACTOR_COMPONENT]["hp"] <= 0:
            skipped.append(actor_id); continue
        run_phase_event(working, "owner_turn", actor_id=actor_id)
        request = requests.get(actor_id)
        if request is None:
            skipped.append(actor_id); continue
        outcomes.append(submit_primary_action(working, registry, request))
    combat_phase = run_phase_event(working, "combat_round")
    time_spend = None
    if time_policy == "finite":
        time_spend = spend_world_time(working, 1, reason="combat")
        world_tick = time_spend.ticks[0]
        session.runtime = working.runtime
    else:
        world_tick = advance_world_tick(working)
    return CombatRoundResult(
        round_index, actor_order, tuple(outcomes), tuple(skipped),
        combat_phase, world_tick, time_spend,
    )


class HumanController:
    def request(self, raw: ActionRequest) -> ActionRequest:
        return raw


class AIController:
    def request(self, raw: ActionRequest) -> ActionRequest:
        return raw


def run_gate2_demo() -> dict:
    """Small deterministic Player/Monster combat using only formal PMW writes."""
    from .action_compiler import build_action_session
    from .basics import basic_registry
    from .blueprints import instantiate_actor, instantiate_area, parse_actor_blueprint, parse_area_blueprint
    from .runtime import clock_entity, discover_profiles
    from .worlds import build_gameplay_world
    actor_blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4", "kind": "actor_blueprint", "id": "demo_actor",
        "hp": {"max": 50, "initial": 50}, "mana": {"max": 30, "initial": 10, "dynamics": None},
        "attributes": {"power": 5, "control": 4, "resilience": 4, "agility": 3}, "traits": [],
    })
    area_blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint", "id": "demo_area",
        "fields": [{"id": "mist", "domain": {"min": 0, "max": 1}, "initial": .3,
                    "target": .2, "rate": .1, "curve": "linear",
                    "max_persistent_patches": 2, "max_temporary_modifiers": 2}],
    })
    hero = instantiate_actor(actor_blueprint, "demo_hero", controller="human")
    enemy = instantiate_actor(actor_blueprint, "demo_enemy", controller="ai")
    area = instantiate_area(area_blueprint, "demo_arena")
    world = build_gameplay_world("gate2_demo", areas=[area], actors=[hero, enemy],
                                 placements=[(hero.id, area.id), (enemy.id, area.id)])
    clock = clock_entity(); world.entities[clock.id] = clock
    registry = basic_registry()
    session = build_action_session(world, discover_profiles(world), registry)
    first = run_combat_round(session, registry, round_index=1, actor_order=(hero.id, enemy.id), requests={
        hero.id: ActionRequest("demo_guard", hero.id, "basic_guard"),
        enemy.id: ActionRequest("demo_attack_1", enemy.id, "basic_attack", hero.id),
    }, time_policy="unbudgeted_fixture")
    second = run_combat_round(session, registry, round_index=2, actor_order=(hero.id, enemy.id), requests={
        hero.id: ActionRequest("demo_attack_2", hero.id, "basic_attack", enemy.id),
        enemy.id: ActionRequest("demo_wait", enemy.id, "basic_wait"),
    }, time_policy="unbudgeted_fixture")
    actors = {key: dict(session.state.entities[key].components[ACTOR_COMPONENT]) for key in (hero.id, enemy.id)}
    return {"rounds": [
        {"round": first.round_index, "actions": [item.definition.id for item in first.outcomes], "world_step": first.world_tick_result.step},
        {"round": second.round_index, "actions": [item.definition.id for item in second.outcomes], "world_step": second.world_tick_result.step},
    ], "actors": actors, "world_tick": session.state.entities[clock.id].components["pmw_gameplay_clock"]["last_completed_step"]}


if __name__ == "__main__":
    print(json.dumps(run_gate2_demo(), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
