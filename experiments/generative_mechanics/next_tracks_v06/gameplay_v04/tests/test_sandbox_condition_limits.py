from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
    basic_registry_document,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    ConditionLimits,
    parse_condition,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.effects import parse_effect
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.hooks import parse_hook
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    MaterialAuthority,
    material_authority,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_process_action import (
    NPC_ID,
    PLAYER_ID,
    _blueprint,
    _material,
    _profile,
    _runtime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
)


_OPERATORS = ("all", "any", "not")


def _nested_not(depth: int) -> dict:
    result: dict = None
    for _ in range(depth - 1):
        result = {"not": result}
    return result


def _nested_operators(depth: int) -> dict:
    result: dict = None
    for index in range(depth - 1, 0, -1):
        operator = _OPERATORS[index % len(_OPERATORS)]
        value = [result] if operator in {"all", "any"} else result
        result = {operator: value}
    return result


def _wide(children: int) -> dict:
    return {"all": [None] * children}


def _shared_siblings(fanout: int) -> dict:
    return {"all": [{"not": {"any": [None] * fanout}} for _ in range(fanout)]}


def _node_tree(nodes: int) -> dict:
    subtree_sizes = (16, 16, 16, nodes - 53)
    return {"all": [{"all": [None] * size} for size in subtree_sizes]}


def _count_nodes(raw) -> int:
    if raw is None:
        return 1
    if not isinstance(raw, dict) or len(raw) != 1:
        return 1
    kind, value = next(iter(raw.items()))
    if kind in {"all", "any"}:
        return 1 + sum(_count_nodes(item) for item in value)
    if kind == "not":
        return 1 + _count_nodes(value)
    return 1


def _count_spec_nodes(spec) -> int:
    return 1 + sum(_count_spec_nodes(child) for child in spec.children)


def _skill_document(*, condition: dict | None = None) -> dict:
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": "bounded_mist",
        "version": 1,
        "trigger": "on_use",
        "condition": condition,
        "duration": None,
        "cost": {"duration": 1, "mana": 0},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": [{
            "id": "mist_step",
            "kind": "modify_field",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "mist",
            "amount": 0.1,
        }],
        "budget": {"limit": 6},
        "max_firings_per_root": 1,
        "material_ids": ["mist_crystal"],
    }


def _effect() -> dict:
    return {
        "id": "conditional_mist",
        "kind": "modify_field",
        "target": {"kind": "current_area"},
        "commitment": "conditional",
        "field_id": "mist",
        "amount": 0.1,
    }


def _blueprint_with_condition(condition: dict):
    material = _material()
    document = json.loads(_blueprint().canonical_document_json)
    document["condition"] = condition
    return parse_skill_blueprint(
        document,
        basic_registry().statuses,
        material_authority((material,)),
    )


class DefaultBoundaryTests(unittest.TestCase):
    def assert_limit_error(self, raw, kind: str, path: str):
        with self.assertRaises(GameplayContractError) as caught:
            parse_condition(raw, "$.case")
        message = str(caught.exception)
        self.assertIn(path, message)
        self.assertIn(kind, message)

    def test_depth_exact_boundary_and_one_over(self):
        exact = parse_condition(_nested_not(16), "$.depth")
        self.assertEqual(exact.kind, "not")
        self.assert_limit_error(
            _nested_not(17),
            "max_depth",
            "$.case" + ".not" * 16,
        )

    def test_node_exact_boundary_and_one_over_after_null_is_counted(self):
        exact_raw = _node_tree(64)
        exact = parse_condition(exact_raw, "$.nodes")
        self.assertEqual(len(exact.children), 4)
        self.assertEqual(_count_nodes(exact_raw), 64)
        self.assertEqual(_count_spec_nodes(exact), 64)
        self.assert_limit_error(_node_tree(65), "max_nodes", "$.case.all[3].all[11]")

    def test_children_exact_boundary_and_one_over(self):
        exact = parse_condition(_wide(16), "$.children")
        self.assertEqual(len(exact.children), 16)
        self.assert_limit_error(_wide(17), "max_children", "$.case.all")
        with self.assertRaisesRegex(
            GameplayContractError, r"max_children 16"
        ):
            parse_condition(_wide(17), "$.children")

    def test_shared_sibling_budget_and_repeated_calls_do_not_leak(self):
        raw = _shared_siblings(7)
        self.assertEqual(_count_nodes(raw), 64)
        for _ in range(20):
            self.assertEqual(_count_spec_nodes(parse_condition(raw)), 64)
        too_many = _shared_siblings(8)
        self.assertEqual(_count_nodes(too_many), 81)
        self.assert_limit_error(too_many, "max_nodes", "$.case.all[6].not.any[1]")
        self.assertEqual(_count_spec_nodes(parse_condition(raw)), 64)

    def test_alternating_operators_are_depth_bounded(self):
        raw = _nested_operators(16)
        spec = parse_condition(raw)
        self.assertEqual(spec.kind, "any")
        self.assertEqual(_count_spec_nodes(spec), 16)
        self.assert_limit_error(_nested_operators(17), "max_depth", "$.case")

    def test_cyclic_python_dict_rejects_with_bounded_depth(self):
        raw: dict = {}
        raw["not"] = raw
        with self.assertRaises(GameplayContractError) as caught:
            parse_condition(raw, "$.cycle")
        message = str(caught.exception)
        self.assertIn("$.cycle", message)
        self.assertIn("max_depth", message)

    def test_frozen_limits_and_invalid_values_are_rejected(self):
        limits = ConditionLimits()
        self.assertEqual(
            (limits.max_depth, limits.max_nodes, limits.max_children),
            (16, 64, 16),
        )
        with self.assertRaises((AttributeError, TypeError)):
            limits.max_depth = 1
        invalid = (
            {"max_depth": 0},
            {"max_depth": 65},
            {"max_depth": True},
            {"max_depth": 1.5},
            {"max_nodes": 0},
            {"max_nodes": 4097},
            {"max_children": 0},
            {"max_children": 257},
        )
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises(GameplayContractError):
                    ConditionLimits(**values)
        for maximum in (
            {"max_depth": 64},
            {"max_nodes": 4096},
            {"max_children": 256},
        ):
            with self.subTest(maximum=maximum):
                ConditionLimits(**maximum)

    def test_trusted_limits_are_keyword_only_and_type_checked(self):
        with self.assertRaises(TypeError):
            parse_condition(None, "$.condition", ConditionLimits())
        with self.assertRaises(GameplayContractError):
            parse_condition(None, limits={"max_depth": 1})


class SharedEntryPointTests(unittest.TestCase):
    def test_effect_skill_and_hook_entry_points_use_shared_budget(self):
        statuses = basic_registry().statuses
        effect = _effect()
        effect["condition"] = _nested_not(17)
        with self.assertRaisesRegex(GameplayContractError, r"effect\.condition.*max_depth"):
            parse_effect(effect, statuses, "$.effect")

        with self.assertRaisesRegex(GameplayContractError, r"skill\.condition.*max_depth"):
            parse_skill_blueprint(
                _skill_document(condition=_nested_not(17)),
                statuses,
                MaterialAuthority(
                    ("mist_crystal",), ("modify_field",), ("current_area",), 6.0
                ),
                "$.skill",
            )

        with self.assertRaisesRegex(GameplayContractError, r"hook\.condition.*max_nodes"):
            parse_hook({
                "id": "bounded_hook",
                "trigger": "damage_resolved",
                "condition": _node_tree(65),
                "effect_ids": ["mist_step"],
                "action_id": "bounded_mist",
                "max_firings_per_root": 1,
            }, "$.hook")

    def test_action_registry_and_cost_modifier_use_shared_budget(self):
        document = basic_registry_document()
        document["actions"][2]["cost_modifiers"] = [{
            "id": "too_deep",
            "condition": _nested_not(17),
            "duration_add": 1,
            "mana_add": 0,
        }]
        with self.assertRaisesRegex(
            GameplayContractError,
            r"cost_modifiers\[0\]\.condition.*max_depth",
        ):
            ActionRegistry.parse(document)

    def test_candidate_json_cannot_raise_budgets_and_caller_is_immutable(self):
        condition = _nested_not(17)
        before = deepcopy(condition)
        document = _skill_document(condition=condition)
        authority = MaterialAuthority(
            ("mist_crystal",), ("modify_field",), ("current_area",), 6.0
        )
        with self.assertRaisesRegex(GameplayContractError, "max_depth"):
            parse_skill_blueprint(document, basic_registry().statuses, authority)
        document["limits"] = {
            "max_depth": 64,
            "max_nodes": 4096,
            "max_children": 256,
        }
        with self.assertRaisesRegex(GameplayContractError, "missing/unknown fields"):
            parse_skill_blueprint(document, basic_registry().statuses, authority)
        self.assertEqual(condition, before)

        accepted = {"all": [None, {"not": None}]}
        accepted_before = deepcopy(accepted)
        spec = parse_condition(accepted)
        self.assertEqual(accepted, accepted_before)
        self.assertEqual(spec.kind, "all")


class AcceptedSemanticsTests(unittest.TestCase):
    def test_typed_leaf_schema_and_meaning_are_unchanged(self):
        raw = {
            "all": [
                {"any": [
                    {"attribute": {
                        "subject": "self",
                        "key": "power",
                        "comparator": "gte",
                        "value": 4,
                    }},
                    {"resource": {
                        "subject": "target_actor",
                        "key": "hp",
                        "comparator": "lt",
                        "value": 20,
                    }},
                ]},
                {"not": {"field": {
                    "subject": "current_area",
                    "key": "mist",
                    "comparator": "gt",
                    "value": 0.9,
                }}},
                {"has_trait": {"subject": "self", "id": "mist_attuned"}},
                {"has_status": {"subject": "target_actor", "id": "burning"}},
            ]
        }
        before = deepcopy(raw)
        spec = parse_condition(raw)
        self.assertEqual(raw, before)
        self.assertEqual(spec.kind, "all")
        self.assertEqual(spec.children[0].children[0].subject, "self")
        for invalid in (
            {"attribute": {"subject": "self", "key": "power", "comparator": "eq"}},
            {"all": []},
            {"unknown": None},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(GameplayContractError):
                    parse_condition(invalid)

    def test_accepted_skill_canonical_hash_is_stable(self):
        condition = {"all": [None, {"not": None}]}
        document = _skill_document(condition=condition)
        expected = hashlib.sha256(
            json.dumps(
                document,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        authority = MaterialAuthority(
            ("mist_crystal",), ("modify_field",), ("current_area",), 6.0
        )
        skill = parse_skill_blueprint(
            document, basic_registry().statuses, authority
        )
        self.assertEqual(skill.condition.kind, "all")
        self.assertEqual(skill.canonical_hash, expected)
        self.assertEqual(skill.canonical_document_json, json.dumps(
            document, sort_keys=True, separators=(",", ":"), allow_nan=False
        ))

    def test_normal_timed_player_and_npc_actions_with_accepted_condition(self):
        condition = {"all": [None, {"not": {"not": None}}]}
        skill = _blueprint_with_condition(condition)
        player = _profile("condition_player", PLAYER_ID)
        npc = _profile("condition_npc", NPC_ID)
        runtime, _, _ = _runtime((player, npc), skill=skill, time_budget=6)

        player_outcome = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("condition_player_use", PLAYER_ID, skill.id),
        )
        npc_outcome = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("condition_npc_use", NPC_ID, skill.id),
        )
        budget = runtime.session.state.entities["pmw:v04:clock"].components[
            TIME_BUDGET_COMPONENT
        ]
        self.assertEqual(player_outcome.time.duration, 2)
        self.assertEqual(npc_outcome.time.duration, 2)
        self.assertEqual(
            (budget["spent_ticks"], budget["remaining_ticks"]),
            (4, 2),
        )
        for actor_id in (PLAYER_ID, NPC_ID):
            self.assertEqual(
                runtime.session.state.entities[actor_id]
                .components["pmw_gameplay_actor"]["mana"],
                16.0,
            )

    def test_pathological_raw_tree_is_atomic_before_execution(self):
        condition = _nested_not(17)
        skill = _blueprint_with_condition({"all": [None]})
        runtime, _, _ = _runtime((_profile("atomic_player", PLAYER_ID),))
        before = deepcopy(runtime.session.state.to_dict())
        revision = runtime.session.runtime.revision
        with self.assertRaisesRegex(GameplayContractError, "max_depth"):
            runtime.install(
                {
                    **json.loads(skill.canonical_document_json),
                    "condition": condition,
                },
                skill.material_authority,
            )
        self.assertEqual(runtime.session.state.to_dict(), before)
        self.assertEqual(runtime.session.runtime.revision, revision)


if __name__ == "__main__":
    unittest.main()
