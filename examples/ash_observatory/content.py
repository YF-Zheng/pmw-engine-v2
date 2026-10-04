"""Application and interaction adapter for Ash Observatory.

World outcomes live in PMW data. This module reads actor Observation data,
filters static UI affordances, builds Events, advances public action time, and
performs persistence. It never implements healing, damage, puzzles, or lifecycle.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pmw import Engine, Event, load_laws, load_observation_rules, load_world, save_world


BASE = Path(__file__).resolve().parent
PLAYER_ID = "actor:player"
ACTION_COSTS = {
    "move": 1.0, "search": 2.0, "talk": 1.0, "use": 1.0,
    "take": 1.0, "repair": 1.0, "disable": 1.0, "hack": 1.0,
    "enter_code": 1.0, "attack": 1.0, "extract": 1.0,
}


class CommandError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActionSpec:
    action_id: str
    namespace: str
    label: str
    description: str
    event_type: str
    time_cost: float
    requires_items: tuple[str, ...] = ()
    requires_any_items: tuple[str, ...] = ()
    requires_actor_tags: tuple[str, ...] = ()
    requires_target_tags: tuple[str, ...] = ()
    requires_observed_actor_paths: tuple[dict[str, Any], ...] = ()
    requires_observed_target_paths: tuple[dict[str, Any], ...] = ()
    forbid_observed_target_paths: tuple[dict[str, Any], ...] = ()
    hide_if_observed_target_paths: tuple[dict[str, Any], ...] = ()
    requires_observed_relation_types: tuple[dict[str, Any], ...] = ()
    input_fields: tuple[dict[str, Any], ...] = ()
    event_payload: dict[str, Any] | None = None
    self_action: bool = False
    allowed_contexts: tuple[str, ...] = ()
    target_state_reason: str | None = None
    hide_if_observed_entities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Affordance:
    spec: ActionSpec
    enabled: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class InteractionContext:
    target_id: str
    kind: str


def load_action_specs(path: Path = BASE / "actions.json") -> dict[str, ActionSpec]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "actions"} or raw["schema_version"] != "1.0" or not isinstance(raw["actions"], list):
        raise ValueError("invalid ActionSpec document")
    specs: dict[str, ActionSpec] = {}
    allowed = {
        "id", "namespace", "label", "description", "event_type", "time_cost",
        "requires_items", "requires_any_items", "requires_actor_tags", "requires_target_tags",
        "requires_observed_actor_paths", "requires_observed_target_paths",
        "forbid_observed_target_paths", "hide_if_observed_target_paths",
        "requires_observed_relation_types",
        "input_fields", "event_payload", "self_action", "target_state_reason",
        "allowed_contexts", "hide_if_observed_entities",
    }
    for index, item in enumerate(raw["actions"]):
        if not isinstance(item, dict) or set(item) - allowed:
            raise ValueError(f"invalid ActionSpec at actions[{index}]")
        required = ("id", "namespace", "label", "description", "event_type", "time_cost")
        if any(not isinstance(item.get(key), str) or not item[key] for key in required[:-1]):
            raise ValueError(f"ActionSpec {index} has missing string field")
        action_id = item["id"]
        if action_id in specs or "." not in action_id or action_id.split(".", 1)[0] != item["namespace"]:
            raise ValueError(f"invalid or duplicate ActionSpec id '{action_id}'")
        for key in ("requires_items", "requires_any_items", "requires_actor_tags",
                    "requires_target_tags", "allowed_contexts", "hide_if_observed_entities"):
            values = item.get(key, [])
            if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
                raise ValueError(f"ActionSpec {action_id}.{key} must be a string list")
        for key in ("requires_observed_actor_paths", "requires_observed_target_paths",
                    "forbid_observed_target_paths", "hide_if_observed_target_paths",
                    "requires_observed_relation_types", "input_fields"):
            if not isinstance(item.get(key, []), list):
                raise ValueError(f"ActionSpec {action_id}.{key} must be a list")
        if not isinstance(item["time_cost"], (int, float)) or item["time_cost"] < 0:
            raise ValueError(f"ActionSpec {action_id}.time_cost must be non-negative")
        if item.get("target_state_reason") is not None and (not isinstance(item["target_state_reason"], str) or not item["target_state_reason"]):
            raise ValueError(f"ActionSpec {action_id}.target_state_reason must be a non-empty string")
        if not set(item.get("allowed_contexts", ())) <= {"environment", "inventory", "self"}:
            raise ValueError(f"ActionSpec {action_id}.allowed_contexts contains an unknown context")
        specs[action_id] = ActionSpec(
            action_id=action_id,
            namespace=item["namespace"],
            label=item["label"],
            description=item["description"],
            event_type=item["event_type"],
            time_cost=float(item["time_cost"]),
            requires_items=tuple(item.get("requires_items", ())),
            requires_any_items=tuple(item.get("requires_any_items", ())),
            requires_actor_tags=tuple(item.get("requires_actor_tags", ())),
            requires_target_tags=tuple(item.get("requires_target_tags", ())),
            requires_observed_actor_paths=tuple(deepcopy(item.get("requires_observed_actor_paths", ()))),
            requires_observed_target_paths=tuple(deepcopy(item.get("requires_observed_target_paths", ()))),
            forbid_observed_target_paths=tuple(deepcopy(item.get("forbid_observed_target_paths", ()))),
            hide_if_observed_target_paths=tuple(deepcopy(item.get("hide_if_observed_target_paths", ()))),
            requires_observed_relation_types=tuple(deepcopy(item.get("requires_observed_relation_types", ()))),
            input_fields=tuple(deepcopy(item.get("input_fields", ()))),
            event_payload=deepcopy(item.get("event_payload", {})),
            self_action=item.get("self_action", False) is True,
            allowed_contexts=tuple(item.get("allowed_contexts", ())),
            target_state_reason=item.get("target_state_reason"),
            hide_if_observed_entities=tuple(item.get("hide_if_observed_entities", ())),
        )
    return specs


class ActionEventAdapter:
    """Turns one selected UI action into an Event without applying outcomes."""

    def build(self, spec: ActionSpec, *, actor_id: str, focused_target_id: str,
              inputs: dict[str, str], event_id: str, event_time: float) -> Event:
        expected = {field["name"] for field in spec.input_fields}
        if set(inputs) != expected:
            raise CommandError("action input fields do not match ActionSpec")
        for field in spec.input_fields:
            value = inputs[field["name"]]
            if field.get("type", "string") != "string" or not isinstance(value, str):
                raise CommandError(field.get("error", "invalid action input"))
            if field.get("pattern") and re.fullmatch(field["pattern"], value) is None:
                raise CommandError(field.get("error", "invalid action input"))
        payload = deepcopy(spec.event_payload or {})
        payload.update(inputs)
        return Event(
            event_id,
            spec.event_type,
            time=event_time,
            source=actor_id,
            target=actor_id if spec.self_action else focused_target_id,
            payload=payload,
        )


class GameSession:
    def __init__(self, world_path: Path | str | None = None) -> None:
        path = Path(world_path) if world_path else BASE / "world.json"
        world = load_world(path)
        self.engine = Engine(
            load_laws(BASE / "laws.json"),
            observation_rules=load_observation_rules(BASE / "observation_rules.json"),
        )
        self.runtime = self.engine.attach(world)
        self.view = self.runtime.observer(PLAYER_ID)
        self.actions = load_action_specs()
        self.action_adapter = ActionEventAdapter()
        # The adapter tracks action time; normal rendering never reads Runtime time.
        self._action_time = float(world.sim_time)
        self._serial = 0
        self._last_result = None

    def observation(self) -> dict[str, Any]:
        return self.view.observe().to_dict()

    def _next_event_id(self) -> str:
        self._serial += 1
        return f"action:{self._action_time:g}:{self._serial}"

    def _dispatch(self, event: Event, duration: float) -> tuple[dict[str, Any], dict[str, Any]]:
        old = self.observation()
        self._last_result = self.runtime.run_event(event)
        if duration:
            self.runtime.advance_by(duration)
            self._action_time += duration
        return old, self.observation()

    def act(self, event_type: str, *, target: str | None = None,
            payload: dict[str, Any] | None = None, cost: float | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        """Legacy/test helper. Default CLI does not expose direct contextual verbs."""
        event = Event(self._next_event_id(), event_type, time=self._action_time,
                      source=PLAYER_ID, target=target, payload=payload or {})
        return self._dispatch(event, ACTION_COSTS.get(event_type, 0.0) if cost is None else float(cost))

    def perform_action(self, action_id: str, focused_target_id: str,
                       inputs: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        observation = self.observation()
        target = entities_by_id(observation).get(focused_target_id)
        if target is None:
            raise CommandError("你已经看不到当前关注的对象。")
        selected = next((item for item in affordances(observation, target, self.actions)
                         if item.spec.action_id == action_id), None)
        if selected is None:
            raise CommandError("当前对象没有这个操作。")
        if not selected.enabled:
            raise CommandError(selected.reason or "这个操作当前不可用。")
        event = self.action_adapter.build(
            selected.spec,
            actor_id=PLAYER_ID,
            focused_target_id=focused_target_id,
            inputs=inputs or {},
            event_id=self._next_event_id(),
            event_time=self._action_time,
        )
        return self._dispatch(event, selected.spec.time_cost)

    def wait(self, seconds: float) -> tuple[dict[str, Any], dict[str, Any]]:
        if seconds <= 0 or seconds > 3600:
            raise CommandError("wait seconds must be in (0, 3600]")
        return self.act("wait", cost=seconds)

    def save(self, filename: str) -> Path:
        path = Path(filename).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        save_world(path, self.runtime.state)
        return path

    @classmethod
    def load(cls, filename: str) -> "GameSession":
        path = Path(filename).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return cls(path)

    def debug_truth(self) -> dict[str, Any]:
        return self.runtime.state.to_dict()

    def debug_queue(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in sorted(self.runtime.state.scheduled_events, key=lambda item: (item.time, item.id))]

    def debug_trace(self) -> dict[str, Any] | None:
        return self._last_result.trace.to_dict() if self._last_result and self._last_result.trace else None

    def debug_stats(self) -> dict[str, Any]:
        return asdict(self.runtime.stats)


def entities_by_id(observation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in observation["entities"]}


def relations_of_type(observation: dict[str, Any], relation_type: str) -> list[dict[str, Any]]:
    return [item for item in observation["relations"] if item.get("type") == relation_type]


def player(observation: dict[str, Any]) -> dict[str, Any]:
    return entities_by_id(observation)[PLAYER_ID]


def inventory_ids(observation: dict[str, Any]) -> set[str]:
    return {relation["source"] for relation in relations_of_type(observation, "owned_by")
            if relation.get("target") == PLAYER_ID and "source" in relation}


def current_room_id(observation: dict[str, Any]) -> str:
    return player(observation)["components"]["position"]["room"]


def environment_objects(observation: dict[str, Any]) -> list[dict[str, Any]]:
    objects = entities_by_id(observation)
    owned = inventory_ids(observation)
    room_id = current_room_id(observation)
    return [item for item in observation["entities"]
            if item["id"] not in owned | {PLAYER_ID, room_id}
            and item.get("archetype") not in {"room", "fact"}]


def interaction_context(observation: dict[str, Any], target_id: str) -> InteractionContext | None:
    if target_id not in entities_by_id(observation):
        return None
    if target_id == PLAYER_ID:
        return InteractionContext(target_id, "self")
    if target_id in inventory_ids(observation):
        return InteractionContext(target_id, "inventory")
    if target_id == current_room_id(observation):
        return InteractionContext(target_id, "environment")
    if target_id in {item["id"] for item in environment_objects(observation)}:
        return InteractionContext(target_id, "environment")
    return InteractionContext(target_id, "known_remote")


def resolve_entity(observation: dict[str, Any], text: str, *, archetypes: set[str] | None = None,
                   candidates: set[str] | None = None) -> dict[str, Any]:
    query = text.strip().casefold()
    if query in {"self", "me", "我", "自己"}:
        query = PLAYER_ID
    matches = []
    for item in observation["entities"]:
        if archetypes and item.get("archetype") not in archetypes:
            continue
        if candidates is not None and item["id"] not in candidates:
            continue
        id_parts = item["id"].split(":")
        aliases = {item["id"].casefold(), id_parts[-1].casefold(), " ".join(reversed(id_parts)).casefold()}
        if item.get("name"):
            aliases.add(item["name"].casefold())
        if query in aliases:
            matches.append(item)
    if not matches:
        raise CommandError(f"你看不到这个对象：{text}")
    if len(matches) > 1:
        raise CommandError("目标不唯一，请输入完整 ID：" + ", ".join(item["id"] for item in matches))
    return matches[0]


def resolve_watch_target(observation: dict[str, Any], text: str) -> InteractionContext:
    query = text.strip().casefold()
    if query == "here":
        return InteractionContext(current_room_id(observation), "environment")
    if query in {"self", "me", "我", "自己"}:
        return InteractionContext(PLAYER_ID, "self")

    environment = environment_objects(observation)
    if query.isdigit():
        index = int(query) - 1
        if index < 0 or index >= len(environment):
            raise CommandError("当前环境中没有这个对象编号。")
        return InteractionContext(environment[index]["id"], "environment")

    owned = inventory_ids(observation)
    candidates = environment + [entities_by_id(observation)[item_id]
                                for item_id in sorted(owned)
                                if item_id in entities_by_id(observation)]
    exact = [item for item in candidates
             if query in {item["id"].casefold(), str(item.get("name", "")).casefold()}]
    if not exact:
        exact = [item for item in candidates if query == item["id"].split(":")[-1].casefold()]
    if not exact:
        exact = [item for item in candidates if query == str(item.get("archetype", "")).casefold()]
    if not exact:
        raise CommandError(f"你看不到这个可交互对象：{text}")
    if len(exact) > 1:
        raise CommandError("目标不唯一，请使用 look 中的对象编号。")
    context = interaction_context(observation, exact[0]["id"])
    if context is None or context.kind == "known_remote":
        raise CommandError(f"这个对象当前不在可交互范围内：{text}")
    return context


def _nested(item: dict[str, Any], *path: str, default=None):
    value: Any = item.get("components", {})
    for segment in path:
        if not isinstance(value, dict) or segment not in value:
            return default
        value = value[segment]
    return value


def _path_value(item: dict[str, Any], path: str):
    return _nested(item, *path.split("."), default=None)


def _comparison(actual: Any, operation: str, expected: Any) -> bool:
    if operation == "eq": return actual == expected
    if operation == "neq": return actual != expected
    if operation == "gt": return actual is not None and actual > expected
    if operation == "gte": return actual is not None and actual >= expected
    if operation == "lt": return actual is not None and actual < expected
    if operation == "lte": return actual is not None and actual <= expected
    raise ValueError(f"unknown ActionSpec comparator '{operation}'")


def affordances(observation: dict[str, Any], target: dict[str, Any],
                specs: dict[str, ActionSpec]) -> list[Affordance]:
    action_ids = _nested(target, "interaction", "actions", default=[])
    if not isinstance(action_ids, list):
        return []
    owned = inventory_ids(observation)
    actor = player(observation)
    context = interaction_context(observation, target["id"])
    if context is None or context.kind == "known_remote":
        return []
    result = []
    for action_id in action_ids:
        spec = specs.get(action_id)
        if spec is None:
            raise ValueError(f"visible object references unknown ActionSpec '{action_id}'")
        if spec.allowed_contexts and context.kind not in spec.allowed_contexts:
            continue
        if set(spec.hide_if_observed_entities) & set(entities_by_id(observation)):
            continue
        if any(_comparison(_path_value(target, requirement["path"]),
                           requirement.get("op", "eq"), requirement.get("value"))
               for requirement in spec.hide_if_observed_target_paths):
            continue
        # Missing actor capability is hidden rather than explained by the target menu.
        if not set(spec.requires_items) <= owned:
            continue
        if spec.requires_any_items and not (set(spec.requires_any_items) & owned):
            continue
        if not set(spec.requires_actor_tags) <= set(actor.get("tags", [])):
            continue
        if any(not _comparison(_path_value(actor, requirement["path"]), requirement.get("op", "eq"), requirement.get("value"))
               for requirement in spec.requires_observed_actor_paths):
            continue

        reason = None
        if not set(spec.requires_target_tags) <= set(target.get("tags", [])):
            reason = spec.target_state_reason or "这个对象目前不满足操作条件。"
        for requirement in spec.requires_observed_target_paths:
            if not _comparison(_path_value(target, requirement["path"]), requirement.get("op", "eq"), requirement.get("value")):
                reason = requirement.get("reason", "目标当前状态不允许这个操作。")
                break
        if reason is None:
            for requirement in spec.forbid_observed_target_paths:
                if _comparison(_path_value(target, requirement["path"]), requirement.get("op", "eq"), requirement.get("value")):
                    reason = requirement.get("reason", "目标当前状态不允许这个操作。")
                    break
        if reason is None:
            visible_types = {relation.get("type") for relation in observation["relations"]}
            for requirement in spec.requires_observed_relation_types:
                if requirement["type"] not in visible_types:
                    reason = requirement.get("reason", "当前状态不允许这个操作。")
                    break
        result.append(Affordance(spec, reason is None, reason))
    labels = [item.spec.label.casefold() for item in result]
    if len(labels) != len(set(labels)):
        raise ValueError(f"duplicate action label in menu for '{target['id']}'")
    return result


def resolve_context_action(user_input: str,
                           current_affordances: list[Affordance]) -> Affordance:
    selector = user_input.strip()
    if selector.casefold().startswith("do "):
        selector = selector[3:].strip()
    if not selector:
        raise CommandError("请输入操作编号或名称。")
    enabled = [item for item in current_affordances if item.enabled]
    if selector.isdigit():
        index = int(selector) - 1
        if index < 0 or index >= len(enabled):
            raise CommandError("当前菜单中没有这个可用编号。")
        return enabled[index]
    normalized = selector.casefold()
    selected = [item for item in current_affordances
                if normalized in {item.spec.label.casefold(), item.spec.action_id.casefold()}]
    if not selected:
        raise CommandError("当前关注对象没有这个操作。")
    if len(selected) > 1:
        raise ValueError("current contextual menu contains duplicate action labels")
    return selected[0]


def _description(item: dict[str, Any]) -> str | None:
    return _nested(item, "public", "description") or _nested(item, "room", "description")


def _state_lines(item: dict[str, Any]) -> list[str]:
    states = []
    condition = _nested(item, "public", "condition")
    if condition:
        states.append("状态：" + {"injured": "伤势严重", "stable": "伤势稳定"}.get(condition, str(condition)))
    repair = _nested(item, "repair", "state")
    if repair:
        states.append("维修状态：" + {"broken": "损坏", "channeling": "维修进行中", "online": "运行正常"}.get(repair, str(repair)))
    online = _nested(item, "power", "online")
    if online is not None:
        states.append("电力：" + ("在线" if online else "未通电"))
    locked = _nested(item, "security", "locked")
    if locked is not None:
        states.append("终端：" + ("锁定" if locked else "已解锁"))
    if _nested(item, "security", "channeling") is True:
        states.append("破解正在进行。")
    door_locked = _nested(item, "door", "locked")
    if door_locked is not None:
        states.append("门锁：" + ("锁定" if door_locked else "已打开"))
    armed = _nested(item, "trap", "armed")
    if armed is not None:
        states.append("触发器：" + ("已武装" if armed else "已解除"))
    hp = _nested(item, "health", "hp")
    if hp is not None and item.get("archetype") == "enemy":
        states.append(f"状态：{'活动' if hp > 0 else '失去行动能力'}（HP {hp}）")
    return states


def render_focus(observation: dict[str, Any], target: dict[str, Any],
                 specs: dict[str, ActionSpec]) -> str:
    lines = ["─" * 56, f"当前关注：{target.get('name', target['id'])}  [{target['id']}]", ""]
    description = _description(target)
    if description:
        lines.extend(description.splitlines())
    context = interaction_context(observation, target["id"])
    if context and context.kind == "inventory":
        lines.append("当前由你持有。")
    role = _nested(target, "public", "role")
    if role:
        lines.append("身份：" + {"station engineer": "站点工程师"}.get(role, str(role)))
    lines.extend(_state_lines(target))
    dialogue = _nested(target, "public", "dialogue")
    if dialogue:
        lines.append(dialogue)
    items = affordances(observation, target, specs)
    lines.extend(["", "可用操作："])
    enabled_number = 0
    if not items:
        lines.append("  当前没有可执行操作。")
    for item in items:
        if item.enabled:
            enabled_number += 1
            lines.append(f"  {enabled_number}. {item.spec.label}")
        else:
            lines.append(f"  — {item.spec.label}")
            lines.append(f"      当前不可用：{item.reason}")
    lines.append("─" * 56)
    return "\n".join(lines)


def enabled_affordances(observation: dict[str, Any], target: dict[str, Any],
                        specs: dict[str, ActionSpec]) -> list[Affordance]:
    return [item for item in affordances(observation, target, specs) if item.enabled]


def render(observation: dict[str, Any], *, section: str = "all", short_inventory: bool = False) -> str:
    objects = entities_by_id(observation)
    me = player(observation)
    room_id = current_room_id(observation)
    room = objects.get(room_id, {"id": room_id, "name": room_id})
    owned = inventory_ids(observation)
    lines = ["─" * 56]

    if section in {"all", "status"}:
        hp = _nested(me, "health", "hp", default="?")
        max_hp = _nested(me, "health", "max_hp", default="?")
        lines.extend([f"位置：{room.get('name', room_id)}  [{room_id}]", "", f"你：{me.get('name', PLAYER_ID)}  HP {hp}/{max_hp}"])
        status_names = {"bleeding": "流血", "channeling": "耗时操作进行中"}
        statuses = [status_names[relation["type"]] for relation in observation["relations"] if relation.get("type") in status_names]
        if "dead" in me.get("tags", []): statuses.append("死亡")
        if statuses:
            lines.extend(["状态：", *[f"  {status}" for status in sorted(set(statuses))]])

    if section == "all":
        description = _nested(room, "room", "description")
        if description:
            lines.extend(["", description])
        exits = [item for item in observation["entities"] if item.get("archetype") == "room" and item["id"] != room_id]
        lines.extend(["", "可前往："])
        lines.extend([f"  {item.get('name', item['id'])}  [{item['id']}]" for item in exits] or ["  （无）"])

        visible = environment_objects(observation)
        lines.extend(["", "你看到："])
        if not visible:
            lines.append("  （无）")
        for index, item in enumerate(visible, 1):
            lines.append(f"  [{index}] {item.get('name', item['id'])}  [{item['id']}]")
            description = _description(item)
            if description:
                lines.extend(f"    {part}" for part in description.splitlines())
            state = _state_lines(item)
            lines.extend(f"    {part}" for part in state[:1])
        if visible:
            lines.append("\n提示：使用 `watch <对象>` 查看可用交互。")

    if section in {"all", "inventory"}:
        lines.extend(["", "你的物品："])
        inventory = [objects[item_id] for item_id in sorted(owned) if item_id in objects]
        if not inventory:
            lines.append("  （无）")
        for item in inventory:
            lines.append(f"  {item.get('name', item['id'])}  [{item['id']}]")
            if not short_inventory and _description(item):
                lines.extend(f"    {part}" for part in _description(item).splitlines())

    if section == "all":
        facts = [item for item in observation["entities"] if item.get("archetype") == "fact"]
        lines.extend(["", "你知道："])
        lines.extend([f"  {_nested(item, 'fact', 'text', default=item.get('name', item['id']))}" for item in facts] or ["  （无）"])

    lines.append("─" * 56)
    return "\n".join(lines)


def render_diff(old: dict[str, Any], new: dict[str, Any]) -> str:
    old_objects, new_objects = entities_by_id(old), entities_by_id(new)
    messages = []
    old_room, new_room = current_room_id(old), current_room_id(new)
    if old_room != new_room:
        room = new_objects.get(new_room, {"id": new_room})
        messages.append(f"你来到{room.get('name', new_room)}。")
    old_hp = _nested(old_objects[PLAYER_ID], "health", "hp")
    new_hp = _nested(new_objects[PLAYER_ID], "health", "hp")
    if old_hp != new_hp:
        messages.append(f"HP：{old_hp} → {new_hp}")
    old_owned, new_owned = inventory_ids(old), inventory_ids(new)
    for object_id in sorted(new_owned - old_owned):
        item = new_objects.get(object_id, {"id": object_id})
        messages.append(f"你取得了{item.get('name', object_id)}。")
    for object_id in sorted(old_owned - new_owned):
        item = old_objects.get(object_id, {"id": object_id})
        messages.append(f"你不再持有{item.get('name', object_id)}。")
    for object_id in sorted(set(old_objects) & set(new_objects)):
        before, after = old_objects[object_id], new_objects[object_id]
        old_condition = _nested(before, "public", "condition")
        new_condition = _nested(after, "public", "condition")
        if old_condition != new_condition and new_condition is not None:
            translated = {"injured": "伤势严重", "stable": "稳定"}.get(new_condition, str(new_condition))
            messages.append(f"{after.get('name', object_id)} 的状态发生了变化：{translated}。")
        old_dialogue = _nested(before, "public", "dialogue")
        new_dialogue = _nested(after, "public", "dialogue")
        if old_dialogue != new_dialogue and new_dialogue:
            messages.append(f"{after.get('name', object_id)}：{new_dialogue}")
        old_locked = _nested(before, "door", "locked")
        new_locked = _nested(after, "door", "locked")
        if old_locked is True and new_locked is False:
            messages.append(f"{after.get('name', object_id)}已解锁。")
        old_armed = _nested(before, "trap", "armed")
        new_armed = _nested(after, "trap", "armed")
        if old_armed is True and new_armed is False:
            messages.append(f"{after.get('name', object_id)}已被解除。")
        old_online = _nested(before, "power", "online")
        new_online = _nested(after, "power", "online")
        if old_online is False and new_online is True:
            messages.append(f"{after.get('name', object_id)}恢复了供电。")
    for object_id in sorted(set(new_objects) - set(old_objects)):
        item = new_objects[object_id]
        if item.get("archetype") == "fact":
            messages.append("你获知了一条新信息：\n“" + str(_nested(item, "fact", "text", default=item.get("name", object_id))) + "”")
        elif item.get("archetype") != "room":
            messages.append(f"现在可见：{item.get('name', object_id)} [{object_id}]")
    old_relations = {(item.get("type"), item.get("id")) for item in old["relations"]}
    new_relations = {(item.get("type"), item.get("id")) for item in new["relations"]}
    if any(kind == "bleeding" for kind, _ in new_relations - old_relations): messages.append("你开始流血。")
    if any(kind == "bleeding" for kind, _ in old_relations - new_relations): messages.append("流血已经停止。")
    if any(kind == "channeling" for kind, _ in new_relations - old_relations): messages.append("你开始执行一个耗时操作。")
    if any(kind == "channeling" for kind, _ in old_relations - new_relations): messages.append("耗时操作已经结束或被中断。")
    if _nested(new_objects[PLAYER_ID], "game", "victory") and not _nested(old_objects[PLAYER_ID], "game", "victory"):
        messages.append("撤离条件已经满足。")
    if not messages and old != new:
        messages.append("你注意到周围发生了变化。")
    return "\n".join(messages or ["没有可见变化。"])


def is_victory(observation: dict[str, Any]) -> bool:
    return _nested(player(observation), "game", "victory", default=False) is True


def is_dead(observation: dict[str, Any]) -> bool:
    return "dead" in player(observation).get("tags", [])
