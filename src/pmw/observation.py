from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .matching.matcher import MatchContext, MatchStats
from .types import Entity, Event, Relation


class MissingObserverError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ObservationRule:
    rule_id: str
    bindings: dict[str, dict[str, Any]]
    when: dict[str, Any]
    subject: str
    reveal: dict[str, tuple[str, ...]]

    @property
    def law_id(self) -> str:
        return self.rule_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.rule_id,
            "bindings": {name: deepcopy(spec) for name, spec in self.bindings.items() if name != "observer"},
            "when": deepcopy(self.when),
            "subject": self.subject,
            "reveal": {key: list(values) for key, values in self.reveal.items()},
        }


def parse_observation_rule(raw: dict[str, Any], *, validate: bool = True) -> ObservationRule:
    if validate:
        from .validation.observation import validate_observation_rules
        validate_observation_rules({"schema_version": "2.0", "observation_rules": [raw]}, "parse_observation_rule")
    bindings = {"observer": {"kind": "entity"}, **deepcopy(raw.get("bindings", {}))}
    reveal = raw.get("reveal", {})
    return ObservationRule(
        str(raw["id"]),
        bindings,
        deepcopy(raw.get("when") or {"all": []}),
        str(raw["subject"]),
        {key: tuple(reveal.get(key, ())) for key in ("core", "tags", "components")},
    )


@dataclass(frozen=True, slots=True)
class Observation:
    observer_id: str
    entities: tuple[dict[str, Any], ...]
    relations: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "observer_id": self.observer_id,
            "entities": deepcopy(list(self.entities)),
            "relations": deepcopy(list(self.relations)),
        }


class ObserverView:
    __slots__ = ("_runtime", "observer_id")

    def __init__(self, runtime, observer_id: str) -> None:
        self._runtime = runtime
        self.observer_id = observer_id

    def observe(self) -> Observation:
        return self._runtime.observe(self.observer_id)


@dataclass(slots=True)
class _Grant:
    obj: Entity | Relation
    core: set[str]
    tags: set[str]
    components: set[str]


def observe_runtime(engine, runtime, observer_id: str) -> Observation:
    if not isinstance(observer_id, str) or not observer_id or observer_id not in runtime.state.entities:
        raise MissingObserverError(f"missing observer entity '{observer_id}'")
    observer = runtime.state.entities[observer_id]
    runtime.stats.observation_calls += 1
    if not engine.observation_rules:
        return Observation(observer_id, (), ())

    world = runtime._read_view()
    neutral_event = Event("__pmw_observation__", "__pmw_observation__")
    context = MatchContext(world, neutral_event, index_provider=runtime.get_index)
    grants: dict[tuple[str, str], _Grant] = {}
    seen_rule_subjects: set[tuple[str, str, str]] = set()

    for rule in engine.observation_rules:
        runtime.stats.observation_rules_evaluated += 1
        stats = MatchStats()
        matches = engine._observation_matcher(
            rule,
            world,
            neutral_event,
            context=context,
            plan=engine.observation_plans[rule.rule_id],
            seed_bindings={"observer": observer},
            stats=stats,
        )
        runtime.stats.observation_matches += len(matches)
        runtime.stats.observation_candidate_rows += stats.candidate_rows_examined
        subject_name = rule.subject[1:]
        for bindings in matches:
            subject = bindings[subject_name]
            kind = "relation" if isinstance(subject, Relation) else "entity"
            runtime.stats.observation_raw_grants += 1
            dedup_key = (rule.rule_id, kind, subject.id)
            if dedup_key in seen_rule_subjects:
                runtime.stats.observation_deduplicated_grants += 1
                continue
            seen_rule_subjects.add(dedup_key)
            key = (kind, subject.id)
            grant = grants.get(key)
            if grant is None:
                grant = grants[key] = _Grant(subject, set(), set(), set())
            grant.core.update(rule.reveal["core"])
            grant.tags.update(rule.reveal["tags"])
            grant.components.update(rule.reveal["components"])

    visible_entity_ids = {object_id for kind, object_id in grants if kind == "entity"}
    entities = tuple(
        _render_grant(grants[("entity", object_id)], visible_entity_ids, runtime)
        for object_id in sorted(visible_entity_ids)
    )
    relation_ids = sorted(object_id for kind, object_id in grants if kind == "relation")
    relations = tuple(
        _render_grant(grants[("relation", object_id)], visible_entity_ids, runtime)
        for object_id in relation_ids
    )
    runtime.stats.observation_entities_returned += len(entities)
    runtime.stats.observation_relations_returned += len(relations)
    return Observation(observer_id, entities, relations)


def _render_grant(grant: _Grant, visible_entity_ids: set[str], runtime) -> dict[str, Any]:
    obj = grant.obj
    result: dict[str, Any] = {"id": obj.id}
    for field in sorted(grant.core):
        if field in {"source", "target"} and getattr(obj, field) not in visible_entity_ids:
            continue
        result[field] = deepcopy(getattr(obj, field))
    visible_tags = sorted(grant.tags & obj.tags)
    if visible_tags:
        result["tags"] = visible_tags
    projected_components: dict[str, Any] = {}
    for path in sorted(grant.components, key=lambda item: (len(item.split(".")), item)):
        parts = path.split(".")
        found, value = _read_dict_path(obj.components, parts)
        if not found:
            continue
        _write_dict_path(projected_components, parts, _owned_json(value))
        runtime.stats.observation_component_paths_copied += 1
    if projected_components:
        result["components"] = projected_components
    return result


def _read_dict_path(root: dict[str, Any], parts: list[str]) -> tuple[bool, Any]:
    current: Any = root
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _write_dict_path(root: dict[str, Any], parts: list[str], value: Any) -> None:
    current = root
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value


def _owned_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _owned_json(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_owned_json(item) for item in value]
    return deepcopy(value)
