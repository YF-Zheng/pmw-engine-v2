"""Deterministic clean-world scenario runner."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from pmw import Engine, Entity, Event, load_laws, load_world, parse_law

from .compiler import compile_skill
from .execution import activation_event
from .spec import SkillSpec, load_skill
from .substrate import apply_public_initialization, public_fields_are_bounded, system_laws

ROOT = Path(__file__).resolve().parent
ACTOR_ID = "actor:researcher"


class ScenarioExecutionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RootExecution:
    command_id: str
    event_id: str
    event_type: str
    triggered_law_ids: tuple[str, ...]
    trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"command_id": self.command_id, "event_id": self.event_id, "event_type": self.event_type, "triggered_law_ids": list(self.triggered_law_ids), "trace": self.trace}


@dataclass(frozen=True, slots=True)
class ScenarioRun:
    scenario_id: str
    split: str
    environment: str
    active_skills: tuple[str, ...]
    initial_state: dict[str, Any]
    roots: tuple[RootExecution, ...]
    horizons: dict[str, dict[str, Any]]
    final_state: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id, "split": self.split, "environment": self.environment,
            "active_skills": list(self.active_skills), "initial_state": self.initial_state,
            "roots": [item.to_dict() for item in self.roots], "horizons": self.horizons,
            "final_state": self.final_state,
        }


def load_skill_catalog() -> dict[str, SkillSpec]:
    return {
        spec.id: spec
        for path in sorted((ROOT / "skills").glob("*.json")) if path.name != "manifest.json"
        for spec in (load_skill(path),)
    }


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _default_active(scenario: Any) -> tuple[str, ...]:
    build = _field(scenario, "build", {})
    return tuple(_field(build, "active", ()))


def _zone_id(world) -> str:
    zones = sorted(item.id for item in world.entities.values() if "zone" in item.components)
    if len(zones) != 1:
        raise ScenarioExecutionError(f"expected exactly one zone, found {zones}")
    return zones[0]


def _record(command_id: str, result) -> RootExecution:
    event = result.trace.root_event
    return RootExecution(command_id, event.id, event.type, tuple(sorted(result.triggered_law_ids)), result.trace.to_dict())


def run_scenario(
    scenario: Any, active_skill_ids: Iterable[str] | None = None,
    *, catalog: dict[str, Any] | None = None,
    compile_mechanic: Callable[[Any], dict[str, Any]] = compile_skill,
    world_setup: Callable[[Any], None] | None = None,
    excluded_world_law_ids: Iterable[str] = (),
) -> ScenarioRun:
    """Execute one scenario from a newly loaded world; no Runtime is reusable."""
    catalog = catalog or load_skill_catalog()
    selected = tuple(sorted(active_skill_ids if active_skill_ids is not None else _default_active(scenario)))
    if len(selected) != len(set(selected)):
        raise ScenarioExecutionError("active build contains duplicate skills")
    missing = set(selected) - set(catalog)
    if missing:
        raise ScenarioExecutionError(f"unknown active skills: {sorted(missing)}")
    if len(selected) > 6 or sum(catalog[item].slot_cost for item in selected) > 6:
        raise ScenarioExecutionError("active build exceeds six skills or six slots")

    environment = _field(scenario, "environment")
    path = ROOT / "environments" / f"{environment}.json"
    world = load_world(path)
    apply_public_initialization(
        world,
        variant=_field(scenario, "environment_variant", "standard"),
        overrides=_field(scenario, "initial_fields", {}),
    )
    if world_setup is not None:
        world_setup(world)
    if not public_fields_are_bounded(world.to_dict()):
        raise ScenarioExecutionError("scenario setup produced an invalid normalized public field")
    zone_id = _zone_id(world)
    target_count = int(_field(scenario, "target_count", 1))
    zone_ids = [zone_id]
    for index in range(2, target_count + 1):
        clone = deepcopy(world.entities[zone_id])
        clone.id = f"{zone_id}:target:{index:02d}"
        clone.name = f"{clone.name or environment} target {index}"
        world.entities[clone.id] = clone
        zone_ids.append(clone.id)
    world.entities.pop("skill:equipped", None)
    for skill_id in selected:
        spec = catalog[skill_id]
        instance_id = f"skill:{skill_id}"
        world.entities[instance_id] = Entity(instance_id, archetype="skill_instance", components={"skill": {"spec_id": skill_id, "owner": ACTOR_ID, "charges": spec.charges}})

    excluded = frozenset(excluded_world_law_ids)
    world_laws = load_laws(ROOT / "substrate" / "world_laws.json")
    known_world_law_ids = {law.law_id for law in world_laws}
    unknown_exclusions = excluded - known_world_law_ids
    if unknown_exclusions:
        raise ScenarioExecutionError(f"unknown excluded world laws: {sorted(unknown_exclusions)}")
    laws = [law for law in world_laws if law.law_id not in excluded] + system_laws()
    laws += [parse_law(raw) for skill_id in selected for raw in compile_mechanic(catalog[skill_id])["laws"]]
    runtime = Engine(laws).attach(world)
    initial = runtime.state.to_dict()
    roots: list[RootExecution] = []
    cast_serial = step_serial = 0
    scenario_id = _field(scenario, "id")

    def ensure_bounded() -> None:
        if not public_fields_are_bounded(runtime.state.to_dict()):
            raise ScenarioExecutionError("normalized public field invariant was not restored by PMW closure")

    def dissipate(command_id: str) -> None:
        nonlocal step_serial
        event = Event(
            f"{scenario_id}.dissipate.{step_serial:03d}", "lab.dissipate",
            time=runtime.state.sim_time, source=None, target=zone_id,
        )
        roots.append(_record(command_id, runtime.run_event(event)))
        ensure_bounded()

    for command_index, command in enumerate(_field(scenario, "program", ())):
        op = _field(command, "op")
        command_id = f"{scenario_id}.cmd.{command_index:03d}.{op}"
        if op == "cast":
            requested = _field(command, "skill")
            cast_ids = selected if requested == "each_active" else (requested,)
            for target_zone_id in zone_ids:
                for skill_id in cast_ids:
                    if skill_id not in selected:
                        continue
                    cast_serial += 1
                    event_id = f"{scenario_id}.cast.{cast_serial:03d}.{skill_id}"
                    result = runtime.run_event(activation_event(
                        catalog[skill_id], activation_id=event_id, skill_instance_id=f"skill:{skill_id}",
                        actor_id=ACTOR_ID, zone_id=target_zone_id, time=runtime.state.sim_time,
                    ))
                    roots.append(_record(command_id, result))
                    ensure_bounded()
        elif op == "step":
            repeats = _field(command, "repeats", 1)
            for _ in range(repeats):
                step_serial += 1
                event = Event(f"{scenario_id}.step.{step_serial:03d}", "lab.step", time=runtime.state.sim_time, source=None, target=zone_id)
                roots.append(_record(command_id, runtime.run_event(event)))
                ensure_bounded()
                dissipate(command_id)
        elif op == "advance":
            target = _field(command, "to")
            advance = runtime.advance_to(float(target))
            for dispatch in advance.dispatches:
                roots.append(_record(command_id, dispatch.result))
                ensure_bounded()
        else:
            raise ScenarioExecutionError(f"unsupported program operation {op!r}")

    horizons: dict[str, dict[str, Any]] = {}
    raw_horizons = _field(scenario, "horizons", {})
    horizon_items = raw_horizons.items() if isinstance(raw_horizons, dict) else ((item.name, item.time) for item in raw_horizons)
    for name, when in sorted(horizon_items, key=lambda item: (float(item[1]), item[0])):
        if float(when) < runtime.state.sim_time:
            raise ScenarioExecutionError(f"horizon {name!r} precedes executed time")
        advance = runtime.advance_to(float(when))
        for dispatch in advance.dispatches:
            roots.append(_record(f"{scenario_id}.horizon.{name}", dispatch.result))
            ensure_bounded()
        horizons[name] = runtime.state.to_dict()
    return ScenarioRun(
        scenario_id, _field(scenario, "split"), environment, selected, initial,
        tuple(roots), horizons, runtime.state.to_dict(),
    )
