from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from experiments.generative_mechanics.next_tracks_v06.validator import load_catalog


ROOT = Path(__file__).resolve().parents[1]


def catalog(name: str = "thermal_fluid"):
    return load_catalog(ROOT / "substrate" / f"{name}.json")


def raw_catalog(name: str = "thermal_fluid"):
    return json.loads((ROOT / "substrate" / f"{name}.json").read_text(encoding="utf-8"))


def operator(
    kind: str = "impulse",
    capability: str = "temperature_impulse",
    target: str = "reactor_temperature",
    parameters: dict | None = None,
    lifecycle: dict | None = None,
    operator_id: str = "operator_01",
):
    return {
        "id": operator_id,
        "kind": kind,
        "capability_id": capability,
        "scope": "local",
        "target": {"object": target},
        "parameters": {"delta": -0.2} if parameters is None else parameters,
        "lifecycle": {"mode": "instant"} if lifecycle is None else lifecycle,
    }


def mechanism(operators: list[dict] | None = None, *, artifact_id: str = "test_mechanism", anchor: str = "reactor_temperature", capabilities: list[str] | None = None, max_instances: int = 1):
    operators = deepcopy(operators or [operator()])
    capabilities = capabilities or sorted({item["capability_id"] for item in operators})
    return {
        "protocol": "gm-mechanism-v0.6",
        "id": artifact_id,
        "name": "Test mechanism",
        "scope": {"kind": "local", "anchor": anchor},
        "artifact_policy": {"owner": "activation_source", "event_namespace": "derived", "temporal_handles": "per_instance"},
        "capability_ids": capabilities,
        "max_instances": max_instances,
        "operators": operators,
    }


VALID_OPERATORS = {
    "impulse": operator(operator_id="impulse_op"),
    "drive": operator("drive", "temperature_drive", parameters={"mode": "field", "rate": 0.05}, lifecycle={"mode": "timed", "steps": 3}, operator_id="drive_op"),
    "attractor_modifier": operator("attractor_modifier", "temperature_attractor", parameters={"attractor": 0.2, "weight": 1.0}, lifecycle={"mode": "timed", "steps": 3}, operator_id="attractor_op"),
    "dynamics_modifier": operator("dynamics_modifier", "thermal_dynamics", parameters={"parameter": "alpha", "delta": 0.1}, lifecycle={"mode": "timed", "steps": 3}, operator_id="dynamics_op"),
    "process_start": operator("process_start", "pump_start", "coolant_pump", {}, {"mode": "timed", "steps": 3}, operator_id="process_start_op"),
    "process_modify": operator("process_modify", "pump_modify", "coolant_pump", {"parameter": "flow_rate", "delta": 0.1}, {"mode": "timed", "steps": 3}, operator_id="process_modify_op"),
    "relation_modifier": operator("relation_modifier", "link_modify", "thermal_link", {"action": "modify", "parameter": "conductivity", "delta": 0.1}, {"mode": "timed", "steps": 3}, operator_id="relation_modify_op"),
}
