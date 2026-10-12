"""Execute SkillLab cases against real PMW Gameplay sessions."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ACTOR_COMPONENT,
    ActionRequest,
    resolve_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.dynamics import DYNAMICS_COMPONENT
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ecology import ECOLOGY_COMPONENT
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.hooks import HookLineage, execute_hook
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.harvest import (
    HarvestRequest,
    MATERIAL_INVENTORY_COMPONENT,
    resolve_harvest,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import run_phase_event
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.shields import SHIELD_COMPONENT
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.status import STATUS_COMPONENT
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    spend_world_time,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.weather import WEATHER_COMPONENT

from .shared import build_case_session


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EVIDENCE = ROOT / "evidence"


def load_cases() -> list[dict[str, Any]]:
    cases = [json.loads(path.read_text()) for path in sorted(SKILLS.glob("*.json"))]
    ids = [case["case_id"] for case in cases]
    skill_ids = [case["blueprint"]["id"] for case in cases]
    if len(ids) != len(set(ids)) or len(skill_ids) != len(set(skill_ids)):
        raise ValueError("case and skill IDs must be unique")
    return cases


def run_case(case: dict[str, Any], *, write_evidence: bool = True) -> dict[str, Any]:
    _validate_pilot_case(case)
    baseline = build_case_session(case)
    treatment = build_case_session(case)
    baseline_events: list[dict[str, Any]] = []
    treatment_events: list[dict[str, Any]] = []
    _run_prelude(case, baseline, baseline_events)
    _run_prelude(case, treatment, treatment_events)
    initial_baseline = observe(baseline.session)
    initial_treatment = observe(treatment.session)
    if initial_baseline != initial_treatment:
        raise AssertionError("baseline and treatment do not share an initial observation")

    if treatment.skill.kind == "skill_blueprint":
        action = resolve_action(
            treatment.session, treatment.content.action_registry,
            ActionRequest(f"cast_{case['case_id']}", "pilot_hero", treatment.skill.id,
                          case["scenario"].get("target_actor_id", "pilot_target")),
        )
        treatment_events.append(_event_result("skill_action", action.event_result))
    else:
        _run_passive_trigger(case, baseline, baseline_events, fire_hook=False)
        _run_passive_trigger(case, treatment, treatment_events, fire_hook=True)

    baseline_timeline = [initial_baseline, observe(baseline.session)]
    treatment_timeline = [initial_treatment, observe(treatment.session)]
    phase = case["scenario"].get("phase")
    phase_steps = case["scenario"].get("phase_steps", 0)
    for index in range(phase_steps):
        left = run_phase_event(baseline.session, phase, actor_id="pilot_hero" if phase == "owner_turn" else None)
        right = run_phase_event(treatment.session, phase, actor_id="pilot_hero" if phase == "owner_turn" else None)
        baseline_events.append(_event_result(f"{phase}_{index + 1}", left))
        treatment_events.append(_event_result(f"{phase}_{index + 1}", right))
        baseline_timeline.append(observe(baseline.session))
        treatment_timeline.append(observe(treatment.session))
    horizon = case["scenario"].get("horizon_ticks", 3)
    baseline_time = spend_world_time(baseline.session, horizon, reason="exploration")
    treatment_time = spend_world_time(treatment.session, horizon, reason="exploration")
    baseline_events.append(_event_result("time_spend", baseline_time.event_result))
    treatment_events.append(_event_result("time_spend", treatment_time.event_result))
    for index, (left, right) in enumerate(zip(baseline_time.ticks, treatment_time.ticks, strict=True), 1):
        baseline_events.append(_event_result(f"world_tick_{index}", left.event_result))
        treatment_events.append(_event_result(f"world_tick_{index}", right.event_result))
        baseline_timeline.append(observe(left.snapshot))
        treatment_timeline.append(observe(right.snapshot))

    changed_steps = [index for index, pair in enumerate(zip(baseline_timeline, treatment_timeline, strict=True))
                     if pair[0] != pair[1]]
    if not changed_steps:
        raise AssertionError("treatment produced no observable difference from baseline")
    counterexample = _run_counterexample(case)
    result = {
        "protocol": "pmw-creative-skilllab-pilot-v1",
        "case_id": case["case_id"], "skill_id": treatment.skill.id,
        "skill_hash": treatment.skill.canonical_hash,
        "material_id": treatment.material.id,
        "legality": {"material": "pass", "blueprint": "pass", "compile": "pass",
                     "registry": "pass", "loadout": "pass"},
        "baseline": {"timeline": baseline_timeline, "events": baseline_events},
        "treatment": {"timeline": treatment_timeline, "events": treatment_events},
        "changed_steps": changed_steps,
        "counterexample": counterexample,
        "claims": case["claims"],
        "result": "validated",
    }
    if write_evidence:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        path = EVIDENCE / f"{case['case_id']}.json"
        path.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        )
    return result


def run_all(*, write_evidence: bool = True) -> list[dict[str, Any]]:
    return [run_case(case, write_evidence=write_evidence) for case in load_cases()]


def observe(subject: Any) -> dict[str, Any]:
    state = subject.state if hasattr(subject, "state") else subject
    hero = state.entities["pilot_hero"]
    target = state.entities["pilot_target"]
    area = state.entities["pilot_area"]
    clock = state.entities["pmw:v04:clock"]
    return {
        "sim_time": state.sim_time,
        "hero": _actor_observation(hero),
        "target": _actor_observation(target),
        "fields": {field_id: {
            "value": row["value"],
            "effective_target": row["diagnostics"]["effective_target"],
            "effective_rate": row["diagnostics"]["effective_rate"],
        } for field_id, row in sorted(area.components[DYNAMICS_COMPONENT]["fields"].items())},
        "weather": deepcopy(area.components[WEATHER_COMPONENT]["states"]),
        "ecology": {
            "current": area.components[ECOLOGY_COMPONENT]["current"],
            "counters": deepcopy(area.components[ECOLOGY_COMPONENT]["counters"]),
        },
        "time_budget": deepcopy(clock.components[TIME_BUDGET_COMPONENT]),
        "inventory": deepcopy(hero.components[MATERIAL_INVENTORY_COMPONENT]["quantities"]),
        "scheduled_events": len(state.scheduled_events),
    }


def _actor_observation(entity: Any) -> dict[str, Any]:
    actor = entity.components[ACTOR_COMPONENT]
    statuses = entity.components[STATUS_COMPONENT]["slots"]
    shields = entity.components[SHIELD_COMPONENT]["slots"]
    return {
        "hp": actor["hp"], "mana": actor["mana"], "shield": actor["shield"],
        "traits": list(actor["traits"]),
        "statuses": [deepcopy(row) for _, row in sorted(statuses.items()) if row["active"]],
        "shield_layers": [deepcopy(row) for _, row in sorted(shields.items()) if row["active"]],
    }


def _run_passive_trigger(case: dict[str, Any], built: Any,
                         events: list[dict[str, Any]], *, fire_hook: bool) -> None:
    trigger = built.skill.trigger
    if trigger in {"attack_applied", "damage_resolved", "action_started"}:
        incoming = case["scenario"].get("trigger_direction") == "incoming"
        request = ActionRequest(
            f"trigger_{case['case_id']}",
            "pilot_target" if incoming else "pilot_hero", "basic_attack",
            "pilot_hero" if incoming else "pilot_target",
        )
    elif trigger == "status_changed":
        request = ActionRequest(f"trigger_{case['case_id']}", "pilot_hero", "basic_guard", "pilot_hero")
    elif trigger == "weather_changed":
        time_result = spend_world_time(built.session, 1, reason="exploration")
        events.append(_event_result("weather_trigger_time", time_result.event_result))
        events.append(_event_result("weather_trigger_tick", time_result.ticks[0].event_result))
    elif trigger == "resource_harvested":
        harvest = built.content.harvest_by_area["pilot_area"][0]
        outcome = resolve_harvest(
            built.session, built.content.action_registry, harvest,
            HarvestRequest(f"trigger_{case['case_id']}", "pilot_hero", harvest.id),
        )
        events.append(_event_result("harvest_trigger", outcome.event_result))
    else:
        request = ActionRequest(f"trigger_{case['case_id']}", "pilot_hero", "basic_wait", "pilot_hero")
    if trigger not in {"weather_changed", "resource_harvested"}:
        trigger_outcome = resolve_action(built.session, built.content.action_registry, request)
        events.append(_event_result("trigger_action", trigger_outcome.event_result))
    if not fire_hook:
        return
    hook = next(item for item in built.content.action_registry.hooks.values()
                if item.action_id == built.skill.id)
    outcome, _ = execute_hook(
        built.session, built.content.action_registry, hook,
        HookLineage(f"root_{case['case_id']}", None, 0, built.skill.max_firings_per_root),
        actor_id="pilot_hero", target_actor_id=case["scenario"].get("target_actor_id", "pilot_target"),
        trigger=trigger,
    )
    if outcome is None:
        raise AssertionError("passive hook condition did not activate in its success case")
    events.append(_event_result("passive_hook", outcome.event_result))


def _run_prelude(case: dict[str, Any], built: Any, events: list[dict[str, Any]]) -> None:
    for index, row in enumerate(case["scenario"].get("prelude_actions", ())):
        outcome = resolve_action(
            built.session, built.content.action_registry,
            ActionRequest(f"setup_{case['case_id']}_{index}", row["actor_id"], row["action_id"],
                          row.get("target_actor_id")),
        )
        events.append(_event_result(f"prelude_{index + 1}", outcome.event_result))


def _run_counterexample(case: dict[str, Any]) -> dict[str, Any]:
    built = build_case_session(case, equip=False)
    before = built.session.state.to_dict()
    rejected = False
    message = ""
    try:
        if built.skill.kind == "skill_blueprint":
            resolve_action(
                built.session, built.content.action_registry,
                ActionRequest(f"denied_{case['case_id']}", "pilot_hero", built.skill.id,
                              case["scenario"].get("target_actor_id", "pilot_target")),
            )
        else:
            hook = next(item for item in built.content.action_registry.hooks.values()
                        if item.action_id == built.skill.id)
            execute_hook(
                built.session, built.content.action_registry, hook,
                HookLineage(f"denied_{case['case_id']}", None, 0, 1),
                actor_id="pilot_hero", target_actor_id="pilot_target", trigger="weather_changed"
                if hook.trigger != "weather_changed" else "damage_resolved",
            )
    except GameplayContractError as exc:
        rejected, message = True, str(exc)
    if not rejected or built.session.state.to_dict() != before:
        raise AssertionError("counterexample did not reject atomically")
    return {"kind": "unequipped_or_wrong_trigger", "rejected": True,
            "state_unchanged": True, "message": message}


def _event_result(label: str, result: Any) -> dict[str, Any]:
    return {
        "label": label, "changed": result.changed,
        "triggered_law_ids": list(result.triggered_law_ids),
        "processed_event_ids": list(result.processed_event_ids),
        "scheduled_event_ids": list(result.scheduled_event_ids),
        "trace": result.trace.to_dict() if result.trace is not None else None,
    }


def _validate_pilot_case(case: dict[str, Any]) -> None:
    required = {"case_id", "name_zh", "creator", "category", "intent_zh", "tags",
                "material", "statuses", "blueprint", "scenario", "claims", "limitations_zh"}
    if set(case) != required:
        raise ValueError(f"pilot case fields differ: {case.get('case_id')}")
    if not 1 <= case["scenario"].get("horizon_ticks", 3) <= 8:
        raise ValueError("pilot horizon must stay in [1, 8]")
    if case["scenario"].get("phase_steps", 0) not in range(0, 9):
        raise ValueError("pilot phase steps must stay in [0, 8]")
    if case["scenario"].get("phase") not in {None, "owner_turn", "combat_round"}:
        raise ValueError("pilot phase is invalid")
    blueprint = case["blueprint"]
    for effect in blueprint["effects"]:
        amount = effect.get("amount")
        if amount is not None and abs(float(amount)) > 100.0:
            raise ValueError("pilot effect amount exceeds published numeric guardrail")
        if effect.get("duration", 1) > 8:
            raise ValueError("pilot effect duration exceeds published numeric guardrail")
    if blueprint["cost"]["mana"] > 15:
        raise ValueError("pilot mana cost exceeds published numeric guardrail")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    cases = load_cases()
    if args.case_id:
        cases = [case for case in cases if case["case_id"] == args.case_id]
        if not cases:
            raise SystemExit(f"unknown case: {args.case_id}")
    results = [run_case(case, write_evidence=not args.no_write) for case in cases]
    print(json.dumps({"validated": len(results), "case_ids": [row["case_id"] for row in results]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
