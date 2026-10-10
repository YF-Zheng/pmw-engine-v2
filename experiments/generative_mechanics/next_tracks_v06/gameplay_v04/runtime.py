"""Trusted Gate 1 adapter; all authoritative writes are PMW Event/Law effects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from pmw import Engine, Entity, Event, WorldState, load_world, parse_law, save_world

from .contracts import DynamicsSource, FieldDefinition, FieldProfile, GameplayContractError, TickResult
from .dynamics import (
    CLOCK_COMPONENT, COMBAT_ROUND_EVENT, DYNAMICS_COMPONENT, OWNER_TURN_EVENT,
    SOURCE_APPLY_EVENT, SOURCE_EXPIRE_EVENT, SOURCE_REMOVE_EVENT,
    WORLD_TICK_EVENT, build_dynamics_laws, source_state, validate_source,
)


@dataclass(slots=True)
class GameplaySession:
    runtime: Any
    profiles: tuple[FieldProfile, ...]

    @property
    def state(self):
        return self.runtime.state

    @property
    def stats(self):
        return self.runtime.stats

    def snapshot(self):
        return self.runtime.snapshot()


def clock_entity(clock_id: str = "pmw:v04:clock") -> Entity:
    return Entity(clock_id, "pmw_gameplay_clock", components={CLOCK_COMPONENT: {
        "next_step": 1, "next_time": 1.0, "last_completed_step": 0,
    }})


def discover_profiles(world: WorldState) -> tuple[FieldProfile, ...]:
    profiles: list[FieldProfile] = []
    for entity_id, entity in sorted(world.entities.items()):
        component = entity.components.get(DYNAMICS_COMPONENT)
        if not isinstance(component, dict):
            continue
        fields = component.get("fields")
        if not isinstance(fields, dict):
            raise GameplayContractError(f"invalid dynamics fields on {entity_id!r}")
        for field_id, state in sorted(fields.items()):
            baseline = state["baseline"]
            definition = FieldDefinition(
                field_id, float(state["domain_min"]), float(state["domain_max"]),
                float(state["value"]), float(baseline["target"]),
                float(baseline["rate"]), baseline["curve"],
                len(state["persistent_patches"]), len(state["temporary_modifiers"]),
            )
            mirror = ("pmw_gameplay_actor", "mana") if field_id == "mana" and "pmw_gameplay_actor" in entity.components else None
            profiles.append(FieldProfile(entity_id, definition, mirror))
    return tuple(profiles)


def build_runtime(
    world: WorldState,
    profiles: Iterable[FieldProfile] | None = None,
    extra_laws: Iterable[Mapping[str, Any]] = (),
) -> GameplaySession:
    profiles = tuple(profiles) if profiles is not None else discover_profiles(world)
    laws = [*build_dynamics_laws(profiles), *[dict(item) for item in extra_laws]]
    parsed = [parse_law(item) for item in sorted(laws, key=lambda item: item["id"])]
    return GameplaySession(Engine(parsed).attach(world), profiles)


def apply_source(
    session: GameplaySession,
    *,
    entity_id: str,
    field_id: str,
    layer: str,
    source: DynamicsSource,
):
    if layer not in {"persistent", "temporary"}:
        raise GameplayContractError("layer must be persistent or temporary")
    profile = _profile(session, entity_id, field_id)
    validate_source(source, profile.field, temporary=layer == "temporary")
    field = _field_state(session, entity_id, field_id)
    all_slots = [
        *field["persistent_patches"].values(),
        *field["temporary_modifiers"].values(),
    ]
    if any(item["active"] and item["source_id"] == source.source_id for item in all_slots):
        raise GameplayContractError("source_id is already active on this Field")
    if source.curve_priority is not None and any(
        item["active"] and item["curve_priority"] == source.curve_priority
        for item in all_slots
    ):
        raise GameplayContractError("curve override priority conflict")
    key = "persistent_patches" if layer == "persistent" else "temporary_modifiers"
    slot = next((name for name, item in sorted(field[key].items()) if not item["active"]), None)
    if slot is None:
        raise GameplayContractError(f"{layer} source capacity exhausted")
    handle = None
    expiry_event = None
    if layer == "temporary":
        handle = f"pmw:v04:expiry:{entity_id}:{field_id}:{source.source_id}:{source.owner}"
        expiry_time = session.state.sim_time + source.duration_ticks
        expiry_payload = {
            "entity_id": entity_id, "field_id": field_id, "layer": layer,
            "slot": slot, "source_id": source.source_id, "owner": source.owner,
            "expiry_handle": handle,
        }
        expiry_event = {
            "id": handle, "type": SOURCE_EXPIRE_EVENT, "time": expiry_time,
            "source": source.owner, "target": entity_id, "payload": expiry_payload,
        }
    payload = {
        "entity_id": entity_id, "field_id": field_id, "layer": layer,
        "slot": slot, "source_id": source.source_id, "owner": source.owner,
        "source": source_state(source, handle), "expiry_event": expiry_event,
    }
    event = Event(
        id=f"pmw:v04:source:apply:{entity_id}:{field_id}:{source.source_id}",
        type=SOURCE_APPLY_EVENT, time=session.state.sim_time,
        source=source.owner, target=entity_id, payload=payload,
    )
    result = session.runtime.run_event(event)
    if not result.changed:
        raise GameplayContractError("source apply did not match its reserved slot")
    return result


def remove_source(
    session: GameplaySession,
    *,
    entity_id: str,
    field_id: str,
    source_id: str,
    owner: str,
):
    _profile(session, entity_id, field_id)
    field = _field_state(session, entity_id, field_id)
    matches = []
    for layer, key in (("persistent", "persistent_patches"), ("temporary", "temporary_modifiers")):
        matches.extend(
            (layer, slot, item) for slot, item in field[key].items()
            if item["active"] and item["source_id"] == source_id and item["owner"] == owner
        )
    if len(matches) != 1:
        raise GameplayContractError("source ownership does not identify one active source")
    layer, slot, item = matches[0]
    payload = {
        "entity_id": entity_id, "field_id": field_id, "layer": layer,
        "slot": slot, "source_id": source_id, "owner": owner,
        "expiry_handle": item["expiry_handle"],
    }
    result = session.runtime.run_event(Event(
        id=f"pmw:v04:source:remove:{entity_id}:{field_id}:{source_id}",
        type=SOURCE_REMOVE_EVENT, time=session.state.sim_time,
        source=owner, target=entity_id, payload=payload,
    ))
    if not result.changed:
        raise GameplayContractError("source removal failed")
    return result


def advance_world_tick(session: GameplaySession, *, clock_id: str = "pmw:v04:clock") -> TickResult:
    clock = _clock(session, clock_id)
    step = clock["next_step"]
    target_time = clock["next_time"]
    session.runtime.advance_to(float(target_time))
    _validate_runtime_priorities(session)
    result = session.runtime.run_event(Event(
        id=f"pmw:v04:world-tick:{step:08d}", type=WORLD_TICK_EVENT,
        time=float(target_time), source=clock_id, payload={"step": step},
    ))
    completed = _clock(session, clock_id)
    if completed["last_completed_step"] != step or completed["next_step"] != step + 1:
        raise GameplayContractError("world_tick did not complete exactly once")
    return TickResult(step, float(target_time), result, session.snapshot())


def run_phase_event(session: GameplaySession, phase: str, *, actor_id: str | None = None):
    event_type = {"combat_round": COMBAT_ROUND_EVENT, "owner_turn": OWNER_TURN_EVENT}.get(phase)
    if event_type is None:
        raise GameplayContractError("unknown gameplay clock phase")
    return session.runtime.run_event(Event(
        id=f"pmw:v04:{phase}:{session.state.tick:08d}:{actor_id or 'none'}",
        type=event_type, time=session.state.sim_time, source=actor_id,
        payload={"actor_id": actor_id},
    ))


def save_checkpoint(path: str | Path, session: GameplaySession) -> None:
    save_world(path, session.state)


def load_checkpoint(path: str | Path, profiles: Iterable[FieldProfile] | None = None) -> GameplaySession:
    return build_runtime(load_world(path), profiles)


def _clock(session: GameplaySession, clock_id: str) -> dict:
    entity = session.state.entities.get(clock_id)
    if entity is None or CLOCK_COMPONENT not in entity.components:
        raise GameplayContractError("missing gameplay clock")
    return entity.components[CLOCK_COMPONENT]


def _profile(session: GameplaySession, entity_id: str, field_id: str) -> FieldProfile:
    matches = [item for item in session.profiles if item.entity_id == entity_id and item.field.id == field_id]
    if len(matches) != 1:
        raise GameplayContractError("unknown dynamics Field instance")
    return matches[0]


def _field_state(session: GameplaySession, entity_id: str, field_id: str) -> dict:
    try:
        return session.state.entities[entity_id].components[DYNAMICS_COMPONENT]["fields"][field_id]
    except KeyError as exc:
        raise GameplayContractError("dynamics Field state is unavailable") from exc


def _validate_runtime_priorities(session: GameplaySession) -> None:
    for profile in session.profiles:
        field = _field_state(session, profile.entity_id, profile.field.id)
        priorities = [
            item["curve_priority"]
            for layer in ("persistent_patches", "temporary_modifiers")
            for item in field[layer].values()
            if item["active"] and item["curve_priority"] >= 0
        ]
        if len(priorities) != len(set(priorities)):
            raise GameplayContractError("runtime curve priorities are ambiguous")
