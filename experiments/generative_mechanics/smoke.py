"""Small deterministic cross-environment execution smoke test."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from pmw import Engine, Event, load_laws, load_world, parse_law

from .compiler import compile_skill
from .execution import activation_event
from .spec import SkillSpec, load_skill
from .substrate import public_fields_are_bounded, system_laws

ROOT = Path(__file__).resolve().parent


def run_cross_environment(spec: SkillSpec) -> dict[str, Any]:
    compiled = compile_skill(spec)
    laws = [parse_law(raw) for raw in compiled["laws"]] + load_laws(ROOT / "substrate" / "world_laws.json") + system_laws()
    result: dict[str, Any] = {}
    for path in sorted((ROOT / "environments").glob("*.json")):
        world = load_world(path)
        zone = next(item for item in world.entities.values() if "zone" in item.components)
        skill = world.entities["skill:equipped"]
        skill.components["skill"].update({"spec_id": spec.id, "charges": spec.charges})
        runtime = Engine(laws).attach(world)
        activation = runtime.run_event(activation_event(
            spec, activation_id=f"activate:{path.stem}:{spec.id}", skill_instance_id="skill:equipped",
            actor_id="actor:researcher", zone_id=zone.id, time=0.0,
        ))
        step = runtime.run_event(Event(id=f"step:{path.stem}", type="lab.step", time=0.0, source=None, target=zone.id))
        runtime.run_event(Event(id=f"dissipate:{path.stem}", type="lab.dissipate", time=0.0, source=None, target=zone.id))
        if runtime.state.scheduled_events:
            runtime.advance_to(max(item.time for item in runtime.state.scheduled_events))
        final_zone = runtime.state.entities[zone.id]
        if not public_fields_are_bounded(runtime.state.to_dict()):
            raise RuntimeError("normalized public field invariant failed")
        result[path.stem] = {
            "activation_laws": sorted(activation.triggered_law_ids),
            "step_laws": sorted(step.triggered_law_ids),
            "fields": deepcopy(final_zone.components["fields"]),
            "process": deepcopy(final_zone.components["process"]),
            "outcome": deepcopy(final_zone.components["outcome"]),
            "energy": runtime.state.entities["actor:researcher"].components["resource"]["energy"],
            "charges": runtime.state.entities["skill:equipped"].components["skill"]["charges"],
        }
    return {"skill": spec.id, "environments": result}


def default_smoke() -> dict[str, Any]:
    return run_cross_environment(load_skill(ROOT / "skills" / "static_grave.json"))
