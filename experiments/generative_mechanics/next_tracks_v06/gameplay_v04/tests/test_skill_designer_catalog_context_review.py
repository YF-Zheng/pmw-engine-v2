"""Independent P3.1A review for offline Catalog/Context.

This suite intentionally exercises public behavior and source-derived claims.
It does not import another test module, so pytest cannot recollect an old
suite through this file.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import re

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
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.reference_skills.fixtures import (
    PROFILES,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer import (
    ExistingSkillInput,
    GenerationContext,
    MechanismCatalog,
    build_generation_context,
    build_mechanism_catalog,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer.catalog import (
    CatalogSourceError,
    _build_catalog_document,
    _load_sources,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_ir import (
    OPERATOR_KINDS,
    SELECTOR_KINDS,
    STATE_CLASS_KINDS,
    CompiledSkillIR,
    SkillIR,
    compile_skill_ir,
    parse_skill_ir,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
MATERIAL_ID = "p3_review_material"
STATUS_ID = "basic_guarding"


def _material(
    material_id: str = MATERIAL_ID,
    *,
    kinds: tuple[str, ...] = EFFECT_KINDS,
    selectors: tuple[str, ...] = tuple(sorted(SELECTOR_KINDS)),
    budget: float = 200.0,
) -> MaterialDefinition:
    return parse_material({
        "id": material_id,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "review_authority",
            "effect_kinds": list(kinds),
            "selectors": list(selectors),
            "budget_points": budget,
        }],
    })


def _authority(material: MaterialDefinition) -> MaterialAuthority:
    return material_authority((material,))


def _effect(kind: str, *, effect_id: str = "effect", **updates) -> dict:
    common = {
        "id": effect_id,
        "kind": kind,
        "target": {"kind": "target_actor"},
        "commitment": "required",
    }
    fields = {
        "damage": {"amount": 4.0},
        "heal": {"amount": 4.0},
        "shield": {"amount": 4.0},
        "add_resource": {"resource": "mana", "amount": 4.0},
        "apply_status": {"status_id": STATUS_ID},
        "modify_field": {"field_id": "humidity", "amount": 0.2},
        "modify_attractor": {
            "field_id": "humidity",
            "amount": 0.2,
            "duration": 2,
        },
        "modify_rate": {
            "field_id": "humidity",
            "amount": 0.2,
            "duration": 2,
        },
        "grant_trait": {"trait_id": "review_trait", "duration": 2},
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
    result = {**common, **fields[kind]}
    if kind in {
        "process_start",
        "process_modify",
        "drive_source",
        "relation_modifier",
        "dynamics_modifier",
    }:
        result["target"] = {"kind": "current_area"}
    elif kind == "move_actor":
        result["target"] = {"kind": "adjacent_area"}
    result.update(updates)
    return result


def _document(
    *,
    skill_id: str = "review_skill",
    name: str = "Review Skill",
    description: str = "Independent parser-legal fixture.",
    summary: str = "Independent parser-legal fixture.",
    effects: list[dict] | None = None,
    condition: dict | None = None,
    trigger: dict | None = None,
    selectors: tuple[str, ...] = (
        "target_actor",
        "current_area",
        "adjacent_area",
    ),
    relation_types: tuple[str, ...] = (),
    budget: float = 50.0,
    tags: tuple[str, ...] = ("review",),
    material_id: str = MATERIAL_ID,
) -> dict:
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
        "capability": {"traits": ["review_scope"]},
        "targeting": {
            "selectors": list(selectors),
            "relation_types": list(relation_types),
        },
        "costs": {"mana": 1.0, "duration": 1},
        "entries": [{
            "id": "entry",
            "trigger": trigger or {"kind": "on_use"},
            "condition": condition,
            "effects": effects or [_effect("damage")],
            "max_firings_per_root": 1,
        }],
        "lifecycle": {"status_duration": None},
        "limits": {"budget": budget},
        "display": {"summary": summary, "tags": list(tags)},
    }


def _parse(raw: dict, material: MaterialDefinition) -> SkillIR:
    return parse_skill_ir(raw, basic_registry().statuses, _authority(material))


def _context(
    *,
    material: MaterialDefinition | None = None,
    profile: str = "combat",
    existing_skills: tuple[ExistingSkillInput, ...] = (),
) -> GenerationContext:
    return build_generation_context(
        profile=profile,
        materials=[material or _material()],
        complexity=2,
        public_known_rules=("review public fact",),
        acquired_capabilities=("review.guard",),
        existing_skills=existing_skills,
    )


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _path_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_gameplay_error(callable_, match: str | None = None) -> None:
    with pytest.raises(GameplayContractError, match=match):
        callable_()


def test_review_legal_samples_and_parser_contradictions_are_public_boundary_ready():
    material = _material()
    statuses = basic_registry().statuses
    for kind in EFFECT_KINDS:
        raw = _effect(kind)
        parsed = parse_effect(raw, statuses)
        assert parsed.kind == kind
        parsed_ir = _parse(_document(effects=[raw]), material)
        compile_skill_ir(parsed_ir)

    # The catalog must describe the generator-facing IR ingress, not the
    # narrower lower-level parser accidentally. These are explicit
    # contradictions in the current owner draft.
    catalog = build_mechanism_catalog().to_dict()
    move = catalog["effects"]["kinds"]["move_actor"]
    assert "condition" not in move["value_constraints"]
    assert "attribute_terms" not in move["value_constraints"]
    assert "targeting" not in move["value_constraints"]
    assert "target" in move["value_constraints"]


@pytest.mark.parametrize(
    ("kind", "key"),
    [
        ("damage", "amount"),
        ("heal", "amount"),
        ("shield", "amount"),
        ("add_resource", "amount"),
        ("add_resource", "resource"),
        ("apply_status", "status_id"),
        ("modify_field", "field_id"),
        ("modify_field", "amount"),
        ("modify_attractor", "field_id"),
        ("modify_attractor", "amount"),
        ("modify_rate", "field_id"),
        ("modify_rate", "amount"),
        ("grant_trait", "trait_id"),
    ],
)
def test_required_catalog_fields_do_not_advertise_ambiguous_parser_nulls(
    kind: str,
    key: str,
):
    row = build_mechanism_catalog().to_dict()["effects"]["kinds"][kind]
    constraint = row["value_constraints"].get(key, {})
    assert constraint.get("null_allowed_by_parser") is not True, (
        f"{kind}.{key} is required in the generator-facing schema; "
        "an unqualified null advertisement is ambiguous"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("condition", None),
        ("attribute_terms", None),
        ("targeting", None),
    ],
)
def test_move_actor_catalog_optionality_matches_exact_ir_schema(
    field: str,
    value: object,
):
    material = _material()
    raw = _effect("move_actor", **{field: value})
    with pytest.raises(GameplayContractError):
        _parse(_document(effects=[raw]), material)
    row = build_mechanism_catalog().to_dict()["effects"]["kinds"]["move_actor"]
    assert field not in row["allowed_keys"]


def test_catalog_exact_schema_and_conditional_rules_cover_parser_legal_samples():
    material = _material()
    catalog = build_mechanism_catalog().to_dict()
    for kind in EFFECT_KINDS:
        raw = _effect(kind)
        row = catalog["effects"]["kinds"][kind]
        assert set(raw) <= set(row["allowed_keys"])
        assert set(row["required_keys"]) <= set(raw)
        assert len(row["operators"]) == 1
        assert row["operators"][0] in OPERATOR_KINDS
        assert set(row["state_classes"]) == {
            name for name, kinds in STATE_CLASS_KINDS.items() if kind in kinds
        }
        _parse(_document(effects=[raw]), material)

    dynamic = catalog["effects"]["kinds"]["dynamics_modifier"]
    assert dynamic["optional_keys"] == []
    assert dynamic["required_keys"] == sorted({
        "id",
        "kind",
        "target",
        "commitment",
        "field_id",
        "rate_add",
        "rate_multiplier",
        "curve",
        "curve_priority",
        "duration",
    })
    assert set(dynamic["conditional_rules"][0]["keys"]) == {
        "attribute_terms",
        "condition",
        "targeting",
    }


def test_catalog_source_drift_mutations_fail_closed_before_schema_is_advertised():
    original = _load_sources()
    mutations = {
        "move_actor fields": (
            "effects.py",
            '"move_actor": set(),',
            '"move_actor": {"amount"},',
        ),
        "dynamics optionality": (
            "effects.py",
            '"dynamics_modifier",',
            '"dynamics_modifier_unused",',
        ),
        "process optional": (
            "effects.py",
            'process_modify_optional = {"process_rate", "process_remaining_ticks"}',
            'process_modify_optional = {"process_rate"}',
        ),
        "reserved trigger": (
            "skill_ir.py",
            '"on_tick", "on_expire", "transition",',
            '"on_expire", "transition",',
        ),
    }
    for label, (name, before, after) in mutations.items():
        assert before in original[name], label
        changed = dict(original)
        changed[name] = original[name].replace(before, after, 1)
        assert changed[name] != original[name]
        with pytest.raises(CatalogSourceError):
            _build_catalog_document(changed)


def test_catalog_snapshots_and_context_are_immutable_and_canonical():
    first = build_mechanism_catalog()
    second = build_mechanism_catalog()
    assert isinstance(first, MechanismCatalog)
    assert first.canonical_json == second.canonical_json
    assert first.hash == second.hash
    assert first.hash == hashlib.sha256(
        first.canonical_json.encode("utf-8")
    ).hexdigest()
    assert _canonical(first.to_dict()) == first.canonical_json

    alias = first.to_dict()
    alias["coverage"]["effect_kind_count"] = 0
    alias["effects"]["kinds"]["damage"]["allowed_keys"].append("malformed")
    assert first.to_dict()["coverage"]["effect_kind_count"] == 15
    assert "malformed" not in first.to_dict()["effects"]["kinds"]["damage"][
        "allowed_keys"
    ]

    context = _context()
    assert isinstance(context, GenerationContext)
    assert context.context_hash == hashlib.sha256(
        context.canonical_json.encode("utf-8")
    ).hexdigest()
    assert _canonical(context.to_dict()) == context.canonical_json
    context_alias = context.to_dict()
    context_alias["authority"]["budget_points"] = 10**100
    context_alias["materials"][0]["traits"][0]["budget_points"] = -1
    fresh_context = context.to_dict()
    assert fresh_context["authority"]["budget_points"] != 10**100
    assert fresh_context["materials"][0]["traits"][0]["budget_points"] > 0


def test_context_authority_is_derived_from_validated_traits_not_caller_text():
    material = _material(
        kinds=("damage",),
        selectors=("target_actor",),
        budget=13.0,
    )
    context = _context(material=material)
    document = context.to_dict()
    assert document["authority"] == {
        "material_ids": [MATERIAL_ID],
        "effect_kinds": ["damage"],
        "selectors": ["target_actor"],
        "budget_points": 13.0,
        "derivation": "validated_material_traits_only",
    }
    serialized = context.canonical_json
    for forbidden in (
        "HIDDEN_WORLDSTATE_SENTINEL",
        "rng_state",
        "scheduled_events",
    ):
        assert forbidden not in serialized
    assert document["visibility"] == {
        "public_allowlist_only": True,
        "world_state_included": False,
        "registry_dump_included": False,
    }


def test_material_authority_overflow_is_fail_closed_at_public_builder():
    materials = [
        parse_material({
            "id": f"p3_review_overflow_{index}",
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
    with pytest.raises(GameplayContractError):
        build_generation_context(
            profile="combat",
            materials=materials,
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
        )


def test_material_boundaries_and_duplicate_or_malformed_traits_fail_closed():
    duplicate = _material()
    _assert_gameplay_error(
        lambda: build_generation_context(
            profile="combat",
            materials=[duplicate, duplicate],
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
        ),
        "unique IDs",
    )
    _assert_gameplay_error(
        lambda: build_generation_context(
            profile="combat",
            materials=[_material()],
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
            existing_skills=(_document(),),
        ),
        "ExistingSkillInput",
    )
    malformed = MaterialDefinition(
        "malformed_material",
        "rare",
        "scarce",
        (MaterialTrait("bad_trait", ("damage",), ("self",), float("nan")),),
    )
    _assert_gameplay_error(
        lambda: build_generation_context(
            profile="combat",
            materials=[malformed],
            complexity=1,
            public_known_rules=(),
            acquired_capabilities=(),
        )
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"profile": "unknown"},
        {"profile": None},
        {"complexity": True},
        {"complexity": False},
        {"complexity": 0},
        {"complexity": 4},
        {"complexity": 1.0},
        {"complexity": float("nan")},
        {"public_known_rules": "not a sequence"},
        {"public_known_rules": ["x" * 513]},
        {"public_known_rules": ["dup", "dup"]},
        {"acquired_capabilities": ["has space"]},
        {"acquired_capabilities": ["x" * 129]},
    ],
)
def test_context_rejects_bounded_profile_complexity_and_text_inputs(kwargs):
    arguments = {
        "profile": "combat",
        "materials": [_material()],
        "complexity": 1,
        "public_known_rules": (),
        "acquired_capabilities": (),
    }
    arguments.update(kwargs)
    _assert_gameplay_error(lambda: build_generation_context(**arguments))


def test_existing_skill_public_summary_revalidates_compiled_and_raw_paths():
    material = _material()
    parsed = _parse(_document(), material)
    compiled = compile_skill_ir(parsed)
    assert isinstance(compiled, CompiledSkillIR)

    compiled_context = _context(
        existing_skills=(ExistingSkillInput.from_compiled(compiled),),
    )
    raw_context = _context(
        existing_skills=(
            ExistingSkillInput.from_raw(
                deepcopy(_document()),
                statuses=basic_registry().statuses,
                authority=_authority(material),
            ),
        ),
    )
    assert compiled_context.to_dict()["existing_skill_structures"] == (
        raw_context.to_dict()["existing_skill_structures"]
    )

    forged = replace(
        compiled,
        ir=replace(compiled.ir, canonical_hash="0" * 64),
    )
    _assert_gameplay_error(
        lambda: _context(
            existing_skills=(ExistingSkillInput.from_compiled(forged),),
        )
    )


@pytest.mark.parametrize(
    "bad_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        "4",
        10**100,
    ],
)
def test_summary_rejects_malformed_effect_scalars_before_hash_generation(
    bad_value: object,
):
    material = _material()
    raw = _effect("damage", amount=bad_value)
    with pytest.raises(GameplayContractError):
        _parse(_document(effects=[raw]), material)


def test_structural_summary_identity_invariance_and_semantic_sensitivity():
    material = _material()
    left_doc = _document(
        skill_id="review_alpha",
        name="Alpha",
        description="First description.",
        summary="First display.",
        effects=[
            _effect(
                "damage",
                amount=7.0,
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
    right_doc = deepcopy(left_doc)
    right_doc["identity"]["id"] = "review_beta"
    right_doc["identity"]["name"] = "Beta"
    right_doc["identity"]["description"] = "Second description."
    right_doc["display"]["summary"] = "Second display."
    left_context = _context(
        material=material,
        existing_skills=(ExistingSkillInput.from_compiled(
            compile_skill_ir(_parse(left_doc, material))
        ),),
    )
    right_context = _context(
        material=material,
        existing_skills=(ExistingSkillInput.from_compiled(
            compile_skill_ir(_parse(right_doc, material))
        ),),
    )
    assert left_context.context_hash == right_context.context_hash
    left_summary = left_context.to_dict()["existing_skill_structures"][0]
    assert left_summary == right_context.to_dict()[
        "existing_skill_structures"
    ][0]
    serialized = _canonical(left_summary)
    for omitted in (
        "review_alpha",
        "review_beta",
        "Alpha",
        "Beta",
        "First description",
        "effect_id",
        "entry_id",
    ):
        assert omitted not in serialized

    changed_doc = deepcopy(left_doc)
    changed_doc["entries"][0]["effects"][0]["amount"] = 8.0
    changed = left_context.structural_summary(_parse(changed_doc, material))
    assert changed["structural_hash"] != left_summary["structural_hash"]


def test_structural_summary_preserves_selector_reference_and_conditions():
    material = _material(
        kinds=("process_modify",),
        selectors=("current_area",),
    )
    document = _document(
        effects=[_effect(
            "process_modify",
            process_template_id="fixture_refine_mod",
            process_rate=2.5,
            condition={
                "all": [
                    {
                        "field": {
                            "subject": "current_area",
                            "key": "humidity",
                            "comparator": "gte",
                            "value": 0.4,
                        }
                    },
                    {
                        "derived": {
                            "subject": "current_area",
                            "key": "comfort",
                            "comparator": "gt",
                            "value": 1.0,
                        }
                    },
                ]
            },
        )],
        selectors=("current_area",),
    )
    context = _context(material=material, profile="process")
    summary = context.structural_summary(_parse(document, material))
    effect = summary["entries"][0]["effects"][0]
    assert summary["selectors"] == ["current_area"]
    assert effect["process_template_id"] == "fixture_refine_mod"
    assert effect["process_rate"] == 2.5
    assert effect["condition"]["kind"] == "all"
    assert [child["kind"] for child in effect["condition"]["children"]] == [
        "field",
        "derived",
    ]
    assert "Derived" in summary["state_classes"]


def test_context_and_catalog_source_anchor_hashes_are_recomputed():
    catalog = build_mechanism_catalog().to_dict()
    anchors = {
        row["path"]: row["sha256"] for row in catalog["source_anchors"]
    }
    root = PROJECT_ROOT / "experiments" / "generative_mechanics" / (
        "next_tracks_v06"
    )
    for path, digest in anchors.items():
        relative = path.split("gameplay_v04/", 1)[1]
        target = root / "gameplay_v04" / relative
        assert target.is_file()
        assert _path_sha256(target) == digest


def test_no_candidate_execution_or_arbitrary_world_paths_are_advertised():
    catalog = build_mechanism_catalog().to_dict()
    assert catalog["semantics"]["arbitrary_code"] is False
    assert catalog["semantics"]["arbitrary_world_paths"] is False
    assert catalog["provenance"]["candidate_data_execution"] is False
    assert catalog["conditions"]["semantics"]["arbitrary_expression"] is False
    assert catalog["selectors"]["single_target_restriction"][
        "multi_endpoint_selection_policy"
    ] is False


def test_profile_and_trigger_reserved_lifecycle_are_explicitly_unavailable():
    catalog = build_mechanism_catalog().to_dict()
    assert catalog["runtime_profiles"]["closed_profiles"] == list(PROFILES)
    supported = {
        (row["kind"], row.get("event"))
        for row in catalog["triggers"]["supported"]
    }
    assert supported == {("on_use", None), ("on_event", "damage_resolved")}
    for row in catalog["triggers"]["reserved"]:
        assert row["supported"] is False
        assert row["reason"].startswith("language_gap:")
    status = catalog["lifecycle"]["status_duration"]
    assert status["supported"] is False
    assert status["non_null"]["supported"] is False
    assert status["non_null"]["reason"] == "language_gap:lifecycle.status_duration"


def test_catalog_source_anchor_does_not_use_mutable_global_fixture_unless_marked():
    sources = _load_sources()
    changed = dict(sources)
    changed["effects.py"] += "\n# semantic drift marker\n"
    first = _build_catalog_document(sources)
    second = _build_catalog_document(changed)
    assert first["source_anchors"] != second["source_anchors"]
    # A comment-only drift should not silently change the parser semantics,
    # but it must change the anchor so the source hash is auditable.
    assert first["effects"] == second["effects"]
