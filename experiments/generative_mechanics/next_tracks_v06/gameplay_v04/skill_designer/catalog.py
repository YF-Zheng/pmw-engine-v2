"""Canonical, source-anchored catalog for the accepted offline Skill IR."""

from __future__ import annotations

from dataclasses import dataclass
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ..conditions import ConditionLimits
from ..contracts import ATTRIBUTES, CURVES, SELECTOR_KINDS
from ..effects import EFFECT_KINDS
from ..materials import MATERIAL_TIERS, REGION_RARITIES
from ..skill_ir import (
    MAX_DESCRIPTION_LENGTH,
    MAX_ENTRIES,
    MAX_JSON_DEPTH,
    MAX_JSON_SAFE_INT,
    MAX_JSON_STRING,
    MAX_JSON_VALUES,
    MAX_MODEL_LENGTH,
    MAX_NAME_LENGTH,
    MAX_SUMMARY_LENGTH,
    MAX_TAGS,
    OPERATOR_KINDS,
    PROTOCOL,
    RESERVED_EVENTS,
    RESERVED_TRIGGERS,
    STATE_CLASS_KINDS,
    SUPPORTED_EVENT,
)


CATALOG_PROTOCOL = "pmw-mechanism-catalog-v1"
_GAMEPLAY_ROOT = Path(__file__).resolve().parents[1]

_SOURCE_ROLES = {
    "skill_ir.py": "IR protocol, triggers, operator/state maps, limits",
    "effects.py": "closed Effect kinds and per-kind parameter schema",
    "conditions.py": "pure condition grammar and defaults",
    "selectors.py": "selector shape and linked relation field",
    "materials.py": "material revalidation and authority derivation",
    "skills.py": "lowered Skill constraints and budget arithmetic",
    "attributes.py": "attribute term schema",
    "contracts.py": "selector enum, attributes, curves, state classes",
    "hooks.py": "bounded passive dispatch limits",
    "processes.py": "Process runtime caps",
    "drives.py": "Drive runtime caps",
    "relations.py": "Relation runtime caps",
    "reference_skills/fixtures.py": "closed reference profile set",
}

_EXPECTED_EFFECT_FIELDS = {
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
        "relation_profile_id",
        "relation_enabled",
        "duration",
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

_EXPECTED_OPERATORS = {
    "impulse": {
        "damage",
        "heal",
        "shield",
        "add_resource",
        "modify_field",
        "apply_status",
        "grant_trait",
    },
    "drive/source": {"drive_source"},
    "attractor_modifier": {"modify_attractor"},
    "dynamics_modifier": {"modify_rate", "dynamics_modifier"},
    "process_start": {"process_start"},
    "process_modify": {"process_modify"},
    "relation_modifier": {"relation_modifier", "move_actor"},
}

_EXPECTED_STATE_CLASSES = {
    "Field": {
        "modify_field",
        "modify_attractor",
        "modify_rate",
        "dynamics_modifier",
    },
    "Stock": {
        "add_resource",
        "process_start",
        "process_modify",
        "drive_source",
    },
    "Process": {"process_start", "process_modify"},
    "Relation": {"relation_modifier", "move_actor"},
    "Discrete": {"apply_status", "grant_trait"},
    "Derived": set(),
}

_EXPECTED_EFFECT_KINDS = (
    "damage",
    "heal",
    "shield",
    "add_resource",
    "apply_status",
    "modify_field",
    "modify_attractor",
    "modify_rate",
    "grant_trait",
    "process_start",
    "process_modify",
    "drive_source",
    "relation_modifier",
    "dynamics_modifier",
    "move_actor",
)


class CatalogSourceError(RuntimeError):
    """The accepted source no longer matches the catalog extractor."""


@dataclass(frozen=True, slots=True)
class MechanismCatalog:
    """Immutable canonical catalog snapshot; callers only receive copies."""

    version: str
    ir_protocol: str
    catalog_hash: str
    canonical_json: str

    def __post_init__(self) -> None:
        actual = hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()
        if actual != self.catalog_hash:
            raise CatalogSourceError("catalog hash does not match canonical JSON")
        try:
            document = json.loads(self.canonical_json)
        except (TypeError, ValueError) as error:
            raise CatalogSourceError("catalog JSON is invalid") from error
        if (
            document.get("version") != self.version
            or document.get("ir_protocol") != self.ir_protocol
        ):
            raise CatalogSourceError("catalog identity does not match JSON")

    @property
    def hash(self) -> str:
        return self.catalog_hash

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-native copy so aliases cannot change the hash."""
        return json.loads(self.canonical_json)


def build_mechanism_catalog() -> MechanismCatalog:
    """Build and verify the canonical catalog from accepted parser sources."""
    document = _build_catalog_document(_load_sources())
    canonical_json = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return MechanismCatalog(
        CATALOG_PROTOCOL,
        document["ir_protocol"],
        digest,
        canonical_json,
    )


def _load_sources(
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    sources: dict[str, str] = {}
    for name in _SOURCE_ROLES:
        if overrides is not None and name in overrides:
            text = overrides[name]
        else:
            path = _GAMEPLAY_ROOT / name
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as error:
                raise CatalogSourceError(
                    f"cannot read accepted source {path}"
                ) from error
        if not isinstance(text, str):
            raise CatalogSourceError(f"source override {name} must be text")
        sources[name] = text
    if overrides is not None:
        unknown = sorted(set(overrides) - set(_SOURCE_ROLES))
        if unknown:
            raise CatalogSourceError(
                f"unsupported source override paths: {unknown}"
            )
    return sources


def _build_catalog_document(sources: Mapping[str, str]) -> dict[str, Any]:
    effect_tree = _parse_source(sources["effects.py"], "effects.py")
    skill_tree = _parse_source(sources["skill_ir.py"], "skill_ir.py")
    condition_tree = _parse_source(sources["conditions.py"], "conditions.py")
    contracts_tree = _parse_source(sources["contracts.py"], "contracts.py")
    selector_tree = _parse_source(sources["selectors.py"], "selectors.py")
    materials_tree = _parse_source(sources["materials.py"], "materials.py")
    skills_tree = _parse_source(sources["skills.py"], "skills.py")
    hooks_tree = _parse_source(sources["hooks.py"], "hooks.py")
    process_tree = _parse_source(sources["processes.py"], "processes.py")
    drive_tree = _parse_source(sources["drives.py"], "drives.py")
    relation_tree = _parse_source(sources["relations.py"], "relations.py")
    fixture_tree = _parse_source(
        sources["reference_skills/fixtures.py"],
        "reference_skills/fixtures.py",
    )
    attribute_tree = _parse_source(sources["attributes.py"], "attributes.py")

    effect_kinds = _module_literal(effect_tree, "EFFECT_KINDS", "effects.py")
    if tuple(effect_kinds) != _EXPECTED_EFFECT_KINDS:
        raise CatalogSourceError(
            "unsupported EFFECT_KINDS drift: "
            f"{tuple(effect_kinds)!r}"
        )
    if tuple(EFFECT_KINDS) != _EXPECTED_EFFECT_KINDS:
        raise CatalogSourceError("imported EFFECT_KINDS disagrees with source")

    operator_map = _mapping_of_string_sets(
        _module_literal(skill_tree, "OPERATOR_KINDS", "skill_ir.py"),
        "OPERATOR_KINDS",
    )
    state_map = _mapping_of_string_sets(
        _module_literal(skill_tree, "STATE_CLASS_KINDS", "skill_ir.py"),
        "STATE_CLASS_KINDS",
    )
    if operator_map != _EXPECTED_OPERATORS:
        raise CatalogSourceError(
            "unsupported OPERATOR_KINDS drift: "
            f"{operator_map!r}"
        )
    if state_map != _EXPECTED_STATE_CLASSES:
        raise CatalogSourceError(
            "unsupported STATE_CLASS_KINDS drift: "
            f"{state_map!r}"
        )
    _check_imported_mapping(OPERATOR_KINDS, operator_map, "OPERATOR_KINDS")
    _check_imported_mapping(STATE_CLASS_KINDS, state_map, "STATE_CLASS_KINDS")

    effect_fields, common, optional, process_optional = (
        _extract_effect_schema(effect_tree, effect_kinds)
    )
    selector_kinds = tuple(
        _module_literal(contracts_tree, "SELECTOR_KINDS", "contracts.py")
    )
    if selector_kinds != tuple(SELECTOR_KINDS):
        raise CatalogSourceError("selector source/import parity failed")
    if set(selector_kinds) != {
        "self",
        "target_actor",
        "current_area",
        "linked_object",
        "adjacent_area",
    }:
        raise CatalogSourceError(
            f"unsupported selector drift: {selector_kinds!r}"
        )

    trigger_data = _extract_trigger_schema(skill_tree)
    condition_data = _extract_condition_schema(
        condition_tree,
        contracts_tree,
    )
    material_data = _extract_material_enums(materials_tree)
    profile_data = _extract_profiles(fixture_tree)
    limits_data = _extract_limits(
        skill_tree,
        hooks_tree,
        process_tree,
        drive_tree,
        relation_tree,
    )
    budget_data = _extract_budget(skills_tree)
    attribute_data = _extract_attribute_terms(attribute_tree)

    effect_documents = {}
    for kind in effect_kinds:
        allowed = (
            set(common) | set(effect_fields[kind])
            if kind == "dynamics_modifier"
            else set(common) | set(optional) | set(effect_fields[kind])
        )
        required = set(common) | set(effect_fields[kind])
        if kind == "move_actor":
            allowed = set(common)
            required = set(common)
        elif kind == "process_modify":
            required -= set(process_optional)
        operators = sorted(
            operator for operator, kinds in operator_map.items()
            if kind in kinds
        )
        state_classes = [
            state_class for state_class, kinds in state_map.items()
            if kind in kinds
        ]
        if len(operators) != 1:
            raise CatalogSourceError(
                f"{kind} must map to exactly one Operator, got {operators}"
            )
        effect_documents[kind] = {
            "source_rule": "parse_effect:fields[kind]",
            "schema_derivation": "source_ast_literal",
            "supported": True,
            "operators": operators,
            "state_classes": state_classes,
            "allowed_keys": sorted(allowed),
            "required_keys": sorted(required),
            "optional_keys": sorted(allowed - required),
            "excluded_optional_keys": sorted(
                set(optional) if kind == "dynamics_modifier" else set()
            ),
            "conditional_rules": _conditional_effect_rules(kind),
            "value_constraints": _effect_constraints(kind),
            "post_extraction_manifest": {
                "role": (
                    "explicit source-anchored rules that are not expressible "
                    "as a single parser literal"
                ),
                "derived_by": "catalog_owner_static_manifest",
                "executes_candidate_data": False,
                "allowed_keys_source": "source_ast_literal",
                "required_keys_source": "source_ast_literal",
            },
        }

    coverage = {
        "effect_kinds": list(effect_kinds),
        "effect_kind_count": len(effect_kinds),
        "operator_families": list(operator_map),
        "operator_family_count": len(operator_map),
        "state_classes": list(state_map),
        "state_class_count": len(state_map),
        "operator_unmapped_effect_kinds": sorted(
            set(effect_kinds)
            - {item for kinds in operator_map.values() for item in kinds}
        ),
        "state_unmapped_effect_kinds": sorted(
            set(effect_kinds)
            - {item for kinds in state_map.values() for item in kinds}
        ),
    }
    if coverage["operator_unmapped_effect_kinds"]:
        raise CatalogSourceError("an Effect kind has no Operator mapping")
    if set(coverage["state_unmapped_effect_kinds"]) != {
        "damage",
        "heal",
        "shield",
    }:
        raise CatalogSourceError(
            "state-class coverage changed outside the accepted "
            "Actor Stock/HP effects"
        )

    document = {
        "version": CATALOG_PROTOCOL,
        "ir_protocol": _module_literal(
            skill_tree, "PROTOCOL", "skill_ir.py"
        ),
        "language_status": {
            "executable": True,
            "scope": "accepted P2.1/P2.2 subset only",
            "catalog_metadata_is_ir_member": False,
        },
        "source_anchors": _source_anchors(sources),
        "provenance": {
            "source_loading": (
                "fixed_relative_sources_only; no candidate input is evaluated"
            ),
            "effect_allowed_required_keys": (
                "ast_literal_extraction_from_parse_effect"
            ),
            "effect_conditional_rules": (
                "static_source_anchored_manifest_checked_by_tests"
            ),
            "effect_value_constraints": (
                "static_source_anchored_manifest_checked_by_tests"
            ),
            "composition_rules": (
                "source_literal_and_static_source_anchored_manifest"
            ),
            "runtime_caps": (
                "ast_literal_extraction_from_closed_typed_sources"
            ),
            "reserved_and_lifecycle_semantics": (
                "ast_constants_and_guard_source_check"
            ),
            "candidate_data_execution": False,
        },
        "coverage": coverage,
        "effects": {
            "common_required_keys": sorted(common),
            "common_optional_keys": sorted(optional),
            "process_modify_optional_keys": sorted(process_optional),
            "kinds": effect_documents,
        },
        "operators": {
            name: sorted(kinds) for name, kinds in operator_map.items()
        },
        "state_classes": {
            name: sorted(kinds) for name, kinds in state_map.items()
        },
        "conditions": condition_data,
        "selectors": _selector_document(selector_kinds),
        "triggers": trigger_data,
        "lifecycle": _lifecycle_document(
            skill_tree, sources["skill_ir.py"]
        ),
        "composition": _composition_rules(skills_tree, skill_tree),
        "limits": limits_data,
        "budget_arithmetic": budget_data,
        "attribute_terms": attribute_data,
        "materials": material_data,
        "runtime_profiles": profile_data,
        "semantics": {
            "conditions": "pure_read_only",
            "catalog": "immutable_canonical_snapshot",
            "source_rules": "static_ast_extraction_fail_closed",
            "parameter_values": "must_be_supplied_by_candidate",
            "arbitrary_code": False,
            "arbitrary_world_paths": False,
        },
    }
    if document["ir_protocol"] != PROTOCOL:
        raise CatalogSourceError("IR protocol source/import parity failed")
    return document


def _parse_source(text: str, name: str) -> ast.Module:
    try:
        return ast.parse(text, filename=name)
    except SyntaxError as error:
        raise CatalogSourceError(f"{name} cannot be parsed") from error


def _module_literal(tree: ast.Module, name: str, source: str) -> Any:
    matches = [
        node.value
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and _assigned_name(node) == name
    ]
    if len(matches) != 1:
        raise CatalogSourceError(
            f"{source}:{name} must have one module literal"
        )
    return _literal_value(matches[0], {}, f"{source}:{name}")


def _assigned_name(node: ast.Assign | ast.AnnAssign) -> str | None:
    target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _literal_value(
    node: ast.AST,
    environment: Mapping[str, Any],
    path: str,
) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, int, float, bool)) or node.value is None:
            return node.value
        raise CatalogSourceError(f"{path} has unsupported constant")
    if isinstance(node, ast.Name):
        if node.id not in environment:
            raise CatalogSourceError(f"{path} references unknown {node.id}")
        return environment[node.id]
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        values = [
            _literal_value(item, environment, f"{path}[{index}]")
            for index, item in enumerate(node.elts)
        ]
        return tuple(values) if isinstance(node, ast.Tuple) else set(values)
    if isinstance(node, ast.Dict):
        result = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                raise CatalogSourceError(f"{path} has dictionary unpacking")
            key = _literal_value(key_node, environment, f"{path}.key")
            if not isinstance(key, str):
                raise CatalogSourceError(f"{path} has a non-text key")
            if key in result:
                raise CatalogSourceError(f"{path} repeats key {key!r}")
            result[key] = _literal_value(
                value_node, environment, f"{path}.{key}"
            )
        return result
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in {
            "frozenset", "set", "tuple", "list",
        }:
            raise CatalogSourceError(f"{path} has unsupported call")
        if node.keywords or len(node.args) > 1:
            raise CatalogSourceError(f"{path} call shape is unsupported")
        value = (
            ()
            if not node.args
            else _literal_value(node.args[0], environment, path)
        )
        converted = {
            "frozenset": frozenset,
            "set": set,
            "tuple": tuple,
            "list": list,
        }[node.func.id](value)
        return converted
    if isinstance(node, ast.BinOp):
        left = _literal_value(node.left, environment, f"{path}.left")
        right = _literal_value(node.right, environment, f"{path}.right")
        if isinstance(node.op, ast.BitOr) and isinstance(left, set) and isinstance(
            right, set
        ):
            return left | right
        if (
            isinstance(node.op, ast.Pow)
            and isinstance(left, int)
            and not isinstance(left, bool)
            and isinstance(right, int)
            and not isinstance(right, bool)
            and 0 <= right <= 63
        ):
            return left**right
        if isinstance(node.op, ast.Add) and isinstance(left, (tuple, str)):
            return left + right
        raise CatalogSourceError(f"{path} has unsupported binary expression")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _literal_value(node.operand, environment, path)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return -value
        raise CatalogSourceError(f"{path} has unsupported negation")
    raise CatalogSourceError(
        f"{path} has unsupported AST node {type(node).__name__}"
    )


def _mapping_of_string_sets(value: Any, name: str) -> dict[str, set[str]]:
    if not isinstance(value, dict):
        raise CatalogSourceError(f"{name} must be a dictionary literal")
    result = {}
    for key, items in value.items():
        if (
            not isinstance(key, str)
            or not isinstance(items, (set, frozenset))
            or any(not isinstance(item, str) for item in items)
        ):
            raise CatalogSourceError(f"{name} has unsupported value shape")
        result[key] = set(items)
    return result


def _check_imported_mapping(
    imported: Mapping[str, frozenset[str]],
    extracted: Mapping[str, set[str]],
    name: str,
) -> None:
    converted = {key: set(value) for key, value in imported.items()}
    if converted != dict(extracted):
        raise CatalogSourceError(f"imported {name} disagrees with source AST")


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise CatalogSourceError(f"expected one function {name}")
    return matches[0]


def _function_assignment(
    function: ast.FunctionDef,
    name: str,
    environment: Mapping[str, Any],
    path: str,
) -> Any:
    matches = [
        node
        for node in function.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == name
    ]
    if len(matches) != 1:
        raise CatalogSourceError(f"{path}:{name} must have one assignment")
    return _literal_value(matches[0].value, environment, f"{path}:{name}")


def _extract_effect_schema(
    tree: ast.Module,
    effect_kinds: tuple[str, ...],
) -> tuple[dict[str, set[str]], set[str], set[str], set[str]]:
    function = _function(tree, "parse_effect")
    common_raw = _function_assignment(
        function, "common", {}, "effects.py:parse_effect"
    )
    optional_raw = _function_assignment(
        function, "optional", {}, "effects.py:parse_effect"
    )
    process_raw = _function_assignment(
        function, "process_modify_optional", {}, "effects.py:parse_effect"
    )
    fields_raw = _function_assignment(
        function,
        "fields",
        {"process_modify_optional": process_raw},
        "effects.py:parse_effect",
    )
    if not all(
        isinstance(value, set)
        and all(isinstance(item, str) for item in value)
        for value in (common_raw, optional_raw, process_raw)
    ):
        raise CatalogSourceError("parse_effect key sets must be text literals")
    if not isinstance(fields_raw, dict):
        raise CatalogSourceError("parse_effect fields must be a dict literal")
    fields = {}
    for kind, values in fields_raw.items():
        if (
            not isinstance(kind, str)
            or not isinstance(values, set)
            or any(not isinstance(item, str) for item in values)
        ):
            raise CatalogSourceError("parse_effect fields has invalid shape")
        fields[kind] = set(values)
    if tuple(fields) != tuple(effect_kinds):
        raise CatalogSourceError(
            "EFFECT_KINDS and parse_effect field order differ"
        )
    if fields != _EXPECTED_EFFECT_FIELDS:
        raise CatalogSourceError(
            "unsupported parse_effect parameter schema drift: "
            f"{fields!r}"
        )
    common, optional, process_optional = (
        set(common_raw),
        set(optional_raw),
        set(process_raw),
    )
    if common != {"id", "kind", "target", "commitment"}:
        raise CatalogSourceError(f"unsupported common Effect keys: {common}")
    if optional != {"condition", "attribute_terms", "targeting"}:
        raise CatalogSourceError(
            f"unsupported optional Effect keys: {optional}"
        )
    if process_optional != {
        "process_rate",
        "process_remaining_ticks",
    }:
        raise CatalogSourceError(
            f"unsupported process_modify options: {process_optional}"
        )
    return fields, common, optional, process_optional


def _conditional_effect_rules(kind: str) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    if kind == "process_modify":
        rules.append({
            "rule": "at_least_one_non_null",
            "keys": ["process_rate", "process_remaining_ticks"],
            "source_rule": "parse_effect:process_modify:missing_required",
        })
    if kind == "dynamics_modifier":
        rules.append({
            "rule": "optional_keys_absent",
            "keys": ["condition", "attribute_terms", "targeting"],
            "source_rule": "parse_effect:dynamics_modifier:allowed",
        })
    if kind == "move_actor":
        rules.extend([
            {
                "rule": "target_exact",
                "value": {"kind": "adjacent_area"},
                "source_rule": "parse_effect:move_actor:target",
            },
            {
                "rule": "commitment_exact",
                "value": "required",
                "source_rule": "parse_effect:move_actor:commitment",
            },
            {
                "rule": "effect_id_pattern",
                "value": "[a-z][a-z0-9_]{1,63}",
                "source_rule": "parse_effect:move_actor:id",
            },
        ])
    if kind in {
        "process_start",
        "process_modify",
        "drive_source",
        "relation_modifier",
        "dynamics_modifier",
    }:
        rules.append({
            "rule": "target_exact",
            "value": {"kind": "current_area"},
            "source_rule": f"parse_effect:{kind}:target",
        })
        rules.append({
            "rule": "commitment_exact",
            "value": "required",
            "source_rule": f"parse_effect:{kind}:commitment",
        })
        rules.append({
            "rule": "attribute_terms_absent",
            "source_rule": f"parse_effect:{kind}:terms",
        })
        rules.append({
            "rule": "targeting_default_only",
            "value": {"sensing": "none", "evadable": False},
            "source_rule": f"parse_effect:{kind}:targeting",
        })
    return rules


def _effect_constraints(kind: str) -> dict[str, Any]:
    constraints: dict[str, Any] = {
        "effect_id": {
            "required": True,
            "type": "string",
            "nonempty": True,
            "pattern": (
                "[a-z][a-z0-9_]{1,63}"
                if kind in {"move_actor", "dynamics_modifier"}
                else None
            ),
        },
        "commitment": {
            "required": True,
            "values": ["required", "conditional"],
        },
        "condition": {
            "allowed": kind != "dynamics_modifier",
            "required": False,
            "null_means": "always",
        },
        "attribute_terms": {
            "allowed": kind != "dynamics_modifier",
            "required": False,
            "type": "list",
            "empty_allowed": True,
        },
        "targeting": {
            "allowed": kind != "dynamics_modifier",
            "required": False,
            "default": {"sensing": "none", "evadable": False},
            "sensing_values": ["none", "visual", "mana"],
            "evadable_type": "strict_boolean",
            "evadable_requires": "at_least_one_check_attribute_term",
        },
    }
    if kind in {"process_start", "process_modify"}:
        constraints["process_template_id"] = {
            "required": True,
            "type": "string",
            "nonempty": True,
            "maximum_length": 128,
            "global_profile_ids_enumerated": False,
        }
    if kind == "process_modify":
        constraints["process_rate"] = {
            "required": False,
            "type": "number",
            "finite": True,
            "exclusive_minimum": 0,
            "parser_maximum": None,
            "runtime_profile_bound": "Process template max_rate",
        }
        constraints["process_remaining_ticks"] = {
            "required": False,
            "type": "integer",
            "minimum": 1,
            "parser_maximum": None,
            "runtime_profile_bound": "Process template max_duration_ticks",
        }
    if kind == "drive_source":
        constraints["drive_profile_id"] = {
            "required": True,
            "type": "string",
            "nonempty": True,
            "maximum_length": 128,
            "global_profile_ids_enumerated": False,
        }
        constraints["drive_rate"] = {
            "required": True,
            "type": "number",
            "finite": True,
            "exclusive_minimum": 0,
            "parser_maximum": None,
            "runtime_profile_bound": "Drive profile max_rate",
        }
        constraints["duration"] = {
            "required": True,
            "type": "integer",
            "minimum": 1,
            "parser_maximum": None,
            "runtime_profile_bound": "Drive profile max_duration_ticks",
        }
    if kind == "relation_modifier":
        constraints["relation_profile_id"] = {
            "required": True,
            "type": "string",
            "nonempty": True,
            "maximum_length": 128,
            "global_profile_ids_enumerated": False,
        }
        constraints["relation_enabled"] = {
            "required": True,
            "type": "strict_boolean",
        }
        constraints["duration"] = {
            "required": True,
            "type": "integer",
            "minimum": 1,
            "parser_maximum": None,
            "runtime_profile_bound": "Relation profile max_duration_ticks",
        }
    if kind in {"modify_attractor", "modify_rate", "grant_trait"}:
        constraints["duration"] = {
            "required": True,
            "type": "integer",
            "minimum": 1,
            "parser_maximum": None,
        }
    if kind == "dynamics_modifier":
        constraints.update({
            "field_id": {
                "required": True,
                "type": "string",
                "pattern": "[a-z][a-z0-9_]{1,47}",
            },
            "rate_add": {
                "required": True,
                "type": "number",
                "finite": True,
                "minimum": -1.0,
                "maximum": 1.0,
            },
            "rate_multiplier": {
                "required": True,
                "type": "number",
                "finite": True,
                "minimum": 0.0,
                "maximum": 8.0,
            },
            "curve": {
                "required": True,
                "values": list(CURVES),
            },
            "curve_priority": {
                "required": True,
                "type": "integer",
                "minimum": 0,
                "maximum": 31,
            },
            "duration": {
                "required": True,
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
            },
        })
        for key in ("condition", "attribute_terms", "targeting"):
            constraints.pop(key)
    if kind in {"damage", "heal", "shield"}:
        constraints["amount"] = {
            "required": True,
            "type": "number",
            "finite": True,
            "minimum": 0,
            **_null_scope(
                parser_null=True,
                ir_null=True,
                ir_note=(
                    "Skill IR preserves this null through parse_skill_ir; "
                    "runtime treats a missing value as 0.0 before attribute "
                    "terms. Null is not a way to omit the scalar from an IR "
                    "document."
                ),
            ),
        }
    if kind in {"modify_field", "modify_attractor", "modify_rate"}:
        constraints["field_id"] = {
            "required": True,
            "type": "string",
            "nonempty": True,
            "global_field_ids_enumerated": False,
            **_null_scope(
                parser_null=True,
                ir_null=True,
                ir_note=(
                    "Skill IR preserves this null through type validation, "
                    "but it is not a usable effect: runtime field lookup "
                    "requires a concrete field ID. Prefer a non-null field ID."
                ),
            ),
        }
        constraints["amount"] = {
            "required": True,
            "type": "number",
            "finite": True,
            **_null_scope(
                parser_null=True,
                ir_null=True,
                ir_note=(
                    "Skill IR preserves this null through type validation; "
                    "runtime's effect amount path treats it as 0.0."
                ),
            ),
        }
    if kind == "add_resource":
        constraints["resource"] = {
            "required": True,
            "type": "string",
            "values": ["hp", "mana", "shield"],
            **_null_scope(
                parser_null=True,
                ir_null=True,
                ir_note=(
                    "Skill IR preserves this null through type validation; "
                    "it does not identify a resource and should not be used."
                ),
            ),
        }
        constraints["amount"] = {
            "required": True,
            "type": "number",
            "finite": True,
            **_null_scope(
                parser_null=True,
                ir_null=True,
                ir_note=(
                    "Skill IR preserves this null through type validation; "
                    "runtime's effect amount path treats it as 0.0."
                ),
            ),
        }
    if kind == "apply_status":
        constraints["status_id"] = {
            "required": True,
            "type": "string",
            "known_status_registry_required": True,
            **_null_scope(
                parser_null=True,
                ir_null=True,
                ir_note=(
                    "Skill IR preserves this null through type validation; "
                    "runtime still requires a known non-null status ID."
                ),
            ),
        }
    if kind == "grant_trait":
        constraints["trait_id"] = {
            "required": True,
            "type": "string",
            "nonempty": True,
            **_null_scope(
                parser_null=True,
                ir_null=True,
                ir_note=(
                    "Skill IR preserves this null through type validation; "
                    "runtime still requires a concrete trait ID."
                ),
            ),
        }
    if kind == "move_actor":
        for key in ("condition", "attribute_terms", "targeting"):
            constraints.pop(key)
        constraints["target"] = {
            "required": True,
            "exact": {"kind": "adjacent_area"},
        }
        constraints["commitment"] = {
            "required": True,
            "values": ["required"],
        }
    return constraints


def _null_scope(
    *,
    parser_null: bool,
    ir_null: bool,
    ir_note: str,
) -> dict[str, Any]:
    return {
        "null_scope": {
            "parse_effect_null_allowed": parser_null,
            "skill_ir_ingress_null_allowed": ir_null,
            "ir_ingress_note": ir_note,
            "ir_lowering_does_not_add_null_restriction": True,
            "annotation_is_source_anchored": False,
            "annotation_kind": "static_owner_review_manifest",
        },
    }


def _extract_trigger_schema(tree: ast.Module) -> dict[str, Any]:
    supported_event = _module_literal(
        tree, "SUPPORTED_EVENT", "skill_ir.py"
    )
    reserved_triggers = set(
        _module_literal(tree, "RESERVED_TRIGGERS", "skill_ir.py")
    )
    reserved_events = set(
        _module_literal(tree, "RESERVED_EVENTS", "skill_ir.py")
    )
    if supported_event != SUPPORTED_EVENT or supported_event != "damage_resolved":
        raise CatalogSourceError("unsupported supported-event drift")
    expected_reserved_triggers = {
        "on_tick",
        "on_expire",
        "transition",
        "condition_enter",
        "condition_exit",
    }
    expected_reserved_events = {
        "action_started",
        "attack_applied",
        "status_changed",
        "weather_changed",
        "resource_harvested",
    }
    if reserved_triggers != expected_reserved_triggers:
        raise CatalogSourceError(
            f"unsupported reserved trigger drift: {reserved_triggers}"
        )
    if reserved_events != expected_reserved_events:
        raise CatalogSourceError(
            f"unsupported reserved event drift: {reserved_events}"
        )
    if (
        set(RESERVED_TRIGGERS) != expected_reserved_triggers
        or set(RESERVED_EVENTS) != expected_reserved_events
    ):
        raise CatalogSourceError("imported trigger sets disagree with source")
    return {
        "supported": [
            {
                "kind": "on_use",
                "trigger": {"kind": "on_use"},
                "execution": "active_primary",
                "supported": True,
            },
            {
                "kind": "on_event",
                "event": supported_event,
                "trigger": {
                    "kind": "on_event",
                    "event": supported_event,
                },
                "execution": "bounded_passive_hook",
                "supported": True,
            },
        ],
        "reserved": [
            {
                "kind": kind,
                "supported": False,
                "reason": f"language_gap:{kind}",
            }
            for kind in sorted(reserved_triggers)
        ] + [
            {
                "kind": "on_event",
                "event": event,
                "supported": False,
                "reason": f"language_gap:on_event:{event}",
            }
            for event in sorted(reserved_events)
        ],
        "accepted_event": supported_event,
    }


def _extract_condition_schema(
    condition_tree: ast.Module,
    contracts_tree: ast.Module,
) -> dict[str, Any]:
    function = _function(condition_tree, "_parse_condition")
    string_sets = {
        frozenset(_string_set_values(node))
        for node in ast.walk(function)
        if isinstance(node, ast.Set)
        and _string_set_values(node) is not None
    }
    expected_sets = {
        frozenset({"self", "target_actor", "current_area"}),
        frozenset({"hp", "mana", "shield"}),
        frozenset({"eq", "neq", "gt", "gte", "lt", "lte"}),
        frozenset({"self", "target_actor"}),
        frozenset({"attribute", "resource", "field"}),
        frozenset({"has_trait", "has_status"}),
        frozenset({"subject", "key", "comparator", "value"}),
        frozenset({"subject", "id"}),
    }
    for expected in expected_sets:
        if expected not in string_sets:
            raise CatalogSourceError(
                f"condition source literal drift; missing {sorted(expected)}"
            )
    limits_class = _class(condition_tree, "ConditionLimits")
    defaults = {}
    maximums = {}
    for node in limits_class.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(
            node.target, ast.Name
        ):
            continue
        if node.target.id not in {"max_depth", "max_nodes", "max_children"}:
            continue
        defaults[node.target.id] = _literal_value(
            node.value, {}, f"ConditionLimits.{node.target.id}"
        )
    for node in ast.walk(limits_class):
        if not isinstance(node, ast.Tuple) or len(node.elts) != 3:
            continue
        try:
            name = _literal_value(node.elts[0], {}, "ConditionLimits")
            maximum = _literal_value(node.elts[2], {}, "ConditionLimits")
        except CatalogSourceError:
            continue
        if name in {"max_depth", "max_nodes", "max_children"}:
            maximums[name] = maximum
    if defaults != {"max_depth": 16, "max_nodes": 64, "max_children": 16}:
        raise CatalogSourceError(f"ConditionLimits defaults drifted: {defaults}")
    if maximums != {"max_depth": 64, "max_nodes": 4096, "max_children": 256}:
        raise CatalogSourceError(
            f"ConditionLimits maximums drifted: {maximums}"
        )
    default_limits = ConditionLimits()
    if (
        default_limits.max_depth != defaults["max_depth"]
        or default_limits.max_nodes != defaults["max_nodes"]
        or default_limits.max_children != defaults["max_children"]
    ):
        raise CatalogSourceError("imported ConditionLimits disagree with source")
    attributes = tuple(
        _module_literal(contracts_tree, "ATTRIBUTES", "contracts.py")
    )
    if attributes != tuple(ATTRIBUTES) or attributes != (
        "power",
        "control",
        "resilience",
        "agility",
    ):
        raise CatalogSourceError("attribute enum drift")
    comparator_values = ["eq", "neq", "gt", "gte", "lt", "lte"]
    types = [
        {
            "kind": "all",
            "value_shape": "nonempty_list_of_condition_nodes",
            "minimum_children": 1,
            "maximum_children": 16,
        },
        {
            "kind": "any",
            "value_shape": "nonempty_list_of_condition_nodes",
            "minimum_children": 1,
            "maximum_children": 16,
        },
        {
            "kind": "not",
            "value_shape": "one_condition_node",
        },
        {
            "kind": "attribute",
            "required_keys": ["subject", "key", "comparator", "value"],
            "subjects": ["self", "target_actor", "current_area"],
            "keys": list(attributes),
            "comparators": comparator_values,
            "value": "finite_number",
        },
        {
            "kind": "resource",
            "required_keys": ["subject", "key", "comparator", "value"],
            "subjects": ["self", "target_actor", "current_area"],
            "keys": ["hp", "mana", "shield"],
            "comparators": comparator_values,
            "value": "finite_number",
        },
        {
            "kind": "field",
            "required_keys": ["subject", "key", "comparator", "value"],
            "subjects": ["self", "target_actor", "current_area"],
            "keys": "nonempty_runtime_field_id",
            "global_field_ids_enumerated": False,
            "comparators": comparator_values,
            "value": "finite_number",
        },
        {
            "kind": "has_trait",
            "required_keys": ["subject", "id"],
            "subjects": ["self", "target_actor"],
            "id": "nonempty_trait_id",
        },
        {
            "kind": "has_status",
            "required_keys": ["subject", "id"],
            "subjects": ["self", "target_actor"],
            "id": "nonempty_status_id",
        },
        {
            "kind": "derived",
            "required_keys": ["subject", "key", "comparator", "value"],
            "subjects": ["current_area"],
            "subject_exact": "current_area",
            "keys": "nonempty_runtime_derived_id",
            "global_derived_ids_enumerated": False,
            "comparators": comparator_values,
            "value": "finite_number",
            "read_only": True,
        },
    ]
    return {
        "kinds": [item["kind"] for item in types],
        "types": types,
        "null_condition": "always",
        "document_budget_shared": True,
        "defaults": defaults,
        "trusted_tighten_only": True,
        "maximum_accepted_limits": maximums,
        "semantics": {
            "pure": True,
            "read_only": True,
            "derived_is_input_only": True,
            "arbitrary_expression": False,
        },
    }


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    matches = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    ]
    if len(matches) != 1:
        raise CatalogSourceError(f"expected one class {name}")
    return matches[0]


def _string_set_values(node: ast.Set) -> frozenset[str] | None:
    if all(isinstance(item, ast.Constant) and isinstance(item.value, str)
           for item in node.elts):
        return frozenset(item.value for item in node.elts)
    return None


def _selector_document(selector_kinds: tuple[str, ...]) -> dict[str, Any]:
    rows = []
    for kind in selector_kinds:
        row = {
            "kind": kind,
            "supported": True,
            "allowed_keys": ["kind", "relation_type"]
            if kind == "linked_object"
            else ["kind"],
            "required_relation_type": kind == "linked_object",
            "resolution": (
                "one_resolved_current_area"
                if kind == "current_area"
                else "one_or_more_adjacent_areas"
                if kind == "adjacent_area"
                else "one_or_more_linked_endpoints"
                if kind == "linked_object"
                else "one_resolved_entity"
            ),
            "effect_target_restriction": "exactly_one_resolved_target",
        }
        rows.append(row)
    return {
        "kinds": list(selector_kinds),
        "entries": rows,
        "linked_object_relation_type": {
            "field": "relation_type",
            "required": True,
            "type": "nonempty_string",
            "must_be_in_targeting_relation_types": True,
            "must_be_authorized_by_material_trait": True,
            "global_relation_ids_enumerated": False,
        },
        "single_target_restriction": {
            "rule": "exactly_one_resolved_target",
            "source_rule": "actions.py:Gate 2 effects require exactly one target",
            "exception": "move_actor uses exactly one requested adjacent target_area",
            "multi_endpoint_selection_policy": False,
        },
    }


def _extract_material_enums(tree: ast.Module) -> dict[str, Any]:
    tiers = tuple(_module_literal(tree, "MATERIAL_TIERS", "materials.py"))
    rarities = tuple(
        _module_literal(tree, "REGION_RARITIES", "materials.py")
    )
    if tiers != tuple(MATERIAL_TIERS) or tiers != (
        "common",
        "fine",
        "rare",
        "epic",
        "legendary",
    ):
        raise CatalogSourceError(f"material tier drift: {tiers!r}")
    if rarities != tuple(REGION_RARITIES) or rarities != (
        "abundant",
        "uncommon",
        "scarce",
        "unique",
    ):
        raise CatalogSourceError(f"region rarity drift: {rarities!r}")
    return {
        "tiers": list(tiers),
        "region_rarities": list(rarities),
        "trait_required_keys": [
            "id",
            "effect_kinds",
            "selectors",
            "budget_points",
        ],
        "trait_budget": {
            "type": "number",
            "finite": True,
            "exclusive_minimum": 0,
        },
        "authority": "derived_only_from_validated_material_traits",
    }


def _extract_profiles(tree: ast.Module) -> dict[str, Any]:
    profiles = tuple(
        _module_literal(
            tree, "PROFILES", "reference_skills/fixtures.py"
        )
    )
    expected = (
        "field",
        "stock",
        "process",
        "relation",
        "combat",
        "travel",
        "derived",
    )
    if profiles != expected:
        raise CatalogSourceError(
            f"unsupported reference profile drift: {profiles!r}"
        )
    return {
        "closed_profiles": list(profiles),
        "profile_specific_ids": {
            "enumerated": False,
            "kinds": [
                "field_id",
                "process_template_id",
                "drive_profile_id",
                "relation_profile_id",
            ],
            "reason": (
                "profile fixtures expose local trusted IDs only at runtime; "
                "the public catalog must not infer a global union"
            ),
        },
    }


def _extract_limits(
    skill_tree: ast.Module,
    hook_tree: ast.Module,
    process_tree: ast.Module,
    drive_tree: ast.Module,
    relation_tree: ast.Module,
) -> dict[str, Any]:
    constant_names = [
        "MAX_ENTRIES",
        "MAX_TAGS",
        "MAX_SUMMARY_LENGTH",
        "MAX_NAME_LENGTH",
        "MAX_DESCRIPTION_LENGTH",
        "MAX_MODEL_LENGTH",
        "MAX_JSON_DEPTH",
        "MAX_JSON_VALUES",
        "MAX_JSON_STRING",
        "MAX_JSON_SAFE_INT",
    ]
    values = {
        name: _module_literal(skill_tree, name, "skill_ir.py")
        for name in constant_names
    }
    expected = {
        "MAX_ENTRIES": 4,
        "MAX_TAGS": 8,
        "MAX_SUMMARY_LENGTH": 240,
        "MAX_NAME_LENGTH": 80,
        "MAX_DESCRIPTION_LENGTH": 600,
        "MAX_MODEL_LENGTH": 128,
        "MAX_JSON_DEPTH": 128,
        "MAX_JSON_VALUES": 65536,
        "MAX_JSON_STRING": 4096,
        "MAX_JSON_SAFE_INT": 2**53,
    }
    if values != expected:
        raise CatalogSourceError(f"Skill IR limits drifted: {values!r}")
    imported_expected = {
        "MAX_ENTRIES": MAX_ENTRIES,
        "MAX_TAGS": MAX_TAGS,
        "MAX_SUMMARY_LENGTH": MAX_SUMMARY_LENGTH,
        "MAX_NAME_LENGTH": MAX_NAME_LENGTH,
        "MAX_DESCRIPTION_LENGTH": MAX_DESCRIPTION_LENGTH,
        "MAX_MODEL_LENGTH": MAX_MODEL_LENGTH,
        "MAX_JSON_DEPTH": MAX_JSON_DEPTH,
        "MAX_JSON_VALUES": MAX_JSON_VALUES,
        "MAX_JSON_STRING": MAX_JSON_STRING,
        "MAX_JSON_SAFE_INT": MAX_JSON_SAFE_INT,
    }
    if imported_expected != expected:
        raise CatalogSourceError("imported Skill IR limits disagree with source")
    hook_defaults = _dataclass_defaults(hook_tree, "HookDispatchLimits")
    hook_limits = _dataclass_maximums(hook_tree, "HookDispatchLimits")
    if hook_defaults != {
        "max_depth": 16,
        "max_firings": 32,
        "max_notifications": 64,
    }:
        raise CatalogSourceError(f"HookDispatchLimits drifted: {hook_defaults}")
    if hook_limits != {
        "max_depth": 16,
        "max_firings": 32,
        "max_notifications": 64,
    }:
        raise CatalogSourceError(
            f"HookDispatchLimits maximums drifted: {hook_limits}"
        )
    controller_data = {
        "process": _controller_limits(process_tree),
        "drive": _controller_limits(drive_tree),
        "relation": _controller_limits(relation_tree),
    }
    if any(
        row["defaults"] != {"max_instances": 16, "max_active": 8}
        or row["maximum_instances"] != 1024
        for row in controller_data.values()
    ):
        raise CatalogSourceError("controller runtime caps drifted")
    return {
        "skill_ir": values,
        "entries": {
            "minimum": 1,
            "maximum": MAX_ENTRIES,
            "maximum_on_use_entries": 1,
            "max_firings_per_root": {"minimum": 1, "maximum": 8},
        },
        "json_ingress": {
            "maximum_depth": MAX_JSON_DEPTH,
            "maximum_values": MAX_JSON_VALUES,
            "maximum_string_or_key_length": MAX_JSON_STRING,
            "maximum_safe_integer_magnitude": MAX_JSON_SAFE_INT,
            "nonfinite_numbers": "reject",
        },
        "conditions": {
            "default": {
                "max_depth": 16,
                "max_nodes": 64,
                "max_children": 16,
            },
            "trusted_configuration_maximum": {
                "max_depth": 64,
                "max_nodes": 4096,
                "max_children": 256,
            },
            "ir_can_only_tighten_default": True,
        },
        "hooks": {
            "defaults": hook_defaults,
            "trusted_maximums": hook_limits,
            "enforcement": "HookDispatchLimits",
        },
        "controllers": controller_data,
        "explicit_effect_count_limit": None,
        "effect_count_bound": "shared budget plus composition rules",
    }


def _dataclass_defaults(tree: ast.Module, name: str) -> dict[str, Any]:
    cls = _class(tree, name)
    result = {}
    for node in cls.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            result[node.target.id] = _literal_value(
                node.value, {}, f"{name}.{node.target.id}"
            )
    return result


def _dataclass_maximums(tree: ast.Module, name: str) -> dict[str, Any]:
    cls = _class(tree, name)
    result = {}
    for node in ast.walk(cls):
        if not isinstance(node, ast.Tuple) or len(node.elts) != 3:
            continue
        try:
            key = _literal_value(node.elts[0], {}, name)
            maximum = _literal_value(node.elts[2], {}, name)
        except CatalogSourceError:
            continue
        if isinstance(key, str):
            result[key] = maximum
    return result


def _controller_limits(tree: ast.Module) -> dict[str, Any]:
    class_matches = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name.endswith("Limits")
        and node.name not in {"FieldDefinition"}
    ]
    preferred = [
        node for node in class_matches
        if node.name in {"ProcessLimits", "DriveLimits", "RelationLimits"}
    ]
    if len(preferred) != 1:
        raise CatalogSourceError("cannot identify controller Limits class")
    cls = preferred[0]
    defaults = {
        node.target.id: _literal_value(
            node.value, {}, f"{cls.name}.{node.target.id}"
        )
        for node in cls.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.value is not None
    }
    maximum = None
    for node in tree.body:
        if (
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and _assigned_name(node) == "MAX_INSTANCES"
        ):
            maximum = _literal_value(
                node.value, {}, "MAX_INSTANCES"
            )
    if maximum is None:
        raise CatalogSourceError("controller MAX_INSTANCES missing")
    return {
        "defaults": defaults,
        "maximum_instances": maximum,
        "enforcement": cls.name,
    }


def _extract_budget(tree: ast.Module) -> dict[str, Any]:
    costs = _module_literal(tree, "_EFFECT_COST", "skills.py")
    expected = {
        "damage": 2.0,
        "heal": 2.0,
        "shield": 2.0,
        "add_resource": 2.0,
        "apply_status": 3.0,
        "modify_field": 2.0,
        "modify_attractor": 3.0,
        "modify_rate": 3.0,
        "grant_trait": 3.0,
        "process_start": 5.0,
        "process_modify": 5.0,
        "drive_source": 5.0,
        "relation_modifier": 5.0,
        "dynamics_modifier": 3.0,
        "move_actor": 2.0,
    }
    if costs != expected:
        raise CatalogSourceError(f"effect budget costs drifted: {costs!r}")
    return {
        "effect_costs": costs,
        "attribute_term_cost": 0.25,
        "duration_cost": {
            "per_tick": 0.1,
            "charged_ticks_cap": 20,
        },
        "sensing_or_evadable_surcharge": 0.25,
        "passive_overhead": 0.5,
        "limit": "positive <= trusted MaterialAuthority.budget_points",
        "compound_limit": "sum of entry budget_used <= document budget",
    }


def _extract_attribute_terms(tree: ast.Module) -> dict[str, Any]:
    function = _function(tree, "parse_attribute_term")
    string_sets = {
        frozenset(_string_set_values(node))
        for node in ast.walk(function)
        if isinstance(node, ast.Set)
        and _string_set_values(node) is not None
    }
    required_sets = {
        frozenset({"scaling", "threshold", "check", "modifier"}),
        frozenset({"eq", "neq", "gt", "gte", "lt", "lte"}),
        frozenset({"add", "multiply"}),
    }
    for expected in required_sets:
        if expected not in string_sets:
            raise CatalogSourceError(
                f"attribute term source literal drift: {sorted(expected)}"
            )
    return {
        "kind_values": ["scaling", "threshold", "check", "modifier"],
        "attributes": list(ATTRIBUTES),
        "forms": {
            "scaling": {
                "required_keys": ["kind", "attribute", "coefficient"],
                "optional_keys": ["maximum"],
                "coefficient": "finite_number",
                "maximum": "nonnegative_finite_number",
            },
            "threshold": {
                "required_keys": [
                    "kind", "attribute", "comparator", "threshold"
                ],
                "comparators": ["eq", "neq", "gt", "gte", "lt", "lte"],
                "threshold": "finite_number",
            },
            "check": {
                "required_keys": [
                    "kind", "attribute", "comparator", "threshold"
                ],
                "comparators": ["eq", "neq", "gt", "gte", "lt", "lte"],
                "threshold": "finite_number",
            },
            "modifier": {
                "required_keys": ["kind", "attribute", "operation", "value"],
                "operations": ["add", "multiply"],
                "value": "finite_number",
            },
        },
    }


def _lifecycle_document(tree: ast.Module, source_text: str) -> dict[str, Any]:
    function = _function(tree, "_status_duration")
    source = ast.get_source_segment(
        source_text, function
    )
    if not source or "language_gap:lifecycle.status_duration" not in source:
        raise CatalogSourceError(
            "unsupported lifecycle.status_duration implementation drift"
        )
    return {
        "status_duration": {
            "supported": False,
            "supported_value": None,
            "non_null": {
                "supported": False,
                "reason": "language_gap:lifecycle.status_duration",
            },
            "replacement": "per_effect_duration",
        },
        "per_effect_duration": {
            "supported": True,
            "note": "Effect parser duration rules in effects/kinds",
        },
        "registry_status_definitions": {
            "supported": True,
            "note": "trusted status registry definitions, not IR lifecycle",
        },
}


def _composition_rules(
    skills_tree: ast.Module,
    skill_tree: ast.Module,
) -> dict[str, Any]:
    function = _function(skills_tree, "parse_skill_blueprint")
    constants = [
        _literal_value(node, {}, "parse_skill_blueprint")
        for node in ast.walk(function)
        if isinstance(node, ast.Set)
        and _string_set_values(node) is not None
    ]
    constants.extend([
        frozenset({"process_start", "process_modify"}),
        frozenset({
            "action_started",
            "attack_applied",
            "damage_resolved",
            "status_changed",
            "weather_changed",
            "resource_harvested",
        }),
        frozenset({
            "damage",
            "process_start",
            "process_modify",
            "drive_source",
            "relation_modifier",
        }),
    ])
    required = {
        frozenset({
            "process_start",
            "process_modify",
            "drive_source",
            "relation_modifier",
        }),
        frozenset({
            "move_actor",
            "heal",
            "shield",
            "add_resource",
            "apply_status",
            "grant_trait",
            "modify_field",
            "modify_attractor",
            "modify_rate",
            "dynamics_modifier",
        }),
        frozenset({
            "damage",
            "process_start",
            "process_modify",
            "drive_source",
            "relation_modifier",
        }),
    }
    for item in required:
        if not any(set(item) == value for value in constants):
            raise CatalogSourceError(
                f"composition source literal drift: {sorted(item)}"
            )
    _function(skill_tree, "_trigger")
    return {
        "per_entry_effects": "nonempty_list",
        "effect_ids_unique": True,
        "one_process_control_operation_per_entry": True,
        "one_process_drive_relation_control_operation_per_entry": True,
        "one_move_actor_per_entry": True,
        "move_actor_incompatible_with": [
            "damage",
            "process_start",
            "process_modify",
            "drive_source",
            "relation_modifier",
        ],
        "passive_entry_forbids": [
            "process_start",
            "process_modify",
            "drive_source",
            "relation_modifier",
            "dynamics_modifier",
            "move_actor",
        ],
        "conflicting_write_footprints": "reject",
        "at_most_one_on_use_entry_per_document": True,
        "effect_order": "preserved",
    }


def _source_anchors(sources: Mapping[str, str]) -> list[dict[str, str]]:
    anchors = []
    for name in sorted(sources):
        text = sources[name]
        anchors.append({
            "path": (
                "experiments/generative_mechanics/next_tracks_v06/"
                f"gameplay_v04/{name}"
            ),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "role": _SOURCE_ROLES[name],
        })
    return anchors
