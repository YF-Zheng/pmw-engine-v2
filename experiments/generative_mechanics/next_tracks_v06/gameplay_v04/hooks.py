"""Bounded event hooks with deterministic lineage and automatic dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import hashlib
import json
import math
from typing import Any

from .conditions import ConditionSpec, evaluate_condition, parse_condition
from .contracts import GameplayContractError


TRIGGERS = ("action_started", "attack_applied", "damage_resolved", "status_changed",
            "weather_changed", "resource_harvested")
DAMAGE_NOTIFICATION = "pmw.v04.hook.damage_resolved"
ACTION_EVENT = "pmw.v04.action.resolve"
ACTOR_COMPONENT = "pmw_gameplay_actor"
REGISTRY_COMPONENT = "pmw_gameplay_mechanism_registry"
_NOTIFICATION_FIELDS = {
    "protocol", "action_id", "action_hash", "effect_id", "actor_id",
    "target_actor_id", "resolved_damage", "hp_loss", "shield_absorbed",
}


@dataclass(frozen=True, slots=True)
class HookDispatchLimits:
    max_depth: int = 16
    max_firings: int = 32
    max_notifications: int = 64

    def __post_init__(self) -> None:
        for name, value, maximum in (
            ("max_depth", self.max_depth, 16),
            ("max_firings", self.max_firings, 32),
            ("max_notifications", self.max_notifications, 64),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise GameplayContractError(
                    f"HookDispatchLimits.{name} must be an integer in [1, {maximum}]"
                )


@dataclass(frozen=True, slots=True)
class HookDispatchRecord:
    root_event_id: str
    notification_id: str
    parent_event_id: str
    hook_id: str
    owner: str
    depth: int
    status: str
    reason: str
    outcome: Any = None


@dataclass(frozen=True, slots=True)
class _NotificationProvenance:
    parent_event_id: str
    proposal_id: str
    action: Any
    damage_law: str
    hp_loss: float
    shield_absorbed: float


@dataclass(frozen=True, slots=True)
class HookSpec:
    id: str
    trigger: str
    condition: ConditionSpec
    effect_ids: tuple[str, ...]
    action_id: str
    max_firings_per_root: int
    cooldown: int = 0


@dataclass(frozen=True, slots=True)
class HookLineage:
    root_event_id: str
    parent_event_id: str | None
    depth: int
    remaining_budget: int
    fired_sources: tuple[str, ...] = ()

    def fire(self, source_key: str, *, max_depth: int = 16) -> "HookLineage":
        if self.depth >= max_depth or self.remaining_budget <= 0:
            raise GameplayContractError("hook cascade budget exhausted")
        if source_key in self.fired_sources:
            raise GameplayContractError("hook source already fired in this root lineage")
        return HookLineage(self.root_event_id, self.parent_event_id, self.depth + 1,
                           self.remaining_budget - 1, (*self.fired_sources, source_key))


def parse_hook(raw: Any, path: str = "$.hook") -> HookSpec:
    required = {"id", "trigger", "condition", "effect_ids", "action_id", "max_firings_per_root"}
    optional = {"cooldown"}
    if not isinstance(raw, dict) or set(raw) - required - optional or not required <= set(raw):
        raise GameplayContractError(f"{path} has missing or unknown fields")
    if not isinstance(raw["id"], str) or not raw["id"]: raise GameplayContractError(f"{path}.id is invalid")
    if raw["trigger"] not in TRIGGERS: raise GameplayContractError(f"{path}.trigger is invalid")
    effect_ids = raw["effect_ids"]
    if not isinstance(effect_ids, list) or not effect_ids or any(not isinstance(x, str) or not x for x in effect_ids) or len(set(effect_ids)) != len(effect_ids):
        raise GameplayContractError(f"{path}.effect_ids is invalid")
    budget = raw["max_firings_per_root"]
    cooldown = raw.get("cooldown", 0)
    for value, name, low in ((budget, "max_firings_per_root", 1), (cooldown, "cooldown", 0)):
        if isinstance(value, bool) or not isinstance(value, int) or value < low:
            raise GameplayContractError(f"{path}.{name} is invalid")
    if not isinstance(raw["action_id"], str) or not raw["action_id"]: raise GameplayContractError(f"{path}.action_id is invalid")
    return HookSpec(raw["id"], raw["trigger"], parse_condition(raw["condition"], f"{path}.condition"),
                    tuple(effect_ids), raw["action_id"], budget, cooldown)


def execute_hook(session, registry, hook: HookSpec, lineage: HookLineage, *, actor_id: str,
                 target_actor_id: str | None, trigger: str):
    """Execute a trusted hook action through the same PMW Effect pipeline."""
    from .actions import ActionRequest, _actor_view, _condition_context, _resolve_action
    from .conditions import evaluate_condition
    if trigger != hook.trigger: raise GameplayContractError("hook trigger mismatch")
    if registry.hooks.get(hook.id) != hook: raise GameplayContractError("hook is not installed in the trusted registry")
    action = registry.actions.get(hook.action_id)
    if action is None or tuple(effect.id for effect in action.effects) != hook.effect_ids:
        raise GameplayContractError("hook effect bundle does not match its trusted action")
    request = ActionRequest(f"hook_{lineage.depth}_{hook.id}", actor_id, hook.action_id, target_actor_id)
    actor = session.state.entities.get(actor_id)
    target = session.state.entities.get(target_actor_id) if target_actor_id else None
    shadow = {actor_id: _actor_view(actor)}
    if target is not None: shadow[target_actor_id] = _actor_view(target)
    if not evaluate_condition(hook.condition, _condition_context(session, request, shadow)):
        return None, lineage
    cooldowns = actor.components.get("pmw_gameplay_hooks", {}).get("cooldowns", {})
    if float(cooldowns.get(hook.id, -1.0)) > session.state.sim_time:
        raise GameplayContractError("hook is on cooldown")
    next_lineage = lineage.fire(f"hook:{hook.id}")
    context = {"hook_id": hook.id, "cooldown_until": session.state.sim_time + hook.cooldown}
    return _resolve_action(session, registry, request, execution_kind="hook", hook_context=context), next_lineage


@dataclass(frozen=True, slots=True)
class _QueuedNotification:
    event: Any
    trace: Any
    depth: int


class _Dispatcher:
    def __init__(self, session, registry, root_id: str, limits: HookDispatchLimits):
        self.session = session
        self.registry = registry
        self.root_id = root_id
        self.limits = limits
        self.queue = deque()
        self.notification_count = 0
        self.firing_count = 0
        self.fired_sources: set[tuple[str, str]] = set()
        self.hook_firings: dict[tuple[str, str], int] = {}
        self.records: list[HookDispatchRecord] = []

    def append(self, outcome, *, depth: int) -> None:
        for row in outcome.event_result.trace.events:
            if row.event.type == DAMAGE_NOTIFICATION:
                self.notification_count += 1
                if self.notification_count > self.limits.max_notifications:
                    raise GameplayContractError("hook notification budget exhausted")
                self.queue.append(_QueuedNotification(
                    row.event, outcome.event_result.trace, depth,
                ))

    def drain(self) -> tuple[HookDispatchRecord, ...]:
        while self.queue:
            self._consume(self.queue.popleft())
        return tuple(self.records)

    def _consume(self, queued: _QueuedNotification) -> None:
        notification = queued.event
        _validate_notification(notification, queued.trace, self.registry)
        notification_trace = next(
            (row for row in queued.trace.events if row.event.id == notification.id),
            None,
        )
        if notification_trace is None:
            raise GameplayContractError("damage notification trace is unavailable")
        owner = notification.target
        attacker = notification.source
        owner_entity = self.session.state.entities.get(owner)
        attacker_entity = self.session.state.entities.get(attacker)
        if owner_entity is None or ACTOR_COMPONENT not in owner_entity.components:
            return
        actor = owner_entity.components[ACTOR_COMPONENT]
        references = _equipped_references(actor)
        if not references:
            return
        if attacker_entity is None or ACTOR_COMPONENT not in attacker_entity.components:
            self._skip_references(queued, references, "notification endpoint is not an Actor")
            return
        candidates, invalid = _eligible_candidates(self.registry, references)
        if invalid:
            self._skip_references(queued, invalid, "formal passive equipment or bundle is invalid")
        if not candidates:
            return
        for _, binding in candidates:
            self._dispatch_candidate(
                queued, owner, attacker, binding,
            )

    def _dispatch_candidate(self, queued, owner, attacker, binding) -> None:
        from .actions import ActionRequest, _actor_view, _condition_context, _resolve_action

        notification = queued.event
        source = (owner, binding.hook.id)
        if source in self.fired_sources:
            self._record(
                queued, binding.hook, "skipped",
                "duplicate owner+hook source in this root",
            )
            return
        owner_entity = self.session.state.entities.get(owner)
        attacker_entity = self.session.state.entities.get(attacker)
        if (
            owner_entity is None
            or attacker_entity is None
            or ACTOR_COMPONENT not in owner_entity.components
            or ACTOR_COMPONENT not in attacker_entity.components
        ):
            self._record(queued, binding.hook, "skipped",
                         "current notification endpoint is not an Actor")
            return
        current = _authorize_binding(self.session, self.registry, owner, binding)
        if current is None:
            self._record(queued, binding.hook, "skipped",
                         "formal passive equipment or bundle is no longer current")
            return
        action, hook = current
        if owner_entity.components[ACTOR_COMPONENT].get("hp", 0) <= 0:
            self._record(queued, hook, "skipped", "owner is defeated")
            return
        if not _same_local_area(self.session, owner, attacker):
            self._record(
                queued, hook, "skipped",
                "owner and attacker are not uniquely colocated",
            )
            return
        if "pmw_gameplay_hooks" not in owner_entity.components:
            self._record(queued, hook, "skipped",
                         "owner has no trusted hook state")
            return
        request = ActionRequest(
            _request_id(self.root_id, notification.id, action, hook, owner),
            owner,
            hook.action_id,
            attacker,
        )
        shadow = {
            owner: _actor_view(owner_entity),
            attacker: _actor_view(attacker_entity),
        }
        context = {
            "root_event_id": self.root_id,
            "notification_id": notification.id,
            "depth": queued.depth,
            "hook_id": hook.id,
            "cooldown_until": self.session.state.sim_time + hook.cooldown,
        }
        if not evaluate_condition(
                hook.condition, _condition_context(self.session, request, shadow)):
            self._record(queued, hook, "skipped", "condition was false")
            return
        hooks_component = owner_entity.components["pmw_gameplay_hooks"]
        cooldowns = hooks_component.get("cooldowns", {})
        if float(cooldowns.get(hook.id, -1.0)) > self.session.state.sim_time:
            self._record(queued, hook, "skipped", "hook is on cooldown")
            return
        source = (owner, hook.id)
        if source in self.fired_sources:
            self._record(
                queued, hook, "skipped",
                "duplicate owner+hook source in this root",
            )
            return
        if queued.depth > self.limits.max_depth:
            raise GameplayContractError("hook depth budget exhausted")
        if self.firing_count >= self.limits.max_firings:
            raise GameplayContractError("hook firing budget exhausted")
        if self.hook_firings.get(source, 0) >= hook.max_firings_per_root:
            raise GameplayContractError("hook firing budget exhausted")
        self.fired_sources.add(source)
        self.firing_count += 1
        self.hook_firings[source] = self.hook_firings.get(source, 0) + 1
        hook_outcome = _resolve_action(
            self.session,
            self.registry,
            request,
            execution_kind="hook",
            hook_context=context,
            parent_event_id=notification.id,
        )
        self.records.append(HookDispatchRecord(
            self.root_id,
            notification.id,
            notification.id,
            hook.id,
            owner,
            queued.depth,
            "fired",
            "fired",
            hook_outcome,
        ))
        self.append(hook_outcome, depth=queued.depth + 1)

    def _skip_references(self, queued, references, reason: str) -> None:
        for _, reference in references:
            hook_id = (
                f"passive_{reference['id']}_v{reference['version']}"
                if isinstance(reference, dict)
                and isinstance(reference.get("id"), str)
                and isinstance(reference.get("version"), int)
                else ""
            )
            self.records.append(HookDispatchRecord(
                self.root_id,
                queued.event.id,
                queued.event.id,
                hook_id,
                queued.event.target,
                queued.depth,
                "skipped",
                reason,
                None,
            ))

    def _record(self, queued, hook: HookSpec, status: str, reason: str,
                outcome=None) -> None:
        self.records.append(HookDispatchRecord(
            self.root_id,
            queued.event.id,
            queued.event.id,
            hook.id,
            queued.event.target,
            queued.depth,
            status,
            reason,
            outcome,
        ))

def dispatch_action_hooks(session, registry, outcome, limits: HookDispatchLimits):
    """Drain this root's real damage notifications on the staged session."""
    if not isinstance(limits, HookDispatchLimits):
        raise GameplayContractError("dispatch limits must be trusted HookDispatchLimits")
    root_id = outcome.event_result.trace.root_event.id
    dispatcher = _Dispatcher(session, registry, root_id, limits)
    dispatcher.append(outcome, depth=1)
    records = dispatcher.drain()
    if not records:
        return outcome
    from dataclasses import replace
    return replace(outcome, auto_hooks=records)


def _validate_notification(notification, trace, registry) -> None:
    payload = _validated_payload(notification)
    actions = [
        action for action in registry.actions.values()
        if action.id == payload["action_id"]
        and action.canonical_hash == payload["action_hash"]
    ]
    if len(actions) != 1:
        raise GameplayContractError("damage notification does not identify one installed Action")
    action = actions[0]
    parent_id = notification.provenance["parent_event"]
    parents = [row for row in trace.events if row.event.id == parent_id]
    notifications = [row for row in trace.events if row.event.id == notification.id]
    if len(parents) != 1 or len(notifications) != 1:
        raise GameplayContractError("damage notification trace parent is missing or ambiguous")
    parent = parents[0]
    if parent.event.type != ACTION_EVENT:
        raise GameplayContractError("damage notification parent is not an Action event")
    effect = next(
        (item for item in action.effects if item.id == payload["effect_id"]),
        None,
    )
    if effect is None or effect.kind != "damage":
        raise GameplayContractError("damage notification effect is not a damage Effect")
    if (
        effect.target.kind == "self"
        and notification.target != parent.event.source
    ):
        raise GameplayContractError(
            "self-target damage notification does not target its Action source"
        )
    if (
        effect.target.kind == "target_actor"
        and notification.target != parent.event.payload.get("target_actor_id")
    ):
        raise GameplayContractError(
            "target_actor damage notification does not target the Action target"
        )
    prepared = parent.event.payload.get("effects", {}).get(effect.id)
    if (
        not isinstance(prepared, dict)
        or prepared.get("kind") != "damage"
        or prepared.get("status") != "applied"
        or prepared.get("target_id") != notification.target
        or parent.event.source != notification.source
        or parent.event.time != notification.time
        or parent.event.payload.get("action_id") != action.id
        or parent.event.payload.get("action_hash") != action.canonical_hash
    ):
        raise GameplayContractError("damage notification does not match its Action parent")
    token = f"{action.id}.v{action.version}.{action.canonical_hash[:12]}"
    damage_law = f"pmw.v04.action.{token}.effect.{payload['effect_id']}"
    proposals = [
        row for row in trace.proposals
        if row.emitted_event_id == notification.id
    ]
    if len(proposals) != 1:
        raise GameplayContractError("damage notification accepted emit is missing or ambiguous")
    proposal = proposals[0]
    if (
        proposal.status != "accepted"
        or proposal.op != "emit_event"
        or proposal.law_id != damage_law
        or proposal.cause_event_id != parent_id
    ):
        raise GameplayContractError("damage notification emit is not accepted from its exact Law")
    committed = any(
        proposal.proposal_id in commit.accepted_proposal_ids
        for commit in parent.commits
    )
    if not committed:
        raise GameplayContractError("damage notification emit was not committed with its Action")
    hp_loss = 0.0
    shield_absorbed = 0.0
    attributed = False
    for commit in parent.commits:
        for delta in commit.state_deltas:
            if delta.address.object_id != notification.target:
                continue
            if delta.address.path not in {
                (ACTOR_COMPONENT, "hp"), (ACTOR_COMPONENT, "shield"),
            }:
                continue
            if damage_law not in delta.law_ids:
                continue
            old = _finite_number(delta.old_value, "damage delta old value")
            new = _finite_number(delta.new_value, "damage delta new value")
            decrease = old - new
            if decrease < -1e-9:
                raise GameplayContractError("damage Law increased its attributed state")
            attributed = True
            if delta.address.path[-1] == "hp":
                hp_loss += max(0.0, decrease)
            else:
                shield_absorbed += max(0.0, decrease)
    if not attributed or hp_loss + shield_absorbed <= 0:
        raise GameplayContractError("damage notification lacks accepted hp/shield deltas")
    if (
        abs(hp_loss - float(payload["hp_loss"])) > 1e-9
        or abs(shield_absorbed - float(payload["shield_absorbed"])) > 1e-9
        or abs(hp_loss + shield_absorbed - float(payload["resolved_damage"])) > 1e-9
    ):
        raise GameplayContractError("damage notification totals differ from accepted deltas")
    return None


def _validated_payload(notification) -> dict[str, Any]:
    if notification.type != DAMAGE_NOTIFICATION:
        raise GameplayContractError("automatic dispatch requires a damage_resolved notification")
    provenance = notification.provenance
    if (
        not isinstance(provenance, dict)
        or provenance.get("kind") != "derived"
        or not isinstance(provenance.get("parent_event"), str)
    ):
        raise GameplayContractError("damage notification provenance is invalid")
    payload = notification.payload
    if not isinstance(payload, dict) or set(payload) != _NOTIFICATION_FIELDS:
        raise GameplayContractError("damage notification payload is invalid")
    if payload.get("protocol") != "pmw-gameplay-v0.4":
        raise GameplayContractError("damage notification protocol is invalid")
    for key in ("action_id", "action_hash", "effect_id", "actor_id", "target_actor_id"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise GameplayContractError(f"damage notification {key} is invalid")
    if payload["actor_id"] != notification.source:
        raise GameplayContractError("damage notification source differs from actor_id")
    if payload["target_actor_id"] != notification.target:
        raise GameplayContractError("damage notification target differs from target_actor_id")
    hp_loss = _finite_number(payload["hp_loss"], "damage notification hp_loss")
    shield_absorbed = _finite_number(
        payload["shield_absorbed"], "damage notification shield_absorbed",
    )
    resolved = _finite_number(
        payload["resolved_damage"], "damage notification resolved_damage",
    )
    if hp_loss < 0 or shield_absorbed < 0 or resolved <= 0:
        raise GameplayContractError("damage notification contains invalid losses")
    if abs(resolved - hp_loss - shield_absorbed) > 1e-9:
        raise GameplayContractError("damage notification totals are inconsistent")
    return payload


def _finite_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GameplayContractError(f"{name} is invalid")
    return float(value)


def _equipped_references(actor) -> tuple[tuple[int, Any], ...]:
    equipped = actor.get("passive_equipped")
    if not isinstance(equipped, list) or len(equipped) != 6:
        return ()
    return tuple(
        (slot, reference) for slot, reference in enumerate(equipped)
        if reference is not None
    )


def _eligible_candidates(registry, references):
    candidates, invalid = [], []
    for slot, reference in references:
        if (
            not isinstance(reference, dict)
            or set(reference) != {"id", "version", "canonical_hash", "kind"}
            or reference.get("kind") != "passive_blueprint"
        ):
            invalid.append((slot, reference))
            continue
        if (
            not isinstance(reference["id"], str)
            or not reference["id"]
            or isinstance(reference["version"], bool)
            or not isinstance(reference["version"], int)
            or reference["version"] < 1
            or not isinstance(reference["canonical_hash"], str)
            or len(reference["canonical_hash"]) != 64
        ):
            invalid.append((slot, reference))
            continue
        binding = registry.passive_bindings.get(
            (reference["id"], reference["version"])
        )
        if (
            binding is None
            or binding.skill_hash != reference["canonical_hash"]
            or binding.skill_kind != reference["kind"]
            or binding.hook.trigger != "damage_resolved"
        ):
            invalid.append((slot, reference))
            continue
        candidates.append((slot, binding))
    return tuple(candidates), tuple(invalid)


def _authorize_binding(session, registry, owner: str, expected):
    entries = [
        entity.components[REGISTRY_COMPONENT].get("entries")
        for entity in session.state.entities.values()
        if REGISTRY_COMPONENT in entity.components
    ]
    if len(entries) != 1 or not isinstance(entries[0], list):
        return None
    matches = [
        entry for entry in entries[0]
        if isinstance(entry, dict)
        and entry.get("skill_id") == expected.skill_id
        and entry.get("version") == expected.skill_version
        and entry.get("canonical_hash") == expected.skill_hash
        and entry.get("kind") == expected.skill_kind
        and entry.get("enabled") is True
    ]
    binding = registry.passive_bindings.get(
        (expected.skill_id, expected.skill_version)
    )
    actor_entity = session.state.entities.get(owner)
    actor = (
        None if actor_entity is None
        else actor_entity.components.get(ACTOR_COMPONENT)
    )
    equipped = None if not isinstance(actor, dict) else actor.get("passive_equipped")
    if not isinstance(equipped, list) or len(equipped) != 6:
        refs = []
    else:
        expected_ref = {
            "id": expected.skill_id,
            "version": expected.skill_version,
            "canonical_hash": expected.skill_hash,
            "kind": expected.skill_kind,
        }
        refs = [
            row for row in equipped
            if isinstance(row, dict) and row == expected_ref
        ]
    if len(matches) != 1 or binding != expected or len(refs) != 1:
        return None
    action = registry.actions.get(binding.skill_id)
    hook = registry.hooks.get(binding.hook.id)
    if (
        action is None
        or action.version != binding.skill_version
        or action.canonical_hash != binding.action_hash
        or hook != binding.hook
    ):
        return None
    return action, hook


def _same_local_area(session, owner: str, attacker: str) -> bool:
    def endpoint_areas(entity_id: str):
        return sorted(
            relation.target for relation in session.state.relations.values()
            if relation.type == "located_in" and relation.source == entity_id
        )
    owner_areas = endpoint_areas(owner)
    attacker_areas = endpoint_areas(attacker)
    if len(owner_areas) != 1 or owner_areas != attacker_areas:
        return False
    area = session.state.entities.get(owner_areas[0])
    return area is not None and "pmw_gameplay_area" in area.components


def _request_id(root_id: str, notification_id: str, action, hook: HookSpec,
                owner: str) -> str:
    material = json.dumps(
        [
            root_id,
            notification_id,
            hook.id,
            action.id,
            action.version,
            action.canonical_hash,
            owner,
        ],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return "ah" + hashlib.sha256(material).hexdigest()[:61]
