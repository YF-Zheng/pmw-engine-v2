"""Generate reproducible Engine and belief evidence for the F2 pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRequest, resolve_action
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import spend_world_time

from .actions import execute_preparation, execute_repair
from .belief_solver import solve_equivalent, solve_native
from .engine_scenario import AREA_ID, F2_COMPONENT, ROOTS, build_f2_runtime
from .observation import observation_digest, public_observation
from .reference_model import reference_initial_q, reference_optimum


ROOT = Path(__file__).resolve().parent
COSTS = ((.10, .03), (.10, .23), (.40, .03))


def run(*, write: bool = True) -> dict[str, Any]:
    physics = _physics_evidence()
    observations = _observation_evidence()
    shortcuts = _shortcut_evidence()
    equivalent = {}
    for cf, ci in COSTS:
        solution = solve_equivalent(cf, ci)
        reference_actions, reference_value = reference_optimum(cf, ci)
        equivalent[f"cf={cf:.2f},ci={ci:.2f}"] = {
            "costs": {"cf": cf, "ci": ci},
            "reference_q": reference_initial_q(cf, ci),
            "reference_optimum": {"actions": list(reference_actions), "value": reference_value},
            "engine_solver": solution.to_dict(),
            "optimum_matches": (
                solution.optimal_actions == reference_actions
                and abs(solution.value - reference_value) < 1e-12
            ),
        }
    result = {
        "protocol": "gccp-f2-engine-pilot-v0.1",
        "reference_source": "independently reconstructed from task mathematics; original files unavailable",
        "physics": physics,
        "observation_boundary": observations,
        "shortcut_audit": shortcuts,
        "equivalent_mode": equivalent,
        "native_resource_mode": solve_native().to_dict(),
        "information_ablation": solve_equivalent(.10, .03, information_ablation=True).to_dict(),
        "adapter_boundaries": [
            "calibrate/forge orchestration across formal Event, Registry, Loadout, and time APIs",
            "allowlisted public observation and exact belief enumeration",
            "binary terminal success predicate final_stability >= pre_repair_stability",
        ],
    }
    if write:
        evidence = ROOT / "evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        _write(evidence / "engine_physics.json", physics)
        _write(evidence / "observation_boundary.json", observations)
        _write(evidence / "shortcut_audit.json", shortcuts)
        _write(evidence / "solver_results.json", {
            "equivalent_mode": equivalent,
            "native_resource_mode": result["native_resource_mode"],
            "information_ablation": result["information_ablation"],
        })
        _write(evidence / "pilot_result.json", result)
    return result


def _physics_evidence() -> dict[str, Any]:
    no_intervention = {}
    for root in ROOTS:
        runtime = build_f2_runtime(root, "water")
        before = runtime.session.state.to_dict()
        time_result = spend_world_time(runtime.session, 1, reason="exploration")
        after = runtime.session.state.to_dict()
        private = runtime.session.state.entities[AREA_ID].components[F2_COMPONENT]
        no_intervention[root] = {
            "before_world": before,
            "after_world": after,
            "damage": private["damage"],
            "stability": private["stability"],
            "time_event": _event_result(time_result.event_result),
            "world_tick": _tick(time_result.ticks[0]),
        }
    probes = {}
    repairs = {}
    for root in ROOTS:
        for interface in ROOTS:
            key = f"H={root},X={interface}"
            runtime = build_f2_runtime(root, interface)
            forge = execute_preparation(runtime, "forge_water")
            probe = execute_preparation(runtime, "probe")
            probes[key] = {"forge": forge.to_dict(), "probe": probe.to_dict()}
        for repair in ROOTS:
            runtime = build_f2_runtime(root, "water")
            transition, success = execute_repair(runtime, f"repair_{repair}")
            repairs[f"H={root},repair={repair}"] = {
                "success": success,
                "transition": transition.to_dict(),
            }
    return {"no_intervention": no_intervention, "water_probe": probes, "repairs": repairs}


def _observation_evidence() -> dict[str, Any]:
    initial = {}
    calibration = {}
    for root in ROOTS:
        for interface in ROOTS:
            key = f"H={root},X={interface}"
            runtime = build_f2_runtime(root, interface)
            document = public_observation(runtime)
            initial[key] = {"digest": observation_digest(document), "document": document}
            calibrated = execute_preparation(runtime, "calibrate")
            calibration[key] = calibrated.to_dict()
    return {
        "initial": initial,
        "initial_digest_count": len({row["digest"] for row in initial.values()}),
        "calibration": calibration,
        "forbidden_agent_surfaces": [
            "WorldState", "EventResult", "CausalTrace", "checkpoint digest",
            "registry internals", "hidden_root", "hidden_interface", "damage",
        ],
    }


def _shortcut_evidence() -> dict[str, Any]:
    rows = {}
    runtime = build_f2_runtime("water", "water")
    before = runtime.session.state.to_dict()
    try:
        resolve_action(
            runtime.session,
            runtime.runtime.action_registry,
            ActionRequest("f2_unforged_probe", "f2_researcher", "f2_probe_water", "f2_researcher"),
        )
    except Exception as exc:
        rows["unregistered_probe"] = {
            "rejected": True,
            "public_error": "action_rejected",
            "trusted_exception_type": type(exc).__name__,
            "state_unchanged": runtime.session.state.to_dict() == before,
        }
    execute_preparation(runtime, "forge_water")
    before = runtime.session.state.to_dict()
    manifest = runtime.runtime.manifest
    try:
        execute_preparation(runtime, "forge_resonance")
    except Exception as exc:
        rows["second_forge"] = {
            "rejected": True,
            "public_error": "action_rejected",
            "trusted_exception_type": type(exc).__name__,
            "state_unchanged": runtime.session.state.to_dict() == before,
            "registry_unchanged": runtime.runtime.manifest == manifest,
        }
    execute_preparation(runtime, "probe")
    before = runtime.session.state.to_dict()
    try:
        execute_preparation(runtime, "probe")
    except Exception as exc:
        rows["second_probe"] = {
            "rejected": True,
            "public_error": "action_rejected",
            "trusted_exception_type": type(exc).__name__,
            "state_unchanged": runtime.session.state.to_dict() == before,
        }
    rows["agent_action_surface"] = {
        "actions": public_observation(build_f2_runtime("water", "water"))["known_actions"],
        "forbidden_absent": ["basic_attack", "basic_guard", "basic_wait", "loadout", "registry", "checkpoint"],
    }
    return rows


def _event_result(result: Any) -> dict[str, Any]:
    return {"changed": result.changed, "trace": result.trace.to_dict()}


def _tick(result: Any) -> dict[str, Any]:
    return {"step": result.step, "time": result.time, "event_result": _event_result(result.event_result)}


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    result = run(write=not args.no_write)
    summary = {
        "equivalent": {
            key: {
                "optimal_actions": row["engine_solver"]["optimal_actions"],
                "value": row["engine_solver"]["value"],
                "matches": row["optimum_matches"],
            }
            for key, row in result["equivalent_mode"].items()
        },
        "native": {
            "optimal_actions": result["native_resource_mode"]["optimal_actions"],
            "value": result["native_resource_mode"]["value"],
        },
        "ablation": {
            "optimal_actions": result["information_ablation"]["optimal_actions"],
            "value": result["information_ablation"]["value"],
        },
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
