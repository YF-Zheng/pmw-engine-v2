"""Public, offline generation context with trusted material authority."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from ..conditions import ConditionSpec, parse_condition
from ..contracts import GameplayContractError
from ..effects import EffectSpec
from ..materials import (
    MaterialAuthority,
    MaterialDefinition,
    MaterialTrait,
    material_authority,
    parse_material,
)
from ..reference_skills.fixtures import PROFILES
from ..skill_ir import (
    OPERATOR_KINDS,
    STATE_CLASS_KINDS,
    CompiledSkillIR,
    SkillIR,
    compile_skill_ir,
    parse_skill_ir,
)
from .catalog import MechanismCatalog, build_mechanism_catalog


CONTEXT_PROTOCOL = "pmw-generation-context-v1"
MAX_MATERIALS = 16
MAX_TRAITS_PER_MATERIAL = 16
MAX_PUBLIC_RULES = 32
MAX_PUBLIC_RULE_LENGTH = 512
MAX_ACQUIRED_CAPABILITIES = 32
MAX_CAPABILITY_LENGTH = 128
MAX_EXISTING_SKILLS = 16
_CAPABILITY = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")


@dataclass(frozen=True, slots=True)
class ExistingSkillInput:
    """Explicit trust wrapper for one already-validated Skill.

    Use ``from_compiled`` for a compiler result, or ``from_raw`` with the
    trusted status registry and material authority that parsed that document.
    A bare mapping is never interpreted as either trust source.
    """

    compiled: CompiledSkillIR | None = None
    raw: Any = None
    statuses: Mapping[str, Any] | None = None
    authority: MaterialAuthority | None = None

    def __post_init__(self) -> None:
        compiled_set = self.compiled is not None
        raw_set = self.raw is not None
        if compiled_set == raw_set:
            raise GameplayContractError(
                "ExistingSkillInput must contain exactly one of compiled or raw"
            )
        if compiled_set:
            if not isinstance(self.compiled, CompiledSkillIR):
                raise GameplayContractError(
                    "ExistingSkillInput.compiled must be CompiledSkillIR"
                )
            if self.statuses is not None or self.authority is not None:
                raise GameplayContractError(
                    "ExistingSkillInput.compiled does not accept trust arguments"
                )
        else:
            if not isinstance(self.statuses, Mapping):
                raise GameplayContractError(
                    "existing raw Skill requires trusted statuses"
                )
            if not isinstance(self.authority, MaterialAuthority):
                raise GameplayContractError(
                    "existing raw Skill requires trusted MaterialAuthority"
                )

    @classmethod
    def from_compiled(cls, compiled: CompiledSkillIR) -> "ExistingSkillInput":
        return cls(compiled=compiled)

    @classmethod
    def from_raw(
        cls,
        raw: Any,
        *,
        statuses: Mapping[str, Any],
        authority: MaterialAuthority,
    ) -> "ExistingSkillInput":
        return cls(raw=raw, statuses=statuses, authority=authority)

    def validated_compiled(self) -> CompiledSkillIR:
        """Re-run trusted compilation instead of accepting editable fields."""
        if self.compiled is not None:
            return compile_skill_ir(self.compiled.ir)
        parsed = parse_skill_ir(
            self.raw,
            self.statuses or {},
            self.authority,
        )
        return compile_skill_ir(parsed)


@dataclass(frozen=True, slots=True)
class GenerationContext:
    """Immutable canonical public context; all outputs are fresh copies."""

    context_hash: str
    canonical_json: str
    catalog: MechanismCatalog

    def __post_init__(self) -> None:
        actual = hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()
        if actual != self.context_hash:
            raise GameplayContractError(
                "generation context hash does not match canonical JSON"
            )
        try:
            document = json.loads(self.canonical_json)
        except (TypeError, ValueError) as error:
            raise GameplayContractError(
                "generation context JSON is invalid"
            ) from error
        if (
            document.get("version") != CONTEXT_PROTOCOL
            or document.get("catalog", {}).get("hash")
            != self.catalog.catalog_hash
        ):
            raise GameplayContractError(
                "generation context identity does not match its catalog"
            )

    @property
    def hash(self) -> str:
        return self.context_hash

    @property
    def catalog_hash(self) -> str:
        return self.catalog.catalog_hash

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-native copy of the canonical context."""
        return json.loads(self.canonical_json)

    def structural_summary(self, skill: SkillIR | CompiledSkillIR) -> dict[str, Any]:
        """Return semantic structure without Skill/entry/effect identity labels.

        This is a skeleton plus semantic references and magnitudes. It is not
        behavioural deduplication and makes no runtime-equivalence claim.
        """
        return _structural_summary(skill)


def build_generation_context(
    *,
    profile: str,
    materials: Sequence[MaterialDefinition],
    complexity: int,
    public_known_rules: Sequence[str],
    acquired_capabilities: Sequence[str],
    existing_skills: Sequence[ExistingSkillInput] = (),
) -> GenerationContext:
    """Build one bounded public context from an explicit trusted allowlist."""
    selected_profile = _closed_profile(profile)
    selected_complexity = _complexity(complexity)
    validated_materials = _validated_materials(materials)
    authority = material_authority(validated_materials)
    if (
        isinstance(authority.budget_points, bool)
        or not isinstance(authority.budget_points, (int, float))
        or not math.isfinite(authority.budget_points)
        or authority.budget_points <= 0
    ):
        raise GameplayContractError(
            "aggregate material authority budget must be finite and positive"
        )
    rules = _bounded_strings(
        public_known_rules,
        "public_known_rules",
        MAX_PUBLIC_RULES,
        MAX_PUBLIC_RULE_LENGTH,
        identifier=False,
    )
    capabilities = _bounded_strings(
        acquired_capabilities,
        "acquired_capabilities",
        MAX_ACQUIRED_CAPABILITIES,
        MAX_CAPABILITY_LENGTH,
        identifier=True,
    )
    skill_inputs = _bounded_existing_skills(existing_skills)
    summaries = [
        _validated_summary(item)
        for item in skill_inputs
    ]
    summaries.sort(
        key=lambda row: (
            row["structural_hash"],
            json.dumps(row, sort_keys=True, separators=(",", ":")),
        )
    )

    catalog = build_mechanism_catalog()
    material_rows = _material_rows(validated_materials)
    document = {
        "version": CONTEXT_PROTOCOL,
        "catalog": {
            "version": catalog.version,
            "hash": catalog.catalog_hash,
            "document": catalog.to_dict(),
        },
        "profile": selected_profile,
        "complexity": selected_complexity,
        "materials": material_rows,
        "authority": {
            "material_ids": list(authority.material_ids),
            "effect_kinds": list(authority.effect_kinds),
            "selectors": list(authority.selectors),
            "budget_points": authority.budget_points,
            "derivation": "validated_material_traits_only",
        },
        "public_known_rules": list(rules),
        "acquired_capabilities": list(capabilities),
        "existing_skill_structures": summaries,
        "summary_semantics": {
            "identity_labels_omitted": [
                "skill_id",
                "version",
                "name",
                "description",
                "display",
                "origin",
                "entry_id",
                "effect_id",
            ],
            "semantic_references_preserved": True,
            "numeric_magnitudes_preserved": True,
            "behavioral_identity_claimed": False,
            "purpose": "bounded structural context only",
        },
        "visibility": {
            "public_allowlist_only": True,
            "world_state_included": False,
            "registry_dump_included": False,
        },
    }
    canonical_json = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return GenerationContext(digest, canonical_json, catalog)


def _closed_profile(profile: Any) -> str:
    if not isinstance(profile, str) or profile not in PROFILES:
        raise GameplayContractError(
            f"profile must be one of the closed reference profiles {PROFILES}"
        )
    return profile


def _complexity(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= 3
    ):
        raise GameplayContractError("complexity must be an integer in [1, 3]")
    return value


def _sequence(value: Any, name: str) -> tuple[Any, ...]:
    if (
        isinstance(value, (str, bytes, bytearray, Mapping))
        or not isinstance(value, Sequence)
    ):
        raise GameplayContractError(f"{name} must be a sequence")
    return tuple(value)


def _bounded_strings(
    value: Any,
    name: str,
    maximum_count: int,
    maximum_length: int,
    *,
    identifier: bool,
) -> tuple[str, ...]:
    items = _sequence(value, name)
    if len(items) > maximum_count:
        raise GameplayContractError(
            f"{name} permits at most {maximum_count} entries"
        )
    result = []
    for index, item in enumerate(items):
        if not isinstance(item, str) or not item:
            raise GameplayContractError(
                f"{name}[{index}] must be a non-empty string"
            )
        if len(item) > maximum_length:
            raise GameplayContractError(
                f"{name}[{index}] exceeds {maximum_length} characters"
            )
        if identifier and _CAPABILITY.fullmatch(item) is None:
            raise GameplayContractError(
                f"{name}[{index}] is not a bounded capability name"
            )
        result.append(item)
    if len(set(result)) != len(result):
        raise GameplayContractError(f"{name} contains duplicates")
    return tuple(sorted(result))


def _validated_materials(value: Any) -> tuple[MaterialDefinition, ...]:
    items = _sequence(value, "materials")
    if not items:
        raise GameplayContractError("materials must be non-empty")
    if len(items) > MAX_MATERIALS:
        raise GameplayContractError(
            f"materials permits at most {MAX_MATERIALS} entries"
        )
    validated = []
    for index, material in enumerate(items):
        if not isinstance(material, MaterialDefinition):
            raise GameplayContractError(
                f"materials[{index}] must be a trusted MaterialDefinition"
            )
        try:
            traits = tuple(material.traits)
            if len(traits) > MAX_TRAITS_PER_MATERIAL:
                raise GameplayContractError(
                    f"materials[{index}].traits permits at most "
                    f"{MAX_TRAITS_PER_MATERIAL} entries"
                )
            if any(not isinstance(item, MaterialTrait) for item in traits):
                raise GameplayContractError(
                    f"materials[{index}].traits contains a malformed trait"
                )
            known = {
                "id": material.id,
                "tier": material.tier,
                "region_rarity": material.region_rarity,
                "traits": [
                    {
                        "id": item.id,
                        "effect_kinds": list(item.effect_kinds),
                        "selectors": list(item.selectors),
                        "budget_points": item.budget_points,
                    }
                    for item in traits
                ],
            }
            validated.append(parse_material(known, f"$.materials[{index}]"))
        except GameplayContractError:
            raise
        except (
            AttributeError,
            TypeError,
            ValueError,
            OverflowError,
            KeyError,
            RecursionError,
        ) as error:
            raise GameplayContractError(
                f"materials[{index}] failed defensive revalidation: "
                f"{type(error).__name__}: {error}"
            ) from error
    if len({item.id for item in validated}) != len(validated):
        raise GameplayContractError("materials must have unique IDs")
    return tuple(sorted(validated, key=lambda item: item.id))


def _validated_summary(item: ExistingSkillInput) -> dict[str, Any]:
    try:
        return _structural_summary(item.validated_compiled())
    except GameplayContractError:
        raise
    except (
        AttributeError,
        TypeError,
        ValueError,
        OverflowError,
        KeyError,
        RecursionError,
    ) as error:
        raise GameplayContractError(
            "existing Skill failed defensive revalidation: "
            f"{type(error).__name__}: {error}"
        ) from error


def _bounded_existing_skills(value: Any) -> tuple[ExistingSkillInput, ...]:
    items = _sequence(value, "existing_skills")
    if len(items) > MAX_EXISTING_SKILLS:
        raise GameplayContractError(
            f"existing_skills permits at most {MAX_EXISTING_SKILLS} entries"
        )
    for index, item in enumerate(items):
        if not isinstance(item, ExistingSkillInput):
            raise GameplayContractError(
                f"existing_skills[{index}] must be ExistingSkillInput"
            )
    return tuple(items)


def _material_rows(
    materials: tuple[MaterialDefinition, ...],
) -> list[dict[str, Any]]:
    rows = []
    for material in materials:
        rows.append({
            "id": material.id,
            "tier": material.tier,
            "region_rarity": material.region_rarity,
            "traits": [
                {
                    "id": trait.id,
                    "effect_kinds": list(trait.effect_kinds),
                    "selectors": list(trait.selectors),
                    "budget_points": trait.budget_points,
                }
                for trait in sorted(material.traits, key=lambda item: item.id)
            ],
        })
    return rows


def _structural_summary(
    value: SkillIR | CompiledSkillIR,
) -> dict[str, Any]:
    if isinstance(value, CompiledSkillIR):
        compiled = compile_skill_ir(value.ir)
        ir = compiled.ir
    elif isinstance(value, SkillIR):
        compiled = compile_skill_ir(value)
        ir = compiled.ir
    else:
        raise GameplayContractError(
            "structural summary requires SkillIR or CompiledSkillIR"
        )
    effect_rows = []
    all_operators = set()
    all_state_classes = set()
    if len(ir.entries) != len(compiled.blueprints):
        raise GameplayContractError(
            "compiled Skill entry count does not match lowered Actions"
        )
    for entry, blueprint in zip(ir.entries, compiled.blueprints):
        if (
            f"{ir.id}__{entry.id}" != blueprint.action.id
            or len(entry.effects) != len(blueprint.action.effects)
            or entry.trigger_kind
            != (
                "on_event"
                if blueprint.kind == "passive_blueprint"
                else "on_use"
            )
        ):
            raise GameplayContractError(
                "compiled Skill entry structure does not match lowered Actions"
            )
        rows = []
        for effect in blueprint.effects:
            summary = _effect_summary(effect)
            rows.append(summary)
            all_operators.update(summary["operators"])
            all_state_classes.update(summary["state_classes"])
        effect_rows.append({
            "trigger": {
                "kind": entry.trigger_kind,
                "event": entry.event,
            },
            "condition": _condition_summary(entry.condition),
            "effects": rows,
            "max_firings_per_root": entry.max_firings_per_root,
        })
    condition_derived = any(
        _condition_has_kind(child, "derived")
        for row in effect_rows
        for child in (
            *_condition_children(row["condition"]),
            *(
                child
                for effect in row["effects"]
                for child in _condition_children(effect["condition"])
            ),
        )
    )
    if condition_derived:
        all_state_classes.add("Derived")
    document = {
        "summary_kind": "semantic_structure_not_behavioral_identity",
        "selectors": list(ir.selectors),
        "relation_types": list(ir.relation_types),
        "costs": {"mana": ir.mana, "duration": ir.duration},
        "budget": ir.budget,
        "limits": {
            "condition_nodes": ir.condition_nodes,
            "condition_max_depth": ir.condition_limits.max_depth,
            "condition_max_nodes": ir.condition_limits.max_nodes,
            "condition_max_children": ir.condition_limits.max_children,
        },
        "lifecycle_status_duration": (
            None
            if ir.status_duration is None
            else deepcopy(dict(ir.status_duration))
        ),
        "entries": effect_rows,
        "operators": sorted(all_operators),
        "state_classes": [
            name for name in STATE_CLASS_KINDS if name in all_state_classes
        ],
        "behavioral_identity_claimed": False,
    }
    canonical = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    document["structural_hash"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return document


def _effect_summary(effect: EffectSpec) -> dict[str, Any]:
    operators = sorted(
        operator
        for operator, kinds in OPERATOR_KINDS.items()
        if effect.kind in kinds
    )
    state_classes = [
        name
        for name, kinds in STATE_CLASS_KINDS.items()
        if effect.kind in kinds
    ]
    if len(operators) != 1:
        raise GameplayContractError(
            f"Effect {effect.kind!r} lacks one Operator classification"
        )
    return {
        "kind": effect.kind,
        "operators": operators,
        "state_classes": state_classes,
        "target": {
            "kind": effect.target.kind,
            "relation_type": effect.target.relation_type,
        },
        "commitment": effect.commitment,
        "condition": _condition_summary(effect.condition),
        "amount": effect.amount,
        "resource": effect.resource,
        "field_id": effect.field_id,
        "trait_id": effect.trait_id,
        "status_id": effect.status_id,
        "duration": effect.duration,
        "attribute_terms": [
            {
                "kind": term.kind,
                "attribute": term.attribute,
                "coefficient": term.coefficient,
                "comparator": term.comparator,
                "threshold": term.threshold,
                "operation": term.operation,
                "value": term.value,
                "maximum": term.maximum,
            }
            for term in effect.terms
        ],
        "sensing": effect.sensing,
        "evadable": effect.evadable,
        "process_template_id": effect.process_template_id,
        "process_rate": effect.process_rate,
        "process_remaining_ticks": effect.process_remaining_ticks,
        "drive_profile_id": effect.drive_profile_id,
        "drive_rate": effect.drive_rate,
        "relation_profile_id": effect.relation_profile_id,
        "relation_enabled": effect.relation_enabled,
        "rate_add": effect.rate_add,
        "rate_multiplier": effect.rate_multiplier,
        "curve": effect.curve,
        "curve_priority": effect.curve_priority,
    }


def _condition_summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {"kind": "always"}
    if isinstance(value, ConditionSpec):
        return {
            "kind": value.kind,
            "subject": value.subject,
            "key": value.key,
            "comparator": value.comparator,
            "value": value.value,
            "children": [
                _condition_summary(child) for child in value.children
            ],
        }
    if isinstance(value, Mapping):
        return _condition_summary(parse_condition(deepcopy(dict(value))))
    raise GameplayContractError("condition cannot be summarized")


def _condition_has_kind(value: Mapping[str, Any], kind: str) -> bool:
    return value.get("kind") == kind or any(
        _condition_has_kind(child, kind)
        for child in value.get("children", ())
    )


def _condition_children(
    value: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    return (value, *value.get("children", ()))
