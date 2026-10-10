"""Projection-only PMW sandbox and newest-state action revalidation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from pmw import Entity, Relation, WorldState

from .action_compiler import build_action_session
from .actions import ACTOR_COMPONENT, ActionOutcome, ActionRegistry, ActionRequest, resolve_action
from .blueprints import field_state
from .contracts import FieldDefinition, GameplayContractError
from .dynamics import CLOCK_COMPONENT, DYNAMICS_COMPONENT
from .observation import ActorObservation, ActorObservationBuilder, ObservationDisclosure, canonical_json
from .runtime import run_phase_event, advance_world_tick
from .status import STATUS_COMPONENT, active_status_slot, neutral_status_slot


@dataclass(frozen=True, slots=True)
class SimulationResult:
    legal: bool
    next_observation: ActorObservation
    outcome_json: str
    trace_json: str
    rejection: str | None = None

    def outcome(self) -> dict[str, Any]:
        return json.loads(self.outcome_json)

    def trace(self) -> dict[str, Any]:
        return json.loads(self.trace_json)


@dataclass(frozen=True, slots=True)
class RevalidationResult:
    accepted: bool
    outcome: ActionOutcome | None
    rejection: str | None
    latest_observation: ActorObservation


class SandboxSimulator:
    """Runs the production resolver over a world rebuilt from one observation."""

    def __init__(self, registry: ActionRegistry):
        self._registry = registry
        self._builder = ActorObservationBuilder()

    def simulate(
        self,
        observation: ActorObservation,
        request: ActionRequest,
        *,
        owner_turn_before: bool = False,
        complete_round_after: bool = False,
    ) -> SimulationResult:
        session, registry, disclosure = self._build(observation)
        before = session.state.to_dict()
        try:
            if owner_turn_before:
                run_phase_event(session, "owner_turn", actor_id=request.actor_id)
            outcome = resolve_action(session, registry, request)
            if complete_round_after:
                run_phase_event(session, "combat_round")
                advance_world_tick(session)
            next_observation = self._builder.build(session, registry, observation.observer_id, disclosure)
            public_outcome = {
                "action_id": outcome.definition.id,
                "actor_id": request.actor_id,
                "target_actor_id": request.target_actor_id,
                "cost": {"duration": outcome.cost.duration, "mana": outcome.cost.mana},
                "effects": [dict(item) for item in outcome.effect_outcomes],
            }
            return SimulationResult(
                True,
                next_observation,
                canonical_json(public_outcome),
                canonical_json(outcome.event_result.trace.semantic_projection()),
            )
        except GameplayContractError as exc:
            if session.state.to_dict() != before:
                raise AssertionError("rejected sandbox action mutated projected state") from exc
            return SimulationResult(False, observation, "{}", "{}", str(exc))

    def _build(self, observation: ActorObservation):
        document = observation.to_dict()
        registry = _registry_projection(self._registry, document)
        entities: dict[str, Entity] = {}
        known = document["known_actions"]
        for actor_id, public in sorted(document["actors"].items()):
            actor = {
                "blueprint_id": "observed_actor",
                "controller": "ai",
                **{key: public[key] for key in (
                    "hp", "max_hp", "mana", "max_mana", "shield",
                    "power", "control", "resilience", "agility", "traits",
                )},
                "active_equipped": [
                    action_id for action_id in known[actor_id]
                    if action_id in registry.actions and not registry.actions[action_id].builtin
                ][:6] + [None] * max(0, 6 - sum(
                    1 for action_id in known[actor_id]
                    if action_id in registry.actions and not registry.actions[action_id].builtin
                )),
                "active_stowed": [None] * 6,
                "passive_equipped": [None] * 6,
            }
            slots = {f"slot_{index}": neutral_status_slot() for index in range(8)}
            for index, row in enumerate(public["statuses"][:8]):
                spec = registry.statuses.get(row["spec_id"])
                if spec is not None:
                    value = active_status_slot(
                        spec,
                        instance_id=f"observed_{actor_id}_{index}",
                        source_id=f"observed_{row['spec_id']}",
                        owner_id=actor_id,
                        stacks=row["stacks"],
                    )
                    value["remaining"] = row["remaining"]
                    value["clock_unit"] = row["clock_unit"]
                else:
                    value = {
                        **neutral_status_slot(), "active": True,
                        "instance_id": f"observed_{actor_id}_{index}",
                        "spec_id": row["spec_id"], "source_id": f"observed_{row['spec_id']}",
                        "owner_id": actor_id, "stacks": row["stacks"],
                        "remaining": row["remaining"], "clock_unit": row["clock_unit"],
                        "granted_traits": list(row["granted_traits"]),
                    }
                slots[f"slot_{index}"] = value
            components = {ACTOR_COMPONENT: actor, STATUS_COMPONENT: {"slots": slots}}
            if "mana_dynamics" in public:
                components[DYNAMICS_COMPONENT] = {
                    "fields": {"mana": _field_from_public("mana", public["mana_dynamics"])}
                }
            entities[actor_id] = Entity(actor_id, "pmw_gameplay_actor", components=components)
        area_id = document["current_area_id"]
        entities[area_id] = Entity(area_id, "pmw_gameplay_area", components={
            "pmw_gameplay_area": {"blueprint_id": "observed_area", "ecology_state": "observed"},
            DYNAMICS_COMPONENT: {"fields": {
                key: _field_from_public(key, value)
                for key, value in sorted(document["area"]["fields"].items())
            }},
        })
        for object_id, public in sorted(document.get("scoped_objects", {}).items()):
            components = {}
            if public["is_area"]:
                components["pmw_gameplay_area"] = {"blueprint_id": "observed_area", "ecology_state": "observed"}
            if public["fields"]:
                components[DYNAMICS_COMPONENT] = {"fields": {
                    key: _field_from_public(key, value)
                    for key, value in sorted(public["fields"].items())
                }}
            entities[object_id] = Entity(object_id, public["archetype"], components=components)
        clock = document["clock"]
        entities["pmw:v04:clock"] = Entity("pmw:v04:clock", "pmw_gameplay_clock", components={
            CLOCK_COMPONENT: {
                "next_step": clock["next_step"], "next_time": clock["next_time"],
                "last_completed_step": clock["last_completed_step"],
            }
        })
        relations = {
            f"located:{actor_id}:{area_id}": Relation(
                f"located:{actor_id}:{area_id}", "located_in", actor_id, area_id
            )
            for actor_id in sorted(document["actors"])
        }
        for row in document.get("scoped_relations", ()):
            relations[row["id"]] = Relation(row["id"], row["type"], row["source"], row["target"])
        world = WorldState(
            "actor_safe_sandbox", tick=clock["world_tick"], sim_time=clock["sim_time"],
            entities=entities, relations=relations,
        )
        session = build_action_session(world, registry=registry)
        disclosure = ObservationDisclosure.create(
            revealed_actions=document["known_actions"],
            visible_laws={row["id"]: row["canonical_sha256"] for row in document["visible_laws"]},
            hostile_actor_ids=document["hostile_actor_ids"],
            visible_relation_types=tuple(sorted({row["type"] for row in document.get("scoped_relations", ())})),
        )
        return session, registry, disclosure


def revalidate_and_execute(
    session,
    registry: ActionRegistry,
    request: ActionRequest,
    *,
    disclosure: ObservationDisclosure | None = None,
) -> RevalidationResult:
    """Submit through the production resolver against the newest live state."""

    latest = ActorObservationBuilder().build(session, registry, request.actor_id, disclosure)
    before = session.state.to_dict()
    # Gate 2 deliberately knows how to resolve any trusted definition in its
    # registry.  The controller boundary additionally enforces that this Actor
    # currently knows/equips the requested action.
    from .legal_actions import LegalActionGenerator
    current = LegalActionGenerator(registry).generate(latest, actor_id=request.actor_id, request_namespace="revalidate")
    allowed = any(
        item.request.action_id == request.action_id
        and item.request.target_actor_id == request.target_actor_id
        for item in current
    )
    if not allowed:
        return RevalidationResult(False, None, "action is no longer legal in the newest state", latest)
    try:
        outcome = resolve_action(session, registry, request)
        return RevalidationResult(True, outcome, None, latest)
    except GameplayContractError as exc:
        if session.state.to_dict() != before:
            raise AssertionError("failed live revalidation mutated WorldState") from exc
        return RevalidationResult(False, None, str(exc), latest)


def _field_from_public(field_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    definition = FieldDefinition(
        field_id,
        float(raw["domain_min"]), float(raw["domain_max"]), float(raw["value"]),
        float(raw["effective_target"]), float(raw["effective_rate"]), raw["effective_curve"],
        4, 4,
    )
    return field_state(definition)


def _registry_projection(registry: ActionRegistry, document: dict[str, Any]) -> ActionRegistry:
    action_ids = {
        action_id for values in document["known_actions"].values() for action_id in values
    }
    actions = tuple(registry.actions[key] for key in sorted(action_ids) if key in registry.actions)
    status_ids = set(document["status_polarities"])
    for action in actions:
        status_ids.update(
            effect.status_id for effect in action.effects if effect.status_id is not None
        )
    statuses = tuple(registry.statuses[key] for key in sorted(status_ids) if key in registry.statuses)
    return ActionRegistry(actions, statuses)
