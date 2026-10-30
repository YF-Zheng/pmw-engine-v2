"""Independent executable review of the C4 legacy positive fixture change."""

from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRequest,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests import (
    test_sandbox_condition_limits as fixture,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
)

EVIDENCE = ROOT / "docs" / "agent_bootstrap" / "evidence"
TEST_PATH = (
    "experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/"
    "test_sandbox_condition_limits.py"
)
TARGET_TEST = "test_normal_timed_player_and_npc_actions_with_accepted_condition"
ORIGINAL = {"all": [None, {"not": None}]}
CORRECTED = {"all": [None, {"not": {"not": None}}]}
EXPECTED_ERROR = "action condition is not satisfied"


def _json_value(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_json_value(item) for item in value)
    return deepcopy(value)


def _snapshot(runtime) -> dict[str, Any]:
    session = runtime.session
    return {
        "world": _json_value(session.state.to_dict()),
        "stats": _json_value(session.runtime.stats),
        "revision": session.runtime.revision,
        "object_revision": session.runtime.object_revision,
        "state_closure_known": session.runtime.state_closure_known,
        "schedule": _json_value(session.state.scheduled_events),
        "profiles": _json_value(session.profiles),
        "tick": session.state.tick,
        "sim_time": session.state.sim_time,
        "actor_components": {
            actor_id: _json_value(
                session.state.entities[actor_id].components["pmw_gameplay_actor"]
            )
            for actor_id in (fixture.PLAYER_ID, fixture.NPC_ID)
        },
        "time_budget": _json_value(
            session.state.entities["pmw:v04:clock"].components[
                TIME_BUDGET_COMPONENT
            ]
        ),
        "process_components": {
            profile.id: _json_value(
                session.state.entities[profile.process_entity_id].components[
                    "pmw_sandbox_process"
                ]
            )
            for profile in runtime.action_registry.process_controller.profiles
        },
        "stocks": {
            entity_id: _json_value(
                session.state.entities[entity_id].components["stock"]
            )
            for entity_id in (
                "condition_player_ore",
                "condition_player_ingot",
                "condition_npc_ore",
                "condition_npc_ingot",
            )
        },
    }


def _runtime(condition):
    skill = fixture._blueprint_with_condition(condition)
    player = fixture._profile("condition_player", fixture.PLAYER_ID)
    npc = fixture._profile("condition_npc", fixture.NPC_ID)
    runtime, _, _ = fixture._runtime(
        (player, npc),
        skill=skill,
        time_budget=6,
    )
    return runtime, skill


def _submission(actor_id: str, skill_id: str, request_id: str) -> ActionRequest:
    return ActionRequest(request_id, actor_id, skill_id)


def _patch_surface() -> dict[str, Any]:
    original = subprocess.run(
        ["git", "show", f"HEAD:{TEST_PATH}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    current = (ROOT / TEST_PATH).read_text(encoding="utf-8")
    old_tree = ast.parse(original)
    new_tree = ast.parse(current)
    assignments: dict[str, list[str]] = {}
    for label, tree in (("HEAD", old_tree), ("WORKTREE", new_tree)):
        cls = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "AcceptedSemanticsTests"
        )
        method = next(
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == TARGET_TEST
        )
        matches = [
            node
            for node in method.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "condition"
                for target in node.targets
            )
        ]
        assignments[label] = [ast.unparse(node) for node in matches]
        method.body = [
            node
            for node in method.body
            if not (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "condition"
                    for target in node.targets
                )
            )
        ]
    return {
        "head_assignment": assignments["HEAD"],
        "worktree_assignment": assignments["WORKTREE"],
        "assignment_count_is_one_each": (
            len(assignments["HEAD"]) == len(assignments["WORKTREE"]) == 1
        ),
        "all_other_ast_identical": (
            ast.dump(old_tree, include_attributes=False)
            == ast.dump(new_tree, include_attributes=False)
        ),
        "ast_node_count": {
            "HEAD": sum(1 for _ in ast.walk(old_tree)),
            "WORKTREE": sum(1 for _ in ast.walk(new_tree)),
        },
        "diff_check": subprocess.run(
            ["git", "diff", "--", TEST_PATH],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.splitlines(),
    }


def _false_rejection(actor_id: str) -> dict[str, Any]:
    runtime, skill = _runtime(ORIGINAL)
    before = _snapshot(runtime)
    error = None
    try:
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            _submission(actor_id, skill.id, f"original_false_{actor_id}"),
        )
    except GameplayContractError as caught:
        error = str(caught)
    after = _snapshot(runtime)
    mana = after["actor_components"][actor_id]["mana"]
    passed = (
        error is not None
        and EXPECTED_ERROR in error
        and before == after
        and mana == 20.0
        and after["time_budget"]["spent_ticks"] == 0
        and after["time_budget"]["remaining_ticks"] == 6
        and after["tick"] == 0
        and after["sim_time"] == 0.0
        and after["schedule"] == []
        and after["stocks"]["condition_player_ore"]["amount"] == 10.0
        and after["stocks"]["condition_npc_ore"]["amount"] == 10.0
    )
    return {
        "actor_id": actor_id,
        "condition": ORIGINAL,
        "raised": error is not None,
        "error": error,
        "snapshot_equal": before == after,
        "mana_before": before["actor_components"][actor_id]["mana"],
        "mana_after": mana,
        "time_budget": after["time_budget"],
        "tick": after["tick"],
        "sim_time": after["sim_time"],
        "schedule": after["schedule"],
        "processes": after["process_components"],
        "stocks": after["stocks"],
        "revision": after["revision"],
        "passed": passed,
    }


def _corrected_positive() -> dict[str, Any]:
    runtime, skill = _runtime(CORRECTED)
    before = _snapshot(runtime)
    player = submit_timed_primary_action(
        runtime.session,
        runtime.action_registry,
        _submission(fixture.PLAYER_ID, skill.id, "corrected_player"),
    )
    npc = submit_timed_primary_action(
        runtime.session,
        runtime.action_registry,
        _submission(fixture.NPC_ID, skill.id, "corrected_npc"),
    )
    after = _snapshot(runtime)
    player_mana = after["actor_components"][fixture.PLAYER_ID]["mana"]
    npc_mana = after["actor_components"][fixture.NPC_ID]["mana"]
    passed = (
        player.time.duration == 2
        and npc.time.duration == 2
        and player.time.after_remaining == 4
        and npc.time.after_remaining == 2
        and after["time_budget"]["spent_ticks"] == 4
        and after["time_budget"]["remaining_ticks"] == 2
        and player_mana == 16.0
        and npc_mana == 16.0
        and after["stocks"]["condition_player_ore"]["amount"] == 6.0
        and after["stocks"]["condition_npc_ore"]["amount"] == 6.0
        and after["stocks"]["condition_player_ingot"]["amount"] == 2.0
        and after["stocks"]["condition_npc_ingot"]["amount"] == 2.0
        and after["tick"] == 1
        and after["sim_time"] == 4.0
    )
    return {
        "condition": CORRECTED,
        "player_duration": player.time.duration,
        "npc_duration": npc.time.duration,
        "player_mana_before": before["actor_components"][fixture.PLAYER_ID]["mana"],
        "player_mana_after": player_mana,
        "npc_mana_before": before["actor_components"][fixture.NPC_ID]["mana"],
        "npc_mana_after": npc_mana,
        "time_budget": after["time_budget"],
        "tick": after["tick"],
        "sim_time": after["sim_time"],
        "schedule": after["schedule"],
        "player_process": after["process_components"]["condition_player"],
        "npc_process": after["process_components"]["condition_npc"],
        "stocks": after["stocks"],
        "revision": after["revision"],
        "passed": passed,
    }


def main() -> int:
    report = {
        "probe": "c4_active_fixture_review_probe.py",
        "repository_root": str(ROOT),
        "test_path": TEST_PATH,
        "target_test": TARGET_TEST,
        "expressions": {"original": ORIGINAL, "corrected": CORRECTED},
        "patch_surface": _patch_surface(),
        "original_false_player": _false_rejection(fixture.PLAYER_ID),
        "original_false_npc": _false_rejection(fixture.NPC_ID),
        "corrected_true": _corrected_positive(),
    }
    checks = (
        report["patch_surface"]["assignment_count_is_one_each"]
        and report["patch_surface"]["all_other_ast_identical"]
        and report["original_false_player"]["passed"]
        and report["original_false_npc"]["passed"]
        and report["corrected_true"]["passed"]
    )
    report["verdict"] = "ACCEPT" if checks else "REJECT"
    target = EVIDENCE / "c4_active_fixture_review.json"
    target.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
