#!/usr/bin/env python3
"""Contextual actor-safe harness for Ash Observatory: Core Zero."""

from __future__ import annotations

import argparse
import json
import shlex
from collections.abc import Callable

from content import (CommandError, GameSession, InteractionContext, affordances,
                     current_room_id, entities_by_id, interaction_context,
                     is_dead, is_victory, render, render_diff, render_focus,
                     resolve_context_action, resolve_entity,
                     resolve_watch_target)


HELP = """观察
  look
      查看当前环境、可前往地点和可见对象。

  watch <对象>
      仔细观察一个可见对象，并显示当前能对它执行的操作。

  status
      查看自己的生命与公开状态。

  inventory [short]
      查看已持有物品及用途；short 只显示名称。

行动
  move <地点>
      前往当前 Observation 中可达的区域。

  wait <秒>
      原地等待。世界中的定时事件仍会继续发生。

交互
  使用 watch <对象> 关注一个当前可见对象；look 中的对象编号可直接使用。
  对象会显示编号操作，例如 `1. 拾取`。你可以输入：
      1
      拾取
      do 1
      do 拾取
  `do <ActionSpec ID>` 是高级输入，普通游玩无需知道内部名称。

系统
  save <文件>     保存正式 WorldState。
  load <文件>     载入存档并重建运行时。
  rawobs          查看 actor-safe Observation JSON。
  help [命令]     查看说明。
  quit            退出游戏。
"""


HELP_DETAILS = {
    "look": "look\n\n查看当前房间、公开描述、可前往地点和当前可见对象。look 不推进时间。",
    "watch": "watch <对象编号或名称>\n\n将交互焦点放到 look 列出的当前环境对象；watch here 关注当前房间，watch self / me / 我 关注自己。watch 本身不会推进时间。",
    "status": "status\n\n查看自己的生命与由 Observation 公开的持续状态。不会显示隐藏计时器。",
    "inventory": "inventory [short]\n\n查看正式 owned_by Relation 授权的物品与公开用途。short 仅显示名称。",
    "move": "move <地点>\n\n前往 look 中列出的当前可达区域。移动耗时 1 秒，并可能中断正在进行的耗时操作。",
    "wait": "wait <秒>\n\n原地等待指定秒数。Scheduler 中的世界事件会正常发生，但其队列不会向玩家公开。",
    "save": "save <文件>\n\n使用 PMW save_world 保存 WorldState，不推进时间。",
    "load": "load <文件>\n\n载入 WorldState、重新 attach Engine，并清除本地交互焦点。",
}


def require(parts: list[str], count: int, usage: str) -> None:
    if len(parts) != count:
        raise CommandError("usage: " + usage)


def _help(session: GameSession, topic: str | None) -> None:
    if topic is None:
        print(HELP)
        return
    key = topic.casefold()
    if key in HELP_DETAILS:
        print(HELP_DETAILS[key])
        return
    spec = session.actions.get(topic)
    if spec:
        lines = [spec.label, "", spec.description, f"行动耗时：{spec.time_cost:g} 秒"]
        if spec.input_fields:
            lines.append("执行时会询问：" + "、".join(field["prompt"].rstrip("：: ") for field in spec.input_fields))
        print("\n".join(lines))
        return
    raise CommandError(f"没有这个帮助主题：{topic}")


def _as_context(observation: dict,
                focus: InteractionContext | str | None) -> InteractionContext | None:
    if isinstance(focus, InteractionContext) or focus is None:
        return focus
    return interaction_context(observation, focus)


def _check_focus(observation: dict,
                 focus: InteractionContext | str | None) -> InteractionContext | None:
    previous = _as_context(observation, focus)
    if previous is None:
        return None
    current = interaction_context(observation, previous.target_id)
    if current is None or current.kind != previous.kind or current.kind == "known_remote":
        print("当前关注已结束。")
        return None
    return current


def _perform_focused(session: GameSession, focus: InteractionContext | str | None,
                     selector: str, input_fn: Callable[[str], str]) -> tuple[dict, dict]:
    observation = session.observation()
    context = _as_context(observation, focus)
    if context is None:
        raise CommandError("请先使用 watch <对象> 选择交互目标。")
    target = entities_by_id(observation).get(context.target_id)
    if target is None:
        raise CommandError("你已经看不到当前关注的对象。")
    selected = resolve_context_action(selector, affordances(observation, target, session.actions))
    if not selected.enabled:
        raise CommandError(selected.reason or "这个操作当前不可用。")
    inputs = {field["name"]: input_fn(field["prompt"] + " ") for field in selected.spec.input_fields}
    return session.perform_action(selected.spec.action_id, context.target_id, inputs)


def execute(session: GameSession, line: str, *, debug: bool,
            focused_target_id: InteractionContext | str | None = None,
            input_fn: Callable[[str], str] = input) -> tuple[GameSession, bool, InteractionContext | None]:
    try:
        parts = shlex.split(line)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    observation = session.observation()
    focus = _as_context(observation, focused_target_id)
    if not parts:
        return session, False, focus
    command = parts[0].casefold()
    aliases = {"观察": "look", "状态": "status", "物品": "inventory", "移动": "move",
               "关注": "watch", "等待": "wait", "帮助": "help", "退出": "quit"}
    command = aliases.get(command, command)

    if command == "help":
        if len(parts) > 2:
            raise CommandError("usage: help [command-or-action-id]")
        _help(session, parts[1] if len(parts) == 2 else None)
        if debug and len(parts) == 1:
            print("Debug: :truth | :queue | :trace | :stats")
        return session, False, focus
    if command == "quit":
        return session, True, focus
    if command == "look":
        require(parts, 1, "look"); print(render(observation)); return session, False, focus
    if command == "status":
        require(parts, 1, "status"); print(render(observation, section="status")); return session, False, focus
    if command == "inventory":
        if len(parts) > 2 or len(parts) == 2 and parts[1].casefold() != "short":
            raise CommandError("usage: inventory [short]")
        print(render(observation, section="inventory", short_inventory=len(parts) == 2))
        return session, False, focus
    if command == "rawobs":
        require(parts, 1, "rawobs"); print(json.dumps(observation, ensure_ascii=False, indent=2)); return session, False, focus
    if command == "watch":
        if len(parts) < 2:
            raise CommandError("usage: watch <visible-object>")
        focus = resolve_watch_target(observation, " ".join(parts[1:]))
        print(render_focus(observation, entities_by_id(observation)[focus.target_id], session.actions))
        return session, False, focus
    if command == "save":
        require(parts, 2, "save <filename>"); print(f"已保存：{session.save(parts[1])}")
        return session, False, focus
    if command == "load":
        require(parts, 2, "load <filename>")
        replacement = GameSession.load(parts[1])
        print(f"已载入：{parts[1]}"); print(render(replacement.observation()))
        return replacement, False, None

    if command.startswith(":"):
        if not debug:
            raise CommandError("privileged debug commands are unavailable in normal mode")
        debug_values = {":truth": session.debug_truth, ":queue": session.debug_queue,
                        ":trace": session.debug_trace, ":stats": session.debug_stats}
        if command not in debug_values:
            raise CommandError("unknown debug command")
        print("[PRIVILEGED DEBUG]")
        print(json.dumps(debug_values[command](), ensure_ascii=False, indent=2))
        return session, False, focus

    old = observation
    if command == "move":
        require(parts, 2, "move <visible-room>")
        candidates = {item["id"] for item in observation["entities"]
                      if item.get("archetype") == "room" and item["id"] != current_room_id(observation)}
        target = resolve_entity(observation, parts[1], archetypes={"room"}, candidates=candidates)
        old, new = session.act("move", target=target["id"])
    elif command == "wait":
        require(parts, 2, "wait <seconds>")
        try:
            seconds = float(parts[1])
        except ValueError as exc:
            raise CommandError("wait seconds must be numeric") from exc
        old, new = session.wait(seconds)
    elif command == "do":
        if len(parts) < 2:
            raise CommandError("usage: do <number-action-label-or-action-id>")
        old, new = _perform_focused(session, focus, line.strip(), input_fn)
    elif command.isdigit():
        require(parts, 1, "<action-number>")
        old, new = _perform_focused(session, focus, command, input_fn)
    elif focus is not None:
        old, new = _perform_focused(session, focus, line.strip(), input_fn)
    else:
        raise CommandError("unknown global command; use watch <对象> and select a contextual action")

    print(render_diff(old, new))
    if command == "move":
        if focus is not None:
            print("当前关注已结束。")
        focus = None
    else:
        focus = _check_focus(new, focus)
    print(render(new))
    if focus:
        print(render_focus(new, entities_by_id(new)[focus.target_id], session.actions))
    if is_victory(new):
        print("你带着零号核心穿过气闸。撤离成功。")
        return session, True, focus
    if is_dead(new):
        print("调查员倒下了。世界仍在继续，但这次行动已经结束。")
        return session, True, focus
    return session, False, focus


def main() -> None:
    parser = argparse.ArgumentParser(description="Ash Observatory: Core Zero")
    parser.add_argument("--debug", action="store_true", help="enable explicitly privileged inspection commands")
    parser.add_argument("--load", metavar="WORLD", help="load a saved WorldState")
    args = parser.parse_args()
    session = GameSession.load(args.load) if args.load else GameSession()

    print("《灰烬观测站：零号核心》")
    print("你进入废弃研究站，任务是取得零号核心并返回气闸撤离。")
    print("输入 help 了解观察、移动和 contextual interaction。")
    if args.debug:
        print("[PRIVILEGED DEBUG] 调试命令已启用。")
    print(render(session.observation()))

    focused_target_id = None
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            break
        try:
            session, finished, focused_target_id = execute(
                session, line, debug=args.debug, focused_target_id=focused_target_id,
            )
            if finished:
                break
        except CommandError as exc:
            print(f"无法执行：{exc}")
        except Exception as exc:
            print(f"世界拒绝了这个动作：{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
