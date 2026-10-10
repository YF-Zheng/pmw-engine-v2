"""Actor-safe, immutable observation documents for gameplay AI.

The trusted builder may inspect a live gameplay session.  Its output is a
canonical JSON value with no reference back to WorldState, Engine, Runtime, or
their mutable component dictionaries.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping

from .actions import ACTOR_COMPONENT, ActionRegistry
from .contracts import GameplayContractError
from .dynamics import CLOCK_COMPONENT, DYNAMICS_COMPONENT
from .status import STATUS_COMPONENT


OBSERVATION_PROTOCOL = "pmw-actor-observation-v0.4"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True, slots=True)
class ActorObservation:
    """An immutable JSON-only capability passed to a controller."""

    document_json: str
    canonical_sha256: str

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "ActorObservation":
        raw = canonical_json(document)
        owned = json.loads(raw)
        if owned.get("protocol") != OBSERVATION_PROTOCOL:
            raise GameplayContractError("invalid ActorObservation protocol")
        if not isinstance(owned.get("observer_id"), str):
            raise GameplayContractError("ActorObservation observer_id is invalid")
        return cls(raw, hashlib.sha256(raw.encode("ascii")).hexdigest())

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.document_json)

    @property
    def observer_id(self) -> str:
        return self.to_dict()["observer_id"]

    @property
    def revision_token(self) -> str:
        return self.to_dict()["revision_token"]

    def for_observer(self, observer_id: str) -> "ActorObservation":
        document = self.to_dict()
        if observer_id not in document["actors"]:
            raise GameplayContractError("modeled observer is not visible")
        document["observer_id"] = observer_id
        document["revision_token"] = _revision_token(document)
        return ActorObservation.from_document(document)


@dataclass(frozen=True, slots=True)
class ObservationDisclosure:
    """Explicit knowledge granted to one planning call.

    `revealed_actions` is actor -> action IDs.  The observer's equipped actions
    are added automatically; other actors receive only built-ins plus these
    explicitly revealed IDs.
    """

    revealed_actions: tuple[tuple[str, tuple[str, ...]], ...] = ()
    visible_laws: tuple[tuple[str, str], ...] = ()
    hostile_actor_ids: tuple[str, ...] = ()
    visible_relation_types: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        revealed_actions: Mapping[str, Iterable[str]] | None = None,
        visible_laws: Mapping[str, str] | None = None,
        hostile_actor_ids: Iterable[str] = (),
        visible_relation_types: Iterable[str] = (),
    ) -> "ObservationDisclosure":
        return cls(
            tuple((key, tuple(sorted(set(values)))) for key, values in sorted((revealed_actions or {}).items())),
            tuple(sorted((visible_laws or {}).items())),
            tuple(sorted(set(hostile_actor_ids))),
            tuple(sorted(set(visible_relation_types))),
        )


class ActorObservationBuilder:
    """Trusted projection from one live session into an actor-safe document."""

    def build(
        self,
        session,
        registry: ActionRegistry,
        observer_id: str,
        disclosure: ObservationDisclosure | None = None,
    ) -> ActorObservation:
        disclosure = disclosure or ObservationDisclosure()
        observer = session.state.entities.get(observer_id)
        if observer is None or ACTOR_COMPONENT not in observer.components:
            raise GameplayContractError("observation subject is not an Actor")
        current_area = _current_area(session.state, observer_id)
        visible_actor_ids = tuple(sorted(
            relation.source for relation in session.state.relations.values()
            if relation.type == "located_in" and relation.target == current_area
            and relation.source in session.state.entities
            and ACTOR_COMPONENT in session.state.entities[relation.source].components
        ))
        revealed = dict(disclosure.revealed_actions)
        builtins = tuple(sorted(key for key, value in registry.actions.items() if value.builtin))
        actors: dict[str, Any] = {}
        known_actions: dict[str, list[str]] = {}
        visible_status_ids: set[str] = set()
        for actor_id in visible_actor_ids:
            entity = session.state.entities[actor_id]
            actors[actor_id] = _public_actor(entity)
            visible_status_ids.update(
                row["spec_id"] for row in actors[actor_id]["statuses"] if row["active"]
            )
            extra = set(revealed.get(actor_id, ()))
            if actor_id == observer_id:
                extra.update(_equipped_action_ids(
                    entity.components[ACTOR_COMPONENT].get("active_equipped", ()), registry,
                ))
            allowed = set(builtins) | {item for item in extra if item in registry.actions}
            known_actions[actor_id] = sorted(allowed)
        area = session.state.entities[current_area]
        fields = _public_fields(area.components.get(DYNAMICS_COMPONENT, {}).get("fields", {}))
        scoped_relations = []
        scoped_object_ids: set[str] = set()
        allowed_relation_types = set(disclosure.visible_relation_types)
        for relation in sorted(session.state.relations.values(), key=lambda item: item.id):
            if relation.type not in allowed_relation_types or current_area not in {relation.source, relation.target}:
                continue
            other = relation.target if relation.source == current_area else relation.source
            if other not in session.state.entities:
                continue
            scoped_object_ids.add(other)
            scoped_relations.append({
                "id": relation.id, "type": relation.type,
                "source": relation.source, "target": relation.target,
            })
        scoped_objects = {
            object_id: _public_scoped_object(session.state.entities[object_id])
            for object_id in sorted(scoped_object_ids)
            if object_id not in actors and object_id != current_area
        }
        status_polarities = {
            status_id: registry.statuses[status_id].polarity
            for status_id in sorted(visible_status_ids)
            if status_id in registry.statuses
        }
        clock = next((
            entity.components[CLOCK_COMPONENT]
            for entity in session.state.entities.values()
            if CLOCK_COMPONENT in entity.components
        ), {"next_step": session.state.tick + 1, "next_time": session.state.sim_time + 1.0,
            "last_completed_step": session.state.tick})
        hostiles = sorted(
            set(disclosure.hostile_actor_ids) & set(visible_actor_ids)
            if disclosure.hostile_actor_ids
            else set(visible_actor_ids) - {observer_id}
        )
        document = {
            "protocol": OBSERVATION_PROTOCOL,
            "observer_id": observer_id,
            "revision_token": "",
            "clock": {
                "world_tick": int(session.state.tick),
                "sim_time": float(session.state.sim_time),
                "next_step": int(clock["next_step"]),
                "next_time": float(clock["next_time"]),
                "last_completed_step": int(clock["last_completed_step"]),
            },
            "current_area_id": current_area,
            "area": {"id": current_area, "fields": fields},
            "scoped_objects": scoped_objects,
            "scoped_relations": scoped_relations,
            "actors": actors,
            "known_actions": known_actions,
            "status_polarities": status_polarities,
            "hostile_actor_ids": hostiles,
            "visible_laws": [{"id": key, "canonical_sha256": value} for key, value in disclosure.visible_laws],
        }
        document["revision_token"] = _revision_token(document)
        return ActorObservation.from_document(document)


def _revision_token(document: Mapping[str, Any]) -> str:
    owned = json.loads(canonical_json(document))
    owned["revision_token"] = ""
    return hashlib.sha256(canonical_json(owned).encode("ascii")).hexdigest()


def _current_area(world, actor_id: str) -> str:
    areas = sorted(
        relation.target for relation in world.relations.values()
        if relation.type == "located_in" and relation.source == actor_id
    )
    if len(areas) != 1:
        raise GameplayContractError("Actor observation requires one current Area")
    return areas[0]


def _public_actor(entity) -> dict[str, Any]:
    actor = entity.components[ACTOR_COMPONENT]
    public = {
        key: actor[key]
        for key in (
            "hp", "max_hp", "mana", "max_mana", "shield",
            "power", "control", "resilience", "agility", "traits",
        )
    }
    slots = entity.components.get(STATUS_COMPONENT, {}).get("slots", {})
    public["statuses"] = [
        {
            "active": True,
            "spec_id": row["spec_id"],
            "stacks": row["stacks"],
            "remaining": row["remaining"],
            "clock_unit": row["clock_unit"],
            "granted_traits": sorted(row.get("granted_traits", ())),
        }
        for _, row in sorted(slots.items()) if row.get("active")
    ]
    mana_field = entity.components.get(DYNAMICS_COMPONENT, {}).get("fields", {}).get("mana")
    if mana_field is not None:
        public["mana_dynamics"] = _public_field(mana_field)
    return public


def _equipped_action_ids(rows, registry: ActionRegistry) -> tuple[str, ...]:
    result = []
    for row in rows:
        if isinstance(row, str) and row:
            result.append(row)
        elif isinstance(row, Mapping) and isinstance(row.get("id"), str):
            action = registry.actions.get(row["id"])
            if (
                action is not None
                and row.get("version") == action.version
                and row.get("canonical_hash") == action.canonical_hash
            ):
                result.append(row["id"])
    return tuple(result)


def _public_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    return {field_id: _public_field(value) for field_id, value in sorted(fields.items())}


def _public_scoped_object(entity) -> dict[str, Any]:
    return {
        "archetype": entity.archetype,
        "is_area": "pmw_gameplay_area" in entity.components,
        "fields": _public_fields(entity.components.get(DYNAMICS_COMPONENT, {}).get("fields", {})),
    }


def _public_field(field: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = field.get("diagnostics", {})
    baseline = field["baseline"]
    return {
        "value": float(field["value"]),
        "domain_min": float(field["domain_min"]),
        "domain_max": float(field["domain_max"]),
        "effective_target": float(diagnostics.get("effective_target", baseline["target"])),
        "effective_rate": float(diagnostics.get("effective_rate", baseline["rate"])),
        "effective_curve": diagnostics.get("effective_curve", baseline["curve"]),
    }
