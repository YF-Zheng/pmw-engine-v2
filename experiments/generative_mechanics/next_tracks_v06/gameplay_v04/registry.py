"""Tick-boundary mechanism registry and safe gameplay-session rebuilds."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping

from pmw import Event, parse_law

from .action_compiler import build_action_laws
from .actions import ActionRegistry
from .contracts import GameplayContractError
from .runtime import GameplaySession, build_runtime, discover_profiles
from .skills import (MechanismRegistryManifest, RegistryEntry, SkillBlueprint,
                     parse_skill_blueprint, passive_hook)


REGISTRY_COMPONENT = "pmw_gameplay_mechanism_registry"
REGISTRY_EVENT = "pmw.v04.registry.change"


def registry_component(manifest: MechanismRegistryManifest, *, last_boundary_step: int = -1) -> dict[str, Any]:
    return {
        "epoch": manifest.epoch,
        "last_boundary_step": last_boundary_step,
        "entries": [entry_to_dict(item) for item in manifest.entries],
    }


def entry_to_dict(entry: RegistryEntry) -> dict[str, Any]:
    return {"skill_id": entry.skill_id, "version": entry.version,
            "canonical_hash": entry.canonical_hash, "kind": entry.kind,
            "enabled": entry.enabled}


def manifest_from_component(raw: Any) -> MechanismRegistryManifest:
    if not isinstance(raw, dict) or set(raw) != {"epoch", "last_boundary_step", "entries"}:
        raise GameplayContractError("registry component shape is invalid")
    epoch, boundary, rows = raw["epoch"], raw["last_boundary_step"], raw["entries"]
    if (isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0 or
            isinstance(boundary, bool) or not isinstance(boundary, int) or boundary < -1 or
            not isinstance(rows, list)):
        raise GameplayContractError("registry component counters are invalid")
    entries = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"skill_id", "version", "canonical_hash", "kind", "enabled"}:
            raise GameplayContractError(f"registry entry {index} is invalid")
        if (not isinstance(row["skill_id"], str) or not row["skill_id"] or
                isinstance(row["version"], bool) or not isinstance(row["version"], int) or row["version"] < 1 or
                not isinstance(row["canonical_hash"], str) or len(row["canonical_hash"]) != 64 or
                row["kind"] not in {"skill_blueprint", "passive_blueprint"} or
                not isinstance(row["enabled"], bool)):
            raise GameplayContractError(f"registry entry {index} values are invalid")
        entries.append(RegistryEntry(row["skill_id"], row["version"], row["canonical_hash"],
                                     row["kind"], row["enabled"]))
    keys = [(item.skill_id, item.version) for item in entries]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise GameplayContractError("registry entries must be unique and canonically ordered")
    enabled_ids = [item.skill_id for item in entries if item.enabled]
    if len(enabled_ids) != len(set(enabled_ids)):
        raise GameplayContractError("registry may enable only one version of each skill")
    return MechanismRegistryManifest(epoch, tuple(entries))


def build_registry_laws() -> tuple[dict, ...]:
    law = {
        "id": "pmw.v04.registry.change", "mode": "event", "priority": 100,
        "bindings": {"registry": {"kind": "entity", "requires": [REGISTRY_COMPONENT, "pmw_gameplay_clock"]}},
        "when": {"all": [
            {"event.type": {"eq": REGISTRY_EVENT}},
            {"ref": "$registry.id", "eq": "$event.source"},
            {"ref": f"$registry.{REGISTRY_COMPONENT}", "eq": "$event.payload.before"},
            {"ref": "$registry.pmw_gameplay_clock.last_completed_step", "eq": "$event.payload.boundary_step"},
        ]},
        "effects": [{"op": "set", "target": f"$registry.{REGISTRY_COMPONENT}",
                     "value": "$event.payload.after"}],
    }
    parse_law(law)
    return (law,)


def registry_configuration(compiled: Any) -> tuple[ActionRegistry, tuple[dict, ...]]:
    skill_ids = {item.id for item in compiled.content.skills}
    passive_hook_ids = {passive_hook(item).id for item in compiled.content.skills
                        if item.kind == "passive_blueprint"}
    registry = compiled.content.action_registry
    base = ActionRegistry(
        (item for item in registry.actions.values() if item.id not in skill_ids),
        registry.statuses.values(),
        (item for item in registry.hooks.values() if item.id not in passive_hook_ids),
    )
    static = tuple(dict(law) for law in compiled.laws if not _dynamic_action_law(law["id"]))
    if not any(law["id"] == "pmw.v04.registry.change" for law in static):
        static = (*static, *build_registry_laws())
    return base, tuple(sorted(static, key=lambda row: row["id"]))


@dataclass(frozen=True, slots=True)
class RegistryChangeResult:
    operation: str
    before: MechanismRegistryManifest
    after: MechanismRegistryManifest
    event_result: Any


@dataclass(slots=True)
class MechanismRegistryRuntime:
    """Owns immutable content definitions while replacing only the attached Engine."""

    session: GameplaySession
    base_registry: ActionRegistry
    static_laws: tuple[dict, ...]
    blueprints: dict[tuple[str, int], SkillBlueprint]
    status_slots: int = 8
    dynamics_slots: int = 4

    @classmethod
    def from_compiled_content(cls, session: GameplaySession, compiled: Any) -> "MechanismRegistryRuntime":
        base, static = registry_configuration(compiled)
        profiles = discover_profiles(session.state)
        dynamics_slots = max((profile.field.max_temporary_modifiers for profile in profiles), default=1)
        result = cls(session, base, static,
                     {(item.id, item.version): item for item in compiled.content.skills},
                     8, dynamics_slots)
        result._validate_formal_state()
        result._rebuild()
        return result
    @property
    def manifest(self) -> MechanismRegistryManifest:
        _, component = self._registry_entity()
        return manifest_from_component(component)

    @property
    def action_registry(self) -> ActionRegistry:
        return self._active_registry()

    def install(self, raw: Mapping[str, Any], authority: Any) -> RegistryChangeResult:
        blueprint = parse_skill_blueprint(raw, self.base_registry.statuses, authority)
        return self.install_blueprint(blueprint)

    def install_blueprint(self, blueprint: SkillBlueprint) -> RegistryChangeResult:
        before = self.manifest
        existing = [item for item in before.entries if item.skill_id == blueprint.id]
        expected = max((item.version for item in existing), default=0) + 1
        if blueprint.version != expected:
            raise GameplayContractError(f"skill version must be the next monotonic version ({expected})")
        if (blueprint.id, blueprint.version) in self.blueprints:
            raise GameplayContractError("skill version is already installed")
        if sha256(blueprint.canonical_document_json.encode()).hexdigest() != blueprint.canonical_hash:
            raise GameplayContractError("SkillBlueprint canonical hash does not match its document")
        self._assert_no_loadout_refs(blueprint.id)
        entries = [RegistryEntry(item.skill_id, item.version, item.canonical_hash, item.kind,
                                 False if item.skill_id == blueprint.id else item.enabled)
                   for item in before.entries]
        entries.append(RegistryEntry(blueprint.id, blueprint.version, blueprint.canonical_hash,
                                     blueprint.kind, True))
        after = MechanismRegistryManifest(before.epoch + 1,
                                          tuple(sorted(entries, key=lambda item: (item.skill_id, item.version))))
        self.blueprints[(blueprint.id, blueprint.version)] = blueprint
        try:
            return self._commit_change("install", before, after)
        except Exception:
            self.blueprints.pop((blueprint.id, blueprint.version), None)
            raise

    def disable(self, skill_id: str, version: int | None = None) -> RegistryChangeResult:
        before = self.manifest
        matches = [item for item in before.entries if item.skill_id == skill_id and item.enabled and
                   (version is None or item.version == version)]
        if len(matches) != 1:
            raise GameplayContractError("disable must identify one enabled skill version")
        selected = matches[0]
        self._assert_no_loadout_refs(selected.skill_id, selected.version)
        entries = tuple(RegistryEntry(item.skill_id, item.version, item.canonical_hash, item.kind,
                                      False if (item.skill_id, item.version) == (selected.skill_id, selected.version)
                                      else item.enabled)
                        for item in before.entries)
        return self._commit_change("disable", before, MechanismRegistryManifest(before.epoch + 1, entries))

    def _commit_change(self, operation: str, before: MechanismRegistryManifest,
                       after: MechanismRegistryManifest) -> RegistryChangeResult:
        registry_id, current = self._registry_entity()
        boundary = self._assert_boundary(current)
        after_component = registry_component(after, last_boundary_step=boundary)
        laws = self._compiled_laws(after)
        # Engine construction and World validation happen before the formal commit.
        build_runtime(deepcopy(self.session.state), discover_profiles(self.session.state), laws)
        result = self.session.runtime.run_event(Event(
            f"pmw:v04:registry:{after.epoch:08d}", REGISTRY_EVENT, self.session.state.sim_time,
            registry_id, None, {"operation": operation, "boundary_step": boundary,
                                "before": current, "after": after_component},
        ))
        if not result.changed:
            raise GameplayContractError("registry transaction did not commit")
        state = self.session.state
        self.session = build_runtime(state, discover_profiles(state), laws)
        return RegistryChangeResult(operation, before, after, result)

    def _assert_boundary(self, component: Mapping[str, Any]) -> int:
        registry_id, _ = self._registry_entity()
        clock = self.session.state.entities[registry_id].components["pmw_gameplay_clock"]
        completed = clock.get("last_completed_step")
        if (isinstance(completed, bool) or not isinstance(completed, int) or
                clock.get("next_step") != completed + 1 or
                abs(float(self.session.state.sim_time) - float(completed)) > 1e-9 or
                float(clock.get("next_time", -1)) <= self.session.state.sim_time):
            raise GameplayContractError("registry changes require a complete World Tick boundary")
        if component["last_boundary_step"] == completed:
            raise GameplayContractError("only one registry transaction is allowed per World Tick boundary")
        if any(event.time <= self.session.state.sim_time for event in self.session.state.scheduled_events):
            raise GameplayContractError("due Scheduler work must be drained before a registry change")
        return completed

    def _registry_entity(self) -> tuple[str, dict[str, Any]]:
        matches = [(entity.id, entity.components[REGISTRY_COMPONENT])
                   for entity in self.session.state.entities.values()
                   if REGISTRY_COMPONENT in entity.components and "pmw_gameplay_clock" in entity.components]
        if len(matches) != 1:
            raise GameplayContractError("world must contain one clock-owned mechanism registry")
        return matches[0]

    def _assert_no_loadout_refs(self, skill_id: str, version: int | None = None) -> None:
        for entity in self.session.state.entities.values():
            actor = entity.components.get("pmw_gameplay_actor")
            if not isinstance(actor, dict):
                continue
            for container in ("active_equipped", "active_stowed", "passive_equipped"):
                for row in actor.get(container, ()):
                    if (isinstance(row, dict) and row.get("id") == skill_id and
                            (version is None or row.get("version") == version)):
                        raise GameplayContractError(
                            "skill must be removed from every loadout before version or disable changes"
                        )

    def _active_registry(self, manifest: MechanismRegistryManifest | None = None) -> ActionRegistry:
        selected = manifest or self.manifest
        enabled = {(entry.skill_id, entry.version) for entry in selected.entries if entry.enabled}
        active = [self.blueprints[key] for key in sorted(enabled)]
        return ActionRegistry(
            (*self.base_registry.actions.values(), *(item.action for item in active)),
            self.base_registry.statuses.values(),
            (*self.base_registry.hooks.values(), *(passive_hook(item) for item in active
                                                   if item.kind == "passive_blueprint")),
        )

    def _compiled_laws(self, manifest: MechanismRegistryManifest | None = None) -> tuple[dict, ...]:
        selected = manifest or self.manifest
        laws: dict[str, dict] = {item["id"]: dict(item) for item in self.static_laws}
        active = self._active_registry(selected)
        for law in build_action_laws(active, status_slots=self.status_slots,
                                     dynamics_slots=self.dynamics_slots):
            laws[law["id"]] = law
        enabled = {(entry.skill_id, entry.version) for entry in selected.entries if entry.enabled}
        for key, blueprint in sorted(self.blueprints.items()):
            if key in enabled:
                continue
            retired = ActionRegistry((blueprint.action,), self.base_registry.statuses.values())
            for law in build_action_laws(retired, status_slots=self.status_slots,
                                         dynamics_slots=self.dynamics_slots):
                if ".expire" in law["id"] or law["id"].startswith("pmw.v04.status."):
                    previous = laws.get(law["id"])
                    if previous is not None and previous != law:
                        raise GameplayContractError("retired lifecycle Law collides with active runtime configuration")
                    laws[law["id"]] = law
        return tuple(laws[key] for key in sorted(laws))

    def _rebuild(self) -> None:
        state = self.session.state
        self.session = build_runtime(state, discover_profiles(state), self._compiled_laws())

    def _validate_formal_state(self) -> None:
        manifest = self.manifest
        for entry in manifest.entries:
            blueprint = self.blueprints.get((entry.skill_id, entry.version))
            if blueprint is None or blueprint.canonical_hash != entry.canonical_hash or blueprint.kind != entry.kind:
                raise GameplayContractError("formal registry manifest does not match installed blueprints")


def static_law_hash(laws: Iterable[Mapping[str, Any]]) -> str:
    canonical = json.dumps(list(laws), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode()).hexdigest()


def _dynamic_action_law(law_id: str) -> bool:
    return (law_id.startswith("pmw.v04.action.") or law_id.startswith("pmw.v04.hook.") or
            law_id.startswith("pmw.v04.status."))
