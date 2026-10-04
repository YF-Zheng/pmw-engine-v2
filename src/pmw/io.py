from __future__ import annotations

import json
from pathlib import Path

from .dsl import Law, parse_law
from .observation import ObservationRule, parse_observation_rule
from .types import Entity, Event, Relation, WorldState
from .validation import validate_event, validate_laws, validate_observation_rules, validate_runtime_world, validate_world


def load_world(path: str | Path) -> WorldState:
    raw = _read_json(path)
    validate_world(raw, str(path))
    time = raw.get("time", {})
    return WorldState(
        world_id=str(raw.get("world_id", Path(path).stem)),
        tick=int(time.get("tick", 0)),
        sim_time=float(time.get("sim_time", 0.0)),
        rng_state=dict(raw.get("rng", {})),
        entities={item["id"]: Entity(item["id"], item.get("archetype", ""), item.get("name"), set(item.get("tags", [])), dict(item.get("components", {}))) for item in raw.get("entities", [])},
        relations={item["id"]: Relation(item["id"], item["type"], item["source"], item["target"], set(item.get("tags", [])), dict(item.get("components", {}))) for item in raw.get("relations", [])},
        scheduled_events=[Event(**({**item, "provenance": item.get("provenance", {"kind": "scheduled", "parent_event": None})})) for item in raw.get("scheduled_events", [])],
    )


def save_world(path: str | Path, world: WorldState) -> None:
    validate_runtime_world(world)
    Path(path).write_text(json.dumps(world.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_laws(path: str | Path) -> list[Law]:
    raw = _read_json(path)
    validate_laws(raw, str(path))
    return [parse_law(item, validate=False) for item in raw.get("laws", [])]


def load_observation_rules(path: str | Path) -> list[ObservationRule]:
    raw = _read_json(path)
    validate_observation_rules(raw, str(path))
    return [parse_observation_rule(item, validate=False) for item in raw["observation_rules"]]


def load_event(path: str | Path) -> Event:
    raw = _read_json(path)
    validate_event(raw, str(path))
    raw.setdefault("provenance", {"kind": "external", "parent_event": None})
    return Event(**raw)


def _read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
