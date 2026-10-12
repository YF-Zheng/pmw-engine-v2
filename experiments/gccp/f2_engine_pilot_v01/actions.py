"""Trusted F2 action facade over Gameplay and PMW public APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pmw import Event

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRequest, resolve_action
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import change_loadout, skill_ref
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    spend_world_time,
)

from .engine_scenario import (
    ACTOR_ID,
    AREA_ID,
    DIAGNOSTIC_MATERIAL,
    F2_COMPONENT,
    REPAIR_MATERIAL,
    ROOTS,
    F2Runtime,
)
from .observation import public_observation


PREP_ACTIONS = ("calibrate", "forge_water", "forge_resonance", "probe")
REPAIR_ACTIONS = ("repair_water", "repair_resonance")


@dataclass(frozen=True, slots=True)
class F2Transition:
    action: str
    before: dict[str, Any]
    after: dict[str, Any]
    event_results: tuple[dict[str, Any], ...]
    world_ticks: tuple[dict[str, Any], ...]
    response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "before": self.before,
            "after": self.after,
            "event_results": list(self.event_results),
            "world_ticks": list(self.world_ticks),
            "response": self.response,
        }


def legal_actions(subject: F2Runtime, *, prep_limit: int = 3) -> tuple[str, ...]:
    private = _private(subject)
    inventory = _inventory(subject)
    spent = _spent(subject)
    actions = list(REPAIR_ACTIONS) if inventory[REPAIR_MATERIAL] == 1 and private["repair_mode"] is None else []
    if spent >= prep_limit or private["repair_mode"] is not None:
        return tuple(actions)
    if not private["calibrated"]:
        actions.append("calibrate")
    if private["forged_probe"] is None and inventory[DIAGNOSTIC_MATERIAL] == 1:
        actions.extend(("forge_water", "forge_resonance"))
    if private["forged_probe"] is not None and not private["probe_used"]:
        actions.append("probe")
    return tuple(actions)


def execute_preparation(subject: F2Runtime, action: str, *, prep_limit: int = 3) -> F2Transition:
    if action not in legal_actions(subject, prep_limit=prep_limit) or action not in PREP_ACTIONS:
        raise GameplayContractError("F2 preparation action is not legal")
    before = public_observation(subject)
    stability_before = before["stability"]
    events: list[dict[str, Any]] = []
    if action == "calibrate":
        result = subject.session.runtime.run_event(Event(
            _event_id(subject, "calibrate"), "gccp.f2.calibrate", subject.session.state.sim_time,
            ACTOR_ID, AREA_ID, {},
        ))
        if not result.changed:
            raise GameplayContractError("calibration did not commit")
        events.append(_event_result(result))
    elif action.startswith("forge_"):
        root = action.removeprefix("forge_")
        result = subject.session.runtime.run_event(Event(
            _event_id(subject, action), "gccp.f2.forge", subject.session.state.sim_time,
            ACTOR_ID, AREA_ID, {"probe_kind": root},
        ))
        if not result.changed:
            raise GameplayContractError("probe forge receipt did not commit")
        events.append(_event_result(result))
        install = subject.runtime.install_blueprint(subject.probe_blueprints[root])
        events.append(_event_result(install.event_result))
        loadout = change_loadout(
            subject.session,
            subject.runtime.manifest,
            actor_id=ACTOR_ID,
            operation="equip_active",
            skill=skill_ref(subject.probe_blueprints[root]),
            slot=2,
        )
        events.append(_event_result(loadout))
    else:
        root = _private(subject)["forged_probe"]
        outcome = resolve_action(
            subject.session,
            subject.runtime.action_registry,
            ActionRequest(_request_id(subject, action), ACTOR_ID, f"f2_probe_{root}", ACTOR_ID),
        )
        events.append(_event_result(outcome.event_result))

    time_result = spend_world_time(subject.session, 1, reason="exploration")
    events.append(_event_result(time_result.event_result))
    after = public_observation(subject)
    response = {
        "calibrated_interface": after["calibrated_interface"] if action == "calibrate" else None,
        "probe_implemented": after["probe_implemented"] if action == "probe" else None,
        "stability_delta": after["stability"] - stability_before,
    }
    return F2Transition(
        action, before, after, tuple(events),
        tuple(_tick_result(tick) for tick in time_result.ticks), response,
    )


def execute_repair(subject: F2Runtime, action: str) -> tuple[F2Transition, bool]:
    if action not in REPAIR_ACTIONS or action not in legal_actions(subject):
        raise GameplayContractError("F2 repair action is not legal")
    root = action.removeprefix("repair_")
    before = public_observation(subject)
    outcome = resolve_action(
        subject.session,
        subject.runtime.action_registry,
        ActionRequest(_request_id(subject, action), ACTOR_ID, f"f2_repair_{root}", None),
    )
    time_result = spend_world_time(subject.session, 4, reason="exploration")
    after = public_observation(subject)
    success = after["stability"] >= before["stability"]
    transition = F2Transition(
        action, before, after,
        (_event_result(outcome.event_result), _event_result(time_result.event_result)),
        tuple(_tick_result(tick) for tick in time_result.ticks),
        {"terminal_success": success, "stability_delta": after["stability"] - before["stability"]},
    )
    return transition, success


def _event_result(result: Any) -> dict[str, Any]:
    return {"changed": result.changed, "trace": result.trace.to_dict()}


def _tick_result(result: Any) -> dict[str, Any]:
    return {
        "step": result.step,
        "time": result.time,
        "event_result": _event_result(result.event_result),
        "snapshot": {
            "world_id": result.snapshot.world_id,
            "tick": result.snapshot.tick,
            "sim_time": result.snapshot.sim_time,
            "revision": result.snapshot.revision,
        },
    }


def _private(subject: F2Runtime) -> dict[str, Any]:
    return subject.session.state.entities[AREA_ID].components[F2_COMPONENT]


def _inventory(subject: F2Runtime) -> dict[str, int]:
    return subject.session.state.entities[ACTOR_ID].components[
        "pmw_gameplay_material_inventory"
    ]["quantities"]


def _spent(subject: F2Runtime) -> int:
    clock = next(
        entity for entity in subject.session.state.entities.values()
        if TIME_BUDGET_COMPONENT in entity.components
    )
    return clock.components[TIME_BUDGET_COMPONENT]["spent_ticks"]


def _event_id(subject: F2Runtime, action: str) -> str:
    return f"gccp_f2_{action}_{subject.session.state.tick:02d}"


def _request_id(subject: F2Runtime, action: str) -> str:
    return f"f2_{action}_{subject.session.state.tick:02d}"
