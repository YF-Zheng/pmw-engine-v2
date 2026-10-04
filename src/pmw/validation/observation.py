from __future__ import annotations

import re
from typing import Any

from .errors import PMWValidationError
from .law import validate_laws


class ObservationValidationError(PMWValidationError):
    pass


def validate_observation_rules(raw: Any, document: str) -> None:
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "observation_rules"} or raw.get("schema_version") != "2.0" or not isinstance(raw.get("observation_rules"), list):
        raise ObservationValidationError(f"document={document} expected v2 observation rule document")
    ids: set[str] = set()
    for index, rule in enumerate(raw["observation_rules"]):
        path = f"observation_rules[{index}]"
        if not isinstance(rule, dict) or set(rule) - {"id", "bindings", "when", "subject", "reveal"}:
            raise ObservationValidationError(f"document={document} path={path} invalid rule object or unknown field")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            raise ObservationValidationError(f"document={document} path={path}.id must be non-empty string")
        if rule_id in ids:
            raise ObservationValidationError(f"document={document} path={path}.id duplicate rule id '{rule_id}'")
        ids.add(rule_id)
        _validate_rule(rule, document, path)


def _validate_rule(rule: dict[str, Any], document: str, path: str) -> None:
    bindings = rule.get("bindings", {})
    if not isinstance(bindings, dict) or "observer" in bindings:
        raise ObservationValidationError(f"document={document} path={path}.bindings observer is reserved")
    internal_bindings = {"observer": {"kind": "entity"}, **bindings}
    synthetic = {
        "schema_version": "2.0",
        "laws": [{
            "id": rule["id"],
            "mode": "state",
            "bindings": internal_bindings,
            "when": rule.get("when") or {"all": []},
            "effects": [],
        }],
    }
    try:
        validate_laws(synthetic, document)
    except Exception as exc:
        raise ObservationValidationError(f"document={document} path={path} invalid binding/condition: {exc}") from exc

    subject = rule.get("subject")
    if not isinstance(subject, str) or not re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", subject):
        raise ObservationValidationError(f"document={document} path={path}.subject must be a root binding reference")
    subject_name = subject[1:]
    if subject_name == "event" or subject_name not in internal_bindings:
        raise ObservationValidationError(f"document={document} path={path}.subject invalid binding")

    reveal = rule.get("reveal")
    if not isinstance(reveal, dict) or set(reveal) - {"core", "tags", "components"}:
        raise ObservationValidationError(f"document={document} path={path}.reveal invalid or unknown field")
    for key in ("core", "tags", "components"):
        values = reveal.get(key, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values) or len(values) != len(set(values)):
            raise ObservationValidationError(f"document={document} path={path}.reveal.{key} must be unique non-empty strings")

    kind = internal_bindings[subject_name].get("kind", "entity")
    allowed_core = {"type", "source", "target"} if kind == "relation" else {"archetype", "name"}
    if set(reveal.get("core", [])) - allowed_core:
        raise ObservationValidationError(f"document={document} path={path}.reveal.core invalid for {kind}")
    for component_path in reveal.get("components", []):
        segments = component_path.split(".")
        if "*" in component_path or any(not segment for segment in segments):
            raise ObservationValidationError(f"document={document} path={path}.reveal.components invalid path '{component_path}'")
