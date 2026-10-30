from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ACTOR_COMPONENT,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import (
    run_combat_round,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    ConditionLimits,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_ir import (
    compile_skill_ir,
    parse_skill_ir,
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
PLAYER = "p2_player"
NPC = "p2_npc"
AREA = "p2_area"
OTHER_AREA = "p2_other_area"
MATERIAL_ID = "p2_material"
CLOCK_ID = "pmw:v04:clock"


def _material(
    *kinds: str,
    selectors: tuple[str, ...] = ("self", "target_actor", "current_area"),
    budget: float = 40.0,
):
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "p2_authority",
            "effect_kinds": list(kinds),
            "selectors": list(selectors),
            "budget_points": budget,
        }],
    })


def _authority(
    *kinds: str,
    selectors: tuple[str, ...] = ("self", "target_actor", "current_area"),
    budget: float = 40.0,
):
    return material_authority((
        _material(*kinds, selectors=selectors, budget=budget),
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
    if condition is not None:
        result["condition"] = condition
    if kind == "damage":
        result.setdefault("amount", 4)
    return result


def _entry(
    entry_id: str = "active",
    *,
    on_use: bool = True,
    effects=None,
    condition=None,
    max_firings: int = 1,
):
    if not isinstance(condition, dict) and condition is not None:
        raise AssertionError("condition fixture must be a dict or None")
    return {
        "id": entry_id,
        "trigger": (
            {"kind": "on_use"}
            if on_use else {"kind": "on_event", "event": "damage_resolved"}
        ),
        "condition": condition,
        "effects": effects or [_effect()],
        "max_firings_per_root": max_firings,
    }


def _document(
    *,
    entries=None,
    budget: float = 40.0,
    selectors=("self", "target_actor", "current_area"),
    relation_types=(),
    mana: float = 4.0,
    duration: int = 1,
    summary: str = "A deterministic preview fixture.",
):
    return {
        "protocol": "pmw-skill-ir-v1",
        "identity": {
            "id": "p2_skill",
            "version": 1,
            "name": "P2 Skill",
            "description": "Skill IR owner conformance fixture.",
        },
        "origin": {
            "source": "authored",
            "model": None,
            "context_hash": None,
            "material_ids": [MATERIAL_ID],
        },
        "capability": {"traits": ["p2_trait"]},
        "targeting": {
            "selectors": list(selectors),
            "relation_types": list(relation_types),
        },
        "costs": {"mana": mana, "duration": duration},
        "entries": entries or [_entry()],
        "lifecycle": {"status_duration": None},
        "limits": {"budget": budget},
        "display": {"summary": summary, "tags": ["test"]},
    }


def _parse(raw, *, authority=None, limits=None):
    return parse_skill_ir(
        raw,
        basic_registry().statuses,
        authority or _authority("damage", "shield", "modify_field"),
        condition_limits=limits,
    )


def _node_tree(nodes: int):
    if nodes not in (1, *range(53, 65)):
        raise AssertionError("node fixture sizes are 1 or 53..64")
    if nodes == 1:
        return {"all": [None]}
    sizes = (16, 16, 16, nodes - 53)
    return {
        "all": [
            {"all": [None] * size}
            for size in sizes
        ]
    }


def _actor(actor_id: str, controller: str, *, mana: float = 30.0):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": f"{actor_id}_blueprint",
        "hp": {"max": 50.0, "initial": 50.0},
        "mana": {"max": 100.0, "initial": mana, "dynamics": None},
        "attributes": {
            "power": 4.0,
            "control": 4.0,
            "resilience": 4.0,
            "agility": 4.0,
        },
        "traits": [],
    })
    return instantiate_actor(blueprint, actor_id, controller=controller)


def _area(area_id: str):
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": f"{area_id}_blueprint",
        "fields": [{
            "id": "heat",
            "domain": {"min": 0.0, "max": 10.0},
            "initial": 1.0,
            "target": 1.0,
            "rate": 0.0,
            "curve": "none",
            "max_persistent_patches": 3,
            "max_temporary_modifiers": 3,
        }],
    })
    return instantiate_area(blueprint, area_id)


def _world():
    areas = {AREA: _area(AREA), OTHER_AREA: _area(OTHER_AREA)}
    actors = {
        PLAYER: _actor(PLAYER, "human"),
        NPC: _actor(NPC, "ai"),
    }
    world = build_gameplay_world(
        "p2_ir_world",
        areas=areas.values(),
        actors=actors.values(),
        placements=((PLAYER, AREA), (NPC, AREA)),
    )
    for entity in (*areas.values(), *actors.values()):
        world.entities[entity.id] = entity
    world.entities[CLOCK_ID] = clock_entity()
    return initialize_time_budget(world, 20)


class SkillIRSchemaTests(unittest.TestCase):
    def assert_rejected(self, raw, pattern: str = ""):
        with self.assertRaisesRegex(GameplayContractError, pattern):
            _parse(raw)

    def test_schema_rejection_matrix(self):
        mutations = []
        raw = deepcopy(_document())
        raw["junk"] = True
        mutations.append((raw, "unknown"))
        raw = deepcopy(_document())
        del raw["display"]
        mutations.append((raw, "missing"))
        raw = deepcopy(_document())
        raw["protocol"] = "pmw-skill-ir-v2"
        mutations.append((raw, "protocol"))
        raw = deepcopy(_document())
        raw["identity"]["id"] = "Bad-ID"
        mutations.append((raw, "identity.id"))
        raw = deepcopy(_document())
        raw["identity"]["version"] = True
        mutations.append((raw, "positive integer"))
        raw = deepcopy(_document())
        raw["origin"]["source"] = "model"
        mutations.append((raw, "origin.source"))
        raw = deepcopy(_document())
        raw["origin"]["context_hash"] = "A" * 64
        mutations.append((raw, "context_hash"))
        raw = deepcopy(_document())
        raw["origin"]["material_ids"] = ["other_material"]
        mutations.append((raw, "material authority"))
        raw = deepcopy(_document())
        raw["targeting"]["selectors"] = ["self", "self"]
        mutations.append((raw, "duplicates"))
        raw = deepcopy(_document())
        raw["costs"]["mana"] = True
        mutations.append((raw, "finite numeric"))
        raw = deepcopy(_document())
        raw["costs"]["duration"] = float("inf")
        mutations.append((raw, "positive integer"))
        raw = deepcopy(_document())
        raw["entries"] = []
        mutations.append((raw, "1..4"))
        raw = deepcopy(_document())
        raw["entries"] = [_entry(f"e{index}") for index in range(5)]
        mutations.append((raw, "1..4"))
        raw = deepcopy(_document())
        raw["entries"] = [
            _entry("active_one"),
            _entry("active_two"),
        ]
        mutations.append((raw, "at most one on_use"))
        raw = deepcopy(_document())
        raw["entries"][0]["id"] = "same"
        raw["entries"].append(_entry("same", on_use=False))
        mutations.append((raw, "duplicate IDs"))
        raw = deepcopy(_document())
        raw["entries"][0]["effects"] = []
        mutations.append((raw, "non-empty"))
        raw = deepcopy(_document())
        raw["entries"][0]["max_firings_per_root"] = 0
        mutations.append((raw, "integer in \\[1, 8\\]"))
        raw = deepcopy(_document())
        raw["limits"]["budget"] = float("nan")
        mutations.append((raw, "finite numeric"))
        raw = deepcopy(_document())
        raw["display"]["summary"] = "x" * 241
        mutations.append((raw, "240"))
        raw = deepcopy(_document())
        raw["display"]["tags"] = [f"tag_{index}" for index in range(9)]
        mutations.append((raw, "8 tags"))
        raw = deepcopy(_document())
        raw["entries"][0]["trigger"] = {"kind": "on_use", "junk": True}
        mutations.append((raw, "unknown fields"))
        raw = deepcopy(_document())
        raw["entries"][0]["trigger"] = {"kind": "junk"}
        mutations.append((raw, "kind is unknown"))
        raw = deepcopy(_document())
        raw["entries"][0]["trigger"] = {"kind": "on_event", "event": "junk"}
        mutations.append((raw, "event is unknown"))
        raw = deepcopy(_document())
        raw["identity"]["id"] = "skill"
        raw["entries"][0]["id"] = "entry"
        del raw["entries"][0]["effects"]
        mutations.append((raw, "missing"))
        for index, (candidate, pattern) in enumerate(mutations):
            with self.subTest(index=index, pattern=pattern):
                self.assert_rejected(candidate, pattern)

    def test_language_gap_triggers(self):
        trigger_cases = (
            ({"kind": "on_tick"}, "language_gap:on_tick"),
            ({"kind": "on_expire"}, "language_gap:on_expire"),
            ({"kind": "transition"}, "language_gap:transition"),
            (
                {"kind": "on_event", "event": "action_started"},
                "language_gap:on_event:action_started",
            ),
            (
                {"kind": "on_event", "event": "attack_applied"},
                "language_gap:on_event:attack_applied",
            ),
            (
                {"kind": "on_event", "event": "status_changed"},
                "language_gap:on_event:status_changed",
            ),
            (
                {"kind": "on_event", "event": "weather_changed"},
                "language_gap:on_event:weather_changed",
            ),
            (
                {"kind": "on_event", "event": "resource_harvested"},
                "language_gap:on_event:resource_harvested",
            ),
        )
        for trigger, message in trigger_cases:
            raw = _document()
            raw["entries"][0]["trigger"] = trigger
            with self.subTest(trigger=trigger):
                with self.assertRaisesRegex(
                    GameplayContractError, f"^{message}"
                ):
                    _parse(raw)


class SkillIRBudgetTests(unittest.TestCase):
    def test_shared_condition_budget_exact_boundary(self):
        limits = ConditionLimits(max_nodes=64)
        raw = _document()
        raw["entries"][0]["effects"][0]["condition"] = _node_tree(63)
        exact = _parse(raw, limits=limits)
        self.assertEqual(exact.condition_nodes, 64)
        parsed = parse_condition(
            raw["entries"][0]["effects"][0]["condition"],
            limits=limits,
        )

        def parsed_nodes(spec):
            return 1 + sum(parsed_nodes(child) for child in spec.children)

        self.assertEqual(exact.condition_nodes, parsed_nodes(parsed) + 1)

        raw["entries"][0]["effects"][0]["condition"] = {
            "all": [_node_tree(63), None]
        }
        with self.assertRaisesRegex(GameplayContractError, "max_nodes 64"):
            _parse(raw, limits=limits)

    def test_shared_condition_budget_aggregates_effect_conditions(self):
        limits = ConditionLimits(max_nodes=64)
        entries = [
            _entry("condition_a", effects=[_effect("a")]),
            _entry(
                "condition_b",
                on_use=False,
                effects=[_effect("b", condition=_node_tree(61))],
                condition=None,
            ),
        ]
        raw = _document(entries=entries)
        exact = _parse(raw, limits=limits)
        self.assertEqual(exact.condition_nodes, 64)
        raw["entries"][1]["condition"] = {"not": None}
        with self.assertRaisesRegex(GameplayContractError, "max_nodes 64"):
            _parse(raw, limits=limits)

    def test_shared_condition_budget_counts_effect_conditions(self):
        raw = _document(entries=[_entry(
            effects=[
                _effect("first", condition=_node_tree(63)),
            ]
        )])
        self.assertEqual(_parse(raw).condition_nodes, 64)
        raw["entries"][0]["effects"][0]["condition"] = {
            "all": [_node_tree(63), None]
        }
        with self.assertRaisesRegex(GameplayContractError, "max_nodes 64"):
            _parse(raw)

    def test_multi_entry_material_bypass_rejected(self):
        # Each bundle fits 20 alone; the two lowered entries do not fit
        # one shared document budget once the passive surcharge is included.
        def bundle(prefix: str):
            return [
                _effect(f"{prefix}_damage", "damage", amount=2),
                {
                    "id": f"{prefix}_status",
                    "target": {"kind": "self"},
                    "commitment": "required",
                    "kind": "add_resource",
                    "resource": "mana",
                    "amount": 2,
                },
                _effect(
                    f"{prefix}_field",
                    "modify_field",
                    target="current_area",
                    field_id="heat",
                    amount=0.1,
                ),
                {
                    "id": f"{prefix}_trait",
                    "kind": "grant_trait",
                    "target": {"kind": "self"},
                    "commitment": "required",
                    "trait_id": "p2_trait",
                    "duration": 2,
                },
                _effect(
                    f"{prefix}_attractor",
                    "modify_attractor",
                    target="current_area",
                    field_id="heat",
                    amount=0.2,
                    duration=2,
                ),
            ]

        entries = [
            _entry("active", effects=bundle("active")),
            _entry(
                "passive",
                on_use=False,
                effects=bundle("passive"),
            ),
        ]
        low_limit = 20
        authority = _authority(
            "damage", "add_resource", "modify_field", "grant_trait",
            "modify_attractor", budget=40,
        )
        active_blueprint = compile_skill_ir(
            _parse(
                _document(entries=[entries[0]], budget=low_limit),
                authority=authority,
            )
        ).blueprints[0]
        passive_blueprint = compile_skill_ir(
            _parse(
                _document(entries=[entries[1]], budget=low_limit),
                authority=authority,
            )
        ).blueprints[0]
        self.assertLessEqual(active_blueprint.budget_used, low_limit)
        self.assertLessEqual(passive_blueprint.budget_used, low_limit)
        self.assertGreater(
            active_blueprint.budget_used + passive_blueprint.budget_used,
            low_limit,
        )
        with self.assertRaisesRegex(
            GameplayContractError, "shared document budget"
        ):
            _parse(
                _document(entries=entries, budget=low_limit),
                authority=authority,
            )

    def test_shared_material_budget_exact_boundary(self):
        authority = _authority("damage", "shield", budget=40)
        entries = [
            _entry(
                "active",
                effects=[_effect("active_damage", "damage", amount=4)],
            ),
            _entry(
                "reaction",
                on_use=False,
                effects=[{
                    "id": "reaction_shield",
                    "kind": "shield",
                    "target": {"kind": "self"},
                    "commitment": "required",
                    "amount": 3,
                }],
            ),
        ]
        exact = _parse(
            _document(entries=entries, budget=4.5),
            authority=authority,
        )
        self.assertEqual(
            sum(
                item.budget_used
                for item in compile_skill_ir(exact).blueprints
            ),
            4.5,
        )
        with self.assertRaisesRegex(
            GameplayContractError, "shared document budget"
        ):
            _parse(
                _document(entries=entries, budget=4.49),
                authority=authority,
            )

    def test_authority_exceeded_by_effect_kind_and_selector(self):
        raw = _document(entries=[_entry(
            effects=[_effect("heal", "heal", amount=2)]
        )])
        with self.assertRaisesRegex(GameplayContractError, "effect authorization"):
            _parse(raw, authority=_authority("damage"))

        raw = _document(
            selectors=("self", "target_actor", "current_area", "adjacent_area"),
            entries=[_entry(effects=[_effect(target="adjacent_area")])],
        )
        with self.assertRaisesRegex(
            GameplayContractError, "scope authorization"
        ):
            _parse(
                raw,
                authority=_authority(
                    "damage",
                    selectors=("self", "target_actor", "current_area"),
                ),
            )

        raw = _document()
        raw["entries"][0]["effects"][0]["target"] = {"kind": "adjacent_area"}
        with self.assertRaisesRegex(GameplayContractError, "targeting selectors"):
            _parse(
                raw,
                authority=_authority(
                    "damage",
                    selectors=(
                        "self", "target_actor", "current_area", "adjacent_area",
                    ),
                ),
            )

        raw = _document(budget=41)
        with self.assertRaisesRegex(GameplayContractError, "material authority"):
            _parse(raw, authority=_authority("damage", budget=40))

    def test_relation_scope_requires_named_relation_type(self):
        raw = _document(
            selectors=("self", "target_actor", "current_area", "linked_object"),
            relation_types=("supply_link",),
            entries=[_entry(effects=[_effect(
                "linked_damage",
                "damage",
                target="linked_object",
            )])],
        )
        raw["entries"][0]["effects"][0]["target"] = {
            "kind": "linked_object",
            "relation_type": "supply_link",
        }
        parsed = _parse(
            raw,
            authority=_authority(
                "damage",
                selectors=(
                    "self", "target_actor", "current_area", "linked_object",
                ),
            ),
        )
        self.assertEqual(parsed.relation_types, ("supply_link",))

        raw["entries"][0]["effects"][0]["target"]["relation_type"] = "other_link"
        with self.assertRaisesRegex(
            GameplayContractError, "relation types"
        ):
            _parse(
                raw,
                authority=_authority(
                    "damage",
                    selectors=(
                        "self", "target_actor", "current_area",
                        "linked_object",
                    ),
                ),
            )

        no_relation_prefix = _document(
            selectors=("self", "target_actor", "current_area", "linked_object"),
            relation_types=(),
        )
        with self.assertRaisesRegex(
            GameplayContractError, "explicit relation type"
        ):
            _parse(
                no_relation_prefix,
                authority=_authority(
                    "damage",
                    selectors=(
                        "self", "target_actor", "current_area",
                        "linked_object",
                    ),
                ),
            )


class SkillIRCompilerTests(unittest.TestCase):
    def test_hash_parity_with_handwritten_v04(self):
        raw = _document()
        parsed = _parse(raw)
        compiled = compile_skill_ir(parsed)
        hand_written = {
            "protocol": "pmw-gameplay-v0.4",
            "kind": "skill_blueprint",
            "id": "p2_skill__active",
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
            hand_written,
            basic_registry().statuses,
            _authority("damage"),
        )
        self.assertEqual(
            compiled.blueprints[0].canonical_hash,
            legacy.canonical_hash,
        )
        self.assertEqual(
            compiled.metadata[0].canonical_hash,
            legacy.canonical_hash,
        )
        self.assertEqual(
            compiled.metadata_by_ir_hash[compiled.canonical_hash],
            compiled.metadata,
        )

    def test_hash_and_key_order_determinism(self):
        raw = _document(entries=[
            _entry(),
            _entry(
                "reaction",
                on_use=False,
                effects=[{
                    "id": "reaction_shield",
                    "kind": "shield",
                    "target": {"kind": "self"},
                    "commitment": "required",
                    "amount": 3,
                }],
            ),
        ])
        reversed_raw = {
            key: raw[key]
            for key in reversed(list(raw))
        }
        first = compile_skill_ir(_parse(raw))
        second = compile_skill_ir(_parse(reversed_raw))
        self.assertEqual(first.canonical_hash, second.canonical_hash)
        self.assertEqual(first.blueprints, second.blueprints)
        self.assertEqual(first.metadata, second.metadata)
        self.assertEqual(first.operators, second.operators)
        self.assertEqual(first.state_classes, second.state_classes)
        self.assertEqual(first.preview, second.preview)
        self.assertEqual(
            first.blueprints[0].canonical_hash,
            second.blueprints[0].canonical_hash,
        )
        self.assertEqual(
            first.blueprints[1].canonical_hash,
            second.blueprints[1].canonical_hash,
        )

    def test_operator_and_state_class_catalog(self):
        entries = [
            _entry(
                "impulse",
                effects=[
                    _effect("damage_effect", "damage"),
                    _effect(
                        "trait_effect",
                        "grant_trait",
                        trait_id="warmed",
                        duration=2,
                    ),
                    _effect(
                        "field_effect",
                        "modify_field",
                        target="current_area",
                        field_id="heat",
                        amount=0.2,
                    ),
                    _effect(
                        "process_effect",
                        "process_start",
                        target="current_area",
                        process_template_id="p2_process",
                    ),
                ],
            ),
        ]
        raw = _document(entries=entries)
        authority = _authority(
            "damage", "grant_trait", "modify_field", "process_start",
        )
        compiled = compile_skill_ir(_parse(raw, authority=authority))
        self.assertEqual(
            set(compiled.operators),
            {
                "impulse", "process_start",
            },
        )
        self.assertEqual(
            set(compiled.state_classes),
            {"Field", "Stock", "Process", "Discrete"},
        )
        self.assertNotIn(compiled.ir.summary, repr(compiled.preview))
        self.assertEqual(
            compiled.preview["effect_kinds"],
            (
                "damage", "grant_trait", "modify_field",
                "process_start",
            ),
        )

    def test_derived_condition_classifies_read_only_coverage(self):
        derived_condition = {
            "derived": {
                "subject": "current_area",
                "key": "heat_index",
                "comparator": "gte",
                "value": 0.5,
            }
        }
        raw = _document(entries=[_entry(
            effects=[{
                "id": "guarded_pulse",
                "kind": "damage",
                "target": {"kind": "target_actor"},
                "commitment": "required",
                "amount": 3,
                "condition": derived_condition,
            }]
        )])
        compiled = compile_skill_ir(_parse(raw))
        self.assertIn("Derived", compiled.state_classes)


class SkillIREndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (
            PROJECT_ROOT / "docs" / "agent_bootstrap" / "evidence" / "test_tmp"
        ).mkdir(parents=True, exist_ok=True)

    def test_two_entry_compiled_ir_through_formal_runtime_for_player_and_npc(self):
        authority = _authority("damage", "shield", budget=40)
        raw = _document(
            mana=6.0,
            entries=[
                _entry(
                    "active",
                    effects=[_effect("compiled_damage", "damage", amount=4)],
                ),
                _entry(
                    "reaction",
                    on_use=False,
                    effects=[{
                        "id": "compiled_shield",
                        "kind": "shield",
                        "target": {"kind": "self"},
                        "commitment": "required",
                        "amount": 3,
                    }],
                ),
            ],
        )
        compiled_ir = compile_skill_ir(_parse(raw, authority=authority))
        self.assertEqual(
            [item.kind for item in compiled_ir.blueprints],
            ["skill_blueprint", "passive_blueprint"],
        )
        self.assertEqual(
            sum(item.budget_used for item in compiled_ir.blueprints),
            4.5,
        )
        base = basic_registry()
        content = make_content(
            base,
            skills=compiled_ir.blueprints,
            material_ids=(MATERIAL_ID,),
        )
        initialized = initialize_content_world(_world(), content)
        compiled_content = compile_content(content)
        session = build_content_session(initialized, compiled_content)
        runtime = MechanismRegistryRuntime.from_compiled_content(
            session, compiled_content
        )
        active, passive = compiled_ir.blueprints
        for actor_id in (PLAYER, NPC):
            change_loadout(
                runtime.session,
                runtime.manifest,
                actor_id=actor_id,
                operation="equip_active",
                skill=skill_ref(active),
                slot=0,
            )
            change_loadout(
                runtime.session,
                runtime.manifest,
                actor_id=actor_id,
                operation="equip_passive",
                skill=skill_ref(passive),
                slot=0,
            )

        for round_index, actor_id, target_id in (
            (1, PLAYER, NPC),
            (2, NPC, PLAYER),
        ):
            outcome = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(
                    f"p2_ir_{actor_id}",
                    actor_id,
                    active.id,
                    target_id,
                ),
            )
            actor = runtime.session.state.entities[
                actor_id
            ].components[ACTOR_COMPONENT]
            target = runtime.session.state.entities[
                target_id
            ].components[ACTOR_COMPONENT]
            self.assertEqual(outcome.action.cost.mana, 6.0)
            self.assertEqual(outcome.action.cost.duration, 1)
            self.assertEqual(outcome.time.duration, 1)
            self.assertEqual(actor["mana"], 24.0)
            self.assertEqual(target["hp"], 46.0)
            self.assertEqual(target["shield"], 3.0)
            fired = [
                row for row in outcome.action.auto_hooks
                if row.status == "fired" and row.owner == target_id
            ]
            self.assertEqual(len(fired), 1)
            self.assertEqual(fired[0].hook_id, f"passive_{passive.id}_v1")
            budget = runtime.session.state.entities[CLOCK_ID].components[
                TIME_BUDGET_COMPONENT
            ]
            self.assertEqual(budget["spent_ticks"], round_index)
            self.assertEqual(budget["remaining_ticks"], 20 - round_index)

        combat = run_combat_round(
            runtime.session,
            runtime.action_registry,
            round_index=3,
            actor_order=(PLAYER, NPC),
            requests={
                PLAYER: ActionRequest(
                    "p2_ir_combat_player", PLAYER, active.id, NPC
                ),
                NPC: ActionRequest(
                    "p2_ir_combat_npc", NPC, active.id, PLAYER
                ),
            },
        )
        player = runtime.session.state.entities[
            PLAYER
        ].components[ACTOR_COMPONENT]
        npc = runtime.session.state.entities[NPC].components[ACTOR_COMPONENT]
        self.assertEqual(player["mana"], 18.0)
        self.assertEqual(npc["mana"], 18.0)
        self.assertEqual(player["hp"], 45.0)
        self.assertEqual(npc["hp"], 45.0)
        self.assertEqual(player["shield"], 3.0)
        self.assertEqual(npc["shield"], 3.0)
        self.assertEqual(combat.time_spend_result.duration, 1)
        budget = runtime.session.state.entities[CLOCK_ID].components[
            TIME_BUDGET_COMPONENT
        ]
        self.assertEqual(budget["spent_ticks"], 3)
        self.assertEqual(budget["remaining_ticks"], 17)
        self.assertEqual(
            player["mana"], 30.0 - 2 * 6.0,
        )
        self.assertEqual(
            npc["mana"], 30.0 - 2 * 6.0,
        )


if __name__ == "__main__":
    unittest.main()
