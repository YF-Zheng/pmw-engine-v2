from __future__ import annotations

from copy import deepcopy
import dataclasses
import hashlib
import json
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ACTOR_COMPONENT,
    ActionRequest,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import (
    run_combat_round,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    ConditionLimits,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_ir import (
    _validate_json_shape,
    compile_skill_ir,
    parse_skill_ir,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    compile_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import (
    build_gate3_demo,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_p1_scenarios import (
    MATERIAL_ID as P1_MATERIAL_ID,
    NPC as P1_NPC,
    PLAYER as P1_PLAYER,
    _actor_state,
    _budget,
    _field,
    _formal_runtime,
    _world,
)
from experiments.generative_mechanics.next_tracks_v06.tests.test_sandbox_passive_dispatch import (
    _records,
)


MATERIAL_ID = "p2r_material"
DEFAULT_SELECTORS = ("self", "target_actor", "current_area")


def _material(
    *kinds: str,
    selectors: tuple[str, ...] = DEFAULT_SELECTORS,
    budget: float = 40.0,
    material_id: str = MATERIAL_ID,
):
    return parse_material({
        "id": material_id,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "p2r_authority",
            "effect_kinds": list(kinds),
            "selectors": list(selectors),
            "budget_points": budget,
        }],
    })


def _authority(
    *kinds: str,
    selectors: tuple[str, ...] = DEFAULT_SELECTORS,
    budget: float = 40.0,
    material_id: str = MATERIAL_ID,
):
    return material_authority((
        _material(
            *kinds,
            selectors=selectors,
            budget=budget,
            material_id=material_id,
        ),
    ))


def _effect(
    effect_id: str = "pulse",
    kind: str = "damage",
    *,
    target: str = "target_actor",
    condition=None,
    **fields,
):
    result = {
        "id": effect_id,
        "kind": kind,
        "target": {"kind": target},
        "commitment": "required",
        **fields,
    }
    if kind == "damage":
        result.setdefault("amount", 4)
    if condition is not None:
        result["condition"] = condition
    return result


def _entry(
    entry_id: str = "active",
    *,
    on_use: bool = True,
    effects=None,
    condition=None,
    max_firings: int = 1,
):
    return {
        "id": entry_id,
        "trigger": (
            {"kind": "on_use"}
            if on_use
            else {"kind": "on_event", "event": "damage_resolved"}
        ),
        "condition": condition,
        "effects": [_effect()] if effects is None else effects,
        "max_firings_per_root": max_firings,
    }


def _document(
    entries=None,
    *,
    budget: float = 40.0,
    selectors=DEFAULT_SELECTORS,
    relation_types=(),
    mana: float = 4.0,
    duration: int = 1,
    status_duration=None,
    material_id: str = MATERIAL_ID,
):
    return {
        "protocol": "pmw-skill-ir-v1",
        "identity": {
            "id": "p2r_skill",
            "version": 1,
            "name": "Independent P2.1 review skill",
            "description": "Adversarial conformance fixture.",
        },
        "origin": {
            "source": "authored",
            "model": None,
            "context_hash": None,
            "material_ids": [material_id],
        },
        "capability": {"traits": ["p2r_trait"]},
        "targeting": {
            "selectors": list(selectors),
            "relation_types": list(relation_types),
        },
        "costs": {"mana": mana, "duration": duration},
        "entries": [_entry()] if entries is None else entries,
        "lifecycle": {"status_duration": status_duration},
        "limits": {"budget": budget},
        "display": {"summary": "Independent review preview.", "tags": ["review"]},
    }


def _parse(raw, *, authority=None, limits=None):
    return parse_skill_ir(
        raw,
        basic_registry().statuses,
        authority or _authority("damage", "shield"),
        condition_limits=limits,
    )


def _condition_tree(nodes: int):
    """Build an acyclic condition with exactly ``nodes`` parser nodes."""
    if nodes < 1:
        raise AssertionError("condition node count must be positive")
    if nodes == 1:
        return None
    remaining = nodes - 1
    child_count = None
    for candidate in range(1, 17):
        if candidate <= remaining <= 17 * candidate:
            child_count = candidate
            break
    if child_count is None:
        raise AssertionError("condition tree exceeds the 256-node fixture range")
    base, extra = divmod(remaining, child_count)
    children = []
    for index in range(child_count):
        child_nodes = base + (1 if index < extra else 0)
        if child_nodes == 1:
            children.append(None)
        else:
            children.append({"all": [None] * (child_nodes - 1)})
    return {"all": children}


def _not_chain(wrappers: int, terminal=None):
    result = terminal
    for _ in range(wrappers):
        result = {"not": result}
    return result


def _reverse_mappings(value):
    if isinstance(value, dict):
        return {
            key: _reverse_mappings(value[key])
            for key in reversed(list(value))
        }
    if isinstance(value, list):
        return [_reverse_mappings(item) for item in value]
    return value


def _force_canonical_document(ir, document):
    """Simulate replacing the claimed parse-time semantic record."""
    canonical_json = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    object.__setattr__(ir, "canonical_json", canonical_json)
    object.__setattr__(
        ir,
        "canonical_hash",
        hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
    )
    return ir


class SkillIRReviewBudgetTests(unittest.TestCase):
    def test_condition_budget_exact_64_and_65_across_entries_and_effects(self):
        entries = [
            _entry(
                "active",
                condition=_condition_tree(16),
                effects=[_effect(condition=_condition_tree(16))],
            ),
            _entry(
                "reaction",
                on_use=False,
                condition=_condition_tree(16),
                effects=[_effect(
                    "guard",
                    "shield",
                    target="self",
                    amount=3,
                    condition=_condition_tree(16),
                )],
            ),
        ]
        raw = _document(entries=entries, budget=10)
        parsed = _parse(raw, limits=ConditionLimits(max_nodes=64))
        self.assertEqual(parsed.condition_nodes, 64)

        raw["entries"][1]["effects"][0]["condition"] = _condition_tree(17)
        with self.assertRaisesRegex(GameplayContractError, "max_nodes 64"):
            _parse(raw, limits=ConditionLimits(max_nodes=64))

    def test_condition_budget_rejects_two_individually_valid_64_node_trees(self):
        raw = _document(entries=[
            _entry(
                "active",
                condition=_condition_tree(63),
                effects=[_effect(condition=None)],
            ),
            _entry(
                "reaction",
                on_use=False,
                condition=_condition_tree(63),
                effects=[_effect("guard", "shield", target="self", amount=3)],
            ),
        ])
        with self.assertRaisesRegex(GameplayContractError, "max_nodes 64"):
            _parse(raw, limits=ConditionLimits(max_nodes=64))

    def test_null_nodes_and_nested_limits_match_conditions_parser(self):
        raw = _document(entries=[_entry(
            condition={"all": [None, None]},
            effects=[
                _effect(condition={"not": None}),
                _effect("guard", "shield", target="self", amount=2),
            ],
        )])
        parsed = _parse(raw, limits=ConditionLimits(max_nodes=64))
        self.assertEqual(parsed.condition_nodes, 6)

        raw = _document(entries=[_entry(
            condition=_not_chain(15),
        )])
        parsed = _parse(raw, limits=ConditionLimits(max_depth=16))
        self.assertEqual(parsed.condition_nodes, 17)

        raw["entries"][0]["condition"] = _not_chain(15, terminal={"all": [None]})
        with self.assertRaisesRegex(GameplayContractError, "max_depth 16"):
            _parse(raw, limits=ConditionLimits(max_depth=16))

        raw["entries"][0]["condition"] = {"all": [None] * 17}
        with self.assertRaisesRegex(GameplayContractError, "max_children 16"):
            _parse(raw, limits=ConditionLimits(max_children=16))

    def test_condition_limits_are_tighten_only_and_default_caps_are_restorable(
        self,
    ):
        from pathlib import Path
        import tempfile

        defaults = ConditionLimits()
        loosened = (
            ("max_depth", ConditionLimits(max_depth=defaults.max_depth + 1)),
            ("max_nodes", ConditionLimits(max_nodes=defaults.max_nodes + 1)),
            (
                "max_children",
                ConditionLimits(max_children=defaults.max_children + 1),
            ),
        )
        for label, limits in loosened:
            with self.subTest(label=label, boundary="parse-tighten-only"):
                with self.assertRaises(GameplayContractError):
                    _parse(_document(), limits=limits)

            with self.subTest(label=label, boundary="compile-tighten-only"):
                parsed = _parse(_document())
                forged = dataclasses.replace(parsed, condition_limits=limits)
                with self.assertRaises(GameplayContractError):
                    compile_skill_ir(forged)

        # The default budgets count the document's entry conditions and every
        # effect condition, including an omitted/null effect condition.
        accepted = (
            (
                "depth-16",
                _document(entries=[
                    _entry("depth", condition=_not_chain(15)),
                ]),
                17,
            ),
            (
                "nodes-64",
                _document(entries=[
                    _entry("nodes_1", on_use=False,
                           condition=_not_chain(14)),
                    _entry("nodes_2", on_use=False,
                           condition=_not_chain(14)),
                    _entry("nodes_3", on_use=False,
                           condition=_not_chain(14)),
                    _entry("nodes_4", on_use=False,
                           condition=_not_chain(14)),
                ]),
                64,
            ),
            (
                "children-16",
                _document(entries=[
                    _entry("children", condition={"all": [None] * 16}),
                ]),
                18,
            ),
        )
        rejected = (
            (
                "depth-17",
                _document(entries=[
                    _entry("depth_over", condition=_not_chain(16)),
                ]),
            ),
            (
                "nodes-65",
                _document(entries=[
                    _entry("nodes_over_1", on_use=False,
                           condition=_not_chain(14)),
                    _entry("nodes_over_2", on_use=False,
                           condition=_not_chain(14)),
                    _entry("nodes_over_3", on_use=False,
                           condition=_not_chain(14)),
                    _entry("nodes_over_4", on_use=False,
                           condition=_not_chain(15)),
                ]),
            ),
            (
                "children-17",
                _document(entries=[
                    _entry("children_over",
                           condition={"all": [None] * 17}),
                ]),
            ),
        )

        def install_and_restore(blueprint):
            session, content, _, _ = build_gate3_demo()
            compiled_content = compile_content(content)
            runtime = MechanismRegistryRuntime.from_compiled_content(
                session, compiled_content
            )
            runtime.install(
                json.loads(blueprint.canonical_document_json),
                blueprint.material_authority,
            )
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "skill_ir_checkpoint.json"
                digest = save_registry_checkpoint(path, runtime)
                restored = load_registry_checkpoint(path, compiled_content)
            self.assertEqual(len(digest), 64)
            restored_blueprint = restored.blueprints[
                (blueprint.id, blueprint.version)
            ]
            self.assertEqual(
                restored_blueprint.canonical_hash,
                blueprint.canonical_hash,
            )

        for label, raw, expected_nodes in accepted:
            with self.subTest(label=label, boundary="accepted"):
                parsed = _parse(raw)
                self.assertEqual(parsed.condition_nodes, expected_nodes)
                compiled = compile_skill_ir(parsed)
                self.assertEqual(compiled.canonical_hash, parsed.canonical_hash)
                install_and_restore(compiled.blueprints[0])

        for label, raw in rejected:
            with self.subTest(label=label, boundary="rejected-parse"):
                with self.assertRaises(GameplayContractError):
                    _parse(raw)

            with self.subTest(label=label, boundary="rejected-compile"):
                parsed = _parse(_document())
                forged = _force_canonical_document(parsed, raw)
                with self.assertRaises(GameplayContractError):
                    compile_skill_ir(forged)

    def test_shared_material_budget_includes_each_passive_surcharge(self):
        active = _entry(
            "active",
            effects=[_effect("strike", "damage", amount=4)],
        )
        passive_one = _entry(
            "reaction_one",
            on_use=False,
            effects=[_effect("guard_one", "shield", target="self", amount=3)],
        )
        passive_two = _entry(
            "reaction_two",
            on_use=False,
            effects=[_effect("guard_two", "shield", target="self", amount=3)],
        )
        authority = _authority("damage", "shield")

        active_only = compile_skill_ir(_parse(
            _document(entries=[active], budget=2.0),
            authority=authority,
        ))
        passive_only = compile_skill_ir(_parse(
            _document(entries=[passive_one], budget=2.5),
            authority=authority,
        ))
        self.assertEqual(active_only.blueprints[0].budget_used, 2.0)
        self.assertEqual(passive_only.blueprints[0].budget_used, 2.5)

        two_passives = compile_skill_ir(_parse(
            _document(
                entries=[active, passive_one, passive_two],
                budget=7.0,
            ),
            authority=authority,
        ))
        self.assertEqual(
            sum(item.budget_used for item in two_passives.blueprints),
            7.0,
        )

        with self.assertRaisesRegex(
            GameplayContractError,
            "shared document budget",
        ):
            _parse(
                _document(entries=[active, passive_one], budget=4.49),
                authority=authority,
            )


class SkillIRReviewAuthorityAndSchemaTests(unittest.TestCase):
    def test_authority_matrix(self):
        cases = []

        raw = _document(entries=[_entry(effects=[
            _effect("heal", "heal", amount=2),
        ])])
        cases.append((
            "unauthorized effect kind",
            raw,
            _authority("damage"),
            "effect authorization",
        ))

        raw = _document(
            selectors=("self", "target_actor", "adjacent_area"),
        )
        cases.append((
            "unauthorized targeting selector",
            raw,
            _authority("damage", selectors=("self", "target_actor")),
            "scope authorization",
        ))

        raw = _document(selectors=("self",))
        cases.append((
            "effect target outside declared selectors",
            raw,
            _authority("damage", selectors=("self", "target_actor")),
            "targeting selectors",
        ))

        raw = _document(
            selectors=("linked_object",),
            relation_types=(),
        )
        cases.append((
            "linked_object without relation types",
            raw,
            _authority("damage", selectors=("linked_object",)),
            "explicit relation type",
        ))

        raw = _document()
        raw["origin"]["material_ids"] = ["other_material"]
        cases.append((
            "material ids mismatch",
            raw,
            _authority("damage"),
            "material authority",
        ))

        for label, raw, authority, message in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(GameplayContractError, message):
                    _parse(raw, authority=authority)

    def test_malformed_membership_inputs_are_schema_errors(self):
        mutations = []

        raw = _document()
        raw["origin"]["source"] = []
        mutations.append(("origin.source", raw))

        raw = _document(status_duration={"unit": [], "amount": 2})
        mutations.append(("status_duration.unit", raw))

        raw = _document(entries=[_entry(effects=[
            _effect("bad_kind") | {"kind": []},
        ])])
        mutations.append(("effect.kind", raw))

        raw = _document(entries=[_entry(effects=[
            _effect() | {"target": []},
        ])])
        mutations.append(("effect.target", raw))

        raw = _document(entries=[_entry(effects=[
            _effect() | {"target": {"kind": 3}},
        ])])
        mutations.append(("effect.target.kind", raw))

        raw = _document(entries=[_entry(condition=3)])
        mutations.append(("entry.condition", raw))

        raw = _document(entries=[_entry(condition=[])])
        mutations.append(("entry.condition.list", raw))

        raw = _document(entries=[_entry(effects=[
            _effect(condition=[]),
        ])])
        mutations.append(("effect.condition.list", raw))

        raw = _document(entries=[_entry(effects=[
            _effect(condition=3),
        ])])
        mutations.append(("effect.condition.int", raw))

        for label, raw in mutations:
            with self.subTest(label=label):
                with self.assertRaises(GameplayContractError):
                    _parse(raw)

    def test_cyclic_and_shared_reference_inputs_fail_closed(self):
        cyclic_list = []
        cyclic_list.append(cyclic_list)
        cyclic_dict = {}
        cyclic_dict["self"] = cyclic_dict
        for label, cyclic in (
            ("list", cyclic_list),
            ("dict", cyclic_dict),
        ):
            with self.subTest(label=label):
                raw = _document()
                raw["entries"][0]["effects"][0]["payload"] = cyclic
                with self.assertRaisesRegex(GameplayContractError, "depth"):
                    _parse(raw)

        shared = [None] * 40_000
        raw = _document()
        raw["entries"][0]["effects"][0]["payload"] = [shared, shared]
        with self.assertRaisesRegex(GameplayContractError, "value limit"):
            _parse(raw)

    def test_plain_json_subclasses_and_scalar_edges(self):
        class DictSubclass(dict):
            pass

        class ListSubclass(list):
            pass

        raw = DictSubclass(_document())
        raw["display"]["tags"] = ListSubclass(["review"])
        parsed = _parse(raw)
        self.assertEqual(parsed.tags, ("review",))
        compile_skill_ir(parsed)

        _validate_json_shape({"flag": True, "count": 3, "ratio": 0.5})

        raw = _document()
        raw["identity"]["version"] = True
        with self.assertRaisesRegex(GameplayContractError, "positive integer"):
            _parse(raw)

    def test_oversized_integers_fail_closed_as_contract_errors(self):
        huge = 10 ** 400
        cases = []

        raw = _document()
        raw["costs"]["mana"] = huge
        cases.append(("costs.mana", raw))

        raw = _document(entries=[_entry(effects=[
            _effect() | {"amount": huge},
        ])])
        cases.append(("effect.amount", raw))

        raw = _document(entries=[_entry(condition={"all": [{
            "resource": {
                "subject": "self",
                "key": "hp",
                "comparator": "gt",
                "value": huge,
            },
        }]})])
        cases.append(("condition.value", raw))

        for label, raw in cases:
            with self.subTest(label=label):
                with self.assertRaises(GameplayContractError):
                    _parse(raw)

    def test_contract_errors_are_not_double_wrapped(self):
        raw = _document(entries=[_entry(effects=[
            _effect() | {"kind": "not_an_effect"},
        ])])
        with self.assertRaises(GameplayContractError) as caught:
            _parse(raw)
        message = str(caught.exception)
        self.assertIn(".kind is invalid", message)
        self.assertNotIn("delegated parse_skill_blueprint failed", message)

    def test_reserved_constructs_are_language_gaps_and_junk_is_schema_error(self):
        reserved_triggers = (
            ({"kind": "on_tick"}, "language_gap:on_tick"),
            ({"kind": "on_expire"}, "language_gap:on_expire"),
            ({"kind": "transition"}, "language_gap:transition"),
            ({"kind": "condition_enter"}, "language_gap:condition_enter"),
            ({"kind": "condition_exit"}, "language_gap:condition_exit"),
        )
        reserved_events = (
            "action_started",
            "attack_applied",
            "status_changed",
            "weather_changed",
            "resource_harvested",
        )
        for trigger, message in reserved_triggers:
            raw = _document()
            raw["entries"][0]["trigger"] = trigger
            with self.subTest(trigger=trigger):
                with self.assertRaisesRegex(GameplayContractError, f"^{message}"):
                    _parse(raw)
        for event in reserved_events:
            raw = _document()
            raw["entries"][0]["trigger"] = {
                "kind": "on_event",
                "event": event,
            }
            with self.subTest(event=event):
                with self.assertRaisesRegex(
                    GameplayContractError,
                    f"^language_gap:on_event:{event}",
                ):
                    _parse(raw)

        for trigger, message in (
            ({"kind": "junk"}, "kind is unknown"),
            ({"kind": "on_event", "event": "junk"}, "event is unknown"),
        ):
            raw = _document()
            raw["entries"][0]["trigger"] = trigger
            with self.subTest(trigger=trigger):
                with self.assertRaisesRegex(GameplayContractError, message) as caught:
                    _parse(raw)
                self.assertNotIn("language_gap", str(caught.exception))


class SkillIRReviewCompilerTests(unittest.TestCase):
    def test_status_duration_must_be_lowered_or_rejected_as_language_gap(self):
        for unit, amount in (
            ("world_tick", 7),
            ("combat_round", 2),
        ):
            raw = _document(
                status_duration={"unit": unit, "amount": amount},
            )
            with self.subTest(unit=unit):
                try:
                    parsed = _parse(raw)
                except GameplayContractError as error:
                    self.assertIn(
                        "language_gap",
                        str(error),
                        "accepted capability was rejected without a language gap",
                    )
                    continue
                compiled = compile_skill_ir(parsed)
                self.assertIsNotNone(
                    compiled.blueprints[0].duration,
                    "accepted status_duration was silently discarded",
                )
                self.assertEqual(compiled.blueprints[0].duration.unit, unit)
                self.assertEqual(compiled.blueprints[0].duration.amount, amount)

        try:
            first = compile_skill_ir(_parse(_document(
                status_duration={"unit": "world_tick", "amount": 1},
            )))
            second = compile_skill_ir(_parse(_document(
                status_duration={"unit": "world_tick", "amount": 7},
            )))
        except GameplayContractError as error:
            self.assertIn("language_gap", str(error))
        else:
            self.assertNotEqual(
                first.blueprints[0].canonical_hash,
                second.blueprints[0].canonical_hash,
                "two accepted lifecycle durations lowered identically",
            )

    def test_recursive_key_permutation_preserves_ir_and_lowered_hashes(self):
        raw = _document(entries=[
            _entry(
                condition={"all": [None, {
                    "not": {"resource": {
                        "subject": "self",
                        "key": "hp",
                        "comparator": "gt",
                        "value": 10,
                    }},
                }]},
                effects=[_effect(condition={
                    "field": {
                        "subject": "current_area",
                        "key": "heat",
                        "comparator": "gte",
                        "value": 0.5,
                    },
                })],
            ),
            _entry(
                "reaction",
                on_use=False,
                effects=[_effect("guard", "shield", target="self", amount=3)],
            ),
        ])
        permuted = _reverse_mappings(raw)
        first = compile_skill_ir(_parse(raw))
        second = compile_skill_ir(_parse(permuted))
        self.assertEqual(first.canonical_hash, second.canonical_hash)
        self.assertEqual(
            [item.canonical_hash for item in first.blueprints],
            [item.canonical_hash for item in second.blueprints],
        )
        self.assertEqual(first.metadata, second.metadata)
        self.assertEqual(first.preview, second.preview)

    def test_single_on_use_lowered_hash_matches_handwritten_v04(self):
        raw = _document(
            entries=[_entry(
                "active",
                effects=[_effect("pulse", "damage", amount=4)],
            )],
            mana=4.0,
            duration=1,
            budget=40.0,
        )
        authority = _authority("damage")
        compiled = compile_skill_ir(_parse(raw, authority=authority))
        handwritten = {
            "protocol": "pmw-gameplay-v0.4",
            "kind": "skill_blueprint",
            "id": "p2r_skill__active",
            "version": 1,
            "trigger": "on_use",
            "condition": None,
            "duration": None,
            "cost": {"duration": 1, "mana": 4.0},
            "scope": {
                "selectors": ["target_actor"],
                "relation_types": [],
            },
            "effects": [{
                "id": "pulse",
                "kind": "damage",
                "target": {"kind": "target_actor"},
                "commitment": "required",
                "amount": 4,
            }],
            "budget": {"limit": 40.0},
            "max_firings_per_root": 1,
            "material_ids": [MATERIAL_ID],
        }
        legacy = parse_skill_blueprint(
            handwritten,
            basic_registry().statuses,
            authority,
        )
        self.assertEqual(
            compiled.blueprints[0].canonical_hash,
            legacy.canonical_hash,
        )
        self.assertEqual(
            compiled.metadata_by_ir_hash[compiled.canonical_hash][0].canonical_hash,
            legacy.canonical_hash,
        )

    def test_lowered_id_overflow_is_rejected(self):
        raw = _document(entries=[_entry("bb")])
        raw["identity"]["id"] = "a" * 62
        with self.assertRaisesRegex(GameplayContractError, "lowered_id"):
            _parse(raw)

    def test_mutating_the_input_after_parse_does_not_alter_the_ir(self):
        raw = _document(entries=[_entry(effects=[
            _effect(condition={"not": None}),
        ])])
        parsed = _parse(raw)
        before_ir_hash = parsed.canonical_hash
        before_blueprint = compile_skill_ir(parsed).blueprints[0]

        raw["identity"]["name"] = "mutated"
        raw["entries"][0]["effects"][0]["amount"] = 999
        raw["entries"][0]["effects"][0]["condition"]["not"] = {
            "all": [None],
        }

        self.assertEqual(parsed.name, "Independent P2.1 review skill")
        self.assertEqual(parsed.canonical_hash, before_ir_hash)
        after_blueprint = compile_skill_ir(parsed).blueprints[0]
        self.assertEqual(
            after_blueprint.canonical_hash,
            before_blueprint.canonical_hash,
        )
        self.assertEqual(after_blueprint.effects[0].amount, 4.0)

    def test_trusted_ir_cannot_silently_diverge_from_its_hash_metadata(self):
        parsed = _parse(_document())
        original = compile_skill_ir(parsed)
        parsed.entries[0].effects[0]["amount"] = 999

        try:
            recompiled = compile_skill_ir(parsed)
        except (TypeError, GameplayContractError):
            self.fail("mutating reachable parsed data invalidated trusted compilation")
        self.assertEqual(
            recompiled.blueprints[0].canonical_hash,
            original.blueprints[0].canonical_hash,
            "mutating the trusted IR changed its lowered semantics",
        )
        self.assertEqual(recompiled.canonical_hash, original.canonical_hash)
        self.assertEqual(recompiled.blueprints[0].effects[0].amount, 4.0)

    def test_self_consistent_canonical_document_gets_full_ir_validation(self):
        cases = []

        raw = _document()
        raw["entries"] = []
        cases.append(("empty entries", raw))

        raw = _document(entries=[
            _entry("active"),
            _entry("active", on_use=False),
        ])
        cases.append(("duplicate entry ids", raw))

        raw = _document(entries=[
            _entry("one"),
            _entry("two"),
        ])
        cases.append(("two on_use entries", raw))

        raw = _document(selectors=("self",))
        cases.append(("effect outside declared selectors", raw))

        raw = _document(selectors=("linked_object",), relation_types=())
        cases.append(("linked_object without relation", raw))

        raw = _document(
            entries=[
                _entry(
                    "active",
                    effects=[_effect("strike", amount=2)],
                ),
                _entry(
                    "reaction",
                    on_use=False,
                    effects=[_effect("counter", amount=2)],
                ),
            ],
            budget=3.0,
        )
        cases.append(("shared budget overflow", raw))

        raw = _document()
        raw["origin"]["source"] = "untrusted"
        cases.append(("invalid origin source", raw))

        raw = _document()
        raw["origin"]["model"] = "m" * 129
        cases.append(("model over bound", raw))

        raw = _document()
        raw["display"]["summary"] = "s" * 241
        cases.append(("summary over bound", raw))

        for label, document in cases:
            with self.subTest(label=label):
                forged = _force_canonical_document(
                    _parse(_document()), document
                )
                with self.assertRaises(GameplayContractError):
                    compile_skill_ir(forged)

    def test_compile_recomputes_condition_nodes_from_canonical_document(self):
        parsed = _parse(_document())
        expected = parsed.condition_nodes
        object.__setattr__(parsed, "condition_nodes", 999)

        compiled = compile_skill_ir(parsed)
        self.assertEqual(compiled.ir.condition_nodes, expected)
        self.assertEqual(compiled.preview["condition_nodes"], expected)

    def test_identity_model_and_display_length_boundaries(self):
        cases = (
            (("identity", "name"), 80, 81),
            (("identity", "description"), 600, 601),
            (("origin", "model"), 128, 129),
        )
        for path, maximum, over in cases:
            section, field = path
            raw = _document()
            raw[section][field] = "x" * maximum
            with self.subTest(field=path, boundary="maximum"):
                _parse(raw)

            raw[section][field] = "x" * over
            with self.subTest(field=path, boundary="over"):
                with self.assertRaisesRegex(
                    GameplayContractError, str(maximum)
                ):
                    _parse(raw)

    def test_compile_ignores_forged_skill_ir_value_fields(self):
        parsed = _parse(_document())
        baseline = compile_skill_ir(parsed)
        forged_values = {
            "id": "forged_skill",
            "version": 99,
            "name": "forged",
            "description": "forged",
            "origin_source": "generated",
            "origin_model": "forged",
            "context_hash": "0" * 64,
            "material_ids": ("other_material",),
            "traits": (),
            "selectors": (),
            "relation_types": (),
            "mana": 999.0,
            "duration": 999,
            "entries": (),
            "status_duration": {"unit": "world_tick", "amount": 7},
            "budget": 999.0,
            "summary": "forged",
            "tags": (),
            "condition_nodes": 999,
        }

        for field, value in forged_values.items():
            with self.subTest(field=field):
                forged = dataclasses.replace(parsed, **{field: value})
                compiled = compile_skill_ir(forged)
                self.assertEqual(
                    compiled.ir.canonical_json,
                    baseline.ir.canonical_json,
                )
                self.assertEqual(
                    compiled.ir.canonical_hash,
                    baseline.ir.canonical_hash,
                )
                self.assertEqual(compiled.ir.id, baseline.ir.id)
                self.assertEqual(compiled.ir.name, baseline.ir.name)
                self.assertEqual(
                    [item.canonical_hash for item in compiled.blueprints],
                    [item.canonical_hash for item in baseline.blueprints],
                )

        for field, value in (
            ("canonical_hash", "0" * 64),
            ("canonical_json", "{}"),
            ("authority", _authority("heal")),
            ("condition_limits", object()),
            ("statuses", object()),
        ):
            with self.subTest(field=field):
                forged = dataclasses.replace(parsed, **{field: value})
                with self.assertRaises(GameplayContractError):
                    compile_skill_ir(forged)

    def test_compile_revalidates_malformed_nested_canonical_payloads(self):
        documents = []

        raw = _document(entries=[_entry(effects=[
            _effect() | {"target": []},
        ])])
        documents.append(("list target", raw))

        raw = _document(entries=[_entry(effects=[
            _effect() | {"target": {"kind": 3}},
        ])])
        documents.append(("non-text target kind", raw))

        raw = _document(entries=[_entry(effects=[
            _effect() | {"kind": []},
        ])])
        documents.append(("list effect kind", raw))

        raw = _document(entries=[_entry(condition=[])])
        documents.append(("list entry condition", raw))

        raw = _document(entries=[_entry(effects=[
            _effect(condition=3),
        ])])
        documents.append(("integer effect condition", raw))

        raw = _document(entries=[_entry(
            condition={"all": [{"not": []}, 3]},
        )])
        documents.append(("malformed nested condition", raw))

        for label, document in documents:
            with self.subTest(label=label):
                forged = _force_canonical_document(
                    _parse(_document()), document
                )
                with self.assertRaises(GameplayContractError):
                    compile_skill_ir(forged)

    def test_parse_deeply_nested_untrusted_input_fails_closed(self):
        raw = _document()
        nested = None
        for _ in range(500):
            nested = [nested]
        raw["entries"][0]["effects"][0]["payload"] = nested

        with self.assertRaises(GameplayContractError):
            _parse(raw)

        parsed = _parse(_document())
        for label, text in (
            ("invalid JSON", "{"),
            ("non-object JSON", "null"),
            ("deep JSON nesting", "[" * 2000 + "]" * 2000),
        ):
            with self.subTest(label=label):
                forged = dataclasses.replace(
                    parsed,
                    canonical_json=text,
                    canonical_hash=hashlib.sha256(
                        text.encode("utf-8")
                    ).hexdigest(),
                )
                with self.assertRaises(GameplayContractError):
                    compile_skill_ir(forged)

    def test_duplicate_json_keys_compile_only_their_fresh_legal_parse(self):
        parsed = _parse(_document())
        text = parsed.canonical_json.replace(
            '"identity":{',
            '"identity":{"name":"overridden",',
            1,
        )
        self.assertNotEqual(
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
            parsed.canonical_hash,
        )

        forged = dataclasses.replace(
            parsed,
            canonical_json=text,
            canonical_hash=parsed.canonical_hash,
        )
        compiled = compile_skill_ir(forged)
        fresh = parse_skill_ir(
            json.loads(text),
            basic_registry().statuses,
            _authority("damage", "shield"),
        )
        self.assertEqual(compiled.ir.canonical_hash, fresh.canonical_hash)
        self.assertEqual(compiled.ir.name, fresh.name)
        self.assertEqual(
            [item.canonical_hash for item in compiled.blueprints],
            [
                item.canonical_hash
                for item in compile_skill_ir(fresh).blueprints
            ],
        )

    def test_forged_condition_limits_stay_within_trusted_condition_caps(self):
        parsed = _parse(_document())

        tighter = dataclasses.replace(
            parsed,
            condition_limits=ConditionLimits(max_nodes=1),
        )
        with self.assertRaisesRegex(GameplayContractError, "max_nodes 1"):
            compile_skill_ir(tighter)

        for limits in (
            object(),
            ConditionLimits(
                max_depth=64,
                max_nodes=4096,
                max_children=256,
            ),
            ConditionLimits(
                max_depth=1,
                max_nodes=4096,
                max_children=256,
            ),
        ):
            with self.subTest(limits=limits):
                try:
                    compiled = compile_skill_ir(dataclasses.replace(
                        parsed,
                        condition_limits=limits,
                    ))
                except GameplayContractError:
                    continue
                fresh = parse_skill_ir(
                    json.loads(parsed.canonical_json),
                    basic_registry().statuses,
                    _authority("damage", "shield"),
                    condition_limits=limits,
                )
                self.assertEqual(
                    compiled.ir.canonical_hash,
                    fresh.canonical_hash,
                )
                self.assertEqual(
                    compiled.preview["condition_nodes"],
                    fresh.condition_nodes,
                )


class SkillIRReviewFormalRuntimeTests(unittest.TestCase):
    def test_two_entry_ir_runs_independently_for_player_and_npc(self):
        raw = _document(
            entries=[
                _entry(
                    "active",
                    effects=[_effect("strike", "damage", amount=3)],
                ),
                _entry(
                    "reaction",
                    on_use=False,
                    effects=[_effect(
                        "guard",
                        "shield",
                        target="self",
                        amount=2,
                    )],
                ),
            ],
            budget=4.5,
            mana=5.0,
            duration=1,
            selectors=("self", "target_actor"),
            material_id=P1_MATERIAL_ID,
        )
        compiled = compile_skill_ir(_parse(
            raw,
            authority=_authority(
                "damage",
                "shield",
                selectors=("self", "target_actor"),
                budget=40.0,
                material_id=P1_MATERIAL_ID,
            ),
        ))
        active, passive = compiled.blueprints
        runtime, _ = _formal_runtime(
            _world(
                [_field(
                    "heat",
                    initial=1.0,
                    target=1.0,
                    rate=0.0,
                    curve="none",
                )],
                time_budget=20,
            ),
            compiled.blueprints,
        )

        for round_index, actor_id, target_id, request_id in (
            (1, P1_PLAYER, P1_NPC, "p2r_hit_player"),
            (2, P1_NPC, P1_PLAYER, "p2r_hit_npc"),
        ):
            outcome = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(request_id, actor_id, active.id, target_id),
            )
            actor = _actor_state(runtime, actor_id)
            target = _actor_state(runtime, target_id)
            self.assertEqual(outcome.action.cost.mana, 5.0)
            self.assertEqual(outcome.action.cost.duration, 1)
            self.assertEqual(outcome.time.duration, 1)
            self.assertEqual(actor["mana"], 25.0)
            self.assertEqual(target["hp"], 47.0)
            self.assertEqual(target["shield"], 2.0)
            fired = [
                row for row in _records(outcome.action)
                if row.status == "fired" and row.owner == target_id
            ]
            self.assertEqual(len(fired), 1)
            self.assertEqual(
                fired[0].hook_id,
                f"passive_{passive.id}_v1",
            )
            budget = _budget(runtime)
            self.assertEqual(budget["spent_ticks"], round_index)
            self.assertEqual(budget["remaining_ticks"], 20 - round_index)

        combat = run_combat_round(
            runtime.session,
            runtime.action_registry,
            round_index=3,
            actor_order=(P1_PLAYER, P1_NPC),
            requests={
                P1_PLAYER: ActionRequest(
                    "p2r_combat_player",
                    P1_PLAYER,
                    active.id,
                    P1_NPC,
                ),
                P1_NPC: ActionRequest(
                    "p2r_combat_npc",
                    P1_NPC,
                    active.id,
                    P1_PLAYER,
                ),
            },
        )
        player = _actor_state(runtime, P1_PLAYER)
        npc = _actor_state(runtime, P1_NPC)
        self.assertEqual(player["mana"], 20.0)
        self.assertEqual(npc["mana"], 20.0)
        self.assertEqual(player["hp"], 46.0)
        self.assertEqual(npc["hp"], 46.0)
        self.assertEqual(player["shield"], 2.0)
        self.assertEqual(npc["shield"], 2.0)
        self.assertEqual(combat.time_spend_result.duration, 1)
        budget = _budget(runtime)
        self.assertEqual(budget["spent_ticks"], 3)
        self.assertEqual(budget["remaining_ticks"], 17)


def p2_text_bound_probe():
    """Non-collected P3 context-size probe; intentionally makes no assertion."""
    text = "x" * 1_000_000
    results = {}
    for field_name in ("name", "description"):
        raw = _document()
        raw["identity"][field_name] = text
        parsed = _parse(raw)
        results[f"identity.{field_name}"] = {
            "accepted": True,
            "canonical_json_bytes": len(parsed.canonical_json.encode("utf-8")),
            "canonical_hash": parsed.canonical_hash,
        }

    raw = _document()
    raw["origin"]["model"] = text
    parsed = _parse(raw)
    results["origin.model"] = {
        "accepted": True,
        "canonical_json_bytes": len(parsed.canonical_json.encode("utf-8")),
        "canonical_hash": parsed.canonical_hash,
    }
    results["probe_sha256"] = hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()
    return results


def p2_ir_mutation_hash_probe():
    """Non-collected defect witness, separated from requirement assertions."""
    parsed = _parse(_document())
    original = compile_skill_ir(parsed)
    parsed.entries[0].effects[0]["amount"] = 999
    changed = compile_skill_ir(parsed)
    return {
        "ir_hash_unchanged": changed.canonical_hash == original.canonical_hash,
        "lowered_hash_changed": (
            changed.blueprints[0].canonical_hash
            != original.blueprints[0].canonical_hash
        ),
        "metadata_matches_changed_lowered_hash": (
            changed.metadata[0].canonical_hash
            == changed.blueprints[0].canonical_hash
        ),
        "original_lowered_hash": original.blueprints[0].canonical_hash,
        "changed_lowered_hash": changed.blueprints[0].canonical_hash,
        "ir_hash": changed.canonical_hash,
    }


if __name__ == "__main__":
    unittest.main()
