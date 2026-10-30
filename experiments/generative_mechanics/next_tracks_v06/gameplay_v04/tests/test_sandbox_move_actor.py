from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pmw import Entity, Relation

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ACTOR_COMPONENT,
    ActionRegistry,
    ActionRequest,
    _resolve_action,
    parse_action_definition,
    parse_action_request,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.effects import (
    EFFECT_KINDS,
    parse_effect,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.relations import (
    RELATION_COMPONENT,
    RelationController,
    RelationProfile,
    instantiate_relation,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    clock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    _effect_cost,
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

PLAYER = "move_player"
NPC = "move_npc"
AREA_A = "move_area_a"
AREA_B = "move_area_b"
AREA_C = "move_area_c"
CLOCK = "pmw:v04:clock"
MATERIAL_ID = "move_crystal"
MOVE_SKILL = "move_step"
CONTROL_SKILL = "move_control"
PROFILE_ID = "move_link_control"
LINK_ID = "move_link_ab"
SOURCE_MARKER = "move_source"
TARGET_MARKER = "move_sink"
SOURCE_ID = "move_source_node"
TARGET_ID = "move_sink_node"


def _field(field_id="humidity", *, initial=0.2, target=0.8, rate=0.2):
    return {
        "id": field_id,
        "domain": {"min": 0.0, "max": 1.0},
        "initial": initial,
        "target": target,
        "rate": rate,
        "curve": "linear",
        "max_persistent_patches": 2,
        "max_temporary_modifiers": 2,
    }


def _area(area_id):
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": f"{area_id}_blueprint",
        "fields": [_field()],
    })
    return instantiate_area(blueprint, area_id)


def _actor(actor_id, *, controller):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": f"{actor_id}_blueprint",
        "hp": {"max": 50, "initial": 50},
        "mana": {"max": 30, "initial": 20, "dynamics": None},
        "attributes": {
            "power": 4, "control": 4, "resilience": 4, "agility": 4,
        },
        "traits": [],
    })
    return instantiate_actor(blueprint, actor_id, controller=controller)


def _move_effect(effect_id="travel", **overrides):
    raw = {
        "id": effect_id,
        "kind": "move_actor",
        "target": {"kind": "adjacent_area"},
        "commitment": "required",
    }
    raw.update(overrides)
    return raw


def _modifier_effect(
    effect_id="link_disable",
    *,
    profile_id=PROFILE_ID,
    enabled=False,
    duration=2,
    **overrides,
):
    raw = {
        "id": effect_id,
        "kind": "relation_modifier",
        "target": {"kind": "current_area"},
        "commitment": "required",
        "relation_profile_id": profile_id,
        "relation_enabled": enabled,
        "duration": duration,
    }
    raw.update(overrides)
    return raw


def _dynamics_effect(effect_id="soak", **overrides):
    raw = {
        "id": effect_id,
        "kind": "dynamics_modifier",
        "target": {"kind": "current_area"},
        "commitment": "required",
        "field_id": "humidity",
        "rate_add": 0.2,
        "rate_multiplier": 1.0,
        "curve": "linear",
        "curve_priority": 2,
        "duration": 6,
    }
    raw.update(overrides)
    return raw


def _skill_document(
    skill_id,
    effects,
    *,
    kind="skill_blueprint",
    trigger="on_use",
    mana=4.0,
    budget=20.0,
    relations=(),
):
    selectors = list(dict.fromkeys(
        item["target"]["kind"] for item in effects
    ))
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": kind,
        "id": skill_id,
        "version": 1,
        "trigger": trigger,
        "condition": None,
        "duration": None,
        "cost": {
            "duration": 1 if kind == "passive_blueprint" else 1,
            "mana": 0 if kind == "passive_blueprint" else mana,
        },
        "scope": {
            "selectors": selectors,
            "relation_types": list(relations),
        },
        "effects": effects,
        "budget": {"limit": budget},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }


def _material(*, kinds=("move_actor",), selectors=("adjacent_area",), budget=20.0):
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "move_authority",
            "effect_kinds": list(kinds),
            "selectors": list(selectors),
            "budget_points": budget,
        }],
    })


def _skill(raw, *, kinds=None, selectors=None):
    return parse_skill_blueprint(
        raw,
        basic_registry().statuses,
        material_authority((_material(
            kinds=kinds or tuple(dict.fromkeys(
                item["kind"] for item in raw["effects"]
            )),
            selectors=selectors or tuple(dict.fromkeys(
                item["target"]["kind"] for item in raw["effects"]
            )),
            budget=raw["budget"]["limit"],
        ),)),
    )


def _profile(
    owner,
    *,
    relation_type="adjacent",
    area_id=AREA_A,
    source_id=AREA_A,
    target_id=AREA_B,
):
    return RelationProfile(
        PROFILE_ID,
        LINK_ID,
        relation_type,
        source_id,
        target_id,
        owner,
        area_id,
        ("pmw_gameplay_area",),
        ("pmw_gameplay_area",),
        8,
    )


def _move_world(
    *,
    player_area=AREA_A,
    npc_area=AREA_A,
    links=(("bare", None),),
    collision=False,
    extra_located=0,
    extra_entities=(),
    extra_relations=(),
    time_budget=20,
):
    areas = {
        AREA_A: _area(AREA_A),
        AREA_B: _area(AREA_B),
        AREA_C: _area(AREA_C),
    }
    actors = {
        PLAYER: _actor(PLAYER, controller="human"),
        NPC: _actor(NPC, controller="ai"),
    }
    world = build_gameplay_world(
        "move_actor_world",
        areas=areas.values(),
        actors=actors.values(),
        placements=((PLAYER, player_area), (NPC, npc_area)),
    )
    world.entities[CLOCK] = clock_entity()
    for relation_id, enabled in links:
        components = {}
        if isinstance(enabled, dict):
            components = enabled
        elif enabled is not None:
            components[RELATION_COMPONENT] = {
                "effective_enabled": enabled,
            }
        world.relations[relation_id] = Relation(
            relation_id,
            "adjacent",
            AREA_A,
            AREA_B,
            components=components,
        )
    for index in range(extra_located):
        relation_id = f"extra_located_{index}"
        world.relations[relation_id] = Relation(
            relation_id, "located_in", PLAYER, AREA_C
        )
    if collision:
        entity = Entity(
            f"located:{PLAYER}:{AREA_B}",
            "collision_marker",
            components={},
        )
        world.entities[entity.id] = entity
    for entity in extra_entities:
        world.entities[entity.id] = entity
    for relation in extra_relations:
        world.relations[relation.id] = relation
    return initialize_time_budget(world, time_budget)


def _formal_runtime(
    skills,
    *,
    world=None,
    relation_controller=None,
    equip=(PLAYER, NPC),
):
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        relation_controller=relation_controller,
    )
    content = make_content(
        base,
        skills=tuple(skills),
        material_ids=(MATERIAL_ID,),
    )
    initialized = initialize_content_world(
        world if world is not None else _move_world(),
        content,
    )
    compiled = compile_content(content)
    session = build_content_session(initialized, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for actor_id in equip:
        for slot, skill in enumerate(skills):
            change_loadout(
                runtime.session,
                runtime.manifest,
                actor_id=actor_id,
                operation="equip_active",
                skill=skill_ref(skill),
                slot=slot,
            )
    return runtime, compiled


def _move_skill(**kwargs):
    return _skill(_skill_document(MOVE_SKILL, [_move_effect()], **kwargs))


def _control_world(*, profile, base_enabled=True, extra_links=()):
    if isinstance(extra_links, dict):
        extra_links = (extra_links,)
    located = (
        Relation("scope_located_area_a", "located_in", AREA_A, AREA_A),
        Relation("scope_located_area_b", "located_in", AREA_B, AREA_A),
    )
    links = (
        instantiate_relation(profile, base_enabled=base_enabled),
        *(
            Relation(
                relation_id,
                "adjacent",
                AREA_A,
                AREA_B,
                components=components,
            )
            for relation_id, components in extra_links
        ),
    )
    return _move_world(
        links=(),
        extra_relations=(*located, *links),
    )


def _control_skill(effect=None):
    return _skill(
        _skill_document(
            CONTROL_SKILL,
            [effect or _modifier_effect()],
            mana=1.0,
            budget=8.0,
            relations=("adjacent",),
        ),
        kinds=("relation_modifier",),
        selectors=("current_area",),
    )


def _actor_state(runtime, actor_id):
    return runtime.session.state.entities[actor_id].components[ACTOR_COMPONENT]


def _budget(runtime):
    return runtime.session.state.entities[CLOCK].components[
        TIME_BUDGET_COMPONENT
    ]


def _field_state(runtime, area_id=AREA_A):
    return runtime.session.state.entities[area_id].components[
        "pmw_gameplay_dynamics"
    ]["fields"]["humidity"]


def _locations(runtime, actor_id):
    return sorted((
        relation for relation in runtime.session.state.relations.values()
        if relation.type == "located_in" and relation.source == actor_id
    ), key=lambda relation: relation.id)


def _snapshot(runtime):
    return (
        deepcopy(runtime.session.state.to_dict()),
        runtime.session.runtime.revision,
        runtime.session.runtime.object_revision,
        deepcopy(runtime.session.runtime.stats),
        runtime.session.runtime.state_closure_known,
        deepcopy(runtime.session.state.scheduled_events),
        id(runtime.session.runtime),
    )


def _request_identity(request):
    return (
        request.request_id,
        request.actor_id,
        request.action_id,
        request.target_actor_id,
        request.target_area_id,
    )


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _assert_rejected(testcase, runtime, request, pattern, *args, **kwargs):
    before = _snapshot(runtime)
    with testcase.assertRaisesRegex(GameplayContractError, pattern):
        _resolve_action(
            runtime.session,
            runtime.action_registry,
            request,
            *args,
            **kwargs,
        )
    testcase.assertEqual(_snapshot(runtime), before)


class MoveActorSchemaTests(unittest.TestCase):
    def test_closed_kind_schema_cost_and_old_hashes(self):
        self.assertEqual(EFFECT_KINDS[-1], "move_actor")
        effect = parse_effect(
            _move_effect(), basic_registry().statuses
        )
        self.assertEqual(effect.target.kind, "adjacent_area")
        self.assertEqual(effect.commitment, "required")
        self.assertEqual(_effect_cost(effect), 2.0)
        for change in (
            {"target": {"kind": "current_area"}},
            {"commitment": "conditional"},
            {"condition": None},
            {"amount": 1},
            {"duration": 1},
            {"extra": True},
        ):
            with self.subTest(change=change):
                with self.assertRaises(GameplayContractError):
                    parse_effect(
                        _move_effect(**change), basic_registry().statuses
                    )
        for key in ("id", "kind", "target", "commitment"):
            raw = _move_effect()
            raw.pop(key)
            with self.subTest(missing=key):
                with self.assertRaises(GameplayContractError):
                    parse_effect(raw, basic_registry().statuses)
        statuses = basic_registry().statuses
        for row in basic_registry_document()["actions"]:
            self.assertEqual(
                parse_action_definition(
                    deepcopy(row), statuses
                ).canonical_hash,
                basic_registry().actions[row["id"]].canonical_hash,
            )

    def test_request_trailing_area_is_strict_and_absent_payload_is_old(self):
        parsed = parse_action_request({
            "request_id": "request_move",
            "actor_id": PLAYER,
            "action_id": MOVE_SKILL,
            "target_area_id": AREA_B,
        })
        self.assertEqual(
            _request_identity(parsed),
            ("request_move", PLAYER, MOVE_SKILL, None, AREA_B),
        )
        old = parse_action_request({
            "request_id": "request_old",
            "actor_id": PLAYER,
            "action_id": MOVE_SKILL,
        })
        self.assertIsNone(old.target_area_id)
        self.assertEqual(
            old,
            ActionRequest("request_old", PLAYER, MOVE_SKILL),
        )
        self.assertEqual(
            ActionRequest("id_x", PLAYER, MOVE_SKILL, AREA_C).target_actor_id,
            AREA_C,
        )
        for bad in (
            "Upper",
            "",
            1,
            True,
            [],
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(GameplayContractError):
                    parse_action_request({
                        "request_id": "request_bad",
                        "actor_id": PLAYER,
                        "action_id": MOVE_SKILL,
                        "target_area_id": bad,
                    })

        move = _move_skill()
        runtime, _ = _formal_runtime((move,))
        submitted = _resolve_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("legacy_wait", PLAYER, "basic_wait"),
        )
        root = submitted.event_result.trace.events[0].event
        self.assertNotIn("target_area_id", root.payload)
        with self.assertRaisesRegex(
            GameplayContractError, "target_area_id"
        ):
            _resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("missing_target", PLAYER, MOVE_SKILL),
            )
        with self.assertRaisesRegex(
            GameplayContractError, "target_area_id"
        ):
            _resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(
                    "non_move_target", PLAYER, "basic_wait", None, AREA_B
                ),
            )

    def test_action_and_skill_reject_forbidden_move_combinations(self):
        statuses = basic_registry().statuses
        move = _move_effect()
        duplicate = _move_effect("travel_again")
        disallowed = {
            "damage": {
                "id": "hit",
                "kind": "damage",
                "target": {"kind": "target_actor"},
                "commitment": "required",
                "amount": 1,
            },
            "process_start": {
                "id": "process",
                "kind": "process_start",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "process_template_id": "template",
            },
            "process_modify": {
                "id": "process_modify",
                "kind": "process_modify",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "process_template_id": "template",
                "process_rate": 1,
            },
            "drive_source": {
                "id": "drive",
                "kind": "drive_source",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "drive_profile_id": "profile",
                "drive_rate": 1,
                "duration": 1,
            },
            "relation_modifier": _modifier_effect(),
        }
        allowed = {
            "heal": {
                "id": "heal",
                "kind": "heal",
                "target": {"kind": "self"},
                "commitment": "required",
                "amount": 1,
            },
            "shield": {
                "id": "shield",
                "kind": "shield",
                "target": {"kind": "self"},
                "commitment": "required",
                "amount": 1,
            },
            "add_resource": {
                "id": "mana",
                "kind": "add_resource",
                "target": {"kind": "self"},
                "commitment": "required",
                "resource": "mana",
                "amount": 1,
            },
            "modify_field": {
                "id": "field",
                "kind": "modify_field",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": "humidity",
                "amount": 0.1,
            },
        }
        for name, extra in disallowed.items():
            scope = sorted({move["target"]["kind"], extra["target"]["kind"]})
            raw = {
                "id": f"bad_{name}",
                "version": 1,
                "action_type": "skill",
                "cost": {"duration": 1, "mana": 1},
                "scope": {"selectors": scope, "relation_types": ["adjacent"]},
                "effects": [deepcopy(move), deepcopy(extra)],
            }
            with self.subTest(disallowed=name):
                with self.assertRaisesRegex(
                    GameplayContractError, "move_actor"
                ):
                    parse_action_definition(raw, statuses)
                document = _skill_document(f"bad_{name}", raw["effects"])
                with self.assertRaisesRegex(
                    GameplayContractError, "move_actor"
                ):
                    _skill(document)
        raw = {
            "id": "duplicate_move",
            "version": 1,
            "action_type": "skill",
            "cost": {"duration": 1, "mana": 1},
            "scope": {
                "selectors": ["adjacent_area"],
                "relation_types": [],
            },
            "effects": [move, duplicate],
        }
        with self.assertRaisesRegex(GameplayContractError, "one move_actor"):
            parse_action_definition(raw, statuses)
        with self.assertRaisesRegex(GameplayContractError, "one move_actor"):
            _skill(_skill_document("duplicate_skill", [move, duplicate]))
        parse_action_definition({
            "id": "move_and_heal",
            "version": 1,
            "action_type": "skill",
            "cost": {"duration": 1, "mana": 1},
            "scope": {
                "selectors": ["adjacent_area", "self"],
                "relation_types": [],
            },
            "effects": [move, allowed["heal"]],
        }, statuses)
        for name, extra in allowed.items():
            with self.subTest(allowed=name):
                parse_action_definition({
                    "id": f"move_and_{name}",
                    "version": 1,
                    "action_type": "skill",
                    "cost": {"duration": 1, "mana": 1},
                    "scope": {
                        "selectors": sorted({
                            move["target"]["kind"],
                            extra["target"]["kind"],
                        }),
                        "relation_types": [],
                    },
                    "effects": [deepcopy(move), deepcopy(extra)],
                }, statuses)

    def test_passive_and_selector_authority_reject(self):
        passive = _skill_document(
            "passive_move",
            [_move_effect()],
            kind="passive_blueprint",
            trigger="damage_resolved",
        )
        with self.assertRaisesRegex(
            GameplayContractError, "active on_use"
        ):
            _skill(passive)
        with self.assertRaisesRegex(
            GameplayContractError, "scope authorization"
        ):
            _skill(_skill_document("wrong_scope", [_move_effect()]),
                   selectors=("current_area",))
        with self.assertRaisesRegex(
            GameplayContractError, "effect authorization"
        ):
            _skill(_skill_document("wrong_kind", [_move_effect()]),
                   kinds=("heal",))


class MoveActorRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_TMP.mkdir(parents=True, exist_ok=True)

    def test_same_parsed_skill_moves_player_and_npc_with_engine_lifecycle(self):
        skill = _move_skill()
        controller = RelationController(())
        runtime, _ = _formal_runtime(
            (skill,),
            world=_move_world(links=(("bare_ab", None),)),
            relation_controller=controller,
        )
        self.assertEqual(
            runtime.blueprints[(MOVE_SKILL, 1)].canonical_hash,
            skill.canonical_hash,
        )
        for actor_id, request_id in (
            (PLAYER, "player_move"),
            (NPC, "npc_move"),
        ):
            submitted = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(request_id, actor_id, MOVE_SKILL, None, AREA_B),
            )
            self.assertEqual(submitted.action.cost.mana, 4.0)
            self.assertEqual(submitted.action.cost.duration, 1)
            self.assertEqual(_actor_state(runtime, actor_id)["mana"], 16.0)
            self.assertEqual(
                [relation.target for relation in _locations(runtime, actor_id)],
                [AREA_B],
            )
            values = submitted.action.effect_outcomes[0]["values"]
            self.assertEqual(
                set(values),
                {
                    "origin_area_id",
                    "destination_area_id",
                    "old_relation_id",
                    "new_relation_id",
                    "via_relation_ids",
                },
            )
            self.assertEqual(values["origin_area_id"], AREA_A)
            self.assertEqual(values["destination_area_id"], AREA_B)
            self.assertEqual(values["via_relation_ids"], ["bare_ab"])
            changed = [
                delta for delta in submitted.action.event_result.trace.proposals
                if hasattr(delta, "op")
            ]
            ops = [
                item.op
                for item in submitted.action.event_result.trace.proposals
                if item.op in {"create_relation", "delete_relation"}
            ]
            self.assertEqual(ops.count("delete_relation"), 1)
            self.assertEqual(ops.count("create_relation"), 1)
            self.assertTrue(
                any(
                    law.law_id.endswith(".delete")
                    for event in submitted.action.event_result.trace.events
                    for law in event.event_law_matches
                )
            )
            self.assertTrue(
                any(
                    law.law_id.endswith(".create")
                    for event in submitted.action.event_result.trace.events
                    for law in event.event_law_matches
                )
            )
        self.assertEqual(_budget(runtime)["spent_ticks"], 2)
        self.assertEqual(_budget(runtime)["remaining_ticks"], 18)
        self.assertEqual(
            runtime.session.state.entities[AREA_A].components[
                "pmw_gameplay_dynamics"
            ]["fields"]["humidity"]["value"],
            _field_state(runtime, AREA_A)["value"],
        )
        advance_world_tick(runtime.session)
        self.assertLess(_field_state(runtime, AREA_A)["value"], 0.8)
        self.assertEqual(_budget(runtime)["spent_ticks"], 2)

    def test_scenario1_persistent_area_change_keeps_evolving_after_move(self):
        area_skill = _skill(
            _skill_document(
                "move_area_pulse",
                [_dynamics_effect()],
                mana=5.0,
                budget=8.0,
            )
        )
        move = _move_skill()
        runtime, _ = _formal_runtime((area_skill, move))
        first = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("area_pulse", PLAYER, area_skill.id),
        )
        self.assertEqual(first.time.duration, 1)
        initial = _field_state(runtime, AREA_A)["value"]
        self.assertAlmostEqual(initial, 0.44, delta=1e-12)
        moved = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("leave_a", PLAYER, move.id, None, AREA_B),
        )
        self.assertEqual(moved.time.duration, 1)
        self.assertEqual(
            [relation.target for relation in _locations(runtime, PLAYER)],
            [AREA_B],
        )
        moved_value = _field_state(runtime, AREA_A)["value"]
        self.assertAlmostEqual(
            moved_value, initial + 0.4 * (0.8 - initial), delta=1e-12
        )
        values = [moved_value]
        for _ in range(3):
            advance_world_tick(runtime.session)
            values.append(_field_state(runtime, AREA_A)["value"])
        self.assertEqual(values, sorted(values))
        self.assertGreater(values[-1], values[0])
        self.assertAlmostEqual(
            values[1], values[0] + 0.4 * (0.8 - values[0]), delta=1e-12
        )
        self.assertEqual(_actor_state(runtime, PLAYER)["mana"], 11.0)
        self.assertEqual(_budget(runtime)["spent_ticks"], 2)

    def test_non_primary_and_missing_target_leave_ledger_unchanged(self):
        skill = _move_skill()
        runtime, _ = _formal_runtime((skill,))
        before = _snapshot(runtime)
        cases = (
            (ActionRequest("ledger_missing", PLAYER, skill.id), {}),
            (
                ActionRequest(
                    "ledger_hook", PLAYER, skill.id, None, AREA_B
                ),
                {
                    "execution_kind": "hook",
                    "hook_context": {"hook_id": "ledger_hook"},
                },
            ),
        )
        for request, options in cases:
            with self.subTest(request=request.request_id):
                with self.assertRaises(GameplayContractError):
                    _resolve_action(
                        runtime.session,
                        runtime.action_registry,
                        request,
                        **options,
                    )
                self.assertEqual(_snapshot(runtime), before)
                self.assertEqual(_budget(runtime)["spent_ticks"], 0)
                self.assertEqual(_budget(runtime)["remaining_ticks"], 20)
                self.assertEqual(_actor_state(runtime, PLAYER)["mana"], 20.0)
                self.assertEqual(
                    runtime.session.state.scheduled_events, []
                )

    def test_c3_paid_overlay_blocks_then_expires_and_parallel_link_opens(self):
        profile = _profile(PLAYER)
        controller = RelationController((profile,))
        control = _control_skill()
        move = _move_skill()
        runtime, _ = _formal_runtime(
            (control, move),
            world=_control_world(profile=profile, base_enabled=True),
            relation_controller=controller,
        )
        disable = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("disable_link", PLAYER, control.id),
        )
        self.assertEqual(disable.time.duration, 1)
        component = runtime.session.state.relations[
            LINK_ID
        ].components[RELATION_COMPONENT]
        self.assertIs(component["effective_enabled"], False)
        _assert_rejected(
            self,
            runtime,
            ActionRequest("blocked", PLAYER, move.id, None, AREA_B),
            "disabled",
        )
        for _ in range(2):
            advance_world_tick(runtime.session)
        component = runtime.session.state.relations[
            LINK_ID
        ].components[RELATION_COMPONENT]
        self.assertIs(component["effective_enabled"], True)
        moved = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("after_expiry", PLAYER, move.id, None, AREA_B),
        )
        self.assertEqual(moved.time.duration, 1)
        self.assertEqual(
            [relation.target for relation in _locations(runtime, PLAYER)],
            [AREA_B],
        )

        parallel_profile = _profile(NPC)
        parallel_controller = RelationController((parallel_profile,))
        parallel_runtime, _ = _formal_runtime(
            (control, move),
            world=_control_world(
                profile=parallel_profile,
                base_enabled=True,
                extra_links=(("enabled_ab", {
                    RELATION_COMPONENT: {"effective_enabled": True},
                }),),
            ),
            relation_controller=parallel_controller,
        )
        disabled = submit_timed_primary_action(
            parallel_runtime.session,
            parallel_runtime.action_registry,
            ActionRequest("npc_disable", NPC, control.id),
        )
        self.assertEqual(disabled.time.duration, 1)
        moved = submit_timed_primary_action(
            parallel_runtime.session,
            parallel_runtime.action_registry,
            ActionRequest("npc_parallel", NPC, move.id, None, AREA_B),
        )
        self.assertEqual(moved.time.duration, 1)
        self.assertEqual(
            [relation.target for relation in _locations(parallel_runtime, NPC)],
            [AREA_B],
        )

    def test_rejection_matrix_is_atomic_and_schedule_stable(self):
        skill = _move_skill()
        runtime, _ = _formal_runtime((skill,))
        cases = (
            (ActionRequest("unknown", PLAYER, skill.id, None, AREA_C),
             "not an adjacent"),
            (ActionRequest("same", PLAYER, skill.id, None, AREA_A),
             "not an adjacent"),
            (ActionRequest("missing", PLAYER, skill.id),
             "requires target_area_id"),
            (ActionRequest("wrong_action", PLAYER, "basic_wait", None, AREA_B),
             "target_area_id"),
        )
        for request, pattern in cases:
            with self.subTest(request=request.request_id):
                _assert_rejected(self, runtime, request, pattern)
        colliding, _ = _formal_runtime(
            (skill,),
            world=_move_world(collision=True),
        )
        _assert_rejected(
            self,
            colliding,
            ActionRequest("collision", PLAYER, skill.id, None, AREA_B),
            "collides",
        )
        duplicate, _ = _formal_runtime(
            (skill,),
            world=_move_world(extra_located=2),
        )
        _assert_rejected(
            self,
            duplicate,
            ActionRequest("two_locations", PLAYER, skill.id, None, AREA_B),
            "exactly one",
        )
        hook_before = _snapshot(runtime)
        with self.assertRaisesRegex(GameplayContractError, "primary"):
            _resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("hook_move", PLAYER, skill.id, None, AREA_B),
                execution_kind="hook",
                hook_context={"hook_id": "move_hook"},
            )
        self.assertEqual(_snapshot(runtime), hook_before)

    def test_runtime_rejects_malformed_link_and_non_area_destination(self):
        skill = _move_skill()
        malformed, _ = _formal_runtime(
            (skill,),
            world=_move_world(links=(("bad_link_component", "bad"),)),
        )
        _assert_rejected(
            self,
            malformed,
            ActionRequest("malformed", PLAYER, skill.id, None, AREA_B),
            "malformed",
        )
        bad_area, _ = _formal_runtime((skill,))
        bad_area.session.state.entities[AREA_B].components.pop(
            "pmw_gameplay_area"
        )
        bad_area.session.runtime.revalidate()
        _assert_rejected(
            self,
            bad_area,
            ActionRequest("non_area", PLAYER, skill.id, None, AREA_B),
            "not an Area|adjacent",
        )

    def test_checkpoint_rebuild_preserves_hashes_and_moved_location(self):
        skill = _move_skill()
        runtime, compiled = _formal_runtime((skill,))
        moved = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("checkpoint_move", PLAYER, skill.id, None, AREA_B),
        )
        action_hash = runtime.action_registry.actions[skill.id].canonical_hash
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as directory:
            path = Path(directory) / "move_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
        self.assertEqual(
            restored.blueprints[(skill.id, 1)].canonical_hash,
            skill.canonical_hash,
        )
        self.assertEqual(
            restored.action_registry.actions[skill.id].canonical_hash,
            action_hash,
        )
        self.assertEqual(
            [relation.target for relation in _locations(restored, PLAYER)],
            [AREA_B],
        )
        self.assertEqual(
            restored.session.state.to_dict(),
            runtime.session.state.to_dict(),
        )
        self.assertEqual(moved.action.definition.canonical_hash, action_hash)


if __name__ == "__main__":
    unittest.main()
