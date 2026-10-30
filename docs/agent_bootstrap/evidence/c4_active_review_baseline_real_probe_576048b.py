"""Standalone C4.3 baseline probe. Not part of the collected review suite."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import importlib
import json
import os
from pathlib import Path
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_actor,
    instantiate_area,
    parse_actor_blueprint,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    evaluate_condition,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    clock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    initialize_time_budget,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


PLAYER = "c43_review_player"
AREA = "c43_review_area"
MATERIAL_ID = "c43_review_catalyst"
SKILL_ID = "c43_review_false_heal"
EVIDENCE_PATH = (
    Path(__file__).resolve().parent / "c4_active_review_baseline_576048b.json"
)


def _actor(actor_id: str, *, controller: str, hp: float = 40.0):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": "c43_review_actor_blueprint",
        "hp": {"max": 50.0, "initial": hp},
        "mana": {"max": 30.0, "initial": 5.0, "dynamics": None},
        "attributes": {
            "power": 4.0,
            "control": 4.0,
            "resilience": 4.0,
            "agility": 4.0,
        },
        "traits": [],
    })
    return instantiate_actor(blueprint, actor_id, controller=controller)


def _material():
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "c43_review_restoration",
            "effect_kinds": ["heal"],
            "selectors": ["self"],
            "budget_points": 8.0,
        }],
    })


def _skill_document():
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": SKILL_ID,
        "version": 1,
        "trigger": "on_use",
        "condition": {"not": None},
        "duration": None,
        "cost": {"duration": 1, "mana": 1.0},
        "scope": {"selectors": ["self"], "relation_types": []},
        "effects": [{
            "id": "restore",
            "kind": "heal",
            "target": {"kind": "self"},
            "commitment": "required",
            "amount": 2.0,
        }],
        "budget": {"limit": 8.0},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _module_source_hash(module_name: str) -> tuple[str, str]:
    module = importlib.import_module(module_name)
    source_path = Path(module.__file__).resolve()
    return str(source_path), _sha256(source_path)


def _snapshot(session):
    return {
        "world": _json_value(session.state.to_dict()),
        "stats": _json_value(session.runtime.stats),
        "revision": session.runtime.revision,
        "object_revision": session.runtime.object_revision,
        "state_closure_known": session.runtime.state_closure_known,
        "schedule": [
            deepcopy(event.to_dict())
            for event in session.state.scheduled_events
        ],
    }


def _json_value(value):
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return deepcopy(value)


class BaselineProbe(unittest.TestCase):
    def test_false_top_level_condition_should_not_cast(self):
        actions_module_path, actions_module_hash = _module_source_hash(
            "experiments.generative_mechanics.next_tracks_v06."
            "gameplay_v04.actions"
        )
        skills_module_path, skills_module_hash = _module_source_hash(
            "experiments.generative_mechanics.next_tracks_v06."
            "gameplay_v04.skills"
        )
        self.assertEqual(
            actions_module_hash,
            "9e2d3589990d7dbf915af00a9a0434241f831903fa92d49ebc542cb8e1f89530",
        )
        self.assertEqual(
            skills_module_hash,
            "5e6569c1ad5bbe3304077f8dcdc0e54349f9a75140a470059fa09d5d32b1102a",
        )

        material = _material()
        raw = _skill_document()
        skill = parse_skill_blueprint(
            raw,
            basic_registry().statuses,
            material_authority((material,)),
        )
        self.assertFalse(
            evaluate_condition(skill.condition, {"self": {}, "target_actor": {}, "current_area": {}})
        )
        base = ActionRegistry(
            basic_registry().actions.values(),
            basic_registry().statuses.values(),
        )
        content = make_content(
            base,
            skills=(skill,),
            material_ids=(MATERIAL_ID,),
        )
        area = instantiate_area(
            parse_area_blueprint({
                "protocol": "pmw-gameplay-v0.4",
                "kind": "area_blueprint",
                "id": "c43_review_area_blueprint",
                "fields": [{
                    "id": "heat",
                    "domain": {"min": 0.0, "max": 10.0},
                    "initial": 1.0,
                    "target": 1.0,
                    "rate": 0.0,
                    "curve": "none",
                }],
            }),
            AREA,
        )
        player = _actor(PLAYER, controller="human")
        world = build_gameplay_world(
            "c43_review_world",
            areas=(area,),
            actors=(player,),
            placements=((PLAYER, AREA),),
        )
        world.entities["pmw:v04:clock"] = clock_entity()
        world = initialize_time_budget(world, 3)
        world = initialize_content_world(world, content)
        compiled = compile_content(content)
        session = build_content_session(world, compiled)
        runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=PLAYER,
            operation="equip_active",
            skill=skill_ref(skill),
            slot=0,
        )

        before = _snapshot(runtime.session)
        before_tick = runtime.session.state.tick
        before_sim_time = runtime.session.state.sim_time
        actor_before = deepcopy(
            runtime.session.state.entities[PLAYER].components["pmw_gameplay_actor"]
        )
        clock_before = deepcopy(
            runtime.session.state.entities["pmw:v04:clock"].components[
                "pmw_gameplay_time_budget"
            ]
        )
        error = None
        outcome = None
        try:
            outcome = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("c43_false_probe", PLAYER, SKILL_ID),
            )
        except GameplayContractError as exc:
            error = str(exc)
        after = _snapshot(runtime.session)
        after_tick = runtime.session.state.tick
        after_sim_time = runtime.session.state.sim_time
        actor_after = deepcopy(
            runtime.session.state.entities[PLAYER].components["pmw_gameplay_actor"]
        )
        clock_after = deepcopy(
            runtime.session.state.entities["pmw:v04:clock"].components[
                "pmw_gameplay_time_budget"
            ]
        )
        observed = {
            "status": "actual_gap_reproduced" if error is None else "condition_rejected",
            "baseline_commit": "576048b0f4796695a63883b46c6c62b03ef92b8b",
            "imported_actions_path": actions_module_path,
            "imported_skills_path": skills_module_path,
            "source_sha256": {
                "actions.py": actions_module_hash,
                "skills.py": skills_module_hash,
            },
            "skill": {
                "id": skill.id,
                "version": skill.version,
                "skill_hash": skill.canonical_hash,
                "action_hash": skill.action.canonical_hash,
                "condition": asdict(skill.condition),
                "evaluated_condition": evaluate_condition(
                    skill.condition,
                    {"self": {}, "target_actor": {}, "current_area": {}},
                ),
            },
            "before": {
                "mana": actor_before["mana"],
                "hp": actor_before["hp"],
                "tick": before_tick,
                "sim_time": before_sim_time,
                "budget": clock_before,
                "state_sha256": hashlib.sha256(
                    json.dumps(before, sort_keys=True).encode()
                ).hexdigest(),
            },
            "after": {
                "mana": actor_after["mana"],
                "hp": actor_after["hp"],
                "tick": after_tick,
                "sim_time": after_sim_time,
                "budget": clock_after,
                "state_sha256": hashlib.sha256(
                    json.dumps(after, sort_keys=True).encode()
                ).hexdigest(),
            },
            "raised_error": error,
            "outcome_present": outcome is not None,
            "outcome_duration": None if outcome is None else outcome.action.cost.duration,
            "world_unchanged": before["world"] == after["world"],
            "runtime_metadata_unchanged": before["stats"] == after["stats"],
            "scope": (
                "Standalone HEAD baseline probe; intentionally fails on the "
                "known omitted top-level condition. It is not collected by the "
                "permanent review suite."
            ),
            "environment": {
                "PYTHONPATH": os.environ.get("PYTHONPATH"),
                "PYTHONDONTWRITEBYTECODE": os.environ.get(
                    "PYTHONDONTWRITEBYTECODE"
                ),
                "PYTHONIOENCODING": os.environ.get("PYTHONIOENCODING"),
                "TEMP": os.environ.get("TEMP"),
                "TMP": os.environ.get("TMP"),
                "TMPDIR": os.environ.get("TMPDIR"),
            },
        }
        EVIDENCE_PATH.write_text(
            json.dumps(observed, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.assertIsNotNone(
            error,
            {
                "failure": "false top-level condition executed",
                "mana": [actor_before["mana"], actor_after["mana"]],
                "hp": [actor_before["hp"], actor_after["hp"]],
                "time": [
                    before_sim_time,
                    clock_after["spent_ticks"],
                ],
            },
        )


if __name__ == "__main__":
    unittest.main()
