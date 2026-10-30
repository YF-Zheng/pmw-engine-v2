from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionDefinition,
    ActionRegistry,
    ActionRequest,
    parse_action_definition,
    resolve_action,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
    basic_registry_document,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_actor,
    instantiate_area,
    parse_actor_blueprint,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    ConditionSpec,
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
    TIME_BUDGET_COMPONENT,
    initialize_time_budget,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
TEST_TMP = PROJECT_ROOT / "docs" / "agent_bootstrap" / "evidence" / "test_tmp"
PLAYER = "condition_player"
NPC = "condition_npc"
AREA = "condition_area"
MATERIAL_ID = "condition_crystal"
SKILL_ID = "conditioned_rest"
ACTOR_COMPONENT = "pmw_gameplay_actor"


def _material():
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "condition_resource",
            "effect_kinds": ["heal", "shield"],
            "selectors": ["self"],
            "budget_points": 4,
        }],
    })


def _actor(actor_id, *, controller, mana=5):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": f"{actor_id}_blueprint",
        "hp": {"max": 50, "initial": 50},
        "mana": {"max": 30, "initial": mana, "dynamics": None},
        "attributes": {
            "power": 4,
            "control": 4,
            "resilience": 4,
            "agility": 4,
        },
        "traits": [],
    })
    return instantiate_actor(blueprint, actor_id, controller=controller)


def _area():
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": "condition_area_blueprint",
        "fields": [{
            "id": "heat",
            "domain": {"min": 0, "max": 10},
            "initial": 1,
            "target": 1,
            "rate": 0,
            "curve": "none",
            "max_persistent_patches": 1,
            "max_temporary_modifiers": 1,
        }],
    })
    return instantiate_area(blueprint, AREA)


def _skill_document(*, condition=None, mana=4, effect_id="restore"):
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": SKILL_ID,
        "version": 1,
        "trigger": "on_use",
        "condition": condition,
        "duration": None,
        "cost": {"duration": 1, "mana": mana},
        "scope": {"selectors": ["self"], "relation_types": []},
        "effects": [{
            "id": effect_id,
            "kind": "heal",
            "target": {"kind": "self"},
            "commitment": "required",
            "amount": 1,
        }],
        "budget": {"limit": 4},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }


def _skill(*, condition=None, mana=4):
    return parse_skill_blueprint(
        _skill_document(condition=condition, mana=mana),
        basic_registry().statuses,
        material_authority((_material(),)),
    )


def _runtime(skills, *, player_mana=5, npc_mana=5):
    if not isinstance(skills, tuple):
        skills = (skills,)
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
    )
    content = make_content(base, skills=skills, material_ids=(MATERIAL_ID,))
    area = _area()
    actors = (
        _actor(PLAYER, controller="human", mana=player_mana),
        _actor(NPC, controller="ai", mana=npc_mana),
    )
    world = build_gameplay_world(
        "condition_world",
        areas=(area,),
        actors=actors,
        placements=((PLAYER, AREA), (NPC, AREA)),
    )
    world.entities["pmw:v04:clock"] = clock_entity()
    world = initialize_time_budget(world, 12)
    world = initialize_content_world(world, content)
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for actor_id in (PLAYER, NPC):
        for slot, skill in enumerate(skills):
            change_loadout(
                runtime.session,
                runtime.manifest,
                actor_id=actor_id,
                operation=(
                    "equip_active"
                    if skill.kind == "skill_blueprint"
                    else "equip_passive"
                ),
                skill=skill_ref(skill),
                slot=slot,
            )
    return runtime, compiled


def _actor_component(runtime, actor_id):
    return runtime.session.state.entities[actor_id].components[ACTOR_COMPONENT]


def _budget(runtime):
    return runtime.session.state.entities["pmw:v04:clock"].components[
        TIME_BUDGET_COMPONENT
    ]


def _snapshot(runtime):
    return (
        deepcopy(runtime.session.state.to_dict()),
        deepcopy(runtime.session.runtime.stats),
        runtime.session.runtime.revision,
        runtime.session.runtime.object_revision,
        runtime.session.runtime.state_closure_known,
        deepcopy(list(runtime.session.state.scheduled_events)),
        deepcopy(runtime.session.profiles),
    )


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


def _nested_not(depth):
    result = None
    for _ in range(depth):
        result = {"not": result}
    return result


class ActiveConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_TMP.mkdir(parents=True, exist_ok=True)

    def test_action_condition_is_typed_optional_and_immutable(self):
        definition = parse_action_definition(
            basic_registry_document()["actions"][2],
            basic_registry().statuses,
        )
        self.assertIsInstance(definition, ActionDefinition)
        self.assertEqual(definition.condition, ConditionSpec("always"))

        raw = deepcopy(basic_registry_document()["actions"][2])
        raw["condition"] = None
        definition = parse_action_definition(raw, basic_registry().statuses)
        self.assertEqual(definition.condition, ConditionSpec("always"))
        self.assertIsNone(raw["condition"])

        for invalid in (
            {"resource": {
                "subject": "self",
                "key": "secret",
                "comparator": "gte",
                "value": 1,
            }},
            {"not": {"not": None, "all": [None]}},
        ):
            with self.subTest(invalid=invalid):
                changed = deepcopy(basic_registry_document()["actions"][2])
                changed["condition"] = invalid
                with self.assertRaises(GameplayContractError):
                    parse_action_definition(
                        changed,
                        basic_registry().statuses,
                    )
        changed = deepcopy(basic_registry_document()["actions"][2])
        changed["condition"] = _nested_not(17)
        with self.assertRaisesRegex(
            GameplayContractError, r"\.condition.*max_depth"
        ):
            parse_action_definition(changed, basic_registry().statuses)

    def test_null_and_absent_condition_preserve_basic_identity(self):
        statuses = basic_registry().statuses
        trusted = basic_registry().actions
        for action_id, original in trusted.items():
            raw = next(
                row for row in basic_registry_document()["actions"]
                if row["id"] == action_id
            )
            absent = parse_action_definition(deepcopy(raw), statuses)
            announced = deepcopy(raw)
            announced["condition"] = None
            nulled = parse_action_definition(announced, statuses)
            self.assertEqual(absent.canonical_hash, original.canonical_hash)
            self.assertEqual(nulled.canonical_hash, original.canonical_hash)
            self.assertEqual(absent.condition, ConditionSpec("always"))
            self.assertEqual(nulled.condition, ConditionSpec("always"))

    def test_altered_nonnull_basic_cannot_gain_slot_free_authority(self):
        raw = deepcopy(basic_registry_document()["actions"][0])
        raw["condition"] = {"all": [None]}
        conditional = parse_action_definition(raw, basic_registry().statuses)
        self.assertNotEqual(
            conditional.canonical_hash,
            basic_registry().actions["basic_attack"].canonical_hash,
        )
        document = basic_registry_document()
        document["actions"][0] = [
            row for row in document["actions"]
            if row["id"] == "basic_attack"
        ][0]
        document["actions"][0]["condition"] = {"all": [None]}
        registry = ActionRegistry.parse(document)
        self.assertEqual(
            registry.actions["basic_attack"].canonical_hash,
            conditional.canonical_hash,
        )
        runtime, _ = _runtime(_skill())
        with self.assertRaises(GameplayContractError):
            resolve_action(
                runtime.session,
                registry,
                ActionRequest("forged_basic", PLAYER, "basic_attack", NPC),
            )

    def test_same_parsed_skill_player_npc_pre_cost_boundary_and_current_state(self):
        skill = _skill(condition={"resource": {
            "subject": "self",
            "key": "mana",
            "comparator": "gte",
            "value": 5,
        }})
        runtime, _ = _runtime(skill)
        self.assertEqual(
            runtime.blueprints[(SKILL_ID, 1)].canonical_hash,
            skill.canonical_hash,
        )
        self.assertIn("condition", runtime.blueprints[(SKILL_ID, 1)].canonical_document_json)
        self.assertEqual(skill.canonical_hash, _digest(json.loads(
            skill.canonical_document_json
        )))
        self.assertEqual(skill.action.condition.subject, "self")

        accepted = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("acceptable_player", PLAYER, SKILL_ID),
        )
        self.assertEqual(accepted.action.cost.mana, 4)
        self.assertEqual(_actor_component(runtime, PLAYER)["mana"], 1)
        self.assertEqual(_budget(runtime)["spent_ticks"], 1)

        accepted_npc = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("acceptable_npc", NPC, SKILL_ID),
        )
        self.assertEqual(accepted_npc.action.cost.mana, 4)
        self.assertEqual(_actor_component(runtime, NPC)["mana"], 1)

        before = _snapshot(runtime)
        with self.assertRaisesRegex(
            GameplayContractError, "^action condition is not satisfied$"
        ):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("current_state_reject", PLAYER, SKILL_ID),
            )
        self.assertEqual(_snapshot(runtime), before)

    def test_false_condition_rejects_before_all_side_effects(self):
        skill = _skill(condition={"not": None})
        runtime, _ = _runtime(skill)
        before = _snapshot(runtime)
        with self.assertRaisesRegex(
            GameplayContractError, "^action condition is not satisfied$"
        ):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("false_condition", PLAYER, SKILL_ID),
            )
        self.assertEqual(_snapshot(runtime), before)

    def test_checkpoint_rebuild_preserves_condition_semantics(self):
        skill = _skill(condition={"resource": {
            "subject": "self",
            "key": "mana",
            "comparator": "gte",
            "value": 5,
        }})
        runtime, compiled = _runtime(skill, player_mana=1, npc_mana=5)
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as directory:
            path = Path(directory) / "active_condition_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)

        self.assertEqual(
            restored.blueprints[(SKILL_ID, 1)].canonical_hash,
            skill.canonical_hash,
        )
        self.assertEqual(
            restored.action_registry.actions[SKILL_ID].canonical_hash,
            skill.action.canonical_hash,
        )
        before = _snapshot(restored)
        with self.assertRaises(GameplayContractError):
            submit_timed_primary_action(
                restored.session,
                restored.action_registry,
                ActionRequest("rebuild_reject", PLAYER, SKILL_ID),
            )
        self.assertEqual(_snapshot(restored), before)
        accepted = submit_timed_primary_action(
            restored.session,
            restored.action_registry,
            ActionRequest("rebuild_accept", NPC, SKILL_ID),
        )
        self.assertEqual(accepted.action.cost.mana, 4)
        self.assertEqual(_actor_component(restored, NPC)["mana"], 1)

    def test_passive_action_remains_always_and_hook_condition_separate(self):
        passive_raw = {
            **_skill_document(),
            "kind": "passive_blueprint",
            "id": "condition_passive",
            "trigger": "damage_resolved",
            "condition": {"resource": {
                "subject": "self",
                "key": "mana",
                "comparator": "gte",
                "value": 5,
            }},
            "cost": {"duration": 1, "mana": 0},
            "effects": [{
                "id": "guard",
                "kind": "shield",
                "target": {"kind": "self"},
                "commitment": "required",
                "amount": 3,
            }],
        }
        passive = parse_skill_blueprint(
            passive_raw,
            basic_registry().statuses,
            material_authority((_material(),)),
        )
        self.assertEqual(passive.action.condition, ConditionSpec("always"))
        self.assertEqual(passive.condition.subject, "self")
        self.assertNotEqual(passive.action.condition, passive.condition)
        runtime, _ = _runtime(passive)
        outcome = resolve_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("passive_compatibility", PLAYER, "basic_attack", NPC),
        )
        fired = tuple(
            record for record in outcome.auto_hooks
            if record.status == "fired"
        )
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].owner, NPC)
        self.assertEqual(_actor_component(runtime, NPC)["shield"], 3)


if __name__ == "__main__":
    unittest.main()
