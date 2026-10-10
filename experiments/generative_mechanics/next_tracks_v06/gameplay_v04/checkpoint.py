"""Canonical gameplay checkpoint envelope for the runtime mechanism registry."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from pmw import Entity, Event, Relation, WorldState
from pmw.validation import validate_world

from .contracts import GameplayContractError
from .materials import MaterialAuthority
from .registry import (MechanismRegistryRuntime, registry_configuration,
                       static_law_hash)
from .runtime import build_runtime, discover_profiles
from .skills import parse_skill_blueprint


CHECKPOINT_SCHEMA = "pmw-gameplay-checkpoint-v0.4"


def save_registry_checkpoint(path: str | Path, runtime: MechanismRegistryRuntime) -> str:
    """Atomically write a self-verifying envelope and return its payload digest."""
    documents = []
    for key, blueprint in sorted(runtime.blueprints.items()):
        if key != (blueprint.id, blueprint.version):
            raise GameplayContractError("registry blueprint key is inconsistent")
        if sha256(blueprint.canonical_document_json.encode()).hexdigest() != blueprint.canonical_hash:
            raise GameplayContractError("cannot checkpoint a blueprint with an invalid canonical hash")
        authority = blueprint.material_authority
        documents.append({
            "id": blueprint.id, "version": blueprint.version,
            "canonical_hash": blueprint.canonical_hash,
            "document": json.loads(blueprint.canonical_document_json),
            "material_authority": {
                "material_ids": sorted(authority.material_ids),
                "effect_kinds": sorted(authority.effect_kinds),
                "selectors": sorted(authority.selectors),
                "budget_points": authority.budget_points,
            },
        })
    payload = {
        "schema": CHECKPOINT_SCHEMA,
        "world": runtime.session.state.to_dict(),
        "blueprints": documents,
        "runtime_config": {
            "status_slots": runtime.status_slots,
            "dynamics_slots": runtime.dynamics_slots,
            "base_registry_hash": _base_registry_hash(runtime.base_registry),
            "static_laws": list(runtime.static_laws),
            "static_laws_hash": static_law_hash(runtime.static_laws),
        },
    }
    digest = _digest(payload)
    envelope = {**payload, "payload_sha256": digest}
    destination = Path(path)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False) + "\n",
                         encoding="utf-8")
    temporary.replace(destination)
    return digest


def load_registry_checkpoint(path: str | Path, compiled: Any) -> MechanismRegistryRuntime:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
            "schema", "world", "blueprints", "runtime_config", "payload_sha256"}:
        raise GameplayContractError("checkpoint envelope shape is invalid")
    digest = raw.pop("payload_sha256")
    if not isinstance(digest, str) or digest != _digest(raw):
        raise GameplayContractError("checkpoint payload hash mismatch")
    if raw["schema"] != CHECKPOINT_SCHEMA:
        raise GameplayContractError("unsupported gameplay checkpoint schema")
    config = raw["runtime_config"]
    if not isinstance(config, dict) or set(config) != {
            "status_slots", "dynamics_slots", "base_registry_hash", "static_laws", "static_laws_hash"}:
        raise GameplayContractError("checkpoint runtime configuration is invalid")
    status_slots = _bounded_integer(config["status_slots"], "status_slots")
    dynamics_slots = _bounded_integer(config["dynamics_slots"], "dynamics_slots")
    base, trusted_static = registry_configuration(compiled)
    if config["base_registry_hash"] != _base_registry_hash(base):
        raise GameplayContractError("checkpoint base registry does not match trusted content")
    if (config["static_laws_hash"] != static_law_hash(config["static_laws"]) or
            config["static_laws_hash"] != static_law_hash(trusted_static) or
            config["static_laws"] != list(trusted_static)):
        raise GameplayContractError("checkpoint static Law configuration does not match trusted content")
    world = _world_from_document(raw["world"])
    documents = raw["blueprints"]
    if not isinstance(documents, list):
        raise GameplayContractError("checkpoint blueprints must be a list")
    blueprints = {}
    for index, row in enumerate(documents):
        if not isinstance(row, dict) or set(row) != {
                "id", "version", "canonical_hash", "document", "material_authority"}:
            raise GameplayContractError(f"checkpoint blueprint {index} is invalid")
        authority = _authority(row["material_authority"])
        blueprint = parse_skill_blueprint(row["document"], base.statuses, authority,
                                          f"$.blueprints[{index}].document")
        if ((blueprint.id, blueprint.version, blueprint.canonical_hash) !=
                (row["id"], row["version"], row["canonical_hash"])):
            raise GameplayContractError("checkpoint blueprint identity/hash mismatch")
        key = (blueprint.id, blueprint.version)
        if key in blueprints:
            raise GameplayContractError("checkpoint contains duplicate blueprint versions")
        blueprints[key] = blueprint
    placeholder = build_runtime(world, discover_profiles(world), trusted_static)
    restored = MechanismRegistryRuntime(placeholder, base, trusted_static, blueprints,
                                        status_slots, dynamics_slots)
    restored._validate_formal_state()
    restored._rebuild()
    return restored


def _authority(raw: Any) -> MaterialAuthority:
    if not isinstance(raw, dict) or set(raw) != {
            "material_ids", "effect_kinds", "selectors", "budget_points"}:
        raise GameplayContractError("checkpoint material authority is invalid")
    for key in ("material_ids", "effect_kinds", "selectors"):
        values = raw[key]
        if (not isinstance(values, list) or not values or
                any(not isinstance(item, str) or not item for item in values) or
                values != sorted(values) or len(values) != len(set(values))):
            raise GameplayContractError(f"checkpoint material authority {key} is invalid")
    budget = raw["budget_points"]
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or budget <= 0:
        raise GameplayContractError("checkpoint material authority budget is invalid")
    return MaterialAuthority(tuple(raw["material_ids"]), tuple(raw["effect_kinds"]),
                             tuple(raw["selectors"]), float(budget))


def _world_from_document(raw: Any) -> WorldState:
    validate_world(raw, "gameplay checkpoint")
    time = raw["time"]
    return WorldState(
        world_id=raw["world_id"], tick=time["tick"], sim_time=time["sim_time"],
        rng_state=deepcopy(raw["rng"]),
        entities={item["id"]: Entity(item["id"], item.get("archetype", ""), item.get("name"),
                                      set(item.get("tags", [])), deepcopy(item.get("components", {})))
                  for item in raw["entities"]},
        relations={item["id"]: Relation(item["id"], item["type"], item["source"], item["target"],
                                         set(item.get("tags", [])), deepcopy(item.get("components", {})))
                   for item in raw["relations"]},
        scheduled_events=[Event(item["id"], item["type"], item["time"], item.get("source"),
                                item.get("target"), deepcopy(item.get("payload", {})),
                                deepcopy(item.get("provenance", {"kind": "scheduled", "parent_event": None})))
                          for item in raw["scheduled_events"]],
    )


def _base_registry_hash(registry: Any) -> str:
    document = {
        "actions": [(item.id, item.version, item.canonical_hash)
                    for item in sorted(registry.actions.values(), key=lambda row: row.id)],
        "statuses": [(item.id, item.canonical_hash)
                     for item in sorted(registry.statuses.values(), key=lambda row: row.id)],
        "hooks": [(item.id, item.trigger, item.action_id, list(item.effect_ids))
                  for item in sorted(registry.hooks.values(), key=lambda row: row.id)],
    }
    return _digest(document)


def _bounded_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 32:
        raise GameplayContractError(f"checkpoint {name} must be in [1, 32]")
    return value


def _digest(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode()).hexdigest()
