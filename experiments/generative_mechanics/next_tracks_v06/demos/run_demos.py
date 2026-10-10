"""Run all five TODO1 demonstrations and emit canonical audit JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..canonical import canonical_json
from ..compiler import compile_mechanisms
from ..execution import activation_event, activate, build_runtime, run_step
from ..worlds import build_electric_world, build_structural_world, build_thermal_world


ROOT = Path(__file__).resolve().parent
BUILDERS = {
    "thermal": build_thermal_world,
    "electric": build_electric_world,
    "structural": build_structural_world,
}


def _trajectory(world: str, runtime) -> dict[str, Any]:
    if world == "thermal":
        return {
            "temperature": runtime.state.entities["reactor"].components["gm_v06_dynamics"]["value"],
            "ambient": runtime.state.entities["ambient"].components["gm_v06_dynamics"]["value"],
            "coolant": runtime.state.entities["coolant_tank"].components["stock"]["amount"],
            "pump": runtime.state.entities["pump_01"].components["process"]["state"],
            "operational": runtime.state.entities["reactor"].components["derived"]["operational"],
        }
    if world == "electric":
        return {
            "voltage": runtime.state.entities["power_bus"].components["gm_v06_dynamics"]["value"],
            "battery": runtime.state.entities["battery"].components["stock"]["amount"],
            "charger": runtime.state.entities["charger"].components["process"]["state"],
            "switch": runtime.state.entities["switch"].components["control"]["mode"],
            "connected": any(item.type == "supplies_power" for item in runtime.state.relations.values()),
        }
    return {
        "stability": runtime.state.entities["frame"].components["gm_v06_dynamics"]["value"],
        "support": runtime.state.entities["support"].components["gm_v06_dynamics"]["value"],
        "operational": runtime.state.entities["frame"].components["derived"]["operational"],
    }


def _event_result(result) -> dict[str, Any]:
    return {
        "changed": result.changed,
        "triggered_law_ids": result.triggered_law_ids,
        "state_delta": [item.to_dict() for item in result.state_delta],
        "scheduled_event_ids": result.scheduled_event_ids,
        "cancelled_event_ids": result.cancelled_event_ids,
        "trace": result.trace.to_dict(),
    }


def _run_branch(world_name: str, specs: list[dict], horizon: int) -> dict[str, Any]:
    world, world_laws, catalog = BUILDERS[world_name]()
    initial = world.to_dict()
    compiled = list(compile_mechanisms(specs, catalog))
    runtime = build_runtime(world, world_laws, compiled)
    activations = []
    for index, mechanism in enumerate(compiled):
        event = activation_event(mechanism, activation_id=f"activation_{index:02d}", instance_index=0, time=0)
        activations.append({"event": event.to_dict(), "result": _event_result(activate(runtime, mechanism, event))})
    trajectory = [{"step": 0, **_trajectory(world_name, runtime)}]
    steps = []
    for _ in range(horizon):
        result = run_step(runtime)
        trajectory.append({"step": result.step, **_trajectory(world_name, runtime)})
        steps.append({
            "step": result.step,
            "scheduled_dispatches": [item.event_id for item in result.advance_result.dispatches],
            "dynamics": _event_result(result.dynamics_result),
            "world_step": _event_result(result.world_step_result),
        })
    return {
        "mechanism_specs": specs,
        "compiled_law_ids": [[law["id"] for law in item.law_bundle] for item in compiled],
        "source_maps": [dict(item.source_map) for item in compiled],
        "initial_world": initial,
        "activations": activations,
        "steps": steps,
        "trajectory": trajectory,
        "final_world": runtime.state.to_dict(),
    }


def run_demo(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if "branches" in document:
        branches = {
            spec["id"]: _run_branch(document["world"], [spec], document["horizon"])
            for spec in document["branches"]
        }
        return {"demo_id": document["demo_id"], "world": document["world"], "branches": branches}
    return {
        "demo_id": document["demo_id"],
        "world": document["world"],
        **_run_branch(document["world"], document["mechanisms"], document["horizon"]),
    }


def run_all(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for path in sorted(ROOT.glob("*.json")):
        result = run_demo(path)
        results[result["demo_id"]] = result
        (output_dir / path.name).write_text(canonical_json(result) + "\n", encoding="utf-8")
    summary = {key: _summary(value) for key, value in sorted(results.items())}
    (output_dir / "summary.json").write_text(canonical_json(summary) + "\n", encoding="utf-8")
    return summary


def _summary(result: dict[str, Any]) -> Any:
    if "branches" in result:
        return {key: value["trajectory"] for key, value in sorted(result["branches"].items())}
    return result["trajectory"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    print(canonical_json(run_all(args.output)))
