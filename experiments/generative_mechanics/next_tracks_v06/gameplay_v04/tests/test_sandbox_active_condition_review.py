"""Independent C4.3 active top-level condition review; not an owner oracle."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import is_dataclass, asdict
import json
from pathlib import Path
import tempfile
import unittest

from pmw import Relation

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    _resolve_action,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.relations import (
    RELATION_COMPONENT,
    RelationController,
    RelationLimits,
    RelationProfile,
    instantiate_relation,
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
REVIEW_TMP = PROJECT_ROOT / "docs" / "agent_bootstrap" / "evidence" / "test_tmp"
HISTORICAL_BASIC_PATH = (
    PROJECT_ROOT
    / "docs"
    / "agent_bootstrap"
    / "evidence"
    / "c4_active_main_historical_basic_hashes.json"
)
PLAYER = "c43_player"
NPC = "c43_npc"
AREA = "c43_area"
REMOTE = "c43_remote"
MATERIAL_ID = "c43_review_material"
PROFILE_ID = "c43_supply_profile"
RELATION_ID = "c43_supply_link"
SOURCE = "c43_power_source"
SINK = "c43_power_sink"
SOURCE_MARKER = "pmw_gameplay_c43_source"
SINK_MARKER = "pmw_gameplay_c43_sink"
SKILL_ID = "c43_shared_gate"
ACTOR_COMPONENT = "pmw_gameplay_actor"


def _material(*, budget=20.0):
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "c43_review_power",
            "effect_kinds": [
                "relation_modifier", "heal", "shield", "damage",
            ],
            "selectors": ["self", "target_actor", "current_area"],
            "budget_points": budget,
        }],
    })


def _acting_condition(key="mana", comparator="gte", value=5, subject="self"):
    return {
        "resource": {
            "subject": subject,
            "key": key,
            "comparator": comparator,
            "value": value,
        },
    }


def _area(instance_id=AREA):
    return instantiate_area(
        parse_area_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "area_blueprint",
            "id": "c43_review_area_blueprint",
            "fields": [{
                "id": "heat",
                "domain": {"min": 0.0, "max": 10.0},
                "initial": 3.0,
                "target": 3.0,
                "rate": 0.0,
                "curve": "none",
                "max_persistent_patches": 1,
                "max_temporary_modifiers": 1,
            }],
        }),
        instance_id,
    )


def _make_actor(actor_id, *, controller, mana=5.0, hp=40.0, traits=()):
    return instantiate_actor(
        parse_actor_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "actor_blueprint",
            "id": "c43_review_actor_blueprint",
            "hp": {"max": 50.0, "initial": hp},
            "mana": {"max": 30.0, "initial": mana, "dynamics": None},
            "attributes": {
                "power": 4.0,
                "control": 4.0,
                "resilience": 4.0,
                "agility": 4.0,
            },
            "traits": list(traits),
        }),
        actor_id,
        controller=controller,
    )


def _skill_document(
    *,
    skill_id=SKILL_ID,
    condition=None,
    effect=None,
    cost=None,
    scope=None,
    duration=None,
    version=1,
):
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": skill_id,
        "version": version,
        "trigger": "on_use",
        "condition": _acting_condition() if condition is None else condition,
        "duration": duration,
        "cost": {"duration": 1, "mana": 4.0} if cost is None else cost,
        "scope": {
            "selectors": ["self", "target_actor", "current_area"],
            "relation_types": ["supplies_power", "located_in"],
        } if scope is None else scope,
        "effects": [{
            "id": "link_change",
            "kind": "relation_modifier",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "relation_profile_id": PROFILE_ID,
            "relation_enabled": False,
            "duration": 3,
        }] if effect is None else [effect],
        "budget": {"limit": 12.0},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }


def _self_heal_effect(effect_id="self_heal", *, amount=2.0, condition=None):
    effect = {
        "id": effect_id,
        "kind": "heal",
        "target": {"kind": "self"},
        "commitment": "required",
        "amount": amount,
    }
    if condition is not None:
        effect["condition"] = condition
    return effect


def _parse_skill(raw):
    return parse_skill_blueprint(
        raw,
        basic_registry().statuses,
        material_authority((_material(),)),
    )


def _profile(*, owner=PLAYER, relation_id=RELATION_ID, area_id=AREA,
             profile_id=PROFILE_ID):
    return RelationProfile(
        profile_id,
        relation_id,
        "supplies_power",
        SOURCE,
        SINK,
        owner,
        area_id,
        (SOURCE_MARKER,),
        (SINK_MARKER,),
        8,
    )


def _marked(entity_id, marker):
    from pmw import Entity
    return Entity(entity_id, "c43_review_endpoint", components={marker: {}})


def _availability_law(profile, suffix):
    return {
        "id": f"pmw.v04.review.c43.availability.{suffix}",
        "mode": "state",
        "priority": 100,
        "bindings": {
            "link": {
                "kind": "relation",
                "type": profile.relation_type,
                "source": "$source",
                "target": "$target",
                "requires": [RELATION_COMPONENT],
            },
            "source": {"kind": "entity", "requires": [SOURCE_MARKER]},
            "target": {"kind": "entity", "requires": [SINK_MARKER]},
            "area": {"kind": "entity", "requires": ["pmw_gameplay_area"]},
        },
        "when": {"all": [
            {"ref": "$link.id", "eq": profile.relation_id},
            {"ref": "$source.id", "eq": profile.source_entity_id},
            {"ref": "$target.id", "eq": profile.target_entity_id},
            {"ref": "$area.id", "eq": profile.area_id},
            {
                "ref": f"$area.pmw_gameplay_c43_availability.{suffix}.enabled",
                "neq": f"$link.{RELATION_COMPONENT}.effective_enabled",
            },
        ]},
        "effects": [{
            "op": "set",
            "target": f"$area.pmw_gameplay_c43_availability.{suffix}.enabled",
            "value": f"$link.{RELATION_COMPONENT}.effective_enabled",
        }],
    }


def _world(profile, *, player=5.0, npc=9.0):
    areas = {AREA: _area(AREA), REMOTE: _area(REMOTE)}
    actors = {
        PLAYER: _make_actor(PLAYER, controller="human", mana=player, hp=40.0),
        NPC: _make_actor(NPC, controller="ai", mana=npc, hp=40.0),
    }
    world = build_gameplay_world(
        "c43_review_world",
        areas=areas.values(),
        actors=actors.values(),
        placements=((PLAYER, AREA), (NPC, AREA)),
    )
    world.entities[SOURCE] = _marked(SOURCE, SOURCE_MARKER)
    world.entities[SINK] = _marked(SINK, SINK_MARKER)
    world.relations[profile.relation_id] = instantiate_relation(profile)
    for endpoint, area_id in ((SOURCE, AREA), (SINK, AREA)):
        world.relations[f"located:{endpoint}"] = Relation(
            f"located:{endpoint}", "located_in", endpoint, area_id
        )
    world.entities[AREA].components["pmw_gameplay_c43_availability"] = {
        "c43_supply_link": {"enabled": True},
    }
    world.entities["pmw:v04:clock"] = clock_entity()
    world = initialize_time_budget(world, 20)
    return world


def _fixture(*, skills, profiles=(), player=5.0, npc=9.0):
    controller = RelationController(tuple(profiles), RelationLimits())
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        relation_controller=controller,
    )
    content = make_content(
        base,
        skills=tuple(skills),
        material_ids=(MATERIAL_ID,),
    )
    profile = profiles[0] if profiles else _profile()
    world = initialize_content_world(
        _world(profile, player=player, npc=npc),
        content,
    )
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    return {
        "runtime": runtime,
        "session": runtime.session,
        "registry": runtime.action_registry,
        "compiled": compiled,
        "controller": controller,
    }


def _equip(runtime, actor_id, skill, slot=0):
    change_loadout(
        runtime.session,
        runtime.manifest,
        actor_id=actor_id,
        operation="equip_active",
        skill=skill_ref(skill),
        slot=slot,
    )


def _equip_both(runtime, skill):
    _equip(runtime, PLAYER, skill)
    _equip(runtime, NPC, skill)


def _json_value(value):
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return deepcopy(value)


def _snapshot(session):
    return {
        "world": _json_value(session.state.to_dict()),
        "stats": _json_value(session.runtime.stats),
        "revision": session.runtime.revision,
        "object_revision": session.runtime.object_revision,
        "state_closure_known": session.runtime.state_closure_known,
        "schedule": _json_value(session.state.scheduled_events),
        "profiles": _json_value(session.profiles),
    }


def _persistent_snapshot(session):
    snapshot = _snapshot(session)
    return {
        "world": snapshot["world"],
        "schedule": snapshot["schedule"],
        "profiles": snapshot["profiles"],
    }


def _actor_component(session, actor_id):
    return session.state.entities[actor_id].components[ACTOR_COMPONENT]


def _budget(session):
    return session.state.entities["pmw:v04:clock"].components[
        TIME_BUDGET_COMPONENT
    ]


def _relation_component(session):
    return session.state.relations[RELATION_ID].components[RELATION_COMPONENT]


def _cast(fixture, request_id, actor_id):
    return submit_timed_primary_action(
        fixture["session"],
        fixture["registry"],
        ActionRequest(request_id, actor_id, SKILL_ID),
    )


def _resolve(fixture, request_id, actor_id, action_id, target_actor_id=None):
    return resolve_action(
        fixture["session"],
        fixture["registry"],
        ActionRequest(request_id, actor_id, action_id, target_actor_id),
    )


class PreCostSharedSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        REVIEW_TMP.mkdir(parents=True, exist_ok=True)

    def test_one_parsed_skill_true_and_false_pre_cost_on_same_definition(self):
        raw = _skill_document(
            condition=_acting_condition(),
            effect=_self_heal_effect(),
        )
        skill = _parse_skill(raw)
        raw_before = deepcopy(raw)
        profile = _profile()
        fixture = _fixture(skills=(skill,), profiles=(profile,), npc=0.0)
        _equip_both(fixture["runtime"], skill)
        self.assertEqual(raw, raw_before)
        expected_ref = skill_ref(skill).to_dict()
        for actor_id in (PLAYER, NPC):
            self.assertEqual(
                _actor_component(fixture["session"], actor_id)
                ["active_equipped"][0],
                expected_ref,
            )
        self.assertEqual(
            fixture["runtime"].manifest.entries[0].canonical_hash,
            skill.canonical_hash,
        )
        self.assertEqual(
            fixture["registry"].actions[SKILL_ID].canonical_hash,
            skill.action.canonical_hash,
        )
        player_before = deepcopy(_actor_component(fixture["session"], PLAYER))
        npc_before = deepcopy(_actor_component(fixture["session"], NPC))
        budget_before = deepcopy(_budget(fixture["session"]))
        before_snapshot = deepcopy(_snapshot(fixture["session"]))

        player_result = _cast(fixture, "c43_player_true", PLAYER)
        self.assertEqual(
            (player_before["mana"], _actor_component(fixture["session"], PLAYER)["mana"]),
            (5.0, 1.0),
        )
        self.assertEqual(
            (player_result.action.cost.mana, player_result.action.cost.duration),
            (4.0, 1),
        )
        self.assertEqual(
            (
                player_result.time.before_remaining,
                player_result.time.after_remaining,
                _budget(fixture["session"])["spent_ticks"],
            ),
            (20, 19, 1),
        )
        before_false = _snapshot(fixture["session"])
        before_false_actors = {
            actor_id: deepcopy(_actor_component(fixture["session"], actor_id))
            for actor_id in (PLAYER, NPC)
        }
        before_false_budget = deepcopy(_budget(fixture["session"]))
        before_false_schedule = deepcopy(fixture["session"].state.scheduled_events)
        with self.assertRaises(GameplayContractError) as caught:
            _cast(fixture, "c43_npc_false", NPC)
        self.assertIn("condition", str(caught.exception))
        self.assertNotIn("mana", str(caught.exception))
        self.assertEqual(_snapshot(fixture["session"]), before_false)
        self.assertEqual(
            {
                actor_id: _actor_component(fixture["session"], actor_id)
                for actor_id in (PLAYER, NPC)
            },
            before_false_actors,
        )
        self.assertEqual(_budget(fixture["session"]), before_false_budget)
        self.assertEqual(
            fixture["session"].state.scheduled_events,
            before_false_schedule,
        )
        self.assertEqual(
            (
                player_result.time.before_remaining,
                player_result.time.after_remaining,
                budget_before["spent_ticks"],
                _budget(fixture["session"])["spent_ticks"],
            ),
            (20, 19, 0, 1),
        )
        self.assertNotEqual(
            before_snapshot["world"]["time"],
            _snapshot(fixture["session"])["world"]["time"],
        )
        self.assertEqual(npc_before["mana"], 0.0)

    def test_current_state_reenables_without_registry_rebuild(self):
        skill = _parse_skill(_skill_document(
            condition=_acting_condition("mana", "gte", 5),
            effect=_self_heal_effect(),
        ))
        profile = _profile()
        fixture = _fixture(skills=(skill,), profiles=(profile,), npc=0.0)
        _equip_both(fixture["runtime"], skill)
        _cast(fixture, "c43_hp_true", PLAYER)
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["mana"],
            1.0,
        )
        before_false = _snapshot(fixture["session"])
        with self.assertRaisesRegex(
            GameplayContractError,
            "action condition is not satisfied",
        ):
            _cast(fixture, "c43_hp_false_player", PLAYER)
        self.assertEqual(_snapshot(fixture["session"]), before_false)
        _resolve(fixture, "c43_wait", PLAYER, "basic_wait")
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["mana"],
            6.0,
        )
        accepted = _cast(fixture, "c43_hp_true_after_wait", PLAYER)
        self.assertEqual(accepted.action.cost.mana, 4.0)
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["mana"],
            2.0,
        )
        self.assertEqual(
            fixture["runtime"].manifest.entries[0].canonical_hash,
            skill.canonical_hash,
        )
        self.assertEqual(
            fixture["registry"].actions[SKILL_ID].canonical_hash,
            skill.action.canonical_hash,
        )


class TypedBoundaryTests(unittest.TestCase):
    def test_condition_reads_current_area_and_target_bounds(self):
        cases = (
            (
                "field",
                {"field": {
                    "subject": "current_area",
                    "key": "heat",
                    "comparator": "gte",
                    "value": 3.0,
                }},
                PLAYER,
                True,
            ),
            (
                "target",
                _acting_condition("hp", "gte", 40, "target_actor"),
                NPC,
                True,
            ),
            (
                "out_of_range",
                _acting_condition("mana", "gte", 200, "self"),
                PLAYER,
                False,
            ),
        )
        profile = _profile()
        for label, condition, actor_id, should_accept in cases:
            with self.subTest(label=label):
                skill = _parse_skill(_skill_document(
                    skill_id=f"c43_{label}",
                    condition=condition,
                    effect=_self_heal_effect(f"c43_{label}_heal"),
                ))
                fixture = _fixture(
                    skills=(skill,),
                    profiles=(profile,),
                    npc=5.0,
                )
                _equip(fixture["runtime"], actor_id, skill)
                before = _snapshot(fixture["session"])
                if should_accept:
                    result = submit_timed_primary_action(
                        fixture["session"],
                        fixture["registry"],
                        ActionRequest(
                            f"c43_{label}_request",
                            actor_id,
                            skill.id,
                            NPC if actor_id != NPC else PLAYER,
                        ),
                    )
                    self.assertIsNotNone(result.action.event_result)
                    self.assertEqual(fixture["session"].state.sim_time, 1.0)
                else:
                    with self.assertRaisesRegex(
                        GameplayContractError,
                        "action condition is not satisfied",
                    ):
                        submit_timed_primary_action(
                            fixture["session"],
                            fixture["registry"],
                            ActionRequest(
                                f"c43_{label}_request",
                                actor_id,
                                skill.id,
                                NPC if actor_id != NPC else PLAYER,
                            ),
                        )
                    self.assertEqual(_snapshot(fixture["session"]), before)

    def test_malformed_typed_conditions_reject_without_mutation(self):
        malformed = (
            {
                "resource": {
                    "subject": "remote_actor",
                    "key": "mana",
                    "comparator": "gte",
                    "value": 1,
                },
            },
            {
                "resource": {
                    "subject": "self",
                    "key": "secret",
                    "comparator": "gte",
                    "value": 1,
                },
            },
            {
                "resource": {
                    "subject": "self",
                    "key": "mana",
                    "comparator": "approx",
                    "value": 1,
                },
            },
            {
                "resource": {
                    "subject": "self",
                    "key": "mana",
                    "comparator": "gte",
                    "value": float("inf"),
                },
            },
            {
                "resource": {
                    "subject": "self",
                    "key": "mana",
                    "comparator": "gte",
                    "value": 1,
                    "prefix": "forbidden",
                },
            },
        )
        for index, condition in enumerate(malformed):
            with self.subTest(index=index):
                raw = _skill_document(condition=condition)
                raw_before = deepcopy(raw)
                with self.assertRaises(GameplayContractError):
                    _parse_skill(raw)
                self.assertEqual(raw, raw_before)


def _historical_basic_hashes():
    document = json.loads(HISTORICAL_BASIC_PATH.read_text(encoding="utf-8"))
    self_hashes = document["expected_basic_action_hashes"]
    return self_hashes


class IdentityAndTimingTests(unittest.TestCase):
    def test_basic_identity_oracle_and_conditional_counterfeit_rejected(self):
        expected = _historical_basic_hashes()
        current = basic_registry().actions
        self.assertEqual(
            {key: current[key].canonical_hash for key in expected},
            expected,
        )
        absent = deepcopy(basic_registry_document())
        null = deepcopy(basic_registry_document())
        for doc in (absent, null):
            for row in doc["actions"]:
                if row["id"] in expected:
                    row.pop("condition", None)
        for row in null["actions"]:
            if row["id"] in expected:
                row["condition"] = None
        absent_candidate = deepcopy(absent)
        null_candidate = deepcopy(null)
        absent_registry = ActionRegistry.parse(absent)
        null_registry = ActionRegistry.parse(null)
        self.assertEqual(absent, absent_candidate)
        self.assertEqual(null, null_candidate)
        self.assertEqual(
            {
                key: item.canonical_hash
                for key, item in absent_registry.actions.items()
                if key in expected
            },
            expected,
        )
        self.assertEqual(
            {
                key: item.canonical_hash
                for key, item in null_registry.actions.items()
                if key in expected
            },
            expected,
        )

        forged = deepcopy(basic_registry_document())
        basic_attack = next(
            row for row in forged["actions"] if row["id"] == "basic_attack"
        )
        basic_attack["condition"] = _acting_condition()
        forged_candidate = deepcopy(forged)
        forged_registry = ActionRegistry.parse(forged)
        self.assertNotEqual(
            forged_registry.actions["basic_attack"].canonical_hash,
            expected["basic_attack"],
        )
        self.assertEqual(forged, forged_candidate)
        profile = _profile()
        content = make_content(
            ActionRegistry(
                forged_registry.actions.values(),
                forged_registry.statuses.values(),
            ),
            skills=(),
            material_ids=(MATERIAL_ID,),
        )
        world = initialize_content_world(_world(profile), content)
        compiled = compile_content(content)
        runtime = MechanismRegistryRuntime.from_compiled_content(
            build_content_session(world, compiled),
            compiled,
        )
        before = _snapshot(runtime.session)
        with self.assertRaises(GameplayContractError):
            resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("c43_forged_basic", PLAYER, "basic_attack", NPC),
            )
        self.assertEqual(_snapshot(runtime.session), before)

    def test_cost_modifier_timing_and_effect_condition_remain_distinct(self):
        raw = _skill_document(
            condition=_acting_condition(),
            effect={
                "id": "self_heal",
                "kind": "heal",
                "target": {"kind": "self"},
                "commitment": "conditional",
                "amount": 2.0,
                "condition": _acting_condition("mana", "gte", 5),
            },
        )
        raw["effects"] = [raw["effects"][0]]
        # Use a normal Skill action first, then a direct trusted Action document
        # to prove quote timing is separate from post-cost Effect predicates.
        skill = _parse_skill(raw)
        self.assertEqual(skill.action.cost.mana, 4.0)
        direct = parse_action_definition(
            {
                "id": "c43_cost_timing",
                "version": 1,
                "action_type": "skill",
                "condition": _acting_condition(),
                "cost": {"duration": 1, "mana": 4.0},
                "scope": {"selectors": ["self"], "relation_types": []},
                "effects": [raw["effects"][0]],
                "cost_modifiers": [{
                    "id": "c43_quote_modifier",
                    "condition": _acting_condition("mana", "gte", 5),
                    "duration_add": 1,
                    "mana_add": 1.0,
                }],
            },
            basic_registry().statuses,
        )
        self.assertIsNotNone(direct)
        profile = _profile()
        controller = RelationController((profile,), RelationLimits())
        direct_base = ActionRegistry(
            (*basic_registry().actions.values(), direct),
            basic_registry().statuses.values(),
            relation_controller=controller,
        )
        direct_content = make_content(
            direct_base,
            skills=(),
            material_ids=(MATERIAL_ID,),
        )
        direct_world = initialize_content_world(_world(profile), direct_content)
        direct_compiled = compile_content(direct_content)
        direct_session = build_content_session(direct_world, direct_compiled)
        direct_runtime = MechanismRegistryRuntime.from_compiled_content(
            direct_session,
            direct_compiled,
        )
        outcome = _resolve_action(
            direct_runtime.session,
            direct_runtime.action_registry,
            ActionRequest("c43_cost_timing_request", PLAYER, direct.id),
        )
        self.assertEqual(
            (outcome.cost.mana, outcome.cost.duration),
            (5.0, 2),
        )
        self.assertEqual(
            _actor_component(direct_runtime.session, PLAYER)["mana"],
            0.0,
        )
        self.assertEqual(
            (outcome.effect_outcomes[0]["status"],
             _actor_component(direct_runtime.session, PLAYER)["hp"]),
            ("skipped", 40.0),
        )


class ContinuityTests(unittest.TestCase):
    def test_checkpoint_continuation_preserves_condition_and_cast(self):
        skill = _parse_skill(_skill_document(
            condition=_acting_condition(),
            effect=_self_heal_effect(),
        ))
        self.assertEqual(
            skill.action.condition,
            skill.condition,
        )
        profile = _profile()
        fixture = _fixture(skills=(skill,), profiles=(profile,), npc=0.0)
        _equip_both(fixture["runtime"], skill)
        before = _persistent_snapshot(fixture["session"])
        with tempfile.TemporaryDirectory(dir=REVIEW_TMP) as directory:
            path = Path(directory) / "c43-active-condition.json"
            save_registry_checkpoint(path, fixture["runtime"])
            restored = load_registry_checkpoint(path, fixture["compiled"])
        self.assertEqual(_persistent_snapshot(restored.session),
                         before)
        self.assertEqual(
            restored.blueprints[(SKILL_ID, 1)].canonical_hash,
            skill.canonical_hash,
        )
        self.assertEqual(
            restored.action_registry.actions[SKILL_ID].canonical_hash,
            skill.action.canonical_hash,
        )
        self.assertEqual(
            restored.action_registry.actions[SKILL_ID].condition,
            skill.action.condition,
        )
        self.assertEqual(
            skill.action.condition.key,
            "mana",
        )
        restored_fixture = {
            "session": restored.session,
            "registry": restored.action_registry,
        }
        accepted = _cast(restored_fixture, "c43_after_load_true", PLAYER)
        self.assertEqual(accepted.action.cost.mana, 4.0)
        self.assertEqual(
            _actor_component(restored.session, PLAYER)["mana"],
            1.0,
        )
        self.assertEqual(
            _actor_component(restored.session, PLAYER)["hp"],
            42.0,
        )
        after_accept = _snapshot(restored.session)
        with self.assertRaisesRegex(
            GameplayContractError,
            "action condition is not satisfied",
        ):
            _cast(restored_fixture, "c43_after_load_false", PLAYER)
        self.assertEqual(_snapshot(restored.session), after_accept)
        self.assertEqual(restored.session.state.sim_time, 1.0)

    def test_c42_passive_dispatch_continues_with_c43_condition_skill(self):
        active = _parse_skill(_skill_document(effect=_self_heal_effect()))
        fired_raw = {
            "protocol": "pmw-gameplay-v0.4",
            "kind": "passive_blueprint",
            "id": "c43_passive_shield_true",
            "version": 1,
            "trigger": "damage_resolved",
            "condition": None,
            "duration": None,
            "cost": {"duration": 1, "mana": 0.0},
            "scope": {
                "selectors": ["self", "target_actor"],
                "relation_types": [],
            },
            "effects": [{
                "id": "passive_shield",
                "kind": "shield",
                "target": {"kind": "self"},
                "commitment": "required",
                "amount": 7.0,
            }],
            "budget": {"limit": 8.0},
            "max_firings_per_root": 1,
            "material_ids": [MATERIAL_ID],
        }
        fired_passive = parse_skill_blueprint(
            fired_raw,
            basic_registry().statuses,
            material_authority((_material(),)),
        )
        skipped_raw = deepcopy(fired_raw)
        skipped_raw["id"] = "c43_passive_shield_false"
        skipped_raw["condition"] = _acting_condition("mana", "gte", 6)
        skipped_passive = parse_skill_blueprint(
            skipped_raw,
            basic_registry().statuses,
            material_authority((_material(),)),
        )
        profile = _profile()
        fixture = _fixture(
            skills=(active, fired_passive, skipped_passive),
            profiles=(profile,),
            player=5.0,
            npc=5.0,
        )
        _equip_both(fixture["runtime"], active)
        change_loadout(
            fixture["session"],
            fixture["runtime"].manifest,
            actor_id=PLAYER,
            operation="equip_passive",
            skill=skill_ref(fired_passive),
            slot=0,
        )
        change_loadout(
            fixture["session"],
            fixture["runtime"].manifest,
            actor_id=PLAYER,
            operation="equip_passive",
            skill=skill_ref(skipped_passive),
            slot=2,
        )
        fired_hash = fired_passive.action.canonical_hash
        skipped_hash = skipped_passive.action.canonical_hash
        before_passive = _snapshot(fixture["session"])
        npc_before = deepcopy(_actor_component(fixture["session"], NPC))
        player_before = deepcopy(_actor_component(fixture["session"], PLAYER))
        result = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("c43_passive_root", NPC, "basic_attack", PLAYER),
        )
        fired = tuple(row for row in result.auto_hooks if row.status == "fired")
        skipped = tuple(row for row in result.auto_hooks if row.status == "skipped")
        self.assertGreaterEqual(len(fired), 1)
        self.assertEqual(len(skipped), 1)
        self.assertIn("condition", skipped[0].reason)
        self.assertIsNone(skipped[0].outcome)
        self.assertEqual(
            fixture["registry"].actions[fired_passive.id].canonical_hash,
            fired_hash,
        )
        self.assertEqual(
            fixture["registry"].actions[skipped_passive.id].canonical_hash,
            skipped_hash,
        )
        self.assertEqual(fired_passive.action.condition.kind, "always")
        self.assertEqual(skipped_passive.action.condition.kind, "always")
        self.assertNotEqual(active.action.condition.kind, "always")
        self.assertEqual(_actor_component(fixture["session"], NPC)["mana"],
                         npc_before["mana"])
        self.assertEqual(_actor_component(fixture["session"], PLAYER)["mana"],
                         player_before["mana"])
        self.assertEqual(_actor_component(fixture["session"], PLAYER)["shield"],
                         7.0)
        self.assertNotEqual(_snapshot(fixture["session"]), before_passive)


if __name__ == "__main__":
    unittest.main()
