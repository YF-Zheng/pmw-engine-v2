"""Strict sequential combat rounds over the unified Actor action API."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping

from .actions import ACTOR_COMPONENT, ActionOutcome, ActionRegistry, ActionRequest, resolve_action
from .contracts import GameplayContractError
from .runtime import advance_world_tick, run_phase_event


@dataclass(frozen=True, slots=True)
class CombatRoundResult:
    round_index: int
    actor_order: tuple[str, ...]
    outcomes: tuple[ActionOutcome, ...]
    skipped: tuple[str, ...]
    combat_phase_result: object
    world_tick_result: object


def run_combat_round(session, registry: ActionRegistry, *, round_index: int,
                     actor_order: tuple[str, ...], requests: Mapping[str, ActionRequest]) -> CombatRoundResult:
    if isinstance(round_index, bool) or not isinstance(round_index, int) or round_index < 1:
        raise GameplayContractError("round_index must be positive")
    if len(actor_order) != len(set(actor_order)): raise GameplayContractError("actor_order contains duplicates")
    if set(requests) - set(actor_order): raise GameplayContractError("request actor is outside encounter order")
    outcomes, skipped = [], []
    for actor_id in actor_order:
        entity = session.state.entities.get(actor_id)
        if entity is None or ACTOR_COMPONENT not in entity.components: raise GameplayContractError("encounter contains non-Actor")
        if entity.components[ACTOR_COMPONENT]["hp"] <= 0:
            skipped.append(actor_id); continue
        run_phase_event(session, "owner_turn", actor_id=actor_id)
        request = requests.get(actor_id)
        if request is None:
            skipped.append(actor_id); continue
        if request.actor_id != actor_id: raise GameplayContractError("controller request actor mismatch")
        outcomes.append(resolve_action(session, registry, request))
    combat_phase = run_phase_event(session, "combat_round")
    world_tick = advance_world_tick(session)
    return CombatRoundResult(round_index, actor_order, tuple(outcomes), tuple(skipped), combat_phase, world_tick)


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
    })
    second = run_combat_round(session, registry, round_index=2, actor_order=(hero.id, enemy.id), requests={
        hero.id: ActionRequest("demo_attack_2", hero.id, "basic_attack", enemy.id),
        enemy.id: ActionRequest("demo_wait", enemy.id, "basic_wait"),
    })
    actors = {key: dict(session.state.entities[key].components[ACTOR_COMPONENT]) for key in (hero.id, enemy.id)}
    return {"rounds": [
        {"round": first.round_index, "actions": [item.definition.id for item in first.outcomes], "world_step": first.world_tick_result.step},
        {"round": second.round_index, "actions": [item.definition.id for item in second.outcomes], "world_step": second.world_tick_result.step},
    ], "actors": actors, "world_tick": session.state.entities[clock.id].components["pmw_gameplay_clock"]["last_completed_step"]}


if __name__ == "__main__":
    print(json.dumps(run_gate2_demo(), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
