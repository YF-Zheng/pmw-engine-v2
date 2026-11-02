from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    ConditionLimits,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.effects import (
    EFFECT_KINDS,
    parse_effect,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    MaterialAuthority,
    MaterialDefinition,
    MaterialTrait,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.reference_skills.fixtures import (
    PROFILES,
    build_fixture,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer.catalog import (
    CATALOG_PROTOCOL,
    CatalogSourceError,
    MechanismCatalog,
    _build_catalog_document,
    _load_sources,
    build_mechanism_catalog,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer.context import (
    CONTEXT_PROTOCOL,
    ExistingSkillInput,
    GenerationContext,
    build_generation_context,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_ir import (
    OPERATOR_KINDS,
    SELECTOR_KINDS,
    STATE_CLASS_KINDS,
    compile_skill_ir,
    parse_skill_ir,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
LIBRARY_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "generative_mechanics"
    / "next_tracks_v06"
    / "gameplay_v04"
    / "reference_skills"
    / "library.json"
)
MATERIAL_ID = "p3_material"


def _material(
    material_id: str = MATERIAL_ID,
    *,
    kinds=None,
    selectors=None,
    budget: float = 200.0,
) -> MaterialDefinition:
    return parse_material({
        "id": material_id,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "p3_authority",
            "effect_kinds": list(kinds or EFFECT_KINDS),
            "selectors": list(selectors or SELECTOR_KINDS),
            "budget_points": budget,
        }],
    })


def _document(
    *,
    skill_id: str = "p3_test",
    name: str = "P3 Test",
    description: str = "Synthetic parser-legal fixture.",
    effects=None,
    condition=None,
    trigger=None,
    selectors=None,
    relation_types=(),
    budget: float = 50.0,
    summary: str = "Synthetic parser-legal fixture.",
    tags=("p3_test",),
    material_id: str = MATERIAL_ID,
):
    if effects is None:
        effects = [_effect("damage", amount=4)]
    return {
        "protocol": "pmw-skill-ir-v1",
        "identity": {
            "id": skill_id,
            "version": 1,
            "name": name,
            "description": description,
        },
        "origin": {
            "source": "authored",
            "model": None,
            "context_hash": None,
            "material_ids": [material_id],
        },
        "capability": {"traits": ["p3_test"]},
        "targeting": {
            "selectors": list(
                selectors or ("target_actor", "current_area", "adjacent_area")
            ),
            "relation_types": list(relation_types),
        },
        "costs": {"mana": 1.0, "duration": 1},
        "entries": [{
            "id": "entry",
            "trigger": trigger or {"kind": "on_use"},
            "condition": condition,
            "effects": effects,
            "max_firings_per_root": 1,
        }],
        "lifecycle": {"status_duration": None},
        "limits": {"budget": budget},
        "display": {"summary": summary, "tags": list(tags)},
    }


def _effect(kind: str, *, effect_id: str = "effect", **fields):
    result = {
        "id": effect_id,
        "kind": kind,
        "target": {"kind": "target_actor"},
        "commitment": "required",
    }
    defaults = {
        "damage": {"amount": 4},
        "heal": {"amount": 4},
        "shield": {"amount": 4},
        "add_resource": {"resource": "mana", "amount": 4},
        "apply_status": {"status_id": "basic_guarding"},
        "modify_field": {"field_id": "humidity", "amount": 0.2},
        "modify_attractor": {
            "field_id": "humidity", "amount": 0.2, "duration": 2,
        },
        "modify_rate": {
            "field_id": "humidity", "amount": 0.2, "duration": 2,
        },
        "grant_trait": {"trait_id": "p3_trait", "duration": 2},
        "process_start": {"process_template_id": "fixture_refine"},
        "process_modify": {
            "process_template_id": "fixture_refine_mod",
            "process_rate": 1.0,
        },
        "drive_source": {
            "drive_profile_id": "fixture_drive",
            "drive_rate": 1.0,
            "duration": 2,
        },
        "relation_modifier": {
            "relation_profile_id": "fixture_link",
            "relation_enabled": False,
            "duration": 2,
        },
        "dynamics_modifier": {
            "field_id": "humidity",
            "rate_add": 0.1,
            "rate_multiplier": 1.0,
            "curve": "linear",
            "curve_priority": 0,
            "duration": 2,
        },
        "move_actor": {},
    }
    result.update(defaults[kind])
    result.update(fields)
    if kind in {
        "process_start",
        "process_modify",
        "drive_source",
        "relation_modifier",
        "dynamics_modifier",
    }:
        result["target"] = {"kind": "current_area"}
    if kind == "move_actor":
        result["target"] = {"kind": "adjacent_area"}
    return result


def _parse(document, material=None):
    material = material or _material()
    authority = _authority(material)
    return parse_skill_ir(
        document,
        basic_registry().statuses,
        authority,
    )


def _authority(material: MaterialDefinition) -> MaterialAuthority:
    trait = material.traits[0]
    return MaterialAuthority(
        (material.id,),
        tuple(sorted(trait.effect_kinds)),
        tuple(sorted(trait.selectors)),
        trait.budget_points,
    )


def _snapshot(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class _PrivateStructuralProbe:
    """Not a TestCase; pytest cannot recollect another suite's helpers."""


def _summary_with_identity(material, skill_id, name, description, summary):
    document = _document(
        skill_id=skill_id,
        name=name,
        description=description,
        summary=summary,
        effects=[
            _effect(
                "damage",
                amount=7,
                condition={
                    "all": [{
                        "attribute": {
                            "subject": "self",
                            "key": "power",
                            "comparator": "gte",
                            "value": 3,
                        }
                    }]
                },
            )
        ],
        selectors=("target_actor",),
    )
    parsed = _parse(document, material)
    compiled = compile_skill_ir(parsed)
    context = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=2,
        public_known_rules=("combat profile",),
        acquired_capabilities=("basic.attack",),
        existing_skills=(ExistingSkillInput.from_compiled(compiled),),
    )
    return context


def test_catalog_is_canonical_immutable_and_covers_all_parser_mechanisms():
    catalog = build_mechanism_catalog()
    assert isinstance(catalog, MechanismCatalog)
    assert catalog.version == CATALOG_PROTOCOL
    assert catalog.ir_protocol == "pmw-skill-ir-v1"
    document = catalog.to_dict()
    assert document["coverage"]["effect_kind_count"] == 15
    assert document["coverage"]["operator_family_count"] == 7
    assert document["coverage"]["state_class_count"] == 6
    assert document["provenance"]["candidate_data_execution"] is False
    assert document["provenance"]["effect_allowed_required_keys"] == (
        "ast_literal_extraction_from_parse_effect"
    )
    assert document["provenance"]["effect_conditional_rules"] == (
        "static_source_anchored_manifest_checked_by_tests"
    )
    assert set(document["effects"]["kinds"]) == set(EFFECT_KINDS)
    assert {
        kind
        for kinds in OPERATOR_KINDS.values()
        for kind in kinds
    } == set(EFFECT_KINDS)
    assert set(document["operators"]) == set(OPERATOR_KINDS)
    assert set(document["state_classes"]) == set(STATE_CLASS_KINDS)
    assert catalog.hash == hashlib.sha256(
        catalog.canonical_json.encode("utf-8")
    ).hexdigest()

    alias = catalog.to_dict()
    alias["effects"]["kinds"]["damage"]["required_keys"].append("injected")
    alias["coverage"]["effect_kind_count"] = -1
    fresh = catalog.to_dict()
    assert "injected" not in fresh["effects"]["kinds"]["damage"]["required_keys"]
    assert fresh["coverage"]["effect_kind_count"] == 15
    assert catalog.hash == build_mechanism_catalog().hash


def test_catalog_effect_schemas_match_parse_effect_and_rules():
    catalog = build_mechanism_catalog().to_dict()
    effects = catalog["effects"]
    assert effects["common_required_keys"] == [
        "commitment", "id", "kind", "target",
    ]
    assert effects["common_optional_keys"] == [
        "attribute_terms", "condition", "targeting",
    ]
    assert effects["process_modify_optional_keys"] == [
        "process_rate", "process_remaining_ticks",
    ]
    expected = {
        "damage": {"amount"},
        "heal": {"amount"},
        "shield": {"amount"},
        "add_resource": {"resource", "amount"},
        "apply_status": {"status_id"},
        "modify_field": {"field_id", "amount"},
        "modify_attractor": {"field_id", "amount", "duration"},
        "modify_rate": {"field_id", "amount", "duration"},
        "grant_trait": {"trait_id", "duration"},
        "process_start": {"process_template_id"},
        "process_modify": {
            "process_template_id",
            "process_rate",
            "process_remaining_ticks",
        },
        "drive_source": {"drive_profile_id", "drive_rate", "duration"},
        "relation_modifier": {
            "relation_profile_id", "relation_enabled", "duration",
        },
        "dynamics_modifier": {
            "field_id",
            "rate_add",
            "rate_multiplier",
            "curve",
            "curve_priority",
            "duration",
        },
        "move_actor": set(),
    }
    for kind, fields in expected.items():
        row = effects["kinds"][kind]
        assert set(row["required_keys"]) == {
            "id", "kind", "target", "commitment",
        } | (
            fields - {"process_rate", "process_remaining_ticks"}
            if kind == "process_modify"
            else fields
        )
        assert set(row["allowed_keys"]) == set(row["required_keys"]) | set(
            row["optional_keys"]
        )
        assert row["supported"] is True
        assert row["schema_derivation"] == "source_ast_literal"
        assert len(row["operators"]) == 1
    dynamic = effects["kinds"]["dynamics_modifier"]
    assert dynamic["excluded_optional_keys"] == [
        "attribute_terms", "condition", "targeting",
    ]
    process = effects["kinds"]["process_modify"]
    assert process["conditional_rules"][0]["keys"] == [
        "process_rate", "process_remaining_ticks",
    ]
    assert process["conditional_rules"][0]["rule"] == "at_least_one_non_null"
    move = effects["kinds"]["move_actor"]
    assert move["required_keys"] == ["commitment", "id", "kind", "target"]
    move_rules = {
        rule["rule"]: rule.get("value")
        for rule in move["conditional_rules"]
    }
    assert move_rules["target_exact"] == {"kind": "adjacent_area"}
    assert move_rules["commitment_exact"] == "required"
    assert effects["kinds"]["dynamics_modifier"]["value_constraints"][
        "duration"
    ]["maximum"] == 64
    assert effects["kinds"]["relation_modifier"]["value_constraints"][
        "relation_enabled"
    ]["type"] == "strict_boolean"
    assert "condition" not in effects["kinds"]["move_actor"][
        "value_constraints"
    ]
    assert "attribute_terms" not in effects["kinds"]["move_actor"][
        "value_constraints"
    ]
    assert "targeting" not in effects["kinds"]["move_actor"][
        "value_constraints"
    ]
    assert effects["kinds"]["move_actor"]["value_constraints"][
        "commitment"
    ]["values"] == ["required"]
    amount_scope = effects["kinds"]["damage"]["value_constraints"][
        "amount"
    ]["null_scope"]
    assert amount_scope["parse_effect_null_allowed"] is True
    assert amount_scope["skill_ir_ingress_null_allowed"] is True
    assert amount_scope["annotation_is_source_anchored"] is False
    assert effects["kinds"]["process_modify"]["value_constraints"][
        "process_rate"
    ]["runtime_profile_bound"] == "Process template max_rate"


@pytest.mark.parametrize("kind", EFFECT_KINDS)
def test_catalog_schema_admits_one_parser_legal_example_per_effect(kind):
    statuses = basic_registry().statuses
    raw = _effect(kind)
    parsed = parse_effect(raw, statuses)
    catalog = build_mechanism_catalog().to_dict()
    row = catalog["effects"]["kinds"][kind]
    assert set(raw) <= set(row["allowed_keys"])
    assert set(row["required_keys"]) <= set(raw)
    assert parsed.kind == kind
    if kind == "process_modify":
        with pytest.raises(GameplayContractError):
            parse_effect({
                **raw,
                "process_rate": None,
                "process_remaining_ticks": None,
            }, statuses)
    if kind == "dynamics_modifier":
        with pytest.raises(GameplayContractError):
            parse_effect({**raw, "condition": None}, statuses)
    if kind == "move_actor":
        with pytest.raises(GameplayContractError):
            parse_effect({**raw, "target": {"kind": "self"}}, statuses)
        with pytest.raises(GameplayContractError):
            parse_effect({**raw, "commitment": "conditional"}, statuses)


def test_null_constraint_annotations_distinguish_parser_from_ir_ingress():
    material = _material(
        kinds=("damage",),
        selectors=("self",),
        budget=20.0,
    )
    parsed = _parse(_document(
        effects=[_effect("damage", amount=None, target={"kind": "self"})],
        selectors=("self",),
        budget=20.0,
    ), material)
    assert parsed.entries[0].effects[0]["amount"] is None
    assert parsed.entries[0].effects[0]["target"] == {"kind": "self"}

    rejected = _document(
        effects=[{
            key: value for key, value in _effect("damage").items()
            if key != "amount"
        } | {"target": {"kind": "self"}}],
        selectors=("self",),
        budget=20.0,
    )
    with pytest.raises(GameplayContractError, match="missing or unknown fields"):
        _parse(rejected, material)


def test_catalog_conditions_selectors_triggers_and_lifecycle_are_exact():
    catalog = build_mechanism_catalog().to_dict()
    conditions = catalog["conditions"]
    assert set(conditions["kinds"]) == {
        "all",
        "any",
        "not",
        "attribute",
        "resource",
        "field",
        "has_trait",
        "has_status",
        "derived",
    }
    assert conditions["defaults"] == {
        "max_depth": 16,
        "max_nodes": 64,
        "max_children": 16,
    }
    assert conditions["semantics"]["pure"] is True
    assert conditions["semantics"]["read_only"] is True
    assert conditions["semantics"]["derived_is_input_only"] is True
    selectors = catalog["selectors"]
    assert set(selectors["kinds"]) == set(SELECTOR_KINDS)
    linked = [
        row for row in selectors["entries"]
        if row["kind"] == "linked_object"
    ][0]
    assert linked["allowed_keys"] == ["kind", "relation_type"]
    assert linked["required_relation_type"] is True
    assert selectors["single_target_restriction"]["rule"] == (
        "exactly_one_resolved_target"
    )
    assert linked["effect_target_restriction"] == "exactly_one_resolved_target"

    supported = {
        (row["kind"], row.get("event"))
        for row in catalog["triggers"]["supported"]
    }
    assert supported == {("on_use", None), ("on_event", "damage_resolved")}
    reserved = catalog["triggers"]["reserved"]
    assert all(row["supported"] is False for row in reserved)
    assert all("language_gap" in row["reason"] for row in reserved)
    assert catalog["lifecycle"]["status_duration"]["supported"] is False
    assert catalog["lifecycle"]["status_duration"]["non_null"]["reason"] == (
        "language_gap:lifecycle.status_duration"
    )


def test_current_reference_library_compiles_against_catalog_snapshot():
    documents = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    assert len(documents) == 40
    catalog = build_mechanism_catalog().to_dict()
    seen_kinds = set()
    seen_selectors = set()
    for document in documents:
        profile = next(
            tag.split(":", 1)[1]
            for tag in document["display"]["tags"]
            if tag.startswith("fixture:")
        )
        fixture = build_fixture(profile)
        parsed = parse_skill_ir(document, fixture.statuses, fixture.authority)
        compiled = compile_skill_ir(parsed)
        assert compiled.canonical_hash == parsed.canonical_hash
        for entry in parsed.entries:
            for effect in entry.effects:
                seen_kinds.add(effect["kind"])
                seen_selectors.add(effect["target"]["kind"])
                assert effect["kind"] in catalog["effects"]["kinds"]
                assert effect["target"]["kind"] in catalog["selectors"]["kinds"]
    assert seen_kinds == set(EFFECT_KINDS)
    assert seen_selectors == set(SELECTOR_KINDS)


def test_catalog_generation_converges_and_runtime_profile_ids_are_not_enumerated():
    first = build_mechanism_catalog()
    second = build_mechanism_catalog()
    assert first.canonical_json == second.canonical_json
    assert first.hash == second.hash
    document = first.to_dict()
    profile = document["runtime_profiles"]
    assert profile["closed_profiles"] == list(PROFILES)
    assert profile["profile_specific_ids"]["enumerated"] is False
    process = document["effects"]["kinds"]["process_start"]["value_constraints"]
    drive = document["effects"]["kinds"]["drive_source"]["value_constraints"]
    relation = document["effects"]["kinds"][
        "relation_modifier"
    ]["value_constraints"]
    assert process["process_template_id"]["global_profile_ids_enumerated"] is False
    assert drive["drive_profile_id"]["global_profile_ids_enumerated"] is False
    assert relation["relation_profile_id"]["global_profile_ids_enumerated"] is False


def test_catalog_source_drift_fails_closed_instead_of_inventing_schema():
    sources = _load_sources()
    changed = dict(sources)
    changed["effects.py"] = sources["effects.py"].replace(
        '"move_actor": set(),',
        '"move_actor": {"amount"},',
        1,
    )
    assert changed["effects.py"] != sources["effects.py"]
    with pytest.raises(CatalogSourceError, match="schema drift"):
        _build_catalog_document(changed)


def test_catalog_source_ast_syntax_drift_fails_closed():
    sources = _load_sources()
    changed = dict(sources)
    changed["conditions.py"] = (
        sources["conditions.py"]
        + "\ndef !!! invalid python !!!\n"
    )
    with pytest.raises(CatalogSourceError, match="cannot be parsed"):
        _build_catalog_document(changed)


def test_context_is_deterministic_and_defensive_for_mutable_inputs():
    material = _material(
        kinds=("damage",),
        selectors=("target_actor",),
    )
    rules = ["combat profile", "damage uses finite numbers"]
    capabilities = ["basic.attack", "basic.guard"]
    first = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=2,
        public_known_rules=rules,
        acquired_capabilities=capabilities,
    )
    second = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=2,
        public_known_rules=tuple(rules),
        acquired_capabilities=tuple(capabilities),
    )
    assert first.canonical_json == second.canonical_json
    assert first.context_hash == second.context_hash
    assert first.catalog_hash == build_mechanism_catalog().hash
    output = first.to_dict()
    output["materials"][0]["trait_ids"] = ["mutated"]
    output["authority"]["effect_kinds"].append("move_actor")
    assert "trait_ids" not in first.to_dict()["materials"][0]
    assert "move_actor" not in first.to_dict()["authority"]["effect_kinds"]
    rules.append("mutated")
    capabilities.append("mutated")
    changed_hash = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=2,
        public_known_rules=rules,
        acquired_capabilities=capabilities,
    ).context_hash
    assert changed_hash != first.context_hash


def test_context_hash_changes_for_each_semantic_input():
    material = _material()
    base = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=1,
        public_known_rules=("rule",),
        acquired_capabilities=("basic.attack",),
    ).context_hash
    variants = [
        dict(
            profile="field",
            materials=[material],
            complexity=1,
            public_known_rules=("rule",),
            acquired_capabilities=("basic.attack",),
        ),
        dict(
            profile="combat",
            materials=[material],
            complexity=2,
            public_known_rules=("rule",),
            acquired_capabilities=("basic.attack",),
        ),
        dict(
            profile="combat",
            materials=[_material(budget=201.0)],
            complexity=1,
            public_known_rules=("rule",),
            acquired_capabilities=("basic.attack",),
        ),
        dict(
            profile="combat",
            materials=[material],
            complexity=1,
            public_known_rules=("different rule",),
            acquired_capabilities=("basic.attack",),
        ),
        dict(
            profile="combat",
            materials=[material],
            complexity=1,
            public_known_rules=("rule",),
            acquired_capabilities=("basic.guard",),
        ),
    ]
    hashes = {
        build_generation_context(**variant).context_hash
        for variant in variants
    }
    assert base not in hashes
    assert len(hashes) == len(variants)


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("complexity", True, "complexity"),
        ("complexity", 0, "complexity"),
        ("complexity", 4, "complexity"),
        ("complexity", 1.0, "complexity"),
        ("complexity", float("nan"), "complexity"),
        ("public_known_rules", "rule", "sequence"),
        ("public_known_rules", [""], "non-empty"),
        ("public_known_rules", ["x" * 513], "512"),
        ("public_known_rules", [f"r{i}" for i in range(33)], "at most"),
        ("public_known_rules", ["dup", "dup"], "duplicates"),
        ("acquired_capabilities", ["bad capability"], "capability name"),
        ("acquired_capabilities", ["a" * 129], "128"),
        ("acquired_capabilities", [f"cap.{i}" for i in range(33)], "at most"),
    ],
)
def test_context_rejects_invalid_bounds_and_types(keyword, value, message):
    arguments = {
        "profile": "combat",
        "materials": [_material()],
        "complexity": 1,
        "public_known_rules": (),
        "acquired_capabilities": (),
    }
    arguments[keyword] = value
    with pytest.raises(GameplayContractError, match=message):
        build_generation_context(**arguments)


def test_context_rejects_unknown_profile_scope_and_duplicate_materials():
    with pytest.raises(GameplayContractError, match="closed reference profiles"):
        build_generation_context(
            profile="unknown",
            materials=[_material()],
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
        )
    bad_scope = MaterialDefinition(
        "bad_scope",
        "rare",
        "scarce",
        (
            MaterialTrait(
                "bad_trait",
                ("damage",),
                ("world_admin",),
                4.0,
            ),
        ),
    )
    with pytest.raises(GameplayContractError, match="unknown scope"):
        build_generation_context(
            profile="combat",
            materials=[bad_scope],
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
        )
    duplicate = _material()
    with pytest.raises(GameplayContractError, match="unique IDs"):
        build_generation_context(
            profile="combat",
            materials=[duplicate, duplicate],
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
        )


def test_context_rejects_malformed_dataclass_and_wraps_huge_numeric_errors():
    malformed = MaterialDefinition(
        "bad_material",
        "rare",
        "scarce",
        (
            MaterialTrait(
                "bad_trait",
                ("damage",),
                ("self",),
                float("nan"),
            ),
        ),
    )
    with pytest.raises(GameplayContractError, match="positive finite"):
        build_generation_context(
            profile="combat",
            materials=[malformed],
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
        )
    huge = MaterialDefinition(
        "huge_material",
        "rare",
        "scarce",
        (
            MaterialTrait(
                "huge_trait",
                ("damage",),
                ("self",),
                10**10000,
            ),
        ),
    )
    with pytest.raises(GameplayContractError, match="defensive revalidation"):
        build_generation_context(
            profile="combat",
            materials=[huge],
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
        )
    broken_fields = replace(malformed, traits=("not a trait",))
    with pytest.raises(GameplayContractError, match="malformed trait"):
        build_generation_context(
            profile="combat",
            materials=[broken_fields],
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
        )


def test_context_rejects_nonfinite_aggregate_material_budget():
    materials = [
        parse_material({
            "id": f"p3_overflow_{index}",
            "tier": "rare",
            "region_rarity": "scarce",
            "traits": [{
                "id": "overflow_trait",
                "effect_kinds": ["damage"],
                "selectors": ["target_actor"],
                "budget_points": 1e308,
            }],
        })
        for index in range(2)
    ]
    with pytest.raises(
        GameplayContractError,
        match="aggregate material authority budget must be finite and positive",
    ):
        build_generation_context(
            profile="combat",
            materials=materials,
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
        )


def test_context_authority_is_derived_from_materials_not_candidate_text():
    material = _material(
        kinds=("damage",),
        selectors=("target_actor",),
        budget=12.0,
    )
    document = _document(
        effects=[_effect("damage", amount=4)],
        selectors=("target_actor",),
        summary="move_actor process_start relation_modifier",
        tags=("move_actor", "all"),
        budget=12.0,
    )
    parsed = _parse(document, material)
    compiled = compile_skill_ir(parsed)
    context = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=1,
        public_known_rules=(),
        acquired_capabilities=(),
        existing_skills=(ExistingSkillInput.from_compiled(compiled),),
    )
    authority = context.to_dict()["authority"]
    assert authority["effect_kinds"] == ["damage"]
    assert authority["selectors"] == ["target_actor"]
    assert authority["budget_points"] == 12.0
    assert authority["material_ids"] == [MATERIAL_ID]


def test_public_context_never_contains_hidden_worldstate_sentinel():
    material = _material()
    context = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=1,
        public_known_rules=("public fact only",),
        acquired_capabilities=("basic.attack",),
    )
    fixture = build_fixture("combat")
    sentinel = "HIDDEN_WORLDSTATE_SENTINEL_DO_NOT_EXPORT"

    class _Probe:
        hidden = sentinel

    fixture.world.rng_state["hidden_worldstate_sentinel"] = sentinel
    canonical = context.canonical_json
    assert sentinel not in canonical
    assert "world" not in {
        key for key in context.to_dict()
        if key in {"world", "world_state", "entities", "relations"}
    }
    assert context.to_dict()["visibility"]["world_state_included"] is False
    assert context.to_dict()["public_known_rules"] == ["public fact only"]


def test_structure_summary_ignores_identity_and_prose_but_changes_semantics():
    material = _material()
    left = _summary_with_identity(
        material,
        "skill_alpha",
        "Alpha Display",
        "First prose.",
        "First display summary.",
    )
    right = _summary_with_identity(
        material,
        "skill_beta",
        "Beta Display",
        "Second prose.",
        "Second display summary.",
    )
    left_doc = left.to_dict()
    right_doc = right.to_dict()
    assert left_doc["existing_skill_structures"] == (
        right_doc["existing_skill_structures"]
    )
    assert left.context_hash == right.context_hash
    summary = left_doc["existing_skill_structures"][0]
    assert summary["summary_kind"] == (
        "semantic_structure_not_behavioral_identity"
    )
    serialized = _snapshot(summary)
    for omitted in (
        "skill_alpha",
        "skill_beta",
        "Alpha Display",
        "First prose",
        "First display",
    ):
        assert omitted not in serialized
    assert '"effect_id"' not in serialized
    assert '"entry_id"' not in serialized
    assert summary["entries"][0]["effects"][0]["amount"] == 7.0
    assert summary["entries"][0]["effects"][0]["target"]["kind"] == (
        "target_actor"
    )

    changed = _parse(_document(
        effects=[_effect("damage", amount=8)],
        selectors=("target_actor",),
    ), material)
    changed_summary = left.structural_summary(changed)
    assert changed_summary["structural_hash"] != summary["structural_hash"]
    other = _parse(_document(
        effects=[_effect("heal", amount=7)],
        selectors=("target_actor",),
    ), material)
    other_summary = left.structural_summary(other)
    assert other_summary["structural_hash"] != summary["structural_hash"]


def test_structural_summary_preserves_semantic_references_and_condition_leaves():
    material = _material()
    document = _document(
        effects=[_effect(
            "process_modify",
            process_template_id="fixture_refine_mod",
            process_rate=2.5,
            condition={
                "all": [{
                    "field": {
                        "subject": "current_area",
                        "key": "humidity",
                        "comparator": "gte",
                        "value": 0.4,
                    }
                }, {
                    "derived": {
                        "subject": "current_area",
                        "key": "comfort",
                        "comparator": "gt",
                        "value": 1.0,
                    }
                }]
            },
        )],
        selectors=("current_area",),
    )
    parsed = _parse(document, material)
    context = build_generation_context(
        profile="process",
        materials=[material],
        complexity=3,
        public_known_rules=(),
        acquired_capabilities=(),
    )
    summary = context.structural_summary(parsed)
    effect = summary["entries"][0]["effects"][0]
    assert effect["process_template_id"] == "fixture_refine_mod"
    assert effect["process_rate"] == 2.5
    assert effect["condition"]["kind"] == "all"
    leaves = effect["condition"]["children"]
    assert leaves[0]["key"] == "humidity"
    assert leaves[0]["value"] == 0.4
    assert leaves[1]["kind"] == "derived"
    assert leaves[1]["key"] == "comfort"
    assert "Derived" in summary["state_classes"]


def test_existing_skill_wrapper_and_compiled_revalidation_fail_closed():
    material = _material()
    compiled = compile_skill_ir(_parse(_document(), material))
    with pytest.raises(GameplayContractError, match="exactly one"):
        ExistingSkillInput()
    with pytest.raises(GameplayContractError, match="CompiledSkillIR"):
        ExistingSkillInput(compiled=object())
    with pytest.raises(GameplayContractError, match="trusted statuses"):
        ExistingSkillInput.from_raw(_document(), statuses=None, authority=None)
    forged = replace(
        compiled,
        ir=replace(compiled.ir, canonical_hash="0" * 64),
    )
    with pytest.raises(GameplayContractError):
        build_generation_context(
            profile="combat",
            materials=[material],
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
            existing_skills=(ExistingSkillInput.from_compiled(forged),),
        )


def test_existing_raw_skill_uses_explicit_trusted_statuses_and_authority():
    material = _material()
    document = _document()
    input_value = ExistingSkillInput.from_raw(
        deepcopy(document),
        statuses=basic_registry().statuses,
        authority=_authority(material),
    )
    context = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=1,
        public_known_rules=(),
        acquired_capabilities=(),
        existing_skills=(input_value,),
    )
    assert len(context.to_dict()["existing_skill_structures"]) == 1
    with pytest.raises(GameplayContractError, match="ExistingSkillInput"):
        build_generation_context(
            profile="combat",
            materials=[material],
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
            existing_skills=(document,),
        )
