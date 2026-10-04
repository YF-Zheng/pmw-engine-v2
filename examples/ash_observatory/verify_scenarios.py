#!/usr/bin/env python3
"""World-content acceptance scenarios for Ash Observatory: Core Zero."""

from __future__ import annotations

import json
import io
import tempfile
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

from content import (BASE, CommandError, GameSession, PLAYER_ID, affordances,
                     entities_by_id, interaction_context, inventory_ids,
                     is_victory, load_world, render, render_diff,
                     resolve_context_action, save_world)
from play import HELP, _check_focus, _help, execute


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def object_by_id(observation, object_id):
    return next((item for item in observation["entities"] if item["id"] == object_id), None)


def relations(observation, relation_type):
    return [item for item in observation["relations"] if item.get("type") == relation_type]


def act(session, event_type, target=None, payload=None, cost=None):
    return session.act(event_type, target=target, payload=payload, cost=cost)[1]


def action_map(session, target_id):
    observation = session.observation()
    target = entities_by_id(observation)[target_id]
    return {item.spec.action_id: item for item in affordances(observation, target, session.actions)}


def session_without(*item_ids):
    world = load_world(BASE / "world.json")
    for relation_id, relation in list(world.relations.items()):
        if relation.type == "owned_by" and relation.source in item_ids:
            del world.relations[relation_id]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.json"
        save_world(path, world)
        return GameSession(path)


def move(session, destination):
    return act(session, "move", destination)


def cli(session, line, focus=None, inputs=()):
    responses = iter(inputs)
    output = io.StringIO()
    with redirect_stdout(output):
        session, finished, focus = execute(
            session, line, debug=False, focused_target_id=focus,
            input_fn=lambda _prompt: next(responses),
        )
    return session, focus, finished, output.getvalue()


def cli_action(session, target, action, focus=None, inputs=()):
    session, focus, finished, watched = cli(session, f"watch {target}", focus)
    check(not finished, f"watch {target} unexpectedly ended the game")
    session, focus, finished, acted = cli(session, action, focus, inputs)
    return session, focus, finished, watched + acted


def cli_move(session, destination, focus=None):
    session, focus, finished, output = cli(session, f"move {destination}", focus)
    check(not finished, f"move {destination} unexpectedly ended the game")
    return session, focus, output


def prepare_generator(session):
    move(session, "room:hall"); move(session, "room:generator")
    act(session, "repair", "machine:generator")
    session.wait(2)
    generator = object_by_id(session.observation(), "machine:generator")
    check(generator["components"]["power"]["online"] is True, "generator did not finish repair")


def reach_archive_with_power(session):
    prepare_generator(session)
    move(session, "room:hall"); move(session, "room:archive")


def take_core_and_extract(session):
    move(session, "room:vault")
    act(session, "take", "artifact:core_zero")
    move(session, "room:vault_ante"); move(session, "room:hall"); move(session, "room:airlock")
    act(session, "extract")
    check(is_victory(session.observation()), "extract did not produce projected victory")


def social_route():
    session = GameSession()
    session, focus, _ = cli_move(session, "hall")
    session, focus, _ = cli_move(session, "infirmary", focus)
    before = json.dumps(session.observation(), ensure_ascii=False, sort_keys=True)
    check("secret" not in before and "3142" not in before and "fact:vault_code" not in before, "Mira secret leaked before knowledge grant")
    session, focus, _, _ = cli_action(session, "medkit", "拾取", focus)
    check(focus is None, "medkit pickup did not clear environment focus")
    session, focus, _, _ = cli_action(session, "Mira", "稳定伤势", focus)
    after = session.observation()
    code_fact = object_by_id(after, "fact:vault_code")
    check(code_fact and "3142" in code_fact["components"]["fact"]["text"], "code Fact not visible after heal")
    check("secret" not in json.dumps(after, ensure_ascii=False, sort_keys=True), "knowledge grant leaked secret component")
    check(any(event["type"] == "mira_followup" for event in session.debug_queue()), "future emitted event was not persisted")
    session, focus, _ = cli_move(session, "hall", focus)
    session, focus, _ = cli_move(session, "vault_ante", focus)
    session, focus, _, _ = cli_action(session, "零号金库门", "输入密码", focus, ("3142",))
    session, focus, _ = cli_move(session, "vault", focus)
    session, focus, _, _ = cli_action(session, "零号核心", "取得核心", focus)
    session, focus, _ = cli_move(session, "vault_ante", focus)
    session, focus, _ = cli_move(session, "hall", focus)
    session, focus, _ = cli_move(session, "airlock", focus)
    session, focus, finished, _ = cli_action(session, "here", "携带核心撤离", focus)
    check(finished and is_victory(session.observation()), "social contextual route did not win")


def technical_route():
    session = GameSession(); session, focus, _ = cli_move(session, "hall")
    session, focus, _ = cli_move(session, "generator", focus)
    session, focus, _, _ = cli_action(session, "generator", "开始维修", focus)
    session, focus, _, _ = cli(session, "wait 2", focus)
    session, focus, _ = cli_move(session, "hall", focus)
    session, focus, _ = cli_move(session, "archive", focus)
    hidden = json.dumps(session.observation(), ensure_ascii=False, sort_keys=True)
    check("trap:archive_wire" not in hidden, "hidden trap visible before discovery")
    session, focus, _, _ = cli_action(session, "here", "仔细搜索", focus)
    discovered = session.observation()
    check(object_by_id(discovered, "trap:archive_wire") is not None, "search did not grant discovered trap")
    session, focus, _, _ = cli_action(session, "trap", "拆除触发器", focus)
    session, focus, _, _ = cli_action(session, "terminal", "破解终端", focus)
    started = session.observation()
    check(relations(started, "channeling"), "hack channel not projected")
    session, focus, _, _ = cli(session, "wait 4", focus)
    terminal = object_by_id(session.observation(), "terminal:archive")
    check(terminal["components"]["security"]["locked"] is False, "hack completion did not unlock terminal")
    session, focus, _ = cli_move(session, "hall", focus)
    session, focus, _ = cli_move(session, "vault_ante", focus)
    session, focus, _ = cli_move(session, "vault", focus)
    session, focus, _, _ = cli_action(session, "零号核心", "取得核心", focus)
    session, focus, _ = cli_move(session, "vault_ante", focus)
    session, focus, _ = cli_move(session, "hall", focus)
    session, focus, _ = cli_move(session, "airlock", focus)
    session, focus, finished, _ = cli_action(session, "here", "携带核心撤离", focus)
    check(finished and is_victory(session.observation()), "technical contextual route did not win")


def force_route():
    session = GameSession(); session, focus, _ = cli_move(session, "hall")
    session, focus, _ = cli_move(session, "vault_ante", focus)
    session, focus, _, _ = cli_action(session, "零号金库门", "安装爆破药", focus)
    check(any(event["id"] == "detonate:vault" for event in session.debug_queue()), "breach did not schedule detonation")
    session, focus, _, _ = cli(session, "wait 1", focus)
    door = object_by_id(session.observation(), "door:vault")
    check(door["components"]["door"] == {"destroyed": True, "locked": False}, "detonation did not destroy and unlock door")
    check(any(event["id"] == "spawn:security_drone" for event in session.debug_queue()), "breach did not schedule drone")
    session, focus, _ = cli_move(session, "vault", focus)
    session, focus, _, _ = cli_action(session, "零号核心", "取得核心", focus)
    session, focus, _ = cli_move(session, "vault_ante", focus)
    seen = session.observation()
    check(object_by_id(seen, "enemy:security_drone") is not None, "future event did not create drone")
    for _ in range(3):
        session, focus, _, _ = cli_action(session, "安保无人机", "攻击", focus)
    session, focus, _ = cli_move(session, "hall", focus)
    session, focus, _ = cli_move(session, "airlock", focus)
    session, focus, finished, _ = cli_action(session, "here", "携带核心撤离", focus)
    check(finished and is_victory(session.observation()), "force contextual route did not win")


def trap_bleeding_bandage():
    session = GameSession(); reach_archive_with_power(session)
    triggered = act(session, "hack", "terminal:archive")
    check(relations(triggered, "bleeding"), "armed trap did not create visible bleeding")
    check(object_by_id(triggered, PLAYER_ID)["components"]["health"]["hp"] == 80, "trap damage was not 20")
    treated = act(session, "use", PLAYER_ID, {"item": "item:bandage"})
    check(not relations(treated, "bleeding"), "bandage did not remove bleeding")
    pending_ids = {event["id"] for event in session.debug_queue()}
    check("pulse:bleeding:player" not in pending_ids and "expire:bleeding:player" not in pending_ids, "bandage did not cancel both handles")
    hp = object_by_id(treated, PLAYER_ID)["components"]["health"]["hp"]
    session.wait(10)
    check(object_by_id(session.observation(), PLAYER_ID)["components"]["health"]["hp"] == hp, "cancelled bleeding pulse still damaged player")


def hack_interrupt():
    session = GameSession(); reach_archive_with_power(session)
    act(session, "search", cost=2); act(session, "disable", "trap:archive_wire")
    act(session, "hack", "terminal:archive")
    check(any(event["id"] == "complete:hack:archive" for event in session.debug_queue()), "hack completion missing")
    move(session, "room:hall")
    check(not any(event["id"] == "complete:hack:archive" for event in session.debug_queue()), "movement did not cancel hack handle")
    session.wait(10); move(session, "room:archive")
    terminal = object_by_id(session.observation(), "terminal:archive")
    check(terminal["components"]["security"]["locked"] is True, "interrupted hack completed anyway")


def repair_reschedule_and_interrupt():
    session = GameSession(); move(session, "room:hall"); move(session, "room:generator")
    act(session, "repair", "machine:generator")
    first_time = next(event["time"] for event in session.debug_queue() if event["id"] == "complete:repair:generator")
    act(session, "repair", "machine:generator")
    second_time = next(event["time"] for event in session.debug_queue() if event["id"] == "complete:repair:generator")
    check(second_time > first_time, "repeat repair did not reschedule temporal handle")
    move(session, "room:hall")
    check(not any(event["id"] == "complete:repair:generator" for event in session.debug_queue()), "movement did not cancel repair")
    session.wait(10); move(session, "room:generator")
    generator = object_by_id(session.observation(), "machine:generator")
    check(generator["components"]["repair"]["state"] == "broken", "interrupted repair completed")


def wrong_code_then_recovery():
    session = GameSession(); move(session, "room:hall"); move(session, "room:vault_ante")
    before = object_by_id(session.observation(), "door:vault")["components"]["door"]
    act(session, "enter_code", "door:vault", {"code": "0000"})
    after = object_by_id(session.observation(), "door:vault")["components"]["door"]
    check(before == after and after["locked"] is True, "wrong code changed the door")
    act(session, "enter_code", "door:vault", {"code": "3142"})
    check(object_by_id(session.observation(), "door:vault")["components"]["door"]["locked"] is False, "world did not continue after failed code")


def combat_after_breach():
    session = GameSession(); move(session, "room:hall"); move(session, "room:vault_ante")
    act(session, "use", "door:vault", {"item": "item:breach_charge"}); session.wait(4)
    check(object_by_id(session.observation(), "enemy:security_drone") is not None, "drone absent for combat")
    act(session, "attack", "enemy:security_drone")
    act(session, "attack", "enemy:security_drone")
    killed = act(session, "attack", "enemy:security_drone")
    drone = object_by_id(killed, "enemy:security_drone")
    check("dead" in drone.get("tags", []), "state closure did not mark drone dead")
    hp = object_by_id(killed, PLAYER_ID)["components"]["health"]["hp"]
    session.wait(4)
    check(object_by_id(session.observation(), PLAYER_ID)["components"]["health"]["hp"] == hp, "dead drone kept attacking")


def save_reload_temporal_handles():
    with tempfile.TemporaryDirectory() as directory:
        hack_path = Path(directory) / "hack.json"
        session = GameSession(); reach_archive_with_power(session)
        act(session, "search", cost=2); act(session, "disable", "trap:archive_wire"); act(session, "hack", "terminal:archive")
        session.save(str(hack_path)); restored = GameSession.load(str(hack_path)); restored.wait(4)
        terminal = object_by_id(restored.observation(), "terminal:archive")
        check(terminal["components"]["security"]["locked"] is False, "hack handle failed across save/load")

        bleeding_path = Path(directory) / "bleeding.json"
        bleeding = GameSession(); reach_archive_with_power(bleeding); act(bleeding, "hack", "terminal:archive")
        bleeding.save(str(bleeding_path)); restored_bleeding = GameSession.load(str(bleeding_path))
        check(relations(restored_bleeding.observation(), "bleeding"), "bleeding state absent after reload")
        restored_bleeding.wait(2)
        hp = object_by_id(restored_bleeding.observation(), PLAYER_ID)["components"]["health"]["hp"]
        check(hp == 76, "bleeding pulse timing changed across save/load")


def observation_boundary():
    observation = GameSession().observation()
    encoded = json.dumps(observation, ensure_ascii=False, sort_keys=True)
    forbidden_keys = {"tick", "revision", "object_revision", "sim_time", "scheduled_events", "rng_state"}

    def walk(value):
        if isinstance(value, dict):
            check(not (set(value) & forbidden_keys), "privileged metadata leaked into Observation")
            for item in value.values(): walk(item)
        elif isinstance(value, list):
            for item in value: walk(item)

    walk(observation)
    for forbidden in ("secret.vault_code", '"secret"', "3142", "trap:archive_wire"):
        check(forbidden not in encoded, f"hidden value leaked: {forbidden}")


def ux_mira_affordance_transition():
    session = GameSession(); move(session, "room:hall"); move(session, "room:infirmary")
    before = action_map(session, "npc:mira")
    check(set(before) == {"social.talk"}, "Mira leaked stabilize affordance without medkit")
    session.perform_action("inventory.take", "item:medkit")
    after = action_map(session, "npc:mira")
    check(after["medical.stabilize"].enabled, "Mira stabilize affordance absent after medkit")
    session.perform_action("medical.stabilize", "npc:mira")
    check("medical.stabilize" not in action_map(session, "npc:mira"), "consumed medkit did not remove stabilize affordance")


def ux_trap_discovery_and_wrench():
    hidden = GameSession(); move(hidden, "room:hall"); move(hidden, "room:archive")
    check("trap:archive_wire" not in entities_by_id(hidden.observation()), "trap focus target leaked before discovery")
    hidden.perform_action("investigation.search", "room:archive")
    check(action_map(hidden, "trap:archive_wire")["trap.disable"].enabled, "wrench did not enable trap disable")

    no_wrench = session_without("item:wrench"); move(no_wrench, "room:hall"); move(no_wrench, "room:archive")
    no_wrench.perform_action("investigation.search", "room:archive")
    check("trap.disable" not in action_map(no_wrench, "trap:archive_wire"), "trap disable leaked without wrench")


def ux_vault_capability_and_focused_code():
    with_charge = GameSession(); move(with_charge, "room:hall"); move(with_charge, "room:vault_ante")
    actions = action_map(with_charge, "door:vault")
    check(set(actions) == {"security.enter_code", "explosive.breach"}, "vault actions wrong with breach charge")
    with_charge.perform_action("security.enter_code", "door:vault", {"code": "0000"})
    check(action_map(with_charge, "door:vault")["security.enter_code"].enabled, "wrong focused code changed door")

    no_charge = session_without("item:breach_charge"); move(no_charge, "room:hall"); move(no_charge, "room:vault_ante")
    check(set(action_map(no_charge, "door:vault")) == {"security.enter_code"}, "breach affordance leaked without charge")
    try:
        no_charge.perform_action("security.enter_code", "room:vault_ante", {"code": "3142"})
    except CommandError:
        pass
    else:
        raise AssertionError("enter_code was executable without door focus target")


def ux_terminal_visible_state():
    offline = GameSession(); move(offline, "room:hall"); move(offline, "room:archive")
    hack = action_map(offline, "terminal:archive")["security.hack"]
    check(not hack.enabled and hack.reason == "终端未通电。", "offline terminal lacks visible disabled reason")

    online = GameSession(); prepare_generator(online); move(online, "room:hall"); move(online, "room:archive")
    check(action_map(online, "terminal:archive")["security.hack"].enabled, "online terminal did not enable hack")
    online.perform_action("security.hack", "terminal:archive")
    check("security.hack" not in action_map(online, "terminal:archive"),
          "hack remained exposed while channeling")

    repair = GameSession(); move(repair, "room:hall"); move(repair, "room:generator")
    repair.perform_action("machine.repair", "machine:generator")
    check("machine.repair" not in action_map(repair, "machine:generator"),
          "repair remained exposed while channeling")


def ux_self_bleeding_and_bandage():
    bandaged = GameSession(); reach_archive_with_power(bandaged)
    bandaged.perform_action("security.hack", "terminal:archive")
    check(action_map(bandaged, PLAYER_ID)["medical.bandage_self"].enabled, "bleeding self lacks bandage action")

    no_bandage = session_without("item:bandage"); reach_archive_with_power(no_bandage)
    no_bandage.perform_action("security.hack", "terminal:archive")
    check("medical.bandage_self" not in action_map(no_bandage, PLAYER_ID), "self bandage leaked without bandage item")


def ux_item_descriptions():
    session = GameSession()
    for item_id in ("item:wrench", "item:bandage", "item:breach_charge"):
        item = object_by_id(session.observation(), item_id)
        check(item["components"]["public"]["description"], f"missing description for {item_id}")
    move(session, "room:hall"); move(session, "room:infirmary")
    session.perform_action("inventory.take", "item:medkit")
    check(object_by_id(session.observation(), "item:medkit")["components"]["public"]["description"], "missing medkit description")

    core = GameSession(); move(core, "room:hall"); move(core, "room:vault_ante")
    core.perform_action("explosive.breach", "door:vault"); core.wait(1); move(core, "room:vault")
    core.perform_action("artifact.take", "artifact:core_zero")
    check(object_by_id(core.observation(), "artifact:core_zero")["components"]["public"]["description"], "missing core description")
    rendered = render(core.observation(), section="inventory")
    for phrase in ("工程扳手", "快速止血用品", "原型能源核心"):
        check(phrase in rendered, f"inventory renderer omitted description phrase: {phrase}")


def ux_help_focus_and_default_command_surface():
    for command in ("look", "watch", "status", "inventory", "move", "wait", "save", "load"):
        check(command in HELP, f"help omitted {command}")
    check("查看" in HELP and "前往" in HELP and "原地等待" in HELP, "help lacks behavior descriptions")
    output = io.StringIO()
    with redirect_stdout(output): _help(GameSession(), "watch")
    check("不会推进时间" in output.getvalue(), "detailed watch help missing time behavior")

    session = GameSession(); move(session, "room:hall"); move(session, "room:infirmary")
    focused = interaction_context(session.observation(), "npc:mira")
    check(_check_focus(session.observation(), focused) == focused, "visible focus unexpectedly invalid")
    move(session, "room:hall")
    output = io.StringIO()
    with redirect_stdout(output): cleared = _check_focus(session.observation(), focused)
    check(cleared is None and "关注已结束" in output.getvalue(), "invisible focus did not invalidate")
    try:
        execute(session, "hack terminal:archive", debug=False)
    except CommandError:
        pass
    else:
        raise AssertionError("legacy contextual command remains in default CLI")


def ux_displayed_action_label_executes():
    session = GameSession(); move(session, "room:hall"); move(session, "room:infirmary")
    output = io.StringIO()
    with redirect_stdout(output):
        session, finished, focus = execute(session, "watch medkit", debug=False)
        session, finished, focus = execute(
            session, "拾取", debug=False, focused_target_id=focus,
        )
    check(not finished, "taking the medkit unexpectedly ended the game")
    check("item:medkit" in inventory_ids(session.observation()),
          "displayed action label did not take the medkit")
    check("unknown global command" not in output.getvalue(),
          "displayed action label was rejected as a global command")
    check(focus is None, "pickup did not clear focus after environment-to-inventory transition")
    medkit = object_by_id(session.observation(), "item:medkit")
    check("available" not in medkit.get("tags", []), "picked-up medkit remained available")
    check("医疗箱" in render(session.observation(), section="inventory"), "inventory omitted medkit")
    with redirect_stdout(output):
        session, finished, focus = execute(session, "watch medkit", debug=False)
    check(focus and focus.kind == "inventory", "re-watched medkit did not enter inventory context")
    check("inventory.take" not in action_map(session, "item:medkit"),
          "inventory medkit still exposed take action")


def ux_action_resolver_aliases_and_unique_labels():
    session = GameSession(); move(session, "room:hall"); move(session, "room:infirmary")

    def assert_forms(target_id, action_id, number, inputs=None):
        observation = session.observation()
        menu = affordances(observation, entities_by_id(observation)[target_id], session.actions)
        spec = session.actions[action_id]
        forms = [number, f"do {number}", spec.label, f"do {spec.label}",
                 action_id, f"do {action_id}"]
        events = []
        for form in forms:
            selected = resolve_context_action(form, menu)
            check(selected.spec.action_id == action_id, f"resolver mapped {form!r} incorrectly")
            event = session.action_adapter.build(
                selected.spec, actor_id=PLAYER_ID, focused_target_id=target_id,
                inputs=inputs or {}, event_id="alias:test", event_time=0,
            ).to_dict()
            events.append(event)
        check(all(event == events[0] for event in events), f"resolver forms changed Event for {action_id}")

    assert_forms("item:medkit", "inventory.take", "1")
    assert_forms("npc:mira", "social.talk", "1")
    session.perform_action("inventory.take", "item:medkit")
    assert_forms("npc:mira", "medical.stabilize", "2")

    duplicate_specs = dict(session.actions)
    duplicate_specs["medical.stabilize"] = replace(
        duplicate_specs["medical.stabilize"], label="交谈",
    )
    try:
        affordances(session.observation(), entities_by_id(session.observation())["npc:mira"], duplicate_specs)
    except ValueError as exc:
        check("duplicate action label" in str(exc), "duplicate label failed for wrong reason")
    else:
        raise AssertionError("duplicate labels in one contextual menu were accepted")


def ux_context_and_target_state_reason():
    session = GameSession(); move(session, "room:hall"); move(session, "room:infirmary")
    observation = session.observation()
    check(interaction_context(observation, PLAYER_ID).kind == "self", "player context is not self")
    check(interaction_context(observation, "item:medkit").kind == "environment", "ground item context is not environment")
    medkit = json.loads(json.dumps(entities_by_id(observation)["item:medkit"]))
    medkit["tags"] = []
    take = next(item for item in affordances(observation, medkit, session.actions)
                if item.spec.action_id == "inventory.take")
    check(not take.enabled and take.reason == "这个物品目前无法拾取。",
          "target_state_reason was not loaded and rendered")
    session.perform_action("inventory.take", "item:medkit")
    check(interaction_context(session.observation(), "item:medkit").kind == "inventory",
          "owned item context is not inventory")


def ux_diff_renderer_invariant():
    def assert_diff(old, new, name, phrase=None):
        check(old != new, f"{name} fixture did not change Observation")
        output = render_diff(old, new)
        check(output != "没有可见变化。", f"{name} falsely reported no visible change")
        if phrase:
            check(phrase in output, f"{name} diff omitted {phrase!r}: {output}")

    move_case = GameSession(); old, new = move_case.act("move", target="room:hall")
    assert_diff(old, new, "move", "你来到中央走廊")

    pickup = GameSession(); move(pickup, "room:hall"); move(pickup, "room:infirmary")
    old, new = pickup.perform_action("inventory.take", "item:medkit")
    assert_diff(old, new, "pickup", "你取得了医疗箱")
    old, new = pickup.perform_action("social.talk", "npc:mira")
    assert_diff(old, new, "talk", "Mira：")
    old, new = pickup.perform_action("medical.stabilize", "npc:mira")
    assert_diff(old, new, "fact discovery", "你获知了一条新信息")
    move(pickup, "room:hall"); move(pickup, "room:vault_ante")
    old, new = pickup.perform_action("security.enter_code", "door:vault", {"code": "3142"})
    assert_diff(old, new, "door unlock", "零号金库门已解锁")

    trap = GameSession(); move(trap, "room:hall"); move(trap, "room:archive")
    trap.perform_action("investigation.search", "room:archive")
    old, new = trap.perform_action("trap.disable", "trap:archive_wire")
    assert_diff(old, new, "trap disable", "细线触发器已被解除")

    generator = GameSession(); move(generator, "room:hall"); move(generator, "room:generator")
    generator.perform_action("machine.repair", "machine:generator")
    old, new = generator.wait(2)
    assert_diff(old, new, "generator online", "发电机恢复了供电")

    damage = GameSession(); reach_archive_with_power(damage)
    old, new = damage.perform_action("security.hack", "terminal:archive")
    assert_diff(old, new, "HP damage", "HP：100 → 80")
    check("你开始流血" in render_diff(old, new), "status-add diff omitted bleeding")
    old, new = damage.perform_action("medical.bandage_self", PLAYER_ID)
    assert_diff(old, new, "status remove", "流血已经停止")


def ux_trap_locality_trigger_and_search_one_shot():
    locality = GameSession(); move(locality, "room:hall"); move(locality, "room:archive")
    locality.perform_action("investigation.search", "room:archive")
    check(object_by_id(locality.observation(), "trap:archive_wire"), "searched trap was not visible")
    room_actions = action_map(locality, "room:archive")
    check("investigation.search" not in room_actions, "search remained available after discovery")
    move(locality, "room:hall")
    check(object_by_id(locality.observation(), "trap:archive_wire") is None,
          "discovered trap remained visible outside archive")
    try:
        cli(locality, "watch trap")
    except CommandError:
        pass
    else:
        raise AssertionError("remote discovered trap remained watchable")
    move(locality, "room:archive")
    check(object_by_id(locality.observation(), "trap:archive_wire"),
          "discovered trap did not reappear on return")
    _, focus, _, _ = cli(locality, "watch trap")
    check(focus and focus.target_id == "trap:archive_wire", "unique archetype alias did not resolve trap")

    triggered = GameSession(); reach_archive_with_power(triggered)
    triggered.perform_action("security.hack", "terminal:archive")
    check(any(relation.get("id") == "discovered:player:archive_wire"
              for relation in triggered.debug_truth()["relations"]),
          "trap trigger did not create discovered relation")
    check(object_by_id(triggered.observation(), "trap:archive_wire"),
          "triggered trap was not immediately visible")


SCENARIOS = [
    ("social route victory", social_route),
    ("technical route victory", technical_route),
    ("force route victory and future drone", force_route),
    ("trap bleeding and bandage cancellation", trap_bleeding_bandage),
    ("hack interrupt on movement", hack_interrupt),
    ("repair reschedule and interrupt", repair_reschedule_and_interrupt),
    ("wrong code is harmless and world continues", wrong_code_then_recovery),
    ("drone combat and dead-state closure", combat_after_breach),
    ("save/reload temporal handles", save_reload_temporal_handles),
    ("ordinary Observation information boundary", observation_boundary),
    ("UX Mira affordance before and after medkit", ux_mira_affordance_transition),
    ("UX trap discovery and wrench filtering", ux_trap_discovery_and_wrench),
    ("UX vault capability and focused code", ux_vault_capability_and_focused_code),
    ("UX terminal offline and online states", ux_terminal_visible_state),
    ("UX self bleeding with and without bandage", ux_self_bleeding_and_bandage),
    ("UX item descriptions in Observation and inventory", ux_item_descriptions),
    ("UX help focus invalidation and command surface", ux_help_focus_and_default_command_surface),
    ("UX displayed action label executes", ux_displayed_action_label_executes),
    ("UX action resolver aliases and unique labels", ux_action_resolver_aliases_and_unique_labels),
    ("UX interaction context and target-state reason", ux_context_and_target_state_reason),
    ("UX diff renderer invariant and specialized output", ux_diff_renderer_invariant),
    ("UX trap locality trigger discovery and one-shot search", ux_trap_locality_trigger_and_search_one_shot),
]


def main():
    for name, scenario in SCENARIOS:
        scenario()
        print(f"PASS: {name}")
    print("ALL PLAYABLE WORLD SCENARIOS PASSED")


if __name__ == "__main__":
    main()
