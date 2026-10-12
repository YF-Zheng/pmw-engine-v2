"""Build A first: prove same-session Status-to-Condition composition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRequest
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import run_combat_round
from .shared import build_multi_skill_session, observe_session


ROOT = Path(__file__).resolve().parents[1]


def run_arm(spec: dict[str, Any], arm_id: str) -> dict[str, Any]:
    initial = spec["initial"]
    built = build_multi_skill_session(
        tuple(spec["skill_case_ids"]),
        environment=spec["environment"],
        hero_hp=initial["hero_hp"],
        hero_mana=initial["hero_mana"],
        target_hp=initial["target_hp"],
        target_mana=initial["target_mana"],
        target_traits=tuple(initial["target_traits"]),
        equip_skill_ids=tuple(spec["arms"][arm_id]["equip"]),
    )
    timeline = [observe_session(built.session)]
    rounds = []
    for round_index, action_id in enumerate(spec["arms"][arm_id]["actions"], 1):
        result = run_combat_round(
            built.session,
            built.content.action_registry,
            round_index=round_index,
            actor_order=("synergy_hero", "synergy_target"),
            requests={
                "synergy_hero": ActionRequest(
                    f"{spec['build_id']}:{arm_id}:hero:{round_index}",
                    "synergy_hero",
                    action_id,
                    "synergy_target" if action_id in {"false_mercy", "doctrinal_exception", "basic_attack"} else "synergy_hero",
                ),
                "synergy_target": ActionRequest(
                    f"{spec['build_id']}:{arm_id}:target:{round_index}",
                    "synergy_target",
                    spec["enemy_action"],
                    "synergy_hero",
                ),
            },
        )
        rounds.append({
            "round": round_index,
            "player_action": action_id,
            "actor_order": list(result.actor_order),
            "outcomes": [
                {
                    "actor_id": outcome.request.actor_id,
                    "action_id": outcome.definition.id,
                    "changed": outcome.event_result.changed,
                    "trace": outcome.event_result.trace.to_dict(),
                }
                for outcome in result.outcomes
            ],
            "world_tick_trace": result.world_tick_result.event_result.trace.to_dict(),
            "time_spend_trace": result.time_spend_result.event_result.trace.to_dict(),
        })
        timeline.append(observe_session(built.session))
    start, final = timeline[0], timeline[-1]
    return {
        "arm_id": arm_id,
        "timeline": timeline,
        "rounds": rounds,
        "metrics": {
            "target_damage": start["target"]["hp"] - final["target"]["hp"],
            "hero_hp_loss": start["hero"]["hp"] - final["hero"]["hp"],
            "hero_mana_delta": final["hero"]["mana"] - start["hero"]["mana"],
            "target_mana_delta": final["target"]["mana"] - start["target"]["mana"],
            "final_sim_time": final["sim_time"],
        },
    }


def run_build_a(*, write: bool = True) -> dict[str, Any]:
    spec = json.loads((ROOT / "build_specs" / "build_a.json").read_text())
    arms = {arm_id: run_arm(spec, arm_id) for arm_id in spec["arms"]}
    times = {row["metrics"]["final_sim_time"] for row in arms.values()}
    if times != {float(spec["rounds"])}:
        raise AssertionError(f"unmatched time horizons: {times}")
    target_after_a = arms["a_then_b"]["timeline"][1]["target"]
    marked = sorted({
        trait
        for status in target_after_a["statuses"]
        for trait in status["granted_traits"]
    })
    if "recently_spared" not in marked:
        raise AssertionError("false_mercy did not create the real combo Trait")
    result = {
        "protocol": "pmw-build-synergy-v0.1",
        "build_id": spec["build_id"],
        "spec": spec,
        "arms": arms,
        "interaction": {
            "same_session": True,
            "preset_target_trait": False,
            "trait_after_a": marked,
            "target_damage": {key: row["metrics"]["target_damage"] for key, row in arms.items()},
        },
    }
    if write:
        path = ROOT / "evidence" / "build_a.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return result


if __name__ == "__main__":
    outcome = run_build_a()
    print(json.dumps(outcome["interaction"], ensure_ascii=False, sort_keys=True))
