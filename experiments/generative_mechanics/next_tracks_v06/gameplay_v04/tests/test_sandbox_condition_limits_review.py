from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from pmw import Relation

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
    ConditionLimits,
    evaluate_condition,
    parse_condition,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.hooks import (
    parse_hook,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.processes import (
    PROCESS_COMPONENT,
    ConversionPort,
    ProcessController,
    ProcessLimits,
    ProcessProfile,
    ProcessTemplate,
    StockBinding,
    StockRef,
    instantiate_process,
    stock_entity,
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
PLAYER_ID = "player_actor"
NPC_ID = "npc_actor"
AREA_ID = "condition_area"
SKILL_ID = "condition_skill"
TEMPLATE_ID = "condition_process"

# Captured from baseline commit d613cc9 (pre-repair conditions.py SHA256
# e7fa4a27596c3709fd9f159b6332e0e270d2827f2ea721a0506d5f71572b5748).
ACCEPTED_CANONICAL_HASHES = {
    "null": "ecd9a0d56bcfbd07e21f3641d46766954e1598c61a734422040c0552b7197021",
    "all": "a11c2d230a5009ed30a774900c6dd992a041be0f3991ca5cba1ce6b7931ba126",
    "any": "4bb401d3f6de6d9e96eaab821091a86780b3d876fc64aa1e9558e554033a80dd",
    "not": "38a96c7c93f51c6b181cabe12cdf8d82101a5cd28608f11fa86cf1dcc8400f90",
    "mixed": "d780ea0cd0073d99668ab714149569aba2a68b1e4660770ad86e2c3453e3df39",
}


def _attribute(
    key: str = "control",
    value: float = 4,
    *,
    comparator: str = "gte",
    subject: str = "self",
) -> dict:
    return {
        "attribute": {
            "subject": subject,
            "key": key,
            "comparator": comparator,
            "value": value,
        }
    }


def _nested_not(depth: int, leaf: dict | None = None) -> dict:
    raw = leaf or _attribute()
    for _ in range(depth - 1):
        raw = {"not": raw}
    return raw


def _nested_all(depth: int) -> dict:
    raw = _attribute()
    for _ in range(depth - 1):
        raw = {"all": [raw]}
    return raw


def _nested_any(depth: int) -> dict:
    raw = _attribute()
    for _ in range(depth - 1):
        raw = {"any": [raw]}
    return raw


def _mixed(depth: int) -> dict:
    raw = _attribute()
    operators = ("all", "any", "not")
    for index in range(depth - 1):
        operator = operators[index % 3]
        raw = {operator: raw if operator == "not" else [raw]}
    return raw


def _wide(count: int, operator: str = "all") -> dict:
    return {operator: [_attribute() for _ in range(count)]}


def _node_budget_tree(*, extra_node: bool = False) -> dict:
    leaf = _attribute()
    if extra_node:
        leaf = {"not": leaf}
    inner = {"all": [leaf, *(_attribute() for _ in range(14))]}
    middle = {"all": [inner, *(_attribute() for _ in range(15))]}
    outer = {"all": [middle, *(_attribute() for _ in range(15))]}
    return {"all": [outer, *(_attribute() for _ in range(15))]}


def _branch_32() -> dict:
    inner = {"all": [_attribute() for _ in range(15)]}
    return {"all": [inner, *(_attribute() for _ in range(15))]}


def _all_nodes_spec() -> tuple[dict, int]:
    names = ("power", "control", "resilience", "agility")
    attributes = [
        {
            "attribute": {
                "subject": "self",
                "key": name,
                "comparator": "gte",
                "value": 0,
            }
        }
        for name in names
    ]
    resources = [
        {
            "resource": {
                "subject": "self",
                "key": name,
                "comparator": "gte",
                "value": 0,
            }
        }
        for name in ("hp", "mana", "shield")
    ]
    leaves = [
        *attributes,
        *resources,
        {
            "field": {
                "subject": "current_area",
                "key": "heat",
                "comparator": "gte",
                "value": 0,
            }
        },
        {"has_trait": {"subject": "self", "id": "condition_trait"}},
        {"has_status": {"subject": "self", "id": "condition_status"}},
        None,
    ]
    raw = {"all": leaves}
    # root + ten typed leaves + always.
    return raw, 12


def _material():
    return parse_material({
        "id": "condition_crystal",
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "condition_shaping",
            "effect_kinds": ["process_start"],
            "selectors": ["current_area"],
            "budget_points": 5,
        }],
    })


def _skill_raw(condition, *, skill_id: str = SKILL_ID) -> dict:
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": skill_id,
        "version": 1,
        "trigger": "on_use",
        "condition": condition,
        "duration": None,
        "cost": {"duration": 2, "mana": 4},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": [{
            "id": "start",
            "kind": "process_start",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "process_template_id": TEMPLATE_ID,
        }],
        "budget": {"limit": 5},
        "max_firings_per_root": 1,
        "material_ids": ["condition_crystal"],
    }


def _parse_skill(condition, *, skill_id: str = SKILL_ID):
    material = _material()
    return parse_skill_blueprint(
        _skill_raw(condition, skill_id=skill_id),
        basic_registry().statuses,
        material_authority((material,)),
    )


def _effect_raw(condition) -> dict:
    return {
        "id": "heal_once",
        "kind": "heal",
        "target": {"kind": "self"},
        "commitment": "conditional",
        "condition": condition,
        "amount": 1,
    }


def _action_raw(condition, *, action_id: str = "condition_action") -> dict:
    return {
        "id": action_id,
        "version": 1,
        "action_type": "skill",
        "cost": {"duration": 1, "mana": 0},
        "scope": {"selectors": ["self"], "relation_types": []},
        "effects": [_effect_raw(condition)],
    }


def _hook_raw(condition) -> dict:
    return {
        "id": "condition_hook",
        "trigger": "action_started",
        "condition": condition,
        "effect_ids": ["heal_once"],
        "action_id": "condition_action",
        "max_firings_per_root": 1,
    }


def _actor(instance_id: str, *, controller: str):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": "condition_actor_blueprint",
        "hp": {"max": 50, "initial": 50},
        "mana": {"max": 30, "initial": 20, "dynamics": None},
        "attributes": {"power": 4, "control": 4, "resilience": 4, "agility": 4},
        "traits": [],
    })
    return instantiate_actor(blueprint, instance_id, controller=controller)


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
            "rate": 0.1,
            "curve": "linear",
            "max_persistent_patches": 2,
            "max_temporary_modifiers": 2,
        }],
    })
    return instantiate_area(blueprint, AREA_ID)


def _profile(profile_id: str, owner: str) -> ProcessProfile:
    prefix = profile_id.replace("_process", "")
    input_port = ConversionPort("ore", 1.0, "ore")
    output_port = ConversionPort("ingot", 1.0, "ingot")
    template = ProcessTemplate(
        TEMPLATE_ID,
        (input_port,),
        (output_port,),
        1.0,
        3,
        2.0,
        3,
    )
    return ProcessProfile(
        profile_id,
        template,
        f"process_{profile_id}",
        owner,
        (StockBinding("ore", StockRef(f"{prefix}_ore")),),
        (StockBinding("ingot", StockRef(f"{prefix}_ingot")),),
    )


def _runtime(skill):
    player_profile = _profile("condition_player_process", PLAYER_ID)
    npc_profile = _profile("condition_npc_process", NPC_ID)
    profiles = (player_profile, npc_profile)
    controller = ProcessController(
        profiles,
        ProcessLimits(max_instances=8, max_active=8),
    )
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        process_controller=controller,
    )
    content = make_content(
        base,
        skills=(skill,),
        material_ids=("condition_crystal",),
    )
    entities = {
        PLAYER_ID: _actor(PLAYER_ID, controller="human"),
        NPC_ID: _actor(NPC_ID, controller="ai"),
        AREA_ID: _area(),
        player_profile.process_entity_id: instantiate_process(player_profile),
        npc_profile.process_entity_id: instantiate_process(npc_profile),
        player_profile.inputs[0].stock.entity_id: stock_entity(
            player_profile.inputs[0].stock.entity_id,
            amount=10.0,
            capacity=20.0,
            unit="ore",
        ),
        player_profile.outputs[0].stock.entity_id: stock_entity(
            player_profile.outputs[0].stock.entity_id,
            amount=0.0,
            capacity=20.0,
            unit="ingot",
        ),
        npc_profile.inputs[0].stock.entity_id: stock_entity(
            npc_profile.inputs[0].stock.entity_id,
            amount=10.0,
            capacity=20.0,
            unit="ore",
        ),
        npc_profile.outputs[0].stock.entity_id: stock_entity(
            npc_profile.outputs[0].stock.entity_id,
            amount=0.0,
            capacity=20.0,
            unit="ingot",
        ),
    }
    world = build_gameplay_world(
        "condition_limits_world",
        areas=(entities[AREA_ID],),
        actors=(entities[PLAYER_ID], entities[NPC_ID]),
        placements=((PLAYER_ID, AREA_ID), (NPC_ID, AREA_ID)),
    )
    for entity_id, entity in entities.items():
        world.entities.setdefault(entity_id, entity)
    for profile in profiles:
        endpoints = (
            profile.process_entity_id,
            *(
                item.stock.entity_id
                for item in (*profile.inputs, *profile.outputs)
            ),
        )
        for endpoint in endpoints:
            relation = Relation(
                f"located:{endpoint}:{AREA_ID}",
                "located_in",
                endpoint,
                AREA_ID,
            )
            world.relations[relation.id] = relation
    world.entities["pmw:v04:clock"] = clock_entity()
    world = initialize_time_budget(world, 8)
    world = initialize_content_world(world, content)
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for actor_id in (PLAYER_ID, NPC_ID):
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=actor_id,
            operation="equip_active",
            skill=skill_ref(skill),
            slot=0,
        )
    return runtime, player_profile, npc_profile


def _snapshot(session) -> tuple:
    return (
        deepcopy(session.state.to_dict()),
        deepcopy(session.runtime.stats),
        session.runtime.revision,
        session.runtime.object_revision,
        session.runtime.state_closure_known,
    )


def _resource_snapshot(session) -> tuple:
    actors = []
    for actor_id in (PLAYER_ID, NPC_ID):
        actor = deepcopy(
            session.state.entities[actor_id].components["pmw_gameplay_actor"]
        )
        actors.append({
            "id": actor_id,
            "hp": actor["hp"],
            "mana": actor["mana"],
            "shield": actor["shield"],
            "statuses": deepcopy(
                session.state.entities[actor_id].components[
                    "pmw_gameplay_statuses"
                ]
            ),
        })
    return (
        tuple(actors),
        deepcopy(
            session.state.entities["pmw:v04:clock"].components[
                TIME_BUDGET_COMPONENT
            ]
        ),
        session.state.sim_time,
        session.state.tick,
    )


def _component(session, profile: ProcessProfile) -> dict:
    return session.state.entities[profile.process_entity_id].components[
        PROCESS_COMPONENT
    ]


class ConditionLimitUnitReviewTests(unittest.TestCase):
    def test_trusted_defaults_match_proposed_contract(self):
        defaults = ConditionLimits()
        self.assertEqual(
            (defaults.max_depth, defaults.max_nodes, defaults.max_children),
            (16, 64, 16),
        )
        self.assertEqual(
            set(ConditionLimits.__dataclass_fields__),
            {"max_depth", "max_nodes", "max_children"},
        )

    def test_depth_exact_boundary_and_one_over_use_root_depth_one(self):
        for builder in (_nested_all, _nested_any, _nested_not, _mixed):
            with self.subTest(builder=builder.__name__, boundary="accepted"):
                spec = parse_condition(builder(16))
                self.assertIsNotNone(spec)
            with self.subTest(builder=builder.__name__, boundary="rejected"):
                with self.assertRaises(GameplayContractError) as caught:
                    parse_condition(builder(17))
                self.assertRegex(str(caught.exception), r"(?i)depth")

    def test_depth_1500_is_bounded_contract_error_not_recursion(self):
        try:
            parse_condition(_nested_not(1500))
        except GameplayContractError as error:
            self.assertRegex(str(error), r"(?i)depth")
        except RecursionError as error:
            self.fail(f"production RecursionError escaped the bounded parser: {error!r}")
        else:
            self.fail("depth 1500 was accepted")

    def test_node_exact_boundary_one_over_and_shared_sibling_budget(self):
        exact = _node_budget_tree()
        spec = parse_condition(exact)
        self.assertEqual(len(spec.children), 16)
        with self.assertRaises(GameplayContractError) as caught:
            parse_condition(_node_budget_tree(extra_node=True))
        self.assertRegex(str(caught.exception), r"(?i)node")

        # Root + two shared sibling branches. Each branch has 32 nodes, but
        # the total is 65, so per-sibling budget resets are detectable.
        sibling = {"all": [_branch_32(), _branch_32()]}
        with self.assertRaises(GameplayContractError) as caught:
            parse_condition(sibling)
        self.assertRegex(str(caught.exception), r"(?i)node")

    def test_children_exact_boundary_and_wide_100_rejection(self):
        for operator in ("all", "any"):
            with self.subTest(operator=operator, boundary="accepted"):
                self.assertEqual(
                    len(parse_condition(_wide(16, operator)).children),
                    16,
                )
            with self.subTest(operator=operator, boundary="rejected"):
                with self.assertRaises(GameplayContractError) as caught:
                    parse_condition(_wide(17, operator))
                self.assertRegex(str(caught.exception), r"(?i)child")
        with self.assertRaises(GameplayContractError) as caught:
            parse_condition(_wide(100))
        self.assertRegex(str(caught.exception), r"(?i)child")

    def test_all_node_kinds_are_counted(self):
        raw, expected_nodes = _all_nodes_spec()
        spec = parse_condition(raw)
        self.assertEqual(len(spec.children), 11)
        self.assertEqual(
            {child.kind for child in spec.children},
            {"attribute", "resource", "field", "has_trait", "has_status", "always"},
        )
        self.assertEqual(expected_nodes, 12)

        # A tree that is exactly 64 nodes passes; one extra operator node
        # takes it over budget and must be counted.
        over = {"not": _node_budget_tree()}
        with self.assertRaises(GameplayContractError) as caught:
            parse_condition(over)
        self.assertRegex(str(caught.exception), r"(?i)node")

    def test_trusted_limits_reject_invalid_values_and_cannot_weaken_defaults(self):
        invalid = [
            {"max_depth": 0},
            {"max_depth": -1},
            {"max_depth": True},
            {"max_depth": 1.0},
            {"max_depth": "16"},
            {"max_nodes": 0},
            {"max_nodes": False},
            {"max_nodes": 12.5},
            {"max_children": 0},
            {"max_children": True},
            {"max_children": 16.0},
            {"max_depth": 65},
            {"max_nodes": 4097},
            {"max_children": 257},
        ]
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises((TypeError, ValueError, GameplayContractError)):
                    ConditionLimits(**values)
        for invalid_limit in (
            object(),
            {},
            {"max_depth": 16},
            (16, 64, 16),
        ):
            with self.subTest(limits=invalid_limit):
                with self.assertRaises((TypeError, ValueError, GameplayContractError)):
                    parse_condition(_attribute(), limits=invalid_limit)

        trusted = ConditionLimits(max_depth=32, max_nodes=128, max_children=32)
        self.assertIsNotNone(parse_condition(_nested_all(32), limits=trusted))

    def test_repeated_parse_and_caller_payload_are_immutable(self):
        raw, _ = _all_nodes_spec()
        original = deepcopy(raw)
        first = parse_condition(raw)
        second = parse_condition(raw)
        self.assertEqual(first, second)
        self.assertEqual(raw, original)

        rejected = _node_budget_tree(extra_node=True)
        rejected_original = deepcopy(rejected)
        for _ in range(3):
            with self.assertRaises(GameplayContractError):
                parse_condition(rejected)
        self.assertEqual(rejected, rejected_original)
        self.assertIsNotNone(parse_condition(_nested_all(16)))

    def test_cyclic_raw_dict_is_rejected_without_recursion_error(self):
        raw = {"any": []}
        raw["any"].append(raw)
        try:
            parse_condition(raw)
        except GameplayContractError:
            pass
        except RecursionError as error:
            self.fail(f"cyclic input escaped as RecursionError: {error!r}")
        else:
            self.fail("cyclic raw condition was accepted")


class ConditionFormalParserReviewTests(unittest.TestCase):
    def test_actual_action_effect_skill_and_hook_parsers_inherit_defaults(self):
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
            parse_action_definition,
        )
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.effects import (
            parse_effect,
        )

        parsers = {
            "action": lambda condition: parse_action_definition(
                _action_raw(condition),
                basic_registry().statuses,
            ),
            "effect": lambda condition: parse_effect(
                _effect_raw(condition),
                basic_registry().statuses,
            ),
            "skill": lambda condition: _parse_skill(condition),
            "hook": lambda condition: parse_hook(_hook_raw(condition)),
        }
        for name, parser in parsers.items():
            with self.subTest(parser=name, boundary="rejected"):
                with self.assertRaises(GameplayContractError) as caught:
                    parser(_nested_not(17))
                self.assertRegex(str(caught.exception), r"(?i)depth")
            with self.subTest(parser=name, boundary="accepted"):
                self.assertIsNotNone(parser(_nested_not(16)))

        with self.assertRaises(GameplayContractError) as caught:
            parse_action_definition(
                _action_raw(_node_budget_tree(extra_node=True)),
                basic_registry().statuses,
            )
        self.assertRegex(str(caught.exception), r"(?i)node")

    def test_baseline_accepted_skill_canonical_hashes_are_preserved(self):
        variants = {
            "null": None,
            "all": {
                "all": [
                    _attribute("control", 4),
                    {
                        "resource": {
                            "subject": "self",
                            "key": "mana",
                            "comparator": "gte",
                            "value": 1,
                        }
                    },
                ]
            },
            "any": {
                "any": [
                    _attribute("power", 0, comparator="gt"),
                    {"has_status": {"subject": "self", "id": "none"}},
                ]
            },
            "not": {"not": {"has_trait": {"subject": "self", "id": "none"}}},
            "mixed": {
                "all": [
                    {
                        "not": _attribute(
                            "agility",
                            0,
                            comparator="lt",
                        )
                    },
                    {
                        "any": [
                            {
                                "resource": {
                                    "subject": "self",
                                    "key": "mana",
                                    "comparator": "gte",
                                    "value": 1,
                                }
                            },
                            _attribute(
                                "resilience",
                                1,
                                subject="target_actor",
                            ),
                        ]
                    },
                ]
            },
        }
        for name, condition in variants.items():
            with self.subTest(variant=name):
                skill = _parse_skill(condition, skill_id=f"baseline_{name}")
                self.assertEqual(
                    skill.canonical_hash,
                    ACCEPTED_CANONICAL_HASHES[name],
                )
                normalized = json.loads(skill.canonical_document_json)
                self.assertEqual(normalized, _skill_raw(condition, skill_id=f"baseline_{name}"))

    def test_malformed_and_semantic_guard_errors_are_product_errors(self):
        cases = {
            "two_operators": {"all": [_attribute()], "any": [_attribute()]},
            "empty_all": {"all": []},
            "unknown_operator": {"sometimes": [_attribute()]},
            "unknown_key": {"attribute": {
                "subject": "self",
                "key": "not_an_attribute",
                "comparator": "gte",
                "value": 1,
            }},
            "bad_scope": {"attribute": {
                "subject": "other",
                "key": "control",
                "comparator": "gte",
                "value": 1,
            }},
            "bool_value": {"attribute": {
                "subject": "self",
                "key": "control",
                "comparator": "gte",
                "value": True,
            }},
            "nonfinite": {"attribute": {
                "subject": "self",
                "key": "control",
                "comparator": "gte",
                "value": float("nan"),
            }},
        }
        for name, raw in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(GameplayContractError):
                    parse_condition(raw)


class ConditionRuntimeAtomicityReviewTests(unittest.TestCase):
    def test_timed_condition_parser_compatibility_player_and_npc(self):
        skill = _parse_skill({
            "all": [
                _attribute("control", 4),
                {"not": {"has_status": {"subject": "self", "id": "condition_status"}}},
            ]
        })
        runtime, player_profile, npc_profile = _runtime(skill)
        for actor_id, profile in ((PLAYER_ID, player_profile), (NPC_ID, npc_profile)):
            with self.subTest(actor=actor_id):
                before_budget = deepcopy(
                    runtime.session.state.entities[
                        "pmw:v04:clock"
                    ].components[TIME_BUDGET_COMPONENT]
                )
                before_mana = runtime.session.state.entities[
                    actor_id
                ].components["pmw_gameplay_actor"]["mana"]
                outcome = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(f"{actor_id}_condition", actor_id, SKILL_ID),
                )
                self.assertEqual(outcome.action.cost.duration, 2)
                self.assertEqual(outcome.time.duration, 2)
                self.assertEqual(_component(runtime.session, profile)["state"], "running")
                self.assertEqual(
                    runtime.session.state.entities[actor_id].components[
                        "pmw_gameplay_actor"
                    ]["mana"],
                    before_mana - 4,
                )
                after_budget = runtime.session.state.entities[
                    "pmw:v04:clock"
                ].components[TIME_BUDGET_COMPONENT]
                self.assertEqual(
                    after_budget["spent_ticks"] - before_budget["spent_ticks"],
                    2,
                )

    def test_pathological_raw_fails_before_timed_action_resource_writes(self):
        # A valid admitted Skill establishes a genuine equipped Actor. The
        # pathological candidate is then parsed through each formal surface.
        skill = _parse_skill({"all": [_attribute(), None]})
        runtime, _, _ = _runtime(skill)
        before = _snapshot(runtime.session)
        resources = _resource_snapshot(runtime.session)

        self.assertIsNotNone(evaluate_condition(skill.condition, {
            "self": runtime.session.state.entities[PLAYER_ID].components[
                "pmw_gameplay_actor"
            ],
            "target_actor": {},
            "current_area": {},
        }))

        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
            parse_action_definition,
        )
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.effects import (
            parse_effect,
        )

        malformed = {
            "depth": _nested_not(1500),
            "wide": _wide(100),
            "cycle": self._cycle(),
        }
        for name, condition in malformed.items():
            with self.subTest(surface="action", case=name):
                with self.assertRaises(GameplayContractError):
                    parse_action_definition(
                        _action_raw(condition),
                        basic_registry().statuses,
                    )
            with self.subTest(surface="effect", case=name):
                with self.assertRaises(GameplayContractError):
                    parse_effect(_effect_raw(condition), basic_registry().statuses)
            with self.subTest(surface="skill", case=name):
                with self.assertRaises(GameplayContractError):
                    _parse_skill(condition)
            with self.subTest(surface="hook", case=name):
                with self.assertRaises(GameplayContractError):
                    parse_hook(_hook_raw(condition))

        self.assertEqual(_snapshot(runtime.session), before)
        self.assertEqual(_resource_snapshot(runtime.session), resources)

    def test_rejected_condition_does_not_consume_budget_or_mana(self):
        skill = _parse_skill(None)
        runtime, _, _ = _runtime(skill)
        before = _snapshot(runtime.session)
        with self.assertRaises(GameplayContractError):
            parse_condition(_nested_not(1500))
        self.assertEqual(_snapshot(runtime.session), before)

        timed_before = _resource_snapshot(runtime.session)
        outcome = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("after_rejection", PLAYER_ID, SKILL_ID),
        )
        self.assertEqual(outcome.time.duration, 2)
        timed_after = _resource_snapshot(runtime.session)
        self.assertEqual(
            timed_after[1]["spent_ticks"] - timed_before[1]["spent_ticks"],
            2,
        )
        self.assertEqual(
            timed_after[0][0]["mana"],
            timed_before[0][0]["mana"] - 4,
        )

    @staticmethod
    def _cycle() -> dict:
        raw = {"any": []}
        raw["any"].append(raw)
        return raw


def probe_top_level_false_gate_omission() -> dict:
    """Report C4.3 behavior without making the known defect a test oracle."""
    skill = _parse_skill({
        "attribute": {
            "subject": "self",
            "key": "control",
            "comparator": "gte",
            "value": 999,
        }
    })
    condition_context = {
        "self": {
            "control": 4,
            "hp": 50,
            "mana": 20,
            "shield": 0,
            "status_slots": {},
        },
        "target_actor": {},
        "current_area": {},
    }
    condition_result = evaluate_condition(skill.condition, condition_context)
    runtime, player_profile, _ = _runtime(skill)
    before = _resource_snapshot(runtime.session)
    outcome = submit_timed_primary_action(
        runtime.session,
        runtime.action_registry,
        ActionRequest("false_top_level_probe", PLAYER_ID, SKILL_ID),
    )
    after = _resource_snapshot(runtime.session)
    return {
        "skill_id": skill.id,
        "condition_evaluated_false": condition_result is False,
        "process_state_after_action": _component(
            runtime.session, player_profile
        )["state"],
        "action_duration": outcome.action.cost.duration,
        "time_duration": outcome.time.duration,
        "spent_ticks_delta": (
            after[1]["spent_ticks"] - before[1]["spent_ticks"]
        ),
        "player_mana_before": before[0][0]["mana"],
        "player_mana_after": after[0][0]["mana"],
        "player_mana_delta": after[0][0]["mana"] - before[0][0]["mana"],
    }


class TemporaryDirectoryReviewTests(unittest.TestCase):
    def test_pmw_local_temp_directory_is_writable(self):
        REVIEW_TMP.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=REVIEW_TMP) as directory:
            path = Path(directory) / "probe.json"
            path.write_text("{}", encoding="utf-8")
            self.assertEqual(path.read_text(encoding="utf-8"), "{}")
            self.assertTrue(Path(directory).resolve().is_relative_to(REVIEW_TMP.resolve()))
        self.assertEqual(os.environ.get("PYTHONDONTWRITEBYTECODE"), "1")


if __name__ == "__main__":
    unittest.main()
