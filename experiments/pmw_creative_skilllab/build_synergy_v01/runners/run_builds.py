"""Run all preregistered Build Synergy arms in real Gameplay sessions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRequest
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import run_combat_round
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.hooks import HookLineage, execute_hook

from .shared import build_multi_skill_session, observe_session


ROOT = Path(__file__).resolve().parents[1]


def load_specs() -> list[dict[str, Any]]:
    return [json.loads(path.read_text()) for path in sorted((ROOT / "build_specs").glob("build_*.json"))]


def run_arm(spec: dict[str, Any], variant: dict[str, Any], arm_id: str) -> dict[str, Any]:
    arm = spec["arms"][arm_id]
    initial = variant["initial"]
    built = build_multi_skill_session(
        tuple(spec["skill_case_ids"]),
        environment=variant["environment"],
        field_overrides=variant.get("field_overrides"),
        hero_hp=initial["hero_hp"],
        hero_mana=initial["hero_mana"],
        target_hp=initial["target_hp"],
        target_mana=initial["target_mana"],
        target_traits=tuple(initial["target_traits"]),
        equip_skill_ids=tuple(arm["equip"]),
        disabled_weather_ids=tuple(variant.get("disabled_weather_ids", ())),
    )
    timeline = [observe_session(built.session)]
    rounds = []
    for round_index, action_id in enumerate(arm["actions"], 1):
        before_state = built.session.state.to_dict()
        rejected = None
        request = _request(built, spec, variant, arm_id, round_index, action_id)
        try:
            result = _combat_round(built, spec, variant, arm_id, round_index, request)
        except GameplayContractError as exc:
            if built.session.state.to_dict() != before_state:
                raise AssertionError("failed build action mutated WorldState") from exc
            rejected = {"action_id": action_id, "message": str(exc), "state_unchanged": True}
            fallback = ActionRequest(
                f"{spec['build_id']}:{variant['variant_id']}:{arm_id}:fallback:{round_index}",
                "synergy_hero",
                "basic_wait",
                "synergy_hero",
            )
            result = _combat_round(built, spec, variant, arm_id, round_index, fallback)

        round_row = {
            "round": round_index,
            "requested_player_action": action_id,
            "rejected": rejected,
            "actor_order": list(result.actor_order),
            "outcomes": [_outcome(row) for row in result.outcomes],
            "combat_phase_trace": result.combat_phase_result.trace.to_dict(),
            "world_tick_trace": result.world_tick_result.event_result.trace.to_dict(),
            "time_spend_trace": result.time_spend_result.event_result.trace.to_dict(),
            "manual_hook_dispatches": [],
        }
        weather_events = _weather_changed_events(result.world_tick_result.event_result.trace.to_dict())
        for weather_event in weather_events:
            for passive_id in arm.get("manual_passives", ()):
                hook = next(
                    item
                    for item in built.content.action_registry.hooks.values()
                    if item.action_id == passive_id
                )
                outcome, lineage = execute_hook(
                    built.session,
                    built.content.action_registry,
                    hook,
                    HookLineage(
                        weather_event["id"],
                        None,
                        0,
                        built.skills[passive_id].max_firings_per_root,
                    ),
                    actor_id="synergy_hero",
                    target_actor_id="synergy_target",
                    trigger="weather_changed",
                )
                if outcome is not None:
                    round_row["manual_hook_dispatches"].append({
                        "mode": "manual_trusted_hook_dispatch",
                        "source_event": weather_event,
                        "action_id": passive_id,
                        "lineage": {
                            "root_event_id": lineage.root_event_id,
                            "depth": lineage.depth,
                        },
                        "trace": outcome.event_result.trace.to_dict(),
                    })
        rounds.append(round_row)
        timeline.append(observe_session(built.session))

    start, final = timeline[0], timeline[-1]
    active_weather = sorted({
        weather_id
        for step in timeline
        for weather_id, state in step["weather"].items()
        if state["active"]
    })
    metrics = {
        "target_damage": start["target"]["hp"] - final["target"]["hp"],
        "hero_hp_loss": start["hero"]["hp"] - final["hero"]["hp"],
        "hero_final_hp": final["hero"]["hp"],
        "hero_final_shield": final["hero"]["shield"],
        "hero_mana_delta": final["hero"]["mana"] - start["hero"]["mana"],
        "target_mana_delta": final["target"]["mana"] - start["target"]["mana"],
        "final_sim_time": final["sim_time"],
        "final_ecology": final["ecology"]["current"],
        "final_biomass": final["fields"]["biomass"]["value"],
        "final_temperature": final["fields"]["temperature"]["value"],
        "final_wetness": final["fields"]["wetness"]["value"],
        "final_electric_field": final["fields"]["electric_field"]["value"],
        "final_smoke": final["fields"]["smoke"]["value"],
        "active_weather_seen": active_weather,
        "rejected_action_count": sum(row["rejected"] is not None for row in rounds),
        "manual_hook_dispatch_count": sum(len(row["manual_hook_dispatches"]) for row in rounds),
    }
    return {
        "arm_id": arm_id,
        "equipped_skill_ids": arm["equip"],
        "loadout_traces": [result.trace.to_dict() for result in built.loadout_results],
        "timeline": timeline,
        "rounds": rounds,
        "metrics": metrics,
    }


def _request(
    built: Any,
    spec: dict[str, Any],
    variant: dict[str, Any],
    arm_id: str,
    round_index: int,
    action_id: str,
) -> ActionRequest:
    definition = built.content.action_registry.actions[action_id]
    target = "synergy_target" if "target_actor" in definition.capability.selectors else "synergy_hero"
    return ActionRequest(
        f"{spec['build_id']}:{variant['variant_id']}:{arm_id}:hero:{round_index}",
        "synergy_hero",
        action_id,
        target,
    )


def _combat_round(
    built: Any,
    spec: dict[str, Any],
    variant: dict[str, Any],
    arm_id: str,
    round_index: int,
    hero_request: ActionRequest,
) -> Any:
    enemy_action = spec["enemy_action"]
    enemy_target = "synergy_hero" if enemy_action == "basic_attack" else "synergy_target"
    return run_combat_round(
        built.session,
        built.content.action_registry,
        round_index=round_index,
        actor_order=("synergy_hero", "synergy_target"),
        requests={
            "synergy_hero": hero_request,
            "synergy_target": ActionRequest(
                f"{spec['build_id']}:{variant['variant_id']}:{arm_id}:target:{round_index}",
                "synergy_target",
                enemy_action,
                enemy_target,
            ),
        },
    )


def _outcome(outcome: Any) -> dict[str, Any]:
    return {
        "actor_id": outcome.request.actor_id,
        "action_id": outcome.definition.id,
        "cost": {"duration": outcome.cost.duration, "mana": outcome.cost.mana},
        "effect_outcomes": [dict(row) for row in outcome.effect_outcomes],
        "changed": outcome.event_result.changed,
        "trace": outcome.event_result.trace.to_dict(),
    }


def _weather_changed_events(trace: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row["event"]
        for row in trace["events"]
        if row["event"]["type"] == "pmw.v04.weather.changed"
    ]


def run_build(spec: dict[str, Any], *, write: bool = True) -> dict[str, Any]:
    variants = spec.get("variants")
    if variants is None:
        variants = [{
            "variant_id": "primary",
            "environment": spec["environment"],
            "field_overrides": spec.get("field_overrides", {}),
            "initial": spec["initial"],
        }]
    results = {}
    for variant in variants:
        arms = {arm_id: run_arm(spec, variant, arm_id) for arm_id in spec["arms"]}
        times = {row["metrics"]["final_sim_time"] for row in arms.values()}
        if times != {float(spec["rounds"])}:
            raise AssertionError(f"unmatched horizons for {spec['build_id']}: {times}")
        results[variant["variant_id"]] = {"variant": variant, "arms": arms}
    result = {
        "protocol": "pmw-build-synergy-v0.1",
        "build_id": spec["build_id"],
        "name_zh": spec["name_zh"],
        "spec": spec,
        "variants": results,
    }
    if write:
        path = ROOT / "evidence" / f"{spec['build_id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return result


def run_all(*, write: bool = True) -> list[dict[str, Any]]:
    return [run_build(spec, write=write) for spec in load_specs()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-id")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    specs = load_specs()
    if args.build_id:
        specs = [spec for spec in specs if spec["build_id"] == args.build_id]
        if not specs:
            raise SystemExit(f"unknown build: {args.build_id}")
    results = [run_build(spec, write=not args.no_write) for spec in specs]
    summary = {
        result["build_id"]: {
            variant_id: {
                arm_id: row["metrics"]
                for arm_id, row in variant["arms"].items()
            }
            for variant_id, variant in result["variants"].items()
        }
        for result in results
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
